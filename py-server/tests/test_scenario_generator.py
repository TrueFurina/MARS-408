# -*- coding: utf-8 -*-
# ============================================================
# scenario_generator · 场景自动生成器单测（对标 HireVue Builder）
#
# 立论：
#   1. 模板兜底是静态方法论素材，结构必须对齐 career_scenarios.json 的 scenario；
#   2. LLM 路径失败/非法必须完整回退模板（无 LLM 环境闭环不崩、离线可复现）；
#   3. 权重与 BARS 一律规整：非法维度剔除、缺失三档的锚点丢弃，杜绝伪造量表。
#
# 运行：python -m pytest tests/test_scenario_generator.py -q
# ============================================================

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from agents import scenario_generator as sg
from agents.career_state import DIMENSIONS, SCENARIO_TYPES

pytestmark = pytest.mark.p0_regression

# scenario 必有的结构字段（对齐黄金样本 career_scenarios.json 的 scenario 结构）
_REQUIRED_FIELDS = [
    "id", "type", "subtype", "type_label", "subtype_label", "title",
    "difficulty_default", "setting", "student_role", "interviewer_role",
    "opening_question", "probe_tree", "dimension_weights", "focus_points",
    "bars_anchor", "rubric_version", "generated", "job_direction",
]


class _RaisingLLM:
    """LLM 全通道宕机桩：text_completion 抛异常，验证完整回退模板。"""

    def __init__(self, *args, **kwargs):
        pass

    async def text_completion(self, *args, **kwargs):
        raise RuntimeError("simulated LLM outage")

    async def chat(self, *args, **kwargs):
        raise RuntimeError("simulated LLM outage")


@pytest.fixture()
def llm_down(monkeypatch):
    monkeypatch.setattr("db.llm_provider.LLMProvider", _RaisingLLM)


def test_list_job_directions_has_five():
    dirs = sg.list_job_directions()
    keys = {d["key"] for d in dirs}
    assert keys == {"frontend", "backend", "algorithm", "product", "ops"}
    for d in dirs:
        assert d["label"] and d["default_scenario_type"] in SCENARIO_TYPES


def test_template_builds_complete_scenario_for_every_direction():
    """每个岗位方向的模板兜底都必须产出结构完整、字段非空的 scenario。"""
    for key in sg.JOB_DIRECTION_LABELS:
        sc = sg.build_scenario_from_template(key, "", "medium")
        for f in _REQUIRED_FIELDS:
            assert f in sc, f"{key} 缺字段 {f}"
        assert sc["type"] in SCENARIO_TYPES
        assert sc["id"].startswith(f"gen_{key}_")
        assert sc["title"] and sc["setting"] and sc["opening_question"]
        assert len(sc["probe_tree"]) >= 3
        assert sc["focus_points"]
        assert sc["bars_anchor"]
        assert sc["rubric_version"] == sg.RUBRIC_VERSION
        assert sc["generated"] is True
        assert sc["job_direction"] == key


def test_build_unknown_direction_raises():
    with pytest.raises(ValueError):
        sg.build_scenario_from_template("nonexistent", "", "medium")


def test_norm_weights_drops_invalid_and_fills_default():
    w = sg._norm_weights({"expression": 0.5, "bogus": 0.5})
    # 六维全在（bogus 剔除，缺省补默认）
    assert set(w) == set(DIMENSIONS)
    assert "bogus" not in w
    assert w["expression"] == 0.5
    assert w["stress"] == sg._DEFAULT_WEIGHTS["stress"]
    # 完全缺失时全部落到默认
    w2 = sg._norm_weights(None)
    assert w2 == sg._DEFAULT_WEIGHTS


def test_norm_bars_anchor_drops_invalid_dim_and_sparse_anchor():
    bars = sg._norm_bars_anchor({
        "expression": {"1": "低", "3": "中", "5": "高"},
        "collab": {"1": "低", "3": "中", "5": "高"},
        "bogus": {"1": "x", "3": "y", "5": "z"},          # 非法维度 → 剔除
        "stress": {"1": "只有一档"},                       # 少于两档 → 丢弃
    })
    assert set(bars) == {"expression", "collab"}
    assert bars["expression"] == {"1": "低", "3": "中", "5": "高"}


def test_generate_scenario_falls_back_to_template_when_llm_down(llm_down):
    """LLM 宕机时 generate_scenario 必须回退模板，且结构完整、标记 generated。"""
    import asyncio
    sc = asyncio.run(sg.generate_scenario("backend", "", "hard"))
    for f in _REQUIRED_FIELDS:
        assert f in sc
    assert sc["job_direction"] == "backend"
    assert sc["type"] == "incident"          # backend 默认情景类型
    assert sc["difficulty_default"] == "hard"
    assert sc["generated"] is True


def test_generate_scenario_invalid_type_falls_back_to_default(llm_down):
    """scenario_type 非法时回退到岗位默认情景类型。"""
    import asyncio
    sc = asyncio.run(sg.generate_scenario("algorithm", "not_a_type", "medium"))
    assert sc["type"] == "defense"           # algorithm 默认 defense


def test_generate_unknown_direction_raises():
    import asyncio
    with pytest.raises(ValueError):
        asyncio.run(sg.generate_scenario("nope", "", "medium"))
