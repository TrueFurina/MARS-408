# -*- coding: utf-8 -*-
"""career 分支正式测试 · 证据链结构与规则兜底（P3①）"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from agents.career_nodes import collect_evidence, _dialogue_brief


class TestCollectEvidenceFallback:
    """无 LLM（mock 返回非 JSON）时走规则兜底，结构必须完整。"""

    def test_empty_answer_structure(self):
        ev = asyncio.run(collect_evidence("test", "问题", ""))
        assert isinstance(ev, dict)
        assert "dimension_hits" in ev and "key_quotes" in ev
        assert "template_suspect" in ev and "density" in ev and "signals" in ev

    def test_short_answer_template_suspect(self):
        ev = asyncio.run(collect_evidence("test", "问题", "好"))
        assert ev["template_suspect"] is True  # 作答过短检测

    def test_long_answer_concrete_specificity(self):
        long_ans = ("我认为应该分三层处理：第一层做根因定位，第二层做方案对比，"
                    "第三层做风险评估并给出回滚预案与监控指标。") * 4
        ev = asyncio.run(collect_evidence("test", "问题", long_ans))
        assert ev["signals"]["specificity"] == "concrete"
        assert ev["template_suspect"] is False

    def test_density_bounded(self):
        ev = asyncio.run(collect_evidence("test", "问题", ""))
        assert 0.0 <= ev["density"] <= 1.0


class TestDialogueBrief:
    def test_keeps_last_n_turns(self):
        turns = [
            {"turn_index": i, "question": f"q{i}", "answer": f"a{i}"} for i in range(1, 7)
        ]
        brief = _dialogue_brief(turns, keep=2)
        assert "第6轮" in brief and "第5轮" in brief
        assert "第1轮" not in brief

    def test_empty_brief(self):
        assert _dialogue_brief([], keep=4) == "（这是第一轮，尚无历史）"
