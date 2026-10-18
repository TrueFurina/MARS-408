# -*- coding: utf-8 -*-
"""app/status.py 与 app/routers.py 的三条长期不变量（2026-09-28 审查新增）

这三条的共同点：**违反时不报错，只会悄悄出错**，所以必须写成断言。

1. 健康探针自身永不抛异常 —— 若 vector_db 一挂探针先 500，编排系统会误判实例
   死亡并反复重启（故障放大器）。
2. 对外宣称的画像维度必须等于唯一真值源 —— 曾是硬编码 8，而本分支权威定义是
   career_state.DIMENSIONS 的 6 维（旧版 408 学情画像遗留），属口径漂移。
3. api/__init__.py 导出的 router 必须全部登记到 ALL_ROUTERS 且仅一次 —— 漏登记
   接口会静默消失，重复登记则让「注册顺序即匹配顺序」的约定失效。
4. 对外 OpenAPI 描述宣称的 LangGraph 节点数必须等于图中真实节点数 —— 该描述
   直接出现在 /docs 与 openapi.json 上（对外契约），数字写错不会报任何错。
5. 对外 OpenAPI 描述宣称的认证覆盖率必须等于从真实路由表重算的值 —— 同属对外契约，
   且历史包袱更重：97.8% 是 2026-07-10 一次性快照，此后路由一直变动而无人重算。
6. status.py 通过 getattr 读取的 vector_db 属性必须真实存在，且回落计数必须能端到端
   抵达探针 —— getattr 的默认值会把「读取方/实现方命名漂移」静默吞掉。
   2026-10-18 实证：embedding_fallback_count 只有私有字段、公开属性从未落地
   （D5 §2.1 的设计漏做），fallback_zero_docs 恒报 0，embedding 降级判定形同虚设。
"""

import pytest

from app import status as status_mod
from app.routers import ALL_ROUTERS


class _BoomVectorDb:
    """替身：模拟向量存储完全不可用。"""

    _milvus_connected = False
    embedding_fallback_count = 0

    def count(self, *args, **kwargs):
        raise RuntimeError("simulated vector store outage")


@pytest.mark.asyncio
async def test_health_probe_reports_degraded_instead_of_raising(monkeypatch):
    """向量库探测抛异常时，健康端点必须降级返回而非 500。

    健康端点是故障时的生命线：它若最先崩掉，上层编排拿到的就不是
    「降级」而是「实例不可用」，从而触发本可避免的重启循环。
    """
    monkeypatch.setattr(status_mod, "vector_db", _BoomVectorDb())

    payload = await status_mod.status()  # 不得抛出

    assert payload["status"] == "degraded"
    assert any("健康探测失败" in r for r in payload["degraded_reasons"]), payload[
        "degraded_reasons"
    ]
    # 探针失败也必须给出完整结构，便于运维直接读健康面
    assert payload["health"]["vector_db"]["collection_size"] == 0


def test_profile_dimensions_uses_single_source_of_truth():
    """对外宣称的画像维度数必须派生自唯一真值源，且该源可达。"""
    from agents.career_state import DIMENSIONS

    derived = status_mod._profile_dimension_count()

    # -1 表示真值源读取失败，宁可让本测试红，也不许对外报一个未经源证的数字
    assert derived != -1, "读取画像维度真值源失败，禁止对外宣称占位数字"
    assert derived == len(DIMENSIONS)
    # 下限保护：真值源若被改坏（清空/去重丢失），上面那条等式会因 0==0 而放行
    assert DIMENSIONS and len(set(DIMENSIONS)) == len(DIMENSIONS) >= 6, DIMENSIONS
    # 维度 key 与展示名必须一一对应，否则前端会渲染出空标签
    from agents.career_state import DIMENSION_LABELS

    assert set(DIMENSION_LABELS) == set(DIMENSIONS)


def test_every_exported_router_is_registered_exactly_once():
    """导出的 router 必须全部登记，且每个仅登记一次。

    新增 router 需要在两处同步（api/__init__.py 导出 + ALL_ROUTERS 登记），
    漏登记不会报任何错，只是接口静默不存在 —— 只能靠这条不变量发现。
    """
    import api

    exported = {name: getattr(api, name) for name in dir(api) if name.endswith("_router")}
    assert exported, "api/__init__.py 未导出任何 *_router，疑似导入方式变更"

    registered_ids = [id(r) for r in ALL_ROUTERS]
    missing = sorted(n for n, obj in exported.items() if id(obj) not in set(registered_ids))
    duplicated = sorted(
        n for n, obj in exported.items() if registered_ids.count(id(obj)) > 1
    )

    assert not missing, f"以下 router 已导出但未登记，其接口将静默不存在: {missing}"
    assert not duplicated, f"以下 router 被重复登记，路由匹配顺序约定失效: {duplicated}"
    assert len(ALL_ROUTERS) == len(set(registered_ids)), "ALL_ROUTERS 存在重复条目"


def test_openapi_description_langgraph_node_count_matches_graph():
    """对外 OpenAPI 描述宣称的 LangGraph 节点数必须等于图中真实节点数。

    该 description 会原样出现在 /docs 与 openapi.json（对外契约），
    写错不报任何错，只能靠这条不变量发现。
    2026-09-28 审查实测：描述曾长期写「10 节点」，而 agents/graph.py 真值为 11。
    """
    import re

    from agents.graph import create_agent_graph
    from main import app

    # 编译图里 __start__ 是框架虚拟节点，不计入业务节点
    compiled = create_agent_graph()
    real = len([n for n in compiled.nodes if not n.startswith("__")])

    desc = app.description or ""
    m = re.search(r"(\d+)\s*节点\s*LangGraph", desc)
    assert m, f"OpenAPI 描述未声明 LangGraph 节点数，对外口径失锚: {desc[:80]!r}"
    assert int(m.group(1)) == real, (
        f"对外宣称 {m.group(1)} 节点，而 agents/graph.py 真值为 {real} 节点"
    )


def test_openapi_description_auth_coverage_matches_recomputation():
    """对外 OpenAPI 描述宣称的认证覆盖率必须等于从真实路由表重算的值。

    该 description 会原样出现在 /docs 与 openapi.json（对外契约），写错不报任何错。

    2026-09-28 审查实测：对外长期宣称「97.8%」，实测仅 93.42%（227/243）。
    97.8% 的唯一出处是 2026-07-10 的一次性审计快照（87/89），此后路由一直在变
    而无人重算 —— 对外数字比真实值高。收紧 literacy 三个数据端点后重算为
    94.65%（230/243）。

    **真值算法的唯一来源是 scripts/verify_auth_coverage.py**：本测试直接复用它，
    不在此另写第二套判定逻辑 —— 否则两套口径迟早会再次分叉。

    ── 2026-09-29 CI 失败的真实根因（更正此前一次误判）────────────────────
    现象：CI 报「宣称 94.65%，重算为 0.0%（0/2）」，本地单独跑却是 230/243=94.65%。
    我最初误判为「pytest 顺序依赖/sys.modules 污染」（该判断**是错的**，见下）。

    实证后的真因是 **fastapi 版本不兼容**：
      - 本地 fastapi 0.136.3：include_router 把子路由**拍平**进 app.routes，条目是 APIRoute。
      - CI fastapi 0.141.1：include_router 只在 app.routes 放一个 **_IncludedRouter 包装对象**，
        实测类型分布 `{'Route':4, '_IncludedRouter':1, 'APIRoute':2}`，真实子路由藏在其中。
      于是「只按 APIRoute 平铺枚举」的旧写法只数到直接装饰器挂的 2 条
      （/api/status、/api/status/competition），include_router 挂的 228 条全被漏掉
      → 覆盖率被算成 0/2。**不是路由表变了，是枚举方式在新版快速失效。**

    验证方式（可复现）：在真实 0.141.1 下构造同构 app（含 include_router + 直接装饰器），
      老写法命中 2 条（复现 CI 的「2」），改用官方展开器 fastapi.routing.iter_route_contexts
      后命中 4 条且与 openapi schema 完全一致。修法已落在 verify_auth_coverage.py。

    本测试据此增加一个**独立来源交叉核对**（OpenAPI schema），用于长期防同类回归：
    它不依赖任何路由枚举实现细节，一旦将来 fastapi 再改路由组织方式导致 collect()
    漏采，这里会立刻报错并指明是「枚举失效」而非「覆盖率真的下降」。
    """
    import importlib.util
    import os
    import re
    import sys

    script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts",
        "verify_auth_coverage.py",
    )
    spec = importlib.util.spec_from_file_location("_verify_auth_coverage", script)
    cov = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cov)

    protected, public = cov.collect()
    total = len(protected) + len(public)

    # 与 collect() 复用同一模块对象：collect() 内 `import main` 会把模块放进 sys.modules，
    # 此处直接取它，保证「算覆盖率用的 app」与「读 description 用的 app」是同一实例。
    main_mod = sys.modules.get("main")
    assert main_mod is not None and getattr(main_mod, "app", None) is not None, (
        "collect() 执行后 sys.modules['main'].app 不可用 —— 环境引导未完成。"
    )
    app = main_mod.app

    # ── 独立来源交叉核对：OpenAPI schema ──
    # schema 由 fastapi 自己从路由表生成，不经过 collect() 的枚举实现；
    # 它天然包含 include_router 挂上的路由（且带完整 prefix），故适合做「漏采」探测器。
    # 与 collect() 的关系：collect() 统计所有 /api APIRoute（含 include_in_schema=False），
    # schema 只含 include_in_schema=True 的子集 → 正确时必有 schema ⊆ collect。
    # 实测（本地 0.136.3）：collect 243 条 / schema 226 条，schema 是 collect 的真子集。
    schema = app.openapi() or {}
    schema_api_paths = {
        p for p in (schema.get("paths") or {}) if p.startswith("/api")
    }
    collected_paths = {i["path"] for i in (protected + public)}
    missing = schema_api_paths - collected_paths
    assert not missing, (
        f"collect() 漏采了 {len(missing)} 条 OpenAPI 已登记的路由（样例 "
        f"{sorted(missing)[:5]}）—— 典型的「路由枚举方式失效」而非覆盖率下降："
        " 多因 fastapi 版本变更后 include_router 的路由不再平铺在 app.routes 里。"
        " 请检查 scripts/verify_auth_coverage.py::_iter_api_route_entries 的版本适配分支。"
        f" （实测 collect={len(collected_paths)} 条 / schema={len(schema_api_paths)} 条）"
    )
    assert total, "未采集到任何 /api 端点，覆盖率判定口径可能已失效"

    measured = round(len(protected) / total * 100, 2)

    desc = app.description or ""
    m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*API\s*认证覆盖率", desc)
    assert m, f"OpenAPI 描述未按「X% API 认证覆盖率」声明覆盖率，对外口径失锚: {desc[-150:]!r}"

    claimed = round(float(m.group(1)), 2)
    assert claimed == measured, (
        f"对外宣称认证覆盖率 {claimed}%，而从真实路由表重算为 {measured}%"
        f"（{len(protected)}/{total}）—— 请跑 scripts/verify_auth_coverage.py 复核并同步文案"
    )


def test_head_status_endpoint_supported():
    """HEAD /api/status 必须可用（HTTP 语义：GET 可用处 HEAD 亦应可用）。

    此前 FastAPI 路由只挂 GET → HEAD 返回 405（allow: GET），只发 HEAD 探活的下游会
    把「服务正常」误判为不可用（如部分 PaaS/LB 的健康检查）。
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.status import install

    app = FastAPI()
    install(app)
    client = TestClient(app)

    resp = client.head("/api/status")
    assert resp.status_code == 200
    assert resp.headers.get("content-length") is not None, "HEAD 响应应带 content-length"
    assert resp.content == b"", "HEAD 响应不得带 body"


# ── 不变量 6：status.py 读取的 vector_db 属性必须真实存在 ──────────────────


def test_status_probe_reads_real_vector_db_attrs():
    """status.py 通过 getattr 读的每个 vector_db 属性，必须在真实单例上存在。

    ``getattr(obj, name, default)`` 的默认值会把「读取方与实现方命名漂移」**静默**吞掉：
    读不到就用默认值，不报错、不告警，探针于是常年上报一个从未被赋过值的数。

    2026-10-18 实证缺陷：``app/status.py`` 按公开名读
    ``embedding_fallback_count``，而 ``db/milvus_client.py`` 只赋值私有字段
    ``_embedding_fallback_count``（D5 §2.1 设计的只读属性漏做了）⇒
    ``fallback_zero_docs`` 恒为 0，「embedding 降级」判定永不触发，
    ``/api/status`` 在 2245 条文档全是零向量占位时照样报 ``status:"ok"``。
    更隐蔽的是：本文件顶部的 ``_BoomVectorDb`` 替身桩恰好也用的公开名，
    测试与实现同错，所以这条链路长期绿灯。

    本测试把契约钉住：status.py 改读取名、或 VectorDB 改字段名，这里立刻红。
    """
    import inspect
    import re

    from db.milvus_client import vector_db

    src = inspect.getsource(status_mod.status)
    names = re.findall(r'getattr\(\s*vector_db\s*,\s*["\']([^"\']+)["\']', src)
    assert names, (
        "status.py 未按 getattr(vector_db, \"NAME\", default) 读取向量库属性 —— "
        "本守护的提取正则已失效，请先更新它再改 status.py"
    )

    missing = [n for n in names if not hasattr(vector_db, n)]
    assert not missing, (
        f"status.py 读取的 vector_db 属性在真实单例上不存在: {missing} —— "
        "getattr 的默认值会静默生效，探针将常年上报假值"
        "（2026-10-18：embedding_fallback_count 就因私有/公开名不一致漏实现）"
    )


@pytest.mark.asyncio
async def test_embedding_fallback_counter_reaches_status_probe(monkeypatch):
    """E5 失败写零向量占位时，计数器必须自增，且 /api/status 如实上报。

    端到端覆盖 ``db/milvus_client.py::_mem_insert`` 的**两处** fallback_zero 赋值点：

    A. 整批无 embedding → 调 ``embed_batch`` 失败 → 全批零向量占位；
    B. 批量里个别 ``embedding`` 为 None → 不重算，直接零向量占位。
       （B 处曾在 2026-09-23 落地时漏记计数，2026-10-18 按 D5 §2.1「两处各 +1」补齐。）

    断言一路打到 ``/api/status`` 的 ``fallback_zero_docs`` 与 ``degraded_reasons``，
    证明的不只是「计数器自增」，而是「运维面真的看得见」。
    """
    from db import embedder as embedder_mod
    from db.milvus_client import vector_db

    dim = int(embedder_mod.get_embedding_config().get("dimension", 768))
    coll = "netlearn_kb"

    class _FakeMemStore:
        """替身：只记账，绝不碰磁盘上的真实 vectordb_data。"""

        def __init__(self):
            self.n = 0

        def add(self, coll_name, ids=None, texts=None, metas=None, embeddings=None, save=True):
            self.n += len(texts or [])

        def count(self, coll_name):
            return self.n

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated E5 outage")

    # 隔离单例运行态：不走 Milvus、不落盘、计数器归零
    monkeypatch.setattr(vector_db, "_milvus_connected", False)
    monkeypatch.setattr(vector_db, "_mem_store", _FakeMemStore())
    monkeypatch.setattr(vector_db, "_embedding_fallback_count", 0)
    monkeypatch.setattr(embedder_mod, "embed_batch", _boom)

    # A. 整批无 embedding → embed_batch 炸 → 全批零向量占位（计数 0 → 1）
    n_a = vector_db._mem_insert(coll, [{"id": "a1", "text": "t1", "metadata": {}}])
    assert n_a == 1
    assert vector_db.embedding_fallback_count == 1, "整批兜底必须计数"

    # B. 批量里个别 embedding 为 None → 同样必须计数（计数 1 → 2；b1 有真向量不计数）
    n_b = vector_db._mem_insert(
        coll,
        [
            {"id": "b1", "text": "t2", "metadata": {}, "embedding": [0.5] * dim},
            {"id": "b2", "text": "t3", "metadata": {}, "embedding": None},
        ],
    )
    assert n_b == 2
    assert vector_db.embedding_fallback_count == 2, (
        "个别 embedding 为 None 的文档也必须计入 fallback 计数（D5 §2.1「两处各 +1」）"
    )

    payload = await status_mod.status()
    assert payload["health"]["embedding"]["fallback_zero_docs"] == 2, payload["health"]["embedding"]
    assert payload["status"] == "degraded"
    assert any(
        "零向量占位" in r for r in payload["degraded_reasons"]
    ), payload["degraded_reasons"]
