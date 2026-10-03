# ============================================================
# 简单内存缓存 — 用于 API 端点响应缓存
# 减少重复 LLM 调用和数据库查询，提升响应速度
# ============================================================

import time
import logging
from typing import Optional, Any, Callable
from functools import wraps

logger = logging.getLogger("netlearn.cache")

# 内存缓存存储
_cache: dict[str, dict] = {}
_default_ttl = 60  # 默认缓存 60 秒


def get_cache_key(prefix: str, *args, **kwargs) -> str:
    """生成缓存键"""
    key_parts = [prefix]
    key_parts.extend(str(a) for a in args)
    key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
    return ":".join(key_parts)


def cached(ttl: int = _default_ttl):
    """缓存装饰器：缓存异步函数返回值

    Args:
        ttl: 缓存有效期（秒），默认 60s
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = get_cache_key(func.__name__, *args, **kwargs)
            now = time.time()

            # 检查缓存
            if cache_key in _cache:
                entry = _cache[cache_key]
                if now - entry["time"] < ttl:
                    logger.debug(f"缓存命中: {cache_key}")
                    return entry["data"]

            # 执行原函数
            result = await func(*args, **kwargs)

            # 写入缓存
            _cache[cache_key] = {
                "data": result,
                "time": now,
            }
            logger.debug(f"缓存写入: {cache_key} (TTL={ttl}s)")

            # 清理过期缓存（每 100 次写入触发一次）
            if len(_cache) > 1000:
                _cleanup()

            return result
        return wrapper
    return decorator


def _cleanup():
    """清理过期缓存条目"""
    now = time.time()
    expired = [k for k, v in _cache.items() if now - v["time"] > _default_ttl * 2]
    for k in expired:
        del _cache[k]
    if expired:
        logger.info(f"缓存清理: 移除 {len(expired)} 条过期条目")


def invalidate(prefix: str = None):
    """失效缓存

    Args:
        prefix: 缓存键前缀，None 则清空所有缓存
    """
    global _cache
    if prefix is None:
        _cache.clear()
        logger.info("缓存已全部清空")
    else:
        _cache = {k: v for k, v in _cache.items() if not k.startswith(prefix)}
        logger.info(f"缓存已清空: prefix={prefix}")


def cache_stats() -> dict:
    """返回缓存统计信息"""
    now = time.time()
    total = len(_cache)
    expired = sum(1 for v in _cache.values() if now - v["time"] > _default_ttl)
    return {
        "total_entries": total,
        "expired_entries": expired,
        "active_entries": total - expired,
        "default_ttl": _default_ttl,
    }