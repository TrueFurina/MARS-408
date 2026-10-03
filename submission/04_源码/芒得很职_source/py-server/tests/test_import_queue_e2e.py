# ============================================================
# E2E 测试：导入队列（ADR-007）—— 经 FastAPI TestClient 全链路 + 单写者共享锁（§6.3）
# ============================================================
# 经 TestClient(app) 全链路；lifespan 拉起 import_worker 消费者（真实 _consume 驱动）。
# 用 monkeypatch 注入受控 chunks + 确定性嵌入 + FakeVectorDB 桩，避免重依赖
# （torch / 真实 E5 / 真实 Milvus / 真实 PDF 解析）。
# auth 由 conftest mock_auth 自动覆盖为 admin（无需手动登录）。
# 标记：@pytest.mark.import_queue
# ============================================================

import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("services.import_worker")
pytest.importorskip("api.imports")

import db.embedder as eb  # monkeypatch embed_batch / embed_text
import db.milvus_client as mc  # patch vector_db
import import_pdfs  # monkeypatch process_file
import services.import_worker as iw_mod  # patch vector_db

pytestmark = pytest.mark.import_queue

COLLECTION = "netlearn_kb"


class FakeVectorDB:
    """内存桩：记录 insert 调用并保存 chunks（与集成测试同款，供 E2E 全链路断言）。"""

    def __init__(self):
        self.insert_calls = []
        self._store = {}

    def insert(self, collection_name, chunks, save=True):
        self.insert_calls.append((collection_name, list(chunks), save))
        for c in chunks:
            self._store[c["id"]] = c
        return len(chunks)

    def flush(self, collection_name=None):
        return

    def get_all_metadata(self, collection_name, filter_dict=None):
        return [
            {"id": c["id"], "metadata": c.get("metadata", {})}
            for c in self._store.values()
        ]

    def delete_by_ids(self, collection_name, ids):
        for i in ids:
            self._store.pop(i, None)
        return len(ids)

    def count(self, collection_name=None):
        return len(self._store)

    def chunks(self):
        return list(self._store.values())


@pytest.fixture
def fake_vector_db(monkeypatch):
    """用 FakeVectorDB 替换 import_worker 与 milvus_client 两处对 vector_db 的引用。"""
    fake = FakeVectorDB()
    monkeypatch.setattr(iw_mod, "vector_db", fake)
    monkeypatch.setattr(mc, "vector_db", fake)
    yield fake


@pytest.fixture
def client(fake_vector_db, isolate_vectordb, monkeypatch):
    """TestClient(app)（触发 lifespan 拉起 import_worker 消费者）。

    isolate_vectordb 把 journal 落盘重定向到 tmp 并强制 InMemory 回退；
    fake_vector_db 注入内存桩。import main 放在 fixture 内，便于同文件其它轻量测试
    不触发重依赖模块加载。
    """
    # 强制启用 Worker：config.json 可能 import_worker.enabled=false（本地关闭导入队列），
    # 但 E2E 需要 lifespan 真实拉起消费者，monkeypatch load_config 使 start() 进入启用分支。
    monkeypatch.setattr(iw_mod, "load_config", lambda: {"import_worker": {"enabled": True}})

    from main import app

    with TestClient(app) as c:
        # lifespan 已拉起 import_worker；再次确认 fake store 生效（覆盖 import 时绑定）
        monkeypatch.setattr(iw_mod, "vector_db", fake_vector_db)
        monkeypatch.setattr(mc, "vector_db", fake_vector_db)
        yield c


def _poll(client, jid, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/imports/jobs/{jid}")
        if r.status_code == 200 and r.json().get("status") in (
            "succeeded",
            "failed",
            "cancelled",
        ):
            return r.json()
        time.sleep(0.05)
    return None


# ────────────────────────────────────────────────────────────
# TC-E2E：submit -> 全链路跑通（真实 _consume 消费者）-> 入库 + job succeeded
# ────────────────────────────────────────────────────────────
def test_e2e_submit_poll_until_succeeded_and_chunks_inserted(
    client, fake_vector_db, monkeypatch, tmp_path
):
    chunks = [
        {
            "id": f"e2e_{i}",
            "text": f"e2e chunk {i}",
            "metadata": {"source": "fixture", "type": "imported", "chunk_index": i},
        }
        for i in range(3)
    ]
    # 解析 / 嵌入：受控桩，避免重依赖
    monkeypatch.setattr(import_pdfs, "process_file", lambda *a, **k: chunks)
    monkeypatch.setattr(eb, "embed_batch", lambda texts: [[0.0] * 768 for _ in texts])
    monkeypatch.setattr(eb, "embed_text", lambda t: [0.0] * 768)

    # 将 DOCS_DIR 重定向到受控 tmp_path（与单测约定一致），使 fixture 源路径
    # 落在允许目录内，能被 S1 护栏正常接受。
    monkeypatch.setattr(iw_mod, "DOCS_DIR", tmp_path)

    src = tmp_path / "e2e_fixture.pdf"
    src.write_text("dummy")

    r = client.post(
        "/api/imports/submit",
        json={"type": "pdf", "source": str(src), "params": {}},
    )
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]

    job = _poll(client, jid)
    assert job is not None, "job 轮询超时（未到达终态）"
    assert job["status"] == "succeeded", f"job 终态非 succeeded: {job}"

    # 经 fake vector_db 确认 chunks 入库（单写者写路径确实命中向量库）
    assert fake_vector_db.count() == 3, (
        f"fake store 入库数不符: {fake_vector_db.count()}"
    )
    assert {c["id"] for c in fake_vector_db.chunks()} == {
        f"e2e_{i}" for i in range(3)
    }


# ────────────────────────────────────────────────────────────
# TC-6.3：单写者共享锁 —— api.knowledge 与 import_worker 引用同一把锁（遗留对比）
# ────────────────────────────────────────────────────────────
def test_single_writer_shared_lock_between_knowledge_and_worker():
    """遗留对比（ADR §6.3）：在线写端点（api.knowledge）必须引用 import_worker 的
    同一把 store_lock 对象，否则单写者保证被打破（跨路径 last-writer-wins）。

    这是 ADR-007 的 single-writer 保证的根基：knowledge.py 通过
    import_worker.store_lock 引用，必须与 Worker 自身持有的锁是【同一对象】。
    """
    from services.import_worker import import_worker
    import api.knowledge as k

    assert k.import_worker is import_worker, (
        "api.knowledge 未引用同一个 import_worker 单例"
    )
    assert k.import_worker.store_lock is import_worker.store_lock, (
        "api.knowledge 与 import_worker 的 store_lock 不是同一对象（单写者保证被破坏）"
    )
    assert isinstance(import_worker.store_lock, asyncio.Lock)
