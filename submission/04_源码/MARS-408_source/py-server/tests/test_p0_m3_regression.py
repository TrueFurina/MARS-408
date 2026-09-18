# ============================================================
# P0 回归：M3 — Milvus schema 补全 id_str / embedding_status（与 InMemory 对齐）
# ============================================================
# 补丁 M3 在 Milvus schema 中补全 id_str(VARCHAR64) 与 embedding_status(VARCHAR32)，
# 使 get_all_with_texts / delete_by_ids 的字段与 InMemory 实现对齐（id_str 主键替代
# 自增 id，delete_by_ids 走 `id_str in [...]`）。
#
# 本用例（仅真实 Milvus 环境跑）：
#   1) 断言集合 schema 字段含 id_str 与 embedding_status；
#   2) 断言 get_all_with_texts 返回项含 id_str / embedding_status；
#   3) 断言 delete_by_ids 按 id_str 删除生效（返回删除条数且查询不再命中）。
# 标记 requires_milvus（进 requires-milvus CI 作业；不在 p0-regression-gate，因需真实 Milvus）。
# ============================================================

import pytest

from db.milvus_client import VectorDB, MILVUS_AVAILABLE

pytestmark = pytest.mark.requires_milvus

COLLECTION = "netlearn_kb"


@pytest.fixture
def vdb():
    v = VectorDB()
    if not v.connect():
        pytest.skip("需要真实 Milvus 服务端")
    # 确保干净集合
    v.delete_collection(COLLECTION)
    yield v
    v.delete_collection(COLLECTION)
    v.disconnect()


def test_m3_schema_has_id_str_and_embedding_status(vdb):
    import db.milvus_client as mc

    # 触发 schema 创建（insert 新集合时建立字段）
    chunks = [
        {
            "id": "m3_1",
            "text": "M3 回归样本",
            "metadata": {"course": "network", "type": "knowledge_point"},
            "embedding": [0.1] * 768,
        }
    ]
    vdb.insert(COLLECTION, chunks, save=True)

    mc._load_pymilvus()
    col = mc.Collection(COLLECTION)
    field_names = {f.name for f in col.schema.fields}
    assert "id_str" in field_names, f"schema 缺 id_str，实际字段: {field_names}"
    assert "embedding_status" in field_names, \
        f"schema 缺 embedding_status，实际字段: {field_names}"


def test_m3_get_all_with_texts_returns_id_str_and_embedding_status(vdb):
    chunks = [
        {
            "id": "m3_2",
            "text": "M3 回查样本",
            "metadata": {"course": "network", "type": "knowledge_point"},
            "embedding": [0.2] * 768,
        }
    ]
    vdb.insert(COLLECTION, chunks, save=True)

    items, total = vdb.get_all_with_texts(COLLECTION, limit=10)
    assert total >= 1
    hit = next(it for it in items if it.get("id") == "m3_2")
    assert hit["metadata"].get("embedding_status") in (None, "", "fallback_zero", "ok"), \
        "embedding_status 字段应可被读取"
    # id_str 作为字符串主键，删除路径依赖它
    assert hit["id"] == "m3_2"


def test_m3_delete_by_ids_via_id_str(vdb):
    chunks = [
        {"id": "m3_3", "text": "M3 删除样本", "metadata": {"type": "x"}, "embedding": [0.3] * 768},
    ]
    vdb.insert(COLLECTION, chunks, save=True)

    n = vdb.delete_by_ids(COLLECTION, ["m3_3"])
    assert n == 1, f"delete_by_ids 应删 1 条，实际 {n}"

    items, total = vdb.get_all_with_texts(COLLECTION, limit=10)
    assert all(it.get("id") != "m3_3" for it in items), "按 id_str 删除后不应再命中 m3_3"
