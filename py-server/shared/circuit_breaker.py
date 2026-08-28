# ============================================================
# 通用熔断器（Circuit Breaker）— 接口级 / 通道级故障隔离
#
# 用途（优先级4b）：
#   1. LLM 通道级熔断：某通道连续失败 N 次 → 熔断该通道 M 秒，
#      避免对已宕机通道反复重试拖慢整体（快速失败）
#   2. 任意外部依赖/接口的故障隔离：单点故障不拖垮主链路
#
# 状态机: CLOSED(正常) → OPEN(熔断) → HALF_OPEN(半开试探) → CLOSED/OPEN
# 线程安全；进程内共享（单进程 workers=1 场景即全局生效）。
# ============================================================

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger("netlearn.circuit")


class CircuitBreaker:
    """通用熔断器

    用法：
        cb = CircuitBreaker(name="llm_qwen", failure_threshold=3, open_timeout=30)
        if not cb.allow_request():
            raise CircuitOpenError(...)
        try:
            ...
            cb.record_success()
        except Exception:
            cb.record_failure()
            raise
    """

    def __init__(self, name: str, failure_threshold: int = 3,
                 open_timeout: float = 30.0, half_open_max: int = 1):
        self.name = name
        self.failure_threshold = failure_threshold
        self.open_timeout = open_timeout
        self.half_open_max = half_open_max
        self._state = "closed"
        self._failures = 0
        self._opened_at = 0.0
        self._half_open_attempts = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            # OPEN 超时 → 自动转 HALF_OPEN（惰性）
            if self._state == "open" and time.time() - self._opened_at >= self.open_timeout:
                self._state = "half_open"
                self._half_open_attempts = 0
            return self._state

    def allow_request(self) -> bool:
        """是否放行请求：CLOSED/HALF_OPEN(未超配额) 放行；OPEN 拒绝"""
        st = self.state
        if st == "open":
            return False
        if st == "half_open":
            with self._lock:
                if self._half_open_attempts >= self.half_open_max:
                    return False  # 半开仅放行 1 个试探请求
                self._half_open_attempts += 1
        return True

    def record_success(self) -> None:
        with self._lock:
            self._state = "closed"
            self._failures = 0
            self._half_open_attempts = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._state = "open"
                self._opened_at = time.time()
                self._half_open_attempts = 0
                logger.warning(
                    "熔断器 %s 触发: %d 次连续失败 → OPEN(熔断 %.0fs)",
                    self.name, self.failure_threshold, self.open_timeout,
                )

    def reset(self) -> None:
        with self._lock:
            self._state = "closed"
            self._failures = 0
            self._half_open_attempts = 0

    def stats(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "failures": self._failures,
            "failure_threshold": self.failure_threshold,
            "open_timeout": self.open_timeout,
        }


class CircuitOpenError(RuntimeError):
    """熔断器 OPEN 状态错误（请求被快速失败）"""


# ── 全局注册表（按 name 共享实例，跨模块复用同一熔断状态）──

_registry: dict[str, CircuitBreaker] = {}
_registry_lock = threading.Lock()


def get_breaker(name: str, **kwargs) -> CircuitBreaker:
    """获取（或创建）全局共享熔断器实例"""
    with _registry_lock:
        if name not in _registry:
            _registry[name] = CircuitBreaker(name=name, **kwargs)
        return _registry[name]


def reset_breaker(name: str) -> Optional[CircuitBreaker]:
    """手动重置熔断器（管理端点用）"""
    with _registry_lock:
        cb = _registry.get(name)
    if cb:
        cb.reset()
    return cb


def all_breaker_stats() -> dict:
    """全部熔断器状态快照（监控端点用）"""
    with _registry_lock:
        return {n: cb.stats() for n, cb in _registry.items()}
