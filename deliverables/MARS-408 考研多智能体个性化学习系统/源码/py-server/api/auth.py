# ============================================================
# API — 认证（/api/auth/*）
# 注册 / 登录 / 当前用户 / 登出
# ============================================================

import logging
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from shared.auth import create_token, get_current_user
from shared.errors import ValidationError, ResourceNotFoundError
from db.user_store import create_user, authenticate, get_user_by_id
from db.redis_client import redis_client
from shared.audit import log_event

logger = logging.getLogger("netlearn.auth_api")
router = APIRouter(prefix="/auth", tags=["auth"])

# ── 速率限制（Redis 回退）──

def _check_rate_limit(key: str, max_requests: int, window: int) -> None:
    """检查速率限制，超限时抛出 ValidationError"""
    if not redis_client.check_rate_limit(key, max_requests, window):
        raise ValidationError(detail="操作过于频繁，请稍后再试")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=8, max_length=128, description="密码至少8位，建议包含字母和数字")
    display_name: str = Field("", max_length=100)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    user: dict
    diagnostic_required: bool = False


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, request: Request):
    """注册新用户，自动登录并返回 Token（限流：3 次/小时/IP）"""
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(f"register:{client_ip}", max_requests=3, window=3600)
    try:
        user = create_user(req.username, req.password, req.display_name)
    except ValueError as e:
        log_event("register", ip=client_ip, result="failure", detail=str(e))
        raise ValidationError(detail=str(e))
    token = create_token(user["id"], user["role"])
    log_event("register", user_id=user["id"], ip=client_ip, result="success", detail=f"username={req.username}")
    logger.info(f"新用户注册: {user['username']} (role={user['role']})")
    return TokenResponse(token=token, user=user)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    """用户/管理员登录（限流：10 次/分钟/IP + 账户级 5 次/15 分钟）"""
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(f"login:ip:{client_ip}", max_requests=10, window=60)
    _check_rate_limit(f"login:user:{req.username}", max_requests=5, window=900)
    user = authenticate(req.username, req.password)
    if not user:
        log_event("login", ip=client_ip, result="failure", detail=f"username={req.username}")
        raise ValidationError(detail="用户名或密码错误")
    token = create_token(user["id"], user["role"])
    log_event("login", user_id=user["id"], ip=client_ip, result="success")
    # 检查是否需要入学测评
    diagnostic_required = False
    try:
        from db.user_store import get_profile
        profile = get_profile(user["id"])
        if not profile or not profile.get("diagnostic_completed"):
            diagnostic_required = True
    except Exception:
        diagnostic_required = True
    return TokenResponse(token=token, user=user, diagnostic_required=diagnostic_required)


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    """获取当前登录用户信息"""
    full = get_user_by_id(user["user_id"])
    if not full:
        raise ResourceNotFoundError(resource="用户")
    return full


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    """登出（无状态 Token：前端丢弃即可）"""
    return {"status": "ok", "user_id": user["user_id"]}
