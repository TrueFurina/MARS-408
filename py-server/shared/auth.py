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

from fastapi import Depends, HTTPException, Header

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


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    """FastAPI dependency: parse current user from `Authorization: Bearer <token>`."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not logged in or missing credentials")
    token = authorization[len("Bearer "):]
    payload = verify_token(token)
    return {"user_id": payload["sub"], "role": payload.get("role", "student")}


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
