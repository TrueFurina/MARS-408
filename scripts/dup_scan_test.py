# -*- coding: utf-8 -*-
"""dup_scan.py 自测（REA #20：门禁必须能证明自己会红）

克隆扫描最容易出的问题不是"漏报"，是**口径漂移后永远绿**：
归一化把三引号字符串也折叠了 → 每段提示词都"互相克隆"（首跑实测 2651 组
假阳性）；或窗口步长写错 → 相邻窗口重复计数。故这里钉住三件事：

1. 归一化：字符串/数字折叠，但**三引号整段**必须抹成空行（否则提示词互相命中）；
2. 检测：两个文件里同样的 10 行代码 → 能找出同一指纹；
3. 不误伤：只有 9 行相同（窗口 10）或行多样性过低（重复字典）→ 不报。

运行：python scripts/dup_scan_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dup_scan as ds  # noqa: E402


class NormalizeTest(unittest.TestCase):
    def test_strings_and_numbers_collapse(self):
        a = ds._normalize('x = "hello" + 42')
        b = ds._normalize("x = 'world' + 7")
        self.assertEqual(a, b, "字符串/数字不同不应算不同代码")

    def test_block_strings_are_erased_but_lines_kept(self):
        text = 'def f():\n    """doc\n    line2\n    """\n    return 1\n'
        out = ds._strip_block_strings(text)
        self.assertNotIn("doc", out)
        self.assertEqual(out.count("\n"), text.count("\n"), "行数必须保持不变")


class WindowTest(unittest.TestCase):
    BODY = "\n".join([
        "def handler(req):",
        "    user = req.user",
        "    if not user:",
        "        raise ValueError('no user')",
        "    data = req.json()",
        "    for k, v in data.items():",
        "        if v is None:",
        "            continue",
        "        store[k] = v",
        "    return {'ok': True}",
    ]) + "\n"

    def _write(self, content: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".py")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        self.addCleanup(os.remove, path)
        return path

    def test_identical_block_in_two_files_shares_fingerprint(self):
        p1 = self._write("import os\n" + self.BODY)
        p2 = self._write("import sys\n" + self.BODY)
        d1 = {d for d, *_ in ds._windows(p1)}
        d2 = {d for d, *_ in ds._windows(p2)}
        self.assertTrue(d1 & d2, "同样的 10 行代码必须命中同一指纹")

    def test_nine_lines_is_below_window(self):
        short = "\n".join(self.BODY.splitlines()[:9]) + "\n"
        p = self._write(short)
        self.assertEqual(list(ds._windows(p)), [], "不足一个窗口不应产出指纹")

    def test_repetitive_dict_block_is_skipped(self):
        """重复的纯数据块（行多样性 < 5）不是可抽公共逻辑的克隆。"""
        blob = "DATA = [\n" + "    {'k': 1},\n" * 12 + "]\n"
        p = self._write(blob)
        self.assertEqual(list(ds._windows(p)), [])

    def test_block_string_bodies_do_not_match(self):
        a = self._write('PROMPT = """\n' + "同一段提示词\n" * 12 + '"""\n')
        b = self._write('OTHER = """\n' + "同一段提示词\n" * 12 + '"""\n')
        self.assertFalse({d for d, *_ in ds._windows(a)} & {d for d, *_ in ds._windows(b)},
                         "提示词/文档字符串不得互相判为克隆")


if __name__ == "__main__":
    unittest.main(verbosity=2)
