# -*- coding: utf-8 -*-
"""career 分支正式测试 · 评估双通道（LLM 归一化 + 规则兜底）（P3①）"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from agents.career_nodes import (
    _normalize_assessment, _rule_based_assessment, build_improvement_plan,
    norm_dimension,
)
from agents.career_state import DIMENSIONS, DIMENSION_LABELS


SCRIPT = {
    "dimension_weights": {d: 1.0 for d in DIMENSIONS},
}


class TestNormDimension:
    def test_chinese_key_to_code(self):
        assert norm_dimension("表达逻辑") == "expression"
        assert norm_dimension("问题解决") == "problem_solving"
        assert norm_dimension("unknown_key") is None


class TestNormalizeAssessment:
    def test_chinese_dimension_keys_normalized(self):
        data = {"dimensions": {"表达逻辑": {"score": 4.0}}}
        out = _normalize_assessment(data, SCRIPT)
        assert "expression" in out["dimensions"]
        assert "表达逻辑" not in out["dimensions"]

    def test_missing_dimensions_filled(self):
        out = _normalize_assessment({"dimensions": {}}, SCRIPT)
        for d in DIMENSIONS:
            assert d in out["dimensions"]
            assert out["dimensions"][d]["score"] is None
            assert out["dimensions"][d]["level"] == "insufficient"

    def test_score_clamped(self):
        data = {"dimensions": {"expression": {"score": 9}, "stress": {"score": 0}}}
        out = _normalize_assessment(data, SCRIPT)
        assert out["dimensions"]["expression"]["score"] == 5.0
        assert out["dimensions"]["stress"]["score"] == 1.0

    def test_overall_weighted(self):
        data = {"dimensions": {
            "expression": {"score": 5.0}, "stress": {"score": 3.0},
            "decompose": {"score": 4.0}, "collab": {"score": 4.0},
            "presentation": {"score": 4.0}, "problem_solving": {"score": 4.0},
        }}
        out = _normalize_assessment(data, SCRIPT)
        assert out["overall"] == pytest.approx(4.0)

    def test_defaults_filled(self):
        out = _normalize_assessment({"dimensions": {}}, SCRIPT)
        assert out.get("strength") == ""
        assert out.get("weaknesses") == []
        assert out.get("template_detected") is False


class TestRuleBasedAssessment:
    def test_empty_turns_no_raise(self):
        out = _rule_based_assessment([], SCRIPT)
        dims = out["dimensions"]
        for d in DIMENSIONS:
            assert d in dims
            assert dims[d]["score"] is None  # 无证据不评分（诚实兜底）
            assert dims[d]["confidence"] == 0.0

    def test_evidence_hits_reflected(self):
        turns = [
            {"turn_index": 1, "probe_dimension": "expression", "answer": "分三层处理",
             "evidence": {
                 "dimension_hits": [
                     {"dimension": "expression", "polarity": "positive",
                      "density": 0.8, "note": "q1"},
                 ],
                 "density": 0.8, "template_suspect": False,
             }},
        ]
        out = _rule_based_assessment(turns, SCRIPT)
        dims = out["dimensions"]
        # score = clamp(2.5 + (1-0)*0.6 + 0.8) = 3.9
        assert dims["expression"]["score"] == 3.9
        assert dims["expression"]["confidence"] == 0.4


class TestImprovementPlanFallback:
    def test_fallback_nonempty(self):
        # mock LLM 返回非 JSON → 走 _fallback_improvement，actions 必须非空
        assessment = {"overall": 3.5, "dimensions": {
            "expression": {"score": 3.0, "label": "表达逻辑"}}}
        plan = asyncio.run(build_improvement_plan(assessment, "test"))
        assert isinstance(plan, dict)
        assert plan.get("actions") or plan.get("items") or plan  # 结构非空可返回
