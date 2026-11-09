# ============================================================
# P0 回归：嵌入模型空间一致性（e5-base-v2）与启动期 space-probe
#
# 背景（已实测确认的代码回归）：向量库 netlearn_kb.json 由
# intfloat/e5-base-v2 + "passage: " 前缀 + normalize 生成，但 config.py
# DEFAULTS 与 embedder.py 常量一度声明了另一个多语言 E5 模型（XLM-R 空间），
# 导致检索静默退化为随机基线。本测试锁定「默认配置 / 常量 / 对外声明」三者
# 一致，并验证缓存失效、space-probe 判定与 fail-soft 行为。
#
# 纯逻辑测试：不依赖项目 conftest 的 autouse fixture（mock_auth / 429），
# 可用 `--noconftest -q --no-cov` 独立运行。
# ============================================================
import asyncio
import os
import pathlib
import sys

import numpy as np
import pytest

# 本测试可 --noconftest 独立运行，故自行把 py-server 根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from app import lifespan as _lifespan  # noqa: E402
from db import embedder  # noqa: E402

EXPECTED_MODEL = "intfloat/e5-base-v2"
_PY_SERVER = pathlib.Path(__file__).resolve().parent.parent


# ── (a) 三者一致：锁定默认配置 / 常量 / 对外声明 ──────────────────────
def test_embedding_model_sources_agree():
    """config DEFAULTS / embedder 常量 / rag.py 对外声明必须同为 e5-base-v2。"""
    assert config.DEFAULTS["embedding"]["model"] == EXPECTED_MODEL
    assert embedder.EMBED_MODEL_NAME == EXPECTED_MODEL
    assert config.DEFAULTS["embedding"]["mode"] == "local"
    assert config.DEFAULTS["embedding"]["dimension"] == 768
    assert config.DEFAULTS["embedding"]["local_model_repo"].endswith(
        os.path.join("models", "e5-base-v2")
    )

    rag_src = (_PY_SERVER / "api" / "rag.py").read_text(encoding="utf-8")
    assert f'"embedding_model": "{EXPECTED_MODEL}"' in rag_src
    # 旧模型名不得再作为「声明」出现（历史陈述注释除外，这里只锁三个真值源）
    assert "intfloat/multilingual-e5-base" not in rag_src
    assert "intfloat/multilingual-e5-base" not in (
        _PY_SERVER / "config.py"
    ).read_text(encoding="utf-8")


# ── (b) _load_cache：模型名不一致时清空缓存的既有行为不被破坏 ──────────
def _write_cache(path, model_name):
    np.savez(
        path,
        meta_model=np.array(model_name),
        meta_dim=np.array([embedder.EMBED_DIM]),
        hashes=np.array(["h1"], dtype=object),
        vectors=np.ones((1, embedder.EMBED_DIM), dtype=np.float32),
    )


def test_load_cache_invalidates_on_model_mismatch(tmp_path, monkeypatch):
    """缓存元信息为旧模型名时，_load_cache 必须清空缓存（失效重建）。"""
    cache_path = tmp_path / "e5_embed_cache.npz"
    _write_cache(cache_path, "intfloat/multilingual-e5-base")
    monkeypatch.setattr(embedder, "_CACHE_PATH", str(cache_path))
    monkeypatch.setattr(embedder, "_CACHE", {"stale": np.ones(embedder.EMBED_DIM, dtype=np.float32)})

    embedder._load_cache()
    assert embedder._CACHE == {}


def test_load_cache_keeps_matching_model(tmp_path, monkeypatch):
    """模型名一致时正常加载（证明 (b) 的清空不是无条件清空）。"""
    cache_path = tmp_path / "e5_embed_cache.npz"
    _write_cache(cache_path, EXPECTED_MODEL)
    monkeypatch.setattr(embedder, "_CACHE_PATH", str(cache_path))
    monkeypatch.setattr(embedder, "_CACHE", {})

    embedder._load_cache()
    assert "h1" in embedder._CACHE
    assert embedder._CACHE["h1"].shape == (embedder.EMBED_DIM,)


# ── (3) 双真值源：_flush_cache 写「实际生效模型」而非常量 ──────────────
def test_flush_cache_writes_effective_model(tmp_path, monkeypatch):
    cache_path = tmp_path / "e5_embed_cache.npz"
    monkeypatch.setattr(embedder, "_CACHE_PATH", str(cache_path))
    monkeypatch.setattr(embedder, "_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(embedder, "_file_lock", None)
    monkeypatch.setattr(embedder, "_CACHE", {"h1": np.ones(embedder.EMBED_DIM, dtype=np.float32)})
    monkeypatch.setattr(embedder, "_CACHE_DIRTY", True)
    # 模拟 config.json / 环境变量覆盖 DEFAULTS
    monkeypatch.setattr(embedder, "get_embedding_config", lambda: {"model": "custom/e5-override"})

    embedder._flush_cache()
    with np.load(str(cache_path), allow_pickle=True) as data:
        assert str(data["meta_model"].item()) == "custom/e5-override"


# ── (c) space-probe 判定 ──────────────────────────────────────────────
class _FakeModel:
    """只实现探针会用到的底层 encode，记录调用参数便于断言只读约束。"""

    def __init__(self, vec):
        self._vec = np.asarray(vec, dtype=np.float32).reshape(1, -1)
        self.calls = []

    def encode(self, texts, normalize_embeddings=False):
        self.calls.append((list(texts), normalize_embeddings))
        return self._vec.copy()


def _install_fake_model(monkeypatch, vec, cache_dir):
    fake = _FakeModel(vec)
    monkeypatch.setattr(embedder, "_get_e5_model", lambda: fake)
    monkeypatch.setattr(embedder, "_PREFIX_ENABLED", True)
    # 只读约束：探针绝不复用 embed_batch / embed_text（它们会落盘污染缓存）
    def _forbidden(*_a, **_k):
        raise AssertionError("space-probe 不得复用 embed_batch/embed_text")
    monkeypatch.setattr(embedder, "embed_batch", _forbidden)
    monkeypatch.setattr(embedder, "embed_text", _forbidden)
    monkeypatch.setattr(embedder, "_CACHE_PATH", str(cache_dir / "e5_embed_cache.npz"))
    return fake


def test_probe_same_space(monkeypatch, tmp_path):
    """cos≈+1.0 → 同空间，且应用 passage 前缀、不落盘缓存。"""
    base = np.ones(embedder.EMBED_DIM, dtype=np.float32)
    base /= np.linalg.norm(base)
    fake = _install_fake_model(monkeypatch, base, tmp_path)

    ok, cos = embedder.probe_embedding_space("TCP三次握手的过程是怎样的", base)
    assert ok is True
    assert cos > 0.999
    assert fake.calls[0][0][0].startswith("passage: ")
    assert fake.calls[0][1] is True
    assert not (tmp_path / "e5_embed_cache.npz").exists()


def test_probe_mismatch_space(monkeypatch, tmp_path):
    """cos≈0.0（正交向量）→ 判定不匹配。"""
    lib = np.zeros(embedder.EMBED_DIM, dtype=np.float32)
    lib[0] = 1.0
    query = np.zeros(embedder.EMBED_DIM, dtype=np.float32)
    query[1] = 1.0
    _install_fake_model(monkeypatch, query, tmp_path)

    ok, cos = embedder.probe_embedding_space("TCP三次握手的过程是怎样的", lib)
    assert ok is False
    assert abs(cos) < 0.05


def test_probe_raises_on_invalid_input():
    """探针自身对无效输入向上抛异常（由调用方 fail-soft 吞掉，不在此静默）。"""
    with pytest.raises(ValueError):
        embedder.probe_embedding_space("", np.ones(embedder.EMBED_DIM, dtype=np.float32))
    with pytest.raises(ValueError):
        embedder.probe_embedding_space("TCP", np.ones(4, dtype=np.float32))


# ── (c) fail-soft：探针异常 / 空库都不得阻断启动 ────────────────────────
class _FakeVectorStore:
    def __init__(self, embeddings):
        self._collections = {"netlearn_kb": {"embeddings": embeddings}}


class _FakeVectorDB:
    def __init__(self, docs, embeddings):
        self._mem_store = _FakeVectorStore(embeddings)
        self._docs = docs

    def connect(self):
        return None

    def count(self, name):
        return 1

    def get_all_with_texts(self, name, skip, limit):
        return (list(self._docs), 0)


def _run_init_with(monkeypatch, db, probe_impl=None):
    monkeypatch.setattr(_lifespan, "vector_db", db)
    monkeypatch.setattr(embedder, "SPACE_PROBE_RESULT", None)
    if probe_impl is not None:
        monkeypatch.setattr(embedder, "probe_embedding_space", probe_impl)
    return asyncio.run(_lifespan._init_vector_db())


def test_probe_fail_soft_when_model_raises(monkeypatch):
    """模型缺失 / CI 注入 mock 导致探针抛异常：lifespan 只 WARNING 跳过，启动继续。"""
    embeddings = np.ones((1, embedder.EMBED_DIM), dtype=np.float32)
    db = _FakeVectorDB([{"content": "TCP三次握手"}], embeddings)

    def _boom(*_a, **_k):
        raise RuntimeError("模型未安装，探针不可用")

    count = _run_init_with(monkeypatch, db, _boom)
    assert count == 1
    assert embedder.SPACE_PROBE_RESULT == {"state": "skipped"}


def test_probe_fail_soft_when_library_empty(monkeypatch):
    """库为空 / 首行文本为空：同样 fail-soft，不抛异常、不阻断启动。"""
    db = _FakeVectorDB([], None)
    count = _run_init_with(monkeypatch, db)
    assert count == 1
    assert embedder.SPACE_PROBE_RESULT == {"state": "skipped"}
