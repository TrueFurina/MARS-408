"""三元评审权重接线协议测试（A·阶段 1）

攻坚令验收要求：接线完成后「全链路行为不变」。
本文件锁死三条契约：
  1. 均匀权重 / 无权重 / 非法权重 → effective == 原 consistency_score（零偏移）
  2. 非均匀权重 → 按信任对象拉高/拉低，方向符合语义
  3. 灰度默认关闭（config.gomarl.use_review_mappo 缺失 → False）

任何一条被破坏，说明接线侵入了现有闸门行为，属于回归。
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.quality_gate import (  # noqa: E402
    UNIFORM_REVIEW_W,
    _normalize_review_weights,
    quality_gate_node,
    review_signals,
    weighted_consistency_score,
)

# ── 夹具 ────────────────────────────────────────────────────────────────────
# 三元信号刻意拉开差距，便于断言加权方向：
#   honest=70（evidence）、critic=50（confidence 0.5）、consensus=60（overall_score）
EVIDENCE = {"consistency_score": 70, "conflicts": [], "grounding_score": 80, "resolved": 0}
CONSENSUS = {"status": "passed", "confidence_score": 0.5, "overall_score": 60}


# ── 1. 信号抽取 ─────────────────────────────────────────────────────────────
def test_review_signals_extracts_three_channels():
    """三元信号正确抽取并归一到 0-100。"""
    h, c, k = review_signals(EVIDENCE, CONSENSUS)
    assert (h, c, k) == (70.0, 50.0, 60.0)


def test_review_signals_falls_back_on_missing():
    """字段缺失时取中性默认值，不抛异常。"""
    h, c, k = review_signals({}, {})
    assert h == 100.0      # 与 quality_gate 原默认值一致
    assert c == 60.0
    assert k == 60.0       # status 缺失 → 中性


def test_review_signals_clamps_to_range():
    """异常数值被 clamp 到 0-100。"""
    h, c, k = review_signals(
        {"consistency_score": 500}, {"confidence_score": 5.0, "overall_score": -20}
    )
    assert 0.0 <= h <= 100.0 and 0.0 <= c <= 100.0 and 0.0 <= k <= 100.0


# ── 2. 均匀权重零偏移（行为不变的核心契约）──────────────────────────────────
def test_uniform_weights_yield_zero_shift():
    """均匀权重 → effective == 原值且 applied=False（等价于未接线）。"""
    eff, applied = weighted_consistency_score(EVIDENCE, CONSENSUS, UNIFORM_REVIEW_W)
    assert eff == pytest.approx(70.0)
    assert applied is False


def test_no_weights_yields_zero_shift():
    """权重缺失/None → 原值，applied=False。"""
    for w in (None, {}, []):
        eff, applied = weighted_consistency_score(EVIDENCE, CONSENSUS, w)
        assert eff == pytest.approx(70.0)
        assert applied is False


def test_malformed_weights_fail_open():
    """非法权重（非 dict / 非数值 / 负值）→ 原值或安全归一化，不抛异常。"""
    for w in ("not-a-dict", {"honest": "x"}, {"honest": None, "critic": 1, "consensus": 1}):
        eff, _applied = weighted_consistency_score(EVIDENCE, CONSENSUS, w)
        assert 0.0 <= eff <= 100.0
    # 负值被裁剪为 0 → 等价于 skip 语义
    eff, applied = weighted_consistency_score(
        EVIDENCE, CONSENSUS, {"honest": -1, "critic": -1, "consensus": -1})
    assert (eff, applied) == (100.0, True)


def test_normalize_weights_rejects_garbage():
    assert _normalize_review_weights("x") is None
    assert _normalize_review_weights({"honest": "a"}) is None
    w = _normalize_review_weights({"honest": 2, "critic": 1, "consensus": 1})
    assert w["honest"] == pytest.approx(0.5)


# ── 3. 非均匀权重方向语义 ───────────────────────────────────────────────────
def test_trust_honest_raises_when_evidence_strongest():
    """证据信号最强（70 > 60 > 50）时信诚实 → 有效分上升。"""
    eff, applied = weighted_consistency_score(
        EVIDENCE, CONSENSUS, {"honest": 0.6, "critic": 0.2, "consensus": 0.2})
    assert applied is True
    assert eff > 70.0


def test_trust_consensus_lowers_when_consensus_signal_below_mean():
    """被信任信号低于三元均值时有效分下降：偏移 = 加权值 − 三元均值。"""
    # S = (70, 50, 30)，均值 50；信共识(30) → 加权值 42 < 均值 → 有效分 62
    ev = {"consistency_score": 70}
    con = {"confidence_score": 0.5, "overall_score": 30}
    eff, applied = weighted_consistency_score(
        ev, con, {"honest": 0.2, "critic": 0.2, "consensus": 0.6})
    assert applied is True
    assert eff == pytest.approx(70 + (0.2 * 70 + 0.2 * 50 + 0.6 * 30) - 50)
    assert eff < 70


def test_shift_is_zero_when_trusted_signal_equals_mean():
    """被信任信号恰等于三元均值时偏移为 0（公式必然性质，锁死防误判为 bug）。"""
    # S = (70, 50, 60)，均值 60；信共识(60) → 偏移 0
    eff, applied = weighted_consistency_score(
        EVIDENCE, CONSENSUS, {"honest": 0.2, "critic": 0.2, "consensus": 0.6})
    assert applied is True
    assert eff == pytest.approx(70.0)


def test_trust_critic_follows_critic_signal():
    """批评者信号最低（50）时信批评者 → 有效分被拉低。"""
    eff, _ = weighted_consistency_score(
        EVIDENCE, CONSENSUS, {"honest": 0.2, "critic": 0.6, "consensus": 0.2})
    assert eff < 70.0


def test_skip_weights_mean_direct_pass():
    """skip（权重全 0）→ 直接放行语义，effective=100。"""
    eff, applied = weighted_consistency_score(
        EVIDENCE, CONSENSUS, {"honest": 0.0, "critic": 0.0, "consensus": 0.0})
    assert (eff, applied) == (100.0, True)


def test_effective_score_always_clamped():
    """极端权重下 effective 仍在 0-100。"""
    for w in ({"honest": 1.0, "critic": 0.0, "consensus": 0.0},
              {"honest": 0.0, "critic": 0.0, "consensus": 1.0}):
        eff, _ = weighted_consistency_score(EVIDENCE, CONSENSUS, w)
        assert 0.0 <= eff <= 100.0


# ── 4. 端到端：闸门行为不变 / 注入生效 ──────────────────────────────────────
def _base_state(**overrides):
    st = {
        "evidence_report": dict(EVIDENCE),
        "consensus": dict(CONSENSUS),
        "teacher_doc": "讲解内容",
        "quiz": "练习题",
        "gate_retry_count": 0,
        "memory_context": "",
    }
    st.update(overrides)
    return st


def test_gate_behaviour_unchanged_without_review_weights():
    """无 review_weights 且灰度关闭 → 闸门判定与有效分完全等同现状。"""
    st = asyncio.run(quality_gate_node(_base_state()))
    assert st["gate_result"]["consistency_score"] == 70
    assert st["gate_result"]["review_weights_applied"] is False
    # 原始值同步落盘，便于追溯
    assert st["gate_result"]["consistency_score_raw"] == 70


def test_gate_applies_injected_review_weights():
    """上游显式注入非均匀权重 → 闸门按加权后的有效分判定。"""
    st = asyncio.run(quality_gate_node(_base_state(
        review_weights={"honest": 0.6, "critic": 0.2, "consensus": 0.2})))
    assert st["gate_result"]["review_weights_applied"] is True
    assert st["gate_result"]["consistency_score"] > 70
    assert st["gate_result"]["consistency_score_raw"] == 70


def test_gate_uniform_weights_keep_original_verdict():
    """注入均匀权重 → 判定结果与不注入时一致（零侵入证明）。"""
    plain = asyncio.run(quality_gate_node(_base_state()))
    uniform = asyncio.run(quality_gate_node(_base_state(
        review_weights=dict(UNIFORM_REVIEW_W))))
    assert plain["gate_verdict"] == uniform["gate_verdict"]
    assert plain["gate_result"]["consistency_score"] == \
        uniform["gate_result"]["consistency_score"]


def test_gate_survives_garbage_state():
    """脏状态（None 字段）不抛异常，fail-open 通过。"""
    st = asyncio.run(quality_gate_node({
        "evidence_report": None, "consensus": None,
        "teacher_doc": "", "quiz": "",
    }))
    assert st["gate_verdict"] in ("pass", "fix", "reject")


# ── 5. 灰度默认关闭 ─────────────────────────────────────────────────────────
def test_review_mappo_disabled_by_default():
    """config 未配置 use_review_mappo → 灰度关闭（生产安全）。"""
    import config

    assert config.use_review_mappo() is False
    assert config.review_min_review() == 2
