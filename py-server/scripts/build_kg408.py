#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ============================================================
# build_kg408.py — 408 知识图谱骨架「单一真源」生成器
#
# 用法（在 py-server 目录下）：
#   python scripts/build_kg408.py \
#       --source "E:/Program/MARL/SAGE/pdf/03_408知识图谱骨架.html" \
#       --out-dir data/kg408
#
# 设计约束（架构设计 §3 / §8）：
#   D3 可复现：ID 由「源表格行序」生成（不由内容生成），连跑两次 git diff 为空。
#   零第三方依赖：仅标准库 html.parser / re / json / hashlib / argparse。
#   诚信红线：未解析引用一律写 unresolved.json 如实挂起，禁止模糊相似度兜底。
#   跨科边权重：源未提供任何数值 → weight=null + not_provided_by_source。
# ============================================================

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── 让脚本可以直接 `python scripts/build_kg408.py` 运行 ──────────
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.kg408 import (  # noqa: E402
    EDGE_ASSOCIATION,
    EDGE_PREREQUISITE,
    LEVEL_CHAPTER,
    LEVEL_KP,
    LEVEL_SUBJECT,
    ORIGIN_MANUAL,
    ORIGIN_SOURCE,
    REASON_ABSENT,
    REASON_AMBIGUOUS,
    REASON_CHAPTER_ONLY,
    RES_ALIAS,
    RES_EXACT,
    SUBJECT_CODES,
    SUBJECT_NAMES,
    WEIGHT_NOT_APPLICABLE,
    WEIGHT_NOT_PROVIDED,
    Kg408,
    KgEdge,
    KgNode,
    Provenance,
    UnresolvedRef,
    build_stats,
)

GENERATOR_VERSION = "1.0.0"
PARSER_RULE_VERSION = "kg408-parse-r1"
SCHEMA_VERSION = "kg408/v1"

DEFAULT_SOURCE = "E:/Program/MARL/SAGE/pdf/03_408知识图谱骨架.html"
DEFAULT_OUT_DIR = "data/kg408"
DEFAULT_DOC_OUT = "deliverables/408-kg/kg408-stats.md"

KP_SPLIT_RE = re.compile(r"[、,，;；]")
SUBJ_CODE_RE = re.compile(r"[（(](DS|CO|OS|CN)[）)]")
DASH_CELLS = {"—", "-", "--", "—", "", "—"}


def _log(msg: str) -> None:
    """stdout 输出；Windows GBK 控制台下对不可编码字符做安全降级。"""
    try:
        sys.stdout.write(msg + "\n")
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        sys.stdout.write(msg.encode(enc, "backslashreplace").decode(enc) + "\n")


# ============================================================
# 解析器
# ============================================================
class HtmlSkeletonParser:
    """解析 03_408知识图谱骨架.html 的三张表。

    仅用标准库 HTMLParser。表格按出现顺序分类：
      - 2 列且首表头含「章」           → 章/考点表（每科目一张）
      - 2 列且表头含「目标考点」        → 先修边表
      - 5 列且首表头为「关联」          → 跨科关联表
    """

    def __init__(self, html: str) -> None:
        self._html = html
        self._tables: List[Dict[str, Any]] = []
        self._headings: List[Dict[str, Any]] = []
        self._parse()

    # ── 内部结构 ──────────────────────────────────────────────
    class _Collector(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.tables: List[Dict[str, Any]] = []
            self.headings: List[Dict[str, Any]] = []
            self._cur_table: Optional[Dict[str, Any]] = None
            self._cur_row: Optional[Dict[str, Any]] = None
            self._cell: Optional[List[str]] = None
            self._in_cell = False
            self._cell_is_header = False
            self._cur_heading: Optional[Dict[str, Any]] = None
            self._last_heading_text = ""

        def handle_starttag(self, tag: str, attrs: Any) -> None:
            if tag in ("h1", "h2", "h3", "h4"):
                self._cur_heading = {
                    "level": tag,
                    "text": "",
                    "line": self.getpos()[0],
                }
            elif tag == "table":
                self._cur_table = {
                    "heading": self._last_heading_text,
                    "header": [],
                    "rows": [],
                }
            elif tag == "tr":
                self._cur_row = {"cells": [], "is_header": False, "line": self.getpos()[0]}
            elif tag in ("td", "th"):
                self._in_cell = True
                self._cell_is_header = tag == "th"
                self._cell = []

        def handle_endtag(self, tag: str) -> None:
            if tag in ("h1", "h2", "h3", "h4"):
                if self._cur_heading is not None:
                    self._cur_heading["text"] = " ".join(
                        self._cur_heading["text"].split()
                    )
                    self.headings.append(self._cur_heading)
                    self._last_heading_text = self._cur_heading["text"]
                    self._cur_heading = None
            elif tag in ("td", "th"):
                if self._cur_row is not None and self._cell is not None:
                    text = " ".join("".join(self._cell).split())
                    self._cur_row["cells"].append(text)
                    if self._cell_is_header:
                        self._cur_row["is_header"] = True
                self._in_cell = False
                self._cell = None
                self._cell_is_header = False
            elif tag == "tr":
                if self._cur_table is not None and self._cur_row is not None:
                    if self._cur_row["cells"]:
                        self._cur_table["rows"].append(self._cur_row)
                self._cur_row = None
            elif tag == "table":
                if self._cur_table is not None:
                    self.tables.append(self._cur_table)
                self._cur_table = None

        def handle_data(self, data: str) -> None:
            if self._cur_heading is not None:
                self._cur_heading["text"] += data
            elif self._in_cell and self._cell is not None:
                self._cell.append(data)

    def _parse(self) -> None:
        c = self._Collector()
        c.feed(self._html)
        c.close()
        self._tables = c.tables
        self._headings = c.headings
        for t in self._tables:
            for r in t["rows"]:
                if r["is_header"]:
                    t["header"] = list(r["cells"])
            t["rows"] = [r for r in t["rows"] if not r["is_header"]]

    # ── 对外接口 ──────────────────────────────────────────────
    def parse_subjects(self) -> List[Dict[str, Any]]:
        """返回 4 个科目：[{code, name, line}]，按文中出现顺序。"""
        out: List[Dict[str, Any]] = []
        for h in self._headings:
            m = SUBJ_CODE_RE.search(h["text"])
            if not m:
                continue
            code = m.group(1)
            if code in SUBJECT_CODES and all(o["code"] != code for o in out):
                name = SUBJ_CODE_RE.sub("", h["text"]).strip()
                out.append(
                    {"code": code, "name": name or SUBJECT_NAMES[code], "line": h["line"]}
                )
        return out

    def parse_chapter_rows(self, subject: str) -> List[Dict[str, Any]]:
        """返回某科目的章行：[{chapter, points:[...], line}]。"""
        code = str(subject).strip().upper()
        out: List[Dict[str, Any]] = []
        for t in self._tables:
            hdr = t.get("header") or []
            if len(hdr) != 2 or "章" not in str(hdr[0]):
                continue
            m = SUBJ_CODE_RE.search(str(t.get("heading", "")))
            if not m or m.group(1) != code:
                continue
            for r in t["rows"]:
                cells = r["cells"]
                if len(cells) < 2:
                    continue
                chapter = cells[0].strip()
                points = self._split_points(cells[1])
                if not chapter:
                    continue
                out.append({"chapter": chapter, "points": points, "line": r["line"]})
        return out

    def parse_prereq_rows(self) -> List[Dict[str, Any]]:
        """返回先修边声明行：[{target, prereqs:[...], line}]。"""
        out: List[Dict[str, Any]] = []
        for t in self._tables:
            hdr = t.get("header") or []
            if len(hdr) != 2 or "目标考点" not in "".join(hdr):
                continue
            for r in t["rows"]:
                cells = r["cells"]
                if len(cells) < 2:
                    continue
                target = cells[0].strip()
                prereqs = [p for p in self._split_points(cells[1]) if p]
                if not target:
                    continue
                out.append({"target": target, "prereqs": prereqs, "line": r["line"]})
        return out

    def parse_cross_rows(self) -> List[Dict[str, Any]]:
        """返回跨科关联行：[{assoc, cells:{DS:..,CO:..,OS:..,CN:..}, line}]。"""
        out: List[Dict[str, Any]] = []
        for t in self._tables:
            hdr = t.get("header") or []
            if len(hdr) != 5 or "关联" not in str(hdr[0]):
                continue
            cols = [str(h).strip() for h in hdr[1:5]]
            for r in t["rows"]:
                cells = r["cells"]
                if len(cells) < 5:
                    continue
                assoc = cells[0].strip()
                if not assoc:
                    continue
                mapping: Dict[str, str] = {}
                for idx, code in enumerate(cols):
                    raw = cells[idx + 1].strip()
                    if code in SUBJECT_CODES and raw not in DASH_CELLS:
                        mapping[code] = raw
                out.append({"assoc": assoc, "cells": mapping, "line": r["line"]})
        return out

    def table_row_index(self) -> Dict[str, Any]:
        """返回解析到的表格结构摘要（供统计与自检）。"""
        return {
            "tables_total": len(self._tables),
            "headings_total": len(self._headings),
            "tables": [
                {
                    "heading": t.get("heading", ""),
                    "header": t.get("header", []),
                    "row_count": len(t["rows"]),
                }
                for t in self._tables
            ],
        }

    @staticmethod
    def _split_points(text: str) -> List[str]:
        """按「、」等分隔符切分考点单元格；不切分括号内的内容。"""
        raw = str(text or "").strip()
        if not raw:
            return []
        parts: List[str] = []
        buf: List[str] = []
        depth = 0
        for ch in raw:
            if ch in "（(":
                depth += 1
            elif ch in "）)":
                depth = max(0, depth - 1)
            if depth == 0 and KP_SPLIT_RE.match(ch):
                parts.append("".join(buf).strip())
                buf = []
            else:
                buf.append(ch)
        parts.append("".join(buf).strip())
        return [p for p in parts if p]


# ============================================================
# 名称解析器
# ============================================================
class NameResolver:
    """按 §8.4 优先级解析：exact → alias → (chapter_level/挂起)。

    **不设模糊相似度兜底**：宁可挂起，不可错配。
    """

    def __init__(self, nodes: List[KgNode], alias_entries: List[Dict[str, Any]]) -> None:
        self._nodes = nodes
        self._unresolved: List[UnresolvedRef] = []
        self._alias: Dict[str, Dict[str, Any]] = {}
        for e in alias_entries:
            raw = str(e.get("raw", "")).strip()
            if raw:
                self._alias[raw] = e
        # (subject, chapter, label) → node
        self._triple: Dict[Tuple[str, str, str], KgNode] = {}
        # label → [nodes]（用于 exact 全局唯一性判定）
        self._by_label: Dict[str, List[KgNode]] = {}
        # chapter 名 → [chapter nodes]（用于 chapter_level 判定）
        self._chapter_names: Dict[str, List[KgNode]] = {}
        self._kp_nodes: List[KgNode] = []
        for n in nodes:
            if n.level == LEVEL_KP:
                key = (n.subject, str(n.chapter or ""), n.label)
                self._triple[key] = n
                self._by_label.setdefault(n.label, []).append(n)
                self._kp_nodes.append(n)
            elif n.level == LEVEL_CHAPTER:
                self._chapter_names.setdefault(n.label, []).append(n)

    # ── 主入口 ────────────────────────────────────────────────
    def resolve(self, raw: str, subject_hint: Optional[str] = None) -> Optional[KgNode]:
        """解析一个原始引用名；失败返回 None。"""
        name = " ".join(str(raw or "").split())
        if not name:
            return None
        cands = self._by_label.get(name, [])
        if subject_hint:
            scoped = [c for c in cands if c.subject == subject_hint]
            if scoped:
                cands = scoped
        if len(cands) == 1:
            return cands[0]
        if len(cands) > 1:
            return None
        ent = self._alias.get(name)
        if ent is not None:
            if subject_hint and str(ent.get("subject", "")).upper() != subject_hint:
                return None
            node = self._triple.get(
                (
                    str(ent.get("subject", "")).upper(),
                    str(ent.get("chapter", "")),
                    str(ent.get("label", "")),
                )
            )
            return node
        return None

    def resolution_of(self, raw: str, subject_hint: Optional[str] = None) -> str:
        """返回该引用命中的解析方式（exact/alias）。仅在 resolve 成功后调用。"""
        name = " ".join(str(raw or "").split())
        cands = self._by_label.get(name, [])
        if subject_hint:
            scoped = [c for c in cands if c.subject == subject_hint]
            if scoped:
                cands = scoped
        if cands:
            return RES_EXACT
        return RES_ALIAS

    def classify_failure(self, raw: str, subject_hint: Optional[str] = None) -> Tuple[str, str, str]:
        """失败时给出 (reason, detail, suggested_action)。"""
        name = " ".join(str(raw or "").split())
        cands = self._by_label.get(name, [])
        if subject_hint:
            cands = [c for c in cands if c.subject == subject_hint]
        if len(cands) > 1:
            where = "、".join(f"{c.subject}/{c.chapter}" for c in cands)
            return (
                REASON_AMBIGUOUS,
                f"骨架中有 {len(cands)} 个同名考点（{where}），源文本未给章前缀，无法消歧。",
                "人工裁定：补章前缀后重跑，或删除该声明。",
            )
        chapters = self._chapter_names.get(name, [])
        if chapters:
            where = "、".join(f"{c.subject}/{c.label}" for c in chapters)
            return (
                REASON_CHAPTER_ONLY,
                f"「{name}」命中章名而非考点名（{where}）。",
                "人工裁定：改为章级先修（补章级边），或补具体考点节点后重跑。",
            )
        extra = self._compound_hint(name)
        detail = f"骨架中不存在名为「{name}」的考点，也无同名章。"
        action = "人工裁定：补考点节点（resolution=manual），或删除该声明。"
        if extra:
            detail += f" {extra}"
            action = "人工裁定：拆分为多个独立声明后重跑（本阶段**不自动拆分**），或删除该声明。"
        return (REASON_ABSENT, detail, action)

    def _compound_hint(self, name: str) -> str:
        """对含『/』的复合引用给出「疑似指向哪些考点」的诊断提示。

        仅用于**人工裁定参考**，绝不据此自动绑定（resolver 不读本方法）。
        """
        if "/" not in name:
            return ""
        parts = [p.strip() for p in name.split("/") if p.strip()]
        hits: List[str] = []
        for p in parts:
            matched = [
                n
                for n in self._kp_nodes
                if p == n.label or p in n.label or n.label in p
            ]
            if matched:
                where = "、".join(
                    f"{m.subject}/{m.chapter}/{m.label}" for m in matched[:2]
                )
                hits.append(f"「{p}」疑似→{where}")
        if not hits:
            return (
                "注意：原文含『/』，疑似把多个考点写在同一单元格，"
                "需人工拆分（本阶段**不自动拆分**）。"
            )
        return (
            "注意：原文含『/』，疑似复合引用——"
            + "；".join(hits)
            + "。本阶段**不自动拆分绑定**，需人工裁定。"
        )

    def record_unresolved(
        self,
        kind: str,
        raw: str,
        subject_hint: Optional[str],
        context_row: int,
        context: str,
    ) -> None:
        """登记一条未解析引用（诚信产物）。"""
        reason, detail, action = self.classify_failure(raw, subject_hint)
        self._unresolved.append(
            UnresolvedRef(
                kind=kind,
                raw_name=raw,
                subject_hint=subject_hint,
                context_row=context_row,
                context=context,
                reason=reason,
                detail=detail,
                suggested_action=action,
            )
        )

    def unresolved(self) -> List[UnresolvedRef]:
        """返回已登记的未解析清单。"""
        return list(self._unresolved)


# ============================================================
# 构建器
# ============================================================
class Kg408Builder:
    """解析 → 解析名 → 建图 → 落盘 → 出统计。"""

    def __init__(
        self,
        html: str,
        source_path: str,
        source_sha256: str,
        source_bytes: int,
        source_mtime_utc: str,
        command: str,
        alias_entries: List[Dict[str, Any]],
        chapter_map: Dict[str, Any],
        manual_nodes: Optional[List[Dict[str, Any]]] = None,
        alias_path: str = "",
        alias_sha256: str = "",
        chapter_map_path: str = "",
        chapter_map_sha256: str = "",
        manual_nodes_path: str = "",
        manual_nodes_sha256: str = "",
    ) -> None:
        self._parser = HtmlSkeletonParser(html)
        self._alias_entries = alias_entries
        self._chapter_map = chapter_map
        self._manual_nodes = list(manual_nodes or [])
        self._provenance = Provenance(
            source_path=source_path,
            source_sha256=source_sha256,
            source_bytes=source_bytes,
            source_mtime_utc=source_mtime_utc,
            alias_path=alias_path,
            alias_sha256=alias_sha256,
            chapter_map_path=chapter_map_path,
            chapter_map_sha256=chapter_map_sha256,
            manual_nodes_path=manual_nodes_path,
            manual_nodes_sha256=manual_nodes_sha256,
            generator="scripts/build_kg408.py",
            generator_version=GENERATOR_VERSION,
            parser_rule_version=PARSER_RULE_VERSION,
            command=command,
            generated_at_utc=source_mtime_utc,
            generated_at_utc_basis="source_file_mtime_utc__deterministic",
        )
        self._resolver: Optional[NameResolver] = None
        self._counter = {"prereq": 0, "cross": 0}
        self._counts = {
            "prereq_rows": 0,
            "prereq_declarations": 0,
            # QA GAP-3.2：与「声明数」同单位的分子——**已解析成边的声明数**。
            # 不能拿「边数」当分子：一条声明将来若产出多条边（或反之），
            # 分子分母单位不一致，成功率会失真。
            "prereq_declarations_resolved": 0,
            "cross_rows": 0,
            "cross_refs": 0,
        }

    # ── 主入口 ────────────────────────────────────────────────
    def build(self) -> Kg408:
        """构建整张图。"""
        nodes = self._build_hierarchy()
        self._resolver = NameResolver(nodes, self._alias_entries)
        self._attach_aliases(nodes)
        prereq_edges = self._build_prereq_edges()
        cross_edges = self._build_cross_edges()
        edges = prereq_edges + cross_edges
        unresolved = self._resolver.unresolved()
        source_counts = self._emit_stats()
        # 唯一统计口径：build_stats。source_counts 是文档级声明计数，
        # 随 kg408.json 持久化，使「重算 == 落盘」在派生产物上可被强制校验。
        stats = build_stats(nodes, edges, unresolved, source_counts)
        return Kg408(
            nodes=nodes,
            edges=edges,
            provenance=self._provenance,
            unresolved=unresolved,
            stats=stats,
            source_counts=source_counts,
        )

    # ── 三级层级 ──────────────────────────────────────────────
    def _group_of(self, subject: str, chapter: Optional[str]) -> Optional[int]:
        """按章节映射表取 group；映射不上返回 null（不伪造）。"""
        if not chapter:
            return None
        for m in self._chapter_map.get("mapping", []):
            if m.get("subject") == subject and m.get("chapter") == chapter:
                g = m.get("group", None)
                return int(g) if g is not None else None
        return None

    def _build_hierarchy(self) -> List[KgNode]:
        """生成 科目(4) → 章(26) → 考点(105) 三级节点，共 135 个。"""
        nodes: List[KgNode] = []
        subjects = self._parser.parse_subjects()
        for s_idx, s in enumerate(subjects, start=1):
            code = s["code"]
            nodes.append(
                KgNode(
                    id=f"408:{code}",
                    label=SUBJECT_NAMES.get(code, s["name"]),
                    level=LEVEL_SUBJECT,
                    subject=code,
                    chapter=None,
                    parent_id=None,
                    ordinal=s_idx,
                    source_row=s["line"],
                    aliases=[code],
                    group=None,
                    origin=ORIGIN_SOURCE,
                )
            )
            chapter_rows = self._parser.parse_chapter_rows(code)
            for c_idx, row in enumerate(chapter_rows, start=1):
                cid = f"408:{code}:CH{c_idx:02d}"
                chapter = row["chapter"]
                nodes.append(
                    KgNode(
                        id=cid,
                        label=chapter,
                        level=LEVEL_CHAPTER,
                        subject=code,
                        chapter=chapter,
                        parent_id=f"408:{code}",
                        ordinal=c_idx,
                        source_row=row["line"],
                        aliases=[],
                        group=self._group_of(code, chapter),
                        origin=ORIGIN_SOURCE,
                    )
                )
                for k_idx, point in enumerate(row["points"], start=1):
                    nodes.append(
                        KgNode(
                            id=f"{cid}:KP{k_idx:02d}",
                            label=point,
                            level=LEVEL_KP,
                            subject=code,
                            chapter=chapter,
                            parent_id=cid,
                            ordinal=k_idx,
                            source_row=row["line"],
                            aliases=[],
                            group=self._group_of(code, chapter),
                            origin=ORIGIN_SOURCE,
                        )
                    )
        nodes.extend(self._build_manual_nodes(nodes))
        return nodes

    # ── 人工补充节点（学科负责人裁决落点）────────────────────
    def _build_manual_nodes(self, existing: List[KgNode]) -> List[KgNode]:
        """由 kg408_manual_nodes.json 生成人工补充节点。

        这些节点**不是源骨架数据**：node.origin = "manual"，统计与报告里
        必须与 origin="source" 的节点分列，禁止合并成一个数字。
        id 在表里显式锁定；与源节点冲突时直接报错退出（不静默覆盖）。
        """
        out: List[KgNode] = []
        existing_ids = {n.id for n in existing}
        for spec in self._manual_nodes:
            nid = str(spec.get("id", "")).strip()
            if not nid:
                raise SystemExit("[build_kg408] 人工补充节点缺少 id")
            if nid in existing_ids:
                raise SystemExit(
                    f"[build_kg408] 人工补充节点 id 与源节点冲突: {nid}"
                    "（拒绝静默覆盖；请改 id 或复核源骨架）"
                )
            subject = str(spec.get("subject", "")).strip().upper()
            chapter = str(spec.get("chapter", "")).strip()
            parent = self._chapter_node_id(subject, chapter, existing)
            if parent is None:
                raise SystemExit(
                    f"[build_kg408] 人工补充节点 {nid} 的挂载章不存在: {subject}/{chapter}"
                )
            existing_ids.add(nid)
            out.append(
                KgNode(
                    id=nid,
                    label=str(spec.get("label", "")).strip(),
                    level=str(spec.get("level", LEVEL_KP)),
                    subject=subject,
                    chapter=chapter,
                    parent_id=parent,
                    ordinal=int(spec.get("ordinal", 0) or 0),
                    source_row=0,  # 人工节点无源表格行
                    aliases=list(spec.get("aliases", []) or []),
                    group=self._group_of(subject, chapter),
                    origin=ORIGIN_MANUAL,
                )
            )
        return out

    def _chapter_node_id(
        self, subject: str, chapter: str, nodes: List[KgNode]
    ) -> Optional[str]:
        """按 (subject, chapter 名) 找章节点 id。"""
        for n in nodes:
            if n.level == LEVEL_CHAPTER and n.subject == subject and n.label == chapter:
                return n.id
        return None

    def _attach_aliases(self, nodes: List[KgNode]) -> None:
        """把 alias 表中的 raw 名反向挂到目标节点的 aliases 字段（去重后排序）。"""
        rev: Dict[str, List[str]] = {}
        for e in self._alias_entries:
            key = (
                str(e.get("subject", "")).upper(),
                str(e.get("chapter", "")),
                str(e.get("label", "")),
            )
            raw = str(e.get("raw", "")).strip()
            if not raw:
                continue
            for n in nodes:
                if n.level == LEVEL_KP and (n.subject, str(n.chapter or ""), n.label) == key:
                    rev.setdefault(n.id, []).append(raw)
                    break
        for n in nodes:
            if n.id in rev:
                merged = sorted(set(list(n.aliases) + rev[n.id]))
                n.aliases = merged
            else:
                n.aliases = sorted(set(n.aliases))

    # ── 先修边 ────────────────────────────────────────────────
    def _build_prereq_edges(self) -> List[KgEdge]:
        """构建 prerequisite 边。方向：source=目标考点，target=先修考点。"""
        assert self._resolver is not None
        edges: List[KgEdge] = []
        rows = self._parser.parse_prereq_rows()
        self._counts["prereq_rows"] = len(rows)
        for row in rows:
            target_raw = row["target"]
            tnode = self._resolver.resolve(target_raw, None)
            if tnode is None:
                self._resolver.record_unresolved(
                    "prerequisite_target", target_raw, None, row["line"], target_raw
                )
            hint = tnode.subject if tnode is not None else None
            for p_raw in row["prereqs"]:
                self._counts["prereq_declarations"] += 1
                pnode = self._resolver.resolve(p_raw, hint)
                if pnode is None:
                    self._resolver.record_unresolved(
                        "prerequisite", p_raw, hint, row["line"], target_raw
                    )
                    continue
                if tnode is None:
                    # 目标未解析 → 该声明整体挂起（已在上面登记 target）
                    continue
                if pnode.id == tnode.id:
                    continue
                self._counter["prereq"] += 1
                # 与分母（声明数）同单位：本条声明成功解析成了边
                self._counts["prereq_declarations_resolved"] += 1
                edge = KgEdge(
                    id=f"408:E:PRE{self._counter['prereq']:04d}",
                    source=tnode.id,
                    target=pnode.id,
                    type=EDGE_PREREQUISITE,
                    directed=True,
                    weight=None,
                    weight_source=WEIGHT_NOT_APPLICABLE,
                    subject_scope="intra" if pnode.subject == tnode.subject else "cross",
                    # QA M7：两端各自留痕，避免「起点靠别名、终点精确」
                    # 的边被整体记成 exact 而低估人工映射覆盖面。
                    source_resolution=self._resolver.resolution_of(target_raw, None),
                    target_resolution=self._resolver.resolution_of(p_raw, hint),
                    source_row=row["line"],
                    evidence=f"{target_raw} ← {p_raw}",
                )
                edge.sync_resolution()
                edges.append(edge)
        return edges

    # ── 跨科关联边 ────────────────────────────────────────────
    def _build_cross_edges(self) -> List[KgEdge]:
        """构建 association 边：行内团扩展（C(k,2)）。"""
        assert self._resolver is not None
        edges: List[KgEdge] = []
        rows = self._parser.parse_cross_rows()
        self._counts["cross_rows"] = len(rows)
        for row in rows:
            assoc = row["assoc"]
            resolved: List[Tuple[KgNode, str]] = []
            for code in SUBJECT_CODES:
                raw = row["cells"].get(code)
                if not raw:
                    continue
                self._counts["cross_refs"] += 1
                node = self._resolver.resolve(raw, code)
                if node is None:
                    self._resolver.record_unresolved(
                        "cross_subject", raw, code, row["line"], assoc
                    )
                    continue
                resolved.append((node, self._resolver.resolution_of(raw, code)))
            uniq: List[Tuple[KgNode, str]] = []
            seen = set()
            for n, res in resolved:
                if n.id not in seen:
                    seen.add(n.id)
                    uniq.append((n, res))
            for i in range(len(uniq)):
                for j in range(i + 1, len(uniq)):
                    a, res_a = uniq[i]
                    b, res_b = uniq[j]
                    self._counter["cross"] += 1
                    edge = KgEdge(
                        id=f"408:E:XSUB{self._counter['cross']:04d}",
                        source=a.id,
                        target=b.id,
                        type=EDGE_ASSOCIATION,
                        directed=False,
                        weight=None,
                        weight_source=WEIGHT_NOT_PROVIDED,
                        subject_scope="cross",
                        source_resolution=res_a,
                        target_resolution=res_b,
                        source_row=row["line"],
                        evidence=f"{assoc}：{a.subject}-{a.label} ↔ {b.subject}-{b.label}",
                    )
                    edge.sync_resolution()
                    edges.append(edge)
        return edges

    def _emit_stats(self) -> Dict[str, Any]:
        """源文档侧的声明计数（与最终解析结果并列，便于核对损耗）。"""
        return {
            "source_prereq_rows": self._counts["prereq_rows"],
            "source_prereq_declarations": self._counts["prereq_declarations"],
            "source_prereq_declarations_resolved": self._counts[
                "prereq_declarations_resolved"
            ],
            "source_cross_rows": self._counts["cross_rows"],
            "source_cross_refs": self._counts["cross_refs"],
        }


# ============================================================
# 落盘
# ============================================================
def _write_json(path: Path, payload: Any) -> None:
    """以 UTF-8 + 2 空格缩进 + 尾换行 + **LF** 写 JSON（字节级稳定）。

    `newline=""` 是刻意的：Windows 下 `write_text` 默认把 `\\n` 翻成 `\\r\\n`，
    会让「逐字节可复现」只在 Windows 内成立、跨平台（Linux CI）失效。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)
    _write_text_lf(path, text + "\n")


def _write_text_lf(path: Path, text: str) -> None:
    """UTF-8 落盘且**不翻译换行**（永远写 LF，保证跨平台逐字节一致）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(text)


def render_stats_md(kg: Kg408) -> str:
    """渲染可引用的统计产物（带 provenance 区块）。

    刻意不含墙钟时刻 → 连跑两次逐字节一致（`git diff` 为空）。
    """
    p = kg.provenance
    s = kg.stats
    bs = s.get("by_subject", {})
    rc = s.get("unresolved_by_reason", {})
    res = s.get("resolution_counts", {})

    def _bar(v: int, total: int) -> str:
        if total <= 0:
            return "0.0%"
        return f"{v * 100.0 / total:.1f}%"

    lines: List[str] = []
    lines.append("# 408 知识图谱骨架 — 可引用统计（kg408）")
    lines.append("")
    lines.append(
        "> 本文件由 `scripts/build_kg408.py` **自动生成**，数字取自 "
        "`data/kg408/kg408.json` 真值。"
    )
    lines.append(">")
    lines.append(
        "> **防伪证（用哪条命令）**：`scripts/verify_kg408.py` **无参 = 全量**"
        "（关卡 1 结构自检 + 关卡 2 重跑逐字节比对 + 关卡 3 文档数字断言），"
        "任一不一致 → exit 1。**本项目要求以无参全量为准。**"
    )
    lines.append(
        "> ⚠️ `--check-doc` 与 `--no-repro` 都是**弱模式**，仅供快速自查："
        "`--check-doc` 只核文档数字，拦不住 `kg408_stats.json` 被篡改、"
        "拦不住 `kg408.json` 内容被改（只要数字自洽）；"
        "`--no-repro` 跳过逐字节比对，同样拦不住内容篡改。"
        "**防伪证必须跑无参全量。**"
    )
    lines.append("")
    lines.append("## 1. 溯源（provenance）")
    lines.append("")
    lines.append("| 项 | 值 |")
    lines.append("|---|---|")
    lines.append(f"| 源骨架文件 | `{p.source_path}` |")
    lines.append(f"| 源骨架 sha256 | `{p.source_sha256}` |")
    lines.append(f"| 源骨架字节数 | {p.source_bytes} |")
    lines.append(f"| 源骨架 mtime (UTC) | {p.source_mtime_utc} |")
    lines.append(f"| 别名表 | `{p.alias_path}` |")
    lines.append(f"| 别名表 sha256 | `{p.alias_sha256}` |")
    lines.append(f"| 章映射表 | `{p.chapter_map_path}` |")
    lines.append(f"| 章映射表 sha256 | `{p.chapter_map_sha256}` |")
    lines.append(f"| 人工补充节点表 | `{p.manual_nodes_path}` |")
    lines.append(f"| 人工补充节点表 sha256 | `{p.manual_nodes_sha256}` |")
    lines.append(f"| 生成脚本 | `{p.generator}` (v{p.generator_version}) |")
    lines.append(f"| 解析规则版本 | `{p.parser_rule_version}` |")
    lines.append(f"| 生成命令 | `{p.command}` |")
    lines.append(f"| generated_at_utc | {p.generated_at_utc} |")
    lines.append(f"| generated_at_utc 口径 | `{p.generated_at_utc_basis}` |")
    lines.append("")
    lines.append(
        "> **全部产物刻意不含墙钟时刻**：`generated_at_utc` 取**源骨架 mtime(UTC)**，"
        "因此本文件、`kg408.json`、`unresolved.json`、`kg408_stats.json` 连跑两次"
        "**逐字节一致**（`git diff` 为空）。构建时刻不属于「结论」，不进入产物；"
        "如确需，看本次构建的 stdout 输出或 `kg408.json` 的 git 提交时间。"
    )
    lines.append("")
    lines.append("## 2. 核心数字（真值锚点，verify_kg408.py 逐项断言）")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|---|---|")
    lines.append(f"| 科目节点 | {s['nodes_subject']} |")
    lines.append(f"| 章节点 | {s['nodes_chapter']} |")
    lines.append(f"| 考点节点 | {s['nodes_knowledge_point']} |")
    lines.append(f"| 节点合计 | {s['nodes_total']} |")
    lines.append(f"| 其中·源骨架节点 | {s['nodes_from_source']} |")
    lines.append(f"| 其中·人工补充节点 | {s['nodes_manual_supplement']} |")
    lines.append(f"| 其中·源骨架考点 | {s['nodes_knowledge_point_from_source']} |")
    lines.append(f"| 其中·人工补充考点 | {s['nodes_knowledge_point_manual']} |")
    lines.append(f"| 先修边（已解析） | {s['edges_prerequisite']} |")
    lines.append(f"| 跨科关联边（已解析） | {s['edges_association']} |")
    lines.append(f"| 边合计 | {s['edges_total']} |")
    lines.append(f"| 先修声明总数（源） | {s['source_prereq_declarations']} |")
    lines.append(f"| 跨科引用总数（源） | {s['source_cross_refs']} |")
    lines.append(f"| 未解析引用 | {s['unresolved_total']} |")
    lines.append("")
    lines.append(
        f"> **源骨架节点 {s['nodes_from_source']} ≠ 节点合计 {s['nodes_total']}**："
        f"差额 {s['nodes_manual_supplement']} 个是**人工补充节点**"
        "（学科负责人裁决补入，`origin=\"manual\"`，见 "
        "`data/kg408/kg408_manual_nodes.json`）。两个数字**分开列出，不合并**，"
        "以便读者区分哪些来自源文档、哪些是人工判断。"
    )
    lines.append("")
    lines.append("## 3. 分科构成（真值锚点）")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|---|---|")
    for code in SUBJECT_CODES:
        d = bs.get(code, {})
        lines.append(f"| {code} 章数 | {d.get('chapters', 0)} |")
        lines.append(f"| {code} 考点数 | {d.get('knowledge_points', 0)} |")
    lines.append(f"| 章数合计 | {s['nodes_chapter']} |")
    lines.append(f"| 考点数合计 | {s['nodes_knowledge_point']} |")
    lines.append("")
    lines.append("## 4. 边的解析方式分布（真值锚点）")
    lines.append("")
    lines.append("| resolution | 条数 |")
    lines.append("|---|---|")
    for k in sorted(res.keys()):
        lines.append(f"| {k} | {res[k]} |")
    lines.append(f"| 边合计（resolution） | {s['edges_total']} |")
    lines.append("")
    lines.append(f"| 依赖人工别名表的边 | {s['edges_depending_on_alias']} |")
    lines.append(f"| 纯精确匹配（不依赖别名表）的边 | {s['edges_pure_exact']} |")
    lines.append("")
    lines.append(
        f"> ⚠️ **口径说明**：`resolution` 取一条边**两端中最不确定的那一端**"
        "（只要任一端点靠人工别名表解析，整条边就记 `alias`）。"
        f"因此 `alias={res.get('alias', 0)}` 与上表「依赖人工别名表的边 = "
        f"{s['edges_depending_on_alias']}」**是同一个数字**，不再是旧版那种"
        "「只记单端点、把 4 条靠别名解析的边误记成 exact」的误导口径。"
        f"即：**{s['edges_depending_on_alias']}/{s['edges_total']} 条边依赖人工映射**，"
        f"仅 {s['edges_pure_exact']} 条是两端都精确命中源文档原文。"
    )
    lines.append("")
    lines.append("## 5. 未解析引用（如实挂起，禁止模糊匹配兜底）（真值锚点）")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|---|---|")
    for k in sorted(rc.keys()):
        lines.append(f"| {k} | {rc[k]} |")
    lines.append(f"| 未解析合计 | {s['unresolved_total']} |")
    lines.append(
        f"| 先修声明已解析（声明数口径） | "
        f"{s.get('source_prereq_declarations_resolved', 0)} |"
    )
    lines.append(f"| 先修声明成功率(%) | {s['prereq_success_pct']} |")
    lines.append("")
    if kg.unresolved:
        lines.append("| 类型 | 原文 | 所在行 | 上下文 | 原因 | 建议 |")
        lines.append("|---|---|---|---|---|---|")
        for u in kg.unresolved:
            lines.append(
                f"| {u.kind} | `{u.raw_name}` | {u.context_row} | {u.context} | "
                f"{u.reason} | {u.suggested_action} |"
            )
        lines.append("")
    lines.append(
        f"> 先修声明解析成功率 "
        f"{_bar(s.get('source_prereq_declarations_resolved', 0), s['source_prereq_declarations'])}"
        f"（{s.get('source_prereq_declarations_resolved', 0)}/"
        f"{s['source_prereq_declarations']} 条声明；分子分母同为单位「声明」，"
        f"不是「边数 ÷ 声明数」），"
        "其余全部如实挂起于 `data/kg408/unresolved.json`，并通过 "
        "`GET /kg408/unresolved` 对外可见。**未做任何模糊相似度兜底匹配。**"
    )
    lines.append("")
    lines.append("## 5b. 人工补充节点清单（origin=manual，非源数据）")
    lines.append("")
    manual_lines = [
        f"| `{n.id}` | {n.label} | {n.subject}/{n.chapter} | {n.origin} |"
        for n in kg.nodes
        if n.origin == ORIGIN_MANUAL
    ]
    if manual_lines:
        lines.append("| id | label | 挂载 | origin |")
        lines.append("|---|---|---|---|")
        lines.extend(manual_lines)
    else:
        lines.append("（无）")
    lines.append("")
    lines.append("## 6. 权重口径（诚信声明）")
    lines.append("")
    lines.append(
        f"- 源文档 §4 文字写「权重=关联强度」，但 §3 表头只有「关联/DS/CO/OS/CN」五列，"
        f"**没有任何权重数值列**。"
    )
    lines.append(
        f"- 因此全部 {s['edges_total']} 条边的 `weight` 均为 `null`"
        f"（实测 null 数 = {s['weight_null_count']}），"
        "`weight_source` = `not_applicable`（先修边）/ `not_provided_by_source`（跨科边）。"
    )
    lines.append("- **禁止**填 0.5/1.0 假装是关联强度。")
    lines.append("")
    return "\n".join(lines)


# ============================================================
# CLI
# ============================================================
def _sha256_of(path: Path) -> str:
    """计算文件 sha256。"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _utc_iso(ts: float) -> str:
    """epoch 秒 → UTC ISO8601（Z 结尾，秒精度）。"""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path, default: Any) -> Any:
    """读 JSON；不存在返回默认值。"""
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def run_build(args: argparse.Namespace) -> Kg408:
    """执行一次完整构建（不写 docs 产物时可复用）。"""
    src = Path(args.source)
    if not src.exists():
        raise SystemExit(f"[build_kg408] 源文件不存在: {src}")
    html = src.read_text(encoding="utf-8")
    out_dir = Path(args.out_dir)
    alias_path = Path(args.alias) if args.alias else out_dir / "kg408_alias.json"
    cmap_path = Path(args.chapter_map) if args.chapter_map else out_dir / "kg408_chapter_map.json"
    manual_path = (
        Path(args.manual_nodes) if args.manual_nodes else out_dir / "kg408_manual_nodes.json"
    )

    # 诚信护栏：缺人工维护表会导致图静默退化（边数从 18 掉到 2），
    # 而这种退化在产物上看不出来。因此默认视为硬错误，除非显式允许。
    if not args.allow_missing_tables:
        missing = [
            str(p) for p in (alias_path, cmap_path, manual_path) if not p.exists()
        ]
        if missing:
            raise SystemExit(
                "[build_kg408] 缺少人工维护表，拒绝生成（会导致图谱静默退化）："
                + "、".join(missing)
                + "。若确为故意，请加 --allow-missing-tables。"
            )

    alias_doc = _load_json(alias_path, {"entries": []})
    cmap_doc = _load_json(cmap_path, {"mapping": []})
    manual_doc = _load_json(manual_path, {"nodes": []})

    # command 默认按实参拼装；可用 --command 覆盖为「规范命令」，
    # 使 verify_kg408.py 重跑时得到逐字节一致的 provenance。
    command = args.command or (
        f"python scripts/build_kg408.py --source {args.source} --out-dir {args.out_dir}"
    )
    builder = Kg408Builder(
        html=html,
        source_path=str(src).replace("\\", "/"),
        source_sha256=_sha256_of(src),
        source_bytes=src.stat().st_size,
        source_mtime_utc=_utc_iso(src.stat().st_mtime),
        command=command,
        alias_entries=list(alias_doc.get("entries", []) or []),
        chapter_map=cmap_doc,
        manual_nodes=list(manual_doc.get("nodes", []) or []),
        alias_path=str(alias_path).replace("\\", "/"),
        alias_sha256=_sha256_of(alias_path) if alias_path.exists() else "",
        chapter_map_path=str(cmap_path).replace("\\", "/"),
        chapter_map_sha256=_sha256_of(cmap_path) if cmap_path.exists() else "",
        manual_nodes_path=str(manual_path).replace("\\", "/"),
        manual_nodes_sha256=_sha256_of(manual_path) if manual_path.exists() else "",
    )
    return builder.build()


def resolve_doc_out(doc_out: str, out_dir: Path) -> Path:
    """决定统计 Markdown 的落点（QA 修复：避免误写真实交付物）。

    规则：
      1. 显式给了 `--doc-out` → 用给定的（相对仓库根解析）；
      2. 留空 且 `--out-dir` 就是默认数据目录 → 写默认交付物
         `deliverables/408-kg/kg408-stats.md`（正式构建的正常行为）；
      3. 留空 且 `--out-dir` 被指到别处（如临时目录）→ 写
         `<out-dir>/kg408-stats.md`，**绝不碰真实 deliverables**。
    """
    if doc_out:
        p = Path(doc_out)
        return p if p.is_absolute() else (_ROOT.parent / p)
    if out_dir.resolve() == (_ROOT / DEFAULT_OUT_DIR).resolve():
        return _ROOT.parent / DEFAULT_DOC_OUT
    return out_dir / "kg408-stats.md"


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 入口。"""
    ap = argparse.ArgumentParser(
        description="构建 408 知识图谱骨架单一真源 data/kg408/kg408.json"
    )
    ap.add_argument("--source", default=DEFAULT_SOURCE, help="源骨架 HTML 路径")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="输出目录")
    ap.add_argument("--alias", default="", help="别名表路径（默认 <out-dir>/kg408_alias.json）")
    ap.add_argument(
        "--chapter-map", default="", help="章映射表路径（默认 <out-dir>/kg408_chapter_map.json）"
    )
    ap.add_argument(
        "--manual-nodes",
        default="",
        help="人工补充节点表路径（默认 <out-dir>/kg408_manual_nodes.json）",
    )
    ap.add_argument(
        "--doc-out",
        default="",
        help="统计 Markdown 输出路径（相对仓库根）。**留空**时按 out-dir 判定："
             f"out-dir 为默认数据目录（{DEFAULT_OUT_DIR}）→ 写 {DEFAULT_DOC_OUT}；"
             "否则写到 <out-dir>/kg408-stats.md。"
             "（QA 修复：避免手工 --out-dir 指到临时目录时，统计 md 仍被误写到"
             "真实交付物路径，污染 deliverables。）",
    )
    ap.add_argument("--no-doc", action="store_true", help="不写 Markdown 统计产物")
    ap.add_argument(
        "--command",
        default="",
        help="覆盖写入 provenance.command 的规范命令（verify 重跑时用于保证逐字节一致）",
    )
    ap.add_argument(
        "--allow-missing-tables",
        action="store_true",
        help="允许缺少别名表/章映射表（会导致图谱静默退化，仅限调试）",
    )
    args = ap.parse_args(argv)

    kg = run_build(args)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    _write_json(out_dir / "kg408.json", kg.to_dict())
    _write_json(
        out_dir / "unresolved.json",
        {
            "schema": SCHEMA_VERSION,
            "provenance": kg.provenance.to_dict(),
            "count": len(kg.unresolved),
            "unresolved": [u.to_dict() for u in kg.unresolved],
        },
    )
    _write_json(
        out_dir / "kg408_stats.json",
        {
            # 派生自 kg408.json；不含墙钟时刻 → 逐字节可复现
            "schema": SCHEMA_VERSION,
            "provenance": kg.provenance.to_dict(),
            "stats": dict(kg.stats),
        },
    )

    if not args.no_doc:
        doc_path = resolve_doc_out(args.doc_out, out_dir)
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        _write_text_lf(doc_path, render_stats_md(kg))
        _log(f"[build_kg408] 文档产物: {doc_path}")

    s = kg.stats
    _log("[build_kg408] 完成")
    _log(
        f"  节点 {s['nodes_total']} = 源骨架 {s['nodes_from_source']} "
        f"+ 人工补充 {s['nodes_manual_supplement']}（**分开计，勿合并**）"
    )
    _log(
        f"  节点 {s['nodes_total']} = 科目 {s['nodes_subject']} + 章 {s['nodes_chapter']} "
        f"+ 考点 {s['nodes_knowledge_point']}"
    )
    _log(
        f"  边 {s['edges_total']} = 先修 {s['edges_prerequisite']} + 跨科 {s['edges_association']}"
    )
    _log(
        f"  源声明：先修 {s['source_prereq_declarations']} 条 / 跨科引用 "
        f"{s['source_cross_refs']} 个"
    )
    _log(f"  未解析（如实挂起）：{s['unresolved_total']} 条")
    _log(f"  源文件 sha256: {kg.provenance.source_sha256}")
    _log(
        f"  依赖人工别名表的边: {s['edges_depending_on_alias']}/{s['edges_total']}"
    )
    _log(f"  产物目录: {out_dir}")
    _log(
        f"  （本次构建墙钟时刻 {_utc_iso(datetime.now(tz=timezone.utc).timestamp())}"
        " —— 仅打印，不写入产物，以保证产物逐字节可复现）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
