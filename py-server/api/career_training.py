# ============================================================
# API — 芒得很职·职业素养对抗实训（/api/career/*）
# P0 最窄闭环：场景列表 → 启动 → 逐轮作答 → 结束 → 六维报告
# 与 408 所有路由前缀隔离，互不影响。
# ============================================================

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from shared.auth import get_current_user
from services import career_service
from db import career_store

logger = logging.getLogger("netlearn.career.api")
router = APIRouter(prefix="/career", tags=["career-training"])


# ── 请求模型 ──
class StartRequest(BaseModel):
    scenario_id: str
    difficulty: str = "medium"          # easy/medium/hard
    max_turns: int = 8
    task_id: Optional[str] = None       # 教师任务（自主练习为空）


class AnswerRequest(BaseModel):
    answer: str = Field("", description="学生本轮口头/文字回答")


class EndRequest(BaseModel):
    force: bool = False


def _check_owner(session_id: str, user: dict) -> dict:
    state = career_store.get_session_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="实训会话不存在")
    if state.get("user_id") != user.get("user_id") and user.get("role") not in ("admin", "teacher"):
        raise HTTPException(status_code=403, detail="无权访问他人实训会话")
    return state


# ── 场景列表 ──
@router.get("/scenarios")
async def scenarios(user: dict = Depends(get_current_user)):
    return {"scenarios": career_service.list_scenarios()}


# ── 启动一场实训 ──
@router.post("/session/start")
async def start(req: StartRequest, user: dict = Depends(get_current_user)):
    try:
        return await career_service.start_session(
            user_id=user["user_id"], scenario_id=req.scenario_id,
            difficulty=req.difficulty, max_turns=req.max_turns, task_id=req.task_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("启动实训失败")
        raise HTTPException(status_code=500, detail=f"启动失败: {e}")


# ── 推进一轮 ──
@router.post("/session/{session_id}/answer")
async def answer(session_id: str, req: AnswerRequest, user: dict = Depends(get_current_user)):
    _check_owner(session_id, user)
    try:
        return await career_service.answer_turn(session_id, req.answer)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("作答推进失败")
        raise HTTPException(status_code=500, detail=f"处理失败: {e}")


# ── 主动结束并出报告 ──
@router.post("/session/{session_id}/end")
async def end(session_id: str, req: EndRequest, user: dict = Depends(get_current_user)):
    _check_owner(session_id, user)
    try:
        return await career_service.end_session(session_id, force=req.force)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("结束实训失败")
        raise HTTPException(status_code=500, detail=f"结束失败: {e}")


# ── 获取报告（含完整对话与证据链）──
@router.get("/session/{session_id}/report")
async def report(session_id: str, user: dict = Depends(get_current_user)):
    _check_owner(session_id, user)
    try:
        return career_service.get_report(session_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── 我的实训历史 ──
@router.get("/sessions")
async def my_sessions(user: dict = Depends(get_current_user)):
    return {"sessions": career_service.list_my_sessions(user["user_id"])}
