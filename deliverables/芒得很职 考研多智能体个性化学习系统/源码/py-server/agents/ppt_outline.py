# ============================================================
# PPT 大纲 Agent (PPT Outline Generator)
# 生成结构化的 PPT 幻灯片大纲, 帮助学生快速复习和课堂展示
#
# 作为 generator_cluster 的子 Agent 被调用。
# 使用 FrugalRAG 检索结果 + LLMProvider 生成大纲。
# ============================================================

import logging

from db.llm_provider import LLMProvider
from prompts import PPT_AGENT_PROMPT

logger = logging.getLogger("netlearn.ppt_outline")


async def generate_ppt_outline(
    topic: str,
    profile: dict,
    knowledge_context: str,
    llm: LLMProvider,
    task_instruction: str = "",
    memory_context: str = "",
) -> str:
    """生成 PPT 大纲

    Args:
        topic: 学习主题
        profile: 学生画像
        knowledge_context: FrugalRAG 检索到的知识上下文
        llm: LLMProvider 实例
        task_instruction: planner 下发的任务指令 (可选)
        memory_context: L1/L2/L3 三层学情记忆上下文（可选，低侵入注入）

    Returns:
        PPT 大纲的 Markdown 文本
    """
    logger.info(f"[PPT] 开始生成, topic={topic}")

    user_prompt = _build_prompt(topic, profile, knowledge_context, task_instruction, memory_context)

    try:
        result = await llm.text_completion(
            PPT_AGENT_PROMPT, user_prompt,
            temperature=0.5,
            max_tokens=2000,
        )
        logger.info(f"[PPT] 生成完成, 长度={len(result)}")
        return result

    except Exception as e:
        logger.error(f"[PPT] 生成失败: {e}")
        return f"## PPT大纲生成失败\n\n错误: {e}"


def _build_prompt(
    topic: str,
    profile: dict,
    knowledge_context: str,
    task_instruction: str,
    memory_context: str = "",
) -> str:
    """构建用户提示（含可选 L1/L2/L3 学情记忆上下文）"""
    parts = [
        f"【学习主题】{topic}",
        f"【任务指令】{task_instruction or '生成结构化的PPT幻灯片大纲'}",
    ]

    level = profile.get("knowledge_base", "beginner")
    goal = profile.get("goal", "general")
    weak = profile.get("weak_points", "")
    parts.append(f"【学生画像】基础水平: {level}, 学习目标: {goal}")
    if weak:
        parts.append(f"【薄弱点】{weak}（请在PPT中增加这些知识点的详细讲解页）")

    # L1/L2/L3 三层学情记忆（低侵入注入：记忆薄弱点驱动PPT讲解重点页）
    if memory_context and memory_context != "【学生记忆】暂无历史学习数据":
        parts.append(f"【历史学情记忆（L1会话/L2长期画像/L3情景事件）】\n{memory_context[:500]}")

    if knowledge_context:
        parts.append(f"\n{knowledge_context}")

    parts.append("\n请先输出 ---PPT_START---，然后输出PPT大纲。")
    return "\n\n".join(parts)
