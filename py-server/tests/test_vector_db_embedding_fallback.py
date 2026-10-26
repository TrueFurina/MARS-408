# -*- coding: utf-8 -*-
"""向量入库的 E5 兜底 —— 两条写入路径必须共用同一实现（2026-10-18）

## 为什么要有这组测试

`/api/status` 的 `fallback_zero_docs` 曾长期恒报 0（公开/私有属性名不一致，
已在 `test_app_status_invariants.py` 里锁住）。修完那一层之后，往下追一层才
发现更严重的问题：

- `_mem_insert`（InMemory 路径）会尝试 E5，失败则零向量占位 + 打
  `embedding_status="fallback_zero"` + 计数。
- `_milvus_insert`（Milvus 路径）**什么都不做** —— 直接
  `c.get("embedding", [0.0] * dim)`，既不调 E5、也不打标记、也不计数。

而检索侧只排除 `embedding_status != "fallback_zero"`（见 `VectorDB.search`
与 `_mem_search`）。于是 Milvus 路径下「没算过嵌入的文档」会以零向量混进
候选集，cosine 相似度恒为 0、排名无意义，**且不报任何错**。

触发条件不是理论上的：`app/lifespan.py::_seed_vector_db` 与
`rebuild_vectordb.py` 都不预计算 embedding，只要「Milvus 已连接且集合为空」
（首次部署、换库、清库后重启）就会走这条路径把 2245 条种子写成零向量。

## 本文件锁什么

1. `_resolve_embeddings` 的三种输入形态（全缺 / 部分缺 / 全有）语义正确；
2. E5 返回条数少于 chunk 数时不得 IndexError（降级为占位）；
3. `_milvus_insert` 真的把零向量与 `fallback_zero` 标记写进 entities 列；
4. **结构守卫**：两条路径都必须调用 `_resolve_embeddings`，谁再自造一份
   零向量兜底就红 —— 这是防「同一个洞修一处、另一处再长出来」的关键。
5. **持久化不落盘已知坏数据**（2026-10-22 新增）：``fallback_zero`` 文档不得写进
   ``netlearn_kb.json`` / ``.emb.npy``。否则第二次启动会「命中二进制缓存、跳过
   JSON 重建」，而 fallback 计数器只统计**本次新插入**、读回不计 ⇒
   ``/api/status`` 重启后低报 ``fallback_zero_docs:0`` / ``status:"ok"``，
   库里却全是零向量 —— **首次启动诚实、重启后说谎**。
6. **读取侧同样过滤**（2026-10-22 新增）：写侧只防未来，治不了**已被旧版本污染**
   的目录。``_load_unlocked`` 读到全零向量库时须返回 ``False``（调用方据此重新
   播种、重新计数），读到混合库时须保住真向量、丢掉零向量 —— 且过滤先于
   ``.emb.npy`` 行数比对，否则「缓存与 JSON 打架」。
"""

import pytest

import db.milvus_client as mc
from config import get_embedding_config


@pytest.fixture()
def dim() -> int:
    return int(get_embedding_config().get("dimension", 768))


@pytest.fixture()
def vdb(monkeypatch):
    """拿单例并把回落计数归零（用例结束后由 monkeypatch 还原）。"""
    from db.milvus_client import vector_db

    monkeypatch.setattr(vector_db, "_embedding_fallback_count", 0)
    return vector_db


@pytest.fixture()
def e5_down(monkeypatch, dim):
    """让 E5 必定失败，模拟瘦包/未装 sentence-transformers 的环境。"""

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated E5 outage")

    import db.embedder as embedder_mod

    monkeypatch.setattr(embedder_mod, "embed_batch", _boom)
    return _boom


# ── 1. _resolve_embeddings 的三种输入形态 ─────────────────────────────────


def test_all_missing_embeddings_fall_back_and_count(vdb, e5_down, dim):
    """整批都没有 embedding 且 E5 挂了 ⇒ 全部零向量 + 全部打标 + 计数 == n。"""
    chunks = [{"id": f"c{i}", "text": f"t{i}", "metadata": {}} for i in range(3)]

    resolved = vdb._resolve_embeddings(chunks, dim)

    assert len(resolved) == 3
    assert all(v == [0.0] * dim for v in resolved), "兜底必须是零向量而非随机向量"
    assert all(c["metadata"]["embedding_status"] == "fallback_zero" for c in chunks)
    assert vdb.embedding_fallback_count == 3


def test_partial_precomputed_only_none_is_marked_and_counted(vdb, e5_down, dim):
    """批量里个别 embedding 为 None ⇒ 只兜底那一条，不整批重算、不误伤好向量。"""
    good = [0.5] * dim
    chunks = [
        {"id": "a", "text": "ta", "metadata": {}, "embedding": good},
        {"id": "b", "text": "tb", "metadata": {}, "embedding": None},
        {"id": "c", "text": "tc", "metadata": {}, "embedding": good},
    ]

    resolved = vdb._resolve_embeddings(chunks, dim)

    assert resolved[0] == good and resolved[2] == good, "已有真向量的条目不得被覆盖"
    assert resolved[1] == [0.0] * dim
    assert "embedding_status" not in chunks[0]["metadata"]
    assert chunks[1]["metadata"]["embedding_status"] == "fallback_zero"
    assert vdb.embedding_fallback_count == 1, "只该给真正兜底的那一条计数"


def test_all_precomputed_never_calls_e5(vdb, monkeypatch, dim):
    """全部自带 embedding ⇒ 一次都不该调 E5（否则等于把已算好的向量白扔）。"""
    import db.embedder as embedder_mod

    calls = []

    def _spy(texts, prefix=None):
        calls.append({"n": len(texts), "prefix": prefix})
        return [[0.1] * dim for _ in texts]

    monkeypatch.setattr(embedder_mod, "embed_batch", _spy)
    chunks = [
        {"id": "a", "text": "ta", "metadata": {}, "embedding": [0.2] * dim},
        {"id": "b", "text": "tb", "metadata": {}, "embedding": [0.3] * dim},
    ]

    resolved = vdb._resolve_embeddings(chunks, dim)

    assert calls == [], f"不应调用 E5，实测调用 {calls}"
    assert resolved == [[0.2] * dim, [0.3] * dim]
    assert vdb.embedding_fallback_count == 0


def test_short_e5_result_degrades_instead_of_raising(vdb, monkeypatch, dim):
    """embed_batch 少返几条时必须降级为占位，不能 IndexError 打断整批入库。

    真实场景：E5 批处理内部对超长文本做了截断/跳过，返回长度 < 输入长度。
    """
    import db.embedder as embedder_mod

    monkeypatch.setattr(
        embedder_mod, "embed_batch", lambda texts, prefix=None: [[0.4] * dim]
    )
    chunks = [
        {"id": "a", "text": "ta", "metadata": {}},
        {"id": "b", "text": "tb", "metadata": {}},
    ]

    resolved = vdb._resolve_embeddings(chunks, dim)  # 不得抛

    assert resolved[0] == [0.4] * dim
    assert resolved[1] == [0.0] * dim, "缺位应降级为零向量占位"
    assert chunks[1]["metadata"]["embedding_status"] == "fallback_zero"
    assert vdb.embedding_fallback_count == 1


def test_metadata_missing_or_not_dict_is_repaired(vdb, e5_down, dim):
    """metadata 缺失或不是 dict 时，兜底不能因写入标记而抛错。"""
    chunks = [
        {"id": "a", "text": "ta"},
        {"id": "b", "text": "tb", "metadata": None},
    ]

    resolved = vdb._resolve_embeddings(chunks, dim)

    assert resolved == [[0.0] * dim, [0.0] * dim]
    assert chunks[0]["metadata"]["embedding_status"] == "fallback_zero"
    assert chunks[1]["metadata"]["embedding_status"] == "fallback_zero"


# ── 2. Milvus 路径：零向量与标记必须真的进 entities ──────────────────────


class _FakeCollection:
    """替身：只记录 insert 收到的列式 entities。"""

    last: "_FakeCollection | None" = None

    def __init__(self, name):
        self.name = name
        self.inserted = None
        _FakeCollection.last = self

    def load(self):
        pass

    def insert(self, entities):
        self.inserted = entities

    def flush(self):
        pass


class _FakeUtility:
    @staticmethod
    def has_collection(name):
        return True  # 走「已存在集合」分支，避开 schema 创建


def _patch_pymilvus(monkeypatch):
    """把模块级 pymilvus 全局换成替身。

    关键点：先把 ``connections`` 置为非 None，``_load_pymilvus()`` 才会因为
    ``if connections is None`` 不成立而直接返回 —— 本机无需安装/启动 Milvus。
    """
    monkeypatch.setattr(mc, "connections", object())
    monkeypatch.setattr(mc, "utility", _FakeUtility())
    monkeypatch.setattr(mc, "Collection", _FakeCollection)


def test_milvus_insert_writes_zero_vectors_and_fallback_marker(
    vdb, e5_down, monkeypatch, dim
):
    """Milvus 路径在 E5 不可用时，必须写入零向量 **且** 打上 fallback_zero。

    打分：entities 的第 2 列是 embedding，最后一列是 embedding_status。
    修复前这里会拿到 ``[0.0] * dim``（因为 get 的默认值）但 status 为空串 ——
    检索侧只排除 ``!= "fallback_zero"``，于是这些零向量会正常参与排序。
    """
    _patch_pymilvus(monkeypatch)
    chunks = [
        {"id": "c0", "text": "t0", "metadata": {"subject": "os"}},
        {"id": "c1", "text": "t1", "metadata": {"subject": "net"}},
    ]

    n = vdb._milvus_insert("netlearn_kb", chunks)

    assert n == 2
    col = _FakeCollection.last
    assert col is not None and col.inserted is not None

    embeddings_col = col.inserted[1]
    status_col = col.inserted[-1]
    assert embeddings_col == [[0.0] * dim, [0.0] * dim]
    assert status_col == ["fallback_zero", "fallback_zero"], (
        f"零向量必须带 fallback_zero 标记，否则会被检索当成正常向量；实测 {status_col}"
    )
    assert vdb.embedding_fallback_count == 2


def test_milvus_insert_keeps_precomputed_embeddings(vdb, monkeypatch, dim):
    """Milvus 路径下已预计算的向量必须原样入库，且不被打上 fallback 标记。"""
    _patch_pymilvus(monkeypatch)
    good = [0.7] * dim
    chunks = [{"id": "c0", "text": "t0", "metadata": {}, "embedding": good}]

    vdb._milvus_insert("netlearn_kb", chunks)

    col = _FakeCollection.last
    assert col.inserted[1] == [good]
    assert col.inserted[-1] == [""], "真向量不得被标记为 fallback_zero"
    assert vdb.embedding_fallback_count == 0


# ── 3. 结构守卫：禁止任何路径再自造一份零向量兜底 ─────────────────────────


def test_both_insert_paths_share_the_single_resolution():
    """两条写入路径都必须调用 _resolve_embeddings，谁也不许自造兜底。

    这条守卫针对的正是本次缺陷的成因：兜底逻辑在两条路径各写一份，
    修了一条另一条还在。源码级断言比行为测试更能拦住「再抄一份」。

    只看**代码行**、跳过整行注释：修复说明里必然会引用旧写法
    （`c.get("embedding", [0.0] * dim)`），按原文比对会被自己的注释绊倒。
    """
    import inspect

    from db.milvus_client import VectorDB

    def _code_only(src: str) -> str:
        return "\n".join(
            ln for ln in src.splitlines() if not ln.lstrip().startswith("#")
        )

    mem_src = _code_only(inspect.getsource(VectorDB._mem_insert))
    milvus_src = _code_only(inspect.getsource(VectorDB._milvus_insert))

    assert "_resolve_embeddings" in mem_src, "_mem_insert 未走统一向量解析"
    assert "_resolve_embeddings" in milvus_src, "_milvus_insert 未走统一向量解析"
    assert "[0.0] * dim" not in milvus_src, (
        "_milvus_insert 又在自己造零向量兜底 —— 请改为调用 _resolve_embeddings，"
        "否则零向量不会带 fallback_zero 标记，检索侧不会排除它"
    )
    assert "[0.0] * dim" not in mem_src, "_mem_insert 又在自己造零向量兜底"


def test_resolution_is_the_only_fallback_counter_owner():
    """embedding_fallback_count 的自增只允许出现在 _resolve_embeddings 里。"""
    import inspect

    from db.milvus_client import VectorDB

    resolver_src = inspect.getsource(VectorDB._resolve_embeddings)
    assert "_embedding_fallback_count += 1" in resolver_src

    for name in ("_mem_insert", "_milvus_insert"):
        src = inspect.getsource(getattr(VectorDB, name))
        assert "_embedding_fallback_count += 1" not in src, (
            f"{name} 里又有独立计数 —— 计数口径必须收敛到 _resolve_embeddings"
        )


# ── 4. 持久化不得落盘已知坏数据（fallback_zero 不落盘）────────────────────


def test_persist_skips_fallback_zero_documents(isolate_vectordb, dim):
    """持久化必须跳过 ``embedding_status == "fallback_zero"`` 的文档。

    2026-10-22 实证（career-only 瘦包，双启动）：E5 不可用时 2245 条种子全部以
    零向量占位入库，**并照常落盘** ``netlearn_kb.json`` + ``.emb.npy``。第二次
    启动于是命中「二进制缓存 2245 条、跳过 JSON 重建」——而 fallback 计数器只
    统计**本次新插入**，读回不计 ⇒ ``/api/status`` 报 ``fallback_zero_docs:0`` /
    ``status:"ok"``，库里 2245 条却仍全是零向量。**首次启动诚实、重启后低报**，
    这是「绿灯说谎」，与 2026-10-18 的 ``881e0be``（探针不得掩盖降级）同 spirit。

    修法（Y·不落盘已知坏数据）：持久化时按 ``embedding_status`` 过滤，且
    ``netlearn_kb.json`` 与 ``.emb.npy`` **一致处理**。真嵌入（408 主部署）
    非零即落盘、行为不变；career-only 包因此什么都不落 ⇒ 每次启动重新播种
    ⇒ 探针每次诚实报 2245/degraded。
    """
    import json
    import pathlib

    import numpy as np

    from db.milvus_client import InMemoryVectorStore

    store = InMemoryVectorStore()
    good = [0.5] * dim
    store.add(
        "netlearn_kb",
        ids=["ok", "bad"],
        texts=["good text", "bad text"],
        metas=[
            {"subject": "os"},
            {"subject": "net", "embedding_status": "fallback_zero"},
        ],
        embeddings=[good, [0.0] * dim],
    )

    json_path = pathlib.Path(store._persist_path) / "netlearn_kb.json"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["ids"] == ["ok"], (
        f"fallback_zero 文档不得落盘，实测落盘 ids={payload['ids']}"
    )
    assert payload["metas"] == [{"subject": "os"}]
    assert payload["embeddings"] == [good], "真向量必须原样落盘"

    # .emb.npy 必须与 JSON 一致：同样只剩 1 行（否则读回时维度校验失配、
    # 二进制缓存与 JSON 打架）
    arr = np.load(json_path.with_name(json_path.name + ".emb.npy"))
    assert arr.shape == (1, dim), f".emb.npy 与 JSON 不一致，实测 shape={arr.shape}"


def test_all_fallback_zero_persists_nothing_and_second_boot_recounts(
    isolate_vectordb, monkeypatch, e5_down, dim
):
    """双启动：全部零向量时什么都不落，第二次启动必须重新播种、重新计数。

    集成级断言。上一条只证明「落盘内容不含坏数据」这 half；这里把两次启动串起来，
    证明运维面（``/api/status`` 的 ``fallback_zero_docs``）在**每次**启动都反映
    事实，而不是只有第一次。
    """
    import pathlib

    from db.milvus_client import InMemoryVectorStore, vector_db

    chunks = [{"id": f"c{i}", "text": f"t{i}", "metadata": {}} for i in range(3)]

    # ── boot 1：E5 挂了 ⇒ 3 条全零向量占位 ──
    monkeypatch.setattr(vector_db, "_milvus_connected", False)
    monkeypatch.setattr(vector_db, "_mem_store", InMemoryVectorStore())
    monkeypatch.setattr(vector_db, "_embedding_fallback_count", 0)

    assert vector_db._mem_insert("netlearn_kb", chunks) == 3
    assert vector_db.embedding_fallback_count == 3, "首次启动必须计入零向量"

    persist_dir = pathlib.Path(vector_db._mem_store._persist_path)
    assert not (persist_dir / "netlearn_kb.json").exists(), (
        "全部为零向量时不得落盘 —— 否则下次启动'跳过 JSON 重建'，计数器不增，"
        "健康探针会把 2245 条零向量库报成 ok"
    )

    # ── boot 2：全新实例、同一磁盘目录（等价于进程重启）──
    boot2 = InMemoryVectorStore()
    assert boot2._load("netlearn_kb") is False, "第二次启动不应读到上次的零向量库"
    assert boot2.count("netlearn_kb") == 0

    monkeypatch.setattr(vector_db, "_mem_store", boot2)
    monkeypatch.setattr(vector_db, "_embedding_fallback_count", 0)
    assert vector_db._mem_insert("netlearn_kb", chunks) == 3
    assert vector_db.embedding_fallback_count == 3, (
        "第二次启动必须重新计入零向量 —— 否则 /api/status 重启后低报成 ok"
    )


# ── 5. 读取侧过滤：已被旧版本污染的目录必须重启即自愈 ────────────────────


def _write_polluted_store(persist_dir, dim, n: int, good_first: bool = False):
    """手工造一份「旧版本留下的」污染库：n 条文档 + 行数匹配的 .emb.npy。

    模拟的是**写侧过滤上线之前**已经落盘的目录（线上实例 / 跑过旧包的副本），
    这是写侧过滤永远治不到的那一半病例。
    """
    import json
    import pathlib

    import numpy as np

    persist_dir = pathlib.Path(persist_dir)
    ids = [f"c{i}" for i in range(n)]
    texts = [f"t{i}" for i in range(n)]
    metas = [{"subject": "os", "embedding_status": "fallback_zero"} for _ in range(n)]
    embs = [[0.0] * dim for _ in range(n)]
    if good_first:
        ids[0] = "ok"
        texts[0] = "good text"
        metas[0] = {"subject": "os"}
        embs[0] = [0.5] * dim
    payload = {"ids": ids, "texts": texts, "metas": metas, "embeddings": embs}
    (persist_dir / "netlearn_kb.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    np.save(
        persist_dir / "netlearn_kb.json.emb.npy",
        np.asarray(embs, dtype=np.float32),
    )
    return persist_dir / "netlearn_kb.json"


def test_polluted_disk_store_loads_as_empty_and_second_boot_recounts(
    isolate_vectordb, tmp_path, monkeypatch, e5_down, dim
):
    """已被污染的历史目录：``_load`` 必须返回 False，且重新播种后重新计数。

    只做写侧过滤（半成品补丁）时此用例转红：``_load`` 会把 3 条零向量当正常数据
    读回（``count == 3``）⇒ 播种被 `count == 0` 跳过 ⇒ 计数器停在 0 ⇒
    ``/api/status`` 报 ``fallback_zero_docs:0`` / ``status:"ok"``，库里全是零向量。
    **首次启动诚实、重启后说谎** 的另一半洞就在这里。
    """
    from db.milvus_client import InMemoryVectorStore, vector_db

    json_path = _write_polluted_store(tmp_path, dim, n=3)

    # ── 重启：同一磁盘目录、全新实例 ──
    store = InMemoryVectorStore()
    assert store._load("netlearn_kb") is False, (
        "过滤后无可用文档 ⇒ _load 必须返回 False，调用方才会重新播种"
    )
    assert store.count("netlearn_kb") == 0

    # INC-2026-09-14：读路径只读不写不改名 —— 污染文件必须原样留着，
    # 不得被删除、搬走或改名 .corrupted.*
    assert json_path.exists(), "读路径不得删除主文件（INC-2026-09-14）"
    assert not list(tmp_path.glob("netlearn_kb.json.corrupted.*")), (
        "污染不是结构性损坏，不得产生 .corrupted 备份"
    )

    # ── 重新播种：全部重新计入 fallback_zero ──
    chunks = [{"id": f"c{i}", "text": f"t{i}", "metadata": {}} for i in range(3)]
    monkeypatch.setattr(vector_db, "_milvus_connected", False)
    monkeypatch.setattr(vector_db, "_mem_store", store)
    monkeypatch.setattr(vector_db, "_embedding_fallback_count", 0)

    assert vector_db._mem_insert("netlearn_kb", chunks) == 3
    assert vector_db.embedding_fallback_count == 3, (
        "污染目录重启后必须重新计入零向量 —— 否则探针继续低报成 ok"
    )

    # 落盘仍被写侧过滤挡住：磁盘上那 3 条零向量留在原处（幂等，不改写）
    import json as _json

    payload = _json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["ids"] == ["c0", "c1", "c2"], (
        "新数据全为零向量时不应覆盖磁盘内容；过滤幂等，下次启动照旧报降级"
    )
    assert all(
        m.get("embedding_status") == "fallback_zero" for m in payload["metas"]
    )


def test_partially_polluted_disk_store_keeps_good_docs_drops_zero_vectors(
    isolate_vectordb, tmp_path, dim
):
    """混合污染：真向量必须保住，零向量必须丢掉，且 embeddings 与 ids 同源对齐。

    这条专门锁「过滤必须发生在 .emb.npy 行数比对之前」：旧缓存按未过滤行数
    （3 行）写成，过滤后只剩 1 条 ⇒ 行数失配 ⇒ 回退 JSON 重建。
    若比对先于过滤、或过滤后忘了同步过滤 JSON 里的 embeddings，这里会读到
    3×dim 的矩阵配 1 个 id（错位读），断言随即失败。
    """
    import numpy as np

    from db.milvus_client import InMemoryVectorStore

    _write_polluted_store(tmp_path, dim, n=3, good_first=True)

    store = InMemoryVectorStore()
    assert store._load("netlearn_kb") is True, "还有可用文档时不应整库判空"
    assert store.count("netlearn_kb") == 1

    coll = store._collections["netlearn_kb"]
    assert coll["ids"] == ["ok"]
    assert coll["texts"] == ["good text"]
    assert coll["metas"] == [{"subject": "os"}]
    assert coll["embeddings"].shape == (1, dim), (
        f"embeddings 必须随 ids 一起过滤，实测 shape={coll['embeddings'].shape}"
    )
    assert np.allclose(coll["embeddings"][0], [0.5] * dim), "真向量不得被改写"
