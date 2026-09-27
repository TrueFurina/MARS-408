# ============================================================
# 产物验收闸门 (Quality Gate) — 硬性阻断不合格内容
#
# 位于 evidence_check 之后、path_planner 之前。
# 三个输出: PASS → path_planner / FIX → generator_cluster / REJECT → END
#
# 硬性指标（任一不满足 → REJECT/FIX）：
#   一致性分数 ≥ 60  |  无高危冲突  |  知识支撑度通过
#   Critic 审阅 passed  |  teacher_doc + quiz 非空
#
# 软性指标（可修复范围 → FIX）：
#   一致性分数 40-60  |  有可消解冲突  |  知识支撑度偏低
#
# 决策逻辑：
#   硬失败 + retry < 2 → FIX  |  硬失败 + retry ≥ 2 → REJECT
#   仅软失败 + retry < 2 → FIX  |  仅软失败 + retry ≥ 2 → PASS（降级）
#   全部通过 → PASS  |  任何异常 → PASS（fail-open）
# ============================================================

import logging
from typing import Literal

from agents.state import AgentState

# M-3：三元评审信号 / 有效分合成的**实现**已下沉 engines/review_policy.py。
# 原位置（本模块）会与 engines.review_policy 形成双向循环 —— 后者的
# analytic_review_action 必须与打分同源（test_review_analytic 以恒等式守护），
# 只能靠函数内延迟导入规避。下沉后方向单一：agents.quality_gate → engines.review_policy。
# 下方名字是**委托再导出**，使既有实验/测试脚本 `from agents.quality_gate import ...` 不受影响。
# review_signals 被多个实验脚本从本模块导入（不再被本模块自身引用）→ 标注 noqa: F401 以免 pyflakes 误报。
from engines.review_policy import (
    UNIFORM_REVIEW_W,  # noqa: F401  - 委托再导出（test_review_weight_protocol 从本模块导入）
    _normalize_review_weights,  # noqa: F401  - 委托再导出（同上；权重归一化真值源在 engines）
    review_signals,  # noqa: F401  - 委托再导出（diag_* 实验脚本从本模块导入）
    weighted_consistency_score,
)

logger = logging.getLogger("netlearn.quality_gate")

# 阈值常量
CONSISTENCY_PASS = 60        # 一致性分数通过线
CONSISTENCY_FIXABLE = 40     # 一致性分数可修复下限
GROUNDING_PASS = 40          # 知识支撑度通过线
MAX_GATE_RETRIES = 1         # 最大闸门重试次数（提速：硬/软失败最多回退生成 1 次）

# ── 三元评审权重接线（攻坚令 3.4 插入点 B）──
# 灰度契约：均匀权重 (1/3,1/3,1/3) 时 effective == 原 consistency_score，行为零变化；
# 权重缺失/非法/异常 → 保持原值（fail-open）。只换判定输入，不换判定逻辑。
# （review_signals / weighted_consistency_score 见顶部委托导入）


def _resolve_review_weights(state: dict, evidence: dict, consensus: dict):
    """解析本轮三元评审权重；无可用来源 → None（调用方保持原值）。

    优先级：state["review_weights"]（上游显式注入）> MAPPO 在线决策（灰度开启时）
    > None（灰度关闭 = 现状）。
    """
    w = state.get("review_weights")
    if isinstance(w, dict) and w:
        return w
    try:
        from engines.review_policy import (
            _mappo_enabled, decide_review_weight, review_state_features,
        )
    except Exception:  # noqa: BLE001 - review_policy 缺失即视为未接线
        return None
    try:
        if not _mappo_enabled():
            return None
        feats = review_state_features(
            evidence=evidence, consensus=consensus, state=state)
        # 传 evidence/consensus：解析最优档位（review_policy.analytic_review_action）
        # 需要与打分同源的 (s_h, s_c, s_k) —— 这两者不在 12 维状态里。
        decision = decide_review_weight(
            feats, use_mappo=True, evidence=evidence, consensus=consensus)
        return decision.get("weights")
    except Exception as e:  # noqa: BLE001
        logger.warning("三元评审权重在线决策失败，回退均匀权重: %s", e)
        return None


async def quality_gate_node(state: AgentState) -> AgentState:
    """产物验收闸门节点：基于 evidence_report 和 consensus 做硬性质量判定。

    Fail-open 设计：任何异常均降级为 PASS，不阻断流水线。
    """
    state["status"] = "gate_checking"
    state["current_agent"] = "quality_gate"

    try:
        evidence = state.get("evidence_report") or {}
        consensus = state.get("consensus") or {}
        gate_retry = state.get("gate_retry_count", 0)
        teacher_doc = (state.get("teacher_doc") or "").strip()
        quiz = (state.get("quiz") or "").strip()

        hard_failures: list[str] = []
        soft_failures: list[str] = []

        # ── 硬性指标检查 ──

        consistency_score = evidence.get("consistency_score", 100)

        # ── 插入点 B：三元评审权重加权（攻坚令 3.4）──
        # 灰度默认关闭 → 均匀权重 → effective == 原值，行为零变化；
        # 异常/无来源 → 原值（fail-open）。只换判定输入，不换判定逻辑。
        _raw_consistency = consistency_score
        _weights_applied = False
        try:
            _w = _resolve_review_weights(state, evidence, consensus)
            if _w:
                consistency_score, _weights_applied = weighted_consistency_score(
                    evidence, consensus, _w)
                if _weights_applied:
                    state["review_weights"] = _w
                    state.setdefault("review_weight_source", "state")
        except Exception as _we:  # noqa: BLE001
            logger.warning("三元评审权重加权失败，回退原始一致性分: %s", _we)
            consistency_score = _raw_consistency
            _weights_applied = False

        if consistency_score < CONSISTENCY_PASS:
            if consistency_score < CONSISTENCY_FIXABLE:
                hard_failures.append(
                    f"一致性分数过低: {consistency_score}/100 (阈值: {CONSISTENCY_PASS})"
                )
            else:
                soft_failures.append(
                    f"一致性分数偏低: {consistency_score}/100 (可修复范围 {CONSISTENCY_FIXABLE}-{CONSISTENCY_PASS})"
                )

        conflicts = evidence.get("conflicts") or []
        high_conflicts = [c for c in conflicts if c.get("severity") == "high"]
        if len(high_conflicts) > 0:
            hard_failures.append(f"存在 {len(high_conflicts)} 个高危冲突")

        if evidence.get("grounding_flagged") is True:
            hard_failures.append("知识支撑度不足，疑似幻觉")

        critic_status = consensus.get("status", "unknown")  # 默认 "unknown" 防漏检：Critic 未执行时不被误判通过
        if critic_status != "passed":
            hard_failures.append(f"Critic 审阅未通过: status={critic_status}")

        if not teacher_doc:
            hard_failures.append("核心资源缺失: teacher_doc 为空")
        if not quiz:
            hard_failures.append("核心资源缺失: quiz 为空")

        # ── 软性指标检查（仅当硬性指标通过时才有关注意义）──

        resolved = evidence.get("resolved", 0)
        if resolved > 0 and len(hard_failures) == 0:
            soft_failures.append(f"有 {resolved} 个可消解冲突")

        grounding_score = evidence.get("grounding_score")
        if grounding_score is not None and grounding_score < GROUNDING_PASS and len(hard_failures) == 0:
            soft_failures.append(f"知识支撑度偏低: {grounding_score}")

        # ── 决策 ──

        if len(hard_failures) > 0:
            if gate_retry < MAX_GATE_RETRIES:
                verdict = "fix"
                reasons = hard_failures + soft_failures
                reasons.append(f"闸门重试 {gate_retry + 1}/{MAX_GATE_RETRIES}")
            else:
                verdict = "reject"
                reasons = hard_failures + [f"已达最大重试次数 ({MAX_GATE_RETRIES})"]
        elif len(soft_failures) > 0:
            if gate_retry < MAX_GATE_RETRIES:
                verdict = "fix"
                reasons = soft_failures + [f"闸门重试 {gate_retry + 1}/{MAX_GATE_RETRIES}"]
            else:
                verdict = "pass"
                reasons = soft_failures + [f"已达最大重试次数 ({MAX_GATE_RETRIES})，降级通过"]
        else:
            verdict = "pass"
            reasons = ["所有硬性指标和软性指标均通过"]

        # ── 写入状态 ──

        state["gate_result"] = {
            "verdict": verdict,
            "reasons": reasons,
            "hard_failures": hard_failures,
            "soft_failures": soft_failures,
            "consistency_score": consistency_score,
            "consistency_score_raw": _raw_consistency,
            "review_weights_applied": _weights_applied,
            "gate_retry_count": gate_retry,
        }
        state["gate_verdict"] = verdict
        state["gate_reasons"] = reasons
        state["gate_passed"] = (verdict == "pass")

        if verdict == "fix":
            state["gate_retry_count"] = gate_retry + 1

        logger.info(
            f"闸门判定: verdict={verdict}, hard_failures={len(hard_failures)}, "
            f"soft_failures={len(soft_failures)}, retry={gate_retry}"
        )

    except Exception as e:
        # Fail-open：不阻断流水线
        logger.error(f"闸门异常，降级通过: {e}")
        state["gate_passed"] = True
        state["gate_verdict"] = "pass"
        state["gate_reasons"] = [f"闸门异常降级通过: {str(e)}"]
        state["gate_result"] = {
            "verdict": "pass",
            "reasons": state["gate_reasons"],
            "hard_failures": [],
            "soft_failures": [],
            "consistency_score": None,
            "consistency_score_raw": None,
            "review_weights_applied": False,
            "gate_retry_count": state.get("gate_retry_count", 0),
            "error": str(e),
        }

    return state


def route_after_quality_gate(
    state: AgentState,
) -> Literal["path_planner", "generator_cluster", "__end__"]:
    """闸门后路由：PASS → path_planner / FIX → generator_cluster / REJECT → END"""
    verdict = state.get("gate_verdict", "pass")
    if verdict == "pass":
        return "path_planner"
    elif verdict == "fix":
        return "generator_cluster"
    else:
        return "__end__"