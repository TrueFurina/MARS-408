# tests/test_review_analytic.py — 解析最优档位（恒等式）守护测试（2026-09-14）
#
# 立论：生产打分 `effective = s_h + (h·s_h + c·s_c + k·s_k) − mean`
# ⇒ 四档有效分可直接算出，最优档位是**解析解**（零训练、零搜索、零拟合）。
# 实测（experiments/diag_state_extend.py，独立泛化集）：
#   无噪 capture 100.0% / 与 oracle 动作一致率 100.0%；
#   加噪 ±0.03 capture 99.7% / 一致率 96.2%；
#   对比：折进阈值的二分支规则 50.1%、RL 最优配置 56.1%。
#
# 本文件守护：
#   1. **恒等式**：解析式 == 生产打分函数在 0..3 上的 argmax（逐位一致）；
#   2. 解析式在独立泛化集上的 capture ≈ 100%（远高于任何学习方案）；
#   3. 对观测噪声稳健（加噪后仍 ≥90% 头寸）；
#   4. 接口接线：decide_review_weight 在 analytic 模式返回 source="analytic"；
#      缺 evidence/consensus 时**不得**崩溃，须退回策略路径；
#   5. 灰度关闭（use_mappo=False）行为零变化。

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiments"))

from agents.quality_gate import weighted_consistency_score  # noqa: E402
from engines.review_env_calibrated import discipline_gate  # noqa: E402
from engines.review_policy import (  # noqa: E402
    RULE_MODE,
    UNIFORM_WEIGHTS,
    _weights_of,
    analytic_review_action,
    decide_review_weight,
    review_state_features,
    review_weight_schema,
)
from run_shadow_probe import generate_samples  # noqa: E402

N = 240
TRAIN_SEED = 20260914
TEST_SEED = 313131
NOISE = 0.03


def _samples(seed: int):
    return generate_samples(N, random.Random(seed))


def _effs(sample):
    return [weighted_consistency_score(
        sample["evidence"], sample["consensus"],
        review_weight_schema(_weights_of(a)))[0] for a in range(4)]


def _noisy_consensus(consensus: dict, rng: random.Random) -> dict:
    co = dict(consensus)
    try:
        co["confidence_score"] = max(0.0, min(
            1.0, float(co.get("confidence_score") or 0.6) + rng.uniform(-NOISE, NOISE)))
    except (TypeError, ValueError):
        pass
    try:
        co["overall_score"] = max(0.0, min(
            100.0, float(co.get("overall_score") or 60.0) + rng.uniform(-100 * NOISE, 100 * NOISE)))
    except (TypeError, ValueError):
        pass
    return co


# ── 1. 恒等式（核心）──

def test_analytic_is_identity_with_scoring_argmax():
    """解析式必须与生产打分函数的 argmax **逐位一致**（这是恒等式，不是近似）。"""
    mism = []
    for s in _samples(TRAIN_SEED):
        eff = _effs(s)
        oracle = max(range(4), key=lambda a: eff[a])
        got = analytic_review_action(s["evidence"], s["consensus"])
        if got != oracle:
            mism.append((oracle, got))
    assert not mism, f"解析式与打分 argmax 不一致 {len(mism)}/{N} 例：{mism[:5]}"


# ── 2. capture ≈ 100%（独立泛化集）──

def test_analytic_capture_near_full_on_holdout():
    samples = _samples(TEST_SEED)
    effs = [_effs(s) for s in samples]
    uni = sum(e[3] for e in effs) / N
    ora = sum(max(e) for e in effs) / N
    headroom = ora - uni
    got = 0.0
    for s, e in zip(samples, effs):
        a = discipline_gate(analytic_review_action(s["evidence"], s["consensus"]),
                            [0.5] * 12, 0, 0)
        got += e[a]
    got /= N
    capture = (got - uni) / headroom
    assert capture > 0.98, f"解析式 capture 应 ≈100%，实际 {100*capture:.1f}%"


def test_analytic_beats_rule_substantially():
    """与折进阈值的规则对比：解析式应显著更高（实测 99.7% vs 50.1%）。"""
    from engines.review_policy import _rule_action_idx
    samples = _samples(TEST_SEED)
    effs = [_effs(s) for s in samples]
    uni = sum(e[3] for e in effs) / N
    ora = sum(max(e) for e in effs) / N
    headroom = ora - uni

    def cap(fn):
        tot = 0.0
        for s, e in zip(samples, effs):
            f = review_state_features(evidence=s["evidence"], critic=s["critic"],
                                     consensus=s["consensus"], state=s["state"],
                                     mode_encoding=s["mode_encoding"], round_ratio=s["round_ratio"])
            a = discipline_gate(fn(s, f), f, 0, 0)
            tot += e[a]
        return (tot / N - uni) / headroom

    c_an = cap(lambda s, f: analytic_review_action(s["evidence"], s["consensus"]))
    c_rule = cap(lambda s, f: _rule_action_idx(f))
    assert c_an > c_rule + 0.3, f"解析式应大幅优于规则：analytic={100*c_an:.1f}% rule={100*c_rule:.1f}%"


# ── 3. 噪声稳健性 ──

def test_analytic_robust_to_observation_noise():
    """决策读带噪观测、验收看真值分 —— 模拟上游估计误差。仍应 ≥90% 头寸。"""
    samples = _samples(TEST_SEED)
    effs = [_effs(s) for s in samples]
    uni = sum(e[3] for e in effs) / N
    ora = sum(max(e) for e in effs) / N
    headroom = ora - uni
    rng = random.Random(777)
    tot = 0.0
    for s, e in zip(samples, effs):
        co_n = _noisy_consensus(s["consensus"], rng)
        a = discipline_gate(analytic_review_action(s["evidence"], co_n), [0.5] * 12, 0, 0)
        tot += e[a]
    capture = (tot / N - uni) / headroom
    assert capture > 0.90, f"加噪后 capture 应 ≥90%，实际 {100*capture:.1f}%"


# ── 4. 接口接线与 fail-open ──

def _feats_of(s):
    return review_state_features(
        evidence=s["evidence"], critic=s["critic"], consensus=s["consensus"],
        state=s["state"], mode_encoding=s["mode_encoding"], round_ratio=s["round_ratio"])


def test_decide_review_weight_analytic_path():
    assert RULE_MODE == "analytic", "默认应为解析最优模式"
    s = _samples(TRAIN_SEED)[0]
    out = decide_review_weight(_feats_of(s), use_mappo=True,
                               evidence=s["evidence"], consensus=s["consensus"])
    assert out["source"] == "analytic"
    assert out["action"] in (0, 1, 2, 3)
    assert out["weights"] == review_weight_schema(_weights_of(out["action"]))


def test_decide_review_weight_without_context_falls_back():
    """缺 evidence/consensus 时不得崩溃，必须退回策略路径（mappo/rule）。"""
    s = _samples(TRAIN_SEED)[0]
    out = decide_review_weight(_feats_of(s), use_mappo=True)
    assert out["source"] in ("mappo", "rule", "rule_fallback", "uniform")
    assert out["action"] in (0, 1, 2, 3, 4)


def test_disabled_path_unchanged():
    """灰度关闭 → 均匀权重，行为零变化（现状安全）。"""
    s = _samples(TRAIN_SEED)[0]
    out = decide_review_weight(_feats_of(s), use_mappo=False,
                               evidence=s["evidence"], consensus=s["consensus"])
    assert out["weights"] == UNIFORM_WEIGHTS
    assert out["source"] == "uniform"
    assert out["action"] == 3


def test_bad_features_do_not_break_analytic_guard():
    """非法特征（NaN）时解析路径应被 `_features_valid` 挡住 → fail-open 均匀权重。"""
    s = _samples(TRAIN_SEED)[0]
    out = decide_review_weight([float("nan")] * 12, use_mappo=True,
                               evidence=s["evidence"], consensus=s["consensus"])
    assert out["weights"] == UNIFORM_WEIGHTS
