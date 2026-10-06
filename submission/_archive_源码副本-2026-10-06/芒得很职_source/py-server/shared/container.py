# ============================================================
# DI 容器 — 替代全局单例模式
# 通过 FastAPI Depends 注入，支持测试 mock 替换
# ============================================================

import logging
import threading
from functools import lru_cache
from typing import Optional

from config import load_config

logger = logging.getLogger("netlearn.container")

# 类级初始化锁：防止多线程首次并发访问时重复构造依赖实例
# （GIL 不保证「检查-创建」两步跨 import/IO 的原子性，FastAPI 线程池下存在双重初始化风险）。
_INSTANCE_LOCK = threading.Lock()


class Container:
    """轻量级依赖注入容器 — 延迟初始化，线程安全（双检锁）"""

    def __init__(self):
        self._settings: Optional[dict] = None
        self._vector_db = None
        self._llm_provider = None
        self._pg_client = None
        self._redis_client = None

    @property
    def settings(self) -> dict:
        if self._settings is None:
            with _INSTANCE_LOCK:
                if self._settings is None:
                    self._settings = load_config()
        return self._settings

    @property
    def vector_db(self):
        if self._vector_db is None:
            with _INSTANCE_LOCK:
                if self._vector_db is None:
                    from db.milvus_client import VectorDB
                    self._vector_db = VectorDB()
        return self._vector_db

    @property
    def llm_provider(self):
        if self._llm_provider is None:
            with _INSTANCE_LOCK:
                if self._llm_provider is None:
                    from db.llm_provider import LLMProvider
                    self._llm_provider = LLMProvider()
        return self._llm_provider

    @property
    def pg_client(self):
        if self._pg_client is None:
            with _INSTANCE_LOCK:
                if self._pg_client is None:
                    from db.pg_client import PgClient
                    self._pg_client = PgClient()
        return self._pg_client

    @property
    def redis_client(self):
        if self._redis_client is None:
            with _INSTANCE_LOCK:
                if self._redis_client is None:
                    from db.redis_client import RedisClient
                    self._redis_client = RedisClient()
        return self._redis_client

    def override(self, name: str, instance):
        """测试用: 替换某个依赖实例"""
        setattr(self, f"_{name}", instance)


@lru_cache
def get_container() -> Container:
    """获取全局容器单例（应用级别，非模块级别）"""
    return Container()
