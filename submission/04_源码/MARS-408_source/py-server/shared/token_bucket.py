# ============================================================
# 进程内令牌桶限流器（Token Bucket）— Redis 不可用时的本地兜底
#
# 用途（优先级4b）：
#   1. LLM 通道级令牌桶：每通道每秒令牌数限制，防止突发并发轰穿单 key
#   2. 接口级令牌桶：非流式 LLM 调用入口的进程内限流（Redis 未启用时兜底）
#
# 与 shared/ratelimit.py 的关系：
#   - ratelimit.py 依赖 Redis 滑动窗口（生产强制）
#   - 本模块是进程内兜底：Redis 未启用（开发/单机）时仍能限制突发并发
#
# 线程安全；令牌桶为进程级共享（单进程 workers=1 即全局生效）。
# ============================================================

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger("netlearn.token_bucket")


class TokenBucket:
    """进程内令牌桶

    每 rate_per_sec 秒补 1 个令牌，桶容量 capacity。
    consume() 成功则扣减令牌，失败返回 False（超限）。
    """

    def __init__(self, name: str, rate_per_sec: float = 5.0, capacity: Optional[int] = None):
        self.name = name
        self.rate_per_sec = max(rate_per_sec, 0.1)          # 最小 0.1/s 防止除零
        self.capacity = capacity or max(int(rate_per_sec * 2), 1)
        self._tokens = float(self.capacity)                  # 初始满桶
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate_per_sec)
        self._last_refill = now

    def consume(self, n: int = 1) -> bool:
        """尝试消费 n 个令牌；足够则扣减并返回 True，不足返回 False"""
        with self._lock:
            self._refill()
            if self._tokens >= n:
                self._tokens -= n
                return True
            return False

    def reset(self) -> None:
        with self._lock:
            self._tokens = float(self.capacity)
            self._last_refill = time.monotonic()

    def stats(self) -> dict:
        with self._lock:
            self._refill()
            return {
                "name": self.name,
                "tokens": round(self._tokens, 2),
                "capacity": self.capacity,
                "rate_per_sec": self.rate_per_sec,
            }


# ── 全局注册表 ──

_registry: dict[str, TokenBucket] = {}
_registry_lock = threading.Lock()


def get_bucket(name: str, rate_per_sec: float = 5.0,
               capacity: Optional[int] = None) -> TokenBucket:
    """获取（或创建）全局共享令牌桶"""
    with _registry_lock:
        if name not in _registry:
            _registry[name] = TokenBucket(name, rate_per_sec, capacity)
        return _registry[name]


def try_consume(name: str, n: int = 1) -> bool:
    """便捷函数：消费令牌，不足返回 False（不抛异常）"""
    bucket = get_bucket(name)
    return bucket.consume(n)


def reset_bucket(name: str) -> None:
    """手动重置令牌桶（满桶）"""
    bucket = get_bucket(name)
    bucket.reset()


def all_bucket_stats() -> dict:
    """全部令牌桶状态快照"""
    with _registry_lock:
        return {n: b.stats() for n, b in _registry.items()}
