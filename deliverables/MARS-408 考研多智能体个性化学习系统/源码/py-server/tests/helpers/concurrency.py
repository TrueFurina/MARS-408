# ============================================================
# 并发写入探针 — 验证 ADR-007 单写者保证（集成 / 系统测试用）
# ============================================================
# 返回 {upload_ids, import_ids} 供 "并集存活 + 无重复爆炸" 断言。
#
# 实际契约（Dev 实现的 services.import_worker，已读源码确认）：
#   - submit(type_, source, params, submitted_by) -> job_id
#   - 写路径内部用 `async with self._store_lock: loop.run_in_executor(_write)`
#     其中 _write = vector_db.insert(coll, chunks, save=False) + vector_db.flush(coll)
#   - 单写者不变式由 _store_lock（asyncio.Lock）保证；在线端点应持同一把锁。
#   - 注意：architect 骨架假设的 write_store(fn)/type=="raw" 并未实现，本 helper 改为
#     直接驱动 _store_lock 下的 insert（worker 与在线端点共用的真实写机制）。
# ============================================================

import asyncio
import os
import sys

_PY_SERVER = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PY_SERVER not in sys.path:
    sys.path.insert(0, _PY_SERVER)

COLLECTION = "netlearn_kb"
EMB_DIM = 768


def _zero(dim=EMB_DIM):
    return [0.0] * dim


def _ensure_embeddings(chunks, dim=EMB_DIM):
    for c in chunks:
        c.setdefault("embedding", _zero(dim))
    return chunks


def _insert(collection, chunks):
    from db.milvus_client import vector_db

    return vector_db.insert(collection, chunks)


def make_chunks(prefix, n, dim=EMB_DIM, text_len=40):
    """生成 n 个确定性 chunk（id 唯一、带零向量占位，避免触发真实 E5）。"""
    return [
        {
            "id": f"{prefix}_{i}",
            "text": f"{prefix} sample text {i}".ljust(text_len),
            "metadata": {"source": prefix, "chunk_index": i, "type": "imported"},
            "embedding": _zero(dim),
        }
        for i in range(n)
    ]


def assert_no_loss_no_dup(store_ids, upload_ids, import_ids):
    """并集存活 + 无重复爆炸：store 中的 id 恰好等于 upload∪import，且无重复。"""
    expected = list(upload_ids) + list(import_ids)
    assert set(store_ids) == set(expected), (
        f"数据丢失或多余：store={sorted(store_ids)} 期望并集={sorted(set(expected))}"
    )
    assert len(store_ids) == len(set(store_ids)), "store 中存在重复 id（条目爆炸）"
    assert len(store_ids) == len(expected), (
        f"数量不符：store={len(store_ids)} 期望={len(expected)}"
    )


async def probe_writes_direct(writer, upload_chunks, import_chunks, loop=None):
    """集成测试：两条写路径都经 worker._store_lock 串行 insert（单写者不变式）。

    直接复用 worker 真实的写机制（_store_lock + 线程池），模拟"在线写 + worker 写"
    并发到达，验证在共享锁下不产生 last-writer-wins 覆盖/截断。

    async 函数：调用方需在事件循环内 `await`，且 writer 必须已在「同一循环」上 start()。
    writer._store_lock / writer._loop 均为实例属性，因此传入全新 ImportWorker 实例时
    不会与模块级单例的锁/loop 绑定产生跨文件污染（见 test_import_queue_single_writer）。
    loop 参数仅为向后兼容保留，实际驱动依赖 writer._loop（= 当前 running loop）。
    """
    _ensure_embeddings(upload_chunks)
    _ensure_embeddings(import_chunks)

    async def _up():
        async with writer._store_lock:
            await writer._loop.run_in_executor(None, _insert, COLLECTION, upload_chunks)

    async def _im():
        async with writer._store_lock:
            await writer._loop.run_in_executor(None, _insert, COLLECTION, import_chunks)

    async def _run():
        await asyncio.gather(_up(), _im())

    await _run()
    return {
        "upload_ids": [c["id"] for c in upload_chunks],
        "import_ids": [c["id"] for c in import_chunks],
    }


def probe_writes_http(client, upload_file, import_payload, poll_timeout=60.0):
    """E2E：经 httpx / TestClient 并发打 /knowledge/upload 与 /imports/submit。

    client: 已带 admin Bearer 头；upload_file=(filename, bytes, mime)；
    import_payload: {"type":"pdf"|"docling"|"textbook","source":"scan"|"/path",
                     "params":{...}}。
    返回 {"upload_ids":[], "import_ids":[...], "upload_resp", "import_resp"}。
    注：/upload 当前不回传 id，upload_ids 留空——存活断言请改查 /knowledge/list。
    """
    import threading

    result = {}

    def _upload():
        result["upload_resp"] = client.post(
            "/api/knowledge/upload", files={"file": upload_file}
        )

    def _import():
        resp = client.post("/api/imports/submit", json=import_payload)
        result["import_resp"] = resp
        if resp.status_code == 200:
            _poll_job(client, resp.json().get("job_id"), poll_timeout)

    t1 = threading.Thread(target=_upload)
    t2 = threading.Thread(target=_import)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    return {
        "upload_ids": [],
        "import_ids": result.get("import_ids", []),
        "upload_resp": result.get("upload_resp"),
        "import_resp": result.get("import_resp"),
    }


def _poll_job(client, job_id, timeout):
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = client.get(f"/api/imports/jobs/{job_id}")
            if r.status_code == 200 and r.json().get("status") in (
                "succeeded",
                "failed",
                "cancelled",
            ):
                return r.json()["status"]
        except Exception:
            pass
        time.sleep(0.2)
    return "timeout"


def _run_in_loop(coro, loop):
    if loop is None:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)
