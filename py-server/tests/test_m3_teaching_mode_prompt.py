# -*- coding: utf-8 -*-
"""M3 接线 · teaching_mode → 生成 prompt（2026-10-14）

守护三件事：
  1. 接线契约：state["policy_action"]["teaching_mode"] 注入 teacher prompt，
     且**只对 teacher 生效**（quizmaster / extension 必须逐字不变）；
  2. 关闭等价：flag 关 / 无 policy_action / 未知取值 → prompt 与接线前逐字等价；
  3. 口径修正：teaching_mode 按**生产画像契约**（weak_points）判定，
     example_first 不是死取值；且 review_intensity 口径**未被带偏**
     （它仍是旧口径，属评审强度控制面，不属本次接线范围）。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.generator_cluster import (
    TEACHING_MODE_INSTRUCTIONS,
    _build_agent_prompt,
    _teaching_mode_instruction,
)
from engines.teaching_rules import teaching_rules


PLAN = {"topic": "TCP 拥塞控制", "chapter": "4.3", "difficulty": "medium", "teacher_task": "讲解"}
PROFILE = {"learning_style": "reading", "knowledge_base": "beginner", "weak_points": "cwnd"}
DIAGNOSIS = {"recommended_focus": ["慢开始"]}
KC = "【知识库】TCP 拥塞控制是…"


def _build(agent_type="teacher", instruction=""):
    return _build_agent_prompt(agent_type, PLAN, PROFILE, KC, DIAGNOSIS, "", instruction)


# ── 1. 接线契约 ──────────────────────────────────────────────


def test_three_modes_all_mapped():
    """三方约定的三个取值都必须有指令（mappo_policy.TEACHING_MODES 同集合）。"""
    assert set(TEACHING_MODE_INSTRUCTIONS) == {"sequential", "example_first", "analogy"}


@pytest.mark.parametrize("mode", ["sequential", "example_first", "analogy"])
def test_teacher_prompt_gains_one_line(mode):
    base = _build()
    new = _build(instruction=TEACHING_MODE_INSTRUCTIONS[mode])
    assert new != base
    assert "【讲解顺序】" in new
    # 只增不减：不得改写原有任何段落
    assert base in new or all(seg in new for seg in base.split("\n\n") if seg.strip())


@pytest.mark.parametrize("agent_type", ["quizmaster", "extension"])
def test_only_teacher_affected(agent_type):
    """讲解顺序只约束讲解，题目与拓展材料必须逐字不变。"""
    assert _build(agent_type) == _build(agent_type, TEACHING_MODE_INSTRUCTIONS["analogy"])


def test_state_flow_teacher_receives_policy_action():
    """端到端：coordinator 产出的 policy_action 能被生成侧取到指令。

    时序前提：graph.py 里 coordinator → diagnostician → planner → retriever
    → generator_cluster，生成在决策之后，故 state 携带可达。
    """
    action = teaching_rules.decide_policy_action(profile={"weak_points": "a,b"})
    assert action["teaching_mode"] == "example_first"
    assert _teaching_mode_instruction(action) == TEACHING_MODE_INSTRUCTIONS["example_first"]


# ── 2. 关闭等价 / fail-open ──────────────────────────────────


@pytest.mark.parametrize("bad", [None, {}, {"teaching_mode": None}, {"teaching_mode": ""},
                                 {"teaching_mode": "brand_new_enum"}, "sequential", 123, []])
def test_fail_open_to_baseline(bad):
    """无/异常 policy_action 一律不注入 ⇒ 与接线前逐字等价。

    含字符串/数字等错类型：上游类型漂移不应让生成侧崩或静默改产物。
    """
    assert _teaching_mode_instruction(bad) == ""
    assert _build(instruction=_teaching_mode_instruction(bad)) == _build()


def test_kill_switch_restores_baseline(monkeypatch):
    """kill-switch 关闭 → 回到接线前行为（灰度回退路径必须可用）。"""
    import config as cfg_module

    cfg = cfg_module.load_config()
    monkeypatch.setitem(cfg["gomarl"], "use_teaching_mode_prompt", False)
    monkeypatch.setattr(cfg_module, "load_config", lambda: cfg, raising=False)
    assert _teaching_mode_instruction({"teaching_mode": "example_first"}) == ""


# ── 3. 口径修正（本次接线的真实阻断项）───────────────────────


def test_mode_uses_production_profile_contract():
    """生产 student_profile 只有 weak_points（字符串），没有 weak_topics。

    接线前 decide_policy_action 读 weak_topics ⇒ weak_count 恒 0
    ⇒ teaching_mode 恒 sequential ⇒ example_first 是死取值、接线也是死代码。
    """
    assert teaching_rules.decide_policy_action(profile={"weak_points": "a,b"})["teaching_mode"] == "example_first"
    assert teaching_rules.decide_policy_action(profile={"weak_points": "a"})["teaching_mode"] == "sequential"
    assert teaching_rules.decide_policy_action(profile={"weak_points": ""})["teaching_mode"] == "sequential"


def test_mode_accepts_chinese_comma_and_list():
    """weak_points 由 api/assessment.py 以 "," join 写入、:285 以"，"/"," 切分解析。"""
    assert teaching_rules.decide_policy_action(profile={"weak_points": "a，b"})["teaching_mode"] == "example_first"
    assert teaching_rules.decide_policy_action(profile={"weak_points": ["a", "b"]})["teaching_mode"] == "example_first"


def test_legacy_keys_take_precedence():
    """保留旧口径（M3 早期 weak_topics/weak_subjects）优先，不破坏既有实验脚本。"""
    assert teaching_rules.decide_policy_action(profile={"weak_topics": ["a", "b"]})["teaching_mode"] == "example_first"
    # 旧键存在（哪怕只有 1 项）时按旧口径判，不与 weak_points 叠加
    got = teaching_rules.decide_policy_action(
        profile={"weak_topics": ["a"], "weak_points": "x,y,z"}
    )["teaching_mode"]
    assert got == "sequential"


def test_review_intensity_not_shifted():
    """review_intensity 是评审强度控制面（与 ADR-011 权重灰度不同层）。

    本次只改 teaching_mode 的口径；intensity 触发条件必须保持旧口径，
    否则接线会顺带改评审行为（超出范围且无实验支撑）。
    """
    # 生产契约的 3 个薄弱点（旧口径读不到 → weak_count=0）仍应 spot
    assert teaching_rules.decide_policy_action(profile={"weak_points": "a,b,c"})["review_intensity"] == "spot"
    # 旧口径的 3 个薄弱点仍是 full
    assert teaching_rules.decide_policy_action(profile={"weak_topics": ["a", "b", "c"]})["review_intensity"] == "full"


def test_difficulty_mapping_unchanged():
    """level→档位映射不受影响（生产无 level ⇒ 恒 medium，属既有行为，非本次范围）。"""
    assert teaching_rules.decide_policy_action(profile={"level": "beginner"})["difficulty"] == "basic"
    assert teaching_rules.decide_policy_action(profile={"level": "advanced"})["difficulty"] == "advanced"
    assert teaching_rules.decide_policy_action(
        profile={"level": "beginner"}, difficulty="advanced")["difficulty"] == "advanced"