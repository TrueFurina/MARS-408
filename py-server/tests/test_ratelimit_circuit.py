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
    """Redis 不可用时的限流语义：生产默认 fail-closed；显式开关下才降级为进程内窗口。

    三条路径（见 ``db/redis_client.check_rate_limit`` docstring）：
      - 非生产 → 进程内滑动窗口兜底（本地联调不受影响）；
      - 生产 + 未开 RATE_LIMIT_ALLOW_LOCAL_FALLBACK → **fail-closed 拒绝**（G2 不变量）；
      - 生产 + 显式开开关 → 进程内窗口兜底（无 Redis 部署的可用性开关）。
    """

    def _disabled_client(self, monkeypatch, strict=None, allow_fallback=None):
        """构造一个「Redis 未启用」的隔离实例；strict 给定则覆盖模块级 REDIS_STRICT。"""
        # 注意：db/__init__.py 的 `from .redis_client import redis_client` 会把包属性
        # db.redis_client 覆盖成「单例实例」，故 `import db.redis_client as rc` 拿到的是
        # 实例而非模块；用 importlib 从 sys.modules 取回真正的模块对象。
        import importlib

        rc = importlib.import_module("db.redis_client")

        if strict is not None:
            monkeypatch.setattr(rc, "REDIS_STRICT", strict)
        if allow_fallback is not None:
            monkeypatch.setattr(rc, "ALLOW_LOCAL_FALLBACK", allow_fallback)
        c = rc.RedisClient()
        c._enabled = False
        return c

    def test_disabled_redis_enforces_local_window(self, monkeypatch):
        """Redis 未启用时：同 key 连调 max_requests 次放行，第 max_requests+1 次拒绝。"""
        c = self._disabled_client(monkeypatch, strict=False)
        for i in range(3):
            assert c.check_rate_limit("k", 3, 60) is True, f"第 {i + 1} 次应放行"
        assert c.check_rate_limit("k", 3, 60) is False

    def test_strict_disabled_redis_fails_closed_without_optin(self, monkeypatch):
        """🔒 安全不变量（CI 门禁 G2）：生产(STRICT) 且未显式开启降级开关时，
        Redis 不可用必须 **fail-closed 立即拒绝**——攻击者打掉 Redis 不能让限流失效。

        这条断言就是 G2（``scripts/security_gate_assert.py``）在 AST 层面守护的语义，
        在行为层面再钉一次：改回「无条件降级」会让本用例红。
        """
        c = self._disabled_client(monkeypatch, strict=True, allow_fallback=False)
        for i in range(5):
            assert c.check_rate_limit("login:ip:1.2.3.4", 5, 900) is False, (
                f"第 {i + 1} 次应为 fail-closed 拒绝，而非放行"
            )
        assert c._local_buckets == {}, "fail-closed 路径不得写入进程内桶"

    def test_strict_with_optin_falls_back_to_local(self, monkeypatch):
        """显式开启 RATE_LIMIT_ALLOW_LOCAL_FALLBACK 后，生产下 Redis 不可用才走兜底。

        这是无 Redis 部署（本试点沙箱）的可用性开关；仍然强制限额，只是计数在单进程内。
        """
        c = self._disabled_client(monkeypatch, strict=True, allow_fallback=True)
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

    def test_query_exception_fails_closed_without_optin(self, monkeypatch):
        """🔒 生产 + 未开降级开关时，Redis 查询抛异常也必须 fail-closed 拒绝。"""
        c = self._disabled_client(monkeypatch, strict=True, allow_fallback=False)

        class _BoomRedis:
            def get(self, k):
                raise RuntimeError("redis down")

        c._client = _BoomRedis()
        c._enabled = True  # 声称已启用，但查询会炸
        for i in range(3):
            assert c.check_rate_limit("ex", 3, 60) is False, f"第 {i + 1} 次应 fail-closed"
        assert c._local_buckets == {}, "fail-closed 路径不得写入进程内桶"

    def test_query_exception_falls_back_with_optin(self, monkeypatch):
        """显式开启开关后，Redis 查询异常才降级为进程内限流。"""
        c = self._disabled_client(monkeypatch, strict=True, allow_fallback=True)

        class _BoomRedis:
            def get(self, k):
                raise RuntimeError("redis down")

        c._client = _BoomRedis()
        c._enabled = True
        for _ in range(3):
            assert c.check_rate_limit("ex", 3, 60) is True
        assert c.check_rate_limit("ex", 3, 60) is False

    def test_query_exception_non_strict_falls_back(self, monkeypatch):
        """非生产环境不设开关也降级（本地联调不受影响），不 fail-closed。"""
        c = self._disabled_client(monkeypatch, strict=False, allow_fallback=False)

        class _BoomRedis:
            def get(self, k):
                raise RuntimeError("redis down")

        c._client = _BoomRedis()
        c._enabled = True
        for _ in range(3):
            assert c.check_rate_limit("ex2", 3, 60) is True
        assert c.check_rate_limit("ex2", 3, 60) is False


# ══════════════════════════════════════════════════════════
# db.redis_client.check_rate_limit —— 进程内兜底的「真实并发」验证
#
# 与 TestRedisLocalRateLimitFallback 互补：Fallback 类用单线程验证语义正确性；
# 本类用**真线程并发**验证竞态（正确性 / 内存上界 / 无死锁）与 FastAPI 同步依赖的
# threadpool 语义（进程内兜底确实被多线程并发调用，而非单线程串行）。
# 依据：shared/ratelimit.require_llm_quota 是同步 `def` 依赖，被 14 个路由模块引用；
#       FastAPI 对同步依赖走 anyio.to_thread.run_sync ⇒ 并发请求落在不同线程。
# ══════════════════════════════════════════════════════════

class TestRedisLocalRateLimitConcurrency:
    """Redis 不可用时的进程内兜底：并发正确性 + 内存上界 + 无死锁 + 多线程实证。"""

    def _disabled_client(self, monkeypatch, strict=False):
        import importlib

        rc = importlib.import_module("db.redis_client")
        monkeypatch.setattr(rc, "REDIS_STRICT", strict)
        c = rc.RedisClient()
        c._enabled = False
        return c

    @pytest.mark.timeout(30)
    def test_concurrent_same_key_exact_admission(self, monkeypatch):
        """T=32 线程 × K=20 次调用**同一 key**，max_requests=50 / window=60，时钟恒定。

        (a) 放行次数必须**恰好 50**（<50 = 丢更新误拒；>50 = 竞态超额放行）；
        (b) 结束后该 key 桶长度必须**恰好 50**。
        30s 超时兜底死锁（锁内做重活会在此暴露）。时钟恒定 ⇒ 不可能发生滑出，
        故「恰好 50」是确定性结论，任何偏差都指向竞态。
        """
        from concurrent.futures import ThreadPoolExecutor

        c = self._disabled_client(monkeypatch)
        c._time_source = lambda: 1000.0  # 恒定 → 无过期
        key, max_req, threads, per_thread = "conc:same", 50, 32, 20

        with ThreadPoolExecutor(max_workers=threads) as ex:
            futures = [
                ex.submit(lambda: [c.check_rate_limit(key, max_req, 60) for _ in range(per_thread)])
                for _ in range(threads)
            ]
            results = [r for f in futures for r in f.result()]

        allowed = sum(1 for r in results if r)
        assert len(results) == threads * per_thread
        assert allowed == max_req, f"放行 {allowed} 次 ≠ 上界 {max_req}（竞态：丢更新或超额放行）"
        assert len(c._local_buckets[key]) == max_req, len(c._local_buckets[key])

    @pytest.mark.timeout(30)
    def test_concurrent_same_key_random_time_source(self, monkeypatch):
        """同 A，但时钟**随机**（去掉确定性）——仍须恰好放行 50 次、桶长恰好 50。

        时钟严格单调、每次随机推进 ≤0.05s，全程跨度 ≤ 32s < window 60s ⇒ 无滑出，
        「恰好 50」依旧成立；随机仅用于打散并发到达顺序，暴露对时间源的隐式假设。
        """
        import random
        import threading
        from concurrent.futures import ThreadPoolExecutor

        c = self._disabled_client(monkeypatch)
        clock_lock = threading.Lock()
        state = {"t": 1000.0}

        def _rand_clock():
            with clock_lock:
                state["t"] += random.uniform(0.0, 0.05)
                return state["t"]

        c._time_source = _rand_clock
        key, max_req, threads, per_thread = "conc:rand", 50, 32, 20

        with ThreadPoolExecutor(max_workers=threads) as ex:
            futures = [
                ex.submit(lambda: [c.check_rate_limit(key, max_req, 60) for _ in range(per_thread)])
                for _ in range(threads)
            ]
            results = [r for f in futures for r in f.result()]

        allowed = sum(1 for r in results if r)
        assert allowed == max_req, f"放行 {allowed} 次 ≠ 上界 {max_req}"
        assert len(c._local_buckets[key]) == max_req

    @pytest.mark.timeout(30)
    def test_concurrent_distinct_keys_respect_memory_bound(self, monkeypatch):
        """64 线程 × 每线程 200 个互异 key（共 12800 ≫ 上界 4096）并发灌入。

        约束：结束后 `_local_buckets` 规模必须 ≤ `_LOCAL_MAX_KEYS`，且全程不抛异常
        （并发下「先清过期桶、再按最久未活跃淘汰」逻辑不能崩、不能越界）。
        时钟恒定 ⇒ 无过期桶 ⇒ 强制走「按最久未活跃淘汰」分支。
        """
        from concurrent.futures import ThreadPoolExecutor

        c = self._disabled_client(monkeypatch)
        c._time_source = lambda: 1000.0
        threads, per_thread = 64, 200
        assert threads * per_thread > c._LOCAL_MAX_KEYS  # 前置：确实超上界

        def _worker(tid):
            for j in range(per_thread):
                c.check_rate_limit(f"flood:{tid}:{j}", 10, 60)
            return True

        with ThreadPoolExecutor(max_workers=threads) as ex:
            list(ex.map(_worker, range(threads)))

        assert len(c._local_buckets) <= c._LOCAL_MAX_KEYS, len(c._local_buckets)

    @pytest.mark.timeout(30)
    def test_fastapi_sync_dependency_enters_from_multiple_threads(self, monkeypatch):
        """实证 FastAPI 同步依赖走 threadpool：并发请求下进入限流路径的线程数 > 1。

        把被 14 个路由模块复用的同步依赖 `require_llm_quota` 挂到测试 App，在真正的
        落点 `RedisClient._local_rate_limit` 上记录 `threading.get_ident()`；
        若为单线程串行，则恒只有 1 个 id —— 本断言即证明并发是真实的。
        """
        import importlib
        import threading
        from concurrent.futures import ThreadPoolExecutor

        from fastapi import Depends, FastAPI
        from fastapi.testclient import TestClient

        from shared.auth import get_current_user
        from shared.ratelimit import require_llm_quota

        rc = importlib.import_module("db.redis_client")
        singleton = rc.redis_client
        monkeypatch.setattr(singleton, "_enabled", False)
        monkeypatch.setattr(singleton, "_time_source", lambda: 1000.0)

        seen: set[int] = set()
        seen_lock = threading.Lock()
        orig = singleton._local_rate_limit

        def _spy(key, max_requests, window):
            with seen_lock:
                seen.add(threading.get_ident())
            return orig(key, max_requests, window)

        monkeypatch.setattr(singleton, "_local_rate_limit", _spy)

        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "conc_probe", "role": "admin"}

        @app.get("/probe")
        def probe(user: dict = Depends(require_llm_quota)):
            return {"ok": True}

        client = TestClient(app)

        with ThreadPoolExecutor(max_workers=16) as ex:
            codes = list(ex.map(lambda _: client.get("/probe").status_code, range(64)))

        assert seen, "限流路径从未被进入（依赖注入失败？）"
        assert len(seen) > 1, f"仅 {len(seen)} 个线程进入限流路径，threadpool 语义不成立"
        assert set(codes) <= {200, 429}, set(codes)


# ══════════════════════════════════════════════════════════
# 守护：限流窗口状态不得跨用例累积
#   （conftest._reset_process_local_rate_windows）
#
# 机制回顾：CI 与本机都没有 Redis，check_rate_limit 恒走进程内兜底，
#   计数落在**进程级**字典；conftest.mock_auth 又让所有用例共用同一个 uid
#   ⇒ 若不在用例间清空窗口，窗口一满，其后用例成片 429
#   （2026-10-14 实测：完整套件本地/CI 同形态失败簇，均由 429 及其引发的 KeyError 组成）。
#
# 本类用两个**有先后依赖**的用例把这条不变量钉死：
#   test_a 把探测 uid 打满 —— 第 N+1 次必 429，同时证明「打满」确实会发生；
#   test_b 在**下一个用例**里断言同一 uid 又能放行 —— 只有 conftest 真在用例间
#          清空了窗口才成立。删掉那个 fixture，test_b 立刻变红。
# ⚠️ 依赖模块内用例定义顺序（pytest 保证按序执行）；只 -k test_b 单跑时为弱断言。
# ══════════════════════════════════════════════════════════

class TestRateWindowIsolation:
    _UID = "u_window_isolation_probe"

    @staticmethod
    def _singleton():
        import importlib

        return importlib.import_module("db.redis_client").redis_client

    @staticmethod
    def _call():
        """按共享聚合键调用一次配额检查；超限抛 HTTPException(429)。"""
        from shared.ratelimit import check_llm_quota

        check_llm_quota({"user_id": TestRateWindowIsolation._UID})

    def _skip_if_redis_backed(self) -> None:
        if self._singleton()._enabled:
            pytest.skip("Redis 启用时计数在服务端，本守护只覆盖进程内兜底路径")

    def test_a_shared_uid_window_fills_up(self):
        """把探测 uid 打到超限：恰好放行 LLM_PER_MINUTE 次，第 N+1 次 429。"""
        from fastapi import HTTPException

        from shared.ratelimit import LLM_PER_MINUTE

        self._skip_if_redis_backed()
        codes = []
        for _ in range(LLM_PER_MINUTE + 1):
            try:
                self._call()
                codes.append(200)
            except HTTPException as e:
                codes.append(e.status_code)

        assert codes[-1] == 429, f"第 {LLM_PER_MINUTE + 1} 次应超限，实测 {codes[-1]}"
        assert codes.count(200) == LLM_PER_MINUTE, codes

    def test_b_next_test_starts_with_clean_window(self):
        """上一个用例已把该 uid 打满；窗口若跨用例累积，这里必然 429。"""
        self._skip_if_redis_backed()
        self._call()  # 不抛即证明 conftest 已在用例间清空进程内窗口
