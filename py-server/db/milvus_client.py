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
    import filelock as _filelock_mod
    from filelock import FileLock, Timeout
    filelock = _filelock_mod  # 便于 except filelock.Timeout 书写
    _HAS_FILELOCK = True
except ImportError:
    FileLock = None
    Timeout = None
    filelock = None
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


# INC-2026-09-14: 空库覆盖守门阈值。持久化 JSON 超过该体积即视为"实质数据"，
# 拒绝以空集合覆盖，防止加载失败导致的连锁清零。
_EMPTY_OVERWRITE_GUARD_BYTES = 1024 * 1024  # 1 MB

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
        """实际写盘逻辑（调用方须已持有锁）

        2026-10-22 起：**不落盘已知坏数据** —— ``embedding_status ==
        "fallback_zero"`` 的文档在持久化时被跳过，``netlearn_kb.json`` 与
        ``.emb.npy`` 一致处理。

        为什么（career-only 瘦包双启动实证）：E5 不可用时种子全部以零向量占位
        入库，若照常落盘，第二次启动会命中「二进制缓存 N 条、跳过 JSON 重建」
        —— 而 :attr:`VectorDB.embedding_fallback_count` 只统计**本次新插入**、
        读回不计 ⇒ ``/api/status`` 重启后低报 ``fallback_zero_docs:0`` /
        ``status:"ok"``，库里却全是零向量。**首次启动诚实、重启后说谎。**

        影响面（边界，勿扩大）：
          - 真嵌入（408 主部署）非零即落盘，持久化行为**一字未改**；
          - career-only 包因此什么都不落 ⇒ 每次启动重新播种、重新计数 ⇒ 探针
            每次诚实报 2245/degraded；
          - 检索侧本就排除 ``fallback_zero``（见 ``_norm_matrix`` 注释），
            故不过滤也不会污染检索 —— 过滤只为「不把坏数据留在磁盘上」；
          - 写侧只防未来：已被旧版本污染的目录由读取侧 ``_load_unlocked`` 的同名
            过滤兜住（重启即自愈），两者必须成对存在。
        """
        os.makedirs(self._persist_path, exist_ok=True)
        coll = self._collections[name]
        filepath = os.path.join(self._persist_path, f"{name}.json")
        # ── 过滤已知坏数据：E5 失败产生的零向量占位文档 ──
        # 列长一致性守卫：keep 由 metas 长度推出、却用于索引 ids/texts —— 三者错位
        # （半截写入 / 外部编辑损坏）时会静默截断而非报错。错位即视为异常态：跳过
        # 过滤、全部照写（保持旧行为），绝不因守卫本身抛错打断保存。
        _emb = coll["embeddings"]
        _n = len(coll["ids"])
        _emb_aligned = _emb is not None and len(_emb) == _n
        if len(coll["texts"]) == _n and len(coll["metas"]) == _n:
            keep = [
                i
                for i, m in enumerate(coll["metas"])
                if not (isinstance(m, dict) and m.get("embedding_status") == "fallback_zero")
            ]
        else:
            keep = list(range(_n))
            logger.warning(
                "InMemoryVectorStore 列长不一致（ids=%d texts=%d metas=%d），"
                "跳过 fallback_zero 过滤、按原样落盘: %s",
                _n, len(coll["texts"]), len(coll["metas"]),
                os.path.join(self._persist_path, f"{name}.json"),
            )
        # 条件里的 _n > 0 不可省：空集合必须继续走下面的空库覆盖守门与正常写盘
        # （delete_by_ids 清空后要把磁盘旧内容覆盖成空），只有「有文档但全为坏数据」
        # 才跳过落盘。
        if _n > 0 and not keep:
            logger.info(
                "InMemoryVectorStore 无可持久化文档（%d 条全部为 E5 失败零向量占位），"
                "跳过落盘: %s —— 下次启动将重新入库并重新计数，健康探针据此如实降级",
                len(coll["ids"]),
                filepath,
            )
            return
        # INC-2026-09-14 空库覆盖守门：内存集合为空而磁盘已存在实质数据时拒绝写入。
        # 这挡住「加载失败 → 空库启动 → _save 覆盖」这条把真库清零的链路。
        # （有文档但全为坏数据时上面已提前返回，故此处只剩 _n == 0 的空集合场景。）
        if len(coll["ids"]) == 0 and os.path.exists(filepath):
            try:
                _disk_size = os.path.getsize(filepath)
            except OSError:
                _disk_size = 0
            if _disk_size > _EMPTY_OVERWRITE_GUARD_BYTES:
                logger.error(
                    "InMemoryVectorStore 拒绝以空集合覆盖非空持久化文件: %s (%d bytes)\n"
                    "  通常意味着上游加载失败导致空库启动，已阻止数据清零。",
                    filepath,
                    _disk_size,
                )
                return
        tmppath = filepath + f".tmp.{os.getpid()}"
        _emb_rows = _emb[keep] if _emb_aligned else _emb
        data = {
            "ids": [coll["ids"][i] for i in keep],
            "texts": [coll["texts"][i] for i in keep],
            "metas": [coll["metas"][i] for i in keep],
            "embeddings": _emb_rows.tolist() if _emb_rows is not None else [],
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
        # 与 JSON **同一份 keep 过滤**：否则读回时二进制缓存行数与 JSON 不一致，
        # 维度校验失配后每次都要回退 JSON 全量重建，缓存等于白写。
        try:
            if _emb_rows is not None and len(keep) > 0:
                emb_path = filepath + ".emb.npy"
                # 原子写入：先写临时文件再 rename，防止崩溃残留半写文件
                emb_tmp = emb_path + f".tmp.{os.getpid()}"
                # INC-2026-09-14: np.save(str) 会自动追加 ".npy" 后缀，导致随后
                # os.replace(emb_tmp, ...) 找不到文件，二进制缓存从未真正更新，
                # 且每次保存遗留一个 6.5MB 垃圾文件。改用显式句柄写，路径可控。
                with open(emb_tmp, "wb") as _emb_f:
                    np.save(_emb_f, np.asarray(_emb_rows, dtype=np.float32))
                os.replace(emb_tmp, emb_path)
        except Exception as e:  # noqa: BLE001
            logger.warning("embeddings 二进制缓存写入失败（非阻塞）: %s", e)

    def _load(self, name: str) -> bool:
        """从 JSON 加载（任何异常都不移动/删除原文件）

        INC-2026-09-14: 旧实现一旦遇到任何加载异常（内存不足 / 并发读写竞争 /
        文件被占用）就用 os.rename 把主文件搬走并改名 .corrupted.<ts>，系统随之
        以空库启动 —— 主库"被损坏"其实是容错逻辑自己造成的（磁盘实证：
        vectordb_data/ 下累积多个 .corrupted 备份，主文件一度消失）。
        现改为：仅结构性错误才 copy2 备份，原文件永存；其余故障只告警。

        读路径刻意不持锁：_save 走「写 tmp + os.replace」原子替换，读到的要么
        是旧版本要么是新版本，不存在半截文件；而 filelock 每次释放都会 unlink
        锁文件，加读锁会让锁文件删除次数翻倍。
        """
        filepath = os.path.join(self._persist_path, f"{name}.json")
        if not os.path.exists(filepath):
            return False
        # 读路径不持锁（刻意设计）：_save 走「写 tmp + os.replace」原子替换，
        # 读到的要么是旧版本要么是新版本，不存在半截文件；而 filelock 每次释放
        # 都会 unlink 锁文件，读锁会把锁文件删除次数翻倍并触发外部批量删除守卫。
        # 数据安全改由「异常不移动原文件 + 空库覆盖守门」保证。
        return self._load_unlocked(name, filepath)

    def _load_unlocked(self, name: str, filepath: str) -> bool:
        """实际加载逻辑（与 _load 分离，便于日后单独加读锁或做落盘复算）

        2026-10-22 起：**读回时同样过滤已知坏数据** —— ``embedding_status ==
        "fallback_zero"`` 的文档在加载阶段即被排除。

        为什么写侧过滤不够（career-only 瘦包双启动实证）：``_save_unlocked`` 的写侧
        过滤只保证「今后不再变脏」，治不了**已经被旧版本污染过**的目录（线上实例、
        任何跑过旧包的副本）。这类目录重启后 ``count`` 非 0 ⇒ 跳过播种、计数器为 0
        （``VectorDB.embedding_fallback_count`` 只统计本进程新插入、读回不计）⇒
        ``/api/status`` 报 ``fallback_zero_docs:0`` / ``status:"ok"``，库里却全是零
        向量。读取侧过滤让这类历史部署**重启即自愈**。

        过滤**必须先于** ``.emb.npy`` 的行数比对：旧缓存是按未过滤的行数写的，过滤后
        ``arr.shape[0] != len(coll["ids"])`` 自然失配 ⇒ 回退 JSON 全量重建，不会出现
        「二进制缓存与 JSON 打架」的错位读取。过滤是幂等的 —— 即使陈旧文件永远不被
        重写，每次启动读到的视图都诚实。

        INC-2026-09-14 硬约束（**勿改为删除/移动/改名**）：旧实现在异常时用
        ``os.rename`` 把主文件搬走，导致「主库被容错逻辑自己搞坏」。本函数对磁盘上的
        污染文件**只读不写、不改名**：被过滤掉的文档的旧文件原样留着，等下一次合法
        ``_save`` 自然把它重写成干净内容；永不重写也不影响正确性。

        Returns:
            True 表示读到可用文档；False 表示文件缺失 / 解析失败 / **过滤后无可用
            文档** —— 调用方（``VectorDB._init_mem_store`` →
            ``app/lifespan._init_vector_db``）据此看到 ``count == 0`` 并重新播种、
            重新计数。
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw_ids = data["ids"]
            raw_texts = data["texts"]
            raw_metas = data["metas"]
            raw_embs = data.get("embeddings")
            # 列长一致性守卫：三列错位（半截写入 / 人工编辑损坏）时按索引取子集才会真的
            # 读错位，因此此时**不做过滤**、原样加载，保持旧行为，绝不因守卫本身抛错。
            if len(raw_ids) == len(raw_texts) == len(raw_metas):
                keep = [
                    i
                    for i, m in enumerate(raw_metas)
                    if not (isinstance(m, dict) and m.get("embedding_status") == "fallback_zero")
                ]
            else:
                keep = list(range(len(raw_ids)))
                logger.warning(
                    "InMemoryVectorStore 列长不一致（ids=%d texts=%d metas=%d），"
                    "跳过 fallback_zero 过滤、按原样加载: %s",
                    len(raw_ids), len(raw_texts), len(raw_metas), filepath,
                )
            if not keep:
                logger.warning(
                    "InMemoryVectorStore 加载 %s 时发现 %d 条文档全部为 E5 失败零向量占位，"
                    "视为空库（返回 False）⇒ 调用方将重新播种并重新计数，健康探针据此如实降级。"
                    "磁盘原文件保留未动（INC-2026-09-14：读路径绝不删除/改名主文件）。",
                    filepath, len(raw_ids),
                )
                return False
            filtered = len(keep) != len(raw_ids)
            if filtered:
                logger.warning(
                    "InMemoryVectorStore 过滤 %d 条 fallback_zero 零向量占位文档（保留 %d 条）: %s",
                    len(raw_ids) - len(keep), len(keep), filepath,
                )
            self._ensure_collection(name)
            coll = self._collections[name]
            coll["ids"] = [raw_ids[i] for i in keep]
            coll["texts"] = [raw_texts[i] for i in keep]
            coll["metas"] = [raw_metas[i] for i in keep]
            # JSON 里的 embeddings 与过滤同源处理：行数与原 ids 一致才按 keep 取，
            # 否则视为残缺（None / 行数不符）→ 统一落到 None，绝不猜测对齐关系。
            json_embs = None
            if raw_embs and len(raw_embs) == len(raw_ids):
                json_embs = [raw_embs[i] for i in keep] if filtered else raw_embs
            # 优先二进制 embeddings 缓存：np.load 二进制远快于 np.array(JSON tolist 重建)；
            # 仅当 .npy 存在且行数一致时复用，否则回退 JSON 全量重建（并回写缓存供下次命中）。
            emb_cache = filepath + ".emb.npy"
            emb_loaded = False
            if os.path.exists(emb_cache) and len(coll["ids"]) > 0:
                try:
                    arr = np.load(emb_cache)
                    # 验证维度：行数一致 + 向量维度与已加载 JSON 数据一致
                    json_dim = len(json_embs[0]) if json_embs and len(json_embs) > 0 else None
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
                if json_embs:
                    coll["embeddings"] = np.array(json_embs, dtype=np.float32)
                else:
                    coll["embeddings"] = None
                # 首次/失配：回写二进制缓存，使下次冷启动命中。
                # 本次加载发生过过滤时**不回写**：JSON 仍是脏的（写侧过滤只防未来），
                # 把它的过滤视图固化进缓存会让「缓存 = JSON 的什么子集」变得不可核对；
                # 读路径保持只读，脏目录每次都从 JSON 重建（幂等、成本可接受）。
                if coll["embeddings"] is not None and not filtered:
                    try:
                        np.save(emb_cache, coll["embeddings"])
                    except Exception:  # noqa: BLE001
                        pass
            self._norm_cache.pop(name, None)  # 新加载数据，使归一化缓存失效
            logger.info(f"InMemoryVectorStore 加载 {len(coll['ids'])} 条文档 from {name}")
            return True
        except Exception as e:
            # INC-2026-09-14: 旧实现用 os.rename 把主文件搬走。一旦遇到非结构性
            # 故障（内存不足 / 并发读写竞争 / 文件被占用），完好的主库会被误判
            # "损坏"并移走，系统随之以空库启动，运行态与对外口径脱节。
            # 现在：① 仅真正的结构/解析错误才备份；② 备份用 copy2，主文件永存；
            #       ③ 其余故障只告警，绝不移动或删除原文件。
            _structural = isinstance(e, (json.JSONDecodeError, ValueError, KeyError))
            if _structural:
                import shutil as _shutil
                import time as _time
                backup_path = filepath + f".corrupted.{int(_time.time())}"
                try:
                    _shutil.copy2(filepath, backup_path)
                    logger.error(
                        "InMemoryVectorStore 加载失败（结构损坏）: %s\n"
                        "  已备份副本到: %s（原文件保留未动）\n"
                        "  系统将以空库启动，请检查备份文件。",
                        e,
                        backup_path,
                    )
                except OSError as _oe:
                    logger.error(
                        "InMemoryVectorStore 加载失败且备份失败: %s / %s（原文件保留）",
                        e,
                        _oe,
                    )
            else:
                logger.error(
                    "InMemoryVectorStore 加载失败（非结构性故障，未备份、未移动原文件）: "
                    "%s: %s\n  常见原因：内存不足或并发读写竞争。原文件保持原样: %s",
                    type(e).__name__,
                    e,
                    filepath,
                )
            return False


class VectorDB:
    """向量数据库统一接口，封装 Milvus / InMemoryVectorStore 差异"""

    def __init__(self):
        self._milvus_connected = False
        self._mem_store: Optional[InMemoryVectorStore] = None
        self._embedding_fallback_count = 0  # E5 嵌入失败（如 sentence-transformers 缺失）走零向量兜底的次数

    @property
    def embedding_fallback_count(self) -> int:
        """E5 失败走零向量占位的累计文档数（只读）。

        2026-10-18 修复：D5 设计（``deliverables/engineering-assurance/
        D5-status-degradation-explicit-2026-09-23.md`` §2.1）明确要求「新增只读属性
        ``embedding_fallback_count``」，但落地时只写了私有字段
        ``_embedding_fallback_count`` —— 而 ``app/status.py`` 按**公开名**
        ``getattr(vector_db, "embedding_fallback_count", 0)`` 读取，默认值 0 于是
        恒生效：``/api/status`` 的 ``fallback_zero_docs`` 永远报 0，
        「embedding 降级」判定（``embedding_fallback > 0``）形同虚设 ——
        按本文件下方的降级判定逻辑，瘦包（无 E5、2245 条种子全零向量、其余组件无降级）
        因此仍会报 ``status:"ok"``。

        本属性落地后该缺口关闭。守护测试：
        ``tests/test_app_status_invariants.py`` 的
        ``test_status_probe_reads_real_vector_db_attrs``（契约：status.py 读的名字必须真实存在）
        与 ``test_embedding_fallback_counter_reaches_status_probe``（行为：计数→探针端到端）。
        """
        return self._embedding_fallback_count

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

    def _resolve_embeddings(self, chunks: list[dict], dim: int) -> list[list[float]]:
        """为一批 chunk 解析入库向量 —— InMemory 与 Milvus 两条路径的**唯一**实现。

        规则（与 D5 §2.1 一致）：

        1. 任一 chunk 自带 ``embedding`` ⇒ 视为已预计算，不再调 E5；
        2. 全都没有 ⇒ 整批调一次 ``embed_batch(prefix="passage")``；
        3. E5 不可用（未装 sentence-transformers / 模型加载失败）或个别元素为
           ``None`` ⇒ 该位置用**零向量**占位，``metadata.embedding_status`` 置为
           ``"fallback_zero"``，并使 ``embedding_fallback_count`` 自增。

        返回值与 ``chunks`` 等长、顺序一致，且**不含 None**（兜底元素是零向量）。
        副作用：会就地写入 ``chunk["metadata"]["embedding_status"]``。

        ── 为什么必须只有一份实现（2026-10-18）──────────────────────────────
        此前 ``_mem_insert`` 与 ``_milvus_insert`` 各写一份。Milvus 路径写的是
        ``c.get("embedding", [0.0] * dim)`` —— 既不尝试 E5、也不打 ``fallback_zero``
        标记、更不计数。而检索侧只排除 ``embedding_status != "fallback_zero"``，
        于是零向量会被当成正常向量参与 cosine 排序（相似度恒为 0，排名无意义，
        且不会报任何错）。种子路径 ``app/lifespan.py::_seed_vector_db`` 与
        ``rebuild_vectordb.py`` 都不预计算嵌入 ⇒「Milvus 已连接且集合为空」时
        必然踩中。抽成单一实现，杜绝两条路径再次分叉。
        守护：``tests/test_vector_db_embedding_fallback.py``。
        """
        precomputed: list = [c.get("embedding") for c in chunks]
        if not any(e is not None for e in precomputed):
            try:
                from db.embedder import embed_batch

                # 入库侧用 passage 前缀，与检索侧 query 前缀、netlearn_kb 向量库一致
                precomputed = embed_batch([c["text"] for c in chunks], prefix="passage")
                logger.info(f"E5 嵌入计算成功（{len(chunks)} 条文档）")
            except Exception as e:  # noqa: BLE001 — 嵌入不可用必须降级而非中断入库
                logger.warning(f"E5 嵌入失败({e})，使用零向量占位并标记 fallback_zero")

        resolved: list[list[float]] = []
        for i, c in enumerate(chunks):
            # 用下标而不是 zip：embed_batch 少返几条时必须能逐条判 None 并兜底，
            # 直接索引 precomputed[i] 会 IndexError 把整批入库打断。
            emb = precomputed[i] if i < len(precomputed) else None
            if emb is None:
                emb = [0.0] * dim
                meta = c.get("metadata")
                if not isinstance(meta, dict):
                    meta = {}
                    c["metadata"] = meta
                meta["embedding_status"] = "fallback_zero"
                self._embedding_fallback_count += 1
            resolved.append(emb)
        return resolved

    def _mem_insert(self, coll_name, chunks, save: bool = True):
        """InMemoryVectorStore 批量插入（E5 失败时使用零向量占位）

        Args:
            save: 透传给 InMemoryVectorStore.add()，False 时仅内存写入，需调用方 flush()。
        """
        if not self._mem_store:
            self._init_mem_store()

        dim = get_embedding_config().get("dimension", 768)
        # 向量解析（含 E5 兜底计数）统一走 _resolve_embeddings，勿在此重复实现
        embeddings_list = self._resolve_embeddings(chunks, dim)

        ids = [c.get("id", f"chunk_{i}") for i, c in enumerate(chunks)]
        docs = [c["text"] for c in chunks]
        metas = [c.get("metadata", {}) for c in chunks]

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
        # HNSW 搜索参数 ef 必须 > top_k（Milvus 硬性约束）。FrugalRAG 为 rerank 取大候选池时
        # top_k 可达 800（course_search_top_k 默认 800），固定 ef=128 会触发
        # "ef(128) should be larger than k(800)" 导致整条检索 500。故 ef 随 top_k 动态抬升。
        search_params = {"metric_type": "COSINE", "params": {"ef": max(128, int(top_k) + 1)}}
        results = col.search(
            data=[query_vector],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            expr=filter_expr,
            output_fields=["id_str", "text", "course", "chapter", "chapter_name", "type", "keywords"],
        )
        return [
            {
                # 主键是 INT64 auto_id（hit.id 为无意义自增整数），逻辑 id 在 id_str 字段；
                # 直接返回 hit.id 会因 RAGSearchResult.id:str 校验失败 500。
                "id": str(hit.entity.get("id_str") or ""),
                "text": hit.entity.get("text") or "",
                "score": hit.score,
                "metadata": {
                    "course": hit.entity.get("course") or "",
                    "chapter": hit.entity.get("chapter") or "",
                    "chapter_name": hit.entity.get("chapter_name") or "",
                    "type": hit.entity.get("type") or "",
                    "keywords": hit.entity.get("keywords") or "",
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
            schema = CollectionSchema(fields, description=f"芒得很职 KB: {coll_name}")
            col = Collection(coll_name, schema)
            index_params = {"metric_type": "COSINE", "index_type": "HNSW", "params": {"M": 16, "efConstruction": 200}}
            col.create_index("embedding", index_params)
            col.load()
        else:
            col = Collection(coll_name)
            col.load()

        # 向量解析（含 E5 兜底计数）与 InMemory 路径共用同一实现 —— 此前这里写的是
        # c.get("embedding", [0.0] * dim)，即「没有嵌入就静默当零向量」，既不调 E5、
        # 也不打 fallback_zero 标记（检索侧因此不会排除它）、更不进计数器。
        embeddings_col = self._resolve_embeddings(chunks, dim)
        entities = [
            [c["text"] for c in chunks],
            embeddings_col,
            [c.get("id", "") for c in chunks],
            [(c.get("metadata") or {}).get("subject", "") for c in chunks],
            [(c.get("metadata") or {}).get("source", "") for c in chunks],
            [(c.get("metadata") or {}).get("course", "") for c in chunks],
            [(c.get("metadata") or {}).get("chapter", "") for c in chunks],
            [(c.get("metadata") or {}).get("chapter_name", "") for c in chunks],
            [(c.get("metadata") or {}).get("type", "") for c in chunks],
            [(c.get("metadata") or {}).get("keywords", "") for c in chunks],
            [(c.get("metadata") or {}).get("embedding_status", "") for c in chunks],
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
