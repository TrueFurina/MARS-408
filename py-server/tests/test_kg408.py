# -*- coding: utf-8 -*-
# ============================================================
# tests/test_kg408.py — 408 知识图谱骨架单元测试 + 可复现性测试
#
# 覆盖 T01/T02/T03/T04 的关键验收项：
#   - 节点 136（4 科目 + 26 章 + 106 考点），无重复 id、无孤儿、无悬空边
#     （136 = 源骨架 135 + 人工补充 1；106 = 源 105 + 人工 1，**分开计勿合并**）
#   - ID 稳定性：重跑 build 得到逐字节一致的产物
#   - 方向约定：prerequisites() 返回出边 target（先修项）
#   - ego-graph 跳数与 candidates 排序
#   - 跨科边双向性
#   - 权重红线：全为 null
#   - 未解析引用如实挂起，resolution 只取 4 个枚举值
#   - QA GAP-1：KB 覆盖率产物（含对外交付物 kb-alignment.md）受防伪证闸门保护
#   - QA GAP-2：输入表「改表 + 重跑」被冻结基线（kg408_inputs_frozen.json）拦住
#
# 不依赖 torch / milvus，可在无模型环境下运行。
# ============================================================

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.kg408 import (  # noqa: E402
    EDGE_ASSOCIATION,
    EDGE_PREREQUISITE,
    LEVEL_KP,
    LEVEL_SUBJECT,
    RESOLUTIONS,
    UNRESOLVED_REASONS,
    Kg408Store,
)

DATA_DIR = _ROOT / "data" / "kg408"
KG_PATH = DATA_DIR / "kg408.json"
SOURCE_HTML = Path("E:/Program/MARL/SAGE/pdf/03_408知识图谱骨架.html")

needs_artifacts = pytest.mark.skipif(
    not KG_PATH.exists(), reason="kg408.json 未生成，先跑 scripts/build_kg408.py"
)
needs_source = pytest.mark.skipif(
    not SOURCE_HTML.exists(), reason=f"源骨架 HTML 不存在: {SOURCE_HTML}"
)


@pytest.fixture(scope="module")
def store() -> Kg408Store:
    """模块级共享 store。"""
    return Kg408Store.load(
        path=KG_PATH,
        unresolved_path=DATA_DIR / "unresolved.json",
        stats_path=DATA_DIR / "kg408_stats.json",
    )


# ============================================================
# T01：数据层
# ============================================================
@needs_artifacts
def test_node_total(store: Kg408Store) -> None:
    """节点 136 = 4 科目 + 26 章 + 106 考点。

    其中**源骨架 135（4+26+105）**，**人工补充 1**（磁盘调度，学科负责人
    裁决补入）。两者必须分列，禁止合并成一个数字。
    """
    nodes = store.all_nodes()
    s = store.stats()
    assert s["nodes_from_source"] == 135
    assert s["nodes_manual_supplement"] == 1
    assert s["nodes_total"] == 136
    assert s["nodes_subject"] == 4
    assert s["nodes_chapter"] == 26
    assert s["nodes_knowledge_point"] == 106
    assert s["nodes_knowledge_point_from_source"] == 105
    assert s["nodes_knowledge_point_manual"] == 1
    assert len(nodes) == 136


@needs_artifacts
def test_manual_node_is_declared_and_isolated(store: Kg408Store) -> None:
    """人工补充节点必须显式标记 origin=manual，且挂在 OS/文件管理。"""
    manual = [n for n in store.all_nodes() if n.origin == "manual"]
    assert [n.id for n in manual] == ["408:OS:CH04:KP05"]
    n = manual[0]
    assert n.label == "磁盘调度"
    assert n.subject == "OS"
    assert n.chapter == "文件管理"
    assert n.source_row == 0, "人工节点无源表格行，不得伪造 source_row"
    # 源节点必须全部 origin=source
    assert all(
        x.origin == "source" for x in store.all_nodes() if x.id != n.id
    )


@needs_artifacts
def test_no_duplicate_node_ids(store: Kg408Store) -> None:
    """无重复 id。"""
    ids = [n.id for n in store.all_nodes()]
    assert len(ids) == len(set(ids))


@needs_artifacts
def test_hierarchy_no_orphan(store: Kg408Store) -> None:
    """除 4 个科目根外，每个节点都有存在的父节点。"""
    ids = {n.id for n in store.all_nodes()}
    for n in store.all_nodes():
        if n.level == LEVEL_SUBJECT:
            assert n.parent_id is None
        else:
            assert n.parent_id is not None, f"{n.id} 缺少 parent_id"
            assert n.parent_id in ids, f"{n.id} 的 parent_id 悬空"


@needs_artifacts
def test_no_dangling_edges(store: Kg408Store) -> None:
    """全部边的 source/target 都指向存在的节点。"""
    ids = {n.id for n in store.all_nodes()}
    for e in store.all_edges():
        assert e.source in ids, f"{e.id} source 悬空"
        assert e.target in ids, f"{e.id} target 悬空"


@needs_artifacts
def test_prereq_edges_not_exceed_source_declarations(store: Kg408Store) -> None:
    """先修边条数 ≤ 源声明的 23 条（只可能少，不可能多）。"""
    stats = store.stats()
    prereq = sum(1 for e in store.all_edges() if e.type == EDGE_PREREQUISITE)
    assert prereq <= stats["source_prereq_declarations"] == 23
    assert prereq == stats["edges_prerequisite"]


@needs_artifacts
def test_resolution_enum_only(store: Kg408Store) -> None:
    """resolution 只取 exact/alias/chapter_level/manual。"""
    for e in store.all_edges():
        assert e.resolution in RESOLUTIONS, f"{e.id} resolution={e.resolution}"


@needs_artifacts
def test_unresolved_reasons_enum_only(store: Kg408Store) -> None:
    """未解析项的 reason 只取三个枚举值，且每条都有 suggested_action。"""
    for u in store.unresolved():
        assert u.reason in UNRESOLVED_REASONS
        assert u.raw_name
        assert u.suggested_action
        assert u.context_row > 0


@needs_artifacts
def test_weight_red_line_all_null(store: Kg408Store) -> None:
    """权重红线：源未提供数值 → weight 全为 null，禁止编造。"""
    for e in store.all_edges():
        assert e.weight is None, f"{e.id} weight 非 null"
    for e in store.all_edges():
        if e.type == EDGE_ASSOCIATION:
            assert e.weight_source == "not_provided_by_source"
        else:
            assert e.weight_source == "not_applicable"


@needs_artifacts
def test_provenance_fields(store: Kg408Store) -> None:
    """provenance 含 sha256 / command / generated_at_utc / parser_rule_version。"""
    p = store.provenance
    assert len(p.source_sha256) == 64
    assert "build_kg408.py" in p.command
    assert p.generated_at_utc
    assert p.parser_rule_version


@needs_artifacts
def test_subject_distribution(store: Kg408Store) -> None:
    """分科考点数：DS 35 / CO 22 / OS 21 / CN 28（OS 多 1 = 人工补充磁盘调度）。"""
    expected = {"DS": 35, "CO": 22, "OS": 21, "CN": 28}
    for code, n_kp in expected.items():
        got = sum(
            1 for n in store.all_nodes() if n.subject == code and n.level == LEVEL_KP
        )
        assert got == n_kp, f"{code} 考点数 {got} != {n_kp}"
    # 源骨架侧的分科考点数（不含人工补充）
    src = {"DS": 35, "CO": 22, "OS": 20, "CN": 28}
    for code, n_kp in src.items():
        got = sum(
            1
            for n in store.all_nodes()
            if n.subject == code and n.level == LEVEL_KP and n.origin == "source"
        )
        assert got == n_kp, f"{code} 源骨架考点数 {got} != {n_kp}"


@needs_artifacts
def test_depends_on_alias_disclosed(store: Kg408Store) -> None:
    """QA M7：如实暴露「多少条边依赖人工别名表」。

    此前 `resolution` 只记单端点，导致「起点靠别名、终点精确」的边被记成
    exact（18 条里只有 12 条标 alias），低估人工映射覆盖面。
    现在 resolution 取最弱环节，且 depends_on_alias 单独给出。
    """
    s = store.stats()
    dep = s["edges_depending_on_alias"]
    total = s["edges_total"]
    pure = s["edges_pure_exact"]
    assert dep + pure == total, "依赖/不依赖别名表的边数之和应等于总边数"
    assert s["resolution_counts"].get("alias", 0) == dep, (
        "resolution=alias 的条数应与 depends_on_alias 一致（最弱环节口径）"
    )
    # 逐边复核：只要任一端点是 alias，边就必须标 alias
    for e in store.all_edges():
        expect = (
            e.source_resolution == "alias" or e.target_resolution == "alias"
        )
        assert e.depends_on_alias is expect, f"{e.id} depends_on_alias 标记错误"
        if expect:
            assert e.resolution == "alias", f"{e.id} 应为 alias（最弱环节）"


@needs_artifacts
def test_stats_are_recomputed_not_read_from_file(store: Kg408Store) -> None:
    """QA M2：服务层统计必须**重算**，与 stats.json 落盘值相互独立。

    即使 stats.json 被篡改，store.stats() 也应返回由 kg408.json 重算的真值。
    """
    from services.kg408 import build_stats

    kg = store.kg
    recomputed = build_stats(
        store.all_nodes(), store.all_edges(), store.unresolved(), kg.source_counts
    )
    assert store.stats() == recomputed
    # 若 stats.json 存在，其内容必须等于重算值（由 verify 强制；这里做同源断言）
    if store.stats_file is not None:
        for k, v in recomputed.items():
            assert store.stats_file.get(k) == v, f"stats.json[{k}] 与重算真值不符"
    # 独立校验：篡改 stats.json 不影响 store.stats()（不读落盘值）
    if store.stats_file is not None:
        tampered = Kg408Store(kg)
        tampered._stats_file = {"nodes_total": 999}
        assert tampered.stats()["nodes_total"] == 136


# ============================================================
# T01：可复现性（ID 稳定性）
# ============================================================
@needs_artifacts
@needs_source
def test_rebuild_is_byte_identical() -> None:
    """重跑 build 到临时目录，产物与已入库逐字节一致（git diff 为空）。"""
    prov = json.loads(KG_PATH.read_text(encoding="utf-8"))["provenance"]
    committed_cmd = prov["command"]
    # 用 provenance 里**记录的**路径原样重放，否则路径字符串本身会造成假差异
    with tempfile.TemporaryDirectory(prefix="kg408-repro-") as tmp:
        cmd = [
            sys.executable,
            str(_ROOT / "scripts" / "build_kg408.py"),
            "--source",
            str(SOURCE_HTML),
            "--out-dir",
            tmp,
            "--no-doc",
            "--alias",
            prov["alias_path"],
            "--chapter-map",
            prov["chapter_map_path"],
            "--manual-nodes",
            prov["manual_nodes_path"],
            "--command",
            committed_cmd,
        ]
        proc = subprocess.run(
            cmd, cwd=str(_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        assert proc.returncode == 0, f"重跑失败: {proc.stderr[:800]}"
        for name in ("kg408.json", "unresolved.json"):
            assert (Path(tmp) / name).read_bytes() == (DATA_DIR / name).read_bytes(), (
                f"{name} 重跑后与已入库不一致"
            )


@needs_artifacts
def test_ids_are_row_order_stable() -> None:
    """ID 由行序生成：CH/KP 编号在同一父下连续且从 01 开始。"""
    data = json.loads(KG_PATH.read_text(encoding="utf-8"))
    kps_by_parent: dict = {}
    for n in data["nodes"]:
        if n["level"] == LEVEL_KP:
            kps_by_parent.setdefault(n["parent_id"], []).append(n)
    for parent, kps in kps_by_parent.items():
        nums = sorted(int(k["id"].rsplit("KP", 1)[1]) for k in kps)
        assert nums == list(range(1, len(kps) + 1)), f"{parent} 的 KP 编号不连续"


# ============================================================
# T02：服务层
# ============================================================
@needs_artifacts
def test_store_builds_all_four_indexes(store: Kg408Store) -> None:
    """_by_id / _children / _out / _in 四类索引均已建立。"""
    assert len(store._by_id) == 136
    assert len(store._children) == 30  # 4 科目 + 26 章
    assert len(store._out) > 0
    assert len(store._in) > 0


@needs_artifacts
def test_prerequisites_returns_out_edge_targets(store: Kg408Store) -> None:
    """方向约定：prerequisites(kp) 返回**出边** target（先修项）。

    408:DS:CH06:KP04 = 最短路径（Dijkstra/Floyd），源声明其先修为
    图存储 + BFS，即 CH06:KP01 与 CH06:KP02。
    """
    kp = "408:DS:CH06:KP04"
    got = sorted(n.id for n in store.prerequisites(kp))
    assert got == ["408:DS:CH06:KP01", "408:DS:CH06:KP02"]
    # dependents 是反向：以 KP01 为先修的考点应包含 KP04
    assert kp in [n.id for n in store.dependents("408:DS:CH06:KP01")]


@needs_artifacts
def test_associations_are_bidirectional(store: Kg408Store) -> None:
    """跨科边 directed=false，查询层双向返回。"""
    assoc_edges = [e for e in store.all_edges() if e.type == EDGE_ASSOCIATION]
    assert assoc_edges, "应至少有一条跨科边"
    for e in assoc_edges:
        assert e.directed is False
        a = [n.id for n in store.associations(e.source)]
        b = [n.id for n in store.associations(e.target)]
        assert e.target in a, f"{e.id} 正向不可见"
        assert e.source in b, f"{e.id} 反向不可见"


@needs_artifacts
def test_ego_graph_hops_and_candidate_order(store: Kg408Store) -> None:
    """ego_graph：hop1 排除自身、hop2 排除 ego∪hop1；candidates 按
    hop1-先修 > hop1-跨科 > hop2 排序。"""
    kp = "408:DS:CH06:KP04"
    res = store.ego_graph(kp, hops=2)
    assert res is not None
    ego_id = res["ego"]["id"]
    hop1_ids = {d["node"]["id"] for d in res["hop1"]}
    hop2_ids = {d["node"]["id"] for d in res["hop2"]}
    assert ego_id not in hop1_ids
    assert ego_id not in hop2_ids
    assert not (hop1_ids & hop2_ids)

    ranks = [c["rank"] for c in res["candidates"]]
    assert ranks == sorted(ranks), f"candidates 未按 rank 排序: {ranks}"
    # hop1-先修(0) 必须排在 hop1-跨科(1) 之前，跨科排在 hop2(2) 之前
    for c in res["candidates"]:
        if c["hop"] == 1 and c["via"] == EDGE_PREREQUISITE:
            assert c["rank"] == 0
        elif c["hop"] == 1 and c["via"] == EDGE_ASSOCIATION:
            assert c["rank"] == 1
        else:
            assert c["rank"] == 2


@needs_artifacts
def test_ego_graph_unknown_id_returns_none(store: Kg408Store) -> None:
    """不存在的 kp_id 返回 None（由接口层转 404）。"""
    assert store.ego_graph("408:NOPE:CH99:KP99") is None


@needs_artifacts
def test_ego_graph_hops1_has_no_hop2(store: Kg408Store) -> None:
    """hops=1 时不产生 hop2。"""
    res = store.ego_graph("408:DS:CH06:KP04", hops=1)
    assert res is not None
    assert res["hop2"] == []


@needs_artifacts
def test_subject_view_contains_only_internal_edges(store: Kg408Store) -> None:
    """subject_view('CN') 返回的边两端均在子树内，且无第 5 份真源。"""
    view = store.kg.subject_view("CN")
    ids = {n.id for n in view.nodes}
    assert view.stats["nodes_knowledge_point"] == 28
    assert view.stats["nodes_chapter"] == 6
    for e in view.edges:
        assert e.source in ids and e.target in ids


@needs_artifacts
def test_subject_rollup(store: Kg408Store) -> None:
    """考点级 → 章级上卷适配口。"""
    assert store.subject_rollup("408:DS:CH06:KP04") == "408:DS:CH06"
    assert store.subject_rollup("408:DS:CH06") == "408:DS:CH06"


@needs_artifacts
def test_legacy_projection_shape(store: Kg408Store) -> None:
    """兼容投影只含 id/label/group 与 source/target（既有消费方口径）。"""
    legacy = store.kg.to_legacy()
    assert set(legacy.keys()) == {"nodes", "edges"}
    for n in legacy["nodes"]:
        assert set(n.keys()) == {"id", "label", "group"}
    for e in legacy["edges"]:
        assert set(e.keys()) == {"source", "target"}


# ============================================================
# T03：接口层
# ============================================================
def _kg408_test_client():
    """构造带鉴权覆盖的 kg408 测试客户端。

    返回 (client, raw_client)：raw_client **不带** 鉴权覆盖，用于断言 401。
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.kg408 import router
    from shared.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "test-user",
        "role": "student",
    }
    raw = FastAPI()
    raw.include_router(router)
    return TestClient(app), TestClient(raw)


@needs_artifacts
def test_api_requires_auth() -> None:
    """QA M13：本模块与其它数据端点一致，未登录应 401（此前是匿名可访问）。"""
    try:
        _client, raw = _kg408_test_client()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"FastAPI TestClient 不可用: {exc}")

    for path in (
        "/kg408/graph",
        "/kg408/stats",
        "/kg408/unresolved",
        "/kg408/ego/408:DS:CH06:KP04",
    ):
        r = raw.get(path)
        assert r.status_code == 401, f"{path} 未鉴权应 401，实际 {r.status_code}"


@needs_artifacts
def test_api_graph_endpoint() -> None:
    """GET /kg408/graph 返回 {nodes, edges, stats, provenance}。"""
    try:
        client, _raw = _kg408_test_client()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"FastAPI TestClient 不可用: {exc}")

    r = client.get("/kg408/graph?subject=DS")
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"nodes", "edges", "stats", "provenance"} <= set(body.keys())
    assert body["stats"]["nodes_knowledge_point"] == 35

    r = client.get("/kg408/graph?subject=BAD")
    assert r.status_code == 400


@needs_artifacts
def test_api_stats_shape_is_uniform() -> None:
    """QA M11：整图与分科子图的 stats **键集合必须一致**（同一 key 一种契约）。"""
    try:
        client, _raw = _kg408_test_client()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"FastAPI TestClient 不可用: {exc}")

    # 分科视图**允许**缺少的 key：仅限「全图口径」的源文档声明计数
    # （见 services.kg408.build_stats 注释与 stats_scope 字段）。
    GLOBAL_ONLY = {
        "source_prereq_rows",
        "source_prereq_declarations",
        "source_prereq_declarations_resolved",
        "source_cross_rows",
        "source_cross_refs",
        "prereq_success_pct",
    }
    all_stats = client.get("/kg408/graph?subject=all").json()["stats"]
    assert all_stats["stats_scope"] == "global"
    assert GLOBAL_ONLY <= set(all_stats), "全图视图应携带源声明计数"
    for code in ("DS", "CO", "OS", "CN"):
        sub_stats = client.get(f"/kg408/graph?subject={code}").json()["stats"]
        assert sub_stats["stats_scope"] == "subject"
        missing = set(all_stats) - set(sub_stats)
        unexpected = missing - GLOBAL_ONLY
        assert not unexpected, f"{code} 的 stats 缺少非预期键: {sorted(unexpected)}"
        # 这些 key 在两种视图下都必须存在且非 None（QA M11 的原始诉求）
        for k in ("weight_null_count", "resolution_counts", "by_subject",
                  "unresolved_total", "edges_depending_on_alias", "stats_scope"):
            assert sub_stats.get(k) is not None, f"{code}: stats[{k}] 为空"


@needs_artifacts
def test_api_ego_404_and_stats_and_unresolved() -> None:
    """ego 非法 id → 404；stats / unresolved 端点可用。"""
    try:
        client, _raw = _kg408_test_client()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"FastAPI TestClient 不可用: {exc}")

    r = client.get("/kg408/ego/408:DS:CH06:KP04?hops=2")
    assert r.status_code == 200, r.text
    assert r.json()["ego"]["id"] == "408:DS:CH06:KP04"

    r = client.get("/kg408/ego/not-a-real-id")
    assert r.status_code == 404
    assert "考点不存在" in r.json()["detail"]

    r = client.get("/kg408/stats")
    assert r.status_code == 200
    assert r.json()["stats"]["nodes_total"] == 136

    r = client.get("/kg408/unresolved")
    assert r.status_code == 200
    assert r.json()["count"] == len(Kg408Store.load().unresolved())


@needs_artifacts
def test_api_unresolved_invalid_reason_is_400() -> None:
    """QA M10：非法 reason 必须 400，不得静默返回空列表（避免误读为「无问题」）。"""
    try:
        client, _raw = _kg408_test_client()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"FastAPI TestClient 不可用: {exc}")

    r = client.get("/kg408/unresolved?reason=NOT_A_REASON")
    assert r.status_code == 400, r.text
    assert "reason 非法" in r.json()["detail"]

    r = client.get("/kg408/unresolved?reason=absent_in_skeleton")
    assert r.status_code == 200
    assert r.json()["count"] > 0
    assert all(
        u["reason"] == "absent_in_skeleton" for u in r.json()["unresolved"]
    )


def test_router_registered_in_api_package() -> None:
    """kg408_router 已注册到 api 包导出列表（否则 main.py 起不来）。"""
    import api

    assert hasattr(api, "kg408_router")
    assert "kg408_router" in api.__all__


# ============================================================
# T04：KB 对齐
# ============================================================
@needs_artifacts
def test_kp_binding_honesty() -> None:
    """考点级绑定只用全等方法，且绑不上的记 null（不伪造、不丢弃）。"""
    binding_path = DATA_DIR / "kp_chunk_binding.json"
    if not binding_path.exists():
        pytest.skip("kp_chunk_binding.json 未生成，先跑 scripts/bind_kb_to_kg408.py")
    doc = json.loads(binding_path.read_text(encoding="utf-8"))
    rows = doc["bindings"]
    allowed = {"chapter_exact", "subject_exact", "subtopic_exact", "alias"}
    for r in rows:
        if r["kp_match_method"] is not None:
            assert r["kp_match_method"] in allowed
        if r["chunk_type"] == "knowledge_variant":
            assert r["kp_id"] is None, "variant 不应参与考点级强制绑定"
        if r["kp_id"] is None:
            assert r["kp_match_method"] is None


@needs_artifacts
def test_kp_coverage_report_exists() -> None:
    """覆盖率产物存在且声明未使用模糊匹配。"""
    cov_path = DATA_DIR / "kp_chunk_coverage.json"
    if not cov_path.exists():
        pytest.skip("kp_chunk_coverage.json 未生成")
    cov = json.loads(cov_path.read_text(encoding="utf-8"))["coverage"]
    assert cov["honesty"]["fuzzy_matching_used"] is False
    assert cov["chunks_total"] == 1892
    # 106 = 源骨架 105 + 人工补充 1（磁盘调度）；覆盖率分母必须是最新真值
    assert cov["kp_level"]["kp_total"] == len(
        [n for n in Kg408Store.load().all_nodes() if n.level == LEVEL_KP]
    )
    assert cov["kp_level"]["bound_pct_of_eligible"] <= 100.0


@needs_artifacts
def test_no_wrong_dispatch_mapping() -> None:
    """QA M9 + 学科负责人裁决：『调度』不得再映射到进程调度『调度算法』。"""
    alias = json.loads(
        (DATA_DIR / "kg408_alias.json").read_text(encoding="utf-8")
    )
    for e in alias["entries"]:
        if e.get("raw") == "调度":
            assert e["chapter"] == "文件管理", "『调度』应改判为磁盘调度"
            assert e["label"] == "磁盘调度"
            assert e.get("supersedes", {}).get("label") == "调度算法"
    # XSUB0004 必须指向人工补充的磁盘调度节点
    kg = json.loads(KG_PATH.read_text(encoding="utf-8"))
    x4 = [e for e in kg["edges"] if e["id"] == "408:E:XSUB0004"]
    assert len(x4) == 1, "XSUB0004 应保留（改目标，不删边）"
    assert x4[0]["target"] == "408:OS:CH04:KP05"


# ============================================================
# 回归：既有消费方不受影响
# ============================================================
@needs_artifacts
def test_legacy_knowledge_graph_untouched() -> None:
    """legacy seed_data.KNOWLEDGE_GRAPH 仍是 643/639（本任务默认并存不替换）。"""
    import seed_data

    assert len(seed_data.KNOWLEDGE_GRAPH["nodes"]) == 643
    assert len(seed_data.KNOWLEDGE_GRAPH["edges"]) == 639
    # 408 图谱是独立真源，不污染 legacy
    assert all(
        not str(n["id"]).startswith("408:") for n in seed_data.KNOWLEDGE_GRAPH["nodes"]
    )


# ============================================================
# QA GAP-1：覆盖率产物必须受防伪证闸门保护
#   （此前 kp_chunk_coverage.json / kb-alignment.md 被改数字，
#     verify 与 pytest 双双绿）
# ============================================================
KB_DOC_PATH = _ROOT.parent / "deliverables" / "408-kg" / "kb-alignment.md"
STATS_DOC_PATH = _ROOT.parent / "deliverables" / "408-kg" / "kg408-stats.md"
FROZEN_PATH = DATA_DIR / "kg408_inputs_frozen.json"

# 变异测试会临时改写这些产物；模块级快照 + 收尾还原（即使单测失败也不留脏）。
_ARTIFACT_PATHS = [
    DATA_DIR / "kg408_alias.json",
    DATA_DIR / "kg408_chapter_map.json",
    DATA_DIR / "kg408_manual_nodes.json",
    DATA_DIR / "kg408_inputs_frozen.json",
    DATA_DIR / "kg408.json",
    DATA_DIR / "kg408_stats.json",
    DATA_DIR / "unresolved.json",
    DATA_DIR / "kp_chunk_coverage.json",
    DATA_DIR / "kp_chunk_binding.json",
    KB_DOC_PATH,
    STATS_DOC_PATH,
]


@pytest.fixture(scope="module", autouse=True)
def _snapshot_and_restore_artifacts():
    """快照全部产物；模块结束（含失败）时逐字节还原，禁止把篡改态留在仓库。"""
    snap = {p: p.read_bytes() for p in _ARTIFACT_PATHS if p.exists()}
    yield
    for p, b in snap.items():
        if p.exists():
            p.write_bytes(b)


def _run_py(args: list) -> subprocess.CompletedProcess:
    """在 py-server 下跑一个脚本，返回 CompletedProcess。"""
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _verify_exit() -> int:
    """跑 verify **无参全量**（唯一可信模式），返回 exit 码。

    在**进程内**直接调用 `verify_kg408.main([])` —— 与 CLI 无参完全等价，
    但避免子进程风暴触发环境侧的批量删除守卫。
    """
    scripts = _ROOT / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import verify_kg408

    return verify_kg408.main([])


def _build_exit() -> int:
    """按 provenance.command 的方式重跑 build。"""
    return _run_py(["scripts/build_kg408.py"]).returncode


@contextlib.contextmanager
def _tamper(path: Path, new_bytes: bytes):
    """临时篡改一个文件，退出时逐字节还原。"""
    original = path.read_bytes()
    try:
        path.write_bytes(new_bytes)
        yield
    finally:
        path.write_bytes(original)


@needs_artifacts
def test_generated_artifacts_use_lf_line_endings() -> None:
    """跨平台逐字节可复现：产物必须写 LF。

    Windows 下 `Path.write_text` 默认把 `\\n` 翻成 `\\r\\n`，会让「逐字节可复现」
    只在 Windows 内成立、在 Linux CI 失效（同一份源产出不同字节）。
    """
    targets = [
        KG_PATH,
        DATA_DIR / "unresolved.json",
        DATA_DIR / "kg408_stats.json",
        DATA_DIR / "kp_chunk_coverage.json",
        DATA_DIR / "kp_chunk_binding.json",
        STATS_DOC_PATH,
        KB_DOC_PATH,
    ]
    for p in targets:
        if not p.exists():
            continue
        assert b"\r\n" not in p.read_bytes(), (
            f"{p.name} 含 CRLF —— 跨平台逐字节复现将失效"
        )


@needs_artifacts
def test_kp_coverage_exact_numbers() -> None:
    """QA GAP-1：覆盖率数字必须**显式**断言（此前只断言 fuzzy=false）。"""
    p = DATA_DIR / "kp_chunk_coverage.json"
    if not p.exists():
        pytest.skip("kp_chunk_coverage.json 未生成")
    cov = json.loads(p.read_text(encoding="utf-8"))["coverage"]
    cl, kl = cov["chapter_level"], cov["kp_level"]
    assert cov["chunks_total"] == 1892
    assert cov["chunks_knowledge_point"] == 748
    assert cov["chunks_knowledge_variant"] == 1144
    # 章级
    assert cl["bound"] == 1684
    assert cl["bound_pct"] == 89.01
    assert cl["chapter_coverage_pct"] == 96.15
    assert cl["chapters_total"] == 26
    assert cl["chapters_with_chunk"] == 25
    # 考点级：36/106 = 33.96%（分母含人工补充节点）
    assert kl["kp_total"] == 106
    assert kl["kp_covered"] == 36
    assert kl["kp_coverage_pct"] == 33.96
    assert kl["bound"] == 46, "kp_id 非空的 chunk 数"
    assert kl["match_methods"] == {"subtopic_exact": 43, "alias": 3}
    assert kl["unbound_eligible"] == 702
    assert kl["variant_excluded_by_design"] == 1144
    assert cov["honesty"]["fuzzy_matching_used"] is False


@needs_artifacts
def test_kb_alignment_doc_matches_coverage_numbers() -> None:
    """kb-alignment.md（对外唯一人读交付物）里的数字必须与 coverage.json 一致。"""
    if not KB_DOC_PATH.exists():
        pytest.skip("kb-alignment.md 未生成")
    md = KB_DOC_PATH.read_text(encoding="utf-8")
    assert "**33.96%**" in md, "考点级覆盖率必须如实写 33.96%"
    assert "（36/106）" in md
    assert "1684（89.01%）" in md
    assert "96.15%" in md
    assert "106 考点）" in md, "分母必须动态为 106（禁止硬编码 105）"
    assert "105 考点" not in md, "不得残留旧分母 105"


@needs_artifacts
def test_verify_catches_kb_alignment_md_tampering() -> None:
    """QA GAP-1 验收：改 kb-alignment.md 33.96 -> 99.99，无参 verify 必须 exit 1。"""
    if not KB_DOC_PATH.exists():
        pytest.skip("kb-alignment.md 未生成")
    assert _verify_exit() == 0, "前置：正常态必须为绿"
    tampered = KB_DOC_PATH.read_text(encoding="utf-8").replace("33.96", "99.99")
    with _tamper(KB_DOC_PATH, tampered.encode("utf-8")):
        assert _verify_exit() == 1, "改 md 覆盖率数字必须被拦住"
    assert _verify_exit() == 0, "还原后必须恢复为绿"


@needs_artifacts
def test_verify_catches_coverage_json_tampering() -> None:
    """QA GAP-1 验收：改 kp_chunk_coverage.json 33.96 -> 99.99，无参 verify 必须 exit 1。"""
    p = DATA_DIR / "kp_chunk_coverage.json"
    if not p.exists():
        pytest.skip("kp_chunk_coverage.json 未生成")
    assert _verify_exit() == 0, "前置：正常态必须为绿"
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["coverage"]["kp_level"]["kp_coverage_pct"] = 99.99
    with _tamper(p, (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")):
        assert _verify_exit() == 1, "改 coverage.json 必须被拦住"
    assert _verify_exit() == 0, "还原后必须恢复为绿"


# ============================================================
# QA GAP-2：输入表「改表 + 重跑」不得自洽通过（冻结基线漂移检测）
# ============================================================
@needs_artifacts
def test_frozen_manifest_pins_input_tables() -> None:
    """冻结清单必须存在，且三张输入表的 sha256 与之一致。"""
    assert FROZEN_PATH.exists(), (
        "kg408_inputs_frozen.json 缺失 —— 缺了它就无法检测『改表→重跑』漂移"
    )
    frozen = json.loads(FROZEN_PATH.read_text(encoding="utf-8"))
    entries = frozen["entries"]
    for name in (
        "kg408_alias.json",
        "kg408_chapter_map.json",
        "kg408_manual_nodes.json",
    ):
        assert name in entries, f"冻结清单缺少 {name}"
        real = _sha256(DATA_DIR / name)
        assert entries[name]["sha256"] == real, (
            f"{name} 当前 sha 与冻结基线不符："
            f"冻结={entries[name]['sha256']}，当前={real}"
        )


@needs_artifacts
def test_frozen_manifest_review_status_is_truthful() -> None:
    """诚信红线：review_status 必须如实——不得把未复核的表虚标为已批准。"""
    frozen = json.loads(FROZEN_PATH.read_text(encoding="utf-8"))
    e = frozen["entries"]
    assert e["kg408_manual_nodes.json"]["review_status"] == (
        "approved_by_discipline_owner"
    )
    # 只有『磁盘调度/调度』一条经裁决；整张 alias 表与 chapter_map 仍待复核
    assert e["kg408_alias.json"]["review_status"] == (
        "pending_discipline_owner_review"
    )
    assert e["kg408_chapter_map.json"]["review_status"] == (
        "pending_discipline_owner_review"
    )
    statuses = {v["review_status"] for v in e.values()}
    assert statuses != {"approved_by_discipline_owner"}, (
        "不得把全部输入表都标成已批准（虚标）"
    )


@needs_artifacts
@needs_source
def test_verify_catches_input_table_drift_despite_rebuild() -> None:
    """QA GAP-2 验收：改 alias 表 → 重跑 build（provenance 锚点自动跟上）→
    无参 verify 仍必须 exit 1（靠冻结清单发现漂移）。"""
    alias = DATA_DIR / "kg408_alias.json"
    if not alias.exists():
        pytest.skip("kg408_alias.json 未生成")
    assert _verify_exit() == 0, "前置：正常态必须为绿"

    doc = json.loads(alias.read_text(encoding="utf-8"))
    for ent in doc["entries"]:
        if ent.get("raw") == "调度":
            ent["subject"], ent["chapter"], ent["label"] = (
                "CO", "中央处理器", "中断",
            )
    tampered = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    # 关键：**按 provenance.command 的方式重跑**，让 provenance 锚点自动跟上改动
    outputs = [
        DATA_DIR / "kg408.json",
        DATA_DIR / "kg408_stats.json",
        DATA_DIR / "unresolved.json",
        KB_DOC_PATH,
    ]
    saved = {p: p.read_bytes() for p in outputs if p.exists()}
    try:
        with _tamper(alias, tampered):
            assert _build_exit() == 0, "改表后重跑应当成功（这正是漏洞的伪装）"
            assert _verify_exit() == 1, (
                "改表 + 重跑后 provenance 锚点自洽，必须靠冻结清单拦住"
            )
    finally:
        for p, b in saved.items():
            p.write_bytes(b)
        _build_exit()  # 还原产物
    assert _verify_exit() == 0, "还原后必须恢复为绿"


def _sha256(path: Path) -> str:
    """文件 sha256。"""
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@needs_artifacts
@needs_source
def test_verify_catches_forged_manual_node_despite_rebuild() -> None:
    """QA GAP-2 验收（P2）：往人工表塞伪造节点 → 重跑 build → 无参 verify 必须 exit 1。"""
    manual = DATA_DIR / "kg408_manual_nodes.json"
    if not manual.exists():
        pytest.skip("kg408_manual_nodes.json 未生成")
    assert _verify_exit() == 0, "前置：正常态必须为绿"

    doc = json.loads(manual.read_text(encoding="utf-8"))
    doc["nodes"].append(
        {
            "id": "408:OS:CH04:KP99",
            "label": "伪造节点对抗测试",
            "subject": "OS",
            "chapter": "文件管理",
            "level": "knowledge_point",
            "ordinal": 99,
            "aliases": [],
            "source": "forged_for_mutation_test",
        }
    )
    tampered = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    outputs = [
        DATA_DIR / "kg408.json",
        DATA_DIR / "kg408_stats.json",
        DATA_DIR / "unresolved.json",
        KB_DOC_PATH,
    ]
    saved = {p: p.read_bytes() for p in outputs if p.exists()}
    try:
        with _tamper(manual, tampered):
            assert _build_exit() == 0, "伪造人工节点后重跑应当成功（伪装成合法真值）"
            assert _verify_exit() == 1, "伪造人工节点必须被冻结清单拦住"
    finally:
        for p, b in saved.items():
            p.write_bytes(b)
        _build_exit()
    assert _verify_exit() == 0, "还原后必须恢复为绿"
