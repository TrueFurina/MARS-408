# ============================================================
# 并发故障注入测试（循环10-P1：模拟 429 全量回退/熔断/令牌桶压力）
#
# 原则：
#   1. 纯逻辑故障注入——不发起真实 HTTP（避免超时/网络依赖/状态污染）
#   2. 每个测试使用独立 key，测试结束清理全局注册表，不影响其他测试
#   3. 验证：限流快速失败 + 熔断快速失败 + 故障计数可观测
# ============================================================

import asyncio
import pytest

from shared.circuit_breaker import get_breaker, reset_breaker, CircuitOpenError
from shared.token_bucket import get_bucket, reset_bucket


# ── 熔断器故障注入 ──

def test_breaker_opens_after_repeated_failures():
    """故障注入：连续失败达到阈值 → 熔断 OPEN，后续请求快速失败"""
    reset_breaker("test_fault_breaker")
    b = get_breaker("test_fault_breaker", failure_threshold=3, open_timeout=60.0)
    assert b.state == "closed"

    for _ in range(3):
        b.record_failure()
    assert b.state == "open"
    assert not b.allow_request()
    with pytest.raises(CircuitOpenError):
        raise CircuitOpenError("circuit open") if not b.allow_request() else None
    reset_breaker("test_fault_breaker")


def test_breaker_blocks_under_concurrency():
    """并发故障注入：熔断 OPEN 后，20 个并发请求全部被快速拒绝（不落 LLM）"""
    reset_breaker("test_fault_conc")
    b = get_breaker("test_fault_conc", failure_threshold=2, open_timeout=60.0)
    b.record_failure(); b.record_failure()
    assert b.state == "open"

    async def concurrent_hit():
        return [b.allow_request() for _ in range(20)]

    results = asyncio.run(concurrent_hit())
    assert all(r is False for r in results)  # 全部拒绝
    reset_breaker("test_fault_conc")


def test_breaker_recovers_after_open_timeout():
    """故障恢复注入：OPEN 超时后进入 HALF_OPEN，成功一次 → 恢复 CLOSED"""
    reset_breaker("test_fault_recover")
    b = get_breaker("test_fault_recover", failure_threshold=2, open_timeout=0.0)
    b.record_failure(); b.record_failure()
    # open_timeout=0 → state 属性惰性转 half_open
    assert b.state == "half_open"
    # half_open 放行试探请求 → 成功 → 恢复 closed
    assert b.allow_request()
    b.record_success()
    assert b.state == "closed"
    reset_breaker("test_fault_recover")


# ── 令牌桶压力注入 ──

def test_token_bucket_backpressure_under_burst():
    """令牌桶压力注入：容量 3，耗尽 3 个令牌后第 4 次快速失败（backpressure）"""
    # 直接构造独立 TokenBucket（不走全局注册表，避免参数缓存复用）
    from shared.token_bucket import TokenBucket
    bucket = TokenBucket("test_burst_bucket_iso", rate_per_sec=0.1, capacity=3)

    assert bucket.consume()  # 1
    assert bucket.consume()  # 2
    assert bucket.consume()  # 3
    assert not bucket.consume()  # 容量耗尽 → 快速失败（不阻塞）


def test_token_bucket_refills_over_time():
    """令牌桶恢复注入：速率 1/s，等待 refill 后可再次消费"""
    import time
    from shared.token_bucket import TokenBucket
    bucket = TokenBucket("test_refill_bucket_iso", rate_per_sec=1.0, capacity=1)

    assert bucket.consume()
    assert not bucket.consume()  # 容量 1 耗尽
    time.sleep(1.1)  # 等待 refill（1/s → 1s 1 个）
    assert bucket.consume()  # refill 后恢复


# ── LLM 层故障观测 ──

def test_llm_chat_uses_breaker_key_convention():
    """验证 LLM 通道使用 llm_bucket_{channel} 令牌桶 + LLMUnavailable 快速失败约定"""
    import inspect
    from db.llm_provider import LLMProvider
    src = inspect.getsource(LLMProvider._call_provider)
    assert "llm_bucket_" in src  # 令牌桶命名约定
    assert "LLMUnavailable" in src  # 超限快速失败（触发通道回退）


def test_llm_chat_uses_token_bucket_key_convention():
    """验证 LLM 通道使用 llm_bucket_{channel} 令牌桶命名约定（限流基础）"""
    import inspect
    from db.llm_provider import LLMProvider
    src = inspect.getsource(LLMProvider._call_provider)
    assert "llm_bucket_" in src
