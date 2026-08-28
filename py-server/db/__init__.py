# 数据层统一入口
from .milvus_client import vector_db
from .pg_client import pg_client
from .redis_client import redis_client
from .llm_provider import LLMProvider, LLMUnavailable

__all__ = ["vector_db", "pg_client", "redis_client", "LLMProvider", "LLMUnavailable"]


def init_db():
    """初始化所有数据库连接（非阻塞，缺失的组件静默降级）"""
    vector_db.connect()
    pg_client.connect()
    redis_client.connect()
