# -*- coding: utf-8 -*-
"""端到端冒烟：mock LLM 跑完整 LangGraph，验证三评审/MAPPO 生产链路字段。
（平台攻坚 P1 验收：policy_action 流经全图、consensus 带置信度与门禁追溯）"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db.llm_provider as _lp


async def _fake_tc(self, system_prompt, user_prompt, *args, **kwargs):
    # 返回结构化 JSON（coordinator 解析 topic；其余节点降级兜底）
    return '{"topic": "TCP 三次握手", "course": "computer_network", "difficulty": "medium"}'


async def _fake_chat(self, messages, *args, **kwargs):
    return {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}


async def _fake_stream(self, messages, *args, **kwargs):
    yield "mock"


def main():
    _lp.LLMProvider.text_completion = _fake_tc
    _lp.LLMProvider.chat = _fake_chat
    _lp.LLMProvider.stream_chat = _fake_stream

    from agents.graph import agent_graph
    from agents.state import AgentState

    initial = AgentState(
        user_request="教我 TCP 三次握手",
        topic="TCP 三次握手",
        student_profile={"level": "beginner", "weak_topics": ["子网划分"]},
        course="computer_network",
    )

    final_state = {}
    seen = []

    async def run():
        async for update in agent_graph.astream(initial, stream_mode="updates"):
            for node, val in update.items():
                seen.append(node)
                if node == "coordinator" and val.get("policy_action"):
                    print(f"[coordinator] policy_action={val['policy_action']}")
                if node == "generator_cluster" and val.get("consensus"):
                    c = val["consensus"]
                    print(f"[generator_cluster] consensus.status={c.get('status')} "
                          f"confidence={c.get('confidence_score')} "
                          f"filtered={len(c.get('filtered_issues', []))}")
                if node == "critic" and val.get("consensus"):
                    c = val["consensus"]
                    print(f"[critic] consensus.status={c.get('status')} "
                          f"confidence={c.get('confidence_score')} "
                          f"filtered={len(c.get('filtered_issues', []))}")
                final_state.update(val)

    asyncio.run(run())

    pa = final_state.get("policy_action")
    cons = final_state.get("consensus") or {}
    print("---")
    print("访问节点顺序:", " → ".join(seen))
    print("policy_action:", pa)
    print("consensus.status:", cons.get("status"))
    print("consensus.confidence_score:", cons.get("confidence_score"))
    print("consensus.filtered_issues:", len(cons.get("filtered_issues", [])))
    assert pa and pa.get("source") == "rules", "policy_action 未端到端生效"
    assert "confidence_score" in cons, "consensus 置信度未透传"
    print("端到端冒烟通过 ✅")


if __name__ == "__main__":
    main()
