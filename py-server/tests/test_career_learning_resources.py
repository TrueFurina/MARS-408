# -*- coding: utf-8 -*-
# ============================================================
# career_nodes · 学习资源挂载（⑥ 学-练-战-验闭环的「学」环节）单测
#
# 立论：
#   1. improvement_plan 的 learning_resources 针对最弱 1-2 维度给方法论/知识点卡；
#   2. LLM 输出缺失/非法时规则兜底（静态通用方法论，不编造）；
#   3. 规则兜底与 LLM 输出同构，离线可复现。
#
# 运行：python -m pytest tests/test_career_learning_resources.py -q
# ============================================================

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from agents.career_nodes import (
    _derive_learning_resources, _fallback_improvement, build_improvement_plan,
)

pytestmark = pytest.mark.p0_regression


def test_derive_learning_resources_targets_weakest_two():
    assessment = {"dimensions": {
        "collab": {"score": 2.0},
        "expression": {"score": 3.0},
        "stress": {"score": 4.0},
        "decompose": {"score": None},
    }}
    lr = _derive_learning_resources(assessment)
    # 最弱两维：collab(2.0)、expression(3.0)，按分数升序
    assert [r["dimension"] for r in lr] == ["collab", "expression"]
    for r in lr:
        assert r["title"] and r["points"] and len(r["points"]) >= 3


def test_derive_learning_resources_falls_back_to_expression_when_no_score():
    lr = _derive_learning_resources({"dimensions": {"collab": {"score": None}}})
    assert lr and lr[0]["dimension"] == "expression"


def test_fallback_improvement_includes_learning_resources():
    assessment = {"dimensions": {
        "collab": {"score": 2.0},
        "expression": {"score": 3.0},
        "stress": {"score": 4.0},
    }}
    plan = _fallback_improvement(assessment)
    assert "learning_resources" in plan
    # 资源维度与 priority_dimensions 同源（都指向最弱维度）
    assert [r["dimension"] for r in plan["learning_resources"]] == plan["priority_dimensions"]
    for r in plan["learning_resources"]:
        assert r["title"] and r["points"]


class _LLMNoResources:
    """返回带 actions 但**无 learning_resources** 的 JSON，验证规则兜底补卡。"""

    def __init__(self, *args, **kwargs):
        pass

    async def text_completion(self, *args, **kwargs):
        return json.dumps({
            "priority_dimensions": ["collab"],
            "actions": [{"dimension": "collab", "do": "先肯定后建议", "frequency": "每周3次"}],
            "next_scenario": "review",
            "encouragement": "加油",
        })


def test_build_improvement_plan_fills_learning_resources_when_llm_omits(monkeypatch):
    monkeypatch.setattr("db.llm_provider.LLMProvider", _LLMNoResources)
    assessment = {"dimensions": {"collab": {"score": 2.0}, "expression": {"score": 3.0}}}
    plan = asyncio.run(build_improvement_plan(assessment, "需求评审质询"))
    assert "learning_resources" in plan
    assert plan["learning_resources"]  # 兜底补上，非空
    # 兜底卡针对最弱维度 collab
    assert plan["learning_resources"][0]["dimension"] == "collab"
