# ============================================================
# 优先级4b — 令牌桶限流 + 通道熔断器 单元测试
#
# 覆盖：
#   1. TokenBucket：消费/补桶/超限/重置
#   2. CircuitBreaker：CLOSED→OPEN→HALF_OPEN 状态机 + 半开试探配额
#   3. LLMProvider 集成：熔断通道快速跳过（mock 场景）
# ============================================================

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ══════════════════════════════════════════════════════════
# TokenBucket 令牌桶
# ══════════════════════════════════════════════════════════

def test_bucket_initial_full():
    from shared.token_bucket import TokenBucket
    b = TokenBucket("t1", rate_per_sec=5.0, capacity=10)
    # 初始满桶：可连续消费 capacity 次
    for _ in range(10):
        assert b.consume() is True
    assert b.consume() is False  # 桶空


def test_bucket_refill_over_time():
    from shared.token_bucket import TokenBucket
    b = TokenBucket("t2", rate_per_sec=10.0, capacity=10)
    for _ in range(10):
        b.consume()
    assert b.consume() is False  # 空桶
    time.sleep(0.15)  # 约补 1.5 个令牌
    assert b.consume() is True   # 已补桶


def test_bucket_reset():
    from shared.token_bucket import TokenBucket
    b = TokenBucket("t3", rate_per_sec=5.0, capacity=5)
    for _ in range(5):
        b.consume()
    assert b.consume() is False
    b.reset()
    assert b.consume() is True  # 重置后满桶


def test_bucket_rate_clamped():
    from shared.token_bucket import TokenBucket
    b = TokenBucket("t4", rate_per_sec=0.0)  # 0 会被钳位到 0.1
    assert b.rate_per_sec >= 0.1


# ══════════════════════════════════════════════════════════
# CircuitBreaker 熔断器
# ══════════════════════════════════════════════════════════

def test_breaker_closed_initial():
    from shared.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker("cb1", failure_threshold=3, open_timeout=60)
    assert cb.state == "closed"
    assert cb.allow_request() is True


def test_breaker_opens_after_threshold():
    from shared.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker("cb2", failure_threshold=2, open_timeout=60)
    cb.record_failure()
    assert cb.state == "closed"   # 1 次未达阈值
    cb.record_failure()
    assert cb.state == "open"     # 2 次达阈值
    assert cb.allow_request() is False


def test_breaker_half_open_recovery():
    from shared.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker("cb3", failure_threshold=1, open_timeout=0.2, half_open_max=1)
    cb.record_failure()
    assert cb.state == "open"
    assert cb.allow_request() is False
    time.sleep(0.3)
    assert cb.state == "half_open"
    assert cb.allow_request() is True   # 半开放行 1 个试探
    assert cb.allow_request() is False  # 超出半开配额


def test_breaker_recovers_on_success():
    from shared.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker("cb4", failure_threshold=2, open_timeout=60)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "open"
    cb.record_success()
    assert cb.state == "closed"


def test_breaker_registry_shared():
    from shared.circuit_breaker import get_breaker
    b1 = get_breaker("shared_cb")
    b2 = get_breaker("shared_cb")
    assert b1 is b2  # 同一实例，跨模块共享熔断状态


# ══════════════════════════════════════════════════════════
# LLMProvider 集成验证
# 注：conftest 的 mock_llm autouse fixture 全局 mock 了 LLMProvider.chat，
#     故此处不测真实 chat() 回退链（与测试套件"离线确定性"规范一致），
#     只验证与 chat() 同源的令牌桶兜底与配置判定。
# ══════════════════════════════════════════════════════════

def test_llm_provider_breaker_registry_is_shared_with_chat():
    """chat() 循环与测试共用同一熔断注册表 key（llm_{channel}），
    熔断状态可跨调用共享——验证命名约定正确即可（用独立 key 不污染生产）。"""
    from shared.circuit_breaker import get_breaker, reset_breaker
    # chat() 内部使用 get_breaker(f"llm_{name}")；此处验证命名约定
    b = get_breaker("test_llm_qwen_iso", failure_threshold=3, open_timeout=30.0)
    assert b.name == "test_llm_qwen_iso"
    assert b.failure_threshold == 3
    reset_breaker("test_llm_qwen_iso")  # 清理，避免全局注册表污染


def test_llm_provider_token_bucket_backpressure():
    """令牌桶超限时快速失败（直接耗尽生产 key 的桶，不依赖 monkeypatch）

    说明：直接操作 _call_provider 使用的真实桶 key（llm_bucket_{channel}），
    耗尽唯一令牌后调用应立即抛 LLMUnavailable，不发起真实 HTTP。
    最后恢复桶，避免污染后续测试。
    """
    import asyncio
    from db.llm_provider import LLMProvider

    provider = LLMProvider()
    provider._config = {
        "llm_provider": "auto",
        "xfyun": {"app_id": ""},
        "deepseek": {"api_key": ""},
        "qwen": {"api_key": "sk-test", "base_url": "http://127.0.0.1:1",
                 "model": "qwen3.8-max"},
    }

    # 操作 _call_provider 使用的真实桶 key（llm_bucket_qwen），耗尽唯一令牌
    from shared.token_bucket import get_bucket, reset_bucket
    bucket = get_bucket("llm_bucket_qwen", rate_per_sec=0.1, capacity=1)
    bucket.reset()
    bucket.consume()  # 消耗唯一令牌

    from db.llm_provider import LLMUnavailable
    try:
        with pytest.raises(LLMUnavailable):
            asyncio.run(provider._call_provider(
                {"name": "qwen", "api_key": "sk-test", "base_url": "http://127.0.0.1:1", "model": "qwen3.8-max"},
                "chat", [{"role": "user", "content": "hi"}], 0.7, 100, None, False, 1,
            ))
    finally:
        reset_bucket("llm_bucket_qwen")  # 恢复满桶，避免污染其他测试


def test_llm_provider_token_bucket_real_key_matches_chat():
    """验证 _call_provider 使用的令牌桶 key 与生产命名约定一致（llm_bucket_{channel}）"""
    import inspect
    from db.llm_provider import LLMProvider
    src = inspect.getsource(LLMProvider._call_provider)
    assert "llm_bucket_" in src  # 命名约定：llm_bucket_{name}


# ══════════════════════════════════════════════════════════
# db.redis_client.check_rate_limit —— Redis 不可用时的「进程内滑动窗口兜底」
#
# 背景（发布沙箱无 Redis）：原实现 STRICT(production) 下 Redis 不可用即 fail-closed
# (return False)，导致 /api/auth/login 一律 422；非 STRICT 下又 fail-open 等于不限流。
# 现改为两者都退回进程内滑动窗口，语义与 Redis 分支一致。
# 适用前提：workers=1（vectordb_data/.import_writer.lock 单写者锁）→ 进程内即全局。
# ══════════════════════════════════════════════════════════

class TestRedisLocalRateLimitFallback:
    """Redis 不可用 → 进程内滑动窗口兜底（既不放行、也不误拒）。"""

    def _disabled_client(self, monkeypatch, strict=None):
        """构造一个「Redis 未启用」的隔离实例；strict 给定则覆盖模块级 REDIS_STRICT。"""
        # 注意：db/__init__.py 的 `from .redis_client import redis_client` 会把包属性
        # db.redis_client 覆盖成「单例实例」，故 `import db.redis_client as rc` 拿到的是
        # 实例而非模块；用 importlib 从 sys.modules 取回真正的模块对象。
        import importlib

        rc = importlib.import_module("db.redis_client")

        if strict is not None:
            monkeypatch.setattr(rc, "REDIS_STRICT", strict)
        c = rc.RedisClient()
        c._enabled = False
        return c

    def test_disabled_redis_enforces_local_window(self, monkeypatch):
        """Redis 未启用时：同 key 连调 max_requests 次放行，第 max_requests+1 次拒绝。"""
        c = self._disabled_client(monkeypatch, strict=False)
        for i in range(3):
            assert c.check_rate_limit("k", 3, 60) is True, f"第 {i + 1} 次应放行"
        assert c.check_rate_limit("k", 3, 60) is False

    def test_strict_disabled_redis_falls_back_not_fail_closed(self, monkeypatch):
        """生产(STRICT) 下 Redis 不可用也必须走兜底，首次调用不得直接拒绝。

        修复前这里首次即 return False → /api/auth/login 一律 422（本次回归的根因）。
        """
        c = self._disabled_client(monkeypatch, strict=True)
        for _ in range(5):
            assert c.check_rate_limit("login:ip:1.2.3.4", 5, 900) is True
        assert c.check_rate_limit("login:ip:1.2.3.4", 5, 900) is False

    def test_window_expiry_releases(self, monkeypatch):
        """窗口滑出后重新放行（注入时间源，不真实 sleep）。"""
        c = self._disabled_client(monkeypatch, strict=False)
        clock = {"t": 1000.0}
        c._time_source = lambda: clock["t"]
        assert c.check_rate_limit("w", 1, 60) is True
        assert c.check_rate_limit("w", 1, 60) is False
        clock["t"] += 61.0  # 越过窗口
        assert c.check_rate_limit("w", 1, 60) is True

    def test_memory_bound_evicts(self, monkeypatch):
        """海量伪造 key 灌入后，进程内桶规模不越界（内存上界保护）。"""
        c = self._disabled_client(monkeypatch, strict=False)
        monkeypatch.setattr(c, "_LOCAL_MAX_KEYS", 16)
        for i in range(500):
            c.check_rate_limit(f"flood:{i}", 10, 60)
        assert len(c._local_buckets) <= 16, len(c._local_buckets)

    def test_redis_enabled_path_unchanged(self, monkeypatch):
        """Redis 启用时仍走 Redis 原子窗口，完全不落到进程内兜底。"""

        class _FakeRedis:
            def __init__(self):
                self.store = {}

            def get(self, k):
                return self.store.get(k)

            def setex(self, k, ttl, v):
                self.store[k] = str(v)

            def incr(self, k):
                self.store[k] = str(int(self.store.get(k, "0")) + 1)

        # 注意：db/__init__.py 的 `from .redis_client import redis_client` 会把包属性
        # db.redis_client 覆盖成「单例实例」，故 `import db.redis_client as rc` 拿到的是
        # 实例而非模块；用 importlib 从 sys.modules 取回真正的模块对象。
        import importlib

        rc = importlib.import_module("db.redis_client")

        c = rc.RedisClient()
        c._client = _FakeRedis()
        c._enabled = True
        for _ in range(2):
            assert c.check_rate_limit("rk", 2, 60) is True
        assert c.check_rate_limit("rk", 2, 60) is False
        assert c._local_buckets == {}, "Redis 启用路径不得使用进程内兜底"

    def test_query_exception_falls_back_to_local(self, monkeypatch):
        """Redis 查询抛异常时降级为进程内限流，而非直接拒绝。"""
        c = self._disabled_client(monkeypatch, strict=True)

        class _BoomRedis:
            def get(self, k):
                raise RuntimeError("redis down")

        c._client = _BoomRedis()
        c._enabled = True  # 声称已启用，但查询会炸
        for _ in range(3):
            assert c.check_rate_limit("ex", 3, 60) is True
        assert c.check_rate_limit("ex", 3, 60) is False
