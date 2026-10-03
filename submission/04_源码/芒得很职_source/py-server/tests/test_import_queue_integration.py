# ============================================================
# 集成测试：导入队列（ADR-007）—— 单写者写路径 / 任务生命周期（真实 _run_job 驱动）
# ============================================================
# 对齐 Dev 实际实现（services.import_worker）：
#   submit(type_, source, params, submitted_by) -> 12-hex job_id
#   _run_job(job_id) 真实驱动：
#       _gather_files -> _process_file（monkeypatch 解析+嵌入）
#         -> vector_db.insert + vector_db.flush（在 store_lock 下）
#         -> _persist（写 journal 到 vectordb_data/import_jobs/<id>.json）
#
# 用受控 FakeVectorDB 桩替换 db.milvus_client.vector_db（记录 insert/flush/
# get_all_metadata/delete_by_ids 调用并保存 chunks），避免依赖真实文件 / 模型 / Milvus。
# CI 干净环境可直接跑。标记：@pytest.mark.import_queue
# ============================================================

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

pytest.importorskip("services.import_worker")

import db.embedder as eb  # monkeypatch embed_batch / embed_text
import db.milvus_client as mc  # patch vector_db
import import_pdfs  # monkeypatch process_file
import services.import_worker as iw_mod  # patch vector_db / JOURNAL_DIR

pytestmark = pytest.mark.import_queue

COLLECTION = "netlearn_kb"


class FakeVectorDB:
    """内存桩：记录 vector_db 的写调用，并按 id 保存 chunks（模拟持久化）。

    暴露 import_worker 真实写路径调用的方法：
    insert / flush / get_all_metadata / delete_by_ids（deliverable B 要求记录这些方法）。
    """

    def __init__(self):
        self.insert_calls = []
        self.flush_calls = []
        self.metadata_calls = []
        self.texts_calls = []
        self.delete_calls = []
        self._store = {}  # id -> chunk

    # ── 真实写路径调用的方法 ──
    def insert(self, collection_name, chunks, save=True):
        self.insert_calls.append((collection_name, list(chunks), save))
        for c in chunks:
            self._store[c["id"]] = c
        return len(chunks)

    def flush(self, collection_name=None):
        self.flush_calls.append(collection_name)
        return

    def get_all_metadata(self, collection_name, filter_dict=None):
        self.metadata_calls.append((collection_name, filter_dict))
        return [
            {"id": c["id"], "metadata": c.get("metadata", {})}
            for c in self._store.values()
        ]

    # F1 修复后 _clear_imported_type 改走 get_all_with_texts（两种实现均返回
    # (items, total)，每项含 id 与 metadata）。补齐该方法使 rebuild 回归测试对齐补丁。
    def get_all_with_texts(self, collection_name, skip=0, limit=20, filter_dict=None):
        self.texts_calls.append((collection_name, skip, limit, filter_dict))
        items = [
            {"id": c["id"], "content": c.get("text", ""), "metadata": c.get("metadata", {})}
            for c in self._store.values()
        ]
        total = len(items)
        sliced = items[skip : skip + limit]
        return sliced, total

    def delete_by_ids(self, collection_name, ids):
        self.delete_calls.append((collection_name, list(ids)))
        removed = 0
        for i in ids:
            if self._store.pop(i, None) is not None:
                removed += 1
        return removed

    # ── 仅供断言 ──
    def count(self, collection_name=None):
        return len(self._store)

    def chunks(self):
        return list(self._store.values())

    def ids(self):
        return set(self._store.keys())


@pytest.fixture
def fake_vector_db(monkeypatch):
    """用 FakeVectorDB 替换 import_worker 与 milvus_client 两处对 vector_db 的引用。

    import_worker 在模块加载时 `from db.milvus_client import vector_db` 绑定了名字，
    因此必须同时 patch iw_mod.vector_db 与 mc.vector_db 才能让真实写路径命中桩。
    """
    fake = FakeVectorDB()
    monkeypatch.setattr(iw_mod, "vector_db", fake)
    monkeypatch.setattr(mc, "vector_db", fake)
    yield fake


@pytest.fixture
def started_worker(tmp_path, fake_vector_db, monkeypatch):
    """最小启动：设置 queue / executor，并把 journal 落盘重定向到 tmp。

    _loop 必须在 async 测试体内用 asyncio.get_running_loop() 设置
    （sync fixture 上下文中无法可靠取到 pytest-asyncio 的当前事件循环）。
    """
    import_worker = iw_mod.import_worker
    monkeypatch.setattr(iw_mod, "JOURNAL_DIR", tmp_path / "import_jobs")
    # 将 DOCS_DIR 重定向到受控 tmp_path（与单测约定一致），使 fixture 源路径落在
    # 允许目录内，能被 S1 护栏正常接受（测试的是逻辑，而非越界读服务器文件）。
    monkeypatch.setattr(iw_mod, "DOCS_DIR", tmp_path)
    import_worker._queue = asyncio.Queue()
    import_worker._executor = ThreadPoolExecutor(max_workers=2)
    yield import_worker
    import_worker._executor.shutdown(wait=False)
    import_worker._executor = None
    import_worker._queue = None
    import_worker._jobs.clear()


def _canned_chunks(n, prefix="imp"):
    return [
        {
            "id": f"{prefix}_{i}",
            "text": f"sample chunk {i}",
            "metadata": {"source": "fixture", "type": "imported", "chunk_index": i},
        }
        for i in range(n)
    ]


# ────────────────────────────────────────────────────────────
# TC-B（deliverable B）：submit -> _run_job 真实驱动 -> 经 FakeVectorDB 入库 + journal 落盘
# ────────────────────────────────────────────────────────────
async def test_submit_drives_run_job_through_fake_store_and_writes_journal(
    started_worker, fake_vector_db, monkeypatch, tmp_path
):
    from services.import_worker import STATUS_SUCCEEDED

    worker = started_worker
    worker._loop = asyncio.get_running_loop()

    chunks = _canned_chunks(3)
    # 解析：返回受控 chunks（avoid 真实 PDF 解析 / torch / docling）
    monkeypatch.setattr(import_pdfs, "process_file", lambda *a, **k: chunks)
    # 嵌入：确定性零向量（avoid 真实 E5）
    monkeypatch.setattr(eb, "embed_batch", lambda texts: [[0.0] * 768 for _ in texts])
    monkeypatch.setattr(eb, "embed_text", lambda t: [0.0] * 768)

    src = tmp_path / "fixture.pdf"
    src.write_text("dummy fixture source")

    job_id = await worker.submit("pdf", str(src), {}, "admin")
    await worker._run_job(job_id)

    job = worker.get_job(job_id)
    assert job["status"] == STATUS_SUCCEEDED, (
        f"job 应 succeeded，实际 {job['status']} error={job.get('error')}"
    )

    # (1) insert 确实发生过（单写者写路径命中向量库）
    assert fake_vector_db.insert_calls, "vector_db.insert 从未被调用"

    # (2) chunks 确实进入 fake store
    assert fake_vector_db.ids() == {f"imp_{i}" for i in range(3)}, (
        f"fake store 中的 chunks 不符: {fake_vector_db.ids()}"
    )
    assert fake_vector_db.count() == 3

    # (3) journal 文件写入 vectordb_data/import_jobs/<id>.json
    journal = tmp_path / "import_jobs" / f"{job_id}.json"
    assert journal.exists(), "journal 未写入 vectordb_data/import_jobs/<id>.json"
    data = json.loads(journal.read_text(encoding="utf-8"))
    assert data["id"] == job_id
    assert data["status"] == STATUS_SUCCEEDED
    assert data["type"] == "pdf"


# ────────────────────────────────────────────────────────────
# TC-B2：rebuild 路径（清旧 -> 重导）走 get_all_metadata + delete_by_ids 桩
# ────────────────────────────────────────────────────────────
async def test_run_job_with_rebuild_exercises_delete_by_ids_on_fake_store(
    started_worker, fake_vector_db, monkeypatch, tmp_path
):
    from services.import_worker import STATUS_SUCCEEDED

    worker = started_worker
    worker._loop = asyncio.get_running_loop()

    chunks = _canned_chunks(3)
    monkeypatch.setattr(import_pdfs, "process_file", lambda *a, **k: chunks)
    monkeypatch.setattr(eb, "embed_batch", lambda texts: [[0.0] * 768 for _ in texts])
    monkeypatch.setattr(eb, "embed_text", lambda t: [0.0] * 768)

    src = tmp_path / "fixture.pdf"
    src.write_text("dummy")

    # 预置 2 条已存在的 imported 类型 chunks（模拟重建前的历史数据）
    # -> rebuild 路径应经 get_all_metadata 找到它们并经 delete_by_ids 清除
    for i in range(2):
        fake_vector_db._store[f"old_{i}"] = {
            "id": f"old_{i}",
            "text": f"legacy chunk {i}",
            "metadata": {"source": "legacy", "type": "imported", "chunk_index": i},
        }

    # rebuild=True -> _run_job 先 _clear_imported_type（走 get_all_metadata + delete_by_ids）
    job_id = await worker.submit("pdf", str(src), {"rebuild": True}, "admin")
    await worker._run_job(job_id)

    job = worker.get_job(job_id)
    assert job["status"] == STATUS_SUCCEEDED

    # rebuild 清理路径确实被桩记录（get_all_with_texts + delete_by_ids 都被调用）
    assert fake_vector_db.texts_calls, "rebuild 路径未调用 get_all_with_texts"
    assert fake_vector_db.delete_calls, "rebuild 路径未调用 delete_by_ids"

    # 清旧（2 条 legacy）后重新 insert 3 条，最终仅剩本次导入的 3 条
    assert fake_vector_db.count() == 3, (
        f"rebuild 后 chunks 数应为 3，实际 {fake_vector_db.count()}"
    )
    assert fake_vector_db.ids() == {f"imp_{i}" for i in range(3)}, (
        f"rebuild 后残留 legacy chunks: {fake_vector_db.ids()}"
    )


# ────────────────────────────────────────────────────────────
# TC-S1：source 路径穿越护栏（S1 修复点）
#   - 显式路径落在 documents/教材（DOCS_DIR）内 -> 正常返回该文件
#   - 越界绝对路径（如 /etc/passwd）-> 必须被拒、返回空列表（禁止读服务器任意文件）
# ────────────────────────────────────────────────────────────
def test_gather_files_source_guardrail_rejects_out_of_bounds(monkeypatch, tmp_path):
    from services.import_worker import import_worker as _iw

    # 将 DOCS_DIR 重定向到受控 tmp_path（模拟 documents/教材）
    monkeypatch.setattr(iw_mod, "DOCS_DIR", tmp_path)

    in_file = tmp_path / "in.pdf"
    in_file.write_text("dummy fixture source")  # 真实存在于 DOCS_DIR 内

    # 1) 内源：显式路径落在 DOCS_DIR 内 -> 收集到该文件
    ok = _iw._gather_files({"type": "pdf", "source": str(in_file), "params": {}})
    assert ok == [in_file], f"S1 护栏应收集 DOCS_DIR 内文件，实际 {ok}"

    # 2) 越界绝对路径：/etc/passwd 不在 DOCS_DIR 内 -> 必须被拒（返回空列表）
    rejected = _iw._gather_files({"type": "pdf", "source": "/etc/passwd", "params": {}})
    assert rejected == [], f"S1 护栏应拒绝越界绝对路径，实际 {rejected}"
