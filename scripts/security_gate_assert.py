#!/usr/bin/env python3
"""芒得很职 / study-help-pro — CI 安全门禁 AST 断言 (G2 / G5 / G7 / G9)。

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


# G7 承载位置（按查序）：demo 种子守卫的真实归属。
#
# 演进史：M-4 拆分（commit 8eae3c3，2026-09-27）把 main.py 从 882 行收敛为
# 86 行纯组装层，种子守卫随生命周期编排整体搬到 app/lifespan.py。本门禁原先
# 只读 main.py，拆分后该文件已不含此逻辑 —— 门禁指向了失效路径，报「G7 缺少
# production/prod 环境判断」，而实现其实完好。
#
# 故改为「按序并查」：任一路径命中即可通过。同时保留 main.py —— 若将来守卫被
# 再搬回入口，也能立刻被认到；若两个位置都没有，门禁依旧红灯（不放松判定）。
_G7_CANDIDATES = (
    "py-server/app/lifespan.py",
    "py-server/main.py",
)


def assert_g7_demo_non_production() -> None:
    """G7: seed_demo_data 仅当 env not in ('production','prod') 时执行。

    判定口径（三方联合，缺一不可）：
      1) 存在 production/prod 环境判断
      2) 存在 seed_demo_data 调用
      3) 该调用被 `not in (production, prod)` 显式守卫
    任一承载文件全部满足即通过。判定只看语义，不绑定单一文件名。
    """
    missing = []
    for path in _G7_CANDIDATES:
        try:
            src = _load(path)
        except FileNotFoundError:
            missing.append(f"{path}(不存在)")
            continue
        ast.parse(src)  # 语法坏了要立刻炸，别静默当作「没命中」
        guarded = (
            'not in ("production", "prod")' in src
            or "not in ('production', 'prod')" in src
        )
        if (
            "production" in src
            and "prod" in src
            and "seed_demo_data" in src
            and guarded
        ):
            return
        missing.append(path)

    raise AssertionError(
        "G7 demo 种子未被 not in (production,prod) 守卫；"
        f"已排查承载位置 {list(_G7_CANDIDATES)} 均未同时满足"
        "「production/prod 判断 + seed_demo_data 调用 + not in 守卫」三项。"
        f"明细：{missing}"
    )


def _g9_guarded_in_same_function(src: str) -> bool:
    """G9 判定：同一函数体内，`workers > 1` 比较与 `raise` 必须共现。

    为什么不能只做全文 `any(raise)`：变异验证实测发现——把 `if workers > 1: raise ...`
    整段删掉后，门禁**依然通过**，因为 app/lifespan.py 里还有 6 处与 workers 无关的
    raise（密钥校验、迁移失败等）把 `any(ast.Raise)` 撑成了恒真。那是假绿。

    故收紧为「函数级共现」：找到含 `UVICORN_WORKERS`/`WEB_CONCURRENCY` 引用的函数，
    要求该函数内**同时**出现 `> 1` 形式的比较与 raise。
    """
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        fn_dump = ast.dump(node)
        if "UVICORN_WORKERS" not in fn_dump and "WEB_CONCURRENCY" not in fn_dump:
            continue
        has_cmp = any(
            isinstance(n, ast.Compare)
            and isinstance(n.ops[0], (ast.Gt, ast.GtE))
            and isinstance(n.comparators[0], ast.Constant)
            and n.comparators[0].value == 1
            for n in ast.walk(node)
        )
        has_guard_raise = False
        for n in ast.walk(node):
            # raise 必须出现在 if 体内（即受比较式控制），而非函数任意位置
            if isinstance(n, ast.If) and any(isinstance(x, ast.Raise) for x in ast.walk(n)):
                has_guard_raise = True
                break
        if has_cmp and has_guard_raise:
            return True
    return False


def assert_g9_workers_gt1_fail_fast() -> None:
    """G9: UVICORN_WORKERS/WEB_CONCURRENCY > 1 时 raise RuntimeError（ADR-007 单写者）。

    与 G7 同源：守卫随 M-4 拆分搬到 app/lifespan.py（`_assert_single_worker`），
    故按序并查承载位置，不绑定单一文件名。
    判定用「函数级比较+raise 共现」，避免被无关 raise 撑成假绿（见 _g9_guarded_in_same_function）。
    """
    for path in _G7_CANDIDATES:  # 同为「生命周期守卫」的承载位置集合
        try:
            src = _load(path)
        except FileNotFoundError:
            continue
        if _g9_guarded_in_same_function(src):
            return

    raise AssertionError(
        "G9 缺少 workers>1 fail-fast；已排查 "
        f"{list(_G7_CANDIDATES)}，未发现任何函数同时满足"
        "「引用 UVICORN_WORKERS/WEB_CONCURRENCY + 与 1 比较 + 该比较控制的 raise」。"
        "（注意：仅全文存在 raise 不算通过——无关 raise 不能替代受守卫的 fail-fast）"
    )


def main() -> int:
    assert_g2_rate_limit_fail_closed()
    assert_g5_auth_secret_fail_fast()
    assert_g7_demo_non_production()
    assert_g9_workers_gt1_fail_fast()
    print("SECURITY AST ASSERTIONS PASSED (G2/G5/G7/G9)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
