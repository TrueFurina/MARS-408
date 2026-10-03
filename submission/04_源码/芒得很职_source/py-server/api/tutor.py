# ============================================================
# API — 智能答疑 Agent (Tutor) — 功能④加分项
# 学生在学习过程中遇到问题时, 调用此端点获取多模态即时答疑
# ============================================================

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from agents.tutor import tutor_answer, quick_answer
from db.llm_provider import LLMProvider
from shared.auth import get_current_user
from shared.content_safety import audit_output  # P1-7：统一输出内容安全审核
from shared.ratelimit import require_llm_quota

logger = logging.getLogger("netlearn.api.tutor")
router = APIRouter(prefix="/tutor", tags=["tutor"])


# ── 请求/响应模型 ──

class TutorRequest(BaseModel):
    """学生答疑请求"""
    question: str = Field(..., description="学生的问题")
    profile: dict = Field(default_factory=dict, description="学生画像")
    course: str = Field(default="computer_network", description="当前课程")
    learning_context: str = Field(default="", description="当前学习上下文 (正在学的知识点)")
    generate_diagram: bool = Field(default=True, description="是否生成图解说明")
    quick_mode: bool = Field(default=False, description="快速模式 (跳过检索, 纯LLM)")


class TutorResponse(BaseModel):
    """答疑响应"""
    answer: str = Field(..., description="完整Markdown答疑文本")
    question: str = Field(..., description="学生原始问题")
    retrieved_context: str = Field(default="", description="检索到的知识上下文")
    diagram_description: str = Field(default="", description="图解说明文本 (如有)")


# ── 端点 ──

@router.post("/answer", response_model=TutorResponse)
async def tutor_endpoint(req: TutorRequest, user: dict = Depends(require_llm_quota)):
    """智能答疑: 学生提问 → 检索 + 多模态解答

    完整流程: FrugalRAG检索 → Qwen2.5生成文字解答+图解说明+知识关联
    快速模式: 跳过检索, 直接LLM回答 (适合简单问题, 减少延迟)
    """
    logger.info(f"答疑请求: question={req.question[:50]}..., quick={req.quick_mode}")

    if req.quick_mode:
        # 快速模式: 跳过检索
        llm = LLMProvider()
        answer = await quick_answer(req.question, req.profile, llm)
        # P1-7：输出内容安全审核
        answer, _ = await audit_output(answer, "tutor/answer/quick")
        return TutorResponse(
            answer=answer,
            question=req.question,
            retrieved_context="",
            diagram_description="",
        )

    # 完整流程: 检索 + 多模态解答
    result = await tutor_answer(
        question=req.question,
        profile=req.profile,
        course=req.course,
        learning_context=req.learning_context,
        generate_diagram=req.generate_diagram,
    )
    # P1-7：输出内容安全审核
    _safe_answer, _ = await audit_output(result["answer"], "tutor/answer")
    result["answer"] = _safe_answer

    # L1/L2/L3 三层学情记忆联动（低侵入：答疑入 L3，供答疑轨迹追溯）
    try:
        user_id = user.get("user_id") or user.get("id") or ""
        if user_id:
            from db import memory_store as _ms
            _ms.append_episode(user_id, "tutor_answer", {
                "question_len": len(req.question),
                "course": req.course,
                "quick_mode": bool(req.quick_mode),
            })
    except Exception as _me:
        logger.debug(f"答疑记忆写入失败(忽略): {_me}")

    return TutorResponse(
        answer=result["answer"],
        question=result["question"],
        retrieved_context=result["retrieved_context"],
        diagram_description=result["diagram_description"],
    )


# ── 增强版多模态答疑（文字+SVG图解+短视频脚本） ──


class EnhancedTutorRequest(BaseModel):
    """增强版答疑请求"""
    question: str = Field(..., description="学生的问题")
    profile: dict = Field(default_factory=dict, description="学生画像")
    course: str = Field(default="computer_network", description="当前课程")
    learning_context: str = Field(default="", description="学习上下文")
    generate_svg: bool = Field(default=True, description="是否生成 SVG 图解")
    generate_video: bool = Field(default=False, description="是否生成短视频脚本")
    quick_mode: bool = Field(default=False, description="快速模式（跳过检索）")


@router.post("/enhanced-answer")
async def tutor_enhanced_endpoint(req: EnhancedTutorRequest, user: dict = Depends(require_llm_quota)):
    """增强版智能答疑：文字解答 + SVG 图解 + 可选短视频脚本

    赛题加分项④：多模态智能辅导
    支持 SVG 教学示意图生成和短视频脚本生成。
    """
    from agents.tutor_enhanced import enhanced_tutor_answer, quick_multimodal_answer

    logger.info(f"增强答疑请求: question={req.question[:50]}..., quick={req.quick_mode}")

    if req.quick_mode:
        result = await quick_multimodal_answer(
            question=req.question,
            profile=req.profile,
        )
        # P1-7：输出内容安全审核
        if isinstance(result, dict) and result.get("answer"):
            _safe, _ = await audit_output(result["answer"], "tutor/enhanced-answer/quick")
            result["answer"] = _safe
        return result

    result = await enhanced_tutor_answer(
        question=req.question,
        profile=req.profile,
        course=req.course,
        learning_context=req.learning_context,
        generate_svg=req.generate_svg,
        generate_video=req.generate_video,
    )
    # P1-7：输出内容安全审核
    if isinstance(result, dict) and result.get("answer"):
        _safe, _ = await audit_output(result["answer"], "tutor/enhanced-answer")
        result["answer"] = _safe
    return result
