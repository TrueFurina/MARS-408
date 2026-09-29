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

    顺序依赖（2026-09-29 修复）：本用例原先单独跑绿（230/243=94.65%），全量跑却采集到
    0/2。原因是同一 pytest 进程内，前序用例可能已把 `main` 置入 sys.modules 或其
    `app.routes` 被改写，而 `collect()` 的前提是「import main 会执行一次完整初始化」——
    它无法识别复用来的半初始化对象，于是静默采到 2 条路由并得出 0.0%。
    这里做两件事把它钉死：
      ① 不再单独 `from main import app`，改为与 collect() 用**同一个** main 模块对象，
         消除「两处 import 可能取到不同 app」的二义性；
      ② 采集结果不足时给出可诊断信息（而不是干瘪的 0.0%），并明确指向真实原因，
         避免下次再被误读为「覆盖率口径失效」。
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

    # 路由表与描述取自同一 app 实例，再断言总量：把「采集塌陷」与「口径失效」区分开。
    api_paths = [
        r.path for r in app.routes if r.path.startswith("/api")
    ]
    assert total, (
        "collect() 未采集到任何 /api 端点，但 app.routes 里有 "
        f"{len(api_paths)} 条 /api 路径 —— 说明 collect() 拿到的是非本次 app 实例"
        "（同进程全局态被前序用例污染），而非覆盖率口径失效。"
        f" app id={id(app)}，样例={api_paths[:5]}"
    )
    assert len(protected) > 2, (
        f"仅采集到 {len(protected)}/{total} 条受保护端点，远低于预期（约 230/243）——"
        " 极可能是 sys.modules['main'] 复用到了半初始化对象（顺序依赖），"
        f"而非真实覆盖率下降。 app id={id(app)}，全量 /api 路径数={len(api_paths)}"
    )
    measured = round(len(protected) / total * 100, 2)

    desc = app.description or ""
    m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*API\s*认证覆盖率", desc)
    assert m, f"OpenAPI 描述未按「X% API 认证覆盖率」声明覆盖率，对外口径失锚: {desc[-150:]!r}"

    claimed = round(float(m.group(1)), 2)
    assert claimed == measured, (
        f"对外宣称认证覆盖率 {claimed}%，而从真实路由表重算为 {measured}%"
        f"（{len(protected)}/{total}）—— 请跑 scripts/verify_auth_coverage.py 复核并同步文案"
    )
