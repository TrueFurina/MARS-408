"""TeachingEnv 的奖励必须反映**实际**正确率变化（2026-11-02）。

旧实现把意图增益（``base_gain + noise``）当作 Δ正确率。正确率饱和到 1.0 后
实际学习为 0，奖励却仍按 ~0.4 的增益发放（实测 step3–5 实际 Δ=0 仍发 ~0.44），
策略会学会「重复无效动作」。修复后饱和后奖励应降到只剩参与度/完成度/成本项。
"""
import pytest

from engines.mappo_policy import TeachingEnv


def _act():
    return {"difficulty": "medium", "teaching_mode": "sequential", "review_intensity": "full"}


def test_reward_drops_accuracy_term_after_saturation():
    env = TeachingEnv(horizon=10, seed=1, drift=0.0)
    env.reset()
    first_reward = None
    for i in range(5):
        _, r, _ = env.step(_act())
        if i == 0:
            first_reward = r
    assert env.accuracy == 1.0, "应已饱和"

    # 饱和后连续两步：实际 Δ=0，其余项恒定 → 奖励应稳定
    _, r1, _ = env.step(_act())
    _, r2, _ = env.step(_act())
    assert r1 == pytest.approx(r2), f"饱和后奖励应稳定：{r1} vs {r2}"

    # 且明显低于第一步（真正学习时）
    assert r1 < first_reward - 0.1, (
        f"饱和后仍按意图增益发奖：first={first_reward:.4f}, sat={r1:.4f}"
    )


def test_reward_monotonic_with_actual_delta():
    """真正学习的一步，奖励必须高于饱和后的零学习步。"""
    env = TeachingEnv(horizon=10, seed=1, drift=0.0)
    env.reset()
    _, r_learn, _ = env.step(_act())
    for _ in range(3):
        env.step(_act())
    _, r_sat, _ = env.step(_act())
    assert r_learn > r_sat
