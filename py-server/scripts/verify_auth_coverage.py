# -*- coding: utf-8 -*-
"""
认证覆盖率机验 — 从真实路由表重算，杜绝传抄
============================================
背景
----
对外材料里长期宣称「97.8% API 认证覆盖率」，其唯一出处是
documents/项目全面审查与架构剖析_2026-07-10.md 的一次性审计快照
（87/89）。路由表此后已变动，该数字**没有任何机制保证仍然成立**。

本脚本把该数字变成可复现产物：直接读运行时的 app.routes，
逐个判定是否挂了鉴权依赖，输出 coverage = protected / (protected + public)。

判定口径
--------
- 只统计 /api 前缀下的 APIRoute（非 /api 的挂载点/文档路由不算 API 面）。
- 受保护：依赖树中出现下列任一函数即视为需鉴权：
    get_current_user / require_admin / require_teacher
    / require_teacher_or_demo_open / require_llm_quota
- 公开：未挂上述依赖，且**必须**在 PUBLIC_ALLOWLIST 中显式登记理由；
  出现未登记的公开端点 → 退出码 1（防止新接口漏挂鉴权而无人发现）。

现状（2026-09-28 重算，作为对外数字的唯一来源）
------------------------------------------------
  /api 端点总数 243 / 受保护 230 / 公开 13 → **认证覆盖率 94.65%**
  当日收紧 literacy 三个数据端点（submit / report / class-report）后，
  受保护数由 227 增至 230；未登记公开端点由 12 降至 8
  （12→9 由收紧上述三端点所致；9→8 由把已核验的 /api/literacy/questions 登记进白名单所致）。
  对外文案（py-server/main.py 的 OpenAPI description、src/views/ShowcaseView.vue、
  tools/generate_demo_ppt.py）已同步为该实测值，并在 main.py 中加了断言锁死，
  防止再次出现「对外数字与代码真值脱钩」。
  注意：97.8% 曾是 2026-07-10 一次性审计快照（87/89），此后路由一直变动而无人重算。

用法
----
  python scripts/verify_auth_coverage.py
  python scripts/verify_auth_coverage.py --json out.json
"""

import argparse
import json
import os
import sys

_PY_SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PY_SERVER_DIR not in sys.path:
    sys.path.insert(0, _PY_SERVER_DIR)

from fastapi.routing import APIRoute  # noqa: E402

# 视为「需鉴权」的依赖函数名（按现网实际使用的鉴权入口列举）
AUTH_DEP_NAMES = {
    "get_current_user",
    "require_admin",
    "require_teacher",
    "require_teacher_or_demo_open",
    "require_llm_quota",
    "require_auth",
}

# 公开端点白名单：路径 → 公开理由。
# 只允许「设计上必须公开」的端点；新增条目必须在审查中说明理由。
#
# 登记纪律（2026-09-28）：只登记**已逐一核验过实现**的端点。
# 为了让退出码变 0 而把未核验的端点批量登记，等于把门禁调松 —— 那正是本脚本
# 存在的意义所在。
# 2026-10-01：benchmark / experiments / cn-distinction 共 8 个端点已逐一阅读
# 实现并核验为「只读 / 纯计算、不含学生数据、无写入、无副作用」，据此登记
# 理由（见下）。此后新增公开端点仍按同一纪律：先核验实现，再补理由。
PUBLIC_ALLOWLIST = {
    "/api/auth/login": "登录入口，用户尚未持有凭据",
    "/api/auth/register": "注册入口，用户尚未持有凭据（另有速率限制）",
    "/api/status": "运维健康探针，供编排系统免凭据探活",
    "/api/status/competition": "运维状态面",
    "/api/literacy/questions": (
        "素养测评题库只读端点：不含任何学生数据、不产生写入；"
        "学生答题页必须在取到题目时才可用（已核验实现，2026-09-28）"
    ),
    # ── 2026-10-01 逐项核验后登记（benchmark / experiments / cn-distinction）──
    # 核验方式：逐一阅读实现，确认「只读 / 纯计算、不含学生数据、无写入、无副作用」，
    # 其中 experiments 详情端点另带 _safe_name 路径穿越防护与 sha256 溯源。
    "/api/benchmark/results": (
        "真实评测产物只读暴露（证据护城河）：返回静态 JSON + provenance，"
        "不含学生数据、无写入（已核验实现，2026-10-01）"
    ),
    "/api/benchmark/results/per-question": (
        "experiment2 逐题明细只读暴露，同上：只读、无学生数据、无写入"
        "（已核验实现，2026-10-01）"
    ),
    "/api/experiments": (
        "真实实验产物画廊只读列表（证据链可溯源）：仅列元信息，不含学生数据、"
        "无写入（已核验实现，2026-10-01）"
    ),
    "/api/experiments/{name}": (
        "单份真实产物只读 + sha256 溯源，含 _safe_name 路径穿越防护；"
        "只读、无学生数据、无写入（已核验实现，2026-10-01）"
    ),
    "/api/cn-distinction": (
        "计网易混概念对只读列表（不含自测题答案），不含学生数据、无写入"
        "（已核验实现，2026-10-01）"
    ),
    "/api/cn-distinction/{pid}": (
        "单概念对只读详情（不含自测题答案），不含学生数据、无写入"
        "（已核验实现，2026-10-01）"
    ),
    "/api/cn-distinction/quiz/random": (
        "随机自测题只读抽取（不含答案），无状态、不含学生数据"
        "（已核验实现，2026-10-01）"
    ),
    "/api/cn-distinction/quiz/answer": (
        "确定性关键词判分：纯计算无副作用——不写库、不依赖 LLM、不持久化，"
        "可复现（已核验实现，2026-10-01）"
    ),
}


def _iter_dep_calls(dependant, seen=None):
    """递归展开依赖树，产出所有被调用依赖的可调用对象。"""
    if seen is None:
        seen = set()
    for sub in getattr(dependant, "dependencies", []) or []:
        call = getattr(sub, "call", None)
        if call is not None and id(call) not in seen:
            seen.add(id(call))
            yield call
        yield from _iter_dep_calls(sub, seen)


def _is_protected(route) -> bool:
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return False
    return any(
        getattr(call, "__name__", "") in AUTH_DEP_NAMES
        for call in _iter_dep_calls(dependant)
    )


def iter_route_entries(app, only_api: bool = False, endpoints_only: bool = False):
    """跨 fastapi 版本枚举路由条目（元素兼容 APIRoute 与 RouteContext）。

    为什么必须做版本适配（2026-09-29 实锤，含 fastapi 0.141.1 对照实验）：

      旧版本（本地 0.136.3）：include_router 会把子路由**拍平**进 app.routes，
        每个条目就是 APIRoute，`isinstance(r, APIRoute)` 能数全。
      新版本（CI 解析到的 0.141.1）：include_router 只在 app.routes 里放一个
        **_IncludedRouter 包装对象**，真实子路由藏在它内部 ——
        实测 app.routes 类型分布 `{'Route': 4, '_IncludedRouter': 1, 'APIRoute': 2}`，
        包装对象**既不是 APIRoute，也不保证有 .path 属性**。

      后果：只按 APIRoute 平铺枚举时，include_router 挂上的业务路由被**整体漏掉**，
      只剩直接装饰器挂的 2 条（/api/status、/api/status/competition）→ 覆盖率被算成
      0.0%（0/2），而真实值是 94.65%（230/243）。这正是 CI 上
      「对外宣称 94.65%，重算为 0.0%（0/2）」的根因 —— 不是路由表变了，
      是**枚举方式在新版 fastapi 下失效**。

      0.141.1 起官方提供展开器 `fastapi.routing.iter_route_contexts`：产出 RouteContext，
        `.path` 已含 router prefix，`.methods` / `.dependant` 经 __getattr__ 透传底层路由，
        故 `_is_protected()` 无需改动即可继续按依赖树判定鉴权。

    兼容策略：有 iter_route_contexts 就用它（新版）；没有则回退到平铺分支（旧版）。
    两条分支都**只认带 str 型 .path 的条目**，避免再对不保证该属性的对象取属性。

    Args:
        app: FastAPI 实例。
        only_api: True 时只保留 path 以 "/api" 开头的条目。
        endpoints_only: True 时只保留**端点**（有 .methods 的 Route/APIRoute），
            排除 Mount 等非端点条目 —— 供「业务路由是否真的注册」这类计数使用。
    """
    try:
        from fastapi.routing import iter_route_contexts  # noqa: PLC0415
    except ImportError:
        iter_route_contexts = None

    entries = []
    candidates = iter_route_contexts(app.routes) if iter_route_contexts else app.routes

    for route in candidates:
        if iter_route_contexts is None and not isinstance(route, APIRoute):
            continue  # 旧版平铺分支：Mount / 文档路由不计入 API 面
        path = getattr(route, "path", None)
        if not isinstance(path, str):
            continue
        if only_api and not path.startswith("/api"):
            continue
        if endpoints_only and not getattr(route, "methods", None):
            continue
        entries.append(route)
    return entries


def _iter_api_route_entries(app):
    """/api 路由条目（collect() 专用入口，语义见 iter_route_entries）。"""
    return iter_route_entries(app, only_api=True)


def collect():
    import main  # noqa: PLC0415 —— 需先设好 sys.path，且 import 会执行环境引导

    protected, public = [], []
    for route in _iter_api_route_entries(main.app):
        methods = getattr(route, "methods", None) or set()
        item = {"path": route.path, "methods": sorted(methods - {"HEAD", "OPTIONS"})}
        (protected if _is_protected(route) else public).append(item)
    return protected, public


def main_cli() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_out", default=None, help="落盘机器可读结果")
    args = ap.parse_args()

    protected, public = collect()
    total = len(protected) + len(public)

    unknown = [p for p in public if p["path"] not in PUBLIC_ALLOWLIST]

    print("=" * 68)
    print(f"/api 端点总数: {total}")
    print(f"  受鉴权保护: {len(protected)}")
    print(f"  设计上公开: {len(public)}")
    if total:
        # 保留两位小数并与 JSON 输出一致：两个表示法不同会让「对外数字」再生二义。
        # 同时带上分数，使任何舍入都可被读者自行验算。
        print(f"认证覆盖率: {len(protected) / total * 100:.2f}% ({len(protected)}/{total})")
    print("=" * 68)
    if public:
        print("\n[公开端点]")
        for p in sorted(public, key=lambda x: x["path"]):
            reason = PUBLIC_ALLOWLIST.get(p["path"], "⚠️ 未登记理由")
            print(f"  {p['path']:46s} {reason}")
    if unknown:
        print(f"\n[❌ 未登记的公开端点 {len(unknown)} 个] —— 新接口漏挂鉴权或需补白名单理由：")
        for p in unknown:
            print(f"  {p['path']}")

    result = {
        "total": total,
        "protected": len(protected),
        "public": len(public),
        "coverage_pct": round(len(protected) / total * 100, 2) if total else 0.0,
        "public_paths": sorted(p["path"] for p in public),
        "unregistered_public": sorted(p["path"] for p in unknown),
    }
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        print(f"\n结果已落盘: {args.json_out}")

    print(
        f"\n__SUMMARY__ total={total} protected={len(protected)} "
        f"public={len(public)} coverage={result['coverage_pct']} "
        f"unregistered={len(unknown)}"
    )
    return 1 if unknown else 0


if __name__ == "__main__":
    sys.exit(main_cli())
