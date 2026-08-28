# ============================================================
# API — 导入队列（/api/imports/*）  ADR-007
# 管理员提交导入任务，由后端内部 Worker 在进程内串行处理。
# 前端 Admin 面板 / CLI 客户端均通过此接口触发导入。
# ============================================================

import logging
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Body

from shared.auth import require_admin
from services.import_worker import (
    import_worker, STATUS_QUEUED, STATUS_RUNNING,
    STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELLED,
)
import services.import_worker as _iw_mod  # 动态引用模块级 DOCS_DIR（与 Worker 同一对象，可被测试 monkeypatch）

logger = logging.getLogger("netlearn.imports")
imports_router = APIRouter(prefix="/imports", tags=["imports"])


@imports_router.post("/submit")
async def submit_import(body: dict = Body(...), user=Depends(require_admin)):
    """提交单个导入任务。

    body: { type: "pdf"|"docling"|"textbook", source?: "scan"|"/path/to/file",
            params?: { rebuild, use_ocr, max_pages, subject_filter } }
    """
    if not import_worker._enabled:
        raise HTTPException(status_code=503, detail="导入 Worker 未启用（import_worker.enabled=false）")

    type_ = body.get("type", "pdf")
    if type_ not in ("pdf", "docling", "textbook"):
        raise HTTPException(status_code=400, detail="type 必须是 pdf/docling/textbook")
    source = body.get("source")  # "scan" 或显式路径；None 默认 scan
    if source and source != "scan":
        _src = Path(source)
        if not _src.is_absolute():
            _src = _iw_mod.DOCS_DIR / _src
        _src = _src.resolve()
        if _src.resolve() != _iw_mod.DOCS_DIR.resolve() and _iw_mod.DOCS_DIR.resolve() not in _src.parents:
            raise HTTPException(status_code=400, detail="source 必须位于 documents/教材 目录内（禁止越界访问服务器文件）")
    params = body.get("params", {}) or {}

    job_id = await import_worker.submit(type_, source, params, user.get("user_id", "admin"))
    return {"job_id": job_id, "status": STATUS_QUEUED}


@imports_router.post("/scan")
async def scan_import(body: dict = Body(default={}), user=Depends(require_admin)):
    """便捷接口：扫描 documents/教材 并提交导入。"""
    if not import_worker._enabled:
        raise HTTPException(status_code=503, detail="导入 Worker 未启用（import_worker.enabled=false）")
    type_ = body.get("type", "pdf")
    params = body.get("params", {}) or {}
    job_id = await import_worker.submit(type_, "scan", params, user.get("user_id", "admin"))
    return {"job_id": job_id, "status": STATUS_QUEUED}


@imports_router.get("/jobs")
async def list_jobs(status: Optional[str] = None, user=Depends(require_admin)):
    """列出导入任务（可按状态过滤）。"""
    return {"jobs": import_worker.list_jobs(status)}


@imports_router.get("/jobs/{job_id}")
async def get_job(job_id: str, user=Depends(require_admin)):
    """查询单个任务进度。"""
    job = import_worker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@imports_router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, user=Depends(require_admin)):
    """协作式取消：在当前文件处理完的间隙停止（无法中断正在进行的阻塞编码）。"""
    job = import_worker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job["status"] in (STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELLED):
        raise HTTPException(status_code=409, detail=f"任务已结束（{job['status']}）")
    ok = await import_worker.cancel(job_id)
    return {"job_id": job_id, "cancelled": ok, "status": job["status"]}
