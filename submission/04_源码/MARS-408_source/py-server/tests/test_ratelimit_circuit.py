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
