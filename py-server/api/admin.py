# ============================================================
# API — 管理员聚合（/api/admin/*）— 需管理员权限
# 汇总所有用户的学习数据与平台级看板统计
# ============================================================

import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from shared.auth import require_admin
from services.user_service import list_all_users, get_platform_stats

logger = logging.getLogger("netlearn.admin_api")
router = APIRouter(prefix="/admin", tags=["admin"])


# ── 响应模型（2026-10-29 补）──
# 此前 /admin/stats 返回裸 dict，前端 `api.get<any>` 后模板里 `stats.user_count`
# 一路 any，字段拼错也不会报。形状对齐 db/user_store.py::get_platform_stats。
class SubjectStat(BaseModel):
    total: int
    correct: int
    accuracy: float


class DailyQuizPoint(BaseModel):
    date: str
    count: int


class PlatformStats(BaseModel):
    """平台级看板统计。

    `by_subject` 的**键是科目名**（动态，随题库变化），故用 `dict[str, SubjectStat]`
    而不是固定字段；`daily_quiz` 固定 7 个点（近 7 日）。
    """
    user_count: int
    student_count: int
    admin_count: int
    active_users: int
    total_quiz: int
    correct_quiz: int
    overall_accuracy: float
    by_subject: dict[str, SubjectStat]
    daily_quiz: list[DailyQuizPoint]


@router.get("/users")
async def admin_users(admin: dict = Depends(require_admin)):
    """汇总所有用户：画像 / 答题 / 对话统计"""
    return {"users": list_all_users()}


@router.get("/stats", response_model=PlatformStats)
async def admin_stats(admin: dict = Depends(require_admin)):
    """平台级看板统计：用户数 / 活跃度 / 科目掌握度 / 7日答题趋势"""
    return get_platform_stats()
