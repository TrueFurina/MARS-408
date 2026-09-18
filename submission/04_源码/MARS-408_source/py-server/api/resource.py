# ============================================================
# 可复用学习资源池 API（/api/resource/*）
# 通过质量审查的生成资源登记为用户私有资源，可重复使用
# 移植自 OS_course learning_resource_service：内容哈希去重 + 幂等登记
# ============================================================

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from shared.auth import get_current_user

logger = logging.getLogger("netlearn.resource")
router = APIRouter(prefix="/resource", tags=["resource"])


class RegisterResourceRequest(BaseModel):
    resource_type: str = Field("reading_material", max_length=50, description="资源类型")
    title: str = Field("", max_length=200, description="资源标题")
    content: dict = Field(default_factory=dict, description="资源内容")
    quality_score: Optional[float] = Field(None, ge=0, le=100, description="质量评分（可选）")


class ResourceIdRequest(BaseModel):
    resource_id: int = Field(..., gt=0, description="资源 ID")


@router.post("/register")
async def register_resource(req: RegisterResourceRequest, user: dict = Depends(get_current_user)):
    """登记可复用资源（内容哈希相同则幂等返回已有资源）"""
    from db.user_store import register_learning_resource

    if not req.content:
        raise HTTPException(status_code=422, detail="资源内容不能为空")
    resource = register_learning_resource(
        owner_user_id=user.get("user_id", ""),
        resource_type=req.resource_type,
        title=req.title,
        content=req.content,
        quality_score=req.quality_score,
    )

    # L1/L2/L3 三层学情记忆联动（低侵入：资源登记入 L3 情景记忆，供资源复用追溯）
    try:
        user_id = user.get("user_id", "")
        if user_id:
            from db import memory_store as _ms
            _ms.append_episode(user_id, "resource", {
                "resource_id": resource.get("id"),
                "resource_type": req.resource_type,
                "title": req.title[:100],
            })
    except Exception as _me:
        logger.debug(f"资源记忆写入失败(忽略): {_me}")

    return {"status": "ok", "resource": resource}


@router.get("/list")
async def list_resources(user: dict = Depends(get_current_user)):
    """列出当前用户的可复用资源（直接打开，也可重新生成）"""
    from db.user_store import list_learning_resources

    resources = list_learning_resources(user.get("user_id", ""))
    return {"status": "ok", "resources": resources, "total": len(resources)}


@router.get("/{resource_id}")
async def get_resource(resource_id: int, user: dict = Depends(get_current_user)):
    """获取单个资源（仅本人私有资源）"""
    from db.user_store import get_learning_resource

    resource = get_learning_resource(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="资源不存在")
    if resource.get("owner_user_id") != user.get("user_id", ""):
        raise HTTPException(status_code=403, detail="无权访问该资源")
    return {"status": "ok", "resource": resource}


@router.post("/delete")
async def delete_resource(req: ResourceIdRequest, user: dict = Depends(get_current_user)):
    """软删除用户私有资源"""
    from db.user_store import delete_learning_resource

    deleted = delete_learning_resource(req.resource_id, user.get("user_id", ""))
    if not deleted:
        raise HTTPException(status_code=404, detail="资源不存在或无权删除")
    return {"status": "ok", "deleted": True}
