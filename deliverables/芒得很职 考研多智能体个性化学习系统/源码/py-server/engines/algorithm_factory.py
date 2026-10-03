# ============================================================
# 节点工厂（feature-flag 路由）— T1 基础层
#
# 按 config.algorithm.version / features.* 路由 real vs lite 检索与共识后端。
# - lite 分支：薄封装现有 engines 规则版实现（engines.frugal_rag / engines.gomarl），不重写；
# - real 分支：T1 仅留清晰标注的 stub（NotImplementedError），真算法在 T2/T3 落地。
#
# 设计要点：
# 1. 全部重依赖（frugal_rag / gomarl / torch）延迟到方法调用时才 import，
#    模块顶层零重依赖，保证 T1 离线单测快速、不触发 Windows SIGSEGV。
# 2. 支持按 session 灰度：resolve_version(state.get("algorithm_version")) 覆盖全局 flag，
#    非法 / 缺失值一律回退 lite（异常即回退，不崩主流程）。
# 3. 不改 10 节点图主流程，仅作为可插拔工厂被 retriever_node / evidence_consensus 节点调用。
# 4. LLM 通道不替换（P0 不接 Qwen2.5）——本模块不涉及任何 LLM 调用。
# ============================================================

from __future__ import annotations

from typing import Optional

import config

# 合法算法版本集合（resolve_version 据此校验 session 覆盖值）
VALID_VERSIONS = ("lite", "real")


# ── 规则版（lite）后端：薄封装 engines，不重写 ──


class LiteRetriever:
    """规则版检索：薄封装 engines.frugal_rag.FrugalRAG（BM25+向量混合，无 cross-encoder）。

    T1 仅做委托，零重写；T2 将新增 NeuralReranker 作为 real 分支实现。
    """

    backend_name = "lite"
    version_tag = "v1 规则原型"

    async def retrieve(
        self, query: str, course: Optional[str] = None, top_k: int = 5, **kwargs
    ) -> list[dict]:
        """委托现有规则版 FrugalRAG 检索（与 retriever_node 当前调用一致）。"""
        from engines.frugal_rag import frugal_rag

        return await frugal_rag.retrieve(query, course=course, top_k=top_k, **kwargs)


class LiteConsensus:
    """规则版共识：薄封装 engines.gomarl.GOMARLConsensus（use_neural_mixer 由 config 控制）。

    T1 仅做委托，零重写；T3 将新增 RealConsensus（NeuralMixer + 冲突消解）作为 real 分支。
    """

    backend_name = "lite"
    version_tag = "v1 规则原型"

    async def evaluate(
        self, results, student_profile, topic, round_num: int = 0, **kwargs
    ):
        """委托现有规则版 GOMARLConsensus 共识评估。"""
        from engines.gomarl import GOMARLConsensus

        backend = GOMARLConsensus()
        return await backend.evaluate(
            results, student_profile, topic, round_num=round_num, **kwargs
        )


class RuleRewardStub:
    """规则版奖励占位（T5 真版奖励模型落地前，保持 get_reward 接口可用）。

    返回中性占位分 0.0，不引入任何真版训练信号；仅为 T1 接口一致性预留。
    """

    backend_name = "lite"
    version_tag = "v1 规则原型"

    def score(self, context: dict) -> float:
        """规则版：返回中性占位分（不计算真实检索质量 / 生成可信度）。"""
        return 0.0


# ── 真版（real）stub：T1 不实现，清晰标注待 T2/T3/T5 ──


class RealRetrieverStub:
    """真版检索 stub — FrugalRAG 可学习重排将在 T2 实现。"""

    backend_name = "real"
    version_tag = "real(待 T2 实现)"
    is_stub = True

    def retrieve(self, *args, **kwargs):
        raise NotImplementedError(
            "真版检索（FrugalRAG 可学习重排）尚未实现，将在 T2 落地。"
            "当前请使用 version='lite'（规则版）。"
        )

    async def aretrieve(self, *args, **kwargs):
        raise NotImplementedError(
            "真版检索（FrugalRAG 可学习重排）尚未实现，将在 T2 落地。"
            "当前请使用 version='lite'（规则版）。"
        )


class RealConsensusStub:
    """真版共识 stub — NeuralMixer + 冲突消解 + EvidenceConsensus 将在 T3 实现。"""

    backend_name = "real"
    version_tag = "real(待 T3 实现)"
    is_stub = True

    def evaluate(self, *args, **kwargs):
        raise NotImplementedError(
            "真版共识（NeuralMixer + 冲突消解 + EvidenceConsensus）尚未实现，将在 T3 落地。"
            "当前请使用 version='lite'（规则版 GOMARLConsensus）。"
        )

    async def aevaluate(self, *args, **kwargs):
        raise NotImplementedError(
            "真版共识（NeuralMixer + 冲突消解 + EvidenceConsensus）尚未实现，将在 T3 落地。"
            "当前请使用 version='lite'（规则版 GOMARLConsensus）。"
        )


# ── 工厂 ──


class AlgorithmFactory:
    """按 feature flag / session 灰度选择检索与共识后端。

    用法：
        factory = AlgorithmFactory()                 # 读实时 config
        retriever = factory.get_retriever()           # 读 config.algorithm.version
        retriever = factory.get_retriever("lite")     # 显式 lite
        retriever = factory.get_retriever("real")     # 返回 RealRetrieverStub
        v = factory.resolve_version(state.get("algorithm_version"))  # session 灰度
    """

    VALID_VERSIONS = VALID_VERSIONS

    def __init__(self, cfg: Optional[dict] = None):
        # cfg 仅用于单测注入；为空时走 config.get_algorithm_config() 实时读取。
        self._cfg = cfg or {}

    def resolve_version(self, session_override: Optional[str] = None) -> str:
        """解析最终算法版本。

        Args:
            session_override: 来自 state["algorithm_version"] 的 per-session 灰度覆盖。
                仅当其为合法 "lite"/"real" 时生效；其余一律回退全局 flag → 默认 lite。

        Returns:
            "lite" | "real"
        """
        if session_override in VALID_VERSIONS:
            return session_override
        version = self._cfg.get("version") or config.algorithm_version()
        return "real" if version == "real" else "lite"

    def get_retriever(self, version: Optional[str] = None):
        """返回检索后端：lite→LiteRetriever（委托 FrugalRAG），real→RealRetrieverStub。"""
        version = self.resolve_version(version)
        if version == "real":
            return RealRetrieverStub()
        return LiteRetriever()

    def get_consensus(self, version: Optional[str] = None):
        """返回共识后端：lite→LiteConsensus（委托 GOMARLConsensus），real→RealConsensusStub。"""
        version = self.resolve_version(version)
        if version == "real":
            return RealConsensusStub()
        return LiteConsensus()

    def get_reward(self, kind: str = "generation", version: Optional[str] = None):
        """返回奖励模型：lite→RuleRewardStub（占位），real→NotImplementedError（待 T5）。

        kind: "retrieval" | "generation"（预留，T5 真版奖励模型按 kind 区分）。
        """
        version = self.resolve_version(version)
        if version == "real":
            raise NotImplementedError(
                f"真版奖励模型({kind})尚未实现，将在 T5 落地。"
            )
        return RuleRewardStub()


# ── 模块级便捷函数（匹配 T1 任务书接口）──

_factory = AlgorithmFactory()


def get_retriever(version: Optional[str] = None):
    """工厂函数：返回检索后端（默认读 config.algorithm.version）。"""
    return _factory.get_retriever(version)


def get_consensus(version: Optional[str] = None):
    """工厂函数：返回共识后端（默认读 config.algorithm.version）。"""
    return _factory.get_consensus(version)


def get_reward(kind: str = "generation", version: Optional[str] = None):
    """工厂函数：返回奖励模型（默认读 config.algorithm.version）。"""
    return _factory.get_reward(kind, version)


def resolve_version(session_override: Optional[str] = None) -> str:
    """工厂函数：解析最终算法版本（含 session 灰度覆盖）。"""
    return _factory.resolve_version(session_override)


__all__ = [
    "VALID_VERSIONS",
    "AlgorithmFactory",
    "LiteRetriever",
    "LiteConsensus",
    "RuleRewardStub",
    "RealRetrieverStub",
    "RealConsensusStub",
    "get_retriever",
    "get_consensus",
    "get_reward",
    "resolve_version",
]
