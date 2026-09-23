# -*- coding: utf-8 -*-
"""M4 · MARL DQN 家族单测（对比研究底座）。

覆盖：
  - MultiAgentTeachingEnv 多智能体适配（3 Agent 联合动作 ↔ TeachingEnv）
  - IQL / VDN / QMIX 训练冒烟 + 评估可运行
  - checkpoint 保存/加载往返
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from engines.marl_dqn import (
    _ensure_torch, MultiAgentTeachingEnv, IQLearner, VDNLearner, QMIXLearner,
    train_value_learner, AGENT_NAMES, AGENT_ACTION_SIZES,
)


class TestMultiAgentTeachingEnv:
    def test_reset_state_dim(self):
        env = MultiAgentTeachingEnv(student_level=0.5, seed=1)
        s = env.reset()
        assert len(s) == 8

    def test_step_maps_actions(self):
        env = MultiAgentTeachingEnv(student_level=0.5, seed=1, horizon=2)
        s = env.reset()
        actions = {0: 0, 1: 0, 2: 0}  # basic / sequential / full
        s2, r, done = env.step(actions)
        assert isinstance(r, float)
        assert env.env.step_count == 1

    def test_action_sizes_match_names(self):
        assert len(AGENT_NAMES) == 3
        assert AGENT_ACTION_SIZES == [4, 3, 3]


@pytest.mark.skipif(_ensure_torch() is None, reason="segv_env: 本地无可用 torch")
class TestDQNFamilySmoke:
    """DQN 家族训练/评估冒烟（小规模，Windows SIGSEGV 场景不覆盖）。"""

    @pytest.mark.parametrize("cls", [IQLearner, VDNLearner, QMIXLearner])
    def test_train_and_eval(self, cls):
        learner = cls(seed=1)
        env = MultiAgentTeachingEnv(student_level=0.5, seed=1, drift=0.06, curriculum=True)
        m = train_value_learner(learner, env, episodes=50, seed=1)
        assert m["trained"] is True
        assert 0.0 < m["avg_reward"] < 2.5  # 有界且为正
        # 评估可运行
        ev = MultiAgentTeachingEnv(student_level=0.5, seed=1, drift=0.06)
        s = ev.reset()
        done = False
        while not done:
            a = learner.select_actions(s, eval_mode=True)
            s, r, done = ev.step(a)

    def test_checkpoint_roundtrip(self, tmp_path):
        learner = QMIXLearner(seed=1)
        env = MultiAgentTeachingEnv(student_level=0.5, seed=1, curriculum=True)
        train_value_learner(learner, env, episodes=30, seed=1)
        ckpt = learner.save(str(tmp_path / "qmix_test.pt"))
        assert ckpt
        learner2 = QMIXLearner(seed=2)
        assert learner2.load(ckpt) is True
