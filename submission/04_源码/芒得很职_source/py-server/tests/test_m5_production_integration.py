# -*- coding: utf-8 -*-
"""M5 · 生产链路集成测试（平台攻坚 P1）

验证 M1-M3 真正接入生产流水线：
  - coordinator_node 写入 state["policy_action"]（规则版，source=rules）
  - critic_node 门禁分支补 consensus["confidence_score"]
  - generator_cluster 的 gomarl.evaluate 产物携带 M2 字段（confidence_score/filtered_issues）
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from agents.state import AgentState
from agents.coordinator import coordinator_node, _resolve_policy_action
from agents.critic import critic_node, _critic_confidence
from engines.gomarl import GOMARLConsensus, AgentResult


# ── coordinator：策略决策接入 ──

class TestCoordinatorPolicyAction:
    def test_node_writes_policy_action(self):
        """coordinator_node 结束必须写入 policy_action（规则版降级可用）。"""
        state = AgentState(
            user_request="教我 TCP 三次握手",
            topic="TCP 三次握手",
            student_profile={"level": "beginner"},
        )
        out = asyncio.run(coordinator_node(state))
        pa = out.get("policy_action")
        assert pa, "policy_action 未被写入"
        assert pa.get("source") in ("rules", "mappo")
        assert "difficulty" in pa and "teaching_mode" in pa and "review_intensity" in pa
        # 规则版：beginner → basic 难度
        if pa.get("source") == "rules":
            assert pa["difficulty"] == "basic"

    def test_resolve_policy_action_rules_default(self):
        """use_mappo_policy 默认 False → 规则版决策。"""
        state = AgentState(student_profile={"level": "advanced"})
        pa = _resolve_policy_action(state)
        assert pa["source"] == "rules"
        assert pa["difficulty"] == "advanced"

    def test_resolve_policy_action_round_escalation(self):
        """评审强度随轮次升级（首轮 basic，重试轮 full）。"""
        state = AgentState(student_profile={"level": "beginner"}, regenerate_round=1)
        pa = _resolve_policy_action(state)
        assert pa["review_intensity"] == "full"


# ── critic：门禁置信度 ──

class TestCriticGateConfidence:
    @staticmethod
    def _install_json_llm(monkeypatch, payload: str):
        import db.llm_provider as _lp

        async def _fake(self, system_prompt, user_prompt, *args, **kwargs):
            return payload

        monkeypatch.setattr(_lp.LLMProvider, "text_completion", _fake)

    def test_gate_blocks_evidenceless_and_writes_confidence(self, monkeypatch):
        """全部无证据批评 → 门禁拦截判定 passed，且 confidence_score 略降。"""
        self._install_json_llm(
            monkeypatch,
            '{"verdict": "flagged", "issues": [{"point": "疑似错误", "evidence": null, "suggestion": "再查"}]}',
        )
        state = AgentState(topic_label="TCP", teacher_doc="内容", quiz="题", consensus={"status": "unknown"})
        out = asyncio.run(critic_node(state))
        cons = out["consensus"]
        assert cons["status"] == "passed"
        assert cons.get("confidence_score", 0.9) <= 0.9
        assert any("无证据批评被门禁拦截" in x for x in cons.get("filtered_issues", []))

    def test_flagged_with_evidence_writes_low_confidence(self, monkeypatch):
        """带证据批评 → flagged + regenerate_round 递增 + confidence_score=0.6。"""
        self._install_json_llm(
            monkeypatch,
            '{"verdict": "flagged", "issues": [{"point": "RFC 793 状态数错误", "evidence": "RFC 793", "suggestion": "改为 11 状态"}]}',
        )
        state = AgentState(topic_label="TCP", teacher_doc="内容", quiz="题", consensus={"status": "unknown"})
        out = asyncio.run(critic_node(state))
        cons = out["consensus"]
        assert cons["status"] == "flagged"
        assert cons.get("confidence_score") == 0.6
        assert out.get("regenerate_round", 0) == 1

    def test_confidence_formula(self):
        assert _critic_confidence("passed", 0, 0) == pytest.approx(0.95)
        assert _critic_confidence("passed", 0, 3) == pytest.approx(0.8)
        assert _critic_confidence("flagged", 1, 0) == 0.6
        assert _critic_confidence("regenerate", 2, 0) == 0.4


# ── generator_cluster：M2 字段生产携带 ──

class TestGeneratorConsensusFields:
    def test_evaluate_carries_m2_fields(self):
        """evaluate 产物必须携带 confidence_score / filtered_issues（生产映射源）。"""
        gomarl = GOMARLConsensus()
        results = [
            AgentResult(agent_name="teacher", content="TCP 三次握手详解", prompt_used="p1"),
            AgentResult(agent_name="quizmaster", content="1. 题目", prompt_used="p2"),
            AgentResult(agent_name="mindmap", content="# 图", prompt_used="p3"),
        ]
        r = asyncio.run(gomarl.evaluate(results, {"level": "beginner"}, "TCP", round_num=0))
        assert r.status in ("passed", "flagged", "regenerate")
        assert isinstance(r.confidence_score, float) and r.confidence_score > 0
        assert isinstance(r.filtered_issues, list)
