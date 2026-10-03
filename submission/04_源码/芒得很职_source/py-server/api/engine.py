# ============================================================
# API — FrugalRAG + GoMARL 引擎接口
#
# 暴露真版增量功能：
#   /api/engine/frugal-rag-full     — 完整 FrugalRAG 检索（SFT+停止决策+重写）
#   /api/engine/gomarl-consensus    — GoMARL 共识评估（NeuralMixer+冲突消解）
#   /api/engine/stop-decision       — GRPO 停止决策状态
#   /api/engine/neural-mixer        — NeuralMixer 统计
#   /api/engine/conflict-check      — 冲突检测+消解
#   /api/engine/lora-config         — LoRA 少样本适配配置
#
# 异常处理: 统一由 main.py 全局处理器接管 (DomainError → 4xx/5xx, Exception → 500)
# ============================================================

from fastapi import APIRouter, Request, Depends
from shared.auth import get_current_user
from shared.ratelimit import require_llm_quota
from pydantic import BaseModel, field_validator
from typing import Optional

# F-011：引擎端点统一鉴权 + 每用户 LLM 配额（429，部分端点调用 LLM）
router = APIRouter(prefix="/engine", tags=["engine"], dependencies=[Depends(require_llm_quota)])


# ── 请求模型 ──

class FrugalRAGFullRequest(BaseModel):
    question: str
    course: str = "computer_network"
    top_k: int = 5
    student_profile: dict = {}  # 报告§3.4.2 个性化排序


class GOMARLConsensusRequest(BaseModel):
    agent_results: list[dict]  # [{agent_name, content, score}]
    student_profile: dict = {}
    topic: str = ""
    course: str = "computer_network"


class ConflictCheckRequest(BaseModel):
    agent_results: list[dict]  # [{agent_name, content}]
    course: str = "computer_network"


class StopDecisionUpdateRequest(BaseModel):
    complexity: str  # simple | medium | complex
    final_coverage: float
    was_good: bool

    @field_validator("final_coverage")
    @classmethod
    def _clamp_coverage(cls, v: float) -> float:
        if v != v:  # NaN check
            raise ValueError("final_coverage must not be NaN")
        return max(0.0, min(1.0, v))


class TeachingRulesValidateRequest(BaseModel):
    topic_ids: list[str] = []
    student_profile: dict = {}


class TeachingRulesAgentAssignRequest(BaseModel):
    topic_id: str
    resource_type: str = ""


class TeachingRulesPrioritizeRequest(BaseModel):
    topic_ids: list[str]
    student_profile: dict


# ── 端点 ──

@router.post("/frugal-rag-full")
async def frugal_rag_full(req: FrugalRAGFullRequest, user: dict = Depends(get_current_user)):
    """完整 FrugalRAG 检索流程

    SFT 查询生成 → 向量检索 → RL 停止决策 → 查询重写 → 答案生成

    返回完整检索轨迹，用于前端可视化
    """
    from engines.frugal_rag_stop import frugal_rag_full

    # L1/L2/L3 三层学情记忆注入（低侵入：薄弱点并入检索，个性化）
    student_profile = req.student_profile or {}
    try:
        user_id = user.get("user_id") or user.get("id") or ""
        if user_id:
            from services.memory_service import build_memory_context
            memory_ctx = build_memory_context(user_id, session_id=None, max_episodes=4)
            if memory_ctx and memory_ctx != "【学生记忆】暂无历史学习数据":
                student_profile = {**student_profile, "_memory_context": memory_ctx}
    except Exception as _me:
        logger.debug(f"FrugalRAG 记忆注入失败(降级): {_me}")

    result = await frugal_rag_full.retrieve_full(
        req.question, req.course, req.top_k,
        student_profile=student_profile,
    )
    return {
        "status": "ok",
        "answer": result["answer"],
        "trajectory": result["trajectory"],
        "total_searches": result["total_searches"],
        "rewrites": result["rewrites"],
        "coverage": result["coverage"],
        "complexity": result["complexity"],
        "cleaned_question": result["cleaned_question"],
        "chunks_count": len(result["all_chunks"]),
        "personalized_rerank": result.get("personalized_rerank", {}),
    }


@router.post("/gomarl-consensus")
async def gomarl_consensus(req: GOMARLConsensusRequest, user: dict = Depends(get_current_user)):
    """GoMARL 共识评估（NeuralMixer + 证据冲突消解）

    输入多个 Agent 的生成结果，输出：
    - NeuralMixer 共识分数
    - 动态权重快照
    - 冲突检测结果
    - 分组信息
    """
    from engines.gomarl_mixer import neural_mixer
    from engines.gomarl_conflict import conflict_engine

    # 1. NeuralMixer 共识混合
    mixer_result = await neural_mixer.mix(
        req.agent_results, req.student_profile, req.topic
    )

    # 2. 冲突检测+消解
    conflict_result = await conflict_engine.check_and_resolve(
        req.agent_results, course=req.course
    )

    return {
        "status": "ok",
        "consensus_score": mixer_result["consensus_score"],
        "neural_used": mixer_result["neural_used"],
        "dynamic_weights": mixer_result["dynamic_weights"],
        "weighted_scores": mixer_result["weighted_scores"],
        "groups": mixer_result["groups"],
        "sd_loss": mixer_result["sd_loss"],
        "conflicts": {
            "total": conflict_result["total_conflicts"],
            "resolved": conflict_result["resolved"],
            "unresolved": conflict_result["unresolved"],
            "overall_consistency": conflict_result["overall_consistency"],
            "details": conflict_result["conflicts"],
        },
    }


@router.get("/stop-decision")
async def stop_decision_stats(user: dict = Depends(get_current_user)):
    """获取启发式停止决策统计"""
    from engines.frugal_rag_stop import stop_decision
    return {"status": "ok", "stats": stop_decision.get_stats()}


@router.post("/stop-decision/update")
async def stop_decision_update(req: StopDecisionUpdateRequest, user: dict = Depends(get_current_user)):
    """更新启发式动态阈值（基于历史效果的 EWMA 自适应，非在线学习）"""
    from engines.frugal_rag_stop import stop_decision
    stop_decision.update_threshold(req.complexity, req.final_coverage, req.was_good)
    return {"status": "ok", "stats": stop_decision.get_stats()}


@router.get("/neural-mixer")
async def neural_mixer_stats(user: dict = Depends(get_current_user)):
    """获取 NeuralMixer 统计"""
    from engines.gomarl_mixer import neural_mixer
    return {"status": "ok", "stats": neural_mixer.get_stats()}


@router.post("/conflict-check")
async def conflict_check(req: ConflictCheckRequest, user: dict = Depends(get_current_user)):
    """独立冲突检测+消解"""
    from engines.gomarl_conflict import conflict_engine
    result = await conflict_engine.check_and_resolve(
        req.agent_results, course=req.course
    )
    return {"status": "ok", **result}


@router.get("/lora-config")
async def lora_config(user: dict = Depends(get_current_user)):
    """获取 LoRA 少样本适配配置"""
    from engines.frugal_rag_stop import lora_adapter
    return {"status": "ok", "config": lora_adapter.get_lora_config()}


@router.get("/status")
async def engine_status(user: dict = Depends(get_current_user)):
    """引擎整体状态"""
    from engines.frugal_rag_stop import stop_decision
    from engines.gomarl_mixer import neural_mixer
    from engines.teaching_rules import teaching_rules

    return {
        "status": "ok",
        "modules": {
            "frugal_rag_lite": True,
            "frugal_rag_sft": True,
            "frugal_rag_stop_decision": True,
            "frugal_rag_query_rewrite": True,
            "frugal_rag_lora": True,
            "frugal_rag_personalized_rerank": True,  # 报告§3.4.2
            "gomarl_lite": True,
            "gomarl_neural_mixer": neural_mixer.use_neural,
            "gomarl_evidence_conflict": True,
            "gomarl_teaching_rules": True,
        },
        "torch_available": neural_mixer.use_neural,
        "stop_decision_stats": stop_decision.get_stats(),
        "mixer_stats": neural_mixer.get_stats(),
        "teaching_rules_stats": teaching_rules.get_stats(),  # 新增
        # 循环11-P1：可观测性增强——熔断器/令牌桶实时状态（供前端可视化面板）
        "reliability": {
            "breakers": _breaker_stats(),
            "token_buckets": _bucket_stats(),
        },
    }


def _breaker_stats() -> dict:
    """熔断器状态快照（LLM 通道 + Skill 插件）"""
    from shared.circuit_breaker import all_breaker_stats
    return all_breaker_stats()


def _bucket_stats() -> dict:
    """令牌桶状态快照（LLM 通道限流）"""
    from shared.token_bucket import all_bucket_stats
    return all_bucket_stats()


# ── 教学规则引擎端点（报告§3.3.3） ──

@router.get("/teaching-rules")
async def teaching_rules_stats(user: dict = Depends(get_current_user)):
    """教学规则引擎统计 — 408知识点依赖+考查权重+Agent适配"""
    from engines.teaching_rules import teaching_rules
    return {"status": "ok", "stats": teaching_rules.get_stats()}


@router.post("/teaching-rules/validate")
async def teaching_rules_validate(req: TeachingRulesValidateRequest, user: dict = Depends(get_current_user)):
    """校验调度顺序是否符合408教学逻辑"""
    from engines.teaching_rules import teaching_rules
    result = teaching_rules.validate_schedule(req.topic_ids, req.student_profile)
    return {
        "status": "ok",
        "is_valid": result.is_valid,
        "violations": result.violations,
        "suggestions": result.suggestions,
        "adjusted_order": result.adjusted_order,
    }


@router.post("/teaching-rules/agent-assign")
async def teaching_rules_agent_assign(req: TeachingRulesAgentAssignRequest, user: dict = Depends(get_current_user)):
    """建议Agent分配方案"""
    from engines.teaching_rules import teaching_rules
    agents = teaching_rules.suggest_agent_assignment(req.topic_id, req.resource_type)
    return {"status": "ok", "topic_id": req.topic_id, "suggested_agents": agents}


@router.post("/teaching-rules/prioritize")
async def teaching_rules_prioritize(req: TeachingRulesPrioritizeRequest, user: dict = Depends(get_current_user)):
    """基于画像调整知识点优先级"""
    from engines.teaching_rules import teaching_rules
    prioritized = teaching_rules.prioritize_by_profile(req.topic_ids, req.student_profile)
    return {"status": "ok", "prioritized_topics": prioritized}


@router.get("/teaching-rules/prerequisites/{topic_id}")
async def teaching_rules_prerequisites(topic_id: str, user: dict = Depends(get_current_user)):
    """获取知识点前置依赖（含跨科目）"""
    from engines.teaching_rules import teaching_rules
    prereqs = teaching_rules.get_prerequisites(topic_id)
    cross = teaching_rules.get_cross_subject_prerequisites(topic_id)
    dep = teaching_rules._dependencies.get(topic_id)
    return {
        "status": "ok",
        "topic_id": topic_id,
        "topic_name": dep.topic_name if dep else "",
        "course": dep.course if dep else "",
        "exam_weight": dep.exam_weight if dep else 0,
        "difficulty": dep.difficulty if dep else "",
        "prerequisites": prereqs,
        "cross_subject_prerequisites": cross,
    }
