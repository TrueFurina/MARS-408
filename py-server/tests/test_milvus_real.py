# B5：真实 Milvus 集成测试（D14 闭环）。
# 使用真实类 VectorDB（非 MilvusClient），仅被 `requires_milvus` 标记收集，
# 由 ci.yml 的 backend-milvus 作业配合真实 Milvus 服务端运行。
import pytest
from db.milvus_client import VectorDB

pytestmark = pytest.mark.requires_milvus


@pytest.fixture
def vdb():
    v = VectorDB()
    if not v.connect():
        pytest.skip("需要真实 Milvus 服务端")
    yield v
    v.disconnect()


def test_milvus_insert_search_roundtrip(vdb):
    import uuid

    coll = f"test_roundtrip_{uuid.uuid4().hex[:8]}"
    chunks = [{"id": "u1", "text": "二叉树遍历", "metadata": {"course": "data_structures"}, "embedding": [0.1] * 768}]
    vdb.insert(coll, chunks)
    try:
        hits = vdb.search(coll, query_vector=[0.1] * 768, top_k=1)
        assert hits and hits[0]["metadata"].get("course") == "data_structures"
    finally:
        try:
            vdb.delete_collection(coll)
        except Exception:
            pass


def test_milvus_search_large_topk_returns_id_str(vdb):
    """回归（2026-10-16 生产 500 双 bug）：

    1. ef 约束：FrugalRAG 全局检索把候选池拉到 top_k=800（course_search_top_k
       默认 800 喂 cross-encoder 重排）。HNSW 硬性要求 ef > k，原 _milvus_search
       写死 ef=128 → MilvusException "ef(128) should be larger than k(800)" → 整条
       RAG 检索 500。修复后 ef 随 top_k 动态抬升，大 top_k 检索应正常返回。
    2. id_str 出参：Milvus 主键 id 是 INT64 auto_id（无意义自增整数），逻辑 id 在
       id_str VARCHAR(64)。原代码回 hit.id（int）→ 与 RAGSearchResult.id: str 冲突
       → pydantic ValidationError 500。修复后必须回 str 类型的逻辑 id_str。

    使用隔离集合，不污染生产 netlearn_kb。
    """
    import uuid

    coll = f"test_rag_reg_{uuid.uuid4().hex[:8]}"
    chunks = [
        {
            "id": f"reg_{i}",
            "text": f"回归测试片段 {i}",
            "metadata": {"course": "regression"},
            "embedding": [0.1 + i * 0.001] * 768,
        }
        for i in range(5)
    ]
    vdb.insert(coll, chunks)
    try:
        # top_k=800 触发原 ef 约束 bug；若仍写死 ef=128 此处会抛 MilvusException
        hits = vdb.search(coll, query_vector=[0.1] * 768, top_k=800)
        assert hits, "大 top_k 检索应返回结果（修复 ef 约束后）"
        # id_str 出参：逻辑 id 必须是 str 且等于插入时的逻辑 id，而非 int PK
        assert isinstance(hits[0]["id"], str), (
            f"RAGSearchResult.id 必须是 str，修复前返回 int PK，实际={hits[0]['id']!r}"
        )
        assert hits[0]["id"].startswith("reg_"), (
            f"id 应为逻辑 id_str，实际={hits[0]['id']!r}"
        )
    finally:
        try:
            vdb.delete_collection(coll)
        except Exception:
            pass
