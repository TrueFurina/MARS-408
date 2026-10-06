# ============================================================
# 代码实操 Agent (Code Practice Generator)
# 生成可运行的代码实操案例, 帮助学生通过动手编程理解核心概念
#
# 作为 generator_cluster 的子 Agent 被调用。
# 使用 FrugalRAG 检索结果 + LLMProvider 生成代码。
# ============================================================

import logging

from db.llm_provider import LLMProvider
from prompts import CODE_PRACTICE_AGENT_PROMPT

logger = logging.getLogger("netlearn.code_practice")


async def generate_code_practice(
    topic: str,
    profile: dict,
    knowledge_context: str,
    llm: LLMProvider,
    task_instruction: str = "",
    memory_context: str = "",
) -> str:
    """生成代码实操案例

    Args:
        topic: 学习主题
        profile: 学生画像 (含编程水平、学习风格等)
        knowledge_context: FrugalRAG 检索到的知识上下文
        llm: LLMProvider 实例
        task_instruction: planner 下发的任务指令 (可选)
        memory_context: L1/L2/L3 三层学情记忆上下文（可选，低侵入注入）

    Returns:
        代码实操案例的 Markdown 文本
    """
    logger.info(f"[CodePractice] 开始生成, topic={topic}")

    user_prompt = _build_prompt(topic, profile, knowledge_context, task_instruction, memory_context)

    try:
        result = await llm.text_completion(
            CODE_PRACTICE_AGENT_PROMPT, user_prompt,
            temperature=0.4,  # 代码生成用低温度
            max_tokens=2500,
        )
        logger.info(f"[CodePractice] 生成完成, 长度={len(result)}")
        return result

    except Exception as e:
        logger.error(f"[CodePractice] 生成失败: {e}")
        return f"## 代码实操生成失败\n\n错误: {e}"


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
        f"【任务指令】{task_instruction or '生成与主题相关的代码实操案例'}",
    ]

    # 学生画像
    level = profile.get("knowledge_base", "beginner")
    style = profile.get("learning_style", "reading")
    weak = profile.get("weak_points", "")
    parts.append(f"【学生画像】基础水平: {level}, 学习风格: {style}")
    if weak:
        parts.append(f"【薄弱点】{weak}（请在代码注释中重点解释相关概念）")

    # L1/L2/L3 三层学情记忆（低侵入注入：记忆薄弱点驱动代码难度与注释）
    if memory_context and memory_context != "【学生记忆】暂无历史学习数据":
        parts.append(f"【历史学情记忆（L1会话/L2长期画像/L3情景事件）】\n{memory_context[:500]}")

    # 知识库上下文
    if knowledge_context:
        parts.append(f"\n{knowledge_context}")

    parts.append("\n请先输出 ---CODE_START---，然后输出代码实操案例。")
    return "\n\n".join(parts)
