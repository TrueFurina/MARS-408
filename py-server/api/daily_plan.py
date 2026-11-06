# ============================================================
# API — 每日学习计划（/api/daily-plan/*）
# ============================================================

import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, ConfigDict
from typing import Optional
from services.user_service import (
    get_or_create_daily_plan,
    update_daily_plan_task,
    list_daily_plans,
    reset_daily_plan,
)
from shared.auth import get_current_user

logger = logging.getLogger("netlearn.daily_plan")
router = APIRouter(prefix="/daily-plan", tags=["daily-plan"])


# ── 请求模型 ──

class PlanTaskUpdateRequest(BaseModel):
    task_id: str
    completed: Optional[bool] = None
    progress: Optional[int] = None


class PlanSettingsRequest(BaseModel):
    target_exam_date: Optional[str] = None
    target_score: Optional[int] = None


# ── 端点 ──

@router.get("")
async def get_today_plan(
    date: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """获取指定日期（默认今日）的学习计划，不存在则自动生成"""
    plan = get_or_create_daily_plan(user["user_id"], plan_date=date)
    return plan


class PlanHistoryTask(BaseModel):
    """每日计划的任务项（_generate_default_daily_tasks 的投影）。"""
    model_config = ConfigDict(extra="allow")  # 任务可加字段，不因新增键收窄
    id: str = ""
    type: str = ""
    title: str = ""
    subject: str = ""
    chapter: str = ""
    progress: int = 0
    completed: bool = False
    estimated_minutes: int = 0


class PlanHistoryItem(BaseModel):
    """db/user_store.py::list_daily_plans 的精简投影（9 键）。
    注意：这里**没有** created_at / updated_at —— 单计划端点才有，
    前端手写 DailyPlan 曾把这两个字段声明为必填，属假契约。"""
    model_config = ConfigDict(extra="allow")
    id: int = 0
    plan_date: str = ""
    tasks: list[PlanHistoryTask] = []
    total_tasks: int = 0
    completed_tasks: int = 0
    completion_rate: float = 0.0
    target_exam_date: str = ""
    target_score: int = 0


class PlanHistoryResponse(BaseModel):
    """GET /daily-plan/history 返回。"""
    plans: list[PlanHistoryItem] = []
    total: int = 0
    start_date: str = ""
    end_date: str = ""


@router.get("/history", response_model=PlanHistoryResponse)
async def get_plan_history(
    days: int = Query(7, ge=1, le=90),
    user: dict = Depends(get_current_user),
):
    """获取最近 N 天的计划历史"""
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    plans = list_daily_plans(user["user_id"], start_date=start_date, end_date=end_date, limit=days)
    return {
        "plans": plans,
        "total": len(plans),
        "start_date": start_date,
        "end_date": end_date,
    }


@router.put("/{pid}/task")
async def update_task(
    pid: int,
    req: PlanTaskUpdateRequest,
    user: dict = Depends(get_current_user),
):
    """更新计划中某个任务的完成状态/进度"""
    if req.completed is None and req.progress is None:
        raise HTTPException(status_code=400, detail="必须提供 completed 或 progress")
    result = update_daily_plan_task(
        pid, user["user_id"], req.task_id,
        completed=req.completed, progress=req.progress,
    )
    if not result:
        raise HTTPException(status_code=404, detail="计划或任务不存在")
    return result


@router.post("/{pid}/reset")
async def reset_plan(pid: int, user: dict = Depends(get_current_user)):
    """重置某日计划为未开始状态（所有任务 progress=0, completed=False）"""
    plan = reset_daily_plan(pid, user["user_id"])
    if plan is None:
        raise HTTPException(status_code=404, detail="计划不存在")
    return plan
