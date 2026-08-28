# 核心引擎
from .frugal_rag import frugal_rag, FrugalRAG, format_retrieval_for_llm
from .gomarl import GOMARLConsensus, AgentResult, ConsensusResult, QualityScore

# FrugalRAG 真版增量模块
from .frugal_rag_sft import (
    QueryPreprocessor, LLMQueryOptimizer, ReActRetriever,
    query_preprocessor, sft_query_generator, react_retriever,
)
from .frugal_rag_stop import (
    HeuristicStopDecision, QueryRewriter, LoRAAdapter, FrugalRAGFull,
    stop_decision, query_rewriter, lora_adapter, frugal_rag_full,
)

# GoMARL 真版增量模块
from .gomarl_mixer import (
    NeuralGroupMixer, AgentOutputEncoder,
    neural_mixer, agent_encoder,
)
from .gomarl_conflict import (
    ConsistencyChecker, EvidenceConflictResolver, ConflictResolutionEngine,
    consistency_checker, conflict_resolver, conflict_engine,
)

# 教学业务规则引擎
from .teaching_rules import (
    TeachingRuleEngine, TopicDependency, ScheduleValidation, AgentTopicAffinity,
    teaching_rules,
)

__all__ = [
    # 基础引擎
    "frugal_rag", "FrugalRAG", "format_retrieval_for_llm",
    "GOMARLConsensus", "AgentResult", "ConsensusResult", "QualityScore",
    # FrugalRAG 真版
    "QueryPreprocessor", "LLMQueryOptimizer", "ReActRetriever",
    "query_preprocessor", "sft_query_generator", "react_retriever",
    "HeuristicStopDecision", "QueryRewriter", "LoRAAdapter", "FrugalRAGFull",
    "stop_decision", "query_rewriter", "lora_adapter", "frugal_rag_full",
    # GoMARL 真版
    "NeuralGroupMixer", "AgentOutputEncoder",
    "neural_mixer", "agent_encoder",
    "ConsistencyChecker", "EvidenceConflictResolver", "ConflictResolutionEngine",
    "consistency_checker", "conflict_resolver", "conflict_engine",
    # 教学规则引擎
    "TeachingRuleEngine", "TopicDependency", "ScheduleValidation", "AgentTopicAffinity",
    "teaching_rules",
]
