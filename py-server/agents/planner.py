# ============================================================
# 规划 Agent (Planner)
# 根据诊断结果和用户请求，制定学习资源生成计划
# 复用现有 prompts.py 中的 PLANNER_PROMPT
# ============================================================

import json
import re
import logging

from agents.state import AgentState
from db.llm_provider import LLMProvider
from prompts import PLANNER_PROMPT

logger = logging.getLogger("netlearn.planner")


async def planner_node(state: AgentState) -> AgentState:
    """规划 Agent：制定学习资源生成计划"""
    state["status"] = "planning"
    state["current_agent"] = "planner"

    topic = state.get("topic", "")
    diagnosis = state.get("diagnosis", {})
    memory_context = state.get("memory_context") or ""

    user_prompt = (
        f"【学生学习主题】{topic}\n\n"
        f"【学生画像】知识基础: {diagnosis.get('level', 'beginner')}, "
        f"学习风格: {diagnosis.get('style', 'reading')}, "
        f"薄弱点: {', '.join(diagnosis.get('weak_areas', [])) or '无'}\n\n"
    )
    # L1/L2/L3 三层学情记忆（低侵入注入）
    if memory_context and memory_context != "【学生记忆】暂无历史学习数据":
        user_prompt += f"【历史学情记忆】\n{memory_context}\n\n"
    user_prompt += "请根据以上信息制定学习资源生成计划。"

    try:
        llm = LLMProvider()
        response = await llm.text_completion(
            PLANNER_PROMPT, user_prompt, temperature=0.5, max_tokens=800
        )

        # 解析 LLM 输出
        plan = _parse_plan_output(response)
        state["plan"] = plan
        state["topic_label"] = plan.get("topic", topic)
        state["chapter"] = plan.get("chapter", "")

    except Exception as e:
        logger.warning(f"Planner LLM 调用失败: {e}，使用默认计划")
        # 降级：默认计划
        state["plan"] = {
            "topic": topic,
            "chapter": "",
            "difficulty": state.get("difficulty", "medium"),
            "teacher_task": f"讲解{topic}的核心概念和原理",
            "quiz_task": f"生成关于{topic}的练习题（包含选择题和简答题）",
            "media_task": f"为{topic}生成思维导图，标注知识结构",
            "code_task": f"生成与{topic}相关的代码实操案例",
            "ppt_task": f"生成{topic}的PPT大纲",
            "video_task": f"生成{topic}的教学视频脚本",
        }
        state["topic_label"] = topic
        state["chapter"] = ""

    return state


def _parse_plan_output(text: str) -> dict:
    """解析 Planner 的标准输出格式"""
    plan = {}
    patterns = {
        "topic": r"---TOPIC---\s*\n(.*?)\n",
        "chapter": r"---CHAPTER---\s*\n(.*?)\n",
        "difficulty": r"---DIFFICULTY---\s*\n(.*?)\n",
        "teacher_task": r"---TEACHER_TASK---\s*\n(.*?)(?:\n---|$)",
        "quiz_task": r"---QUIZ_TASK---\s*\n(.*?)(?:\n---|$)",
        "media_task": r"---MEDIA_TASK---\s*\n(.*?)(?:\n---|$)",
        "code_task": r"---CODE_TASK---\s*\n(.*?)(?:\n---|$)",
        "ppt_task": r"---PPT_TASK---\s*\n(.*?)(?:\n---|$)",
        "video_task": r"---VIDEO_TASK---\s*\n(.*?)(?:\n---|$)",
    }

    for key, pattern in patterns.items():
        m = re.search(pattern, text, re.DOTALL)
        if m:
            plan[key] = m.group(1).strip()

    return plan
