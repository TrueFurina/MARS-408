# ============================================================
# API — 计网易混淆概念辨析专项（/api/cn-distinction/*）
# ============================================================

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from engines.cn_distinction import (
    get_pairs,
    get_pair,
    get_random_quiz,
    grade_quiz,
)

logger = logging.getLogger("netlearn.cn_distinction")
router = APIRouter(prefix="/cn-distinction", tags=["cn-distinction"])


class AnswerRequest(BaseModel):
    pair_id: str
    user_answer: str


@router.get("")
async def list_pairs():
    """列出全部计网易混淆概念对（含混淆点与关键辨析，不含自测题答案）。"""
    return {"total": len(get_pairs()), "pairs": get_pairs()}


@router.get("/{pid}")
async def get_pair_detail(pid: str):
    """获取单个概念对的完整辨析（含关键辨析点，不含自测题答案）。"""
    p = get_pair(pid)
    if not p:
        raise HTTPException(status_code=404, detail="概念对不存在")
    return {
        "id": p["id"],
        "title": p["title"],
        "category": p["category"],
        "confusion": p["confusion"],
        "key_points": p["key_points"],
    }


@router.get("/quiz/random")
async def random_quiz():
    """随机抽取一道区分自测题（不含答案，需作答后判分）。"""
    q = get_random_quiz()
    return {
        "pair_id": q["pair_id"],
        "pair_title": q["pair_title"],
        "question": q["question"],
    }


@router.post("/quiz/answer")
async def answer_quiz(req: AnswerRequest):
    """对自测作答做确定性关键词判分（可复现，不依赖 LLM）。"""
    p = get_pair(req.pair_id)
    if not p:
        raise HTTPException(status_code=404, detail="概念对不存在")
    result = grade_quiz(p["quiz"], req.user_answer)
    return {
        "pair_id": req.pair_id,
        "pair_title": p["title"],
        "score": result["score"],
        "passed": result["passed"],
        "hit_keywords": result["hit_keywords"],
        "missed_keywords": result["missed_keywords"],
        "answer": result["answer"],
    }
