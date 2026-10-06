# ============================================================
# 智能答疑 Agent (Tutor) — 功能④ 加分项
# 学生遇到问题时提供多模态即时答疑
#
# 独立于主 LangGraph 流程, 由 API 层按需调用。
# 流程: 检索相关知识点 → Qwen2.5 生成文字解答 → [可选] 生成图解说明
# ============================================================

import json
import logging
from typing import Optional

from db.llm_provider import LLMProvider
from engines.frugal_rag import frugal_rag, format_retrieval_for_llm

logger = logging.getLogger("netlearn.tutor")


# ============================================================
# Prompt 模板
# ============================================================

TUTOR_SYSTEM_PROMPT = """\
你是计算机408考研学习系统的「智能答疑Agent」。
学生在学习过程中遇到问题, 你需要提供即时、清晰、多模态的解答。

## 答疑规则
1. 先理解学生问题的核心困惑点
2. 结合检索到的知识库内容给出准确解答
3. 适配学生画像: 基础薄弱的学生用类比和通俗语言, 基础好的学生可以直接用专业术语
4. 多模态输出:
   - 文字解答: 核心概念解释, 条理清晰
   - 图解说明: 用文字描述一张能帮助理解的图表 (流程图/对比表/结构图)
   - 关联知识: 指出这个问题关联的其他知识点

## 输出格式 (Markdown)
先输出 ---TUTOR_START--- 标记, 然后按以下结构输出:

---TUTOR_START---

## 问题理解
[简述你对问题的理解, 确认没有理解偏差]

## 核心解答
[详细的文字解答, 条理清晰]

## 图解说明
> 📊 [用文字描述一张帮助理解的图: 类型(流程图/对比表/树形图等) + 具体内容]

## 知识关联
- 前置知识: ...
- 延伸知识: ...

## 常见误区
[这个知识点学生常犯的错误]"""


# ============================================================
# 主入口函数
# ============================================================

async def tutor_answer(
    question: str,
    profile: dict,
    course: str = "computer_network",
    learning_context: str = "",
    generate_diagram: bool = True,
    memory_context: str = "",
) -> dict:
    """智能答疑: 学生提问 → 检索 + 多模态解答

    Args:
        question: 学生的问题
        profile: 学生画像
        course: 当前课程 (computer_network / data_structures / ...)
        learning_context: 当前学习上下文 (正在学的知识点, 可选)
        generate_diagram: 是否生成图解说明 (默认True)
        memory_context: L1/L2/L3 三层学情记忆上下文（可选，低侵入注入）

    Returns:
        {
            "answer": "完整Markdown答疑文本",
            "question": "学生原始问题",
            "retrieved_context": "检索到的知识上下文",
            "diagram_description": "图解说明文本 (如有)",
        }
    """
    logger.info(f"[Tutor] 收到问题: {question[:50]}...")

    # Step 1: 检索相关知识
    try:
        chunks = await frugal_rag.retrieve(question, course=course)
        knowledge_context = format_retrieval_for_llm(chunks, max_chars=2000) if chunks else ""
        logger.info(f"[Tutor] 检索到 {len(chunks) if chunks else 0} 个知识片段")
    except Exception as e:
        logger.warning(f"[Tutor] 检索失败, 降级为无上下文答疑: {e}")
        knowledge_context = ""

    # Step 2: 构建提示
    user_prompt = _build_tutor_prompt(question, profile, knowledge_context, learning_context, memory_context)

    # Step 3: LLM 生成解答
    try:
        llm = LLMProvider()
        answer = await llm.text_completion(
            TUTOR_SYSTEM_PROMPT, user_prompt,
            temperature=0.5,
            max_tokens=2500,
        )
        logger.info(f"[Tutor] 解答完成, 长度={len(answer)}")
    except Exception as e:
        logger.error(f"[Tutor] LLM 调用失败: {e}", exc_info=True)
        answer = "## 答疑失败\n\n抱歉, 当前无法生成解答。\n\n请稍后重试或换个方式提问。"

    # Step 4: 提取图解说明 (如果生成了)
    diagram_desc = ""
    if generate_diagram and "## 图解说明" in answer:
        try:
            start = answer.find("## 图解说明")
            end = answer.find("##", start + 5)
            diagram_desc = answer[start:end].strip() if end > start else answer[start:].strip()
        except Exception:
            pass

    return {
        "answer": answer,
        "question": question,
        "retrieved_context": knowledge_context,
        "diagram_description": diagram_desc,
    }


def _build_tutor_prompt(
    question: str,
    profile: dict,
    knowledge_context: str,
    learning_context: str,
    memory_context: str = "",
) -> str:
    """构建答疑提示词（含可选 L1/L2/L3 学情记忆上下文）"""
    parts = [
        f"【学生问题】\n{question}",
    ]

    # 学生画像
    level = profile.get("knowledge_base", "beginner")
    style = profile.get("learning_style", "reading")
    weak = profile.get("weak_points", "")
    parts.append(f"【学生画像】基础水平: {level}, 学习风格: {style}")
    if weak:
        parts.append(f"【已知薄弱点】{weak} (如果问题与薄弱点相关, 请特别注意解释清晰)")

    # L1/L2/L3 三层学情记忆（低侵入注入）
    if memory_context and memory_context != "【学生记忆】暂无历史学习数据":
        parts.append(f"【历史学情记忆（L1会话/L2长期画像/L3情景事件）】\n{memory_context}")

    # 当前学习上下文
    if learning_context:
        parts.append(f"【当前学习上下文】\n{learning_context}")

    # 知识库上下文
    if knowledge_context:
        parts.append(f"【知识库检索结果】\n{knowledge_context}")

    parts.append("\n请根据以上信息, 为学生提供多模态即时答疑。")
    return "\n\n".join(parts)


# ============================================================
# 快速答疑模式 (无检索, 纯LLM, 用于快速响应)
# ============================================================

async def quick_answer(question: str, profile: dict, llm: LLMProvider = None) -> str:
    """快速答疑: 跳过检索, 直接调LLM

    用于学生提出简单问题时, 减少延迟。
    复杂问题应使用完整的 tutor_answer() 流程。
    """
    if llm is None:
        llm = LLMProvider()

    level = profile.get("knowledge_base", "beginner")
    user_prompt = f"学生(基础水平: {level})提问: {question}\n\n请给出简洁清晰的解答。"

    try:
        return await llm.text_completion(
            "你是计算机408考研学习系统的答疑助手, 请简洁准确地解答学生问题。",
            user_prompt,
            temperature=0.5,
            max_tokens=1000,
        )
    except Exception as e:
        logger.error(f"[Tutor] 快速答疑失败: {e}", exc_info=True)
        return "答疑失败: LLM 服务暂时不可用，请稍后重试"
