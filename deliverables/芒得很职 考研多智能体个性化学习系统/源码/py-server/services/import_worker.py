# ============================================================
# 导入队列服务化 — 后端内部导入 Worker（ADR-007）
# ------------------------------------------------------------
# 让后端成为向量库的唯一写者（single writer）：
#   1. 导入逻辑（解析→分块→embedding→insert）全部在后端进程内执行；
#   2. 所有向量库变更（在线 /upload、/upsert、/reindex 与导入 Worker）
#      统一经 store_lock 串行化，从根上消除跨进程 last-writer-wins；
#   3. CPU 重活（PDF 解析 / E5 encoding / OCR）卸载到线程池，事件循环不冻结。
#
# 硬约束：uvicorn 必须 --workers 1（单进程）。多进程会重新引入多写者。
# ============================================================

import os
import sys
import asyncio
import logging
import time
import uuid
import json
import tempfile
import functools
from typing import Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# F6：跨进程单写者身份锁（filelock）。缺失时降级为仅依赖 --workers 1 约定，
# 无法在运行时拦截多进程多写者，但 ADR-007 的硬约束仍由启动期环境变量检查兜底。
try:
    from filelock import FileLock, Timeout as FileLockTimeout
    _HAS_FILELOCK = True
except ImportError:
    FileLock = None
    FileLockTimeout = Exception
    _HAS_FILELOCK = False

from db.milvus_client import vector_db
from config import load_config

logger = logging.getLogger("netlearn.import_worker")


# ── F6 辅助：解析启动命令的 uvicorn worker 数 ──
# main.py 的硬约束守卫（UVICORN_WORKERS/WEB_CONCURRENCY 环境变量）覆盖不到
# `uvicorn --workers N` 的纯 CLI 形式；本函数对其做*前置*解析（运行时仍由 filelock 兜底）。
# 返回解析到的 worker 数，缺省 1；任何解析异常安全回退 1（不抛错，避免影响正常启动）。
def _resolve_uvicorn_workers(argv: Optional[list[str]] = None) -> int:
    """解析 argv 中的 `--workers N` / `--workers=N`，回退环境变量，缺省 1。"""
    import os

    if argv is None:
        argv = sys.argv[1:]
    try:
        for i, tok in enumerate(argv):
            if tok == "--workers" and i + 1 < len(argv):
                return int(argv[i + 1])
            if tok.startswith("--workers="):
                return int(tok.split("=", 1)[1])
        env = os.environ.get("UVICORN_WORKERS") or os.environ.get("WEB_CONCURRENCY")
        return int(env) if env else 1
    except (ValueError, IndexError):
        return 1

COLLECTION = "netlearn_kb"
PROJECT_ROOT = Path(__file__).parent.parent
DOCS_DIR = PROJECT_ROOT / "documents" / "教材"
JOURNAL_DIR = PROJECT_ROOT / "vectordb_data" / "import_jobs"

# ── 任务状态机 ──
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
STATUS_INTERRUPTED = "interrupted"


class ImportWorker:
    """进程内导入队列 + 单消费者 Worker。"""

    def __init__(self):
        self._queue: Optional[asyncio.Queue] = None
        self._store_lock = asyncio.Lock()        # 单写者串行化（核心不变式）
        self._jobs: dict[str, dict] = {}
        self._task: Optional[asyncio.Task] = None
        self._executor: Optional[ThreadPoolExecutor] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._enabled = True
        self._writer_lock = None  # 跨进程单写者锁（filelock），强绑定 writer 身份

    # ── 单写者不变式（公开锁，供 api.knowledge 等在线写端点共享）──
    @property
    def store_lock(self) -> asyncio.Lock:
        """公开 asyncio 锁：在线写端点（/upload、/upsert、/delete、/batch-commit、
        /reindex、/clear）与导入 Worker 共用同一把锁，从根上消除跨路径 last-writer-wins。

        ADR-007 的 single-writer 保证正是建立在这“同一把锁对象”之上 ——
        knowledge.py 通过 import_worker.store_lock 引用，本属性返回内部 _store_lock，
        因此两边是同一对象（见 test_import_queue_e2e 的 6.3 遗留对比测试）。
        """
        return self._store_lock

    # ── 生命周期 ──
    async def start(self):
        cfg = load_config().get("import_worker", {})
        self._enabled = cfg.get("enabled", True)
        if not self._enabled:
            logger.info("[import] Worker 已禁用 (import_worker.enabled=false)")
            return

        # F6：前置解析启动命令的 `--workers N` CLI 形式（main.py 的环境变量软守卫
        # 覆盖不到），与下方 filelock 运行时兜底共同消除多写者(last-writer-wins)。
        _cli_workers = _resolve_uvicorn_workers()
        if _cli_workers > 1:
            raise RuntimeError(
                f"[import] F6 硬约束违规：启动命令解析到 --workers {_cli_workers} (>1)。"
                " 多进程会重新引入多写者(last-writer-wins)，必须 --workers 1 单进程运行。"
            )

        # F6：跨进程单写者强绑定。main.py 仅读环境变量的软守卫无法覆盖
        # `uvicorn --workers N` 的 CLI 形式；这里用 filelock 在进程级抢 writer 锁，
        # 抢不到 = 已存在其它写者（多进程/多 worker），直接 fail-fast 拒绝启动，
        # 从根上消除 last-writer-wins。锁随进程生命周期持有，stop() 释放。
        if _HAS_FILELOCK:
            WRITER_LOCK_PATH = JOURNAL_DIR.parent / ".import_writer.lock"
            self._writer_lock = FileLock(str(WRITER_LOCK_PATH), timeout=2)
            try:
                self._writer_lock.acquire(blocking=True, timeout=2)
            except FileLockTimeout:
                raise RuntimeError(
                    "[import] F6 单写者锁获取失败：检测到另一进程已持有 writer 锁。"
                    " 禁止以多进程/多 worker 方式启动（如 uvicorn --workers N），"
                    " 必须 --workers 1 单进程运行，否则会重引入多写者(last-writer-wins)。"
                )
        else:
            logger.warning("[import] filelock 不可用，无法强制跨进程单写者锁；仅依赖环境变量守卫")

        self._loop = asyncio.get_running_loop()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="import")
        self._queue = asyncio.Queue()
        self._task = self._loop.create_task(self._consume())
        JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("[import] 导入队列 Worker 已启动（单消费者 + store_lock 串行化）")

    async def stop(self):
        if getattr(self, "_writer_lock", None) is not None:
            try:
                self._writer_lock.release()
            except Exception:
                pass
            self._writer_lock = None
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None
        logger.info("[import] 导入队列 Worker 已停止")

    # ── 对外接口 ──
    async def submit(self, type_: str, source: Optional[str], params: dict, submitted_by: str = "admin") -> str:
        job_id = uuid.uuid4().hex[:12]
        now = time.time()
        job = {
            "id": job_id,
            "type": type_,
            "source": source or "scan",
            "params": params or {},
            "submitted_by": submitted_by,
            "status": STATUS_QUEUED,
            "progress": {
                "stage": "queued",
                "total_files": 0,
                "processed_files": 0,
                "total_chunks": 0,
                "inserted_chunks": 0,
                "current_file": "",
            },
            "error": None,
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "cancel_requested": False,
        }
        self._jobs[job_id] = job
        if self._queue is not None:
            await self._queue.put(job_id)
        else:
            job["status"] = STATUS_FAILED
            job["error"] = "导入 Worker 未运行（import_worker.enabled=false）"
        self._persist(job)
        return job_id

    def get_job(self, job_id: str) -> Optional[dict]:
        return self._jobs.get(job_id)

    def list_jobs(self, status: Optional[str] = None) -> list[dict]:
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j["status"] == status]
        jobs.sort(key=lambda j: j["created_at"], reverse=True)
        return jobs

    async def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        job["cancel_requested"] = True
        self._persist(job)
        return True

    # ── 消费者 ──
    async def _consume(self):
        while True:
            job_id = await self._queue.get()
            try:
                await self._run_job(job_id)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # 单个 job 失败不影响消费者
                logger.exception(f"[import] job {job_id} 处理异常: {e}")
            finally:
                self._queue.task_done()

    async def _run_job(self, job_id: str):
        job = self._jobs[job_id]
        job["status"] = STATUS_RUNNING
        job["started_at"] = time.time()
        self._persist(job)
        try:
            files = self._gather_files(job)
            # 可选：rebuild 仅在确实扫到文件后才清理旧数据，避免“清空后 0 文件”静默丢数据
            if job["params"].get("rebuild"):
                if files:
                    await self._clear_imported_type(job["type"])
                else:
                    logger.warning(f"[import][{job_id}] rebuild 请求但扫描到 0 文件，已跳过清理以防数据丢失")
            job["progress"]["total_files"] = len(files)
            job["progress"]["stage"] = "processing"
            self._persist(job)
            logger.info(f"[import][{job_id}] 扫描到 {len(files)} 个文件")

            inserted_total = 0
            failed_files = 0
            for idx, fp in enumerate(files):
                if job["cancel_requested"]:
                    job["status"] = STATUS_CANCELLED
                    logger.info(f"[import][{job_id}] 收到取消请求，在文件间隙停止")
                    break
                job["progress"]["current_file"] = str(fp)
                try:
                    n = await self._process_file(fp, job)
                    if n == -1:  # 解析/引擎失败（docling 等）约定值
                        failed_files += 1
                    else:
                        inserted_total += max(n, 0)
                except Exception as e:
                    failed_files += 1
                    logger.warning(f"[import][{job_id}] 文件处理失败 {fp}: {e}")
                job["progress"]["processed_files"] = idx + 1
                job["progress"]["inserted_chunks"] = inserted_total
                self._persist(job)

            if job["status"] == STATUS_RUNNING:
                # C1/C2：扫到文件但全部解析失败 → 标 FAILED，不谎报 SUCCEEDED
                if files and failed_files == len(files) and inserted_total == 0:
                    job["status"] = STATUS_FAILED
                    job["error"] = f"全部 {len(files)} 个文件解析/导入失败（无有效文本入库）"
                else:
                    job["status"] = STATUS_SUCCEEDED
                job["progress"]["stage"] = "done"
        except asyncio.CancelledError:
            job["status"] = STATUS_CANCELLED
            raise
        except Exception as e:
            job["status"] = STATUS_FAILED
            job["error"] = str(e)[:500]
            logger.exception(f"[import][{job_id}] job 失败: {e}")
        finally:
            job["finished_at"] = time.time()
            self._persist(job)

    # ── 文件收集 ──
    def _gather_files(self, job: dict) -> list[Path]:
        type_ = job["type"]
        source = job.get("source") or "scan"
        subject_filter = job["params"].get("subject_filter")

        paths: list[Path] = []
        if source and source != "scan":
            _p = Path(source)
            if not _p.is_absolute():
                _p = DOCS_DIR / _p
            _p = _p.resolve()
            # 安全护栏：显式路径必须落在 documents/教材 内，禁止越界读服务器任意文件
            if DOCS_DIR.resolve() in _p.parents or _p.resolve() == DOCS_DIR.resolve():
                if _p.exists() and _p.is_file():
                    paths = [_p]
            else:
                logger.warning(f"[import] 拒绝越界 source: {source}（不在 {DOCS_DIR} 内）")
        else:
            paths = []
            if type_ == "docling":
                # docling 仅处理扫描版 PDF（文字版由 pdf 路径处理）
                try:
                    from import_docling import SCANNED_PDFS
                    for rel in SCANNED_PDFS:
                        p = DOCS_DIR / rel
                        if p.exists():
                            paths.append(p)
                except Exception as e:
                    logger.warning(f"[import] 加载 docling SCANNED_PDFS 失败，docling 扫描跳空: {e}")
            else:
                supported = {".pdf", ".pptx", ".docx", ".doc"}
                if DOCS_DIR.exists():
                    for root, _dirs, files in os.walk(str(DOCS_DIR)):
                        for f in files:
                            if Path(f).suffix.lower() in supported:
                                paths.append(Path(root) / f)

        if subject_filter:
            paths = [p for p in paths if subject_filter in p.name]

        # 去重（保持顺序）
        seen, uniq = set(), []
        for p in paths:
            key = str(p)
            if key not in seen:
                seen.add(key)
                uniq.append(p)
        return uniq

    # ── 单文件处理：解析→分块→embedding→insert(+flush) ──
    async def _process_file(self, filepath: Path, job: dict) -> int:
        type_ = job["type"]
        params = job["params"]
        loop = self._loop

        # 1) 解析 + 分块（线程池，CPU/IO 重活）
        if type_ == "docling":
            # F20 修复：semantic_chunk / detect_subject 定义在 import_pdfs
            # （import_docling 仅定义 convert_with_docling / import_all / SCANNED_PDFS），
            # 原写法从 import_docling 导入两个不存在的符号 → ImportError，docling 路径完全不可用。
            from import_docling import convert_with_docling
            from import_pdfs import semantic_chunk, detect_subject
            max_pages = int(params.get("max_pages", 100))
            try:
                text = await loop.run_in_executor(
                    self._executor, functools.partial(convert_with_docling, str(filepath), max_pages)
                )
            except Exception as e:
                # docling + OCR 全部不可用：记录失败而非静默返回 0（ADR-007 C1）
                logger.warning(f"[import] docling 解析失败 {filepath}: {e}")
                return -1  # 约定 -1 = 解析/引擎失败（区别于 0 条内容）
            if not text or not text.strip():
                return -1
            subject = detect_subject(str(filepath))
            raw_chunks = semantic_chunk(text)
            chunks = []
            for i, c in enumerate(raw_chunks):
                cid = uuid.uuid5(uuid.NAMESPACE_URL, f"docling_{filepath}_{i}").hex[:12]
                chunks.append({
                    "id": f"docling_{cid}",
                    "text": c,
                    "metadata": {"subject": subject, "chapter": "Docling导入",
                                  "type": "docling", "source": filepath.name, "chunk_index": i},
                })
        else:
            # pdf / textbook / 通用：import_pdfs.process_file 覆盖 PDF/PPTX/DOCX/DOC
            from import_pdfs import process_file
            use_ocr = bool(params.get("use_ocr", False))
            chunks = await loop.run_in_executor(
                self._executor, functools.partial(process_file, str(filepath), False, use_ocr)
            )
            if not chunks:
                return 0

        # 2) embedding（线程池，E5 CPU 重活；失败降级零向量）
        texts = [c["text"] for c in chunks]
        embeddings = await loop.run_in_executor(self._executor, self._embed, texts)

        vector_chunks = []
        for c, emb in zip(chunks, embeddings):
            vc = dict(c)
            vc["embedding"] = emb
            vector_chunks.append(vc)

        # 3) 入库 + 落盘（持 store_lock，单写者不变式；每文件 checkpoint 减小崩溃丢失窗口）
        def _write():
            vector_db.insert(COLLECTION, vector_chunks, save=False)
            vector_db.flush(COLLECTION)

        async with self._store_lock:
            await loop.run_in_executor(self._executor, _write)

        return len(vector_chunks)

    # ── rebuild 清理 ──
    async def _clear_imported_type(self, type_: str):
        """rebuild 前清理旧数据（F1 修复）。

        原实现调 get_all_metadata() 并假设返回 [{id, metadata:{type}}]，但真实 VectorDB
        两种实现均无 id 字段（InMemory 返裸 metadata；Milvus 返字段 dict）→ m.get("metadata",{})
        .get("type") 永远 None → ids=[] → delete_by_ids([]) 静默 no-op，旧 chunk 不被清理。

        改用 get_all_with_texts()（两种实现均返回 (items, total)，每项含 id 与 metadata），
        分页遍历取 id+metadata.type；删除走 delete_by_ids（Milvus 分支见 milvus_client 鲁棒处理）。
        """
        type_key = "docling" if type_ == "docling" else "imported"

        def _clear():
            to_delete: list[str] = []
            skip = 0
            page = 500
            while True:
                items, total = vector_db.get_all_with_texts(COLLECTION, skip=skip, limit=page)
                for it in items:
                    if it.get("metadata", {}).get("type") == type_key:
                        cid = it.get("id")
                        if cid:
                            to_delete.append(str(cid))
                if not items or skip + len(items) >= total:
                    break
                skip += len(items)
            if to_delete:
                vector_db.delete_by_ids(COLLECTION, to_delete)
                vector_db.flush(COLLECTION)
            return len(to_delete)

        async with self._store_lock:
            n = await self._loop.run_in_executor(self._executor, _clear)
            logger.info(f"[import] rebuild 清理 type={type_key}: 删除 {n} 条旧数据")

    # ── 工具 ──
    @staticmethod
    def _embed(texts: list[str]) -> list[list[float]]:
        try:
            from db.embedder import embed_batch
            return embed_batch(texts)
        except Exception as e:
            logger.warning(f"[import] E5 编码失败，使用零向量: {e}")
            import numpy as np
            return [np.zeros(768).tolist() for _ in texts]

    def _persist(self, job: dict):
        """把 job 状态持久化到 journal 文件（崩溃后可审计/标记 interrupted）。"""
        try:
            JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
            path = JOURNAL_DIR / f"{job['id']}.json"
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(job, f, ensure_ascii=False, default=str)
            os.replace(tmp, path)
        except Exception as e:
            logger.warning(f"[import] job journal 写入失败（非阻塞）: {e}")


# 模块级单例：路由、lifespan、knowledge.py 写端点共享同一实例与同一把锁
import_worker = ImportWorker()
