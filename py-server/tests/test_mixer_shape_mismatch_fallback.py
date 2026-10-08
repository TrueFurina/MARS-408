# ============================================================
# 回归测试：n≠6 权重形状不匹配 ⇒ 禁止冒充神经推理
#
# 背景（诚信红线）：
#   训练时 n_agents=6，故 global_mixer.0.weight 形状为 (64, 6+64)=(64,70)。
#   生产调用点 engines/gomarl.py 传的是 zip(results, scores) 的全量 agent 列表，
#   长度不恒为 6。当 n≠6 时该层形状不匹配 → 权重不加载 → 保持随机初始化，
#   但旧代码仍走神经输出并把 neural_used 置为 True。
#   这与已修复的 ONNX「均匀权重冒充神经推理」是同一类错误：
#   用非神经输出（随机/均匀权重）冒充神经推理。
#
#   实测后果：n=3 四档全被 clamp 成 0.0、n=5「很差」档 0.0、n=7「9.5 分」档 0.32。
#
# 本文件锁死：只要权重未完整加载，结果必须 neural_used=False 且
#   mode == "shape_mismatch_fallback"（不得为 "torch"）。
# ============================================================

import asyncio

import numpy as np
import pytest

import engines.gomarl_mixer as mixer_mod
from engines.gomarl_mixer import NeuralGroupMixer

pytestmark = pytest.mark.unit

# 训练权重对应的 agent 数（改这个值等于改了训练产物，需要同步重新训练）
_TRAINED_N_AGENTS = 6

_ALL_AGENT_NAMES = [
    "teacher",
    "quizmaster",
    "media_designer",
    "extension",
    "ppt_designer",
    "code_practice",
]


def _make_results(n: int, level: float) -> list[dict]:
    """构造 n 个 agent 的结果，评分统一为 level。"""
    return [
        {
            "agent_name": _ALL_AGENT_NAMES[i] if i < len(_ALL_AGENT_NAMES) else f"agent_{i}",
            "content": f"固定内容-{i}",
            "score": level,
        }
        for i in range(n)
    ]


def _build_mixer(monkeypatch, n: int) -> NeuralGroupMixer:
    """构造一个编码器/权重被 stub 掉的 mixer（不触碰真实 E5 / PG / Redis）。"""
    rng = np.random.default_rng(20261005 + n)
    embeddings = rng.standard_normal((n, 768)).astype(np.float32)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)

    mixer = NeuralGroupMixer()
    monkeypatch.setattr(mixer.encoder, "encode_batch", lambda texts: embeddings)
    # 动态权重固定为 1.0 ⇒ 规则降级路径的期望值 == 各 agent 评分的算术平均
    monkeypatch.setattr(
        mixer,
        "_compute_dynamic_weights",
        lambda names, profile: {name: 1.0 for name in names},
    )
    monkeypatch.setattr(mixer_mod.pg_client, "log_agent_score", lambda *args: None)
    monkeypatch.setattr(mixer_mod.redis_client, "cache_agent_weights", lambda weights: None)
    return mixer


class TestShapeMismatchForbidsNeuralClaim:
    def test_n5_mix_must_not_claim_neural(self, monkeypatch, trained_mixer_checkpoint):
        """n=5 触发形状不匹配 ⇒ neural_used=False 且 mode 为 shape_mismatch_fallback。"""
        mixer = _build_mixer(monkeypatch, 5)
        result = asyncio.run(mixer.mix(_make_results(5, 8.0), {}, "形状不匹配回归"))

        # 核心断言：绝不允许把随机初始化层的输出标成神经推理
        assert result["neural_used"] is False
        assert result["neural_mode"] == "shape_mismatch_fallback"
        assert result["neural_mode"] != "torch"

        stats = mixer.get_stats()
        assert stats["mixer_neural_mode"] == "shape_mismatch_fallback"
        assert stats["mixer_weights_complete"] is False
        assert "global_mixer.0.weight" in stats["mixer_weight_mismatch_layers"]

    def test_n5_falls_back_to_rule_weighted_mean(self, monkeypatch, trained_mixer_checkpoint):
        """降级后必须走规则模式加权（动态权重 × 评分 的均值），而非随机网络输出。"""
        mixer = _build_mixer(monkeypatch, 5)
        result = asyncio.run(mixer.mix(_make_results(5, 8.0), {}, "形状不匹配回归"))

        assert result["neural_used"] is False
        # 前置条件（防"以错误理由通过"）：必须命中「形状不匹配」这条降级，
        # 而非「训练权重加载失败」的通用 rule 降级 —— 二者都 neural_used=False、
        # 都退化为加权均值，只断言数值无法区分。
        # 实测：若不注入 checkpoint，「加载失败 → rule」下本用例仍然 PASSED。
        assert result["neural_mode"] == "shape_mismatch_fallback"
        # 动态权重被 stub 成 1.0 ⇒ 规则降级结果 == 8.0（而不是随机网络的 0.0）
        assert result["consensus_score"] == pytest.approx(8.0, abs=1e-5)

    def test_n5_keeps_level_discrimination(self, monkeypatch, trained_mixer_checkpoint):
        """降级后各档位仍须单调可分——旧 bug 是四档全被 clamp 成同一个值。"""
        mixer = _build_mixer(monkeypatch, 5)
        results = [
            asyncio.run(mixer.mix(_make_results(5, level), {}, "形状不匹配回归"))
            for level in (1.0, 4.0, 7.0, 9.5)
        ]
        # 同上的前置条件：区分「形状不匹配降级」与「加载失败降级」。
        assert {r["neural_mode"] for r in results} == {"shape_mismatch_fallback"}
        scores = [r["consensus_score"] for r in results]

        assert scores == sorted(scores), scores
        assert len(set(scores)) == 4, scores
        assert all(0.0 < s <= 10.0 for s in scores), scores

    def test_other_agent_counts_also_forbid_neural(self, monkeypatch, trained_mixer_checkpoint):
        """n=3/4/7/8 同样不得宣称神经推理（生产调用点长度不恒为 6）。"""
        for n in (3, 4, 7, 8):
            mixer = _build_mixer(monkeypatch, n)
            result = asyncio.run(mixer.mix(_make_results(n, 7.0), {}, "形状不匹配回归"))
            assert result["neural_used"] is False, f"n={n} 错误宣称神经推理"
            assert result["neural_mode"] == "shape_mismatch_fallback", f"n={n}"

    def test_n6_still_uses_real_neural(self, monkeypatch, trained_mixer_checkpoint):
        """对照：n=6 且权重完整加载 ⇒ 必须走 torch 分支，降级逻辑不得误伤。"""
        # 必须与 conftest 夹具 trained_mixer_checkpoint 的 n_agents 一致（=6），
        # 否则本用例会因"夹具的 n 与断言不符"而失败，且失败原因指向错误方向。
        assert _TRAINED_N_AGENTS == 6
        mixer = _build_mixer(monkeypatch, 6)
        result = asyncio.run(mixer.mix(_make_results(6, 8.0), {}, "n=6 对照"))

        assert result["neural_used"] is True
        assert result["neural_mode"] == "torch"
        stats = mixer.get_stats()
        assert stats["mixer_weights_complete"] is True
        assert stats["mixer_weight_mismatch_layers"] == []
