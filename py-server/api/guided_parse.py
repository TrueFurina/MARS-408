# ============================================================
# API — 思路引导式解析（/api/guide/*）
# ============================================================

import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from shared.auth import get_current_user
from engines.guided_parse import generate_guide

logger = logging.getLogger("netlearn.guided_parse")
router = APIRouter(prefix="/guide", tags=["guide"])


class GuideRequest(BaseModel):
    question: dict
    use_llm: bool = True  # False 时强制走规则模板（便于离线/无凭证场景）


@router.post("/quiz")
async def guide_quiz(req: GuideRequest, user: dict = Depends(get_current_user)):
    """对一道题生成『思路引导式解析』（苏格拉底分步提示）。
    返回 steps（引导步骤）+ source（llm/template）+ degraded 标志（诚信：模板降级明确标注）。"""
    result = await generate_guide(req.question, use_llm=req.use_llm)
    return {
        "question_id": req.question.get("id"),
        "subject": req.question.get("subject"),
        "source": result["source"],
        "degraded": result["degraded"],
        "qtype": result["qtype"],
        "steps": result["steps"],
    }
