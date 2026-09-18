# ============================================================
# Evidence 数据结构 — T1 基础层单一来源（schema 单一来源）
#
# 定义 Evidence / EvidenceChain / ArgumentChain / EvidenceCard。
# 规则版（lite）与真版（real）共识后端都必须产出本模块定义的 Evidence，
# 前端只认这一份 → 杜绝双份结构（架构 §7.1）。
#
# 诚信红线内建：
# - Evidence.version ∈ {"lite", "real"} 区分规则版 / 真版证据；
# - Evidence.source_type ∈ {"rule", "real", "retrieval"} 区分证据来源；
# - 规则版填 source_type="rule" + 低可信 + 标注 version_tag="v1 规则原型"；
# - 真版发生型证据（真实 Trace / 实验成效）不可造假（见 train_mixer.py 顶部声明）。
#
# 本文件仅定义数据结构（可序列化），不实现任何检索 / 共识 / 训练算法
# （FrugalRAG 重排见 T2、GOMARL 共识见 T3、奖励模型 / 训练见 T5）。
# ============================================================

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

# 算法版本：lite=规则版/原型；real=真版（灰度开关）
AlgorithmVersion = Literal["lite", "real"]
# 证据来源类型：rule=规则版；real=真版发生型（真实 Trace / 成效）；retrieval=检索召回
EvidenceSourceType = Literal["rule", "real", "retrieval"]
# 论证链节点类型
ChainNodeKind = Literal["agent", "consensus", "conflict", "conclusion"]
# 论证链边关系
ChainEdgeRelation = Literal["supports", "conflicts", "resolves"]


def _utcnow() -> datetime:
    """返回带时区的当前 UTC 时间（可序列化、跨时区一致）。"""
    return datetime.now(timezone.utc)


def _short_uid(prefix: str) -> str:
    """生成带前缀的短 UID，便于 debug 与前端稳定 key。"""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class Evidence(BaseModel):
    """单条证据（可序列化、单一来源）。

    用于 7 路资源 Agent 生成内容 → 可溯源论证链的最小单元。
    字段为架构 §3 类图 + T1 任务书要求的最小超集。
    """

    evidence_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="证据唯一 ID",
    )
    group_id: str = Field(
        default="",
        description="408 知识点 group 编号（如 'G408-001'）",
    )
    snippet: str = Field(default="", description="原文片段（被引用的文本）")
    credibility: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="可信度 0-1；规则版填低可信，真版按真实信号填充",
    )
    source_agent: str = Field(default="", description="产出该证据的 Agent 名（如 Teacher/QuizMaster）")
    version: AlgorithmVersion = Field(
        default="lite",
        description="lite=规则版/原型 | real=真版（区分规则版/真版证据）",
    )
    source_type: EvidenceSourceType = Field(
        default="rule",
        description="证据来源：rule=规则版 | real=真版发生型 | retrieval=检索召回",
    )
    chunk_ref: str = Field(default="", description="关联检索片段引用（chunk id 等）")
    metadata: dict = Field(default_factory=dict, description="扩展元数据（可放 group 置信、命中率等）")
    created_at: datetime = Field(default_factory=_utcnow, description="创建时间(UTC)")

    def to_dict(self) -> dict:
        """序列化为可 JSON 化的 dict（前端证据卡 / 日志消费）。"""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict) -> "Evidence":
        """从 dict 反序列化（兼容 to_dict 输出）。"""
        return cls.model_validate(data)

    def mark_rule_prototype(self) -> "Evidence":
        """就地标注为「v1 规则原型」（规则版诚信标记，便于前端按 flag 显隐）。"""
        self.version = "lite"
        self.source_type = "rule"
        return self


class EvidenceChain(BaseModel):
    """证据列表 → 可溯源论证链（轻量容器）。

    T3 的 EvidenceConsensus 节点将 7 路生成结果汇聚为 EvidenceChain，
    供前端证据卡 / ArgumentChain 消费。T1 仅定义容器与序列化，不实现汇聚算法。
    """

    chain_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    version: AlgorithmVersion = Field(default="lite")
    evidences: list[Evidence] = Field(default_factory=list)
    conclusion: Optional[str] = Field(default=None, description="汇聚结论（T3 写入）")
    consensus_score: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="共识可信度总评（T3 写入）"
    )
    created_at: datetime = Field(default_factory=_utcnow)

    def add(self, evidence: Evidence) -> "EvidenceChain":
        """追加一条证据（链式调用）。"""
        self.evidences.append(evidence)
        return self

    def add_many(self, evidences: list[Evidence]) -> "EvidenceChain":
        """批量追加证据。"""
        self.evidences.extend(evidences)
        return self

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict) -> "EvidenceChain":
        return cls.model_validate(data)


class ChainNode(BaseModel):
    """论证链节点（agent / consensus / conflict / conclusion）。"""

    node_id: str = Field(default_factory=lambda: _short_uid("node"))
    kind: ChainNodeKind = "agent"
    label: str = Field(default="", description="节点展示标签")
    credibility: float = Field(default=0.0, ge=0.0, le=1.0, description="节点可信度 0-1")


class ChainEdge(BaseModel):
    """论证链有向边（supports / conflicts / resolves）。"""

    from_id: str
    to_id: str
    relation: ChainEdgeRelation = "supports"


class ArgumentChain(BaseModel):
    """可溯源论证链（节点-边结构，T3 EvidenceConsensus 构建）。

    T1 仅定义容器 + 轻量构建 API，供 T3 复用，避免双份结构。
    """

    chain_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    version: AlgorithmVersion = Field(default="lite")
    nodes: list[ChainNode] = Field(default_factory=list)
    edges: list[ChainEdge] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)

    def add_evidence_node(
        self, agent: str, credibility: float = 0.0, label: str = ""
    ) -> ChainNode:
        """添加一个 agent 证据节点，返回该节点（便于后续连边）。"""
        node = ChainNode(kind="agent", label=label or agent, credibility=credibility)
        self.nodes.append(node)
        return node

    def add_consensus_node(self, score: float, label: str = "consensus") -> ChainNode:
        """添加共识节点（T3 写入 dynamic weights 总评）。"""
        node = ChainNode(kind="consensus", label=label, credibility=score)
        self.nodes.append(node)
        return node

    def add_conflict_node(self, label: str = "conflict") -> ChainNode:
        """添加冲突节点（T3 冲突消解前占位）。"""
        node = ChainNode(kind="conflict", label=label)
        self.nodes.append(node)
        return node

    def add_edge(self, from_id: str, to_id: str, relation: str = "supports") -> ChainEdge:
        """连接两个节点，relation 限制为 supports/conflicts/resolves。"""
        edge = ChainEdge(from_id=from_id, to_id=to_id, relation=relation)  # type: ignore[arg-type]
        self.edges.append(edge)
        return edge

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict) -> "ArgumentChain":
        return cls.model_validate(data)


class EvidenceCard(BaseModel):
    """前端证据卡 payload（T4 消费），单一来源。

    version_tag 控制前端显隐与「v1 规则原型」占位标注（诚信红线）。
    """

    version_tag: str = Field(default="v1 规则原型", description="版本标签：v1 规则原型 | 真版")
    consensus_score: float = Field(default=0.0, ge=0.0, le=1.0, description="共识总评 0-1")
    evidence: list[Evidence] = Field(default_factory=list, description="支撑证据列表")
    conclusion: str = Field(default="", description="汇聚结论")
    created_at: datetime = Field(default_factory=_utcnow)

    def to_payload(self) -> dict:
        """序列化为前端证据卡 payload。"""
        return self.model_dump(mode="json")


__all__ = [
    "Evidence",
    "EvidenceChain",
    "ArgumentChain",
    "ChainNode",
    "ChainEdge",
    "EvidenceCard",
    "AlgorithmVersion",
    "EvidenceSourceType",
    "ChainNodeKind",
    "ChainEdgeRelation",
]
