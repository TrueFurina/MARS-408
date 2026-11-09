# -*- coding: utf-8 -*-
"""嵌入模型名必须「配置驱动、单一真值源」—— 防缓存静默错配回归。

背景：embedder 曾用常量 ``EMBED_MODEL_NAME`` 比对/写缓存元数据，而实际加载的是
config 里的模型。一旦在 config.json 切换 ``embedding.model``，旧的磁盘缓存会被
误判为有效（元数据写死旧名），向量与模型名错配却不报任何降级；``/api/status``
也只上报常量，掩盖真相。

本文件锁：
1. ``_effective_model_name()`` 在 config 覆盖时返回覆盖值；
2. ``_flush_cache()`` 落盘的 ``meta_model`` == 生效模型名（不再写死常量）；
3. ``_load_cache()`` 在磁盘缓存的 ``meta_model`` 与生效模型不一致时整体失效；
4. ``/api/status`` 的 ``health.embedding.model`` 反映生效模型名。
"""

import numpy as np
import pytest

import db.embedder as embedder
from app import status as status_mod


@pytest.fixture()
def dim():
    return 768


@pytest.fixture()
def isolated_cache(tmp_path, monkeypatch, dim):
    """把缓存模块重定向到临时文件，且不让它碰真实 vectordb_data。"""
    cache_file = tmp_path / "e5_embed_cache.npz"
    monkeypatch.setattr(embedder, "_CACHE_PATH", str(cache_file))
    monkeypatch.setattr(embedder, "_CACHE", None)
    monkeypatch.setattr(embedder, "_CACHE_MODEL", None)
    monkeypatch.setattr(embedder, "_CACHE_DIRTY", False)
    monkeypatch.setattr(embedder, "_file_lock", None)  # 测试不抢真实锁
    return cache_file


def test_effective_model_name_returns_config_override(monkeypatch):
    """config 指定 e5-base-v2 时，生效模型名必须跟着变。"""
    monkeypatch.setattr(
        embedder,
        "get_embedding_config",
        lambda: {"model": "intfloat/e5-base-v2", "dimension": 768},
    )
    assert embedder._effective_model_name() == "intfloat/e5-base-v2"


def test_flush_cache_writes_effective_model_name(isolated_cache, monkeypatch, dim):
    """落盘元数据必须写下「生效模型名」，而非写死常量。"""
    monkeypatch.setattr(
        embedder,
        "get_embedding_config",
        lambda: {"model": "intfloat/e5-base-v2"},
    )
    monkeypatch.setattr(
        embedder,
        "_CACHE",
        {"h1": np.array([0.2] * dim, dtype=np.float32)},
    )
    monkeypatch.setattr(embedder, "_CACHE_DIRTY", True)
    embedder._flush_cache()
    with np.load(isolated_cache) as data:
        assert str(data["meta_model"].item()) == "intfloat/e5-base-v2", (
            f"缓存元数据必须记录生效模型名，实测 {data['meta_model'].item()}"
        )
        assert int(data["meta_dim"].item()) == dim


def test_load_cache_invalidated_when_model_mismatch(isolated_cache, monkeypatch, dim):
    """磁盘缓存是 multilingual，但生效模型被切到 e5-base-v2 ⇒ 缓存必须整体失效。"""
    np.savez(
        isolated_cache,
        meta_model=np.array("intfloat/multilingual-e5-base"),
        meta_dim=np.array([dim]),
        hashes=np.array(["h1"], dtype=object),
        vectors=np.array([[0.1] * dim], dtype=np.float32),
    )
    monkeypatch.setattr(
        embedder,
        "get_embedding_config",
        lambda: {"model": "intfloat/e5-base-v2"},
    )
    monkeypatch.setattr(embedder, "_CACHE", None)
    embedder._load_cache()
    assert embedder._CACHE == {}, (
        "模型切换后旧缓存必须失效重建，否则向量与模型名静默错配"
    )


def test_load_cache_accepted_when_model_matches(isolated_cache, monkeypatch, dim):
    """磁盘缓存模型与生效模型一致时，缓存正常命中。"""
    np.savez(
        isolated_cache,
        meta_model=np.array("intfloat/multilingual-e5-base"),
        meta_dim=np.array([dim]),
        hashes=np.array(["h1"], dtype=object),
        vectors=np.array([[0.1] * dim], dtype=np.float32),
    )
    monkeypatch.setattr(
        embedder,
        "get_embedding_config",
        lambda: {"model": "intfloat/multilingual-e5-base"},
    )
    monkeypatch.setattr(embedder, "_CACHE", None)
    embedder._load_cache()
    assert "h1" in embedder._CACHE, "模型一致时缓存应被接受"


@pytest.mark.asyncio
async def test_status_reports_effective_model_name(monkeypatch):
    """/api/status 的 health.embedding.model 必须反映生效模型名，而非常量。"""
    monkeypatch.setattr(
        embedder,
        "_effective_model_name",
        lambda: "intfloat/e5-base-v2",
    )
    payload = await status_mod.status()
    assert payload["health"]["embedding"]["model"] == "intfloat/e5-base-v2", (
        payload["health"]["embedding"]
    )
