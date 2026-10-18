# -*- coding: utf-8 -*-
"""career 分支正式测试 · 动态取证追问 + BEI 分层追问 + 报告 360°（2026-10-18 竞品借鉴落地）

覆盖三块（不依赖 LLM，纯函数 + 结构守卫，稳定可复现）：
  ① 动态取证式追问：_derive_evidence_gap 三类缺口 + collect_evidence 输出 evidence_gap
     + _format_evidence_gap 注入追问提示；
  ② BEI 三层追问：ADVERSARY_SYSTEM 三模式含行为事件访谈阶梯（结构守卫）；
  ③ 报告 360°：_derive_risk_flags 风险派生 + _normalize_assessment/_rule_based_assessment
     补 highlights/risk_flags（结构守卫）。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.career_nodes import (
    _derive_evidence_gap, _format_evidence_gap, _derive_risk_flags,
    _normalize_assessment, _rule_based_assessment, collect_evidence,
)
from agents.career_state import DIMENSIONS
from prompts_career import (
    ADVERSARY_SYSTEM, EVIDENCE_COLLECT_SYSTEM, CAREER_ASSESS_SYSTEM, ADVERSARY_USER_TMPL,
)


SCRIPT = {"dimension_weights": {d: 1.0 for d in DIMENSIONS}}


class TestDeriveEvidenceGap:
    """证据缺口规则兜底：三类缺口（vague / no_quantification / none）。"""

    def test_template_suspect_vague(self):
        gap = _derive_evidence_gap(
            {"template_suspect": True, "signals": {"specificity": "concrete"}, "density": 0.8},
            "x" * 50,
        )
        assert gap["gap_type"] == "vague"

    def test_empty_answer_vague(self):
        gap = _derive_evidence_gap(
            {"template_suspect": False, "signals": {"specificity": "empty"}, "density": 0.1},
            "",
        )
        assert gap["gap_type"] == "vague"

    def test_general_no_quantification(self):
        gap = _derive_evidence_gap(
            {"template_suspect": False, "signals": {"specificity": "general"}, "density": 0.3},
            "x" * 50,
        )
        assert gap["gap_type"] == "no_quantification"

    def test_low_density_no_quantification(self):
        gap = _derive_evidence_gap(
            {"template_suspect": False, "signals": {"specificity": "concrete"}, "density": 0.2},
            "x" * 50,
        )
        assert gap["gap_type"] == "no_quantification"

    def test_concrete_none(self):
        gap = _derive_evidence_gap(
            {"template_suspect": False, "signals": {"specificity": "concrete"}, "density": 0.8},
            "x" * 50,
        )
        assert gap["gap_type"] == "none"


class TestFormatEvidenceGap:
    def test_none_gap(self):
        out = _format_evidence_gap({"evidence_gap": {"gap_type": "none", "description": "", "suggested_probe": ""}})
        assert out == "（上轮回答无明确证据缺口）"

    def test_missing_gap(self):
        assert _format_evidence_gap({}) == "（上轮回答无明确证据缺口）"

    def test_gap_with_probe(self):
        gap = {"evidence_gap": {"gap_type": "vague", "description": "回答空泛", "suggested_probe": "追具体数字"}}
        out = _format_evidence_gap(gap)
        assert "回答空泛" in out and "追具体数字" in out


class TestCollectEvidenceGap:
    def test_fallback_has_gap(self):
        ev = asyncio.run(collect_evidence("test", "问题", ""))
        assert "evidence_gap" in ev
        assert ev["evidence_gap"]["gap_type"] in ("vague", "no_quantification", "role_ambiguous", "none")


class TestDeriveRiskFlags:
    """风险预警派生：只据结构性事实（证据不足 / 低置信 / 低分 / 套模板），不做能力定性。"""

    def test_insufficient_dimension(self):
        assessment = {"dimensions": {"expression": {"score": None, "confidence": 0.0}}, "template_detected": False}
        flags = _derive_risk_flags(assessment)
        assert any("证据不足" in f for f in flags)

    def test_low_confidence(self):
        assessment = {"dimensions": {"expression": {"score": 3.0, "confidence": 0.3}}, "template_detected": False}
        flags = _derive_risk_flags(assessment)
        assert any("置信度偏低" in f for f in flags)

    def test_low_score(self):
        assessment = {"dimensions": {"expression": {"score": 1.5, "confidence": 0.8}}, "template_detected": False}
        flags = _derive_risk_flags(assessment)
        assert any("得分偏低" in f for f in flags)

    def test_template_flag(self):
        assessment = {"dimensions": {"expression": {"score": 4.0, "confidence": 0.9}}, "template_detected": True}
        flags = _derive_risk_flags(assessment)
        assert any("套模板" in f for f in flags)

    def test_no_flags_when_healthy(self):
        assessment = {"dimensions": {"expression": {"score": 4.0, "confidence": 0.9}}, "template_detected": False}
        assert _derive_risk_flags(assessment) == []


class TestNormalizeAssessment360:
    def test_highlights_risk_flags_filled(self):
        out = _normalize_assessment({"dimensions": {}}, SCRIPT)
        assert out.get("highlights") == []
        assert isinstance(out.get("risk_flags"), list)  # insufficient → 规则派生风险

    def test_risk_flags_llm_priority(self):
        data = {"dimensions": {}, "risk_flags": ["自定义风险"]}
        out = _normalize_assessment(data, SCRIPT)
        assert out["risk_flags"] == ["自定义风险"]  # LLM 输出优先，不被规则覆盖


class TestRuleBasedAssessment360:
    def test_has_highlights_risk_flags(self):
        out = _rule_based_assessment([], SCRIPT)
        assert "highlights" in out and out["highlights"] == []
        assert isinstance(out.get("risk_flags"), list)


class TestPromptStructure:
    """结构守卫：三块改动的 prompt 关键词不漂移（防回归）。"""

    def test_adversary_prompts_contain_bei(self):
        for mode in ("normal", "escalating", "catfish"):
            assert "行为事件访谈" in ADVERSARY_SYSTEM[mode]

    def test_adversary_user_tmpl_has_evidence_gap(self):
        assert "{evidence_gap}" in ADVERSARY_USER_TMPL

    def test_evidence_collect_has_gap(self):
        assert "evidence_gap" in EVIDENCE_COLLECT_SYSTEM

    def test_assess_has_360_fields(self):
        assert "highlights" in CAREER_ASSESS_SYSTEM
        assert "risk_flags" in CAREER_ASSESS_SYSTEM
