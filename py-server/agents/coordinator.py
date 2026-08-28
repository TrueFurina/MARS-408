# ============================================================
# 全局协调 Agent (Coordinator)
# 调用 LLM 解析用户自然语言请求，确定主题、课程、难度
# ============================================================

import logging

from agents.state import AgentState
from db.llm_provider import LLMProvider
from prompts import COORDINATOR_PROMPT

logger = logging.getLogger("netlearn.coordinator")


async def coordinator_node(state: AgentState) -> AgentState:
    """全局协调 Agent：调用 LLM 解析用户请求，确定主题、课程、难度"""
    state["status"] = "planning"
    state["current_agent"] = "coordinator"

    topic = state.get("topic", "")
    user_request = state.get("user_request", "")

    # 如果 topic 已由上层 API 设置，直接使用（但仍可通过 LLM 补全 course/difficulty）
    if not topic and user_request:
        topic = user_request.strip()
        state["topic"] = topic

    # 调用 LLM 解析请求
    user_prompt = f"【用户请求】\n{user_request or topic}\n\n请解析以上请求，确定学习主题、所属408课程（computer_network/data_structures/computer_organization/operating_system）和难度等级。如果请求不明确涉及特定科目，留空course字段让后续逻辑自动判断。如果用户未指定科目，请根据内容自动推断最可能的科目。"

    # L1/L2/L3 三层学情记忆（低侵入注入：协调阶段参考薄弱点/进度）
    memory_context = state.get("memory_context") or ""
    if memory_context and memory_context != "【学生记忆】暂无历史学习数据":
        user_prompt += (
            f"\n\n【历史学情记忆（L1会话/L2长期画像/L3情景事件）】\n{memory_context}\n"
            "请结合学生历史薄弱点与学习进度解析请求，若请求主题属于已知薄弱科目则优先推荐该课程。"
        )

    try:
        llm = LLMProvider()
        response = await llm.text_completion(
            COORDINATOR_PROMPT, user_prompt,
            temperature=0.3, max_tokens=300,
        )

        parsed = _parse_coordination(response)

        # 用 LLM 解析结果更新状态
        if parsed.get("topic"):
            state["topic"] = parsed["topic"]
        state["course"] = parsed.get("course", "computer_network")
        state["difficulty"] = parsed.get("difficulty", "medium")
        state.setdefault("regenerate_round", 0)

        logger.info(f"Coordinator LLM 解析完成: topic={state['topic']}, "
                     f"course={state['course']}, difficulty={state['difficulty']}")

    except Exception as e:
        logger.warning(f"Coordinator LLM 调用失败: {e}，降级为规则解析")
        state["topic"] = topic
        state.setdefault("difficulty", "medium")
        state.setdefault("course", "computer_network")
        state.setdefault("regenerate_round", 0)

    return state


def _parse_coordination(text: str) -> dict:
    """解析 LLM 协调输出（JSON格式），复用共享提取工具"""
    from shared.llm_utils import extract_json_from_llm_output

    data = extract_json_from_llm_output(
        text,
        default={"topic": "", "course": "computer_network", "difficulty": "medium"},
    )
    if not data:
        return {"topic": "", "course": "computer_network", "difficulty": "medium"}

    data.setdefault("topic", "")
    data.setdefault("course", "computer_network")
    data.setdefault("difficulty", "medium")
    data.setdefault("parsed_intent", "")

    # 验证 course 值
    valid_courses = {
        "computer_network", "data_structures",
        "computer_organization", "operating_system",
    }
    if data["course"] not in valid_courses:
        data["course"] = "computer_network"

    # 验证 difficulty 值
    valid_difficulties = {"easy", "medium", "hard"}
    if data["difficulty"] not in valid_difficulties:
        data["difficulty"] = "medium"

    return data
