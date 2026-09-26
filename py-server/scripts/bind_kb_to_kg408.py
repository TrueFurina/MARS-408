#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ============================================================
# bind_kb_to_kg408.py — KB chunk（1892 条）↔ 408 考点 对齐与覆盖率报告
#
# 用法（在 py-server 目录下）：
#   python scripts/bind_kb_to_kg408.py
#
# 匹配口径（架构设计 T04 验收标准）：
#   - 只走 chapter_exact（章级，高精度）与 subtopic_exact / alias（考点级）
#   - **不使用模糊相似度阈值**
#   - 1144 条 knowledge_variant chunk **不参与**考点级强制绑定（单独统计）
#   - 绑不上的 chunk 记 kp_id=null，不丢弃、不伪造
#
# 产物：
#   data/kg408/kp_chunk_binding.json     逐条绑定明细
#   data/kg408/kp_chunk_coverage.json    覆盖率统计
#   deliverables/408-kg/kb-alignment.md  人类可读报告（覆盖率偏低也照写）
# ============================================================

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import seed_data  # noqa: E402

from services.kg408 import (  # noqa: E402
    LEVEL_CHAPTER,
    LEVEL_KP,
    Kg408Store,
)

DEFAULT_OUT_DIR = "data/kg408"
DEFAULT_DOC_OUT = "deliverables/408-kg/kb-alignment.md"

# match_method → (confidence, 说明)
CONFIDENCE = {
    "chapter_exact": 1.0,      # SEED subject 键 → 骨架章（映射表显式维护）
    "subject_exact": 1.0,      # ds/co/os/cn 科目级键 → 骨架科目（无章）
    "subtopic_exact": 1.0,     # chunk.sub_topic == 考点名（字符串全等）
    "alias": 0.8,              # chunk.sub_topic 命中考点 aliases（人工别名表）
}
KB_VARIANT_TYPE = "knowledge_variant"


def _log(msg: str) -> None:
    """stdout 输出，兼容 Windows GBK 控制台。"""
    try:
        sys.stdout.write(msg + "\n")
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        sys.stdout.write(msg.encode(enc, "backslashreplace").decode(enc) + "\n")


def _write_json(path: Path, payload: Any) -> None:
    """UTF-8 JSON 落盘（**永远写 LF**，保证跨平台逐字节可复现）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_text_lf(
        path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    )


def _write_text_lf(path: Path, text: str) -> None:
    """UTF-8 落盘且**不翻译换行**（Windows 下避免 `\\n` 变 `\\r\\n`）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(text)


# ============================================================
# 绑定器
# ============================================================
class KbBinder:
    """把 SEED_KNOWLEDGE_CHUNKS 绑定到 408 骨架的章 / 考点。"""

    def __init__(self, store: Kg408Store, chapter_map: Dict[str, Any]) -> None:
        self._store = store
        self._kg = store.kg
        self._cmap = chapter_map
        # seed subject 键 → (skeleton_subject, skeleton_chapter)
        self._seed_to_skel: Dict[str, Tuple[str, Optional[str]]] = {}
        for m in chapter_map.get("mapping", []):
            ss = m.get("seed_subject")
            if ss:
                self._seed_to_skel[str(ss)] = (m.get("subject"), m.get("chapter"))
            for extra in m.get("seed_subject_extra", []) or []:
                self._seed_to_skel[str(extra)] = (m.get("subject"), m.get("chapter"))
        # ds/co/os/cn 科目级键
        self._seed_subject_level: Dict[str, str] = {
            str(k): str(v)
            for k, v in (chapter_map.get("seed_subject_level", {}) or {}).items()
            if not str(k).startswith("_")
        }
        # (subject, label) → [kp nodes]
        self._kp_by_label: Dict[Tuple[str, str], List[Any]] = {}
        # (subject, alias) → [kp nodes]
        self._kp_by_alias: Dict[Tuple[str, str], List[Any]] = {}
        for n in self._kg.nodes:
            if n.level != LEVEL_KP:
                continue
            self._kp_by_label.setdefault((n.subject, n.label), []).append(n)
            for a in n.aliases or []:
                self._kp_by_alias.setdefault((n.subject, str(a)), []).append(n)

    # ── 章级 ──────────────────────────────────────────────────
    def bind_chapter(self, seed_subject: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """SEED subject 键 → (skeleton_subject, skeleton_chapter_id, match_method)。"""
        key = str(seed_subject or "").strip()
        if not key:
            return (None, None, None)
        hit = self._seed_to_skel.get(key)
        if hit:
            subj, chapter = hit
            cid = self._chapter_id(subj, chapter)
            return (subj, cid, "chapter_exact")
        subj_code = self._seed_subject_level.get(key)
        if subj_code:
            return (subj_code, None, "subject_exact")
        return (None, None, None)

    def _chapter_id(self, subject: Optional[str], chapter: Optional[str]) -> Optional[str]:
        """按 (subject, chapter 名) 找章节点 id。"""
        if not subject or not chapter:
            return None
        for n in self._kg.nodes:
            if n.level == LEVEL_CHAPTER and n.subject == subject and n.label == chapter:
                return n.id
        return None

    # ── 考点级 ────────────────────────────────────────────────
    def bind_kp(
        self, subject: Optional[str], sub_topic: Optional[str]
    ) -> Tuple[Optional[str], Optional[str], float, str]:
        """chunk.sub_topic → (kp_id, match_method, confidence, note)。

        只做全等匹配与人工别名匹配；歧义/未命中一律返回 null（不丢弃、不伪造）。
        """
        st = " ".join(str(sub_topic or "").split())
        if not st or not subject:
            return (None, None, 0.0, "sub_topic 为空或科目未知")
        exact = self._kp_by_label.get((subject, st), [])
        if len(exact) == 1:
            return (exact[0].id, "subtopic_exact", CONFIDENCE["subtopic_exact"], "")
        if len(exact) > 1:
            where = "、".join(f"{n.chapter}/{n.label}" for n in exact)
            return (
                None, None, 0.0,
                f"sub_topic「{st}」在 {subject} 内命中 {len(exact)} 个同名考点（{where}），挂起待人工裁定",
            )
        aliased = self._kp_by_alias.get((subject, st), [])
        if len(aliased) == 1:
            return (
                aliased[0].id, "alias", CONFIDENCE["alias"],
                f"命中人工别名表：{st} → {aliased[0].label}（待学科负责人复核）",
            )
        if len(aliased) > 1:
            return (None, None, 0.0, f"别名「{st}」在 {subject} 内多义，挂起")
        return (None, None, 0.0, f"sub_topic「{st}」未命中任何考点名或别名")

    # ── 全量绑定 ──────────────────────────────────────────────
    def bind_all(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """对全部 chunk 做绑定，返回明细列表。"""
        rows: List[Dict[str, Any]] = []
        for idx, c in enumerate(chunks):
            md = c.get("metadata", {}) or {}
            seed_subject = md.get("subject")
            stype = md.get("type")
            sub_topic = md.get("sub_topic")
            subj, chapter_id, ch_method = self.bind_chapter(seed_subject)

            kp_id: Optional[str] = None
            kp_method: Optional[str] = None
            kp_conf = 0.0
            note = ""
            if stype == KB_VARIANT_TYPE:
                note = "knowledge_variant 类型，按设计不参与考点级强制绑定"
            else:
                kp_id, kp_method, kp_conf, note = self.bind_kp(subj, sub_topic)

            rows.append(
                {
                    "chunk_index": idx,
                    "seed_subject": seed_subject,
                    "seed_chapter": md.get("chapter"),
                    "sub_topic": sub_topic,
                    "chunk_type": stype,
                    "variant": md.get("variant"),
                    "kg_subject": subj,
                    "kg_chapter_id": chapter_id,
                    "chapter_match_method": ch_method,
                    "kp_id": kp_id,
                    "kp_match_method": kp_method,
                    "confidence": kp_conf,
                    "note": note,
                }
            )
        return rows


# ============================================================
# 统计
# ============================================================
def compute_coverage(
    rows: List[Dict[str, Any]], store: Kg408Store
) -> Dict[str, Any]:
    """计算覆盖率统计。"""
    total = len(rows)
    variant_rows = [r for r in rows if r["chunk_type"] == KB_VARIANT_TYPE]
    point_rows = [r for r in rows if r["chunk_type"] != KB_VARIANT_TYPE]

    chapter_bound = [r for r in rows if r["kg_chapter_id"]]
    subject_bound_only = [
        r for r in rows if not r["kg_chapter_id"] and r["kg_subject"]
    ]

    kp_bound = [r for r in point_rows if r["kp_id"]]
    kp_bound_variant = [r for r in variant_rows if r["kp_id"]]

    per_kp: Dict[str, int] = {}
    for r in kp_bound:
        per_kp[r["kp_id"]] = per_kp.get(r["kp_id"], 0) + 1

    all_kps = [n for n in store.all_nodes() if n.level == LEVEL_KP]
    kp_covered = len(per_kp)

    methods: Dict[str, int] = {}
    for r in kp_bound:
        m = str(r["kp_match_method"])
        methods[m] = methods.get(m, 0) + 1

    # 每章覆盖：有 chunk 绑定到的章数 / 26
    chapter_ids = {
        n.id for n in store.all_nodes() if n.level == LEVEL_CHAPTER
    }
    chapter_with_chunk = {r["kg_chapter_id"] for r in chapter_bound}

    def _pct(a: int, b: int) -> float:
        return round(a * 100.0 / b, 2) if b else 0.0

    return {
        "chunks_total": total,
        "chunks_knowledge_point": len(point_rows),
        "chunks_knowledge_variant": len(variant_rows),
        "chapter_level": {
            "bound": len(chapter_bound),
            "bound_pct": _pct(len(chapter_bound), total),
            "subject_only": len(subject_bound_only),
            "unbound": total - len(chapter_bound) - len(subject_bound_only),
            "chapters_total": len(chapter_ids),
            "chapters_with_chunk": len(chapter_with_chunk),
            "chapter_coverage_pct": _pct(len(chapter_with_chunk), len(chapter_ids)),
        },
        "kp_level": {
            "eligible_chunks": len(point_rows),
            "bound": len(kp_bound),
            "bound_pct_of_eligible": _pct(len(kp_bound), len(point_rows)),
            "bound_pct_of_total": _pct(len(kp_bound), total),
            "unbound_eligible": len(point_rows) - len(kp_bound),
            "variant_bound": len(kp_bound_variant),
            "variant_excluded_by_design": len(variant_rows),
            "kp_total": len(all_kps),
            "kp_covered": kp_covered,
            "kp_coverage_pct": _pct(kp_covered, len(all_kps)),
            "match_methods": methods,
            "per_kp_chunk_count": dict(sorted(per_kp.items())),
        },
        "honesty": {
            "fuzzy_matching_used": False,
            "policy": (
                "只使用 chapter_exact / subject_exact / subtopic_exact / alias 四种全等匹配；"
                "未命中一律记 kp_id=null，不丢弃、不伪造、不做模糊相似度兜底。"
            ),
        },
    }


def render_alignment_md(
    cov: Dict[str, Any],
    store: Kg408Store,
) -> str:
    """渲染 KB 对齐覆盖率报告。

    刻意不含墙钟时刻 → 连跑两次逐字节一致，可纳入 verify 的重跑比对
    （QA GAP-1：本文件是对外唯一一份人读交付物，必须受防伪证闸门保护）。
    """
    cl = cov["chapter_level"]
    kl = cov["kp_level"]
    lines: List[str] = []
    lines.append("# KB chunk ↔ 408 考点 对齐覆盖率报告")
    lines.append("")
    lines.append(
        "> 由 `scripts/bind_kb_to_kg408.py` 自动生成。"
        "覆盖率偏低**照写不修饰**——本文件的价值在于可回溯，不在于好看。"
    )
    lines.append(">")
    lines.append(
        "> **防伪证**：本文件数字由 `scripts/verify_kg408.py`（**无参 = 全量**）"
        "逐项断言；`kp_chunk_coverage.json` 与 `kp_chunk_binding.json` 亦参与"
        "重跑逐字节比对。任一数字被改 → exit 1。"
    )
    lines.append(
        "> 本文件刻意**不含墙钟时刻**（仅打印到 stdout），以保证逐字节可复现。"
    )
    lines.append("")
    lines.append("## 1. 总体")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|---|---|")
    lines.append(f"| KB chunk 总数 | {cov['chunks_total']} |")
    lines.append(f"| 其中 knowledge_point | {cov['chunks_knowledge_point']} |")
    lines.append(f"| 其中 knowledge_variant | {cov['chunks_knowledge_variant']} |")
    lines.append(f"| 章级已绑定 | {cl['bound']}（{cl['bound_pct']}%） |")
    lines.append(f"| 仅科目级绑定（无章） | {cl['subject_only']} |")
    lines.append(f"| 章级未绑定 | {cl['unbound']} |")
    lines.append(f"| 骨架章总数 | {cl['chapters_total']} |")
    lines.append(f"| 有 chunk 命中的章数 | {cl['chapters_with_chunk']} |")
    lines.append("")
    lines.append("## 2. 覆盖率")
    lines.append("")
    lines.append("| 口径 | 覆盖率 |")
    lines.append("|---|---|")
    lines.append(f"| 章级覆盖率（有 chunk 的章 / 骨架章） | {cl['chapter_coverage_pct']}% |")
    # 分母必须与真值同源：用 kl['kp_total'] 动态取值，禁止写死数字
    # （历史缺陷：此处曾硬编码「105 考点」，人工补充节点后真值变 106，
    #   导致同一文件内标签写 105、计算用 106 的自相矛盾）。
    lines.append(
        f"| 考点级覆盖率（有 chunk 的考点 / {kl['kp_total']} 考点） "
        f"| **{kl['kp_coverage_pct']}%** |"
    )
    lines.append(
        f"| 考点级 chunk 绑定率（已绑定 / 可绑定 {kl['eligible_chunks']} 条） | "
        f"{kl['bound_pct_of_eligible']}% |"
    )
    lines.append("")
    lines.append(
        f"**考点级覆盖率 = {kl['kp_coverage_pct']}%"
        f"（{kl['kp_covered']}/{kl['kp_total']}）**。"
        "这是**如实值**：骨架考点名与 KB 的 `sub_topic` 是两套各自独立命名的体系，"
        "本阶段只做全等匹配，不做语义/模糊对齐，因此覆盖率天然偏低。"
        "提升路径只有两条合法：① 人工补 alias 表；② 由错题共现学习。两者都不得伪造。"
    )
    lines.append("")
    lines.append("## 3. 考点级匹配方式分布")
    lines.append("")
    lines.append("| match_method | 条数 | confidence |")
    lines.append("|---|---|---|")
    for m, c in sorted(kl["match_methods"].items()):
        lines.append(f"| {m} | {c} | {CONFIDENCE.get(m, 0.0)} |")
    lines.append(f"| **合计** | {kl['bound']} | |")
    lines.append("")
    lines.append(
        f"- knowledge_variant（{kl['variant_excluded_by_design']} 条）"
        "按设计**不参与考点级强制绑定**，仅参与章级统计。"
    )
    lines.append(f"- 可绑定但未能绑定的 chunk：{kl['unbound_eligible']} 条，记为 `kp_id=null`。")
    lines.append("")
    lines.append("## 4. 匹配口径（诚信声明）")
    lines.append("")
    lines.append("- 允许的 match_method：`chapter_exact` / `subject_exact` / `subtopic_exact` / `alias`。")
    lines.append("- **未使用任何模糊相似度阈值**。")
    lines.append("- 绑不上的 chunk **不丢弃、不伪造**，一律 `kp_id=null` 并保留原因。")
    lines.append("")
    return "\n".join(lines)


# ============================================================
# CLI
# ============================================================
def main(argv: Optional[List[str]] = None) -> int:
    """CLI 入口。"""
    ap = argparse.ArgumentParser(description="KB chunk ↔ 408 考点 对齐")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                    help="**读**输入目录（kg408.json / kg408_chapter_map.json）")
    ap.add_argument("--write-dir", default="",
                    help="**写** JSON 产物目录（默认 = --out-dir）。"
                         "供 verify 重跑时「读真源、写临时目录」")
    ap.add_argument("--doc-out", default=DEFAULT_DOC_OUT)
    ap.add_argument("--chunks-limit", type=int, default=0, help="只处理前 N 条（调试用）")
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = _ROOT / out_dir
    write_dir = Path(args.write_dir) if args.write_dir else out_dir
    if not write_dir.is_absolute():
        write_dir = _ROOT / write_dir

    store = Kg408Store.load(
        path=out_dir / "kg408.json",
        unresolved_path=out_dir / "unresolved.json",
        stats_path=out_dir / "kg408_stats.json",
    )
    cmap = json.loads((out_dir / "kg408_chapter_map.json").read_text(encoding="utf-8"))

    chunks = list(seed_data.SEED_KNOWLEDGE_CHUNKS)
    if args.chunks_limit and args.chunks_limit > 0:
        chunks = chunks[: args.chunks_limit]

    binder = KbBinder(store, cmap)
    rows = binder.bind_all(chunks)
    cov = compute_coverage(rows, store)

    # 不含墙钟时刻 → 逐字节可复现（QA GAP-1：纳入 verify 重跑比对）。
    # provenance 里的 generated_at_utc 取源骨架 mtime，本身即确定性。
    _write_json(
        write_dir / "kp_chunk_binding.json",
        {
            "schema": "kg408-kp-binding-v1",
            "provenance": store.provenance.to_dict(),
            "count": len(rows),
            "bindings": rows,
        },
    )
    _write_json(
        write_dir / "kp_chunk_coverage.json",
        {
            "schema": "kg408-kp-coverage-v1",
            "provenance": store.provenance.to_dict(),
            "coverage": cov,
        },
    )

    doc_path = Path(args.doc_out)
    if not doc_path.is_absolute():
        doc_path = _ROOT.parent / doc_path
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    _write_text_lf(doc_path, render_alignment_md(cov, store))

    _log("[bind_kb] 完成")
    _log(f"  chunk 总数 {cov['chunks_total']}")
    _log(
        f"  章级绑定 {cov['chapter_level']['bound']}"
        f"（{cov['chapter_level']['bound_pct']}%），"
        f"章覆盖率 {cov['chapter_level']['chapter_coverage_pct']}%"
    )
    _log(
        f"  考点级绑定 {cov['kp_level']['bound']}/{cov['kp_level']['eligible_chunks']}"
        f"，考点覆盖率 {cov['kp_level']['kp_coverage_pct']}%"
        f"（{cov['kp_level']['kp_covered']}/{cov['kp_level']['kp_total']}）—— 如实值，不修饰"
    )
    _log(f"  报告: {doc_path}")
    _log(
        f"  （本次运行墙钟时刻 {wallclock_utc()} —— 仅打印，不写入产物，"
        "以保证产物逐字节可复现）"
    )
    return 0


def wallclock_utc() -> str:
    """当前 UTC 时刻（ISO8601，秒精度）。"""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
