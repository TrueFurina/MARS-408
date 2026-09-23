# -*- coding: utf-8 -*-
"""M2 · 评审门禁单测（三评审集成·增量二/三）。

覆盖：
  - critic 结构化解析（_parse_critic_report）：valid 标记 / 无证据批评 / 非法 JSON 降级
  - GOMARL 证据门禁（evaluate critic_issues 参数）：无证据不触发重生成、
    带证据触发重生成、无效批评过滤追溯、向后兼容、manual_review 字段完整性。
"""
import asyncio


from agents.critic import _parse_critic_report
from engines.gomarl import GOMARLConsensus, AgentResult, QualityScore


# ── critic 结构化解析 ──

class TestParseCriticReport:
    def test_mixed_issues_valid_flag(self):
        report = (
            '{"verdict": "flagged", "issues": ['
            '{"point": "三次握手顺序写反", "evidence": "RFC 793: SYN→SYN+ACK→ACK", "suggestion": "改正"},'
            '{"point": "感觉讲得不好", "evidence": null, "suggestion": "重写"},'
            '{"point": "太长了", "evidence": "", "suggestion": "精简"}]}'
        )
        parsed = _parse_critic_report(report)
        assert parsed["verdict"] == "flagged"
        assert len(parsed["issues"]) == 3
        valid = [i for i in parsed["issues"] if i.get("valid")]
        invalid = [i for i in parsed["issues"] if not i.get("valid")]
        assert len(valid) == 1 and valid[0]["point"] == "三次握手顺序写反"
        assert len(invalid) == 2

    def test_all_no_evidence_invalid(self):
        report = '{"verdict": "regenerate", "issues": [{"point": "就是觉得不对", "evidence": null}]}'
        parsed = _parse_critic_report(report)
        assert parsed["verdict"] == "regenerate"
        assert parsed["issues"][0]["valid"] is False

    def test_passed_empty_issues(self):
        parsed = _parse_critic_report('{"verdict": "passed", "issues": []}')
        assert parsed["verdict"] == "passed"
        assert parsed["issues"] == []

    def test_invalid_json_fallback_empty(self):
        """非法 JSON → 降级空（fail-open，调用方走关键词兜底）"""
        parsed = _parse_critic_report("这不是JSON，❌ 存在错误")
        assert parsed["verdict"] == ""
        assert parsed["issues"] == []

    def test_unknown_verdict_emptied(self):
        parsed = _parse_critic_report('{"verdict": "maybe", "issues": []}')
        assert parsed["verdict"] == ""


# ── GOMARL 共识证据门禁 ──

def _build_gomarl_with_mocks():
    """构造 GOMARLConsensus，mock LLM/外部依赖，聚焦门禁逻辑。"""
    g = GOMARLConsensus()

    async def fake_score_all(results, profile, topic):
        return [QualityScore(agent_name="teacher", accuracy=8.0, completeness=8.0,
                             adaptability=8.0, overall=8.0)]
    async def fake_consistency(results, topic, profile):
        return []
    async def fake_neural(results, scores, profile, topic):
        return {"consensus_score": 8.0, "dynamic_weights": {}}
    g._score_all = fake_score_all
    g._check_consistency_enhanced = fake_consistency
    g._neural_mix = fake_neural
    g._validate_teaching_schedule = lambda *a, **k: []
    return g


class TestGOMARLReviewGate:
    def test_no_evidence_does_not_regenerate(self):
        """全部无证据批评 → 不触发重生成，且记入 filtered_issues"""
        g = _build_gomarl_with_mocks()
        results = [AgentResult(agent_name="teacher", content="TCP三次握手是SYN→SYN+ACK→ACK")]

        async def run():
            return await g.evaluate(results, {}, "TCP", critic_issues=[
                {"point": "就是觉得不对", "evidence": None, "valid": False},
                {"point": "太长了", "evidence": "", "valid": False},
            ])
        r = asyncio.run(run())
        assert r.status == "passed"
        assert len(r.filtered_issues) == 2

    def test_evidence_critic_triggers_regenerate(self):
        """带证据批评 → 触发重生成；无证据批评被过滤追溯"""
        g = _build_gomarl_with_mocks()
        results = [AgentResult(agent_name="teacher", content="TCP三次握手是SYN→SYN+ACK→ACK")]

        async def run():
            return await g.evaluate(results, {}, "TCP", critic_issues=[
                {"point": "三次握手顺序写反", "evidence": "RFC793", "valid": True},
                {"point": "就是觉得不对", "evidence": None, "valid": False},
            ])
        r = asyncio.run(run())
        assert r.status == "regenerate"
        assert len(r.filtered_issues) == 1
        assert r.confidence_score > 0

    def test_backward_compatible_no_critic_issues(self):
        """不传 critic_issues → 行为不变（向后兼容）"""
        g = _build_gomarl_with_mocks()
        results = [AgentResult(agent_name="teacher", content="TCP三次握手是SYN→SYN+ACK→ACK")]

        async def run():
            return await g.evaluate(results, {}, "TCP")
        r = asyncio.run(run())
        assert r.status in ("passed", "regenerate", "manual_review")
        assert r.filtered_issues == []

    def test_manual_review_branch_keeps_filtered(self):
        """manual_review 分支含门禁追溯字段"""
        g = _build_gomarl_with_mocks()
        g.max_regenerate_rounds = 0
        results = [AgentResult(agent_name="teacher", content="x")]

        async def run():
            return await g.evaluate(results, {}, "TCP", round_num=5, critic_issues=[
                {"point": "就是觉得不对", "evidence": None, "valid": False},
            ])
        r = asyncio.run(run())
        assert r.status == "manual_review"
        assert len(r.filtered_issues) == 1
