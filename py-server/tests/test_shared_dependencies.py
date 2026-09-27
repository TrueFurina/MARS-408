# -*- coding: utf-8 -*-
"""DI 依赖注入与容器懒加载单测 —— shared/dependencies.py（0%）、shared/container.py（67%）

这两个模块是"路由如何拿到向量库 / LLM / PG / Redis 实例"的唯一入口。
此前 dependencies.py 完全没有测试，容器懒加载分支也未被执行过。

⚠️ 设计要点（首次提交踩过坑）：容器属性是**函数内延迟导入**具体实现类
（`from db.redis_client import RedisClient`），而其它测试文件会用 sys.modules 替身
替换 db.* 子模块 —— 若直接构造真实容器，就会随机撞上"替身模块里没有 RedisClient"的
ImportError（全量跑挂、单跑过）。因此本文件用 `isolated_deps` 显式注入伪实现模块，
让断言只检验**容器自己的懒加载与缓存语义**，不依赖全局 import 现状。
"""

import sys
import types

import pytest


class _StubImpl:
    """占位实现：只要能被实例化即可（容器的懒加载/缓存语义与实现细节无关）。"""

    def __init__(self, *args, **kwargs):
        pass


@pytest.fixture
def isolated_deps(monkeypatch):
    """把四个 db.* 依赖模块替换为受控伪模块，隔离外部 stub 污染。"""
    mapping = {
        "db.milvus_client": "VectorDB",
        "db.llm_provider": "LLMProvider",
        "db.pg_client": "PgClient",
        "db.redis_client": "RedisClient",
    }
    for module_name, class_name in mapping.items():
        module = types.ModuleType(module_name)
        setattr(module, class_name, type(f"{class_name}Stub", (_StubImpl,), {}))
        monkeypatch.setitem(sys.modules, module_name, module)
    yield mapping


class TestContainerLazyInit:
    def test_fresh_container_creates_all_members(self, isolated_deps):
        from shared.container import Container
        container = Container()
        assert container.vector_db is not None
        assert container.llm_provider is not None
        assert container.pg_client is not None
        assert container.redis_client is not None

    def test_members_are_cached_not_recreated(self, isolated_deps):
        """懒加载必须缓存：同一容器两次取到同一实例，否则连接会泄漏。"""
        from shared.container import Container
        container = Container()
        assert container.vector_db is container.vector_db
        assert container.llm_provider is container.llm_provider
        assert container.pg_client is container.pg_client
        assert container.redis_client is container.redis_client

    def test_created_member_is_the_injected_impl(self, isolated_deps):
        """确认懒加载确实走的是依赖模块里的类（而非硬编码或缓存了别的对象）。"""
        from shared.container import Container
        container = Container()
        assert type(container.redis_client).__name__ == "RedisClientStub"

    def test_settings_loaded_once(self):
        from shared.container import Container
        container = Container()
        assert container.settings is container.settings


class TestDependencyGetters:
    def test_getters_return_container_members(self, isolated_deps):
        from shared import dependencies as dep
        from shared.container import get_container

        container = get_container()
        assert dep.get_vector_db(container=container) is container.vector_db
        assert dep.get_llm_provider(container=container) is container.llm_provider
        assert dep.get_pg_client(container=container) is container.pg_client
        assert dep.get_redis_client(container=container) is container.redis_client

    def test_get_container_is_singleton(self):
        from shared.container import get_container
        assert get_container() is get_container()

    def test_getters_visible_to_dependency_overrides(self):
        """契约：这些函数可被 app.dependency_overrides 替换（测试替身入口）。"""
        from fastapi import FastAPI
        from shared import dependencies as dep

        app = FastAPI()
        app.dependency_overrides[dep.get_vector_db] = lambda: "fake-vector-db"
        resolved = app.dependency_overrides[dep.get_vector_db]()
        assert resolved == "fake-vector-db"


class TestContainerIsolation:
    def test_two_containers_do_not_share_members(self, isolated_deps):
        from shared.container import Container
        a, b = Container(), Container()
        assert a.vector_db is not b.vector_db, "不同容器实例不得共用同一向量库对象"
