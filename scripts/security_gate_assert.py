#!/usr/bin/env python3
"""MARS-408 / study-help-pro — CI 安全门禁 AST 断言 (G2 / G5 / G7 / G9)。

承载 deliverables/gstack/security-gate-checklist.md §1 中 type=c 的强化断言：
  G2  限流 fail-closed（prod 拒绝）
  G5  AUTH_SECRET 生产缺失 fail-fast
  G7  demo 种子仅非生产
  G9  C3 workers>1 fail-fast（ADR-007 单写者约束）

设计：纯 ast 静态解析，不依赖依赖树安装；任一断言失败即抛 AssertionError
-> 非零退出 -> CI 门禁阻断合并。禁止 --warn-only 绕过。

路径相对仓库根；CI 在仓库根目录调用 `python scripts/security_gate_assert.py`。
"""
from __future__ import annotations

import ast
import sys


def _load(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def assert_g2_rate_limit_fail_closed() -> None:
    """G2: redis_client.check_rate_limit 在生产(REDIS_STRICT)下 fail-closed 返回 False。"""
    tree = ast.parse(_load("py-server/db/redis_client.py"))
    dump = ast.dump(tree)
    assert "REDIS_STRICT" in dump, "G2 REDIS_STRICT 逻辑被移除"
    fns = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "check_rate_limit"
    ]
    assert fns, "G2 check_rate_limit 被移除"
    returns_false = any(
        isinstance(n, ast.Return) and getattr(n.value, "value", None) is False
        for n in ast.walk(fns[0])
    )
    assert returns_false, "G2 check_rate_limit 缺少 fail-closed 的 return False"


def assert_g5_auth_secret_fail_fast() -> None:
    """G5: auth.py 生产缺失 AUTH_SECRET 即 raise RuntimeError。"""
    tree = ast.parse(_load("py-server/shared/auth.py"))
    raises = [n for n in ast.walk(tree) if isinstance(n, ast.Raise)]
    assert raises, "G5 auth.py 无 raise"
    assert any(
        "RuntimeError" in ast.dump(n) for n in raises
    ), "G5 缺少 production 下的 RuntimeError"
    assert "AUTH_SECRET" in ast.dump(tree), "G5 auth.py 缺少 AUTH_SECRET 引用"


def assert_g7_demo_non_production() -> None:
    """G7: seed_demo_data 仅当 env not in ('production','prod') 时执行。"""
    src = _load("py-server/main.py")
    tree = ast.parse(src)
    assert "production" in src and "prod" in src, "G7 缺少 production/prod 环境判断"
    assert "seed_demo_data" in src, "G7 缺少 seed_demo_data 调用"
    assert (
        'not in ("production", "prod")' in src
        or "not in ('production', 'prod')" in src
    ), "G7 demo 种子未被 not in (production,prod) 守卫"


def assert_g9_workers_gt1_fail_fast() -> None:
    """G9: UVICORN_WORKERS/WEB_CONCURRENCY > 1 时 raise RuntimeError（ADR-007 单写者）。"""
    src = _load("py-server/main.py")
    assert (
        "UVICORN_WORKERS" in src and "WEB_CONCURRENCY" in src
    ), "G9 缺少 UVICORN_WORKERS/WEB_CONCURRENCY 判定"
    assert "> 1" in src, "G9 缺少 workers > 1 的比较"
    assert any(
        isinstance(n, ast.Raise) for n in ast.walk(ast.parse(src))
    ), "G9 缺少 raise（workers>1 未 fail-fast）"


def main() -> int:
    assert_g2_rate_limit_fail_closed()
    assert_g5_auth_secret_fail_fast()
    assert_g7_demo_non_production()
    assert_g9_workers_gt1_fail_fast()
    print("SECURITY AST ASSERTIONS PASSED (G2/G5/G7/G9)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
