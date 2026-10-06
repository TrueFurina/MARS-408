# ============================================================
# P0 回归：F1 — _clear_imported_type 真实删除旧 type（不误删其他）
# ============================================================
# 补丁 F1 将 _clear_imported_type 从 get_all_metadata（两种实现均无 id 字段 →
# 静默 no-op）改为 get_all_with_texts（返回 id+metadata，分页遍历真删）。
#
# 本用例用【真实 InMemoryVectorStore】（非 fake）断言：
#   - 混合 type 入库后，rebuild 清 "docling" 仅删 docling 类；
#   - imported / knowledge_point 等其他类保留（不误删）。
# 复用 conftest 的 isolate_vectordb（强制 InMemory 回退 + 落盘重定向 tmp）。
# 标记 import_queue + p0_regression（进 fast-unit 与 p0-regression-gate）。
# ============================================================

import asyncio
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

pytestmark = [pytest.mark.import_queue, pytest.mark.p0_regression]

COLLECTION = "netlearn_kb"


@pytest.fixture
def real_store(isolate_vectordb, monkeypatch, tmp_path):
    """用真实 InMemoryVectorStore 替换两处 vector_db 引用（对齐 F1 真实路径）。"""
    import db.milvus_client as mc
    import services.import_worker as iw_mod
    from db.milvus_client import InMemoryVectorStore

    store = InMemoryVectorStore(persist_path=str(tmp_path))
    monkeypatch.setattr(mc, "vector_db", store)
    monkeypatch.setattr(iw_mod, "vector_db", store)
    yield store


async def test_f1_clear_imported_type_truly_deletes_only_target_type(
    real_store, tmp_path
):
    dim = 8

    def _add(tid, ttype):
        real_store.add(
            COLLECTION,
            [tid],
            [f"text-{tid}"],
            [{"type": ttype, "source": "x", "course": "net"}],
            [np.zeros(dim).tolist()],
        )

    _add("doc1", "docling")
    _add("doc2", "docling")
    _add("imp1", "imported")
    _add("kp1", "knowledge_point")
    assert real_store.count(COLLECTION) == 4

    from services.import_worker import ImportWorker

    w = ImportWorker()
    w._loop = asyncio.get_running_loop()
    w._executor = ThreadPoolExecutor(max_workers=1)
    # rebuild 清 docling：应真删 doc1/doc2，保留 imp1/kp1
    await w._clear_imported_type("docling")

    items, total = real_store.get_all_with_texts(COLLECTION, limit=100)
    types = {it["metadata"]["type"] for it in items}
    assert total == 2, f"rebuild 后应为 2 条，实际 {total}"
    assert types == {"imported", "knowledge_point"}, f"残留类型异常: {types}"
    # 显式确认 docling 类已被删除（不误删、不残留）
    assert all(it["metadata"]["type"] != "docling" for it in items)


async def test_f1_clear_imported_type_keeps_others_when_clearing_imported(
    real_store, tmp_path
):
    dim = 8

    def _add(tid, ttype):
        real_store.add(
            COLLECTION,
            [tid],
            [f"text-{tid}"],
            [{"type": ttype, "source": "x"}],
            [np.zeros(dim).tolist()],
        )

    _add("doc1", "docling")
    _add("imp1", "imported")
    _add("imp2", "imported")

    from services.import_worker import ImportWorker

    w = ImportWorker()
    w._loop = asyncio.get_running_loop()
    w._executor = ThreadPoolExecutor(max_workers=1)
    # 清 imported：删 imp1/imp2，保留 doc1
    await w._clear_imported_type("imported")

    items, total = real_store.get_all_with_texts(COLLECTION, limit=100)
    assert total == 1, f"应仅剩 1 条 docling，实际 {total}"
    assert items[0]["metadata"]["type"] == "docling"
