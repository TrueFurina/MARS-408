# ============================================================
# 嵌入服务 — 独立模块，不依赖 engines 层
# 解决循环依赖: db/milvus_client.py 不再导入 engines/frugal_rag.py
#
# 模型: intfloat/e5-base-v2 (768维, ~420MB)
# 注意: 与 config.json embedding 配置保持一致
#
# v2 优化（2026-07-22）：内容寻址的磁盘嵌入缓存。
#   相同文本（种子数据 / 教材分块）在跨进程重启、重复导入时无需重新跑 E5，
#   直接命中缓存，显著削减冷启动与重复导入的 E5 推理耗时（原 ~30s 瓶颈之一）。
#   缓存以 sha256(文本) 为键，模型名/维度写入元信息，模型切换自动失效，
#   避免维度错配；命中率统计打印在日志中便于观测。
# ============================================================

import logging
import os
import hashlib
import threading
from typing import Optional

import numpy as np

from config import get_embedding_config

logger = logging.getLogger("netlearn.embedder")

# ── 模型延迟加载 ──
_e5_model = None

# 模型配置（与 config.json embedding 保持一致）
EMBED_MODEL_NAME = "intfloat/e5-base-v2"
EMBED_DIM = 768

# ── 嵌入缓存（内容寻址）──
# 缓存文件: vectordb_data/e5_embed_cache.npz
#   meta_model : 模型名（模型切换自动失效缓存，防维度错配）
#   meta_dim   : 向量维度
#   hashes     : 文本 sha256 十六进制串数组
#   vectors    : (N, dim) float32 嵌入矩阵
# 内存中以 dict[hash] -> np.ndarray 提供 O(1) 查询；仅在 miss 时调用模型推理。
_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vectordb_data")
_CACHE_PATH = os.path.join(_CACHE_DIR, "e5_embed_cache.npz")
_CACHE_LOCK = threading.Lock()
_CACHE: Optional[dict] = None            # hash -> np.ndarray(768,)
_CACHE_MODEL: Optional[str] = None
_CACHE_DIM: int = EMBED_DIM
_CACHE_DIRTY = False
_CACHE_HITS = 0
_CACHE_MISSES = 0

# 缓存容量软上限（超出则落盘时截断到最近 N 条，防止无限增长占盘）
_CACHE_MAX = int(os.environ.get("E5_CACHE_MAX", "500000"))

try:
    from filelock import FileLock
    _HAS_FILELOCK = True
except ImportError:
    FileLock = None
    _HAS_FILELOCK = False
_file_lock = None
if _HAS_FILELOCK:
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        _file_lock = FileLock(os.path.join(_CACHE_DIR, ".e5_cache.lock"), timeout=10)
    except Exception:
        _file_lock = None


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_cache():
    """加载磁盘缓存到内存（模型不匹配则视为空，避免维度错配）。"""
    global _CACHE, _CACHE_MODEL, _CACHE_DIM
    _CACHE = {}
    try:
        if not os.path.exists(_CACHE_PATH):
            return
        with np.load(_CACHE_PATH, allow_pickle=True) as data:
            meta_model = str(data["meta_model"].item()) if "meta_model" in data else ""
            meta_dim = int(data["meta_dim"].item()) if "meta_dim" in data else EMBED_DIM
            hashes = data.get("hashes")
            vectors = data.get("vectors")
            if hashes is None or vectors is None:
                return
            if meta_model and meta_model != EMBED_MODEL_NAME:
                logger.info(
                    "嵌入缓存模型(%s)与当前(%s)不一致，缓存失效重建",
                    meta_model, EMBED_MODEL_NAME,
                )
                return
            for h, v in zip(hashes, vectors):
                _CACHE[str(h)] = np.asarray(v, dtype=np.float32)
        _CACHE_MODEL = EMBED_MODEL_NAME
        _CACHE_DIM = meta_dim
        logger.info("嵌入缓存加载: %d 条", len(_CACHE))
    except Exception as e:  # 任何损坏都降级为空缓存，绝不抛错阻断启动
        logger.warning("嵌入缓存加载失败，以空缓存启动: %s", e)
        _CACHE = {}


def _flush_cache():
    """将内存缓存原子落盘（仅在 dirty 时调用）。锁外调用需自行持锁。"""
    global _CACHE_DIRTY
    if not _CACHE_DIRTY or _CACHE is None:
        return
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        # 快照 items 后再操作，防止并发修改导致 RuntimeError
        with _CACHE_LOCK:
            items = list(_CACHE.items())
        if len(items) > _CACHE_MAX:
            items = items[-_CACHE_MAX:]
            logger.info("嵌入缓存超过软上限 %d，截断到最近 %d 条", _CACHE_MAX, len(items))
        hashes = np.array([h for h, _ in items], dtype=object)
        vectors = np.array([v for _, v in items], dtype=np.float32)
        tmp = _CACHE_PATH + f".tmp.{os.getpid()}.npz"
        np.savez(
            tmp,
            meta_model=np.array(EMBED_MODEL_NAME),
            meta_dim=np.array([EMBED_DIM]),
            hashes=hashes,
            vectors=vectors,
        )
        os.replace(tmp, _CACHE_PATH)
        _CACHE_DIRTY = False
        logger.info("嵌入缓存落盘: %d 条 -> %s", len(items), _CACHE_PATH)
    except Exception as e:
        logger.warning("嵌入缓存落盘失败（非阻塞）: %s", e)


def _ensure_cache():
    global _CACHE
    if _CACHE is None:
        with _CACHE_LOCK:
            if _CACHE is None:
                _load_cache()


def _get_e5_model():
    """延迟加载 e5-base-v2 模型（优先本地预打包 models/e5-base-v2）"""
    global _e5_model
    if _e5_model is not None:
        return _e5_model

    emb_config = get_embedding_config()
    model_name = emb_config.get("model", EMBED_MODEL_NAME)

    try:
        from sentence_transformers import SentenceTransformer
        local_repo = emb_config.get("local_model_repo", "")
        if local_repo:
            import os as _os
            if _os.path.isdir(local_repo):
                _e5_model = SentenceTransformer(local_repo)
                logger.info(f"嵌入模型加载: {local_repo}")
                return _e5_model

        _e5_model = SentenceTransformer(model_name)
        logger.info(f"嵌入模型加载: {model_name} (维度: {EMBED_DIM})")
        return _e5_model
    except ImportError:
        logger.error("sentence-transformers 未安装，无法进行向量检索")
        raise
    except Exception as e:
        logger.error(f"嵌入模型加载失败: {e}")
        raise


def embed_batch(texts: list[str]) -> list[list[float]]:
    """批量文本 → 向量（768维，e5-base-v2）。命中缓存的文本跳过模型推理。

    返回顺序与输入严格一致。缓存 miss 的文本才调用模型；同一 batch 内的重复文本
    也只在模型侧计算一次（batch 内去重），推理结果写回内存缓存并原子落盘
    （带 filelock 防跨进程损坏）。模型不可用时会抛错（与旧行为一致）。
    """
    _ensure_cache()
    dim = get_embedding_config().get("dimension", EMBED_DIM)
    results: list = [None] * len(texts)
    miss_entries: list[tuple[int, str]] = []   # (result_index, hash)
    miss_unique: list[tuple[str, str]] = []    # (hash, text) 去重后的待编码文本
    unique_index: dict[str, int] = {}

    global _CACHE_HITS, _CACHE_MISSES, _CACHE_DIRTY
    with _CACHE_LOCK:
        for i, t in enumerate(texts):
            h = _hash_text(t)
            cached = _CACHE.get(h)
            if cached is not None:
                results[i] = cached.tolist()
                _CACHE_HITS += 1
            else:
                if h not in unique_index:
                    unique_index[h] = len(miss_unique)
                    miss_unique.append((h, t))
                miss_entries.append((i, h))
                _CACHE_MISSES += 1

    if miss_unique:
        model = _get_e5_model()
        # e5-base-v2 检索场景建议加 "query:"/"passage:" 前缀，
        # 但现有向量库(netlearn_kb.json, 2083条)与 NeuralMixer 训练权重均基于无前缀编码，
        # 为保持一致性此处不加前缀；如需启用需重建索引并重训权重。
        uniq_texts = [t for _, t in miss_unique]
        computed = model.encode(uniq_texts, normalize_embeddings=True)
        computed = np.asarray(computed, dtype=np.float32)
        with _CACHE_LOCK:
            for k, (h, _t) in enumerate(miss_unique):
                _CACHE[h] = computed[k]
            # 内存硬上限：超过时驱逐最旧条目（FIFO 近似）
            if len(_CACHE) > _CACHE_MAX:
                excess = len(_CACHE) - _CACHE_MAX
                for _old_key in list(_CACHE.keys())[:excess]:
                    del _CACHE[_old_key]
            for (i, h) in miss_entries:
                results[i] = _CACHE[h].tolist()
            _CACHE_DIRTY = True
        # 落盘（带文件锁，原子替换），失败则无锁重试一次
        if _file_lock is not None:
            try:
                with _file_lock:
                    _flush_cache()
            except Exception:
                _flush_cache()
        else:
            _flush_cache()
        logger.info(
            "E5 嵌入完成 batch=%d (unique miss=%d, cache hit=%d)",
            len(texts), len(miss_unique), len(texts) - len(miss_entries),
        )
    return results


def embed_text(text: str) -> list[float]:
    """文本 → 向量（768维，e5-base-v2）"""
    return embed_batch([text])[0]


def get_embed_dim() -> int:
    """获取嵌入向量维度（优先从 config 读取，与实际模型一致）"""
    dim = get_embedding_config().get("dimension")
    return int(dim) if dim else EMBED_DIM


def is_available() -> bool:
    """检查模型是否可用（不抛异常）"""
    try:
        _get_e5_model()
        return True
    except Exception:
        return False
