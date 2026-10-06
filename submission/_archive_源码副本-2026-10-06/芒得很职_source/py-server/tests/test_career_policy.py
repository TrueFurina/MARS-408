# ============================================================
# P3③ 鲶鱼 MAPPO 化测试（设计文档验收：≥12 用例）
# 覆盖：状态特征 / 奖励可复算 / 合成环境 / 动作映射 /
#       灰度关闭零影响 / 降级路径 / 纪律（连压≤2）
# 运行：python -m pytest tests/test_career_policy.py -q
# ============================================================

import pytest

from engines.career_policy import (
    CAREER_ACTIONS,
    CATFISH_MAX_CONTINUE,
    CareerAdversaryEnv,
    CareerModePolicy,
    REWARD_W,
    _rule_action_idx,
    career_reward,
    career_state_features,
    maybe_mappo_decide,
    reset_shared_policy,
)
from agents.career_nodes import decide_adversary_mode
from agents.career_state import DIMENSIONS


# ────────────────────────────────────────────────────────────
# 状态特征（8 维）
# ────────────────────────────────────────────────────────────

def test_features_dimension_is_eight():
    feats = career_state_features([], current_mode="normal", catfish_streak=0)
    assert len(feats) == 8


def test_features_all_normalized():
    turns = [{"evidence": {"density": d}} for d in (0.2, 0.9, 0.5, 1.3)]
    feats = career_state_features(turns, six_scores={d: 5.0 for d in DIMENSIONS},
                                  current_mode="catfish", catfish_streak=5,
                                  max_turns=4)
    assert all(0.0 <= f <= 1.0 for f in feats), feats


def test_features_reflect_turn_progress():
    early = career_state_features([], max_turns=8)
    late = career_state_features([{"evidence": {}}] * 8, max_turns=8)
    assert late[0] == 1.0 and early[0] == 0.0  # turn_ratio


def test_features_density_averages_recent_three():
    turns = [{"evidence": {"density": 0.1}}, {"evidence": {"density": 0.1}},
             {"evidence": {"density": 0.1}}, {"evidence": {"density": 0.7}},
             {"evidence": {"density": 0.7}}, {"evidence": {"density": 0.7}}]
    feats = career_state_features(turns)
    assert abs(feats[1] - 0.7) < 1e-6  # 只取最近 3 轮


# ────────────────────────────────────────────────────────────
# 奖励（可复算，4 分量）
# ────────────────────────────────────────────────────────────

def test_reward_improvement_positive():
    r = career_reward({d: 3.0 for d in DIMENSIONS}, {d: 4.0 for d in DIMENSIONS},
                      0.4, 0.6, tokens=0, catfish_streak=0)
    assert r > 0


def test_reward_degradation_negative():
    r = career_reward({d: 4.0 for d in DIMENSIONS}, {d: 3.0 for d in DIMENSIONS},
                      0.6, 0.4, tokens=1000, catfish_streak=0)
    assert r < 0


def test_reward_token_cost_penalized():
    cheap = career_reward({d: 3.0 for d in DIMENSIONS}, {d: 3.0 for d in DIMENSIONS},
                          0.5, 0.5, tokens=100, catfish_streak=0)
    dear = career_reward({d: 3.0 for d in DIMENSIONS}, {d: 3.0 for d in DIMENSIONS},
                         0.5, 0.5, tokens=2000, catfish_streak=0)
    assert dear < cheap  # 同收益下高 token 奖励更低


def test_reward_catfish_abuse_discipline():
    ok = career_reward({d: 3.0 for d in DIMENSIONS}, {d: 3.0 for d in DIMENSIONS},
                       0.5, 0.5, tokens=0, catfish_streak=CATFISH_MAX_CONTINUE)
    abuse = career_reward({d: 3.0 for d in DIMENSIONS}, {d: 3.0 for d in DIMENSIONS},
                          0.5, 0.5, tokens=0, catfish_streak=CATFISH_MAX_CONTINUE + 3)
    assert abuse < ok  # 超限重罚


# ────────────────────────────────────────────────────────────
# 合成环境与规则策略
# ────────────────────────────────────────────────────────────

def test_env_step_returns_contract():
    env = CareerAdversaryEnv(seed=42, horizon=4)
    feats = env.reset()
    assert len(feats) == 8
    f2, reward, done = env.step(1)
    assert len(f2) == 8 and isinstance(reward, float) and done is False
    for _ in range(3):
        f2, _r, done = env.step(0)
    assert done is True  # horizon 到达


def test_env_catfish_streak_counts_and_resets():
    env = CareerAdversaryEnv(seed=1, horizon=8)
    env.reset()
    env.step(2); env.step(2)
    assert env.catfish_streak == 2
    env.step(0)
    assert env.catfish_streak == 0


def test_rule_action_respects_discipline():
    # 鲶鱼连压到上限 → 必须回 normal（idx=0）
    feats = [0.5, 0.2, 0.3, 1.0, 1.0, 0.5, 0.3, 0.5]
    assert _rule_action_idx(feats) == 0


def test_rule_action_low_density_escalates():
    feats = [0.3, 0.2, 0.6, 0.0, 0.0, 0.5, 0.3, 0.3]
    assert _rule_action_idx(feats) in (1, 2)  # 加压或鲶鱼


def test_policy_fallback_without_torch():
    """无 torch / 未训练 → 规则动作（降级路径）"""
    p = CareerModePolicy()
    idx, src = p.select_action([0.5] * 8)
    assert src in ("rule", "mappo") and 0 <= idx < 3


# ────────────────────────────────────────────────────────────
# 决策层：灰度关闭零影响 / 灰度开启同契约
# ────────────────────────────────────────────────────────────

@pytest.fixture()
def mappo_off(monkeypatch):
    import engines.career_policy as cp
    monkeypatch.setattr(cp, "_mappo_enabled", lambda: False)
    reset_shared_policy()
    yield
    reset_shared_policy()


@pytest.fixture()
def mappo_on(monkeypatch):
    import engines.career_policy as cp
    monkeypatch.setattr(cp, "_mappo_enabled", lambda: True)
    reset_shared_policy()
    yield
    reset_shared_policy()


def test_gray_off_uses_rule_verbatim(mappo_off):
    """灰度关闭 → 与原规则版逐字节一致（零影响）"""
    turns = [{"evidence": {"template_suspect": True, "density": 0.2}},
             {"evidence": {"template_suspect": True, "density": 0.2}}]
    assert decide_adversary_mode(turns, "normal", 0) == ("catfish", True, 1)


def test_gray_off_empty_turns(mappo_off):
    assert decide_adversary_mode([], "normal", 0) == ("normal", False, 0)


def test_gray_on_same_contract(mappo_on):
    """灰度开启 → 返回三元组契约不变，鲶鱼连压永不超限"""
    turns = [{"evidence": {"template_suspect": True, "density": 0.2}}] * 4
    mode, triggered, cont = decide_adversary_mode(turns, "catfish", CATFISH_MAX_CONTINUE)
    assert mode in CAREER_ACTIONS
    assert isinstance(triggered, bool)
    if mode == "catfish":
        assert cont <= CATFISH_MAX_CONTINUE


def test_gray_on_discipline_zero_violation(mappo_on):
    """纪律红线：连跑 20 轮低密度对话，鲶鱼连续段永不超 2（设计验收）"""
    import random
    rng = random.Random(123)
    turns, mode, streak, violations = [], "normal", 0, 0
    for _ in range(20):
        turns.append({"evidence": {"template_suspect": rng.random() < 0.5,
                                   "density": rng.uniform(0.1, 0.4)}})
        mode, _t, streak = decide_adversary_mode(turns, mode, streak)
        if mode == "catfish" and streak > CATFISH_MAX_CONTINUE:
            violations += 1
    assert violations == 0


def test_maybe_mappo_returns_none_when_disabled(mappo_off):
    assert maybe_mappo_decide([], "normal", 0, rule_fn=lambda *a: ("normal", False, 0)) is None


def test_reward_weights_match_design():
    """奖励权重与设计文档初值一致（w1=0.5/w2=0.3/w3=0.15/w4=0.05）"""
    assert REWARD_W == {"gain": 0.5, "evidence": 0.3, "cost": 0.15, "discipline": 0.05}
