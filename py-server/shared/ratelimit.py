# ============================================================
# 限流辅助：每用户 LLM 配额（F-011）/ 登录注册限流（F-010 复用）
# 复用 db.redis_client 的 Redis 滑动窗口限流（RedisClient.check_rate_limit）。
# 开发环境(Redis 未启用)：限流 fail-open（放行），不影响本地联调；
# 生产环境(REDIS_STRICT + Redis 启用)：真正强制限额。
# ============================================================

import os
import logging

from fastapi import Depends, HTTPException

from shared.auth import get_current_user

logger = logging.getLogger("netlearn.ratelimit")

# ── 每用户 LLM 配额上限（生产环境由 Redis 限流强制）──
# 可通过环境变量覆盖：LLM_QUOTA_PER_MINUTE / LLM_QUOTA_PER_DAY
LLM_PER_MINUTE = int(os.environ.get("LLM_QUOTA_PER_MINUTE", "20"))
LLM_PER_DAY = int(os.environ.get("LLM_QUOTA_PER_DAY", "500"))


def _uid(user: dict) -> str:
    return user.get("user_id") or user.get("sub") or "anonymous"


def check_llm_quota(user: dict) -> None:
    """检查每用户 LLM 配额；超限抛 429。

    采用双窗口计数（每分钟 + 每日），防止单用户刷爆 LLM 通道。
    依赖 RedisClient.check_rate_limit：Redis 未启用时（开发）返回 True（放行）。
    """
    from db.redis_client import redis_client

    uid = _uid(user)
    if not redis_client.check_rate_limit(f"llm_min:{uid}", LLM_PER_MINUTE, 60):
        logger.warning("LLM 每分钟配额超限 user=%s", uid)
        raise HTTPException(
            status_code=429,
            detail="LLM 调用过于频繁，请稍后再试（每分钟上限）",
        )
    if not redis_client.check_rate_limit(f"llm_day:{uid}", LLM_PER_DAY, 86400):
        logger.warning("LLM 每日配额超限 user=%s", uid)
        raise HTTPException(
            status_code=429,
            detail="今日 LLM 调用额度已用尽（每日上限）",
        )


def require_llm_quota(user: dict = Depends(get_current_user)) -> dict:
    """FastAPI 依赖：先鉴权(get_current_user)，再校验每用户 LLM 配额。

    用法：
      - 路由级：APIRouter(prefix=..., dependencies=[Depends(require_llm_quota)])
      - 端点级：async def x(user: dict = Depends(require_llm_quota)): ...
    """
    check_llm_quota(user)
    return user
