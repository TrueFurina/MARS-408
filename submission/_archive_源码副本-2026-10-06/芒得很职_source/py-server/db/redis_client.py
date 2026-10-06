# ============================================================
# Redis 缓存客户端
# 用途：LLM 响应缓存、会话状态、限流、Agent 权重缓存
# ============================================================

import json
import logging
import os
from typing import Optional

from config import get_redis_config

logger = logging.getLogger("netlearn.redis")

# 生产环境(NETLEARN_ENV=production)下，Redis 不可用/异常时限流改为 fail-closed（拒绝请求），
# 避免登录/注册限流被静默关闭；开发环境保持 fail-open（放行），便于本地无 Redis 调试。
REDIS_STRICT = os.environ.get("NETLEARN_ENV", "development").lower() in ("production", "prod")

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    logger.warning("redis-py 未安装，Redis 不可用")
    REDIS_AVAILABLE = False


class RedisClient:
    """Redis 缓存封装，开发期不可用时静默降级"""

    def __init__(self):
        self._client = None
        self._enabled = False

    def connect(self) -> bool:
        config = get_redis_config()
        if not REDIS_AVAILABLE or not config.get("enabled", False):
            logger.info("Redis 未启用")
            return False

        try:
            self._client = redis.Redis(
                host=config.get("host", "localhost"),
                port=config.get("port", 6379),
                password=config.get("password", "") or None,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            self._client.ping()
            self._enabled = True
            logger.info("Redis 连接成功")
            return True
        except Exception as e:
            logger.warning(f"Redis 连接失败: {e}")
            self._enabled = False
            return False

    def disconnect(self):
        if self._client:
            self._client.close()
            self._enabled = False

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    # ── 通用缓存 ──

    def get(self, key: str) -> Optional[str]:
        if not self._enabled:
            return None
        try:
            return self._client.get(key)
        except Exception:
            return None

    def set(self, key: str, value: str, ttl: int = 3600):
        if not self._enabled:
            return
        try:
            self._client.setex(key, ttl, value)
        except Exception as e:
            logger.debug("redis set failed (fail-open): %s", e)

    def delete(self, key: str):
        if not self._enabled:
            return
        try:
            self._client.delete(key)
        except Exception as e:
            logger.debug("redis delete failed (fail-open): %s", e)

    # ── JSON 缓存 ──

    def get_json(self, key: str) -> Optional[dict | list]:
        val = self.get(key)
        if val:
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return None
        return None

    def set_json(self, key: str, data: dict | list, ttl: int = 3600):
        self.set(key, json.dumps(data, ensure_ascii=False), ttl)

    # ── LLM 响应缓存 ──

    def cache_llm_response(self, prompt_hash: str, response: str, ttl: int = 1800):
        """缓存 LLM 响应用于完全相同的请求（30分钟）"""
        self.set(f"llm:{prompt_hash}", response, ttl)

    def get_cached_llm_response(self, prompt_hash: str) -> Optional[str]:
        """获取缓存的 LLM 响应"""
        return self.get(f"llm:{prompt_hash}")

    # ── Agent 权重缓存 ──

    def cache_agent_weights(self, weights: dict[str, float], ttl: int = 600):
        """缓存 Agent 动态权重（10分钟）"""
        self.set_json("gomarl:agent_weights", weights, ttl)

    def get_agent_weights(self) -> Optional[dict]:
        """获取缓存的 Agent 权重"""
        return self.get_json("gomarl:agent_weights")

    # ── 限流 ──

    def check_rate_limit(self, key: str, max_requests: int, window: int = 60) -> bool:
        """滑动窗口限流：返回 True 表示允许，False 表示超限/被拒绝

        安全基线：生产环境(REDIS_STRICT)下，Redis 未启用或异常时返回 False（fail-closed），
        杜绝限流静默失效导致的暴力破解风险；开发环境返回 True（fail-open）。
        """
        if not self._enabled:
            if REDIS_STRICT:
                logger.error("Redis 未启用，限流 fail-closed 拒绝请求(key=%s)。生产环境请启用 Redis。", key)
                return False
            return True
        try:
            current = self._client.get(key)
            if current is None:
                self._client.setex(key, window, 1)
                return True
            count = int(current)
            if count >= max_requests:
                return False
            self._client.incr(key)
            return True
        except Exception as e:
            if REDIS_STRICT:
                logger.error("限流查询异常，fail-closed 拒绝请求(key=%s): %s", key, e)
                return False
            logger.warning("限流查询异常，开发环境 fail-open 放行(key=%s): %s", key, e)
            return True


# 全局单例
redis_client = RedisClient()
