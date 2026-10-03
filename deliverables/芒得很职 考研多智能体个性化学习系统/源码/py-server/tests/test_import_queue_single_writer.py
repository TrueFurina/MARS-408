# ============================================================
# 集成扩展：单写者不变式 / 线程池卸载 / 串行化 / Milvus 语义 / 去重回归（ADR-007）
# ============================================================
# 发布门禁标记：@pytest.mark.import_queue（合并进 tests/test_import_queue_* 门禁）
#
# 设计要点（修复“简单重标即 Red”的根因）：
#   * import_worker 是模块级单例，其 _store_lock 是 asyncio.Lock()，首次 await 时绑定到
#     当时运行的 event loop。兄弟文件（test_import_queue_integration / e2e）的 async 测试
#     在 pytest-asyncio 的 loop 上 await 过该锁 → 锁被绑定到那个 loop。若本文件再用
#     asyncio.new_event_loop() 自建 loop 并 await 同一把锁 → RuntimeError「bound to a
#     different event loop」→ TC-1 直接 FAIL 且 _consume 任务永远拿不到锁 → 进程中止。
#   * 原 worker_and_loop 自建 loop 后仅 run_until_complete(start()) 启动消费者，之后 loop
#     停止；job 类用例用阻塞 time.sleep 轮询 _wait，事件循环不再驱动 _consume → job 永远
#     queued（30s 超时），embedding 从未执行（TC-4 FAIL）。
#
# 修复：
#   * 每个测试用函数级【全新 ImportWorker 实例】（自带独立 _store_lock + 独立 loop），
#     彻底规避跨文件的「单例锁 / loop 绑定」污染；单写者不变式在实例自身锁上验证，语义等价。
#   * 以 pytest-asyncio 的 running loop 驱动：async fixture 内 await import_worker.start()，
#     测试体内 await submit / await _wait_async，消费者与测试共用同一 loop，天然串行推进，
#     不再需要手动 new_event_loop / set_event_loop / run_until_complete。
#   * probe_writes_direct 改为 async，直接 await，不再 run_until_complete（避免
#     “This event loop is already running”）。
#
# 保留 5 个用例的独特断言（LWW 无重复 / 线程池卸载 / 串行度=1 / Milvus 语义 / 去重 xfail）。
# TC-12 保持 @pytest.mark.xfail(strict=False)（Gap B 已知缺口，不应改绿）。
# 不改动 services/import_worker.py 等生产代码。
# ============================================================

import asyncio
import threading
import time

import pytest

pytest.importorskip("services.import_worker")

pytestmark = pytest.mark.import_queue

from tests.helpers.concurrency import (
    assert_no_loss_no_dup,
    make_chunks,
    probe_writes_direct,
)

COLLECTION = "netlearn_kb"


@pytest.fixture(autouse=True)
def isolate_vectordb(tmp_path, monkeypatch):
    import db.milvus_client as mc
    import services.import_worker as iw

    # 强制 InMemory 回退（避免 pymilvus 原生库在 Windows 段错误），落盘重定向到 tmp
    monkeypatch.setattr(mc, "MILVUS_AVAILABLE", False)
    orig_init = mc.InMemoryVectorStore.__init__

    def _init(self, persist_path=str(tmp_path), *a, **k):
        orig_init(self, persist_path, *a, **k)

    monkeypatch.setattr(mc.InMemoryVectorStore, "__init__", _init)
    monkeypatch.setattr(iw, "JOURNAL_DIR", tmp_path / "import_jobs")
    yield


@pytest.fixture
def fake_embedder(monkeypatch):
    import hashlib
    import numpy as np

    import db.embedder as eb

    def fake_batch(texts):
        out = []
        for t in texts:
            h = hashlib.md5(t.encode()).digest()
            vec = np.frombuffer(h, dtype=np.float32)[:8].tolist()
            n = np.linalg.norm(vec) or 1.0
            out.append((np.array(vec) / n).tolist())
        return out

    monkeypatch.setattr(eb, "embed_batch", fake_batch)
    monkeypatch.setattr(eb, "embed_text", lambda t: fake_batch([t])[0])
    yield


@pytest.fixture
async def worker_and_loop(isolate_vectordb, fake_embedder, tmp_path, monkeypatch):
    from db.milvus_client import vector_db, InMemoryVectorStore
    import services.import_worker as iw_mod
    from services.import_worker import ImportWorker

    # 强制启用 Worker：config.json 可能 import_worker.enabled=false（本地关闭导入队列），
    # 但本测试套件需要真实消费者线程，monkeypatch load_config 使 start() 进入启用分支。
    monkeypatch.setattr(iw_mod, "load_config", lambda: {"import_worker": {"enabled": True}})

    # 全新实例 + 独立 _store_lock + 独立 loop：规避模块单例锁在兄弟文件被绑到别的 loop。
    # 直接用 tmp 下的【空】store，避免加载真实 ./vectordb_data（含 seed 数据）污染断言。
    vector_db._milvus_connected = False
    vector_db._mem_store = InMemoryVectorStore(persist_path=str(tmp_path))

    w = ImportWorker()
    # 在 pytest-asyncio 的 running loop 上启动消费者；_loop 与测试 loop 完全一致。
    await w.start()
    yield w, w._loop
    await w.stop()
    vector_db._mem_store = None
    vector_db._milvus_connected = False


def _patch_ingest(w, monkeypatch, chunks, fake_path):
    """注入受控 chunks：worker 扫描到 fake_path，process_file 返回 chunks。"""
    import import_pdfs

    monkeypatch.setattr(import_pdfs, "process_file", lambda *a, **k: chunks)
    monkeypatch.setattr(w, "_gather_files", lambda job: [__import__("pathlib").Path(fake_path)])


async def _wait(w, jid, timeout=30.0):
    """异步等待 job 终态：用 await asyncio.sleep 让出循环，消费者得以推进。

    原实现用阻塞 time.sleep → 事件循环停转、_consume 永远拿不到循环 → job 卡 queued。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = w.get_job(jid)
        if job and job["status"] in ("succeeded", "failed", "cancelled"):
            return job
        await asyncio.sleep(0.05)
    return w.get_job(jid)


def _store_ids():
    from db.milvus_client import vector_db

    items, _ = vector_db.get_all_with_texts(COLLECTION, limit=100000)
    return [it["id"] for it in items]


def _count():
    from db.milvus_client import vector_db

    return vector_db.count(COLLECTION)


def _last(w):
    jobs = w.list_jobs()
    return jobs[0]["id"] if jobs else None


# ── TC-1：单写者消除 last-writer-wins（核心验收 / 接受准则）──
async def test_single_writer_eliminates_lww(worker_and_loop):
    """两条写路径都经 worker._store_lock 串行 insert（单写者不变式）。

    直接复用 worker 真实的写机制（_store_lock + 线程池），模拟"在线写 + worker 写"
    并发到达，验证在共享锁下不产生 last-writer-wins 覆盖/截断。
    这是 ADR-007 「彻底消除 LWW」的核心证明：store 中 id 恰好 = upload∪import，无重复。
    """
    w, loop = worker_and_loop
    upload = make_chunks("upload", 50)
    imp = make_chunks("import", 50)
    res = await probe_writes_direct(w, upload, imp, loop=loop)
    assert_no_loss_no_dup(_store_ids(), res["upload_ids"], res["import_ids"])


# ── TC-4：重活在独立线程执行，事件循环不被阻塞 ──
async def test_heavy_work_offloaded_to_threadpool(worker_and_loop, monkeypatch, tmp_path):
    import db.embedder as eb

    recorded = {"thread": None}

    def _fake_batch(texts):
        recorded["thread"] = threading.current_thread()
        time.sleep(0.02)  # 模拟 CPU 重活（E5 encoding）
        return [[0.0] * 768 for _ in texts]

    # 覆盖 fake_embedder 注入的 embed_batch，记录执行线程
    monkeypatch.setattr(eb, "embed_batch", _fake_batch)

    w, loop = worker_and_loop
    chunks = make_chunks("off", 3)
    _patch_ingest(w, monkeypatch, chunks, str(tmp_path / "x.pdf"))
    jid = await w.submit("pdf", str(tmp_path / "x.pdf"), {}, "admin")
    await _wait(w, jid)

    assert recorded["thread"] is not None, "embedding 从未执行"
    assert recorded["thread"] != threading.main_thread(), (
        "embedding 应在独立线程执行（否则事件循环线程被阻塞，在线请求会挂起）"
    )


# ── TC-5：并发 job 串行处理，写并发度恒为 1 ──
async def test_concurrent_jobs_serialized(worker_and_loop, monkeypatch, tmp_path):
    from db.milvus_client import vector_db

    state = {"current": 0, "max": 0}
    gate = threading.Lock()
    orig = vector_db.insert

    def _ins(coll, chunks, save=True):
        with gate:
            state["current"] += 1
            state["max"] = max(state["max"], state["current"])
        try:
            return orig(coll, chunks, save=save)
        finally:
            with gate:
                state["current"] -= 1

    monkeypatch.setattr(vector_db, "insert", _ins)

    w, loop = worker_and_loop
    jids = []
    for i in range(3):
        chunks = make_chunks(f"c{i}", 5)
        _patch_ingest(w, monkeypatch, chunks, str(tmp_path / f"x{i}.pdf"))
        jids.append(
            await w.submit("pdf", str(tmp_path / f"x{i}.pdf"), {}, "admin")
        )
    for j in jids:
        await _wait(w, j)

    assert state["max"] <= 1, f"单写者下并发 insert 度应为 1，实际峰值={state['max']}"


# ── TC-15：Milvus 语义下（flush no-op / insert append）worker 仍获 job 跟踪 ──
async def test_worker_job_tracking_under_milvus_like_backend(worker_and_loop, monkeypatch, tmp_path):
    from db.milvus_client import vector_db

    calls = {"insert": 0, "flush": 0}
    orig_insert = vector_db.insert
    orig_flush = vector_db.flush

    def _insert(coll, chunks, save=True):
        calls["insert"] += 1
        # Milvus：append 不覆盖，忽略 save
        return orig_insert(coll, chunks, save=False)

    def _flush(coll=None):
        calls["flush"] += 1  # Milvus flush 是 no-op（仅记录调用）
        return

    monkeypatch.setattr(vector_db, "insert", _insert)
    monkeypatch.setattr(vector_db, "flush", _flush)

    w, loop = worker_and_loop
    chunks = make_chunks("mil", 5)
    _patch_ingest(w, monkeypatch, chunks, str(tmp_path / "x.pdf"))
    jid = await w.submit("pdf", str(tmp_path / "x.pdf"), {}, "admin")
    job = await _wait(w, jid)

    assert job["status"] == "succeeded", "Milvus 语义下 worker 仍应完成 job 跟踪"
    assert calls["insert"] >= 1 and calls["flush"] >= 1, (
        "worker 写路径仍应调用 insert/flush（与底层 backend 无关）"
    )
    assert _count() == 5


# ── TC-12（ADR §6 risk 6 去重回归）：同源重导不得条目爆炸（Gap B）──
@pytest.mark.xfail(
    reason="Gap B: ADR §6 risk 6 要求 seen_ids 预过滤，但当前 _process_file 未实现；"
    "InMemoryVectorStore.add 不去重 → 重导同内容会重复插入。需 Dev 补 seen_ids 预过滤。",
    strict=False,
)
async def test_reimport_same_source_no_duplicate(worker_and_loop, monkeypatch, tmp_path):
    """重导同一来源（同 id chunks）→ count 不得翻倍。

    ADR §6 明确把「InMemoryVectorStore.add 不去重」列为 risk 6，要求 Worker 做
    seen_ids 预过滤。当前 Dev 实现未做该预过滤 → 重导会重复插入，条目爆炸。
    标记为 xfail 跟踪该已知缺口；Dev 补全 seen_ids 后本用例应转绿。
    """
    w, loop = worker_and_loop
    chunks = make_chunks("dup", 10)
    fp = str(tmp_path / "x.pdf")
    _patch_ingest(w, monkeypatch, chunks, fp)
    await w.submit("pdf", fp, {}, "admin")
    await _wait(w, _last(w))
    base = _count()
    assert base == 10, f"首次导入应有 10 条，实际 {base}"
    # 重导同内容（同 id）
    await w.submit("pdf", fp, {}, "admin")
    await _wait(w, _last(w))
    assert _count() == base, "重导未去重：seen_ids 预过滤缺失 → 条目爆炸（Gap B）"
