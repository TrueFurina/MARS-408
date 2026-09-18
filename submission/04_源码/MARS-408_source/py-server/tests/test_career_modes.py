# -*- coding: utf-8 -*-
"""career 分支正式测试 · 对抗模式状态机（P3①）"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from agents.career_nodes import decide_adversary_mode
from agents.career_state import CATFISH_MAX_CONTINUE


def _turn(template=False, density=0.5, idx=1):
    return {"turn_index": idx, "evidence": {"template_suspect": template, "density": density}}


class TestDecideModeBasics:
    def test_empty_turns_normal(self):
        assert decide_adversary_mode([], "normal", 0) == ("normal", False, 0)

    def test_single_turn_no_trigger(self):
        # n < 2 不触发（避免开场误判）
        assert decide_adversary_mode([_turn(template=True)], "normal", 0)[0] == "normal"

    def test_normal_no_trigger(self):
        turns = [_turn(density=0.8, idx=1), _turn(density=0.8, idx=2)]
        assert decide_adversary_mode(turns, "normal", 0) == ("normal", False, 0)


class TestEscalating:
    def test_low_density_triggers_escalating(self):
        turns = [_turn(density=0.3, idx=1), _turn(density=0.2, idx=2)]
        mode, trig, cnt = decide_adversary_mode(turns, "normal", 0)
        assert mode == "escalating" and trig is True and cnt == 1

    def test_escalating_continues_while_condition(self):
        turns = [_turn(density=0.3, idx=3), _turn(density=0.2, idx=4)]
        mode, trig, cnt = decide_adversary_mode(turns, "escalating", 1)
        assert mode == "escalating" and trig is False and cnt == 2

    def test_escalating_releases_when_recovered(self):
        turns = [_turn(density=0.8, idx=3), _turn(density=0.8, idx=4)]
        mode, trig, cnt = decide_adversary_mode(turns, "escalating", 1)
        assert mode == "normal" and cnt == 0


class TestCatfish:
    def test_double_template_triggers_catfish(self):
        turns = [_turn(template=True, idx=1), _turn(template=True, idx=2)]
        mode, trig, cnt = decide_adversary_mode(turns, "normal", 0)
        assert mode == "catfish" and trig is True and cnt == 1

    def test_catfish_max_continue_back_to_normal(self):
        turns = [_turn(density=0.5, idx=3), _turn(density=0.5, idx=4)]
        # 已连压满 CATFISH_MAX_CONTINUE → 必须回 normal
        mode, trig, cnt = decide_adversary_mode(turns, "catfish", CATFISH_MAX_CONTINUE)
        assert mode == "normal" and cnt == 0

    def test_catfish_never_exceeds_limit(self):
        # 连压计数被硬约束在 CATFISH_MAX_CONTINUE 内，防鲶鱼滥用
        turns = [_turn(template=True, idx=3), _turn(template=True, idx=4)]
        mode, trig, cnt = decide_adversary_mode(turns, "catfish", CATFISH_MAX_CONTINUE - 1)
        assert cnt <= CATFISH_MAX_CONTINUE
