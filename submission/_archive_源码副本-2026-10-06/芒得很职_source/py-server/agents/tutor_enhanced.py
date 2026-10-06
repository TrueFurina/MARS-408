# ============================================================
# 增强版智能辅导 — 功能④ 加分项（多模态即时答疑）
# 在原有 tutor 基础上增加：
# 1. SVG 图解生成（替代纯文字描述）
# 2. 短视频动画脚本生成
# 3. 统一多模态答疑输出
# ============================================================

import asyncio
import logging
from typing import Optional

from agents.tutor import tutor_answer, quick_answer
from agents.media_generator import generate_teaching_diagram, generate_enhanced_video_script, _fallback_svg
from db.llm_provider import LLMProvider
from engines.frugal_rag import frugal_rag, format_retrieval_for_llm

logger = logging.getLogger("netlearn.tutor_enhanced")


async def enhanced_tutor_answer(
    question: str,
    profile: dict,
    course: str = "computer_network",
    learning_context: str = "",
    generate_svg: bool = True,
    generate_video: bool = False,
    memory_context: str = "",
) -> dict:
    """增强版智能答疑：文字解答 + SVG 图解 + 可选短视频脚本

    Args:
        question: 学生问题
        profile: 学生画像
        course: 课程
        learning_context: 学习上下文
        generate_svg: 是否生成 SVG 图解
        generate_video: 是否生成短视频脚本
        memory_context: L1/L2/L3 三层学情记忆上下文（可选，低侵入注入）

    Returns:
        {
            "answer": 文字解答,
            "svg_diagram": SVG 图解代码,
            "video_script": 短视频脚本,
            "diagram_description": 图解文字说明,
            "retrieved_context": 检索上下文,
            "question": 原始问题,
        }
    """
    # 先用基础 tutor 获取文字解答（30s 超时 + 降级，避免 RAG+LLM 慢导致整体挂起）
    try:
        base_result = await asyncio.wait_for(
            tutor_answer(question=question, profile=profile, course=course,
                         learning_context=learning_context, generate_diagram=generate_svg,
                         memory_context=memory_context),
            timeout=30.0,
        )
    except asyncio.TimeoutError as e:
        logger.warning(f"enhanced_tutor_answer 文本段超时(30s): {e}")
        base_result = {"answer": "答疑检索超时(30s)，请稍后重试或使用快速模式。", "question": question, "retrieved_context": "", "diagram_description": ""}
    except Exception as e:
        logger.warning(f"enhanced_tutor_answer 文本段失败: {e}")
        base_result = {"answer": "答疑暂时不可用，请稍后重试。", "question": question, "retrieved_context": "", "diagram_description": ""}

    answer = base_result["answer"]
    retrieved = base_result.get("retrieved_context", "")
    diagram_desc = base_result.get("diagram_description", "")
    question_text = base_result.get("question", question)

    # 并行生成 SVG 和短视频脚本
    svg_diagram = ""
    video_script = ""

    async def _gen_svg():
        if generate_svg:
            topic = _extract_topic(question, answer)
            return await generate_teaching_diagram(topic, retrieved)
        return ""

    async def _gen_video():
        if generate_video:
            topic = _extract_topic(question, answer)
            return await generate_enhanced_video_script(topic, profile, retrieved)
        return ""

    async def _gen_svg_t():
        try:
            return await asyncio.wait_for(_gen_svg(), timeout=15.0)
        except Exception:
            return ""

    async def _gen_video_t():
        try:
            return await asyncio.wait_for(_gen_video(), timeout=15.0)
        except Exception:
            return ""

    results = await asyncio.gather(_gen_svg_t(), _gen_video_t(), return_exceptions=True)
    svg_diagram = results[0] if not isinstance(results[0], Exception) else ""
    video_script = results[1] if not isinstance(results[1], Exception) else ""

    return {
        "answer": answer,
        "question": question_text,
        "svg_diagram": svg_diagram,
        "video_script": video_script,
        "diagram_description": diagram_desc,
        "retrieved_context": retrieved,
        "multimodal_types": ["text", "svg"] + (["video_script"] if video_script else []),
        "thinking": "已检索知识库并生成解答" + ("，含SVG图解" if svg_diagram else "") + ("，含视频脚本" if video_script else ""),
    }


def _extract_topic(question: str, answer: str) -> str:
    """从问题或答案中提取主题关键词"""
    # 取问题前 50 个字符作为主题
    topic = question.strip()[:50]
    if not topic:
        topic = answer.strip()[:50]
    return topic


# ── 快速多模态答疑（仅文字+SVG，轻量级） ──


async def quick_multimodal_answer(
    question: str,
    profile: dict,
) -> dict:
    """快速多模态答疑：跳过 RAG 检索，直接 LLM + SVG 生成

    每段加 wait_for 超时 + 降级，避免 X2 11200/DeepSeek 慢导致端点整体挂起。
    """
    llm = LLMProvider()

    # 快速文字解答（15s 超时，失败给兜底文案）
    try:
        answer = await asyncio.wait_for(quick_answer(question, profile, llm), timeout=15.0)
    except Exception as e:
        logger.warning(f"quick_multimodal_answer 文本段失败/超时: {e}")
        answer = "答疑暂时不可用，请稍后重试，或在设置页切换 LLM 通道。"

    # 生成 SVG 图解（12s 超时，失败走 fallback_svg）
    topic = _extract_topic(question, answer)
    try:
        svg = await asyncio.wait_for(generate_teaching_diagram(topic), timeout=12.0)
    except Exception as e:
        logger.warning(f"quick_multimodal_answer SVG 段失败/超时: {e}")
        svg = _fallback_svg(topic)

    return {
        "answer": answer,
        "question": question,
        "svg_diagram": svg,
        "multimodal_types": ["text", "svg"],
        "thinking": "快速模式：已生成解答" + ("，含SVG图解" if svg else ""),
    }