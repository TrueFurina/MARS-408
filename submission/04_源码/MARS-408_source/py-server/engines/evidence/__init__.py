# Evidence 数据结构包 — T1 基础层单一来源（schema 单一来源）
# 规则版（lite）与真版（real）共识后端都必须产出本包定义的 Evidence，
# 前端只认这一份 → 杜绝双份结构（架构 §7.1）。
from .schema import (
    ArgumentChain,
    ChainEdge,
    ChainNode,
    Evidence,
    EvidenceCard,
    EvidenceChain,
)

__all__ = [
    "Evidence",
    "EvidenceChain",
    "ArgumentChain",
    "ChainNode",
    "ChainEdge",
    "EvidenceCard",
]
