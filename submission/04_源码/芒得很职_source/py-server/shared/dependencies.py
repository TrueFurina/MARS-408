# ============================================================
# FastAPI 依赖注入函数 — 路由通过 Depends 获取依赖实例
# 测试时可通过 app.dependency_overrides 替换
# ============================================================

from fastapi import Depends
from db.milvus_client import VectorDB
from db.llm_provider import LLMProvider
from shared.container import get_container, Container


def get_vector_db(container: Container = Depends(get_container)) -> VectorDB:
    """注入向量数据库实例"""
    return container.vector_db


def get_llm_provider(container: Container = Depends(get_container)) -> LLMProvider:
    """注入 LLM 提供者实例"""
    return container.llm_provider


def get_pg_client(container: Container = Depends(get_container)):
    """注入 PostgreSQL 客户端"""
    return container.pg_client


def get_redis_client(container: Container = Depends(get_container)):
    """注入 Redis 客户端"""
    return container.redis_client
