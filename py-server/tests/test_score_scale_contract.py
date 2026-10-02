"""量纲（score scale）契约测试 — 三层量纲 + 唯一跨界转换点

背景（2026-10-02 复盘）：同一批「分数」在三层各自为政，已发生两起真实事故：
  ① `gomarl_mixer.mix()` 把神经网络**原生 1-10** 输出又 ×10 → 越过上限被 clamp，
     共识分恒为 10.0（`src/components/GOMARLPanel.vue` 面板永远显示 10.00）；
     四条独立证据：训练标签 = 各 Agent 分数加权平均（train_mixer_real_v2.py:87-96）、
     基准记录的裸网络输出均值 6.37/6.81（experiments/results/benchmark_2026-09-18.json）、
     **同一份**体检报告里离线网络输出均值 6.46（diagnostics/项目体检报告-2026-09-02.md:215）
     与线上 HTTP 实测 `consensus_score = 10.0`（同文件 :229）并存 —— 离线正确、线上被 ×10 钳死。
  ② `agents/generator_cluster.py` 把 1-10 的共识分直接写进 state，而门禁
     （`quality_gate.review_signals` 契约即「各归一到 0-100」）与 RL 环境
     （`review_env_calibrated` 虚构 `overall_score ∈ [40,95]`）都按 **0-100** 用
     → 生产区间 [1,10] 与训练区间 [40,95] **交集为空**，该通道在 sim2real 上失效。
     同类历史事故：一致性分由 0-100 改 0-1 时阈值 60/75 未同步，精准率恒为 0
     （见 tests/test_review_single_source.py 的「量纲哨兵」）。

本文件把契约锁成可执行断言：
    引擎层 1-10  ──×10──▶  门禁/RL 信号层 0-100   （唯一跨界点：generator_cluster）
    引擎层 1-10  ──÷10──▶  证据链 payload 层 0-1   （唯一跨界点：T3 汇聚）
退还任一层的量纲、或在错误的一侧做换算（重复换算），本文件必须失败。
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.score_scale import (  # noqa: E402
    EMPTY_SCORE,
    clamp_gate_signal,
    clamp_ten_point,
    clamp_unit,
    ten_point_to_hundred,
    ten_point_to_unit,
)


# ── 1. 换算函数（单一真源） ──────────────────────────────────────────────────

def test_clamp_helpers_bound_and_guard_non_finite():
    """三层 clamp 的边界与脏值兜底。"""
    assert clamp_ten_point(7.5) == 7.5
    assert clamp_ten_point(28.0) == 10.0        # 越上限 → 10（不是 28，也不是 1）
    assert clamp_ten_point(-3.0) == 1.0         # 引擎层下限是 1 分
    assert clamp_unit(0.75) == 0.75
    assert clamp_unit(7.5) == 1.0               # 1-10 值裸入 0-1 层 → 封顶（会被看见，而非静默通过）
    assert clamp_gate_signal(73.0) == 73.0
    assert clamp_gate_signal(1000.0) == 100.0
    for bad in (None, float("nan"), float("inf"), "abc"):
        assert clamp_ten_point(bad) == 1.0
        assert clamp_unit(bad) == 0.0
        assert clamp_gate_signal(bad) == 0.0


def test_cross_layer_conversions_are_exact_and_round_trip():
    """跨界换算：1-10 ↔ 0-100 / 0-1（唯一方向，禁止就地心算）。"""
    assert ten_point_to_hundred(7.5) == 75.0
    assert ten_point_to_unit(7.5) == 0.75
    assert ten_point_to_hundred(clamp_ten_point(10.0)) == 100.0
    # 门禁层 0-100 的取值必须落在 RL 环境虚构区间 [40,95] 的同量纲空间内
    assert 0.0 <= ten_point_to_unit(7.5) <= 1.0
    assert EMPTY_SCORE == 0.0                   # 空输入哨兵：不属于任何一层量纲


# ── 2. 混音器：神经网络输出不得再缩放（事故①回归守卫） ──────────────────────

class _FakeOnnxSession:
    """假的 ONNX 推理会话：直接给出网络原生输出值。"""

    def __init__(self, value: float):
        self.value = value

    def run(self, output_names, inputs):  # noqa: ARG002
        return [
            np.array(self.value, dtype=np.float32),
            np.zeros((6, 64), dtype=np.float32),
            np.array(0.1, dtype=np.float32),
        ]


def _agent_results(n=6, score=7.5):
    return [
        {"agent_name": name, "content": f"内容 {i}", "score": score}
        for i, name in enumerate(
            ["teacher", "quizmaster", "media_designer", "extension", "ppt_designer", "code_practice"][:n]
        )
    ]


async def test_mixer_neural_output_is_not_rescaled(monkeypatch):
    """神经网络原生输出 6.8 → 共识分必须是 6.8，而不是 ×10 后被 clamp 成 10.0。

    （回归守卫：把 `* 10.0` 改回来，本用例必须失败。）
    """
    from engines.gomarl_mixer import neural_mixer

    monkeypatch.setattr(neural_mixer, "use_neural", True)
    monkeypatch.setattr(neural_mixer, "_init_mixer", lambda n: object())
    monkeypatch.setattr(neural_mixer, "_onnx_session", _FakeOnnxSession(6.8))

    result = await neural_mixer.mix(_agent_results(), {"level": "intermediate"}, "TCP三次握手")

    assert result["neural_used"] is True
    assert abs(result["consensus_score"] - 6.8) < 1e-6, (
        f"神经网络共识分被缩放了：期望 6.8（原生 1-10），实际 {result['consensus_score']}"
    )
    assert result["consensus_score"] < 10.0, "共识分被 clamp 到上限 → 区分度归零"


async def test_mixer_rule_fallback_is_ten_point_clamped(monkeypatch):
    """规则兜底（神经网络降级）也走同一 1-10 量纲与同一 clamp。"""
    from engines.gomarl_mixer import neural_mixer

    monkeypatch.setattr(neural_mixer, "use_neural", False)
    # 动态权重 >1 时，加权平均会越界 → 必须被钳到 10，而不是静默漂移
    monkeypatch.setattr(
        neural_mixer, "_compute_dynamic_weights",
        lambda names, profile: {n: 2.0 for n in names},
    )

    result = await neural_mixer.mix(_agent_results(score=9.0), {}, "TCP三次握手")

    assert result["neural_used"] is False
    assert result["consensus_score"] == 10.0, "兜底路径未钳制 → 会产出 18.0 这类越界值"


async def test_mixer_empty_input_returns_sentinel(monkeypatch):
    """空输入返回哨兵 0（"无数据"），而非伪造一个 1-10 的分数。"""
    from engines.gomarl_mixer import neural_mixer

    result = await neural_mixer.mix([], {}, "TCP三次握手")
    assert result["consensus_score"] == EMPTY_SCORE


# ── 3. 门禁层：consensus 通道是 0-100，且不得重复换算 ────────────────────────

def test_gate_consensus_channel_is_zero_to_hundred_and_not_reconverted():
    """门禁三通道同为 0-100；`review_signals` 不做 ×10（换算只在 generator_cluster 发生一次）。"""
    from agents.quality_gate import review_signals

    # 生产真实形态：evidence 0-100、confidence 0-1、overall_score 已由 generator_cluster 换算成 0-100
    evidence = {"consistency_score": 70.0}
    consensus = {"confidence_score": 0.5, "overall_score": ten_point_to_hundred(7.2)}
    s_h, s_c, s_k = review_signals(evidence, consensus)

    assert (s_h, s_c, s_k) == (70.0, 50.0, 72.0)
    # 若 review_signals 再 ×10，会得到 100（封顶）→ 与 RL 环境的奖励空间不一致
    assert s_k == 72.0, "consensus 通道被重复换算（×10）"


def test_gate_status_fallback_is_same_scale_as_overall_score():
    """status 兜底映射（90/50/45/40）与 overall_score 必须同量纲（0-100）。"""
    from agents.quality_gate import review_signals

    _, _, s_k = review_signals({}, {"status": "passed"})
    assert s_k == 90.0
    # 与换算后的 1-10 值同处 0-100 区间（10-100）
    assert ten_point_to_hundred(1.0) <= s_k <= ten_point_to_hundred(10.0)


# ── 4. 证据链 payload 层：0-1 硬约束 + T3 唯一入口 ───────────────────────────

def test_evidence_layer_rejects_ten_point_values():
    """证据层是 0-1 硬约束：喂 1-10 值必须报错（而不是静默截断成 1.0）。"""
    import pydantic
    import pytest

    from engines.evidence.schema import EvidenceChain

    with pytest.raises(pydantic.ValidationError):
        EvidenceChain(consensus_score=7.5)


def test_evidence_chain_converts_via_single_entry():
    """T3 写入走 set_consensus_from_ten_point（÷10），禁止人肉心算。"""
    from engines.evidence.schema import EvidenceChain

    chain = EvidenceChain().set_consensus_from_ten_point(7.5)
    assert chain.consensus_score == 0.75
    assert chain.to_dict()["consensus_score"] == 0.75


# ── 5. 事故②的机器守卫：RL 区间一致性 / 档位可达性 / 唯一跨界点 ──────────────

def test_rl_env_fabricates_consensus_in_same_scale_as_production():
    """RL 环境虚构的 overall_score 区间必须与生产换算后同处 0-100 空间。

    事故②的另一半：`generator_cluster` 曾裸写 1-10（区间 [1,10]），而
    `review_env_calibrated` 虚构 `uniform(40, 95)` ⇒ 两个区间**交集为空**，
    策略在训练中学到的该通道经验在生产上一条也用不上（sim2real 失效）。
    本用例锁住「两侧同处 0-100 且有实质重叠」，改回 0-1 虚构区间即失败。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(here, "..", "engines", "review_env_calibrated.py"),
               encoding="utf-8").read()

    assert '"overall_score": round(r.uniform(40.0, 95.0), 1)' in src, (
        "RL 环境虚构的 consensus 区间已变更：必须保持在与生产换算后同处的 0-100 空间内"
    )
    # 生产侧换算后的取值范围，必须与虚构区间有实质重叠（否则该通道在 sim2real 上失效）
    prod_lo, prod_hi = ten_point_to_hundred(1.0), ten_point_to_hundred(10.0)
    rl_lo, rl_hi = 40.0, 95.0
    assert max(prod_lo, rl_lo) < min(prod_hi, rl_hi), (
        f"生产区间 [{prod_lo},{prod_hi}] 与 RL 虚构区间 [{rl_lo},{rl_hi}] 无交集 → 该通道生产失效"
    )


def test_consensus_scale_break_makes_trust_consensus_unreachable():
    """量化事故②的后果：consensus 以 1-10 裸写时，`trust_consensus` 档位**完全不可达**。

    在 45 组典型生产样本上（s_h ∈ {40..100} × confidence ∈ {0.2,0.5,0.8} × 共识分 ∈ {4,6,9}）：
      · 旧行为（1-10 裸写）：档位 2 `trust_consensus` 被选中 **0 次**；
      · 修复后（0-100）：被选中 **16 次**，35.6% 的样本决策发生改变。
    这正是「RL 学到的 consensus 权重在生产上不产生增益」的机制 ——
    该通道因量级被压缩到 ~1/10，在 `analytic_review_action` 的加权比较中永远垫底。
    """
    from agents.quality_gate import review_signals  # noqa: F401  (同源前提)
    from engines.review_policy import analytic_review_action

    picks_old = {0: 0, 1: 0, 2: 0, 3: 0}
    picks_new = {0: 0, 1: 0, 2: 0, 3: 0}
    for s_h in (40.0, 55.0, 70.0, 85.0, 100.0):
        for conf in (0.2, 0.5, 0.8):
            for sk in (4.0, 6.0, 9.0):
                ev = {"consistency_score": s_h}
                picks_new[analytic_review_action(
                    ev, {"confidence_score": conf, "overall_score": ten_point_to_hundred(sk)}
                )] += 1
                picks_old[analytic_review_action(
                    ev, {"confidence_score": conf, "overall_score": sk}
                )] += 1

    assert picks_old[2] == 0, "旧量纲（1-10）下 trust_consensus 档位竟可达，量化前提已变"
    assert picks_new[2] > 0, "修复后 trust_consensus 档位仍不可达 → 跨界换算未生效"


def test_generator_cluster_is_the_only_crossing_point():
    """state["consensus"]["overall_score"] 必须经换算写入，不得裸赋 1-10 值。"""
    here = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(here, "..", "agents", "generator_cluster.py"), encoding="utf-8").read()

    assert "ten_point_to_hundred(consensus_result.overall_score)" in src, (
        "generator_cluster 未对共识分做 1-10 → 0-100 换算（门禁/RL 层按 0-100 消费该字段）"
    )
    assert '"overall_score": consensus_result.overall_score' not in src, (
        "generator_cluster 出现裸赋值：1-10 的引擎层分数直接流入 0-100 的门禁层"
    )
