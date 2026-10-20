# ============================================================
# 限流辅助：每用户 LLM 配额（F-011）/ 登录注册限流（F-010 复用）
# 复用 db.redis_client 的 Redis 滑动窗口限流（RedisClient.check_rate_limit）。
#
# 计数落在哪里，取决于 check_rate_limit 走哪条路径（详见其 docstring）：
#   · Redis 启用 → Redis 原子滑动窗口，计数跨进程/跨 worker 共享。
#   · Redis 未启用（含 CI 与本机联调，二者都没有 Redis）→ **进程内滑动窗口兜底**
#     （RedisClient._local_rate_limit），同一 uid 的配额只由**单进程内存**计数；
#     多 worker 部署下每个 worker 各记一份、实际阈值被放大 workers 倍
#     （本部署受 vectordb_data/.import_writer.lock 单写者锁约束为 workers=1，
#      故与 Redis 计数等价）。生产(REDIS_STRICT)且未显式设
#     RATE_LIMIT_ALLOW_LOCAL_FALLBACK=1 时，这条路径改为 fail-closed 直接拒绝。
#
# ⚠️ 订正（2026-10-14）：本文件此前的头注释写「开发环境(Redis 未启用)：限流 fail-open
#    （放行），不影响本地联调」——该描述在「进程内兜底」落地后**已不成立**：无 Redis 的
#    进程同样会强制限额。这处失真把「整套测试成片 429」一度引向「环境噪声」的误判
#    （CI 与本机都无 Redis，而 tests/conftest.py 的 mock_auth 给**所有用例同一个 uid**，
#    全套件共用一个「每分钟 20 次」的窗口，跨用例累积后集体超限）。
#    测试侧的对应处置见 tests/conftest.py 的 `_reset_process_local_rate_windows`：
#    用例之间清空进程内窗口，不放行、不打桩。
# ============================================================

import logging

from fastapi import Depends, HTTPException

from shared.auth import get_current_user
# 边界常量单一真值源（REA #30）：数字与时间窗都在 shared/limits.py 具名，
# 本模块只引用名字。此处保留同名再导出，历史 `from shared.ratelimit import
# LLM_PER_MINUTE`（含 tests/test_ratelimit_circuit.py）不受影响。
from shared.limits import (
    LLM_PER_DAY,
    LLM_PER_MINUTE,
    WINDOW_LLM_DAY_SECONDS,
    WINDOW_LLM_MINUTE_SECONDS,
)

logger = logging.getLogger("netlearn.ratelimit")

# 每用户 LLM 配额上限（生产环境由 Redis 限流强制）。
# 阈值定义与依据见 shared/limits.py；可用 LLM_QUOTA_PER_MINUTE / LLM_QUOTA_PER_DAY 覆盖。


def _uid(user: dict) -> str:
    return user.get("user_id") or user.get("sub") or "anonymous"


def check_llm_quota(user: dict) -> None:
    """检查每用户 LLM 配额；超限抛 429。

    采用双窗口计数（每分钟 + 每日），防止单用户刷爆 LLM 通道。
    依赖 RedisClient.check_rate_limit：Redis 未启用时（开发）返回 True（放行）。
    """
    from db.redis_client import redis_client

    uid = _uid(user)
    if not redis_client.check_rate_limit(f"llm_min:{uid}", LLM_PER_MINUTE, WINDOW_LLM_MINUTE_SECONDS):
        logger.warning("LLM 每分钟配额超限 user=%s", uid)
        raise HTTPException(
            status_code=429,
            detail="LLM 调用过于频繁，请稍后再试（每分钟上限）",
        )
    if not redis_client.check_rate_limit(f"llm_day:{uid}", LLM_PER_DAY, WINDOW_LLM_DAY_SECONDS):
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
