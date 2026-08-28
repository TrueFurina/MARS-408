# ============================================================
# API — 安全审计日志查询（/api/audit/*）
# admin/teacher 可查近期拦截/告警事件
# ============================================================

import logging
from fastapi import APIRouter, Depends, Query

from shared.auth import require_teacher
from shared.audit import query_audit_logs, get_audit_stats

logger = logging.getLogger("netlearn.audit_api")
router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs")
async def get_audit_logs(
    limit: int = Query(100, ge=1, le=500, description="返回条数上限"),
    action: str = Query(None, description="按事件类型过滤"),
    result: str = Query(None, description="按结果过滤: success/failure/blocked"),
    user: dict = Depends(require_teacher),
):
    """查询近期安全审计日志（admin/teacher 可查）。

    返回近期内容安全拦截、合规告警、幻觉检测等事件，
    按时间倒序排列。供审计日志页展示。
    """
    logs = query_audit_logs(limit=limit, action=action, result=result)
    return {"logs": logs, "count": len(logs)}


@router.get("/stats")
async def audit_stats(user: dict = Depends(require_teacher)):
    """审计事件统计摘要（供看板）。"""
    return get_audit_stats()
