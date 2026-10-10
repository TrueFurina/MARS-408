# ============================================================
# 回归测试：规则模式 consensus_score 必须约束到 0–10 契约区间
#
# 背景（gstack-investigator 发现，诚信红线相邻）：
#   gomarl_mixer.py:731 规则模式 consensus_score = mean(weighted_scores)，
#   而 weighted_scores = score × dynamic_weight，dynamic_weight 可为 0.5–1.5（EWMA 因子）。
#   当 score 高且 weight>1 时加权均值会越界 >10，违背
#   test_engine_modules.py:396-398,424 的「consensus_score 为 10 分制、须 ∈ [0,10]」契约。
#   神经路径 :763 已做 max(0,min(10,cs)) 钳制，规则路径此前未钳制 → 两路径量纲不一致。
#
# 本文件锁死：纯规则模式下，无论 score × weight 取何值，consensus_score 必须 ∈ [0,10]，
# 且与神经路径契约对齐；而 per-agent weighted_scores 字段可如实反映乘子（不钳制）。
# ============================================================

import asyncio

import numpy as np
import pytest

import engines.gomarl_mixer as mixer_mod
from engines.gomarl_mixer import NeuralGroupMixer

pytestmark = pytest.mark.unit

_AGENT_NAMES = [
    "teacher",
    "quizmaster",
    "media_designer",
    "extension",
    "ppt_designer",
    "code_practice",
]


def _make_results(n: int, level: float) -> list[dict]:
    return [
        {
            "agent_name": _AGENT_NAMES[i] if i < len(_AGENT_NAMES) else f"agent_{i}",
            "content": f"固定内容-{i}",
            "score": level,
        }
        for i in range(n)
    ]


def _build_rule_mixer(monkeypatch, n: int, weight: float) -> NeuralGroupMixer:
    """构造纯规则模式的 mixer（编码器/pg/redis 全部 stub，不触真实 E5 / PG / Redis）。"""
    rng = np.random.default_rng(20261011 + n)
    embeddings = rng.standard_normal((n, 768)).astype(np.float32)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)

    mixer = NeuralGroupMixer()
    mixer.use_neural = False  # 纯规则模式，跳过一切神经路径
    monkeypatch.setattr(mixer.encoder, "encode_batch", lambda texts: embeddings)
    # 动态权重全部固定为 weight ⇒ 规则加权均值 == mean(score × weight)
    monkeypatch.setattr(
        mixer,
        "_compute_dynamic_weights",
        lambda names, profile: {name: weight for name in names},
    )
    monkeypatch.setattr(mixer_mod.pg_client, "log_agent_score", lambda *args: None)
    monkeypatch.setattr(mixer_mod.redis_client, "cache_agent_weights", lambda weights: None)
    return mixer


class TestRuleModeConsensusClamp:
    def test_high_score_high_weight_clamped_to_10(self, monkeypatch):
        """score=10 × weight=1.5 ⇒ 加权均值 15.0 ⇒ 必须钳制到契约上界 10.0。"""
        mixer = _build_rule_mixer(monkeypatch, 6, weight=1.5)
        result = asyncio.run(mixer.mix(_make_results(6, 10.0), {}, "规则模式钳制-上界"))

        assert result["neural_used"] is False
        assert result["consensus_score"] == pytest.approx(10.0, abs=1e-6)
        # per-agent 加权分可如实反映乘子（不钳制）
        assert all(abs(v - 15.0) < 1e-6 for v in result["weighted_scores"].values())

    def test_mid_score_identity(self, monkeypatch):
        """常规区间（score=6 × weight=1.0）应保持原值，不引入偏移。"""
        mixer = _build_rule_mixer(monkeypatch, 6, weight=1.0)
        result = asyncio.run(mixer.mix(_make_results(6, 6.0), {}, "规则模式中位"))

        assert result["consensus_score"] == pytest.approx(6.0, abs=1e-6)

    def test_low_clamped_to_0(self, monkeypatch):
        """score=-2 × weight=1.5 ⇒ 加权均值 -3.0 ⇒ 必须钳制到下界 0.0。"""
        mixer = _build_rule_mixer(monkeypatch, 6, weight=1.5)
        result = asyncio.run(mixer.mix(_make_results(6, -2.0), {}, "规则模式钳制-下界"))

        assert result["consensus_score"] == pytest.approx(0.0, abs=1e-6)

    def test_within_range_for_varied_weights(self, monkeypatch):
        """权重在 0.5–1.5 范围内抖动时，consensus_score 仍须 ∈ [0,10]。"""
        mixer = _build_rule_mixer(monkeypatch, 6, weight=1.5)
        # score 在 0–10 之间，weight 1.5 ⇒ 单值最高 15.0，钳制后应 ≤10
        for level in (0.0, 3.3, 7.7, 10.0):
            result = asyncio.run(mixer.mix(_make_results(6, level), {}, f"规则模式-档位{level}"))
            assert 0.0 <= result["consensus_score"] <= 10.0, result["consensus_score"]
