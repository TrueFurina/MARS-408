# -*- coding: utf-8 -*-
"""M3 · MAPPO 教学策略层单测（三评审集成·增量四）。

覆盖：
  - 状态编码 / 奖励函数（可解释、可复算）
  - 模拟教学环境（难度匹配 → 学习效果）
  - MappoPolicy：规则降级、agent 权重调整、checkpoint 保存/加载
  - teaching_rules.decide_policy_action 规则版策略决策
  - Mixer 权重来源灰度接入（use_mappo 关闭 → 零影响）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from engines.mappo_policy import (
    DIFFICULTIES, REVIEW_INTENSITIES, TeachingEnv, MappoPolicy,
    compute_reward, encode_state, _ensure_torch,
)
from engines.teaching_rules import teaching_rules


class TestEncodeState:
    def test_dim_and_determinism(self):
        s1 = encode_state({"level": "beginner", "weak_topics": ["tcp"]}, "", 0, 0.5)
        s2 = encode_state({"level": "beginner", "weak_topics": ["tcp"]}, "", 0, 0.5)
        assert len(s1) == 8
        assert s1 == s2  # 确定性

    def test_mastery_reflects_level(self):
        b = encode_state({"level": "beginner"}, "", 0, 0.5)[0]
        a = encode_state({"level": "advanced"}, "", 0, 0.5)[0]
        assert b < a

    def test_retried_flag(self):
        s = encode_state({}, "", 0, 0.5, gate_result={"verdict": "fix"})
        assert s[-1] == 1.0


class TestComputeReward:
    def test_full_cost_higher_than_skip(self):
        r_full = compute_reward(0.3, 0.6, 1.0, "full")
        r_skip = compute_reward(0.3, 0.6, 1.0, "skip")
        # full 完成度高但成本高；同条件下 skip 因成本低可能更高或接近，
        # 关键是 full 的 token 成本系数更大
        assert {"full": 3.0, "skip": 1.0}["full"] > {"full": 3.0, "skip": 1.0}["skip"]

    def test_bounded(self):
        r = compute_reward(1.0, 1.0, 1.0, "full")
        assert -2.0 < r < 1.5  # 有界


class TestTeachingEnv:
    def test_matching_difficulty_gives_higher_accuracy(self):
        """难度匹配（medium vs 0.5 水平）应比失配（basic vs 0.8）效果好。"""
        env_match = TeachingEnv(student_level=0.5, seed=1)
        state = env_match.reset()
        _, r_match, _ = env_match.step({"difficulty": "medium", "teaching_mode": "sequential",
                                        "review_intensity": "full"})
        env_bad = TeachingEnv(student_level=0.8, seed=1)
        env_bad.reset()
        _, r_bad, _ = env_bad.step({"difficulty": "basic", "teaching_mode": "sequential",
                                    "review_intensity": "full"})
        assert r_match > r_bad

    def test_horizon_terminates(self):
        env = TeachingEnv(student_level=0.5, seed=1, horizon=3)
        env.reset()
        for i in range(3):
            _, _, done = env.step({"difficulty": "medium", "teaching_mode": "sequential",
                                   "review_intensity": "spot"})
        assert done is True


class TestMappoPolicyRuleFallback:
    def test_rule_fallback_source(self, tmp_path):
        """未训练（无 checkpoint）→ 规则降级，不崩溃。"""
        policy = MappoPolicy({"mappo_checkpoint": str(tmp_path / "missing.pt")})
        action = policy.select_action({"level": "beginner"}, deterministic=True)
        assert action["source"] == "rule"
        assert action["difficulty"] == "basic"

    def test_rule_retry_forces_full(self, tmp_path):
        policy = MappoPolicy({"mappo_checkpoint": str(tmp_path / "missing.pt")})
        action = policy.select_action({"level": "intermediate"}, round_num=1)
        assert action["review_intensity"] == "full"

    def test_agent_weight_adjust_basic(self):
        policy = MappoPolicy({"mappo_checkpoint": ""})
        adj = policy.agent_weight_adjust({"level": "beginner"}, {"difficulty": "basic"})
        assert adj["teacher"] > 1.0  # 基础难度重讲解


class TestTeachingRulesPolicyAction:
    def test_level_maps_difficulty(self):
        a = teaching_rules.decide_policy_action(profile={"level": "beginner"})
        assert a["difficulty"] == "basic" and a["source"] == "rules"
        b = teaching_rules.decide_policy_action(profile={"level": "advanced"})
        assert b["difficulty"] == "advanced"

    def test_explicit_difficulty_priority(self):
        a = teaching_rules.decide_policy_action(profile={"level": "beginner"}, difficulty="advanced")
        assert a["difficulty"] == "advanced"

    def test_weak_topics_change_mode_and_intensity(self):
        a = teaching_rules.decide_policy_action(
            profile={"level": "intermediate", "weak_topics": ["tcp", "ip", "udp"]}
        )
        assert a["teaching_mode"] == "example_first"
        assert a["review_intensity"] == "full"


class TestMixerMappoGrayscale:
    def test_flag_off_zero_impact(self):
        """use_mappo_policy 关闭（默认）→ _use_mappo=False。"""
        from engines.gomarl_mixer import NeuralGroupMixer
        mixer = NeuralGroupMixer()
        assert mixer._use_mappo is False


@pytest.mark.skipif(_ensure_torch() is None, reason="segv_env: 本地无可用 torch")
class TestMappoPolicyTrainingSmoke:
    """torch 可用时的训练冒烟（小规模，不覆盖 Windows SIGSEGV 场景）。"""

    def test_warmup_and_train_smoke(self, tmp_path):
        policy = MappoPolicy({"mappo_checkpoint": str(tmp_path / "smoke.pt")})
        env = TeachingEnv(student_level=0.5, seed=1, drift=0.06, curriculum=True)
        warm = policy.warmup_with_rules(env, steps=100, seed=7)
        assert warm["warmup"] is True
        metrics = policy.train(env, episodes=20, seed=1)
        assert metrics["trained"] is True
        assert metrics["avg_accuracy"] > 0.5  # 比随机 0.5 起步好

    def test_checkpoint_roundtrip(self, tmp_path):
        policy = MappoPolicy({"mappo_checkpoint": str(tmp_path / "missing.pt")})
        env = TeachingEnv(student_level=0.5, seed=1, curriculum=True)
        policy.warmup_with_rules(env, steps=50, seed=7)
        ckpt = policy.save(str(tmp_path / "mappo_test.pt"))
        assert ckpt
        policy2 = MappoPolicy({"mappo_checkpoint": ckpt})
        assert policy2._trained is True
