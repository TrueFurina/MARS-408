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
PUBLIC_ALLOWLIST = {
    "/api/auth/login": "登录入口，用户尚未持有凭据",
    "/api/auth/register": "注册入口，用户尚未持有凭据（另有速率限制）",
    "/api/status": "运维健康探针，供编排系统免凭据探活",
    "/api/status/competition": "运维状态面",
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


def collect():
    import main  # noqa: PLC0415 —— 需先设好 sys.path，且 import 会执行环境引导

    protected, public = [], []
    for route in main.app.routes:
        if not isinstance(route, APIRoute):
            continue  # Mount / 文档路由不计入 API 面
        path = route.path
        if not path.startswith("/api"):
            continue
        item = {"path": path, "methods": sorted(route.methods - {"HEAD", "OPTIONS"})}
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
        print(f"认证覆盖率: {len(protected) / total * 100:.1f}%")
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
