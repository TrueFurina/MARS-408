# B5：真实 Milvus 集成测试（D14 闭环）。
# 使用真实类 VectorDB（非 MilvusClient），仅被 `requires_milvus` 标记收集，
# 由 ci.yml 的 backend-milvus 作业配合真实 Milvus 服务端运行。
import pytest
from db.milvus_client import VectorDB, MILVUS_AVAILABLE

pytestmark = pytest.mark.requires_milvus


@pytest.fixture
def vdb():
    v = VectorDB()
    if not v.connect():
        pytest.skip("需要真实 Milvus 服务端")
    yield v
    v.disconnect()


def test_milvus_insert_search_roundtrip(vdb):
    chunks = [{"id": "u1", "text": "二叉树遍历", "metadata": {"course": "data_structures"}, "embedding": [0.1] * 768}]
    vdb.insert("netlearn_kb", chunks)
    hits = vdb.search("netlearn_kb", query_vector=[0.1] * 768, top_k=1)
    assert hits and hits[0]["metadata"].get("course") == "data_structures"
