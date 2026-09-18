# ============================================================
# test_review_mappo — 三元评审权重 MAPPO 化（攻坚令阶段 2 验收）
#
# 覆盖：状态编码 / 动作映射 / 权重协议 / 奖励可复算 / 合成环境 /
#       规则预热 / PPO 训练 / 降级 fail-open / 灰度关闭零影响 / 纪律硬约束
# 诚信：torch 不可用时对训练相关断言做诚实降级标注，不伪造收敛结论。
# ============================================================

import pytest

from engines import review_policy as rp


# ── 1. 状态编码（12 维、归一化、确定性、缺失中性）──

def test_state_features_dim_and_range():
    feats = rp.review_state_features(
        evidence={"consistency_score": 80.0, "coverage": 4, "expected_coverage": 5},
        critic={"confidence": 0.7, "valid_count": 3, "invalid_count": 1},
        consensus={"status": "conflict", "disagreement": 0.6},
        state={"gate_retry_count": 2, "tokens_used": 2000, "token_budget": 4000},
        mode_encoding=0.5, round_ratio=0.5,
    )
    assert len(feats) == 12
    assert all(0.0 <= v <= 1.0 for v in feats)


def test_state_features_deterministic():
    kwargs = dict(
        evidence={"consistency_score": 65.0, "coverage": 3, "expected_coverage": 6},
        critic={"confidence": 0.4, "valid_count": 2, "invalid_count": 2},
        consensus={"status": "pass"}, state={"gate_retry_count": 1},
    )
    a = rp.review_state_features(**kwargs)
    b = rp.review_state_features(**kwargs)
    assert a == b


def test_state_features_missing_fields_are_neutral():
    feats = rp.review_state_features()
    assert len(feats) == 12
    assert all(0.0 <= v <= 1.0 for v in feats)
    # 无 last_consistency 时 quality_delta 取中性 0.5
    assert feats[8] == 0.5


def test_state_features_normalizes_consistency_and_status():
    feats = rp.review_state_features(
        evidence={"consistency_score": 100.0}, consensus={"status": "none"})
    assert feats[1] == pytest.approx(1.0)   # consistency /100
    assert feats[3] == pytest.approx(1.0)   # none → 1.0


# ── 2. 动作映射与权重协议 ──

def test_action_space_and_weights():
    assert len(rp.REVIEW_ACTIONS) == 5
    assert rp.REVIEW_WEIGHTS[0] == (0.6, 0.2, 0.2)
    assert rp.REVIEW_WEIGHTS[1] == (0.2, 0.6, 0.2)
    assert rp.REVIEW_WEIGHTS[2] == (0.2, 0.2, 0.6)
    assert sum(rp.REVIEW_WEIGHTS[3]) == pytest.approx(1.0)
    assert rp.REVIEW_WEIGHTS[4] == (0.0, 0.0, 0.0)  # skip


def test_weight_schema_normalizes():
    w = rp.review_weight_schema({"honest": 2.0, "critic": 1.0, "consensus": 1.0})
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["honest"] == pytest.approx(0.5)


def test_weight_schema_skip_and_invalid_fallback():
    assert rp.review_weight_schema({"honest": 0, "critic": 0, "consensus": 0}) == {
        "honest": 0.0, "critic": 0.0, "consensus": 0.0}
    assert rp.review_weight_schema(None) == rp.UNIFORM_WEIGHTS
    assert rp.review_weight_schema("not-a-dict") == rp.UNIFORM_WEIGHTS
    assert sum(rp.UNIFORM_WEIGHTS.values()) == pytest.approx(1.0)


def test_weights_of_out_of_range_action():
    assert rp._weights_of(99) == rp.UNIFORM_WEIGHTS


# ── 3. 奖励（4 分量、可复算、skip 纪律）──

def test_reward_is_recomputable():
    a = rp.review_reward(50.0, 70.0, True, 400.0, 0)
    b = rp.review_reward(50.0, 70.0, True, 400.0, 0)
    assert a == pytest.approx(b)


def test_reward_precision_matters():
    good = rp.review_reward(60.0, 60.0, True, 0.0, 0)
    bad = rp.review_reward(60.0, 60.0, False, 0.0, 0)
    assert good > bad


def test_reward_penalizes_skip_streak():
    r0 = rp.review_reward(60.0, 60.0, False, 0.0, 0)
    r3 = rp.review_reward(60.0, 60.0, False, 0.0, 3)
    assert r3 < r0  # 连发 ≥2 触发 w4 重罚


# ── 4. 合成评审环境 ──

def test_env_reset_step_shape_and_done():
    env = rp.ReviewEnv(seed=1, horizon=3)
    feats = env.reset()
    assert len(feats) == 12
    done = False
    steps = 0
    while not done and steps < 10:
        feats, r, done = env.step(3)
        steps += 1
        assert len(feats) == 12
        assert isinstance(r, float)
    assert done and steps == 3


def test_env_same_seed_is_reproducible():
    def run(seed):
        env = rp.ReviewEnv(seed=seed, horizon=4)
        env.reset()
        total = 0.0
        for a in (0, 1, 3, 2):
            _f, r, _d = env.step(a)
            total += r
        return total
    assert run(42) == pytest.approx(run(42))


# ── 5. 规则版策略 ──

def test_rule_action_maps_strong_evidence_to_honest():
    # consistency=0.8（≥0.6）→ trust_honest
    feats = [0.5] * 12
    feats[1] = 0.8
    assert rp._rule_action_idx(feats) == 0


def test_rule_action_default_balanced():
    feats = [0.5, 0.45, 0.5, 0.5, 0.0, 0.5, 0.2, 0.2, 0.5, 0.1, 0.5, 0.2]
    assert rp._rule_action_idx(feats) in (2, 3)


# ── 6. 策略：预热 / 推理 / 纪律硬约束 ──

def test_policy_select_action_blocks_skip_under_discipline():
    pol = rp.ReviewWeightPolicy()
    feats = rp.review_state_features()
    # 真实评审不足 → 禁止 skip
    idx, src = pol.select_action(feats, deterministic=True, skip_streak=0, reviews_done=0)
    assert idx != 4
    assert src in ("mappo", "rule", "rule_fallback")
    # skip 连发超限时即使策略想选 4 也被压回
    idx2, _ = pol.select_action(feats, deterministic=True, skip_streak=3, reviews_done=5)
    assert idx2 != 4


def test_decide_review_weight_uniform_when_disabled():
    """灰度关闭（use_mappo=False）→ 均匀权重，等价于现状，行为零变化。"""
    out = rp.decide_review_weight(rp.review_state_features(), use_mappo=False)
    assert out["weights"] == rp.UNIFORM_WEIGHTS
    assert out["source"] == "uniform"
    assert out["action"] == 3


def test_decide_review_weight_fails_open_on_bad_features():
    """异常输入不得抛出，必须 fail-open 到均匀权重。"""
    out = rp.decide_review_weight([float("nan")] * 12, use_mappo=True)
    assert out["weights"] == rp.UNIFORM_WEIGHTS
    assert out["source"] in ("uniform", "mappo", "rule", "rule_fallback")


def test_mappo_disabled_by_default_in_config():
    """默认未配置 use_review_mappo → 灰度关闭（生产安全）。"""
    assert rp._mappo_enabled() is False


# ── 7. 预热与训练（torch 可用则真跑；不可用诚实降级）──

def test_warmup_with_rules():
    pol = rp.ReviewWeightPolicy()
    if not pol.torch_available:
        res = pol.warmup_with_rules(steps=10)
        assert res["warmed"] is False  # 诚实降级，不伪造
        pytest.skip("torch 不可用，warmup 走规则降级路径")
    res = pol.warmup_with_rules(steps=30, seed=7)
    assert res["warmed"] is True
    assert res["steps"] == 30


def test_ppo_training_runs_or_degrades_honestly():
    pol = rp.ReviewWeightPolicy()
    if not pol.torch_available:
        res = pol.train_ppo(episodes=2)
        assert res["trained"] is False
        pytest.skip("torch 不可用，PPO 训练诚实降级")
    res = pol.train_ppo(episodes=8, horizon=4, seed=42)
    assert res["trained"] is True
    assert len(res["returns"]) == 8
    assert isinstance(res["improved"], bool)


def test_evaluate_policy_reports_discipline_zero_violation():
    """规则版与 RL 版均不得出现 skip 连发 ≥2 的纪律违例。"""
    pol = rp.ReviewWeightPolicy()
    if pol.torch_available:
        pol.warmup_with_rules(steps=20, seed=7)
    env = rp.ReviewEnv(seed=7, horizon=6)
    res = pol.select_action and rp.evaluate_policy(pol, rp.ReviewEnv(seed=7, horizon=6))
    assert res["discipline_violation"] is False
    assert res["max_skip_streak"] < rp.SKIP_STREAK_LIMIT
    _ = env


def test_evaluate_rule_baseline_no_violation():
    res = rp.evaluate_policy("rule", rp.ReviewEnv(seed=3, horizon=6))
    assert res["discipline_violation"] is False


def test_reset_shared_policy_is_idempotent():
    rp.reset_shared_policy()
    pol1 = rp._get_shared_policy()
    rp.reset_shared_policy()
    pol2 = rp._get_shared_policy()
    assert pol1 is not pol2


# ── 9. 可复现性（防回归：网络初始化必须受 seed 控制）──

def test_same_seed_training_is_reproducible():
    """同一 seed 两次训练必须产出完全相同的策略。

    回归背景：早期版本 ReviewWeightPolicy 未播种，网络权重初始化走 torch 全局 RNG，
    导致同 seed 两次跑动作分布不同（实测 balanced 1.000 vs trust_honest 0.339），
    3-seed 实验事实上不可复算。
    """
    if not rp.ReviewWeightPolicy().torch_available:
        pytest.skip("torch 不可用，无法验证训练可复现性")

    def _train_once(seed: int) -> list[int]:
        pol = rp.ReviewWeightPolicy(seed=seed)
        pol.warmup_with_rules(rp.ReviewEnv(seed=seed), steps=30, seed=seed)
        pol.train_ppo(rp.ReviewEnv(seed=seed), episodes=5, seed=seed)
        env = rp.ReviewEnv(seed=999, horizon=6)
        acts = []
        s = env.reset()
        for _ in range(6):
            a, _src = pol.select_action(s, deterministic=True)
            acts.append(a)
            s, _r, done = env.step(a)
            if done:
                break
        return acts

    assert _train_once(11) == _train_once(11), (
        "同 seed 两次训练动作序列不一致：网络初始化未受 seed 控制，"
        "3-seed 实验结果将不可复算"
    )


def test_seed_all_covers_torch_rng():
    """_seed_all 必须同时播种 python/numpy/torch，否则 dist.sample() 仍不可控。"""
    rp._seed_all(7)
    try:
        import torch
    except Exception:
        pytest.skip("torch 不可用")
    a = float(torch.rand(1).item())
    rp._seed_all(7)
    b = float(torch.rand(1).item())
    assert a == b, "_seed_all 未真正固定 torch 全局 RNG"
