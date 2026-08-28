# ============================================================
# API — 每日学习计划（/api/daily-plan/*）
# ============================================================

import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional
from db.user_store import (
    get_or_create_daily_plan,
    update_daily_plan_task,
    list_daily_plans,
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


@router.get("/history")
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
    from db.user_store import _get_conn, _lock, _now
    import json as _json
    conn = _get_conn()
    now = _now()
    with _lock:
        row = conn.execute("SELECT * FROM user_daily_plans WHERE id=? AND user_id=?", (pid, user["user_id"])).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="计划不存在")
        try:
            tasks = _json.loads(row["tasks_json"])
        except Exception:
            tasks = []
        for t in tasks:
            t["progress"] = 0
            t["completed"] = False
        conn.execute(
            "UPDATE user_daily_plans SET tasks_json=?, completed_tasks=0, updated_at=? WHERE id=?",
            (_json.dumps(tasks, ensure_ascii=False), now, pid)
        )
        conn.commit()
    plan = get_or_create_daily_plan(user["user_id"], plan_date=row["plan_date"])
    return plan
