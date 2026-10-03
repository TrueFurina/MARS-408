# ============================================================
# API — 管理员聚合（/api/admin/*）— 需管理员权限
# 汇总所有用户的学习数据与平台级看板统计
# ============================================================

import logging
from fastapi import APIRouter, Depends

from shared.auth import require_admin
from db.user_store import list_all_users, get_platform_stats

logger = logging.getLogger("netlearn.admin_api")
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
async def admin_users(admin: dict = Depends(require_admin)):
    """汇总所有用户：画像 / 答题 / 对话统计"""
    return {"users": list_all_users()}


@router.get("/stats")
async def admin_stats(admin: dict = Depends(require_admin)):
    """平台级看板统计：用户数 / 活跃度 / 科目掌握度 / 7日答题趋势"""
    return get_platform_stats()
