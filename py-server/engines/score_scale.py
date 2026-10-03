# ============================================================
# score_scale — 「分数 / 可信度」量纲的单一真源（single source of truth）
#
# 为什么需要这个文件（2026-10-02 复盘，三类真实事故）：
#   ① 混音器把神经网络**原生 1-10** 输出又 ×10 → 越过上限被 clamp ⇒ 共识分恒为 10.0，
#      区分度归零（`src/components/GOMARLPanel.vue` 面板上「共识质量分数」永远显示 10.00）。
#   ② 质量门把 1-10 的 `consensus.overall_score` 当 0-100 用 ⇒ 三元评审里 consensus
#      通道的量级只有 1/10，学到的权重在生产上几乎不产生增益。
#      同类历史事故：一致性分由 0-100 改 0-1 时阈值 60/75 未同步 ⇒ 精准率恒为 0
#      （见 tests/test_review_single_source.py 的「量纲哨兵」）。
#   ③ 证据链 payload 的 0-1 契约与上游 1-10 之间没有显式转换点 ⇒ T3 汇聚落地即
#      Pydantic 校验失败（`le=1.0`）。
#
# 三层量纲 + **唯一跨界转换点**（纪律：跨层赋值必须显式调用本模块的换算函数，
# 禁止裸赋值；本模块是唯一的换算入口）：
#
#   ┌ 引擎层（模型原生量纲）              1-10
#   │   · QualityScore.accuracy/completeness/adaptability/overall
#   │     （LLM 按「1-10分」打分，见 gomarl._score_single 的 prompt）
#   │   · NeuralGroupMixer.mix()["consensus_score"]
#   │     （训练标签 = 各 Agent 分数的加权平均，天然 1-10：train_mixer_real_v2.py:96）
#   │   · ConsensusResult.overall_score
#   │   · 配置 gomarl.quality_threshold = 7（比较对象是 QualityScore.overall，勿改成 0.7）
#   │
#   ├ 门禁 / RL 信号层                   0-100
#   │   · evidence_report.consistency_score = overall_consistency × 100
#   │     （见 agents/evidence_check.py:_build_report）
#   │   · consensus.overall_score = 引擎层共识分 × 10
#   │     （见 agents/generator_cluster.py：state["consensus"] 是唯一跨界写入点）
#   │   · consensus.confidence_score × 100（0-1 → 0-100，见 quality_gate.review_signals）
#   │   · 阈值 CONSISTENCY_PASS=60 / CONSISTENCY_FIXABLE=40 / GROUNDING_PASS=40
#   │   · _STATUS_SIGNAL 90/50/45/40；RL 环境虚构 overall_score ∈ [40,95]
#   │
#   └ 证据链 payload 层                  0-1
#       · EvidenceChain.consensus_score / EvidenceCard.consensus_score / ChainNode.credibility
#       · 前端只认这一层（架构 §7.1），T3 写入时须经 ten_point_to_unit 换算
# ============================================================

from __future__ import annotations

import math

# ── 三层量纲的边界常量 ──
TEN_POINT_MIN = 1.0
TEN_POINT_MAX = 10.0
UNIT_MIN = 0.0
UNIT_MAX = 1.0
GATE_SIGNAL_MIN = 0.0
GATE_SIGNAL_MAX = 100.0

# 空输入哨兵：mix() 无 Agent 可混合时返回它。它**不属于任何一层量纲**，
# 只是"无数据"标记，消费方须自行判空（勿当成 1-10 里的最低分）。
EMPTY_SCORE = 0.0


def _finite(value, default: float) -> float:
    """数值化 + 非有限值（None/NaN/Inf/非数字）兜底为 default。"""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(x) or math.isinf(x):
        return default
    return x


def clamp_ten_point(score, default: float = TEN_POINT_MIN) -> float:
    """钳制到引擎层量纲 [1, 10]。非有限值回落 default。"""
    return min(TEN_POINT_MAX, max(TEN_POINT_MIN, _finite(score, default)))


def clamp_unit(score, default: float = UNIT_MIN) -> float:
    """钳制到证据链 payload 量纲 [0, 1]。"""
    return min(UNIT_MAX, max(UNIT_MIN, _finite(score, default)))


def clamp_gate_signal(score, default: float = GATE_SIGNAL_MIN) -> float:
    """钳制到门禁/RL 信号量纲 [0, 100]。"""
    return min(GATE_SIGNAL_MAX, max(GATE_SIGNAL_MIN, _finite(score, default)))


def ten_point_to_hundred(score) -> float:
    """引擎层 1-10 → 门禁/RL 信号层 0-100（×10）。

    唯一跨界点：`agents/generator_cluster.py` 写 state["consensus"]["overall_score"]。
    """
    return clamp_gate_signal(_finite(score, TEN_POINT_MIN) * 10.0)


def ten_point_to_unit(score) -> float:
    """引擎层 1-10 → 证据链 payload 0-1（÷10）。

    唯一跨界点：T3 汇聚（EvidenceConsensus）写 EvidenceChain/EvidenceCard.consensus_score。
    """
    return clamp_unit(_finite(score, TEN_POINT_MIN) / 10.0)


def unit_to_ten_point(score) -> float:
    """证据链 payload 0-1 → 引擎层 1-10（×10）。"""
    return clamp_ten_point(_finite(score, UNIT_MIN) * 10.0)


def hundred_to_ten_point(score) -> float:
    """门禁/RL 信号 0-100 → 引擎层 1-10（÷10）。"""
    return clamp_ten_point(_finite(score, GATE_SIGNAL_MIN) / 10.0)


__all__ = [
    "TEN_POINT_MIN",
    "TEN_POINT_MAX",
    "UNIT_MIN",
    "UNIT_MAX",
    "GATE_SIGNAL_MIN",
    "GATE_SIGNAL_MAX",
    "EMPTY_SCORE",
    "clamp_ten_point",
    "clamp_unit",
    "clamp_gate_signal",
    "ten_point_to_hundred",
    "ten_point_to_unit",
    "unit_to_ten_point",
    "hundred_to_ten_point",
]
