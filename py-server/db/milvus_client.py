# ============================================================
# Milvus 向量数据库客户端（抽象层）
# 开发期若 Milvus 不可用，回退 InMemoryVectorStore（纯 numpy）
# ============================================================

import json
import logging
import os
import threading
from typing import Optional

import numpy as np

# 跨进程写锁（防止多个 Python 进程并发写同一 JSON 互相截断）
try:
    from filelock import FileLock
    _HAS_FILELOCK = True
except ImportError:
    FileLock = None
    _HAS_FILELOCK = False

from config import get_milvus_config, get_embedding_config

logger = logging.getLogger("netlearn.milvus")

# ── Milvus 可用性探测（仅 locate，不加载原生库）──
# 重要：pymilvus 3.x 原生库若早于 torch 载入，会在 Windows 触发段错误（退出码 139）。
# 因此此处只做 find_spec 探测，真正的 `from pymilvus import ...` 延迟到 _load_pymilvus()，
# 仅当 Milvus 代码路径实际执行时才加载原生库。开发期用 InMemoryVectorStore 时永不加载。
import importlib.util

try:
    _pymilvus_spec = importlib.util.find_spec("pymilvus")
    MILVUS_AVAILABLE = _pymilvus_spec is not None
except (ImportError, ValueError, ModuleNotFoundError):
    MILVUS_AVAILABLE = False

if not MILVUS_AVAILABLE:
    logger.warning("pymilvus 未安装，Milvus 不可用，将回退 InMemoryVectorStore")

# 延迟加载的 pymilvus 名称（首次 Milvus 路径执行时由 _load_pymilvus() 填充）
connections = None
Collection = None
FieldSchema = None
CollectionSchema = None
DataType = None
utility = None


def _load_pymilvus():
    """Lazily import pymilvus and populate module-level names.

    仅在 Milvus 代码路径实际执行时调用，因此原生库不会在模块导入期被加载
    （否则会早于 torch 载入并在 Windows 上触发 access violation 段错误）。
    """
    global connections, Collection, FieldSchema, CollectionSchema, DataType, utility
    if connections is None:
        from pymilvus import (
            connections as _connections,
            Collection as _Collection,
            FieldSchema as _FieldSchema,
            CollectionSchema as _CollectionSchema,
            DataType as _DataType,
            utility as _utility,
        )
        connections = _connections
        Collection = _Collection
        FieldSchema = _FieldSchema
        CollectionSchema = _CollectionSchema
        DataType = _DataType
        utility = _utility


class InMemoryVectorStore:
    """轻量级内存向量库，基于 numpy 余弦相似度。
    开发期替代 ChromaDB（后者在 Windows 上有 DLL 冲突导致 segfault）。
    支持持久化到 JSON 文件。
    """

    def __init__(self, persist_path: str = "./vectordb_data"):
        self._persist_path = persist_path
        self._collections: dict[str, dict] = {}  # name → {ids, texts, metas, embeddings}
        self._emb_dim = get_embedding_config().get("dimension", 768)
        # Q5: 并发写保护
        #   - _save_lock: 进程内线程锁，防止同进程多线程同时写
        #   - _file_lock: 跨进程文件锁（filelock），防止多个 Python 进程同时写同一 JSON
        self._save_lock = threading.Lock()
        # 检索热路径优化：惰性归一化矩阵缓存（详见 _norm_matrix）
        self._norm_cache: dict = {}
        self._file_lock = None
        if _HAS_FILELOCK:
            os.makedirs(self._persist_path, exist_ok=True)
            # timeout=30s：极端情况下放弃本次写而非无限等待（避免进程挂死）
            self._file_lock = FileLock(
                os.path.join(self._persist_path, ".vectordb_write.lock"),
                timeout=30,
            )

    def _ensure_collection(self, name: str):
        if name not in self._collections:
            self._collections[name] = {
                "ids": [],
                "texts": [],
                "metas": [],
                "embeddings": None,  # numpy array, shape (N, dim)
            }

    def add(self, name: str, ids: list[str], texts: list[str],
            metas: list[dict], embeddings: list[list[float]],
            save: bool = True):
        """批量写入

        Args:
            save: 是否立即持久化。批量导入时设 False，循环结束后调用 flush()
                  可减少 O(n²) 全量重写（Q6）。默认 True（在线写入即时落盘）。
        """
        self._ensure_collection(name)
        coll = self._collections[name]
        coll["ids"].extend(ids)
        coll["texts"].extend(texts)
        coll["metas"].extend(metas)

        new_emb = np.array(embeddings, dtype=np.float32)
        if coll["embeddings"] is None:
            coll["embeddings"] = new_emb
        else:
            coll["embeddings"] = np.vstack([coll["embeddings"], new_emb])
        self._norm_cache.pop(name, None)  # embeddings 变更，使归一化缓存失效

        logger.info(f"InMemoryVectorStore 写入 {len(ids)} 条文档到 {name}")
        if save:
            self._save(name)

    def flush(self, name: str = None):
        """强制持久化指定集合（或全部集合）。

        批量导入设 save=False 后，须在结束时调用以落盘。
        """
        if name is not None:
            if name in self._collections:
                self._save(name)
        else:
            for n in self._collections:
                self._save(n)

    def _norm_matrix(self, name: str):
        """惰性构建并缓存某集合的 L2 归一化嵌入矩阵（检索热路径优化）。

        入库嵌入已由 E5 归一化（normalize_embeddings=True），零向量占位文档
        在 query() 候选过滤阶段已排除，故归一化矩阵恒定、可跨请求复用；
        仅在 add/delete/_load 等变更时通过 _norm_cache.pop 失效。
        返回 None 表示集合无可用嵌入。
        """
        cached = self._norm_cache.get(name)
        if cached is not None:
            return cached
        coll = self._collections.get(name)
        if coll is None or coll["embeddings"] is None or len(coll["ids"]) == 0:
            return None
        embs = np.asarray(coll["embeddings"], dtype=np.float32)
        norms = np.linalg.norm(embs, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        norm = embs / norms
        self._norm_cache[name] = norm
        return norm

    def query(self, name: str, query_vector: list[float], top_k: int = 10,
              filter_dict: Optional[dict] = None) -> list[dict]:
        """向量检索，返回 [{id, text, score, metadata}, ...]
        filter_dict: 例如 {"subject": "network", "type": "knowledge_point"}
        自动排除 embedding_status == "fallback_zero" 的文档
        """
        self._ensure_collection(name)
        coll = self._collections[name]

        if coll["embeddings"] is None or len(coll["ids"]) == 0:
            return []

        # 先按 filter_dict 和 fallback_zero 过滤候选集
        candidate_indices = []
        for idx in range(len(coll["ids"])):
            meta = coll["metas"][idx]
            # 排除零向量占位文档
            if meta.get("embedding_status") == "fallback_zero":
                continue
            # 排除模板废话填充条目（无实质内容，仅污染向量空间）
            if meta.get("exclude_retrieval"):
                continue
            # 应用用户过滤条件
            if filter_dict:
                match = True
                for key, val in filter_dict.items():
                    if meta.get(key) != val:
                        match = False
                        break
                if not match:
                    continue
            candidate_indices.append(idx)

        if not candidate_indices:
            return []

        # 构造候选集的嵌入矩阵（复用惰性归一化缓存，避免每次检索重复归一化静态矩阵）
        norm_matrix = self._norm_matrix(name)
        if norm_matrix is None:
            return []
        candidate_embs = norm_matrix[candidate_indices]

        query_emb = np.asarray(query_vector, dtype=np.float32).reshape(1, -1)

        # 余弦相似度（候选矩阵已 L2 归一化）
        q_norm = np.linalg.norm(query_emb)
        if q_norm == 0:
            return []
        q_normalized = query_emb / q_norm

        scores = (q_normalized @ candidate_embs.T).flatten()  # cosine similarity

        # 按分数排序取 top_k
        top_order = np.argsort(scores)[::-1][:top_k]

        results = []
        for rank in top_order:
            orig_idx = candidate_indices[rank]
            results.append({
                "id": coll["ids"][orig_idx],
                "text": coll["texts"][orig_idx],
                "score": float(scores[rank]),
                "metadata": coll["metas"][orig_idx],
            })
        return results

    def count(self, name: str) -> int:
        self._ensure_collection(name)
        return len(self._collections[name]["ids"])

    def delete_collection(self, name: str) -> bool:
        if name in self._collections:
            self._norm_cache.pop(name, None)
            del self._collections[name]
            filepath = os.path.join(self._persist_path, f"{name}.json")
            if os.path.exists(filepath):
                os.remove(filepath)
            # 同步清理 .emb.npy 二进制缓存，防止维度/行数残留
            emb_cache = filepath + ".emb.npy"
            if os.path.exists(emb_cache):
                os.remove(emb_cache)
            return True
        return False

    def delete_by_ids(self, name: str, ids: list[str]) -> int:
        """按 ID 删除文档，返回删除数量"""
        self._ensure_collection(name)
        coll = self._collections[name]
        id_set = set(ids)
        keep_indices = [i for i in range(len(coll["ids"])) if coll["ids"][i] not in id_set]
        removed_count = len(coll["ids"]) - len(keep_indices)

        if removed_count == 0:
            return 0

        coll["ids"] = [coll["ids"][i] for i in keep_indices]
        coll["texts"] = [coll["texts"][i] for i in keep_indices]
        coll["metas"] = [coll["metas"][i] for i in keep_indices]
        if coll["embeddings"] is not None and len(keep_indices) > 0:
            coll["embeddings"] = coll["embeddings"][keep_indices]
        elif coll["embeddings"] is not None and len(keep_indices) == 0:
            coll["embeddings"] = None

        self._norm_cache.pop(name, None)  # embeddings 变更，使归一化缓存失效
        self._save(name)
        return removed_count

    def get_all_metadata(self, name: str, filter_dict: Optional[dict] = None) -> list[dict]:
        """返回所有 metadata 列表，可选按 filter_dict 过滤"""
        self._ensure_collection(name)
        coll = self._collections[name]
        result = []
        for idx in range(len(coll["ids"])):
            meta = coll["metas"][idx]
            if filter_dict:
                match = True
                for key, val in filter_dict.items():
                    if meta.get(key) != val:
                        match = False
                        break
                if not match:
                    continue
            result.append(meta)
        return result

    def get_all_with_texts(self, name: str, skip: int = 0, limit: int = 20,
                           filter_dict: Optional[dict] = None) -> list[dict]:
        """分页查询含文本，返回 [{id, content, metadata}, ...]"""
        self._ensure_collection(name)
        coll = self._collections[name]

        # 先过滤
        filtered_indices = []
        for idx in range(len(coll["ids"])):
            meta = coll["metas"][idx]
            if filter_dict:
                match = True
                for key, val in filter_dict.items():
                    if meta.get(key) != val:
                        match = False
                        break
                if not match:
                    continue
            filtered_indices.append(idx)

        total = len(filtered_indices)
        sliced = filtered_indices[skip:skip + limit]

        items = []
        for idx in sliced:
            items.append({
                "id": coll["ids"][idx],
                "content": coll["texts"][idx],
                "metadata": coll["metas"][idx],
            })
        return items, total

    def _save(self, name: str):
        """持久化到 JSON（带并发锁，防止多进程/多线程同时写互相截断）"""
        with self._save_lock:
            if self._file_lock is not None:
                # 跨进程锁：超时 30s 避免死等（极端情况下丢失本次写但不崩溃）
                try:
                    with self._file_lock:
                        self._save_unlocked(name)
                except filelock.Timeout:
                    logger.error(
                        f"InMemoryVectorStore 写锁获取超时(30s)，跳过本次持久化: {name}\n"
                        f"  这可能意味着另一个进程长时间持有写锁，请检查是否有并发导入任务未结束。"
                    )
            else:
                self._save_unlocked(name)

    def _save_unlocked(self, name: str):
        """实际写盘逻辑（调用方须已持有锁）"""
        os.makedirs(self._persist_path, exist_ok=True)
        coll = self._collections[name]
        filepath = os.path.join(self._persist_path, f"{name}.json")
        tmppath = filepath + f".tmp.{os.getpid()}"
        data = {
            "ids": coll["ids"],
            "texts": coll["texts"],
            "metas": coll["metas"],
            "embeddings": coll["embeddings"].tolist() if coll["embeddings"] is not None else [],
        }
        # 先写临时文件
        with open(tmppath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        # 原子替换：临时文件 → 正式文件（Windows 上可能需要重试）
        for _attempt in range(5):
            try:
                os.replace(tmppath, filepath)
                break
            except PermissionError:
                if _attempt == 4:
                    raise
                import time as _time
                _time.sleep(0.1 * (_attempt + 1))
        # ── 二进制 embeddings 缓存（加速冷启动加载）──
        # JSON 仍是完整真源（含 embeddings），本缓存仅用于跳过 np.array 重建，
        # 缺失/损坏时自动回退 JSON，零数据风险。
        try:
            if coll["embeddings"] is not None and len(coll["ids"]) > 0:
                emb_path = filepath + ".emb.npy"
                # 原子写入：先写临时文件再 rename，防止崩溃残留半写文件
                emb_tmp = emb_path + f".tmp.{os.getpid()}"
                np.save(emb_tmp, np.asarray(coll["embeddings"], dtype=np.float32))
                os.replace(emb_tmp, emb_path)
        except Exception as e:  # noqa: BLE001
            logger.warning("embeddings 二进制缓存写入失败（非阻塞）: %s", e)

    def _load(self, name: str) -> bool:
        """从 JSON 加载（损坏时自动备份原文件并降级为空库，防止静默数据覆盖）"""
        filepath = os.path.join(self._persist_path, f"{name}.json")
        if not os.path.exists(filepath):
            return False
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._ensure_collection(name)
            coll = self._collections[name]
            coll["ids"] = data["ids"]
            coll["texts"] = data["texts"]
            coll["metas"] = data["metas"]
            # 优先二进制 embeddings 缓存：np.load 二进制远快于 np.array(JSON tolist 重建)；
            # 仅当 .npy 存在且行数一致时复用，否则回退 JSON 全量重建（并回写缓存供下次命中）。
            emb_cache = filepath + ".emb.npy"
            emb_loaded = False
            if os.path.exists(emb_cache) and len(coll["ids"]) > 0:
                try:
                    arr = np.load(emb_cache)
                    # 验证维度：行数一致 + 向量维度与已加载 JSON 数据一致
                    json_dim = len(data["embeddings"][0]) if data.get("embeddings") and len(data["embeddings"]) > 0 else None
                    npy_dim_ok = (arr.ndim == 2 and arr.shape[0] == len(coll["ids"]))
                    if json_dim is not None:
                        npy_dim_ok = npy_dim_ok and arr.shape[1] == json_dim
                    if npy_dim_ok:
                        coll["embeddings"] = np.asarray(arr, dtype=np.float32)
                        emb_loaded = True
                        logger.info(
                            "InMemoryVectorStore 二进制缓存命中 %d 条 embeddings（跳过 JSON 重建）",
                            arr.shape[0],
                        )
                except Exception as e:  # noqa: BLE001
                    logger.warning("embeddings 二进制缓存读取失败，回退 JSON: %s", e)
            if not emb_loaded:
                if data.get("embeddings"):
                    coll["embeddings"] = np.array(data["embeddings"], dtype=np.float32)
                else:
                    coll["embeddings"] = None
                # 首次/失配：回写二进制缓存，使下次冷启动命中
                if coll["embeddings"] is not None:
                    try:
                        np.save(emb_cache, coll["embeddings"])
                    except Exception:  # noqa: BLE001
                        pass
            self._norm_cache.pop(name, None)  # 新加载数据，使归一化缓存失效
            logger.info(f"InMemoryVectorStore 加载 {len(coll['ids'])} 条文档 from {name}")
            return True
        except Exception as e:
            # P0 修复：JSON 损坏时备份原文件 + ERROR 日志，防止空库 _save 覆盖数据
            import time as _time
            backup_path = filepath + f".corrupted.{int(_time.time())}"
            try:
                os.rename(filepath, backup_path)
                logger.error(
                    f"InMemoryVectorStore 加载失败（JSON 损坏）: {e}\n"
                    f"  原文件已备份到: {backup_path}\n"
                    f"  系统将以空库启动，请检查备份文件并手动恢复数据！"
                )
            except OSError:
                logger.error(
                    f"InMemoryVectorStore 加载失败（JSON 损坏）: {e}\n"
                    f"  原文件备份失败，路径: {filepath}\n"
                    f"  系统将以空库启动，请立即检查数据文件！"
                )
            return False


class VectorDB:
    """向量数据库统一接口，封装 Milvus / InMemoryVectorStore 差异"""

    def __init__(self):
        self._milvus_connected = False
        self._mem_store: Optional[InMemoryVectorStore] = None

    # ── 公共接口 ──

    def connect(self) -> bool:
        """尝试连接 Milvus（支持 Milvus Lite URI），失败则初始化 InMemoryVectorStore。

        P0 修复（INC-04 回归）：pymilvus 的 connections.connect 为「惰性连接」，
        即使服务端不可达也默认返回成功，导致 _milvus_connected 被错误置 True，
        随后首个真实 RPC（count/search）会在死连上无限阻塞，使 /api/status 等
        端点挂起。此处显式设置 connect 超时，并在标记连接成功前用一次真实 RPC
        （utility.has_collection）校验可达性；任何失败都快速回退 InMemory，
        绝不阻塞启动或后续请求。
        """
        config = get_milvus_config()
        connect_timeout = float(config.get("connect_timeout", 5))

        if MILVUS_AVAILABLE and config.get("enabled", False):
            _load_pymilvus()
            try:
                uri = config.get("uri", "")
                if uri:
                    # Milvus Lite 使用 URI (http://127.0.0.1:PORT)
                    connections.connect(alias="default", uri=uri, timeout=connect_timeout)
                else:
                    connections.connect(
                        alias="default",
                        host=config.get("host", "localhost"),
                        port=config.get("port", 19530),
                        timeout=connect_timeout,
                    )

                # 关键：惰性连接不校验网络，必须跑一次真实 RPC 验证可达性；
                # 服务端不可达时 has_collection 会抛连接错误（或触发 timeout）。
                try:
                    utility.has_collection("__milvus_health_check__", timeout=connect_timeout)
                except TypeError:
                    # 老版本 pymilvus 的 has_collection 不支持 timeout 参数
                    utility.has_collection("__milvus_health_check__")

                self._milvus_connected = True
                logger.info(
                    f"Milvus 连接成功 ({uri or config.get('host') + ':' + str(config.get('port', 19530))})"
                )
                return True
            except Exception as e:
                logger.warning(f"Milvus 连接/健康检查失败: {e}，回退 InMemoryVectorStore")
                # 清理可能存在的半连接，避免资源泄漏
                try:
                    connections.disconnect("default")
                except Exception:
                    pass

        # 回退 InMemoryVectorStore（显式置 False，永不残留错误连接态）
        self._milvus_connected = False
        self._init_mem_store()
        return False

    def disconnect(self):
        """断开连接"""
        if self._milvus_connected:
            _load_pymilvus()
            connections.disconnect("default")
            self._milvus_connected = False

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        top_k: int = 10,
        filter_dict: Optional[dict] = None,
    ) -> list[dict]:
        """向量检索，返回 [{id, text, score, metadata}, ...]
        filter_dict: 例如 {"subject": "network"}，Milvus 转为 filter_expr
        """
        if self._milvus_connected:
            filter_expr = self._dict_to_milvus_expr(filter_dict) if filter_dict else None
            # 同时排除 fallback_zero 文档
            fallback_expr = 'embedding_status != "fallback_zero"'
            if filter_expr:
                combined_expr = f"({filter_expr}) and {fallback_expr}"
            else:
                combined_expr = fallback_expr
            return self._milvus_search(collection_name, query_vector, top_k, combined_expr)
        return self._mem_search(collection_name, query_vector, top_k, filter_dict)

    def insert(self, collection_name: str, chunks: list[dict], save: bool = True) -> int:
        """批量插入，chunks = [{id, text, metadata, embedding?}, ...]

        Args:
            save: 是否立即持久化（透传给底层存储）。批量导入设 False + 末尾 flush()。
        """
        if self._milvus_connected:
            return self._milvus_insert(collection_name, chunks)
        return self._mem_insert(collection_name, chunks, save=save)

    def flush(self, collection_name: str = None):
        """强制持久化（批量导入 save=False 后必须调用）。

        Milvus 模式为 no-op（服务端自动持久化）。
        """
        if self._milvus_connected:
            return
        if self._mem_store:
            self._mem_store.flush(collection_name)

    def count(self, collection_name: str, timeout: float = 5.0) -> int:
        """获取文档数。

        永不阻塞：Milvus 模式在独立 daemon 线程中执行真实 RPC，join(timeout)
        超时即视为服务端不可达/挂起，降级返回 0 并自愈（标记 _milvus_connected=False，
        后续请求直接走 InMemory），避免 /api/status 等端点因死连而挂起。
        """
        if self._milvus_connected:
            result_holder: dict = {}
            exc_holder: dict = {}

            def _run():
                try:
                    _load_pymilvus()
                    try:
                        exists = utility.has_collection(collection_name, timeout=int(timeout))
                    except TypeError:
                        # 老版本 pymilvus 的 has_collection 不支持 timeout 参数
                        exists = utility.has_collection(collection_name)
                    if exists:
                        col = Collection(collection_name)
                        result_holder["v"] = col.num_entities
                    else:
                        result_holder["v"] = 0
                except Exception as e:  # noqa: BLE001 - 任何 Milvus 异常均降级
                    exc_holder["e"] = e

            worker = threading.Thread(target=_run, daemon=True)
            worker.start()
            worker.join(timeout=timeout)
            if "e" in exc_holder:
                logger.warning(f"Milvus count 失败，降级返回 0: {exc_holder['e']}")
                self._milvus_connected = False
                return 0
            if worker.is_alive():
                # 超时：daemon 线程会被回收，主线程不阻塞
                logger.warning(
                    f"Milvus count 超时({timeout}s)，降级返回 0（服务端可能不可达）"
                )
                self._milvus_connected = False
                return 0
            return int(result_holder.get("v", 0))
        if self._mem_store:
            return self._mem_store.count(collection_name)
        return 0

    def delete_collection(self, collection_name: str) -> bool:
        """删除集合"""
        if self._milvus_connected:
            _load_pymilvus()
            if utility.has_collection(collection_name):
                utility.drop_collection(collection_name)
                return True
            return False
        if self._mem_store:
            return self._mem_store.delete_collection(collection_name)
        return False

    def delete_by_ids(self, collection_name: str, ids: list[str]) -> int:
        """按 ID 删除文档"""
        if self._milvus_connected:
            _load_pymilvus()
            if not utility.has_collection(collection_name):
                return 0
            col = Collection(collection_name)
            # Milvus 删除用 filter expr: id in [xxx, yyy]
            # 注意：Milvus 的 id 字段是 INT64 auto_id，需用自定义 string id 字段
            expr = f'id_str in {json.dumps(ids)}'
            try:
                col.delete(expr)
                col.flush()
                return len(ids)
            except Exception as e:
                logger.warning(f"Milvus delete_by_ids 失败: {e}")
                return 0
        if self._mem_store:
            return self._mem_store.delete_by_ids(collection_name, ids)
        return 0

    def get_all_metadata(self, collection_name: str, filter_dict: Optional[dict] = None) -> list[dict]:
        """返回所有 metadata 列表"""
        if self._mem_store:
            return self._mem_store.get_all_metadata(collection_name, filter_dict)
        if self._milvus_connected:
            _load_pymilvus()
            if not utility.has_collection(collection_name):
                return []
            col = Collection(collection_name)
            col.load()
            expr = self._dict_to_milvus_expr(filter_dict) if filter_dict else ""
            results = col.query(expr=expr or "",
                                output_fields=["id_str", "subject", "course", "chapter",
                                               "chapter_name", "type", "keywords"])
            return [
                {
                    "id": r.get("id_str", ""),
                    "subject": r.get("subject", ""),
                    "course": r.get("course", ""),
                    "chapter": r.get("chapter", ""),
                    "chapter_name": r.get("chapter_name", ""),
                    "type": r.get("type", ""),
                    "keywords": r.get("keywords", ""),
                }
                for r in results
            ]
        return []

    def get_all_with_texts(self, collection_name: str, skip: int = 0, limit: int = 20,
                           filter_dict: Optional[dict] = None) -> tuple[list[dict], int]:
        """分页查询含文本，返回 (items_list, total_count)"""
        if self._mem_store:
            return self._mem_store.get_all_with_texts(collection_name, skip, limit, filter_dict)
        if self._milvus_connected:
            _load_pymilvus()
            if not utility.has_collection(collection_name):
                return [], 0
            col = Collection(collection_name)
            col.load()
            expr = self._dict_to_milvus_expr(filter_dict) if filter_dict else ""
            # P5：总数用 count(*) 聚合，避免全量拉取（生产集合 10万+ 条时防 OOM）
            count_results = col.query(expr=expr or "", output_fields=["count(*)"])
            total = int(count_results[0]["count(*)"]) if count_results else 0
            # 分页：offset/limit 参数（P5：不再全量拉取后切片）
            sliced = col.query(
                expr=expr or "",
                offset=skip,
                limit=limit,
                output_fields=["id_str", "subject", "source", "text",
                              "course", "chapter", "chapter_name",
                              "type", "keywords", "embedding_status"],
            )
            items = [
                {
                    "id": str(r.get("id_str", "")),
                    "content": r.get("text", ""),
                    "metadata": {
                        "subject": r.get("subject", ""),
                        "source": r.get("source", ""),
                        "course": r.get("course", ""),
                        "chapter": r.get("chapter", ""),
                        "chapter_name": r.get("chapter_name", ""),
                        "type": r.get("type", ""),
                        "keywords": r.get("keywords", ""),
                        "embedding_status": r.get("embedding_status", ""),
                    },
                }
                for r in sliced
            ]
            return items, total
        return [], 0

    # ── 工具函数 ──

    def _dict_to_milvus_expr(self, filter_dict: dict) -> str:
        """将 Python dict 过滤条件转为 Milvus filter expression string。
        对字符串值做转义，防止 filter 表达式注入。
        """
        parts = []
        for key, val in filter_dict.items():
            # 白名单校验 key，防止注入（只允许字母、数字、下划线）
            if not key.replace("_", "").isalnum():
                logger.warning(f"Milvus filter key 包含非法字符: {key}")
                continue
            if isinstance(val, str):
                # 转义反斜杠和双引号，防止 filter 表达式注入
                escaped = val.replace("\\", "\\\\").replace('"', '\\"')
                parts.append(f'{key} == "{escaped}"')
            elif isinstance(val, (int, float)):
                parts.append(f'{key} == {val}')
            else:
                logger.warning(f"Milvus filter 不支持的值类型: {key}={type(val).__name__}")
        return " and ".join(parts)

    # ── InMemoryVectorStore 回退实现 ──

    def _init_mem_store(self):
        self._mem_store = InMemoryVectorStore(persist_path="./vectordb_data")
        # 尝试加载已有数据
        loaded = self._mem_store._load("netlearn_kb")
        if loaded:
            logger.info(f"InMemoryVectorStore 初始化成功（已加载 {self._mem_store.count('netlearn_kb')} 条数据）")
        else:
            logger.info("InMemoryVectorStore 初始化成功（空库）")

    def _mem_search(self, coll_name, query_vector, top_k, filter_dict=None):
        """InMemoryVectorStore 向量检索"""
        if not self._mem_store:
            return []
        return self._mem_store.query(coll_name, query_vector, top_k, filter_dict)

    def _mem_insert(self, coll_name, chunks, save: bool = True):
        """InMemoryVectorStore 批量插入（E5 失败时使用零向量占位）

        Args:
            save: 透传给 InMemoryVectorStore.add()，False 时仅内存写入，需调用方 flush()。
        """
        if not self._mem_store:
            self._init_mem_store()

        dim = get_embedding_config().get("dimension", 768)
        ids = []
        docs = []
        metas = []
        embeddings_list = []

        # 尝试计算 E5 嵌入，失败则零向量占位
        precomputed_embeddings = [c.get("embedding", None) for c in chunks]
        has_precomputed = any(e is not None for e in precomputed_embeddings)
        embedding_failed = False

        if not has_precomputed:
            try:
                from db.embedder import embed_batch
                texts_for_embed = [c["text"] for c in chunks]
                # 入库侧用 passage 前缀，与检索侧 query 前缀、netlearn_kb 向量库一致
                computed = embed_batch(texts_for_embed, prefix="passage")
                precomputed_embeddings = computed
                has_precomputed = True
                logger.info(f"E5 嵌入计算成功（{len(chunks)} 条文档）")
            except Exception as e:
                logger.warning(f"E5 嵌入失败({e})，使用零向量占位并标记 fallback_zero")
                embedding_failed = True

        for i, c in enumerate(chunks):
            ids.append(c.get("id", f"chunk_{i}"))
            docs.append(c["text"])
            meta = c.get("metadata", {})
            if has_precomputed:
                emb = precomputed_embeddings[i] if precomputed_embeddings[i] is not None else [0.0] * dim
                if precomputed_embeddings[i] is None:
                    meta["embedding_status"] = "fallback_zero"
            else:
                # P1-2: 零向量占位而非随机向量
                emb = [0.0] * dim
                meta["embedding_status"] = "fallback_zero"
            metas.append(meta)
            embeddings_list.append(emb)

        self._mem_store.add(coll_name, ids=ids, texts=docs, metas=metas,
                            embeddings=embeddings_list, save=save)
        return len(chunks)

    # ── Milvus 实现 ──

    def _milvus_search(self, coll_name, query_vector, top_k, filter_expr):
        _load_pymilvus()
        if not utility.has_collection(coll_name):
            return []
        col = Collection(coll_name)
        col.load()
        search_params = {"metric_type": "COSINE", "params": {"ef": 128}}
        results = col.search(
            data=[query_vector],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            expr=filter_expr,
            output_fields=["text", "course", "chapter", "chapter_name", "type", "keywords"],
        )
        return [
            {
                "id": hit.id,
                "text": hit.entity.get("text", ""),
                "score": hit.score,
                "metadata": {
                    "course": hit.entity.get("course", ""),
                    "chapter": hit.entity.get("chapter", ""),
                    "chapter_name": hit.entity.get("chapter_name", ""),
                    "type": hit.entity.get("type", ""),
                    "keywords": hit.entity.get("keywords", ""),
                },
            }
            for hit in results[0]
        ]

    def _milvus_insert(self, coll_name, chunks):
        _load_pymilvus()
        emb_config = get_embedding_config()
        dim = emb_config.get("dimension", 768)

        if not utility.has_collection(coll_name):
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=2048),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
                FieldSchema(name="id_str", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="subject", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=256),
                FieldSchema(name="course", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="chapter", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="chapter_name", dtype=DataType.VARCHAR, max_length=128),
                FieldSchema(name="type", dtype=DataType.VARCHAR, max_length=32),
                FieldSchema(name="keywords", dtype=DataType.VARCHAR, max_length=512),
                FieldSchema(name="embedding_status", dtype=DataType.VARCHAR, max_length=32),
            ]
            schema = CollectionSchema(fields, description=f"MARS-408 KB: {coll_name}")
            col = Collection(coll_name, schema)
            index_params = {"metric_type": "COSINE", "index_type": "HNSW", "params": {"M": 16, "efConstruction": 200}}
            col.create_index("embedding", index_params)
            col.load()
        else:
            col = Collection(coll_name)
            col.load()

        entities = [
            [c["text"] for c in chunks],
            [c.get("embedding", [0.0] * dim) for c in chunks],
            [c.get("id", "") for c in chunks],
            [c.get("metadata", {}).get("subject", "") for c in chunks],
            [c.get("metadata", {}).get("source", "") for c in chunks],
            [c.get("metadata", {}).get("course", "") for c in chunks],
            [c.get("metadata", {}).get("chapter", "") for c in chunks],
            [c.get("metadata", {}).get("chapter_name", "") for c in chunks],
            [c.get("metadata", {}).get("type", "") for c in chunks],
            [c.get("metadata", {}).get("keywords", "") for c in chunks],
            [c.get("metadata", {}).get("embedding_status", "") for c in chunks],
        ]
        col.insert(entities)
        # Windows 上 milvus-lite 的 flush() 有文件重命名 bug (WinError 183)
        # 跳过 explicit flush，Milvus Lite 会自动持久化
        try:
            col.flush()
        except Exception as _flush_err:
            logger.warning(f"Milvus flush 跳过 (Windows 兼容): {_flush_err}")
        return len(chunks)


# ── 模块级属性代理（PEP 562）──
# 消除双重实例化：`from db.milvus_client import vector_db` 不再创建独立实例，
# 而是委托给 shared.container.get_container().vector_db 的同一单例。
# 这样 main.py 的 connect() 和 DI 注入的实例保证一致。
def __getattr__(name: str):
    if name == "vector_db":
        from shared.container import get_container
        return get_container().vector_db
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
