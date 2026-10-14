# ============================================================
# Redis 缓存客户端
# 用途：LLM 响应缓存、会话状态、限流、Agent 权重缓存
# ============================================================

import json
import logging
import os
import threading
import time
from collections import deque
from typing import Optional

from config import get_redis_config

logger = logging.getLogger("netlearn.redis")

# 生产环境(NETLEARN_ENV=production)标记。它决定「Redis 不可用 → 限流 fail-closed」。
REDIS_STRICT = os.environ.get("NETLEARN_ENV", "development").lower() in ("production", "prod")

# 「Redis 不可用时降级为进程内滑动窗口限流」的**显式开关**（默认关闭）。
#
# 🔒 默认关闭 ⇒ 生产环境 Redis 不可用仍 **fail-closed 拒绝请求**，这是 CI 安全门禁
#    G2（`scripts/security_gate_assert.py::assert_g2_rate_limit_fail_closed`）固化的
#    安全不变量：**攻击者打掉 Redis 不能使限流失效**。不要为了让某次部署跑起来就
#    把默认值翻成 True——那等于移除该不变量。
#
# 仅在**设计上就没有 Redis 的部署**（本试点沙箱无缓存/队列）显式打开：此时以进程内
# 滑动窗口替代，**仍然强制限额（不是放行）**，只是计数落在单进程内。
# 代价：多 worker 下每个 worker 各记一份、实际阈值被放大 workers 倍；本部署被
# `vectordb_data/.import_writer.lock` 单写者锁约束为 workers=1 ⇒ 与 Redis 计数等价。
ALLOW_LOCAL_FALLBACK = os.environ.get(
    "RATE_LIMIT_ALLOW_LOCAL_FALLBACK", ""
).lower() in ("1", "true", "yes", "on")

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    logger.warning("redis-py 未安装，Redis 不可用")
    REDIS_AVAILABLE = False


class RedisClient:
    """Redis 缓存封装，开发期不可用时静默降级"""

    # 进程内兜底限流的 key 上界：防止被海量（如伪造头生成的）key 打爆内存。
    _LOCAL_MAX_KEYS = 4096

    def __init__(self):
        self._client = None
        self._enabled = False
        # 进程内滑动窗口限流：key → 最近 window 秒内的请求时间戳 deque。
        # 仅在 Redis 不可用/异常时使用（见 check_rate_limit）。
        self._local_buckets: dict[str, deque[float]] = {}
        self._local_lock = threading.Lock()
        # 时间源可注入（默认单调时钟），便于测试确定性地推进窗口而无需真实 sleep。
        self._time_source = time.monotonic

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

    def _local_rate_limit(self, key: str, max_requests: int, window: int) -> bool:
        """进程内滑动窗口限流（Redis 不可用时的兜底）。

        语义与 Redis 分支完全一致：``window`` 秒内允许 ``max_requests`` 次；
        超限返回 False，未超限返回 True（并计入本次）。实现为「每 key 一个时间戳
        deque + 一把可重入安全的互斥锁」，该进程唯一，故无需跨进程协调。

        内存安全：桶数受 :attr:`_LOCAL_MAX_KEYS` 上界保护——新增 key 前先清理
        「已完全滑出窗口」的空桶，仍达上界则淘汰最久未活跃的桶，硬保证字典规模不越界。
        """
        now = self._time_source()
        with self._local_lock:
            dq = self._local_buckets.get(key)
            if dq is None:
                # 内存上界保护：仅在确实要新建 key 时才付出清理代价。
                if len(self._local_buckets) >= self._LOCAL_MAX_KEYS:
                    self._evict_local_buckets(now, window)
                dq = deque()
                self._local_buckets[key] = dq
            # 剔除滑出窗口的时间戳
            cutoff = now - window
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= max_requests:
                return False
            dq.append(now)
            return True

    def _evict_local_buckets(self, now: float, window: int) -> None:
        """内存上界保护：清空过期桶，仍达上界则按「最久未活跃」淘汰。"""
        cutoff = now - window
        stale = [k for k, dq in self._local_buckets.items() if not dq or dq[-1] <= cutoff]
        for k in stale:
            del self._local_buckets[k]
        # 仍达上界（窗口内活跃 key 过多）→ 淘汰最旧的一批，硬保证上界
        if len(self._local_buckets) >= self._LOCAL_MAX_KEYS:
            overflow = len(self._local_buckets) - self._LOCAL_MAX_KEYS + 1
            oldest = sorted(
                self._local_buckets.items(),
                key=lambda kv: kv[1][-1] if kv[1] else 0.0,
            )
            for k, _ in oldest[:overflow]:
                del self._local_buckets[k]

    def check_rate_limit(self, key: str, max_requests: int, window: int = 60) -> bool:
        """滑动窗口限流：返回 True 表示允许，False 表示超限/被拒绝。

        三条路径（前两条是 Redis 不可用时的行为，由 :data:`ALLOW_LOCAL_FALLBACK` 决定）：
          - **Redis 正常启用** → 复用 Redis 原子滑动窗口（行为一字未改）。
          - **Redis 不可用 / 查询异常 + 生产(STRICT) + 未开开关** → **fail-closed 返回
            False**（CI 安全门禁 G2 固化的不变量：打掉 Redis 不能让限流失效）。
          - **Redis 不可用 / 查询异常 + （非生产 或 显式开了开关）** → 退回**进程内
            滑动窗口兜底**（:meth:`_local_rate_limit`），**既不 fail-open 放行、也不
            fail-closed 拒绝**，语义与 Redis 分支一致：``window`` 秒内允许
            ``max_requests`` 次。

        ── 为什么进程内兜底在本部署下与 Redis 限流「功能等价」────────────────────
        本部署被 ``vectordb_data/.import_writer.lock`` 单写者锁硬约束为 **workers=1**
        （见 ``app/lifespan._assert_single_worker``），全进程唯一 → 进程内计数器即全局
        唯一计数器，与 Redis 共享计数无差别。**若将来改为多 worker，必须换回 Redis
        或其它共享存储**，否则每个 worker 各记一份，实际阈值会被放大 workers 倍。

        内存安全：进程内桶按 key 计数，受 :attr:`_LOCAL_MAX_KEYS` 上界保护。
        """
        if not self._enabled:
            if REDIS_STRICT and not ALLOW_LOCAL_FALLBACK:
                logger.error(
                    "Redis 未启用，生产限流 fail-closed（拒绝本次请求, key=%s）。"
                    "如需在无 Redis 的部署下降级为进程内滑动窗口（仍强制限额，但仅单进程），"
                    "显式设置 RATE_LIMIT_ALLOW_LOCAL_FALLBACK=1。",
                    key,
                )
                return False
            if REDIS_STRICT:
                logger.error(
                    "Redis 未启用，限流已降级为进程内滑动窗口(key=%s)。"
                    "多 worker 部署下进程内限流不生效；本部署 workers=1。",
                    key,
                )
            return self._local_rate_limit(key, max_requests, window)
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
            if REDIS_STRICT and not ALLOW_LOCAL_FALLBACK:
                logger.error(
                    "限流查询异常，生产 fail-closed（拒绝本次请求, key=%s）: %s", key, e
                )
                return False
            if REDIS_STRICT:
                logger.error("限流查询异常，已降级为进程内滑动窗口(key=%s): %s", key, e)
            else:
                logger.warning("限流查询异常，已降级为进程内滑动窗口(key=%s): %s", key, e)
            return self._local_rate_limit(key, max_requests, window)


# 全局单例
redis_client = RedisClient()
