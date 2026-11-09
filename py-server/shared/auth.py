# ============================================================
# Auth - self-contained HMAC-SHA256 Token (zero external deps, JWT-equivalent)
# Design: no PyJWT / bcrypt. Use stdlib only so it runs in any environment.
# ============================================================

import os
import time
import json
import hmac
import hashlib
import base64
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Header, Request

logger = logging.getLogger("netlearn.auth")

# Token signing secret: lazily resolved by resolve_auth_secret() and cached in _SECRET.
# No hardcoded fallback value (the old netlearn-dev-secret-change-me-2026 is removed, F-005).
# In production, if AUTH_SECRET is missing or shorter than 32 chars -> raise (fail-fast / fail-closed).
_SECRET: Optional[str] = None
_TOKEN_TTL = 60 * 60 * 24 * 7  # 7 days


def resolve_auth_secret() -> str:
    """Resolve and return the JWT signing secret, caching it in module-level _SECRET.

    Security constraints (F-005):
    - Production (NETLEARN_ENV=production|prod) without AUTH_SECRET -> raise RuntimeError
      (fail-fast / fail-closed; never fall back to a hardcoded literal that lets attackers forge tokens).
    - Dev without AUTH_SECRET -> generate a random >=32-char secret and warn (invalidated on restart).
    - Any mode with AUTH_SECRET shorter than 32 chars -> raise (enforce minimum key length).
    main.py's lifespan calls this at startup so a missing production secret fails to boot;
    get_current_user / create_token also trigger lazy resolution when needed.
    """
    global _SECRET
    if _SECRET is not None:
        return _SECRET
    env = os.environ.get("NETLEARN_ENV", "development").lower()
    secret = (os.environ.get("AUTH_SECRET") or "").strip()
    if not secret:
        if env in ("production", "prod"):
            # Production must not use a temporary random key: missing => fail-fast,
            # avoid all users being logged out after restart / workers disagreeing on signature.
            raise RuntimeError(
                "Production requires the AUTH_SECRET environment variable (inject a strong "
                "random value via a secret manager, length >= 32). Refusing to boot with a "
                "temporary random key."
            )
        import secrets as _secrets
        secret = _secrets.token_urlsafe(32)
        logger.warning(
            "AUTH_SECRET is not set; generated a temporary random secret (all issued tokens "
            "will be invalid after restart). Set AUTH_SECRET in production."
        )
    if len(secret) < 32:
        raise RuntimeError(
            f"AUTH_SECRET must be >= 32 characters (current length {len(secret)}). "
            "Inject a stronger secret in production."
        )
    _SECRET = secret
    return _SECRET


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def create_token(user_id: str, role: str = "student") -> str:
    """Create a self-contained Token (header.payload.signature)."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + _TOKEN_TTL,
    }
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h}.{p}".encode("ascii")
    secret = resolve_auth_secret()
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url_encode(sig)}"


def verify_token(token: str) -> dict:
    """Verify Token, return payload; raise 401 if invalid/expired."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("malformed")
        h, p, sig = parts
        signing_input = f"{h}.{p}".encode("ascii")
        secret = resolve_auth_secret()
        expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_encode(expected), sig):
            raise ValueError("bad signature")
        payload = json.loads(_b64url_decode(p))
        if payload.get("exp", 0) < int(time.time()):
            raise ValueError("expired")
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired credentials")


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    x_app_token: Optional[str] = Header(default=None, alias="X-App-Token"),
    request: Request = None,
) -> dict:
    """FastAPI dependency: parse current user from `X-App-Token` (preferred) or `Authorization: Bearer`.

    为什么优先 ``X-App-Token``：发布沙箱（CloudStudio）的入口网关会把请求的
    ``Authorization`` 头**替换成平台自己的身份 token**（2026-10-15 实测：发
    ``Bearer FAKE_TEST_123`` 到达服务端的是 395 字符的 cloudstudio.net token），
    应用自己的 JWT 因此永远验不过；而自定义头（X-App-Token / Cookie）原样透传。
    本地/dev 无该网关，两个头都设时行为一致（X-App-Token 优先）。
    ⚠️ 两个参数都必须做 isinstance(str) 判定：FastAPI 依赖注入时它们是 str/None，
    但**直接调用**（单测、内部复用）时拿到的是 `Header(default=...)` **对象本身**——
    若不做类型判定，那个对象是 truthy，会被当成 token 传给 verify_token 并崩在
    `.split(".")`（AttributeError）。曾因此挂掉 test_valid_bearer_returns_user。
    """
    token = x_app_token if isinstance(x_app_token, str) else None
    if not token and isinstance(authorization, str) and authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):]
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in or missing credentials")
    payload = verify_token(token)
    user = {"user_id": payload["sub"], "role": payload.get("role", "student")}
    # 只读演示账号在任何写方法上就地拦截（2026-11-09）
    return enforce_readonly(user, request)


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency: admin only."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


def require_teacher(user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency: teacher or admin only.

    teacher 角色可通过 admin 端点 POST /api/admin/users 创建
    （由 api/admin_users.py 提供，需 admin 登录后调用）。

    允许 admin 或 role == "teacher" 通过，其余（如 student）返回 403。
    教师端 API 已改为使用 get_current_user 展示模拟数据，本依赖保留供后续正式权限控制使用。
    """
    role = user.get("role", "student")
    if role in ("admin", "teacher"):
        return user
    raise HTTPException(status_code=403, detail="需要教师或管理员权限")


def _is_demo_teacher_open() -> bool:
    """NETLEARN_DEMO_TEACHER_OPEN=1 时，教师端点权限放宽（仅演示用）。

    该开关仅用于本地/演示环境让 demo 学生账号也能预览教师仪表板，
    生产环境（NETLEARN_ENV=production）绝不应设置；放宽时会在审计日志打
    [DEMO-RELAX] 警告，保证审计链路诚实可见。
    """
    return os.environ.get("NETLEARN_DEMO_TEACHER_OPEN", "") in ("1", "true", "True", "yes")


# 生产环境开启演示放宽时，只允许这些演示账号（其余学生一律 403）。
_DEMO_TEACHER_ACCOUNTS = ("demo",)

# ── 只读演示账号（2026-11-09）──
# 背景：评审/演示需要一个"能看教师端、但不能改动任何数据"的账号。
# 现有 users.role 只有 student/teacher/admin 三种（api/admin_users.py:VALID_ROLES）。
# 这里采用**账号级禁写**而不是新增第五种角色：账号本身仍是 teacher（教师端可见），
# 但非安全方法（POST/PUT/PATCH/DELETE）在鉴权入口即被 403，不进入业务逻辑。
# 之所以不新增角色：`src/router/navConfig.ts` 的 resolveRole 会把未知角色兜底成
# student（路由守卫则直接重定向到 /），扩角色需要连带改前端映射与守卫，改动面更大；
# 账号级禁写只需一处收口。名单来自环境变量，不硬编码 user_id（账号重建后 ID 会变）。
_READONLY_ENV = "NETLEARN_READONLY_USERS"
# 只读账号可放行的「POST 承载读语义」接口（2026-11-09 复核补丁）。
# 背景：本仓库有多个 POST 路由实际是检索/报告/推荐（/literacy/class-report、
# /rag/search、/knowledge-base/search 等），按 HTTP 方法一刀切会把读功能误杀。
# 格式：逗号分隔的 `METHOD:/api/path`，精确匹配（不含 query）。
_READONLY_ALLOW_ENV = "NETLEARN_READONLY_ALLOW"
_SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def _readonly_user_ids() -> set:
    """读取只读账号 user_id 名单（逗号分隔），未配置则为空集。"""
    raw = os.environ.get(_READONLY_ENV, "")
    return {s.strip().lower() for s in raw.split(",") if s.strip()}


def _readonly_allow() -> set:
    """读取只读账号可用的非 GET 路径白名单，形如 {'POST:/API/LITERACY/CLASS-REPORT'}。"""
    raw = os.environ.get(_READONLY_ALLOW_ENV, "")
    out = set()
    for item in raw.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        out.add(item.upper().rstrip("/"))
    return out


def enforce_readonly(user: dict, request: object = None) -> dict:
    """只读账号的写操作闸门：安全方法放行，白名单内的读语义 POST 放行，其余 403。

    request 为 None 时（单测/内部直接调用）不拦截，保持既有调用兼容。
    """
    if request is None:
        return user
    method = str(getattr(request, "method", "GET")).upper()
    if method in _SAFE_METHODS:
        return user
    uid = str(user.get("user_id", "")).lower()
    if not uid or uid not in _readonly_user_ids():
        return user
    path = str(getattr(getattr(request, "url", None), "path", "")).rstrip("/")
    if ("%s:%s" % (method, path)).upper() in _readonly_allow():
        return user
    logger.warning("[READONLY] 只读账号 %s 试图执行 %s %s，已拒绝",
                   uid, method, path or "<unknown>")
    raise HTTPException(
        status_code=403,
        detail="该账号为只读演示账号，不允许执行任何写操作",
    )



def _demo_open_allowed(user: dict) -> bool:
    """演示放宽是否对**该用户**生效（2026-11-02 安全审计加固）。

    - 未设置 `NETLEARN_DEMO_TEACHER_OPEN` → False（默认严格）；
    - 非生产（dev/test）→ True（保持既有演示行为不变，兼容既有回归测试）；
    - 生产（`NETLEARN_ENV=production|prod`）→ **仅 `_DEMO_TEACHER_ACCOUNTS` 内的演示账号**。

    为什么生产必须收窄：审计实测，生产开启该开关时任意已登录学生都能通过教师门禁
    并读取全员能力画像（越权读）。开关的本意只是「让 demo 账号预览教师仪表板」，
    因此按账号收窄既保留演示能力，又消除越权面。
    """
    if not _is_demo_teacher_open():
        return False
    env = os.environ.get("NETLEARN_ENV", "development").lower()
    if env in ("production", "prod"):
        return str(user.get("user_id", "")) in _DEMO_TEACHER_ACCOUNTS
    return True


def require_teacher_or_demo_open(
    user: dict = Depends(get_current_user),
    request: Request = None,
) -> dict:
    """FastAPI dependency: 教师端端点权限控制。

    默认行为等同 require_teacher（仅 admin/teacher 放行，其余 403）。
    若设置了 NETLEARN_DEMO_TEACHER_OPEN=1（演示开关），则**非生产**环境允许任意已登录
    用户通过；**生产环境仅放行 `_DEMO_TEACHER_ACCOUNTS`（默认 demo）**——见
    `_demo_open_allowed` 的 2026-11-02 审计说明。放行时向审计日志写入清晰的
    [DEMO-RELAX] 警告（含用户与端点），既保留演示可用性，又保证放宽行为在审计轨迹中
    显式可见、永不静默。

    说明：演示账号 demo/demo123456 的角色为 student，因此演示环境必须打开该开关，
    否则教师仪表板对 demo 账号不可见。生产环境严禁设置该开关。
    """
    role = user.get("role", "student")
    if role in ("admin", "teacher"):
        return user
    if _demo_open_allowed(user):
        path = getattr(request, "url", None)
        path_str = str(path.path) if path is not None else "<unknown>"
        logger.warning(
            "[DEMO-RELAX] 教师端点 %s 权限放宽：用户 %s (role=%s) 以演示模式放行，"
            "未校验教师角色。生产环境请勿设置 NETLEARN_DEMO_TEACHER_OPEN。",
            path_str, user.get("user_id"), role,
        )
        return user
    raise HTTPException(status_code=403, detail="需要教师或管理员权限")


def require_self_or_teacher(user_id: str, user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency: 「自有数据」端点权限控制（本人 / 教师 / 管理员）。

    用于形如 `GET /xxx/{user_id}` 的**个人数据**端点：
    - 调用者身份（token sub）等于路径 `user_id` → 放行（本人读自己的数据）；
    - 角色为 admin / teacher → 放行（教师查学生，教学场景必需）；
    - 其余 → 403。

    **刻意不接入 `NETLEARN_DEMO_TEACHER_OPEN` 演示放宽**：该放宽是为了让 demo 学生账号
    预览教师仪表板；而本依赖守护的是「按 user_id 逐条读取的个人数据」，一旦放宽，
    演示环境里任何持 demo 账号者即可枚举学号读取任意学生数据（等于把 IDOR 原样放回）。
    本人自查场景不依赖该开关（token sub 与目标 user_id 相等即通过），故无需放宽。

    `user_id` 由 FastAPI 从同名路径参数自动注入，调用方不必显式传参。
    """
    if user.get("user_id") == user_id:
        return user
    if user.get("role") in ("admin", "teacher"):
        return user
    logger.warning(
        "越权读取被拒绝：用户 %s (role=%s) 请求 user_id=%s 的个人数据",
        user.get("user_id"), user.get("role", "student"), user_id,
    )
    raise HTTPException(status_code=403, detail="仅可查看本人的数据")
