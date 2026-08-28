# ============================================================
# 进程内 LRU + TTL 缓存（Redis 不可用时的本地兜底）
#
# 用途：在开发/演示/单机环境（默认不启用 Redis）下，为确定性、无用户态
# 输入的查询结果提供本地缓存，避免重复查询重跑整条管线（E5 + 向量检索
# + BM25 + 融合 + 重排）。语义与 FrugalRAG 既有的 Redis 缓存一致：
#   仅缓存 query+course 且 student_profile 为空的结果。
# 纯标准库实现（threading/collections/time），无第三方依赖，可独立单测。
# ============================================================

import threading
import time
from collections import OrderedDict
from typing import Any, Optional, Tuple

__all__ = ["LocalLRUCache"]


class LocalLRUCache:
    """线程安全的进程内 LRU + TTL 缓存。

    设计要点：
    - LRU 淘汰：超过 max_size 时淘汰最久未使用的条目。
    - TTL 过期：每条目带写入时间戳，读取时若超过 ttl 秒视为失效并剔除
      （默认 1800s，与 FrugalRAG 的 Redis 缓存 TTL 对齐，避免导入新
      知识库后长期服务陈旧结果）。ttl<=0 表示不过期。
    - 线程安全：单锁保护 OrderedDict 的读写与移动，跨协程/线程安全。
    """

    def __init__(self, max_size: int = 1024, ttl: float = 1800.0):
        self._max = max(1, int(max_size))
        self._ttl = float(ttl)
        self._data: "OrderedDict[str, Tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """读取缓存；未命中或已过期返回 None。"""
        with self._lock:
            item = self._data.get(key)
            if item is None:
                self._misses += 1
                return None
            ts, val = item
            if self._ttl > 0 and (time.monotonic() - ts) > self._ttl:
                self._data.pop(key, None)
                self._misses += 1
                return None
            self._data.move_to_end(key)
            self._hits += 1
            return val

    def set(self, key: str, value: Any) -> None:
        """写入缓存；超容量时按 LRU 淘汰。"""
        with self._lock:
            self._data[key] = (time.monotonic(), value)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def clear(self) -> None:
        """清空全部缓存。"""
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    @property
    def stats(self) -> dict:
        """返回命中/未命中统计，便于观测缓存收益。"""
        with self._lock:
            return {"size": len(self._data), "hits": self._hits, "misses": self._misses}
