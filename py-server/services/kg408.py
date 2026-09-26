# -*- coding: utf-8 -*-
# ============================================================
# 408 知识图谱（curated 骨架）— 数据模型与内存索引服务层
#
# 定位（对应架构设计 §3 决策 D1/D2/D4）：
#   1. 单一真源 = data/kg408/kg408.json（由 scripts/build_kg408.py 生成，可复现）
#   2. Schema = 扩展既有 Schema A（nodes/edges），**只加字段不改字段**，
#      因此 api/subjects.py / api/knowledge.py / api/teacher.py /
#      engines/frugal_rag_sft.py 四个既有消费方零影响。
#   3. legacy seed_data.KNOWLEDGE_GRAPH（643 节点）**默认并存不替换**。
#
# 边的方向约定（§8.1，最容易搞反，务必遵守）：
#   prerequisite 边：source = 目标考点（后继/依赖方），target = 先修考点（前置）
#   「A 需要先修 B」→ source=A, target=B，箭头指向前置。
#   推论：prerequisites(kp) 取的是该节点的**出边** target 集合（与直觉相反）。
#   association 边：directed=false，只存一条，查询层双向展开。
#
# 零第三方依赖：仅 json / dataclasses / pathlib。
# ============================================================

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("netlearn.kg408")

# ── 默认路径 ──────────────────────────────────────────────────
KG408_DIR = Path(__file__).resolve().parent.parent / "data" / "kg408"
DEFAULT_KG408_PATH = KG408_DIR / "kg408.json"
DEFAULT_UNRESOLVED_PATH = KG408_DIR / "unresolved.json"
DEFAULT_STATS_PATH = KG408_DIR / "kg408_stats.json"

# ── 层级枚举 ──────────────────────────────────────────────────
LEVEL_SUBJECT = "subject"
LEVEL_CHAPTER = "chapter"
LEVEL_KP = "knowledge_point"
LEVELS = (LEVEL_SUBJECT, LEVEL_CHAPTER, LEVEL_KP)

# ── 边类型枚举 ────────────────────────────────────────────────
EDGE_PREREQUISITE = "prerequisite"
EDGE_ASSOCIATION = "association"
EDGE_TYPES = (EDGE_PREREQUISITE, EDGE_ASSOCIATION)

# ── 权重来源枚举（§8.3 诚信红线）──────────────────────────────
WEIGHT_NOT_APPLICABLE = "not_applicable"
WEIGHT_NOT_PROVIDED = "not_provided_by_source"
WEIGHT_MANUAL = "manual"
WEIGHT_LEARNED = "learned_from_error_cooccurrence"
WEIGHT_SOURCES = (
    WEIGHT_NOT_APPLICABLE,
    WEIGHT_NOT_PROVIDED,
    WEIGHT_MANUAL,
    WEIGHT_LEARNED,
)

# ── 解析方式枚举（§8.4，禁止模糊相似度兜底）────────────────────
RES_EXACT = "exact"
RES_ALIAS = "alias"
RES_CHAPTER_LEVEL = "chapter_level"
RES_MANUAL = "manual"
RESOLUTIONS = (RES_EXACT, RES_ALIAS, RES_CHAPTER_LEVEL, RES_MANUAL)

# ── 未解析原因枚举 ────────────────────────────────────────────
REASON_ABSENT = "absent_in_skeleton"
REASON_AMBIGUOUS = "ambiguous_multi_match"
REASON_CHAPTER_ONLY = "chapter_level_only"
UNRESOLVED_REASONS = (REASON_ABSENT, REASON_AMBIGUOUS, REASON_CHAPTER_ONLY)

SUBJECT_CODES: Tuple[str, ...] = ("DS", "CO", "OS", "CN")
SUBJECT_NAMES: Dict[str, str] = {
    "DS": "数据结构",
    "CO": "计算机组成原理",
    "OS": "操作系统",
    "CN": "计算机网络",
}


# ============================================================
# 数据模型
# ============================================================
@dataclass
class Provenance:
    """溯源信息：每一个对外引用的数字都必须能回溯到这里。"""

    source_path: str = ""
    source_sha256: str = ""
    source_bytes: int = 0
    source_mtime_utc: str = ""
    # QA M3 延伸：人工维护表也必须有哈希锚点，否则「改表 + 重跑 + 提交」
    # 这条链路无法追溯到底改了哪一版表。
    alias_path: str = ""
    alias_sha256: str = ""
    chapter_map_path: str = ""
    chapter_map_sha256: str = ""
    manual_nodes_path: str = ""
    manual_nodes_sha256: str = ""
    generator: str = "scripts/build_kg408.py"
    generator_version: str = "1.0.0"
    parser_rule_version: str = "kg408-parse-r1"
    command: str = ""
    generated_at_utc: str = ""
    generated_at_utc_basis: str = (
        "source_file_mtime_utc__deterministic"
    )

    def to_dict(self) -> Dict[str, Any]:
        """按固定键序导出，保证 JSON 字节级可复现。"""
        return {
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "source_bytes": self.source_bytes,
            "source_mtime_utc": self.source_mtime_utc,
            "alias_path": self.alias_path,
            "alias_sha256": self.alias_sha256,
            "chapter_map_path": self.chapter_map_path,
            "chapter_map_sha256": self.chapter_map_sha256,
            "manual_nodes_path": self.manual_nodes_path,
            "manual_nodes_sha256": self.manual_nodes_sha256,
            "generator": self.generator,
            "generator_version": self.generator_version,
            "parser_rule_version": self.parser_rule_version,
            "command": self.command,
            "generated_at_utc": self.generated_at_utc,
            "generated_at_utc_basis": self.generated_at_utc_basis,
        }

    @staticmethod
    def from_dict(data: Optional[Dict[str, Any]]) -> "Provenance":
        """从 dict 构造；缺失字段用默认值，绝不因缺键崩溃。"""
        data = data or {}
        return Provenance(
            source_path=str(data.get("source_path", "")),
            source_sha256=str(data.get("source_sha256", "")),
            source_bytes=int(data.get("source_bytes", 0) or 0),
            source_mtime_utc=str(data.get("source_mtime_utc", "")),
            alias_path=str(data.get("alias_path", "")),
            alias_sha256=str(data.get("alias_sha256", "")),
            chapter_map_path=str(data.get("chapter_map_path", "")),
            chapter_map_sha256=str(data.get("chapter_map_sha256", "")),
            manual_nodes_path=str(data.get("manual_nodes_path", "")),
            manual_nodes_sha256=str(data.get("manual_nodes_sha256", "")),
            generator=str(data.get("generator", "scripts/build_kg408.py")),
            generator_version=str(data.get("generator_version", "1.0.0")),
            parser_rule_version=str(data.get("parser_rule_version", "kg408-parse-r1")),
            command=str(data.get("command", "")),
            generated_at_utc=str(data.get("generated_at_utc", "")),
            generated_at_utc_basis=str(
                data.get("generated_at_utc_basis", "source_file_mtime_utc__deterministic")
            ),
        )


ORIGIN_SOURCE = "source"
ORIGIN_MANUAL = "manual"


@dataclass
class KgNode:
    """图节点。字段 = 既有 {id,label,group} + 新增层级/溯源字段。

    `origin` 用于把「源骨架节点」与「人工补充节点」**永不合并**地区分开
    （学科负责人裁决 2026-09-25 补入「磁盘调度」后新增）：
    统计时必须分别列出两边的数量，否则读者无法判断哪些数字来自源文档、
    哪些是人补的。
    """

    id: str = ""
    label: str = ""
    level: str = LEVEL_KP
    subject: str = ""
    chapter: Optional[str] = None
    parent_id: Optional[str] = None
    ordinal: int = 0
    source_row: int = 0
    aliases: List[str] = field(default_factory=list)
    group: Optional[int] = None
    origin: str = ORIGIN_SOURCE

    def is_leaf(self) -> bool:
        """是否为叶子（考点）节点。"""
        return self.level == LEVEL_KP

    def to_dict(self) -> Dict[str, Any]:
        """按固定键序导出。"""
        return {
            "id": self.id,
            "label": self.label,
            "group": self.group,
            "level": self.level,
            "subject": self.subject,
            "chapter": self.chapter,
            "parent_id": self.parent_id,
            "ordinal": self.ordinal,
            "source_row": self.source_row,
            "aliases": list(self.aliases),
            "origin": self.origin,
        }

    def to_legacy(self) -> Dict[str, Any]:
        """投影回 Schema A 既有三字段，供老消费方使用。"""
        return {"id": self.id, "label": self.label, "group": self.group}

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "KgNode":
        """从 dict 构造。"""
        return KgNode(
            id=str(data.get("id", "")),
            label=str(data.get("label", "")),
            level=str(data.get("level", LEVEL_KP)),
            subject=str(data.get("subject", "")),
            chapter=data.get("chapter", None),
            parent_id=data.get("parent_id", None),
            ordinal=int(data.get("ordinal", 0) or 0),
            source_row=int(data.get("source_row", 0) or 0),
            aliases=list(data.get("aliases", []) or []),
            group=data.get("group", None),
            origin=str(data.get("origin", ORIGIN_SOURCE)),
        )


@dataclass
class KgEdge:
    """图边。字段 = 既有 {source,target} + 新增类型/权重/解析留痕字段。

    resolution 口径修正（QA M7）：
        `resolution` 取**两端中最不确定的那一端**（最弱环节）：只要任一端点
        依赖人工别名表，整条边就记 `alias`。此前只记录单个端点，导致
        「B树→二叉排序树」这类「起点靠别名、终点精确」的边被记成 `exact`，
        使读者低估人工判断的覆盖面。
        `source_resolution` / `target_resolution` 保留两端各自的原始口径，
        `depends_on_alias` 是「是否依赖人工别名表」的显式布尔量。
    """

    id: str = ""
    source: str = ""
    target: str = ""
    type: str = EDGE_PREREQUISITE
    directed: bool = True
    weight: Optional[float] = None
    weight_source: str = WEIGHT_NOT_APPLICABLE
    subject_scope: str = "intra"
    resolution: str = RES_EXACT
    source_resolution: str = RES_EXACT
    target_resolution: str = RES_EXACT
    depends_on_alias: bool = False
    source_row: int = 0
    evidence: str = ""

    def sync_resolution(self) -> None:
        """按两端 resolution 重算 `resolution` 与 `depends_on_alias`。

        最弱环节优先：alias > manual > chapter_level > exact。
        """
        rank = {RES_EXACT: 0, RES_CHAPTER_LEVEL: 1, RES_MANUAL: 2, RES_ALIAS: 3}
        weakest = max(
            (self.source_resolution, self.target_resolution),
            key=lambda r: rank.get(r, 0),
        )
        self.resolution = weakest
        self.depends_on_alias = (
            self.source_resolution == RES_ALIAS or self.target_resolution == RES_ALIAS
        )

    def both_dirs(self) -> List[Tuple[str, str]]:
        """返回该边在查询层应展开的有序对；无向边返回双向。"""
        if self.directed:
            return [(self.source, self.target)]
        return [(self.source, self.target), (self.target, self.source)]

    def to_dict(self) -> Dict[str, Any]:
        """按固定键序导出。"""
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "directed": self.directed,
            "weight": self.weight,
            "weight_source": self.weight_source,
            "subject_scope": self.subject_scope,
            "resolution": self.resolution,
            "source_resolution": self.source_resolution,
            "target_resolution": self.target_resolution,
            "depends_on_alias": self.depends_on_alias,
            "source_row": self.source_row,
            "evidence": self.evidence,
        }

    def to_legacy(self) -> Dict[str, Any]:
        """投影回 Schema A 既有两字段。"""
        return {"source": self.source, "target": self.target}

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "KgEdge":
        """从 dict 构造。"""
        return KgEdge(
            id=str(data.get("id", "")),
            source=str(data.get("source", "")),
            target=str(data.get("target", "")),
            type=str(data.get("type", EDGE_PREREQUISITE)),
            directed=bool(data.get("directed", True)),
            weight=data.get("weight", None),
            weight_source=str(data.get("weight_source", WEIGHT_NOT_APPLICABLE)),
            subject_scope=str(data.get("subject_scope", "intra")),
            resolution=str(data.get("resolution", RES_EXACT)),
            source_resolution=str(data.get("source_resolution", RES_EXACT)),
            target_resolution=str(data.get("target_resolution", RES_EXACT)),
            depends_on_alias=bool(data.get("depends_on_alias", False)),
            source_row=int(data.get("source_row", 0) or 0),
            evidence=str(data.get("evidence", "")),
        )


@dataclass
class UnresolvedRef:
    """未解析引用（诚信产物，必须可见，隐藏即视为伪证）。"""

    kind: str = ""            # prerequisite_target | prerequisite | cross_subject
    raw_name: str = ""
    subject_hint: Optional[str] = None
    context_row: int = 0
    context: str = ""         # 原文片段（目标考点 / 关联名）
    reason: str = REASON_ABSENT
    detail: str = ""
    suggested_action: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """按固定键序导出。"""
        return {
            "kind": self.kind,
            "raw_name": self.raw_name,
            "subject_hint": self.subject_hint,
            "context_row": self.context_row,
            "context": self.context,
            "reason": self.reason,
            "detail": self.detail,
            "suggested_action": self.suggested_action,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "UnresolvedRef":
        """从 dict 构造。"""
        return UnresolvedRef(
            kind=str(data.get("kind", "")),
            raw_name=str(data.get("raw_name", "")),
            subject_hint=data.get("subject_hint", None),
            context_row=int(data.get("context_row", 0) or 0),
            context=str(data.get("context", "")),
            reason=str(data.get("reason", REASON_ABSENT)),
            detail=str(data.get("detail", "")),
            suggested_action=str(data.get("suggested_action", "")),
        )


@dataclass
class Kg408:
    """整张图（单一真源的内存表示）。"""

    nodes: List[KgNode] = field(default_factory=list)
    edges: List[KgEdge] = field(default_factory=list)
    provenance: Provenance = field(default_factory=Provenance)
    unresolved: List[UnresolvedRef] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    # 源文档侧声明计数（先修声明总数、跨科引用总数等）。
    # 无法仅由图结构反推，故随 kg408.json 一并持久化 —— 它是真源的一部分，
    # 而 kg408_stats.json 只是它的派生产物。
    source_counts: Dict[str, Any] = field(default_factory=dict)

    # ── 分科视图 ──────────────────────────────────────────────
    def subject_view(self, subj: str) -> "Kg408":
        """导出某科目的子树视图；边两端均在子树内才保留。

        这是替代「手写 CN_KNOWLEDGE_GRAPH 常量」的方案（决策 D3）：
        分科视图一律由单一真源导出，杜绝第 5 份真源。
        """
        code = str(subj or "").strip().upper()
        sub_nodes = [n for n in self.nodes if n.subject == code]
        keep_ids = {n.id for n in sub_nodes}
        sub_edges = [
            e
            for e in self.edges
            if e.source in keep_ids and e.target in keep_ids
        ]
        return Kg408(
            nodes=sub_nodes,
            edges=sub_edges,
            provenance=self.provenance,
            unresolved=[u for u in self.unresolved if u.subject_hint == code],
            stats=self._sub_stats(code, sub_nodes, sub_edges),
        )

    def _sub_stats(
        self, code: str, nodes: List[KgNode], edges: List[KgEdge]
    ) -> Dict[str, Any]:
        """计算分科视图的统计。"""
        return {
            "subject": code,
            "subject_name": SUBJECT_NAMES.get(code, code),
            "nodes_total": len(nodes),
            "nodes_subject": sum(1 for n in nodes if n.level == LEVEL_SUBJECT),
            "nodes_chapter": sum(1 for n in nodes if n.level == LEVEL_CHAPTER),
            "nodes_knowledge_point": sum(1 for n in nodes if n.level == LEVEL_KP),
            "edges_total": len(edges),
            "edges_prerequisite": sum(1 for e in edges if e.type == EDGE_PREREQUISITE),
            "edges_association": sum(1 for e in edges if e.type == EDGE_ASSOCIATION),
        }

    # ── 投影 / 统计 ───────────────────────────────────────────
    def to_legacy(self) -> Dict[str, Any]:
        """投影回 Schema A（nodes/edges，仅老字段），供既有消费方对比。"""
        return {
            "nodes": [n.to_legacy() for n in self.nodes],
            "edges": [e.to_legacy() for e in self.edges],
        }

    def to_dict(self) -> Dict[str, Any]:
        """完整导出（含 provenance / unresolved / stats）。"""
        return {
            "schema": "kg408/v1",
            "provenance": self.provenance.to_dict(),
            "source_counts": dict(self.source_counts),
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "unresolved": [u.to_dict() for u in self.unresolved],
            "stats": dict(self.stats),
        }

    def stats_view(self) -> Dict[str, Any]:
        """返回统计；始终由节点/边/未解析清单重算（不读落盘值）。"""
        return build_stats(
            self.nodes, self.edges, self.unresolved, self.source_counts
        )

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Kg408":
        """从 dict 构造。"""
        return Kg408(
            nodes=[KgNode.from_dict(d) for d in (data.get("nodes") or [])],
            edges=[KgEdge.from_dict(d) for d in (data.get("edges") or [])],
            provenance=Provenance.from_dict(data.get("provenance")),
            unresolved=[
                UnresolvedRef.from_dict(d) for d in (data.get("unresolved") or [])
            ],
            stats=dict(data.get("stats") or {}),
            source_counts=dict(data.get("source_counts") or {}),
        )


def build_stats(
    nodes: List[KgNode],
    edges: List[KgEdge],
    unresolved: List[UnresolvedRef],
    source_counts: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """由节点/边/未解析清单计算统计（唯一口径，避免多处各算各的）。

    `source_counts` 是**源文档侧的声明计数**（先修声明总数、跨科引用总数等），
    无法仅从图结构反推，故作为参数传入。它持久化在 kg408.json 的
    `source_counts` 字段里，因此 kg408.json 依然是唯一真源。

    QA M2：本函数是唯一统计口径。`kg408_stats.json` 与文档都被要求
    等于本函数的输出，杜绝「第二真源」。
    """
    source_counts = source_counts or {}
    by_subject: Dict[str, Dict[str, int]] = {}
    for code in SUBJECT_CODES:
        by_subject[code] = {
            "chapters": sum(
                1 for n in nodes if n.subject == code and n.level == LEVEL_CHAPTER
            ),
            "knowledge_points": sum(
                1 for n in nodes if n.subject == code and n.level == LEVEL_KP
            ),
        }
    reason_counts: Dict[str, int] = {}
    for u in unresolved:
        reason_counts[u.reason] = reason_counts.get(u.reason, 0) + 1
    stats: Dict[str, Any] = {
        "nodes_total": len(nodes),
        "nodes_subject": sum(1 for n in nodes if n.level == LEVEL_SUBJECT),
        "nodes_chapter": sum(1 for n in nodes if n.level == LEVEL_CHAPTER),
        "nodes_knowledge_point": sum(1 for n in nodes if n.level == LEVEL_KP),
        # 源骨架节点 vs 人工补充节点：**永不合并**，必须分列对外呈现
        "nodes_from_source": sum(1 for n in nodes if n.origin == ORIGIN_SOURCE),
        "nodes_manual_supplement": sum(1 for n in nodes if n.origin == ORIGIN_MANUAL),
        "nodes_knowledge_point_from_source": sum(
            1 for n in nodes if n.level == LEVEL_KP and n.origin == ORIGIN_SOURCE
        ),
        "nodes_knowledge_point_manual": sum(
            1 for n in nodes if n.level == LEVEL_KP and n.origin == ORIGIN_MANUAL
        ),
        "edges_total": len(edges),
        "edges_prerequisite": sum(1 for e in edges if e.type == EDGE_PREREQUISITE),
        "edges_association": sum(1 for e in edges if e.type == EDGE_ASSOCIATION),
        "unresolved_total": len(unresolved),
        "unresolved_by_reason": reason_counts,
        "by_subject": by_subject,
        "weight_null_count": sum(1 for e in edges if e.weight is None),
        "resolution_counts": _count_by(edges, lambda e: e.resolution),
        # QA M7：如实暴露「有多少条边依赖人工别名表」。这是中期材料必须
        # 交代的数字——它决定这 18 条边里有多少是人工判断而非源文档直给。
        "edges_depending_on_alias": sum(1 for e in edges if e.depends_on_alias),
        "edges_pure_exact": sum(
            1 for e in edges if not e.depends_on_alias
        ),
        # 诚实记录：源声明的先修边里也存在跨科情形（如 CO 虚拟存储 ← OS 分页），
        # 与「先修边=同科内」的直觉不一致，如实暴露而不改写。
        "edges_prerequisite_cross_subject": sum(
            1
            for e in edges
            if e.type == EDGE_PREREQUISITE and e.subject_scope == "cross"
        ),
    }
    # 源文档侧声明计数（无法从图结构反推，随 kg408.json 一并持久化）。
    # 注意：这是**全图口径**的文档级属性，只在全图视图（subject=all）里出现；
    # 分科子图不携带这些 key（`stats_scope="subject"` 明确标示），
    # 以免「23 条声明」被误读成某个科目的声明数。
    if source_counts:
        for k, v in source_counts.items():
            stats[k] = v
        decl = int(source_counts.get("source_prereq_declarations", 0) or 0)
        # QA GAP-3.2：分子必须与分母**同单位**（都是「声明」）。
        # 旧实现拿「已解析先修边数」当分子，一条声明将来产出多条边就会失真。
        got = int(
            source_counts.get(
                "source_prereq_declarations_resolved",
                stats.get("edges_prerequisite", 0),
            )
            or 0
        )
        stats["prereq_success_pct"] = round(got * 100.0 / decl, 1) if decl else 0.0
    return stats


def _count_by(items: List[Any], key_fn: Any) -> Dict[str, int]:
    """按 key_fn 计数（保持插入序，避免 dict 顺序抖动影响 diff）。"""
    out: Dict[str, int] = {}
    for it in items:
        k = str(key_fn(it))
        out[k] = out.get(k, 0) + 1
    return out


# ============================================================
# 服务层：加载 / 索引 / ego-graph 查询
# ============================================================
class Kg408Store:
    """408 图谱内存索引。135 节点规模，全量常驻，无需图数据库。"""

    def __init__(self, kg: Optional[Kg408] = None) -> None:
        self._kg: Kg408 = kg or Kg408()
        self._by_id: Dict[str, KgNode] = {}
        self._children: Dict[str, List[str]] = {}
        self._out: Dict[str, List[KgEdge]] = {}
        self._in: Dict[str, List[KgEdge]] = {}
        # kg408_stats.json 里落盘的 stats（派生产物，仅供校验比对）
        self._stats_file: Optional[Dict[str, Any]] = None
        if kg is not None:
            self._reindex()

    # ── 加载 ──────────────────────────────────────────────────
    @classmethod
    def load(
        cls,
        path: Optional[Path] = None,
        unresolved_path: Optional[Path] = None,
        stats_path: Optional[Path] = None,
    ) -> "Kg408Store":
        """从 JSON 加载并建索引。文件缺失时抛带明确信息的异常。"""
        p = Path(path) if path else DEFAULT_KG408_PATH
        if not p.exists():
            raise FileNotFoundError(
                f"kg408 真源不存在: {p} —— 请先运行 "
                f"python scripts/build_kg408.py --source <骨架HTML> --out-dir data/kg408"
            )
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        kg = Kg408.from_dict(data)

        up = Path(unresolved_path) if unresolved_path else DEFAULT_UNRESOLVED_PATH
        if up.exists():
            with up.open("r", encoding="utf-8") as f:
                udata = json.load(f)
            kg.unresolved = [
                UnresolvedRef.from_dict(d) for d in (udata.get("unresolved") or [])
            ]

        sp = Path(stats_path) if stats_path else DEFAULT_STATS_PATH
        stats_from_file: Optional[Dict[str, Any]] = None
        if sp.exists():
            with sp.open("r", encoding="utf-8") as f:
                sdata = json.load(f)
            if isinstance(sdata.get("stats"), dict):
                stats_from_file = dict(sdata["stats"])

        # ── QA M2 修复：kg408.json 是唯一真源 ──────────────────
        # 此前直接把 kg408_stats.json 的 stats 读进 kg.stats，使它成为
        # 「无锚点的第二真源」：同步篡改 md + stats.json 即可让校验全绿。
        # 现在 stats 一律由 nodes/edges/unresolved **重算**，stats.json
        # 降级为派生产物，仅原样保留在 _stats_file 供校验器比对。
        kg.stats = build_stats(
            kg.nodes, kg.edges, kg.unresolved, kg.source_counts
        )

        inst = cls(kg)
        inst._stats_file = stats_from_file
        return inst

    @property
    def stats_file(self) -> Optional[Dict[str, Any]]:
        """返回 `kg408_stats.json` 里**落盘**的 stats（派生产物，非真源）。

        仅供 verify_kg408.py 做「派生产物 == 重算真值」比对使用；
        任何业务读取都应走 `stats()`（重算值）。
        """
        return self._stats_file

    def _reindex(self) -> None:
        """重建四类索引：_by_id / _children / _out / _in。"""
        self._by_id = {n.id: n for n in self._kg.nodes}
        self._children = {}
        for n in self._kg.nodes:
            if n.parent_id:
                self._children.setdefault(n.parent_id, []).append(n.id)
        self._out = {}
        self._in = {}
        for e in self._kg.edges:
            self._out.setdefault(e.source, []).append(e)
            self._in.setdefault(e.target, []).append(e)

    @property
    def kg(self) -> Kg408:
        """返回底层图对象。"""
        return self._kg

    @property
    def provenance(self) -> Provenance:
        """返回溯源信息。"""
        return self._kg.provenance

    # ── 基础查询 ──────────────────────────────────────────────
    def get(self, node_id: str) -> Optional[KgNode]:
        """按 id 取节点；不存在返回 None（由调用方决定 404）。"""
        return self._by_id.get(str(node_id or ""))

    def node_ids(self) -> List[str]:
        """全部节点 id（按图中顺序）。"""
        return [n.id for n in self._kg.nodes]

    def by_subject(self, subj: str) -> List[KgNode]:
        """取某科目全部节点（含科目/章/考点三级）。"""
        code = str(subj or "").strip().upper()
        return [n for n in self._kg.nodes if n.subject == code]

    def children(self, node_id: str) -> List[KgNode]:
        """取直接子节点。"""
        return [self._by_id[i] for i in self._children.get(node_id, []) if i in self._by_id]

    def all_nodes(self) -> List[KgNode]:
        """全部节点。"""
        return list(self._kg.nodes)

    def all_edges(self) -> List[KgEdge]:
        """全部边。"""
        return list(self._kg.edges)

    def unresolved(self) -> List[UnresolvedRef]:
        """未解析引用清单（诚信透明）。"""
        return list(self._kg.unresolved)

    # ── 边查询（方向约定见文件头注释）──────────────────────────
    def prerequisites(self, kp_id: str) -> List[KgNode]:
        """返回 kp 的**先修项** = 出边 target。

        注意：prerequisite 边的 source 是「目标考点」，target 才是「先修考点」，
        所以这里取的是出边（与直觉相反，勿改）。
        """
        out: List[KgNode] = []
        for e in self._out.get(kp_id, []):
            if e.type != EDGE_PREREQUISITE:
                continue
            n = self._by_id.get(e.target)
            if n is not None:
                out.append(n)
        return out

    def dependents(self, kp_id: str) -> List[KgNode]:
        """返回「以 kp 为先修」的后继考点 = 入边 source。"""
        out: List[KgNode] = []
        for e in self._in.get(kp_id, []):
            if e.type != EDGE_PREREQUISITE:
                continue
            n = self._by_id.get(e.source)
            if n is not None:
                out.append(n)
        return out

    def associations(self, kp_id: str) -> List[KgNode]:
        """返回跨科关联邻居；无向边双向返回（不重复存反向边，查询层展开）。"""
        seen: Dict[str, KgNode] = {}
        for e in self._kg.edges:
            if e.type != EDGE_ASSOCIATION:
                continue
            other: Optional[str] = None
            if e.source == kp_id:
                other = e.target
            elif e.target == kp_id:
                other = e.source
            if other is None:
                continue
            n = self._by_id.get(other)
            if n is not None and other not in seen:
                seen[other] = n
        return list(seen.values())

    # ── ego-graph ─────────────────────────────────────────────
    def ego_graph(self, kp_id: str, hops: int = 2) -> Optional[Dict[str, Any]]:
        """以 kp 为中心的 1~2 跳邻域（BayesG 聚焦掩码的采样空间）。

        hop1 = 先修项 ∪ 跨科关联；hop2 = 对 hop1 再展开（先修 ∪ 关联）。
        candidates 排序：hop1-先修(0) > hop1-跨科(1) > hop2(2)。
        """
        ego = self.get(kp_id)
        if ego is None:
            return None
        hops = 1 if int(hops or 1) <= 1 else 2

        hop1: Dict[str, Dict[str, Any]] = {}

        def _put(bucket: Dict[str, Dict[str, Any]], node: KgNode, via: str, hop: int) -> None:
            if node.id == ego.id:
                return
            if node.id in bucket:
                return
            bucket[node.id] = {"node": node.to_dict(), "via": via, "hop": hop}

        for n in self.prerequisites(ego.id):
            _put(hop1, n, EDGE_PREREQUISITE, 1)
        for n in self.associations(ego.id):
            _put(hop1, n, EDGE_ASSOCIATION, 1)

        hop2: Dict[str, Dict[str, Any]] = {}
        if hops >= 2:
            for nid in list(hop1.keys()):
                for n in self.prerequisites(nid):
                    if n.id == ego.id or n.id in hop1:
                        continue
                    _put(hop2, n, EDGE_PREREQUISITE, 2)
                for n in self.associations(nid):
                    if n.id == ego.id or n.id in hop1:
                        continue
                    _put(hop2, n, EDGE_ASSOCIATION, 2)

        rank_of = {EDGE_PREREQUISITE: 0, EDGE_ASSOCIATION: 1}

        def _sorted(bucket: Dict[str, Dict[str, Any]], base: int) -> List[Dict[str, Any]]:
            items = sorted(
                bucket.values(),
                key=lambda d: (rank_of.get(str(d["via"]), 9), str(d["node"]["id"])),
            )
            return items

        hop1_list = _sorted(hop1, 0)
        hop2_list = _sorted(hop2, 0)

        candidates: List[Dict[str, Any]] = []
        for d in hop1_list:
            candidates.append(
                {
                    "id": d["node"]["id"],
                    "label": d["node"]["label"],
                    "subject": d["node"]["subject"],
                    "chapter": d["node"]["chapter"],
                    "hop": 1,
                    "via": d["via"],
                    "rank": rank_of.get(str(d["via"]), 9),
                }
            )
        for d in hop2_list:
            candidates.append(
                {
                    "id": d["node"]["id"],
                    "label": d["node"]["label"],
                    "subject": d["node"]["subject"],
                    "chapter": d["node"]["chapter"],
                    "hop": 2,
                    "via": d["via"],
                    "rank": 2,
                }
            )

        return {
            "ego": ego.to_dict(),
            "hops": hops,
            "hop1": hop1_list,
            "hop2": hop2_list,
            "candidates": candidates,
        }

    # ── 章级上卷适配口（§3.5，本期不接 MemoryGraphDB）────────────
    def subject_rollup(self, kp_id: str) -> Optional[str]:
        """考点级 → 章级上卷，返回所属章节点 id；不存在返回 None。"""
        n = self.get(kp_id)
        if n is None:
            return None
        if n.level == LEVEL_CHAPTER:
            return n.id
        if n.parent_id:
            parent = self.get(n.parent_id)
            if parent is not None and parent.level == LEVEL_CHAPTER:
                return parent.id
        return None

    # ── 导出 ──────────────────────────────────────────────────
    def graph_view(self, subject: str = "all") -> Dict[str, Any]:
        """返回给接口层的图视图：{nodes, edges, stats, provenance}。

        QA M11 修复：stats 一律用 `build_stats(...)` 现算，**键集合在
        「整图」与「分科子图」两种情况下完全一致**。此前分科视图走
        `_sub_stats()`，导致 `weight_null_count` / `resolution_counts` /
        `by_subject` / `unresolved_total` 等键缺失（同一 key 两种契约）。
        """
        s = str(subject or "all").strip().upper()
        is_all = s in ("ALL", "", "全部")
        kg = self._kg if is_all else self._kg.subject_view(s)
        # 源文档声明计数是全图口径，只在全图视图携带（见 build_stats 注释）
        stats = build_stats(
            kg.nodes, kg.edges, kg.unresolved,
            self._kg.source_counts if is_all else None,
        )
        stats["stats_scope"] = "global" if is_all else "subject"
        if not is_all:
            stats["subject"] = s
            stats["subject_name"] = SUBJECT_NAMES.get(s, s)
        return {
            "nodes": [n.to_dict() for n in kg.nodes],
            "edges": [e.to_dict() for e in kg.edges],
            "stats": stats,
            "provenance": kg.provenance.to_dict(),
        }

    def stats(self) -> Dict[str, Any]:
        """返回统计 —— **始终由 kg408.json 的 nodes/edges/unresolved 重算**。

        QA M2 修复：不再返回 `kg408_stats.json` 里落盘的值（那是派生产物）。
        """
        return build_stats(
            self._kg.nodes, self._kg.edges, self._kg.unresolved, self._kg.source_counts
        )


# ── 进程内单例（懒加载，避免 import 期就 IO）─────────────────────
_STORE: Optional[Kg408Store] = None


def get_store(reload: bool = False) -> Kg408Store:
    """获取进程内共享的 Kg408Store；首次调用时懒加载。"""
    global _STORE
    if _STORE is None or reload:
        _STORE = Kg408Store.load()
    return _STORE


def reset_store() -> None:
    """清空单例（供测试使用）。"""
    global _STORE
    _STORE = None
