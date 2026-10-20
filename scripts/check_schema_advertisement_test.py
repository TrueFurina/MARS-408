# -*- coding: utf-8 -*-
"""check_schema_advertisement.py 自测（REA #31 的可执行证明）

为什么门禁脚本必须自测：一个"永远绿"的检查器比没有检查器更坏——它给出
"已检查、没问题"的错觉。本文件用**构造的快照**把三个分支都打一遍：

  1. 有环（A→B→A）且 --gate → 退出码 1（能拦住）
  2. 无环 → 退出码 0（不误伤）
  3. 快照缺失 / 零 paths → 退出码 2（fail-closed：照不到 ≠ 干净）

运行：python scripts/check_schema_advertisement_test.py
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_schema_advertisement as chk  # noqa: E402


def _snapshot(schemas: dict, response_schema: dict) -> dict:
    return {
        "openapi": "3.1.0",
        "paths": {
            "/probe": {
                "post": {
                    "responses": {
                        "200": {"content": {"application/json": {
                            "schema": response_schema}}}
                    }
                }
            }
        },
        "components": {"schemas": schemas},
    }


class CheckSchemaAdvertisementTest(unittest.TestCase):
    def _run(self, doc: dict | None, gate: bool = True) -> int:
        if doc is None:
            path = os.path.join(tempfile.gettempdir(), "nonexistent-openapi-probe.json")
            if os.path.exists(path):
                os.remove(path)
        else:
            fd, path = tempfile.mkstemp(suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(doc, f)
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                return chk.main(["--openapi", path] + (["--gate"] if gate else []))
        except SystemExit as e:      # fail-closed 路径用 sys.exit(2)
            return int(e.code or 0)
        finally:
            if doc is not None:
                os.remove(path)

    def test_cycle_is_caught_under_gate(self):
        """可到达环：Node.children → Node 自递归（最常见的树形结构写法）。"""
        doc = _snapshot(
            {"Node": {"type": "object", "properties": {
                "children": {"type": "array", "items": {"$ref": "#/components/schemas/Node"}}}}},
            {"$ref": "#/components/schemas/Node"},
        )
        self.assertEqual(self._run(doc, gate=True), 1, "有可达递归时 --gate 必须退出 1")

    def test_indirect_cycle_is_caught(self):
        """间接环：A → B → A，只在深层被引用，不能因为"不在第一层"就漏掉。"""
        doc = _snapshot(
            {
                "A": {"type": "object", "properties": {"b": {"$ref": "#/components/schemas/B"}}},
                "B": {"type": "object", "properties": {"a": {"$ref": "#/components/schemas/A"}}},
            },
            {"$ref": "#/components/schemas/A"},
        )
        self.assertEqual(self._run(doc, gate=True), 1)

    def test_dag_passes(self):
        doc = _snapshot(
            {
                "A": {"type": "object", "properties": {"b": {"$ref": "#/components/schemas/B"}}},
                "B": {"type": "object", "properties": {"x": {"type": "string"}}},
            },
            {"$ref": "#/components/schemas/A"},
        )
        self.assertEqual(self._run(doc, gate=True), 0, "无环快照不得被误伤")

    def test_report_only_does_not_block(self):
        doc = _snapshot(
            {"Node": {"type": "object", "properties": {"self": {"$ref": "#/components/schemas/Node"}}}},
            {"$ref": "#/components/schemas/Node"},
        )
        self.assertEqual(self._run(doc, gate=False), 0, "report-only 模式不阻断")

    def test_missing_snapshot_is_fail_closed(self):
        self.assertEqual(self._run(None), 2, "快照缺失必须退出 2（照不到 ≠ 干净）")

    def test_zero_operations_is_fail_closed(self):
        doc = {"openapi": "3.1.0", "paths": {}, "components": {"schemas": {}}}
        self.assertEqual(self._run(doc), 2)

    def test_unrelated_schema_cycle_does_not_block(self):
        """未被任何 operation 广告的环不算违规——检查的是"广告出去的"，不是全库。"""
        doc = _snapshot(
            {
                "Orphan": {"type": "object", "properties": {
                    "self": {"$ref": "#/components/schemas/Orphan"}}},
                "Used": {"type": "object", "properties": {"x": {"type": "string"}}},
            },
            {"$ref": "#/components/schemas/Used"},
        )
        self.assertEqual(self._run(doc, gate=True), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
