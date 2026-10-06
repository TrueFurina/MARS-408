# ============================================================
# career 规则基线有效性检查门（CTO 派单一 / §6.1）
#
# 背景（CTO 深度验收 2026-09-14 派单一）：
#   旧默认证据密度 0.5 使规则判据 `density < 0.35` 恒不满足 → 规则死锁 normal、
#   escalating/catfish 永不触发（"在几乎失效的基线上取得胜利"，答辩一问即穿）。
# 本文件把"实验基线有效性检查门"固化为回归测试，锁死三条：
#   a) 基线会动   → 规则版在目标特征空间触发率 > 0（≥10%）
#   b) 基线有效   → 已知简单场景产生预期行为（低密度→加压、高密度→normal）
#   c) 随机性可控 → 同 seed 两次运行逐位一致
# 运行：python -m pytest tests/test_career_policy_baseline.py -q
# ============================================================

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from engines.career_policy import (
    CAREER_ACTIONS,
    EVIDENCE_DENSITY_DEFAULT,
    CareerAdversaryEnv,
    _rule_action_idx,
    career_state_features,
)
from agents.career_nodes import decide_adversary_mode


# ────────────────────────────────────────────────────────────
# a) 基线会动：规则版在合成 env 的对抗模式触发率 > 0（≥10%）
# ────────────────────────────────────────────────────────────

def test_env_rule_triggers_adversarial_modes():
    """合成 env 跑 100 局（seed=7）：escalating+catfish 合计触发率 ≥ 10%（不再 100% normal）。"""
    env = CareerAdversaryEnv(seed=7, horizon=8)
    dist = collections.Counter()
    for _ep in range(100):
        f = env.reset()
        done = False
        while not done:
            a = _rule_action_idx(f)
            dist[CAREER_ACTIONS[a]] += 1
            f, _r, done = env.step(a)
    total = sum(dist.values())
    adversarial = dist["escalating"] + dist["catfish"]
    assert total > 0
    assert adversarial / total >= 0.10, dict(dist)


def test_env_rule_triggers_catfish_across_seeds():
    """多 seed 稳健：至少 2 个 seed 触发过 catfish（防单 seed 巧合）。"""
    hits = 0
    for seed in (1, 42, 2024):
        env = CareerAdversaryEnv(seed=seed, horizon=8)
        dist = collections.Counter()
        for _ep in range(20):
            f = env.reset()
            done = False
            while not done:
                a = _rule_action_idx(f)
                dist[CAREER_ACTIONS[a]] += 1
                f, _r, done = env.step(a)
        if dist["catfish"] > 0:
            hits += 1
    assert hits >= 2


# ────────────────────────────────────────────────────────────
# 无证据 / 低信息轮不 deadlock（派单一核心验收：n≥2 后能触发）
# ────────────────────────────────────────────────────────────

def test_career_state_features_no_evidence_not_deadlock():
    """career_state_features 路径：无证据 turns 的密度取默认值，且 n≥2 后必触发对抗。"""
    for turns in ([{"evidence": {}}, {"evidence": {}}], [{"evidence": {}}] * 8):
        feats = career_state_features(turns)
        assert feats[1] == pytest.approx(EVIDENCE_DENSITY_DEFAULT, abs=1e-9)
        assert _rule_action_idx(feats) != 0, f"deadlock(normal): feats={feats}"


def test_career_state_features_empty_turns_not_normal():
    """空 turns（会话起始）在 career_policy 规则下不恒 normal。"""
    feats = career_state_features([])
    assert feats[1] == pytest.approx(EVIDENCE_DENSITY_DEFAULT, abs=1e-9)
    assert _rule_action_idx(feats) in (1, 2)


def test_production_rule_no_evidence_not_deadlock():
    """生产规则 decide_adversary_mode：n≥2 且无证据 → 触发（旧实现死锁 normal）。"""
    # 保留既有语义：n==0 / n<2 不触发（避免开场误判）
    assert decide_adversary_mode([], "normal", 0) == ("normal", False, 0)
    assert decide_adversary_mode([{"evidence": {}}], "normal", 0)[0] == "normal"
    # 修复点：n≥2 且无证据 → 必须触发
    for n in (2, 8):
        mode, trig, _ = decide_adversary_mode([{"evidence": {}}] * n, "normal", 0)
        assert mode in ("escalating", "catfish") and trig is True, (n, mode, trig)


# ────────────────────────────────────────────────────────────
# b) 基线有效：已知简单场景产生预期行为
# ────────────────────────────────────────────────────────────

def test_baseline_low_density_escalates():
    turns = [{"evidence": {"density": 0.1}}, {"evidence": {"density": 0.1}}]
    assert _rule_action_idx(career_state_features(turns)) in (1, 2)


def test_baseline_high_density_normal():
    turns = [{"evidence": {"density": 0.9}}, {"evidence": {"density": 0.9}}]
    assert _rule_action_idx(career_state_features(turns)) == 0


# ────────────────────────────────────────────────────────────
# 状态退化修复：无 six_scores 时 dimension_variance 不再恒 0.5
# ────────────────────────────────────────────────────────────

def test_dimension_variance_not_constant_without_six_scores():
    """无六维评估时，维度方差随最近轮密度离散度变化（旧实现恒 0.5 → 状态退化）。"""
    spread = career_state_features(
        [{"evidence": {"density": 0.1}}, {"evidence": {"density": 0.9}}])
    flat = career_state_features(
        [{"evidence": {"density": 0.5}}, {"evidence": {"density": 0.5}}])
    assert spread[6] > 0.0
    assert spread[6] != flat[6]


# ────────────────────────────────────────────────────────────
# c) 随机性可控：同 seed 两次运行逐位一致
# ────────────────────────────────────────────────────────────

def test_seed_reproducible_features_and_rule():
    e1 = CareerAdversaryEnv(seed=3, horizon=8)
    e2 = CareerAdversaryEnv(seed=3, horizon=8)
    f1, f2 = e1.reset(), e2.reset()
    for _ in range(8):
        assert f1 == f2
        a1, a2 = _rule_action_idx(f1), _rule_action_idx(f2)
        assert a1 == a2
        f1, _r1, d1 = e1.step(a1)
        f2, _r2, d2 = e2.step(a2)
        assert d1 == d2
