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

logger = logging.getLogger("netlearn.quality_gate")

# 阈值常量
CONSISTENCY_PASS = 60        # 一致性分数通过线
CONSISTENCY_FIXABLE = 40     # 一致性分数可修复下限
GROUNDING_PASS = 40          # 知识支撑度通过线
MAX_GATE_RETRIES = 1         # 最大闸门重试次数（提速：硬/软失败最多回退生成 1 次）

# ── 三元评审权重接线（攻坚令 3.4 插入点 B）──
# 灰度契约：均匀权重 (1/3,1/3,1/3) 时 effective == 原 consistency_score，行为零变化；
# 权重缺失/非法/异常 → 保持原值（fail-open）。只换判定输入，不换判定逻辑。
UNIFORM_REVIEW_W = {"honest": 1 / 3, "critic": 1 / 3, "consensus": 1 / 3}
_SKIP_EPS = 1e-9

# consensus.status → 共识信号兜底映射（overall_score 缺失时使用）
_STATUS_SIGNAL = {
    "passed": 90.0, "pass": 90.0, "conflict": 50.0,
    "flagged": 45.0, "regenerate": 40.0,
}


def review_signals(evidence: dict, consensus: dict) -> tuple[float, float, float]:
    """抽取三元评审信号，各归一到 0-100：返回 (honest, critic, consensus)。

    - honest    : evidence_report.consistency_score（证据/诚实 Agent）
    - critic    : consensus.confidence_score × 100（批评者置信度，critic 节点写入）
    - consensus : consensus.overall_score（GOMARL 共识总分），缺失时按 status 映射
    """
    evidence = evidence or {}
    consensus = consensus or {}
    try:
        s_h = float(evidence.get("consistency_score", 100) or 0)
    except (TypeError, ValueError):
        s_h = 100.0

    conf = consensus.get("confidence_score")
    try:
        s_c = float(conf) * 100.0 if conf is not None else 60.0
    except (TypeError, ValueError):
        s_c = 60.0

    overall = consensus.get("overall_score")
    if overall is not None:
        try:
            s_k = float(overall)
        except (TypeError, ValueError):
            s_k = None
    else:
        s_k = None
    if s_k is None:
        s_k = _STATUS_SIGNAL.get(
            str(consensus.get("status", "")).lower(), 60.0)

    return (
        max(0.0, min(100.0, s_h)),
        max(0.0, min(100.0, s_c)),
        max(0.0, min(100.0, s_k)),
    )


def _normalize_review_weights(w) -> dict | None:
    """归一化三元权重（非法 → None，交由调用方保持原值）。"""
    if not isinstance(w, dict):
        return None
    try:
        h = max(0.0, float(w.get("honest", 0.0)))
        c = max(0.0, float(w.get("critic", 0.0)))
        k = max(0.0, float(w.get("consensus", 0.0)))
    except (TypeError, ValueError, AttributeError):
        return None
    total = h + c + k
    if total <= _SKIP_EPS:
        return {"honest": 0.0, "critic": 0.0, "consensus": 0.0}
    return {"honest": h / total, "critic": c / total, "consensus": k / total}


def weighted_consistency_score(
    evidence: dict, consensus: dict, weights=None,
) -> tuple[float, bool]:
    """按三元评审权重合成有效一致性分。返回 (effective, applied)。

    合成公式（保证均匀权重零偏移）：
        weighted = w_h·S_h + w_c·S_c + w_k·S_k
        uniform  = (S_h + S_c + S_k) / 3
        effective = S_h + (weighted − uniform)

    - 均匀权重：weighted == uniform ⇒ effective == S_h，applied=False（行为=现状）
    - skip（权重全 0）：直接放行语义，effective=100，applied=True
    - 其余：按信任对象拉高/拉低有效分，applied=True
    """
    s_h, s_c, s_k = review_signals(evidence, consensus)
    # 空权重（None/{}/[]）一律视为「无权重」；空 dict 不得被当作 skip 全 0 放行，
    # 否则会把「未加权」静默变成「直接放行」，是危险的语义混淆。
    if not weights:
        return s_h, False
    w = _normalize_review_weights(weights)
    if w is None:
        return s_h, False

    h, c, k = w["honest"], w["critic"], w["consensus"]
    if h + c + k <= _SKIP_EPS:
        return 100.0, True  # skip_review：不评审直接放行
    if (abs(h - 1 / 3) < 1e-9 and abs(c - 1 / 3) < 1e-9 and abs(k - 1 / 3) < 1e-9):
        return s_h, False   # 均匀权重 = 现状，不施加任何偏移

    weighted = h * s_h + c * s_c + k * s_k
    uniform = (s_h + s_c + s_k) / 3.0
    effective = s_h + (weighted - uniform)
    return max(0.0, min(100.0, effective)), True


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

        # L1/L2/L3 三层学情记忆（低侵入：记忆薄弱点缺失的产物软告警）
        memory_context = state.get("memory_context") or ""
        memory_weak_missing = False
        if memory_context and memory_context != "【学生记忆】暂无历史学习数据":
            import re as _re
            weak_block = _re.search(r"薄弱[：:]\s*(.+?)(?:\n|$)", memory_context)
            if weak_block:
                weak_terms = [w.strip() for w in weak_block.group(1).split(",") if w.strip()]
                # 记忆薄弱点在产物中完全未出现 → 软告警（针对性讲解缺失）
                if weak_terms and teacher_doc and not any(
                    t.lower() in teacher_doc.lower() for t in weak_terms
                ):
                    memory_weak_missing = True

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