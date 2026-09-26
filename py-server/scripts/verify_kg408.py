#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ============================================================
# verify_kg408.py — 408 知识图谱「防伪证」关卡
#
# 关卡（任一失败 exit 1）：
#   1. 结构自检：节点/边/未解析清单的完整性（无悬空引用、无孤儿、无重复 id）
#   1b. 覆盖率产物自检：kp_chunk_coverage.json == 重算真值（QA GAP-1）
#       sha256 锚点：provenance == 真实文件 == **冻结基线清单**（QA GAP-2）
#   2. 可复现性：用同一份源重跑 build_kg408.py 到临时目录，
#      逐字节比对 kg408.json / unresolved.json / kg408_stats.json / kg408-stats.md
#   2b. 覆盖率可复现性：重跑 bind_kb_to_kg408.py，逐字节比对
#       kp_chunk_coverage.json / kp_chunk_binding.json / kb-alignment.md（QA GAP-1）
#   3. 文档一致性：解析两份 Markdown 的数字，
#      断言「文档数字 == 重算真值」（kg408.json 真值 + KB binder 真值）
#
# ⚠️ 弱模式警告：
#   `--check-doc` 只跑关卡 3，`--no-repro` 跳过关卡 2/2b。
#   二者都**拦不住** `kg408_stats.json` 被篡改、也拦不住 `kg408.json`
#   内容被改（只要数字自洽）。**防伪证必须跑无参全量。**
#
# 用法：
#   python scripts/verify_kg408.py                       # 全量（唯一可信模式）
#   python scripts/verify_kg408.py --check-doc            # 弱：只跑文档关
#   python scripts/verify_kg408.py --no-repro             # 弱：跳过重跑
# ============================================================

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    RESOLUTIONS,
    SUBJECT_CODES,
    UNRESOLVED_REASONS,
    WEIGHT_SOURCES,
    Kg408,
    Kg408Store,
    build_stats,
)

DEFAULT_SOURCE = "E:/Program/MARL/SAGE/pdf/03_408知识图谱骨架.html"
DEFAULT_OUT_DIR = "data/kg408"
DEFAULT_DOC = "deliverables/408-kg/kg408-stats.md"

# 文档中被断言的标签 → JSON 真值取值路径（stats 中的 key）
# QA M5/M6/M8/M12 修复：补上 §3 分科构成、§4 resolution 分布、
# 先修解析成功率、§5 reason 分布，以及源/人工节点分列。
DOC_TRUTH_FIELDS: List[Tuple[str, str]] = [
    ("科目节点", "nodes_subject"),
    ("章节点", "nodes_chapter"),
    ("考点节点", "nodes_knowledge_point"),
    ("节点合计", "nodes_total"),
    ("其中·源骨架节点", "nodes_from_source"),
    ("其中·人工补充节点", "nodes_manual_supplement"),
    ("其中·源骨架考点", "nodes_knowledge_point_from_source"),
    ("其中·人工补充考点", "nodes_knowledge_point_manual"),
    ("先修边（已解析）", "edges_prerequisite"),
    ("跨科关联边（已解析）", "edges_association"),
    ("边合计", "edges_total"),
    ("先修声明总数（源）", "source_prereq_declarations"),
    ("跨科引用总数（源）", "source_cross_refs"),
    ("未解析引用", "unresolved_total"),
    # §3 分科构成
    ("DS 章数", "by_subject.DS.chapters"),
    ("DS 考点数", "by_subject.DS.knowledge_points"),
    ("CO 章数", "by_subject.CO.chapters"),
    ("CO 考点数", "by_subject.CO.knowledge_points"),
    ("OS 章数", "by_subject.OS.chapters"),
    ("OS 考点数", "by_subject.OS.knowledge_points"),
    ("CN 章数", "by_subject.CN.chapters"),
    ("CN 考点数", "by_subject.CN.knowledge_points"),
    ("章数合计", "nodes_chapter"),
    ("考点数合计", "nodes_knowledge_point"),
    # §4 resolution 分布 + 别名依赖
    ("exact", "resolution_counts.exact"),
    ("alias", "resolution_counts.alias"),
    ("边合计（resolution）", "edges_total"),
    ("依赖人工别名表的边", "edges_depending_on_alias"),
    ("纯精确匹配（不依赖别名表）的边", "edges_pure_exact"),
    # §5 未解析 reason 分布 + 成功率
    ("absent_in_skeleton", "unresolved_by_reason.absent_in_skeleton"),
    ("ambiguous_multi_match", "unresolved_by_reason.ambiguous_multi_match"),
    ("chapter_level_only", "unresolved_by_reason.chapter_level_only"),
    ("未解析合计", "unresolved_total"),
    # QA GAP-3.2：分子改用与分母同单位的「已解析声明数」
    ("先修声明已解析（声明数口径）", "source_prereq_declarations_resolved"),
    ("先修声明成功率(%)", "prereq_success_pct"),
    # §1 溯源中的数值（QA GAP-3.3：此前只靠全量重跑字节比对兜底）
    ("源骨架字节数", "provenance.source_bytes"),
]

# 冻结基线清单（QA GAP-2）：**只允许人手工更新**，任何生成脚本都不得改写。
FROZEN_MANIFEST_NAME = "kg408_inputs_frozen.json"

DOC_ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(\d+(?:\.\d+)?)\s*\|\s*$")

# 人工维护输入文件 → provenance 中对应的 sha256 字段名
HASH_ANCHORS: List[Tuple[str, str]] = [
    ("kg408_alias.json", "alias_sha256"),
    ("kg408_chapter_map.json", "chapter_map_sha256"),
    ("kg408_manual_nodes.json", "manual_nodes_sha256"),
]


def _log(msg: str) -> None:
    """stdout 输出，兼容 Windows GBK 控制台。"""
    try:
        sys.stdout.write(msg + "\n")
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        sys.stdout.write(msg.encode(enc, "backslashreplace").decode(enc) + "\n")


# ============================================================
# 关卡 1：结构自检
# ============================================================
def assert_all_edges_resolve(kg: Kg408) -> List[str]:
    """断言全部边的 source/target 都指向存在的节点（无悬空引用）。"""
    errs: List[str] = []
    ids = {n.id for n in kg.nodes}
    for e in kg.edges:
        if e.source not in ids:
            errs.append(f"边 {e.id} 的 source 悬空: {e.source}")
        if e.target not in ids:
            errs.append(f"边 {e.id} 的 target 悬空: {e.target}")
    return errs


def assert_hierarchy(kg: Kg408) -> List[str]:
    """断言层级结构：无重复 id、非科目节点有存在的父节点、无孤儿。"""
    errs: List[str] = []
    seen: Dict[str, int] = {}
    for n in kg.nodes:
        seen[n.id] = seen.get(n.id, 0) + 1
    for nid, c in seen.items():
        if c > 1:
            errs.append(f"节点 id 重复 {c} 次: {nid}")

    ids = set(seen.keys())
    roots = [n for n in kg.nodes if n.level == LEVEL_SUBJECT]
    if len(roots) != len(SUBJECT_CODES):
        errs.append(f"科目根节点数应为 {len(SUBJECT_CODES)}，实际 {len(roots)}")
    for n in kg.nodes:
        if n.level == LEVEL_SUBJECT:
            if n.parent_id is not None:
                errs.append(f"科目节点 {n.id} 不应有 parent_id")
            continue
        if not n.parent_id:
            errs.append(f"非科目节点 {n.id} 缺少 parent_id（孤儿）")
        elif n.parent_id not in ids:
            errs.append(f"节点 {n.id} 的 parent_id 悬空: {n.parent_id}")
    return errs


def assert_enums(kg: Kg408) -> List[str]:
    """断言枚举字段取值合法（尤其 resolution 只允许 4 个值）。"""
    errs: List[str] = []
    for n in kg.nodes:
        if n.level not in (LEVEL_SUBJECT, LEVEL_CHAPTER, LEVEL_KP):
            errs.append(f"节点 {n.id} 的 level 非法: {n.level}")
        if n.subject not in SUBJECT_CODES:
            errs.append(f"节点 {n.id} 的 subject 非法: {n.subject}")
    for e in kg.edges:
        if e.type not in (EDGE_PREREQUISITE, EDGE_ASSOCIATION):
            errs.append(f"边 {e.id} 的 type 非法: {e.type}")
        if e.resolution not in RESOLUTIONS:
            errs.append(f"边 {e.id} 的 resolution 非法: {e.resolution}")
        if e.weight_source not in WEIGHT_SOURCES:
            errs.append(f"边 {e.id} 的 weight_source 非法: {e.weight_source}")
        if e.type == EDGE_PREREQUISITE and not e.directed:
            errs.append(f"先修边 {e.id} 必须 directed=true")
        if e.type == EDGE_ASSOCIATION and e.directed:
            errs.append(f"跨科边 {e.id} 必须 directed=false")
    for u in kg.unresolved:
        if u.reason not in UNRESOLVED_REASONS:
            errs.append(f"未解析项 {u.raw_name} 的 reason 非法: {u.reason}")
    return errs


def assert_weight_policy(kg: Kg408) -> List[str]:
    """断言权重红线：源未提供数值 → weight 必须全为 null。"""
    errs: List[str] = []
    for e in kg.edges:
        if e.weight is not None:
            errs.append(
                f"边 {e.id} 的 weight 非 null（{e.weight}）。"
                f"源文档未提供任何权重数值，禁止编造。"
            )
    return errs


def assert_provenance(kg: Kg408) -> List[str]:
    """断言 provenance 必备字段齐全。"""
    errs: List[str] = []
    p = kg.provenance
    for field in ("source_path", "source_sha256", "command", "generated_at_utc",
                  "parser_rule_version"):
        if not getattr(p, field, ""):
            errs.append(f"provenance 缺失字段: {field}")
    if len(p.source_sha256) != 64:
        errs.append(f"source_sha256 长度异常: {len(p.source_sha256)}")
    return errs


def check_structure(kg: Kg408) -> List[str]:
    """汇总关卡 1 的全部断言。"""
    errs: List[str] = []
    errs += assert_hierarchy(kg)
    errs += assert_all_edges_resolve(kg)
    errs += assert_enums(kg)
    errs += assert_weight_policy(kg)
    errs += assert_provenance(kg)
    return errs


# ============================================================
# 关卡 2：可复现性
# ============================================================
def rebuild_and_compare(
    source: str,
    out_dir: Path,
    alias: Optional[str],
    chapter_map: Optional[str],
    replay_command: str = "",
    manual_nodes: Optional[str] = None,
    doc_path: Optional[Path] = None,
) -> List[str]:
    """重跑 build 到临时目录，与已入库产物逐字节比对。"""
    errs: List[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="kg408-repro-"))
    try:
        cmd = [
            sys.executable,
            str(_HERE / "build_kg408.py"),
            "--source",
            source,
            "--out-dir",
            str(tmp),
            "--doc-out",
            str(tmp / "kg408-stats.md"),
        ]
        if alias:
            cmd += ["--alias", alias]
        if chapter_map:
            cmd += ["--chapter-map", chapter_map]
        if manual_nodes:
            cmd += ["--manual-nodes", manual_nodes]
        if replay_command:
            # 用已入库产物里记录的规范命令重放，保证 provenance.command 一致
            cmd += ["--command", replay_command]
        proc = subprocess.run(
            cmd,
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            errs.append(
                f"重跑 build_kg408.py 失败（exit {proc.returncode}）: "
                f"{proc.stderr.strip()[:500]}"
            )
            return errs
        for name in ("kg408.json", "unresolved.json"):
            committed = out_dir / name
            fresh = tmp / name
            if not committed.exists():
                errs.append(f"已入库产物缺失: {committed}")
                continue
            if not fresh.exists():
                errs.append(f"重跑产物缺失: {fresh}")
                continue
            a = committed.read_bytes()
            b = fresh.read_bytes()
            if a != b:
                errs.append(
                    f"重跑后 {name} 与已入库产物内容不一致"
                    f"（已入库 {len(a)} 字节，重跑 {len(b)} 字节）"
                )

        # QA M2：kg408_stats.json 也纳入关卡 2。
        # 产物不含墙钟时刻，因此可以做**整文件字节**比对（比只比子对象更强）。
        committed_s = out_dir / "kg408_stats.json"
        fresh_s = tmp / "kg408_stats.json"
        if not committed_s.exists() or not fresh_s.exists():
            errs.append("kg408_stats.json 缺失（已入库或重跑产物），关卡 2 无法比对")
        else:
            a = committed_s.read_bytes()
            b = fresh_s.read_bytes()
            if a != b:
                errs.append(
                    f"重跑后 kg408_stats.json 与已入库内容不一致"
                    f"（已入库 {len(a)} 字节，重跑 {len(b)} 字节）"
                    "—— 该文件应逐字节可复现"
                )

        # 统计 Markdown 同样必须逐字节可复现（产物不含墙钟时刻）
        committed_md = doc_path
        fresh_md = tmp / "kg408-stats.md"
        if committed_md is None or not Path(committed_md).exists():
            errs.append("统计 Markdown 未生成，关卡 2 无法比对")
        elif not fresh_md.exists():
            errs.append("重跑未生成统计 Markdown")
        else:
            a = Path(committed_md).read_bytes()
            b = fresh_md.read_bytes()
            if a != b:
                errs.append(
                    f"重跑后 kg408-stats.md 与已入库内容不一致"
                    f"（已入库 {len(a)} 字节，重跑 {len(b)} 字节）"
                    "—— 该文件应逐字节可复现"
                )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return errs


# ============================================================
# 真值计算：一律从 kg408.json 重算（QA M2）
# ============================================================
def compute_truth(kg: Kg408) -> Dict[str, Any]:
    """从 kg408.json 的 nodes/edges/unresolved **重算**统计真值。

    这是本次修复的关键：`kg408_stats.json` 是**派生产物**，不是真源。
    任何断言都必须以本函数的结果为准。
    """
    return build_stats(kg.nodes, kg.edges, kg.unresolved, kg.source_counts)


def _resolve_key(obj: Any, dotted: str) -> Any:
    """按 `a.b.c` 路径取值；任一层缺失返回 None。"""
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def assert_stats_file_is_derived(
    store: Kg408Store, truth: Dict[str, Any]
) -> List[str]:
    """QA M2 核心断言：`kg408_stats.json` 必须 == 从 kg408.json 重算的真值。

    堵住的绕过：同步篡改 `kg408-stats.md` 与 `kg408_stats.json` 的「节点合计」
    使三关全绿。现在 stats.json 只是派生产物，与重算值不符即失败。
    """
    errs: List[str] = []
    sf = store.stats_file
    if sf is None:
        errs.append("kg408_stats.json 不存在或缺少 stats 字段（派生产物缺失）")
        return errs
    for key, expected in truth.items():
        if key not in sf:
            errs.append(
                f"kg408_stats.json 缺少字段: {key}（派生产物与真值口径不一致）"
            )
            continue
        if sf[key] != expected:
            errs.append(
                f"kg408_stats.json 与 kg408.json 重算真值不符："
                f"stats.json[{key}]={sf[key]!r}，重算值={expected!r}"
            )
    return errs


def assert_provenance_anchors(kg: Kg408, source: str, out_dir: Path) -> List[str]:
    """断言 sha256 锚点 == **各输入文件的真实 sha256**，且 == **冻结清单**。

    两层含义，缺一不可：
      1. provenance 声称的 sha256 必须等于当前文件真实 sha256
         （堵 QA M3：把 provenance.source_sha256 改成 64 个 0）。
      2. 当前文件真实 sha256 必须等于 `kg408_inputs_frozen.json` 里冻结的 sha256
         （堵 QA GAP-2：sha 是 build 当场算的，『改表后重跑』锚点会自动跟上，
          于是两个闸门全绿。与冻结基线比对才能发现输入表被改过）。

    冻结点的一致性检查是**漂移检测**，不是「全表已批准」——清单里的
    `review_status` 如实标注每张表的复核状态。
    """
    errs: List[str] = []
    src = Path(source)
    if src.exists():
        real = _sha256_file(src)
        if kg.provenance.source_sha256 != real:
            errs.append(
                f"provenance.source_sha256 与源骨架真实 sha256 不符："
                f"声称={kg.provenance.source_sha256}，实际={real}"
            )
    else:
        errs.append(f"源骨架不存在，无法校验 source_sha256 锚点: {src}")

    # ── 冻结清单：缺失即失败（fail-closed，避免删掉清单就绕过漂移检测）──
    frozen = _load_frozen_manifest(out_dir)
    if frozen is None:
        errs.append(
            f"冻结清单缺失或无法解析: {out_dir / FROZEN_MANIFEST_NAME}"
            "（该文件只允许人工维护；缺失无法检测『改表→重跑』漂移）"
        )

    for fname, field in HASH_ANCHORS:
        p = out_dir / fname
        claimed = getattr(kg.provenance, field, "")
        if not p.exists():
            errs.append(f"人工维护输入文件缺失: {p}")
            continue
        real = _sha256_file(p)
        # (1) provenance 声称值 == 真实值
        if claimed != real:
            errs.append(
                f"provenance.{field} 与 {fname} 真实 sha256 不符："
                f"声称={claimed or '(空)'}，实际={real}"
            )
        # (2) 真实值 == 冻结基线值
        if frozen is not None:
            ent = (frozen.get("entries") or {}).get(fname)
            if not isinstance(ent, dict) or not ent.get("sha256"):
                errs.append(f"冻结清单缺少条目或 sha256: {fname}")
                continue
            frozen_sha = str(ent["sha256"])
            if frozen_sha != real:
                errs.append(
                    f"当前 {fname} 表 sha ≠ 冻结清单 sha（输入表已被改动）："
                    f"冻结={frozen_sha}，当前={real}。"
                    "若本次改动已获学科负责人复核，请**手工**更新 "
                    f"{FROZEN_MANIFEST_NAME} 后重跑；未经复核不得更新清单。"
                )
    return errs


def _load_frozen_manifest(out_dir: Path) -> Optional[Dict[str, Any]]:
    """读冻结基线清单；不存在或非法返回 None。"""
    p = out_dir / FROZEN_MANIFEST_NAME
    if not p.exists():
        return None
    try:
        with p.open("r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def _sha256_file(path: Path) -> str:
    """计算文件 sha256。"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ============================================================
# 关卡 3：文档数字 == **从 kg408.json 重算的**真值
# ============================================================
def assert_stats_match_doc(md_path: Path, truth: Dict[str, Any]) -> List[str]:
    """解析 stats.md 的表格行，断言每个被断言标签的数字 == 重算真值。

    QA M2：`truth` 必须来自 `compute_truth(kg)`（kg408.json），
    **不得**来自 `kg408_stats.json`。
    """
    errs: List[str] = []
    if not md_path.exists():
        return [f"统计文档不存在: {md_path}"]
    text = md_path.read_text(encoding="utf-8")
    found: Dict[str, float] = {}
    for line in text.splitlines():
        m = DOC_ROW_RE.match(line.strip())
        if not m:
            continue
        label = m.group(1).strip()
        found[label] = float(m.group(2))
    for label, key in DOC_TRUTH_FIELDS:
        truth_val = _resolve_key(truth, key)
        if truth_val is None:
            errs.append(f"重算真值缺少字段: {key}")
            continue
        if label not in found:
            errs.append(f"统计文档缺少可断言行: 「{label}」")
            continue
        if abs(found[label] - float(truth_val)) > 1e-9:
            errs.append(
                f"文档数字与重算真值不符：「{label}」文档={found[label]:g}，"
                f"真值[{key}]={float(truth_val):g}"
            )
    return errs


# ============================================================
# 关卡 1b/2b/3b：KB 覆盖率产物防伪证（QA GAP-1）
# ============================================================
# 背景：`kp_chunk_binding.json` / `kp_chunk_coverage.json` / `kb-alignment.md`
# 由 bind_kb_to_kg408.py 单独生成，此前**完全不在**任何防伪证关卡里 ——
# 改 `kb-alignment.md` 的 33.96% 为 99.99%，verify 与 pytest 双双绿。
# 而 kb-alignment.md 是**唯一一份给人看的对外交付物**，必须受保护。

KB_COVERAGE_NAME = "kp_chunk_coverage.json"
KB_BINDING_NAME = "kp_chunk_binding.json"
DEFAULT_KB_DOC = "deliverables/408-kg/kb-alignment.md"

# (md 表格行的 label 前缀, 该行数值单元格里第几个数字(0-based), coverage 取值路径)
KB_DOC_ROW_CHECKS: List[Tuple[str, int, str]] = [
    ("KB chunk 总数", 0, "chunks_total"),
    ("其中 knowledge_point", 0, "chunks_knowledge_point"),
    ("其中 knowledge_variant", 0, "chunks_knowledge_variant"),
    ("章级已绑定", 0, "chapter_level.bound"),
    ("章级已绑定", 1, "chapter_level.bound_pct"),
    ("仅科目级绑定", 0, "chapter_level.subject_only"),
    ("章级未绑定", 0, "chapter_level.unbound"),
    ("骨架章总数", 0, "chapter_level.chapters_total"),
    ("有 chunk 命中的章数", 0, "chapter_level.chapters_with_chunk"),
    ("章级覆盖率", 0, "chapter_level.chapter_coverage_pct"),
    ("考点级覆盖率", 0, "kp_level.kp_coverage_pct"),
    ("考点级 chunk 绑定率", 0, "kp_level.bound_pct_of_eligible"),
    ("alias", 0, "kp_level.match_methods.alias"),
    ("subtopic_exact", 0, "kp_level.match_methods.subtopic_exact"),
    ("合计", 0, "kp_level.bound"),
]

_KB_HEADLINE_RE = re.compile(
    r"\*\*考点级覆盖率 = ([\d.]+)%（(\d+)/(\d+)）\*\*"
)
_KB_VARIANT_RE = re.compile(r"knowledge_variant（(\d+) 条）")
_KB_UNBOUND_RE = re.compile(r"可绑定但未能绑定的 chunk：(\d+) 条")

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def compute_kb_truth(out_dir: Path) -> Optional[Dict[str, Any]]:
    """**在进程内重算** KB 覆盖率真值（跑 binder，不读已入库 coverage.json）。

    与 `compute_truth` 同样的原则：覆盖率也是「可被篡改的产物」，
    断言必须以重算为准，而不是相信磁盘上那份 JSON。
    """
    cmap_path = out_dir / "kg408_chapter_map.json"
    if not cmap_path.exists():
        return None
    scripts_dir = str(_HERE)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import bind_kb_to_kg408 as bind_mod  # 延迟导入：仅在需要时加载 seed_data

    store = Kg408Store.load(
        path=out_dir / "kg408.json",
        unresolved_path=out_dir / "unresolved.json",
        stats_path=out_dir / "kg408_stats.json",
    )
    cmap = json.loads(cmap_path.read_text(encoding="utf-8"))
    chunks = list(bind_mod.seed_data.SEED_KNOWLEDGE_CHUNKS)
    rows = bind_mod.KbBinder(store, cmap).bind_all(chunks)
    return bind_mod.compute_coverage(rows, store)


def assert_kb_coverage_file_is_derived(
    out_dir: Path, cov_truth: Optional[Dict[str, Any]]
) -> List[str]:
    """断言已入库 `kp_chunk_coverage.json` == 重算的覆盖率真值。

    堵 QA GAP-1 变异场景 2：把 coverage.json 的 33.96 改成 99.99。
    """
    errs: List[str] = []
    if cov_truth is None:
        return [f"无法重算 KB 覆盖率真值（缺少 {out_dir / 'kg408_chapter_map.json'}）"]
    p = out_dir / KB_COVERAGE_NAME
    if not p.exists():
        return [f"KB 覆盖率产物缺失: {p}"]
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"KB 覆盖率产物无法解析: {p}（{exc}）"]
    committed = doc.get("coverage")
    if not isinstance(committed, dict):
        return [f"KB 覆盖率产物缺少 coverage 字段: {p}"]

    def _walk(truth: Dict[str, Any], path: str = "") -> None:
        for k, v in truth.items():
            here = f"{path}.{k}" if path else k
            if isinstance(v, dict):
                _walk(v, here)
            else:
                got = _resolve_key(committed, here)
                if got != v:
                    errs.append(
                        f"kp_chunk_coverage.json 与重算真值不符："
                        f"coverage[{here}]={got!r}，重算值={v!r}"
                    )

    _walk(cov_truth)
    return errs


def assert_kb_doc_matches_truth(
    md_path: Path, cov_truth: Optional[Dict[str, Any]]
) -> List[str]:
    """断言 `kb-alignment.md` 表格数字 == 重算覆盖率真值。

    堵 QA GAP-1 变异场景 1：把 md 的 33.96%（36/106）改成 99.99%（106/106）。
    本函数即使 `--no-repro` 也生效（纯数字断言，不需要重跑）。
    """
    errs: List[str] = []
    if cov_truth is None:
        return ["无法重算 KB 覆盖率真值，kb-alignment.md 数字断言跳过"]
    if not md_path.exists():
        return [f"KB 对齐文档不存在: {md_path}"]

    # label 前缀 → 该行所有数值单元格里的数字序列
    rows: Dict[str, List[float]] = {}
    for line in md_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2:
            continue
        label = cells[0].replace("*", "").strip()
        nums: List[float] = []
        for cell in cells[1:]:
            nums.extend(float(x) for x in _NUM_RE.findall(cell.replace("*", "")))
        if label and nums:
            rows.setdefault(label, []).extend(nums)

    def _row_for(prefix: str) -> Optional[List[float]]:
        for label, nums in rows.items():
            if label.startswith(prefix):
                return nums
        return None

    for prefix, idx, key in KB_DOC_ROW_CHECKS:
        nums = _row_for(prefix)
        if nums is None:
            errs.append(f"kb-alignment.md 缺少可断言行（前缀「{prefix}」）")
            continue
        if idx >= len(nums):
            errs.append(f"kb-alignment.md 「{prefix}」行数值个数不足（取第 {idx} 个）")
            continue
        truth_val = _resolve_key(cov_truth, key)
        if truth_val is None:
            errs.append(f"重算覆盖率真值缺少字段: {key}")
            continue
        if abs(nums[idx] - float(truth_val)) > 1e-9:
            errs.append(
                f"kb-alignment.md 数字与重算真值不符：「{prefix}」文档={nums[idx]:g}，"
                f"真值[{key}]={float(truth_val):g}"
            )

    # 正文段落里的数字（不在表格中，单独抓）
    text = md_path.read_text(encoding="utf-8")
    m = _KB_HEADLINE_RE.search(text)
    if not m:
        errs.append("kb-alignment.md 缺少「考点级覆盖率 = …%（…/…）」正文声明")
    else:
        pct, covered, total = float(m.group(1)), int(m.group(2)), int(m.group(3))
        for got, key in (
            (pct, "kp_level.kp_coverage_pct"),
            (covered, "kp_level.kp_covered"),
            (total, "kp_level.kp_total"),
        ):
            truth_val = _resolve_key(cov_truth, key)
            if truth_val is None or abs(got - float(truth_val)) > 1e-9:
                errs.append(
                    f"kb-alignment.md 正文数字与重算真值不符："
                    f"「{key}」文档={got:g}，真值={truth_val}"
                )

    m = _KB_VARIANT_RE.search(text)
    if not m:
        errs.append("kb-alignment.md 缺少 knowledge_variant 条数声明")
    else:
        tv = _resolve_key(cov_truth, "kp_level.variant_excluded_by_design")
        if tv is None or int(m.group(1)) != int(tv):
            errs.append(
                f"kb-alignment.md variant 条数与真值不符：文档={m.group(1)}，真值={tv}"
            )

    m = _KB_UNBOUND_RE.search(text)
    if not m:
        errs.append("kb-alignment.md 缺少「可绑定但未能绑定的 chunk」条数声明")
    else:
        tv = _resolve_key(cov_truth, "kp_level.unbound_eligible")
        if tv is None or int(m.group(1)) != int(tv):
            errs.append(
                f"kb-alignment.md 未绑定条数与真值不符：文档={m.group(1)}，真值={tv}"
            )
    return errs


def rebuild_and_compare_kb(out_dir: Path, doc_path: Optional[Path]) -> List[str]:
    """关卡 2b：重跑 bind_kb_to_kg408.py，逐字节比对 3 个 KB 产物。

    「读真源、写临时目录」：`--out-dir` 指向已入库目录（只读 kg408.json /
    章映射表），`--write-dir` 指向临时目录，避免污染已入库产物。
    """
    errs: List[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="kg408-kbrepro-"))
    try:
        cmd = [
            sys.executable,
            str(_HERE / "bind_kb_to_kg408.py"),
            "--out-dir",
            str(out_dir),
            "--write-dir",
            str(tmp),
            "--doc-out",
            str(tmp / "kb-alignment.md"),
        ]
        proc = subprocess.run(
            cmd,
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            errs.append(
                f"重跑 bind_kb_to_kg408.py 失败（exit {proc.returncode}）: "
                f"{proc.stderr.strip()[:500]}"
            )
            return errs

        pairs: List[Tuple[str, Path, Path]] = [
            (
                KB_COVERAGE_NAME,
                out_dir / KB_COVERAGE_NAME,
                tmp / KB_COVERAGE_NAME,
            ),
            (
                KB_BINDING_NAME,
                out_dir / KB_BINDING_NAME,
                tmp / KB_BINDING_NAME,
            ),
        ]
        if doc_path is not None:
            pairs.append(("kb-alignment.md", Path(doc_path), tmp / "kb-alignment.md"))

        for name, committed, fresh in pairs:
            if not committed.exists():
                errs.append(f"已入库 KB 产物缺失: {committed}")
                continue
            if not fresh.exists():
                errs.append(f"重跑 KB 产物缺失: {fresh}")
                continue
            a = committed.read_bytes()
            b = fresh.read_bytes()
            if a != b:
                errs.append(
                    f"重跑后 {name} 与已入库内容不一致"
                    f"（已入库 {len(a)} 字节，重跑 {len(b)} 字节）"
                    "—— 该文件应逐字节可复现（数字被改动即失败）"
                )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return errs


# ============================================================
# CLI
# ============================================================
def main(argv: Optional[List[str]] = None) -> int:
    """CLI 入口：全绿返回 0，任一关卡失败返回 1。"""
    ap = argparse.ArgumentParser(description="408 知识图谱防伪证校验")
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--doc", default=DEFAULT_DOC, help="统计 Markdown（相对仓库根）")
    ap.add_argument(
        "--kb-doc", default=DEFAULT_KB_DOC,
        help="KB 对齐 Markdown（相对仓库根）",
    )
    ap.add_argument("--check-doc", dest="doc_only", action="store_true",
                    help="**弱模式**：只跑文档数字关卡（漏 stats.json 篡改、"
                         "漏 kg408.json 内容篡改）")
    ap.add_argument("--no-repro", action="store_true",
                    help="**弱模式**：跳过重跑逐字节比对关卡")
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = _ROOT / out_dir

    all_errs: List[str] = []

    store = Kg408Store.load(
        path=out_dir / "kg408.json",
        unresolved_path=out_dir / "unresolved.json",
        stats_path=out_dir / "kg408_stats.json",
    )
    kg = store.kg
    # QA M2：真值一律从 kg408.json **重算**，不读 kg408_stats.json
    truth = compute_truth(kg)
    # QA GAP-3.3：文档还要断言 provenance 里的数值（如源骨架字节数），
    # 因此给文档断言单独一份「真值 + provenance」视图（不影响 stats.json 比对）。
    doc_truth: Dict[str, Any] = dict(truth)
    doc_truth["provenance"] = kg.provenance.to_dict()

    doc = Path(args.doc)
    if not doc.is_absolute():
        doc = _ROOT.parent / doc
    kb_doc = Path(args.kb_doc)
    if not kb_doc.is_absolute():
        kb_doc = _ROOT.parent / kb_doc

    # QA GAP-1：KB 覆盖率真值也必须**重算**（coverage.json 同样可被篡改）
    cov_truth = compute_kb_truth(out_dir)

    if not args.doc_only:
        _log("[verify] 关卡 1/3 结构自检 …")
        all_errs += check_structure(kg)
        all_errs += assert_provenance_anchors(kg, args.source, out_dir)
        all_errs += assert_stats_file_is_derived(store, truth)
        # 关卡 1b：KB 覆盖率产物 == 重算真值
        all_errs += assert_kb_coverage_file_is_derived(out_dir, cov_truth)

        if not args.no_repro:
            _log("[verify] 关卡 2/3 可复现性（重跑比对）…")
            # 用 provenance 里**记录的**输入路径原样重放，而不是重新拼一个
            # 绝对路径 —— 否则 provenance.alias_path 等字段的字面值会变，
            # 产物出现「仅路径字符串不同」的假差异。
            def _recorded(recorded: str, fallback: str) -> Optional[str]:
                """返回可传给子进程的路径字符串；文件不存在则 None。"""
                p = recorded or fallback
                probe = Path(p)
                if not probe.is_absolute():
                    probe = _ROOT / p
                return p if probe.exists() else None

            all_errs += rebuild_and_compare(
                args.source, out_dir,
                _recorded(kg.provenance.alias_path, "data/kg408/kg408_alias.json"),
                _recorded(
                    kg.provenance.chapter_map_path,
                    "data/kg408/kg408_chapter_map.json",
                ),
                replay_command=str(kg.provenance.command or ""),
                manual_nodes=_recorded(
                    kg.provenance.manual_nodes_path,
                    "data/kg408/kg408_manual_nodes.json",
                ),
                doc_path=doc,
            )
            # 关卡 2b：重跑 bind 脚本，逐字节比对 3 个 KB 产物
            _log("[verify] 关卡 2b/3 可复现性（KB 覆盖率产物重跑比对）…")
            all_errs += rebuild_and_compare_kb(out_dir, kb_doc)
        else:
            _log("[verify] 关卡 2/3 可复现性 —— 已跳过（--no-repro，弱模式）")

    _log("[verify] 关卡 3/3 文档数字 == 重算真值（kg408.json / KB binder）…")
    all_errs += assert_stats_match_doc(doc, doc_truth)
    all_errs += assert_kb_doc_matches_truth(kb_doc, cov_truth)

    _log("")
    _log(
        f"[verify] 真值：节点 {truth.get('nodes_total')}"
        f"（源骨架 {truth.get('nodes_from_source')} + 人工补充 "
        f"{truth.get('nodes_manual_supplement')}）"
        f" / 边 {truth.get('edges_total')}"
        f"（先修 {truth.get('edges_prerequisite')} + 跨科 {truth.get('edges_association')}）"
        f" / 未解析 {truth.get('unresolved_total')}"
        f" / 依赖别名表 {truth.get('edges_depending_on_alias')}"
    )
    if cov_truth is not None:
        kl = cov_truth.get("kp_level", {})
        cl = cov_truth.get("chapter_level", {})
        _log(
            f"[verify] KB 覆盖率真值：考点级 {kl.get('kp_coverage_pct')}%"
            f"（{kl.get('kp_covered')}/{kl.get('kp_total')}）"
            f" / 章级 {cl.get('chapter_coverage_pct')}%"
            f" / chunk 绑定 {kl.get('bound')}"
        )

    if all_errs:
        _log(f"[verify] ❌ 失败 {len(all_errs)} 项：")
        for e in all_errs:
            _log(f"  - {e}")
        return 1
    _log("[verify] ✅ 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
