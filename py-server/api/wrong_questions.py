# ============================================================
# API — 错题本（/api/wrong-questions/*）
# ============================================================

import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional
from db.user_store import (
    add_wrong_question,
    get_wrong_question,
    list_wrong_questions,
    mark_wrong_question_mastered,
    delete_wrong_question,
    get_wrong_question_stats,
    get_error_profile,
)
from shared.auth import get_current_user
from engines.error_attributor import attribute_error

logger = logging.getLogger("netlearn.wrong_questions")
router = APIRouter(prefix="/wrong-questions", tags=["wrong-questions"])


# ── 请求/响应模型 ──

class AddWrongQuestionRequest(BaseModel):
    question: dict
    wrong_answer: str
    error_type: str = "concept"
    auto_attrib: bool = True  # 是否自动调用 LLM 做智能归因（失败则降级规则，并标注 degraded）


class MasteryUpdateRequest(BaseModel):
    mastered: bool = True


# ── 端点 ──

@router.get("")
async def get_wrong_questions(
    subject: Optional[str] = None,
    mastered: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """获取错题列表，支持按科目/掌握状态过滤，分页"""
    result = list_wrong_questions(
        user["user_id"], subject=subject, mastered=mastered,
        page=page, page_size=page_size,
    )
    return result


@router.get("/stats")
async def get_stats(user: dict = Depends(get_current_user)):
    """获取错题统计：总数/掌握率/科目分布/错误类型分布"""
    return get_wrong_question_stats(user["user_id"])


@router.get("/{qid}")
async def get_wrong_question_detail(qid: int, user: dict = Depends(get_current_user)):
    """获取单条错题详情"""
    item = get_wrong_question(qid)
    if not item:
        raise HTTPException(status_code=404, detail="错题不存在")
    # 权限校验：只能查看自己的错题
    # 注意：get_wrong_question 不校验 user_id，需要通过列表接口间接校验
    # 此处简单校验：检查该题是否属于当前用户
    from db.user_store import _get_conn, _lock
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            "SELECT user_id FROM user_wrong_questions WHERE id=?", (qid,)
        ).fetchone()
    if not row or row["user_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="错题不存在")
    return item


@router.post("")
async def add_wrong_question_api(req: AddWrongQuestionRequest, user: dict = Depends(get_current_user)):
    """手动添加错题；auto_attrib=True 时自动做智能归因（LLM 不可用则规则降级并标注）。"""
    attribution = None
    error_type = req.error_type
    if req.auto_attrib:
        correct_answer = req.question.get("answer", req.question.get("correct_answer", ""))
        try:
            attribution = await attribute_error(req.question, req.wrong_answer, correct_answer)
            # LLM 成功归因时，用更细的错误类型覆盖默认单标签（degraded 时保留用户/默认标签）
            if attribution and not attribution.get("degraded"):
                error_type = attribution.get("error_type", error_type)
        except Exception as e:
            logger.warning("错题归因异常，跳过: %s", e)
    item = add_wrong_question(
        user["user_id"], req.question, req.wrong_answer, error_type, attribution,
    )
    return item


@router.get("/error-profile")
async def get_error_profile_api(user: dict = Depends(get_current_user)):
    """获取用户错题『错误画像』：错误类型分布、高频知识点、归因来源(LLM/规则)。"""
    return get_error_profile(user["user_id"])


@router.put("/{qid}/mastery")
async def update_mastery(qid: int, req: MasteryUpdateRequest, user: dict = Depends(get_current_user)):
    """标记错题已掌握/未掌握"""
    ok = mark_wrong_question_mastered(qid, user["user_id"], req.mastered)
    if not ok:
        raise HTTPException(status_code=404, detail="错题不存在或无权操作")
    return {"success": True, "mastered": req.mastered}


@router.delete("/{qid}")
async def delete_wrong(qid: int, user: dict = Depends(get_current_user)):
    """删除错题"""
    ok = delete_wrong_question(qid, user["user_id"])
    if not ok:
        raise HTTPException(status_code=404, detail="错题不存在或无权操作")
    return {"success": True}
