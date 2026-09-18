# ============================================================
# P0 回归：F20 — docling 导入链路符号修正（无 ImportError + 端到端入库）
# ============================================================
# 补丁 F20 将 docling 分支的符号导入从
#   `from import_docling import semantic_chunk, detect_subject`  (二者不在 import_docling → ImportError)
# 修正为
#   `from import_docling import convert_with_docling`
#   `from import_pdfs import semantic_chunk, detect_subject`     (二者定义在 import_pdfs)
#
# 本用例：
#   1) 真实 `from import_pdfs import semantic_chunk, detect_subject` 必须成功（捕获符号回归）；
#   2) 跑通 import_worker._process_file 的 docling 分支（convert_with_docling 用 mock 规避
#      重 docling 原生库，semantic_chunk/detect_subject 用 import_pdfs 真实符号）；
#   3) 断言端到端入库 netlearn_kb 且按 type=docling 回查命中。
# 本地+CI 可跑（不触真实 docling/torch 原生库）。
# 标记 import_queue + p0_regression。
# ============================================================

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

pytestmark = [pytest.mark.import_queue, pytest.mark.p0_regression]

COLLECTION = "netlearn_kb"


async def test_f20_docling_chain_no_import_error_and_ingests(
    isolate_vectordb, fake_embedder, monkeypatch, tmp_path
):
    # 1) F20 核心回归：这两个符号现在必须存在于 import_pdfs（旧实现从 import_docling 导入会 ImportError）
    from import_docling import convert_with_docling  # noqa: F401 必须可导入
    from import_pdfs import semantic_chunk, detect_subject  # noqa: F401 必须可导入

    # 2) mock 重 docling 原生转换器，但保留真实 semantic_chunk/detect_subject 符号链
    monkeypatch.setattr(
        __import__("import_docling"), "convert_with_docling",
        lambda pdf_path, max_pages=100: "docling 解析出的示例文本",
    )
    monkeypatch.setattr(
        __import__("import_pdfs"), "semantic_chunk",
        lambda text, max_chars=600: [f"{text[:5]}-chunk-{i}" for i in range(2)],
    )
    monkeypatch.setattr(
        __import__("import_pdfs"), "detect_subject",
        lambda fp: "network",
    )

    import db.milvus_client as mc
    import services.import_worker as iw_mod
    from db.milvus_client import InMemoryVectorStore, vector_db

    # 用真实 InMemoryVectorStore 作底层存储，但保留 VectorDB 包装（生产路径即走
    # vector_db.insert/delete_by_ids）。强制 InMemory 回退 + 落盘重定向 tmp。
    store = InMemoryVectorStore(persist_path=str(tmp_path))
    monkeypatch.setattr(mc, "MILVUS_AVAILABLE", False)
    monkeypatch.setattr(vector_db, "_milvus_connected", False)
    monkeypatch.setattr(vector_db, "_mem_store", store)

    from services.import_worker import ImportWorker

    w = ImportWorker()
    w._loop = asyncio.get_running_loop()
    w._executor = ThreadPoolExecutor(max_workers=1)

    # 3) 跑 docling 分支（type="docling"）；不应抛 ImportError，且返回 >0 条
    n = await w._process_file(Path("fake_scanned.pdf"), {"type": "docling", "params": {}})
    assert n and n > 0, f"docling 分支应入库 >0 条，实际 {n}"

    # 端到端回查：按 type=docling 能命中刚入库的 chunk
    items, total = store.get_all_with_texts(COLLECTION, limit=100)
    assert total == n, f"入库 {n} 条但回查到 {total} 条"
    assert any(it["metadata"].get("type") == "docling" for it in items), \
        "未能按 type=docling 回查到入库 chunk（F20 端到端失败）"
