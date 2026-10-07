#!/usr/bin/env python3
"""芒得很职 / study-help-pro — CI 安全门禁 AST 断言 (G2 / G5 / G7 / G9)。

承载 deliverables/gstack/security-gate-checklist.md §1 中 type=c 的强化断言：
  G2  限流 fail-closed（prod 拒绝）
  G5  AUTH_SECRET 生产缺失 fail-fast
  G7  demo 种子仅非生产
  G9  C3 workers>1 fail-fast（ADR-007 单写者约束）
  G11 SVG 注入转义（html.escape 的**实际调用**，非字符串存在性）

设计：纯 ast 静态解析，不依赖依赖树安装；任一断言失败即抛 AssertionError
-> 非零退出 -> CI 门禁阻断合并。禁止 --warn-only 绕过。

路径相对仓库根；CI 在仓库根目录调用 `python scripts/security_gate_assert.py`。

## 判定口径：守卫链共现（2026-10-08 收紧）

四道断言统一使用「**守卫链共现**」：不仅要求目标语句存在，还要求它**受正确的条件
守卫控制**。即从函数根到该语句的 `if` 条件链（`_guard_chains`）中，必须出现语义
所需的条件。

背景：本文件原先对 G2/G5 只做**全文级存在性**检查（`any(Raise)` / 任意位置
`return False`），实测可被**变异绕过**——把真正的守卫整段删掉后，门禁**照旧通过**，
因为文件里别处还有与安全无关的 `raise` / `return False` 把判定撑成了恒真。这是
「假绿」（ghost green）：门禁看起来在守，实际什么都没守。

G9 曾在 2026-09 因同一原因被单独收紧（见其 docstring 的变异验证记录），但 G2/G5
当时漏改。2026-10-08 复测确认两者仍可被绕过（变异后退出码 0），故本次统一改用
`_guard_chains`，四道断言同一套判据。

**口径后果（有意为之，宁严勿松）**：若把判定条件改写成门禁认不出等价形式
（例如把 `REDIS_STRICT` 先用别名变量接住、或把守卫条件挪进被调函数），门禁会
**变红**。这是刻意的——门禁无法证明语义等价时应当拦人复核，而不是默认放行。
"""
from __future__ import annotations

import ast
import sys


def _load(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _guard_chains(fn: ast.AST) -> list[tuple[ast.stmt, list[ast.expr]]]:
    """返回 `[(语句, 从函数根到该语句的 if 条件链), ...]`。

    - 下钻 `if/else`、`try/except/else/finally`、`for/while`、`with` 的**语句块**，
      把遇到的条件累积进链（`try` 等不贡献条件，但继续下钻以覆盖 try 内的守卫）。
    - **不进入嵌套函数 / 类体**：内层作用域的守卫与外层无关，不能互相顶替。
    - 只产出「叶子语句」（含 `raise` / `return` / 调用表达式的语句）。
    """
    out: list[tuple[ast.stmt, list[ast.expr]]] = []

    def walk(stmts: list[ast.stmt], conds: list[ast.expr]) -> None:
        for st in stmts:
            if isinstance(st, ast.If):
                walk(st.body, [*conds, st.test])
                walk(st.orelse, conds)
            elif isinstance(st, ast.Try):
                walk(st.body, conds)
                for handler in st.handlers:
                    walk(handler.body, conds)
                walk(st.orelse, conds)
                walk(st.finalbody, conds)
            elif isinstance(st, (ast.For, ast.AsyncFor, ast.While)):
                walk(st.body, conds)
                walk(st.orelse, conds)
            elif isinstance(st, (ast.With, ast.AsyncWith)):
                walk(st.body, conds)
            elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            else:
                out.append((st, conds))

    body = getattr(fn, "body", None)
    if body:
        walk(body, [])
    return out


def _conds_dump(conds: list[ast.expr]) -> str:
    return " ".join(ast.dump(c) for c in conds)


def _iter_functions(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def assert_g2_rate_limit_fail_closed() -> None:
    """G2: redis_client.check_rate_limit 在生产(REDIS_STRICT)下 fail-closed 返回 False。

    判定：存在 `return False`，其守卫链含 `REDIS_STRICT`。
    （仅「文件里某处有 return False」不算——超限分支 `count >= max_requests` 也返回
    False，但它与 Redis 故障无关，不能顶替 fail-closed 路径。）
    """
    tree = ast.parse(_load("py-server/db/redis_client.py"))
    assert "REDIS_STRICT" in ast.dump(tree), "G2 REDIS_STRICT 逻辑被移除"
    fns = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "check_rate_limit"
    ]
    assert fns, "G2 check_rate_limit 被移除"

    for stmt, conds in _guard_chains(fns[0]):
        if "REDIS_STRICT" not in _conds_dump(conds):
            continue
        for node in ast.walk(stmt):
            # 形式一：`return False`
            if isinstance(node, ast.Return) and getattr(node.value, "value", None) is False:
                return
            # 形式二：三元 `return False if REDIS_STRICT else True`
            if isinstance(node, ast.IfExp) and getattr(node.body, "value", None) is False:
                return
            if isinstance(node, ast.IfExp) and getattr(node.orelse, "value", None) is False:
                return

    raise AssertionError(
        "G2 check_rate_limit 缺少「受 REDIS_STRICT 守卫的 return False」；"
        "已确认无任何 fail-closed 路径的条件链引用 REDIS_STRICT。"
        "（注意：与 Redis 故障无关的 return False 不能替代，例如超限分支"
        " `if count >= max_requests: return False`。）"
    )


def assert_g5_auth_secret_fail_fast() -> None:
    """G5: auth.py 生产缺失 AUTH_SECRET 即 raise RuntimeError。

    判定：存在 `raise RuntimeError(...)`，其守卫链**同时**含
    「AUTH_SECRET / secret 缺失类条件」与「production / prod 环境条件」。

    （原先只做 `any(Raise)` + 全文含 "AUTH_SECRET" —— 实测删掉生产 fail-fast 后
    门禁仍绿：`if len(secret) < 32: raise RuntimeError` 这种长度校验的 raise 会把
    判定撑成恒真。）
    """
    tree = ast.parse(_load("py-server/shared/auth.py"))

    for fn in _iter_functions(tree):
        for stmt, conds in _guard_chains(fn):
            raises = [n for n in ast.walk(stmt) if isinstance(n, ast.Raise)]
            if not raises:
                continue
            if not any("RuntimeError" in ast.dump(n) for n in raises):
                continue
            cd = _conds_dump(conds)
            has_secret = "AUTH_SECRET" in cd or "secret" in cd
            has_env = "production" in cd or "prod" in cd
            if has_secret and has_env:
                return

    raise AssertionError(
        "G5 缺少「生产环境缺失 AUTH_SECRET 即 RuntimeError」的 fail-fast；"
        "未发现任何 RuntimeError 的守卫链同时引用 AUTH_SECRET/secret 与 production/prod。"
        "（注意：仅全文存在 RuntimeError 不算通过——长度校验等无关 raise 不能替代。）"
    )


# G7 承载位置（按序）：demo 种子守卫的真实归属。
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

    判定（AST 守卫链，2026-10-08 由字符串匹配升级）：存在对 `seed_demo_data` 的
    **调用**，其守卫链中含「`not in` 比较 且 引用 production/prod」。

    原实现用 `'not in ("production", "prod")' in src` 做字符串匹配——把守卫删掉、
    仅在**注释**里保留该片段即可让门禁通过。改为 AST 判定后只能靠真实调用点通过。
    """
    missing = []
    for path in _G7_CANDIDATES:
        try:
            src = _load(path)
        except FileNotFoundError:
            missing.append(f"{path}(不存在)")
            continue
        tree = ast.parse(src)  # 语法坏了要立刻炸，别静默当作「没命中」

        for fn in _iter_functions(tree):
            for stmt, conds in _guard_chains(fn):
                calls = [
                    n
                    for n in ast.walk(stmt)
                    if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Name)
                    and n.func.id == "seed_demo_data"
                ]
                if not calls:
                    continue
                for cond in conds:
                    if not isinstance(cond, ast.Compare):
                        continue
                    if not any(isinstance(op, ast.NotIn) for op in cond.ops):
                        continue
                    if "production" in ast.dump(cond) or "prod" in ast.dump(cond):
                        return
        missing.append(path)

    raise AssertionError(
        "G7 demo 种子未被 not in (production,prod) 守卫；"
        f"已排查承载位置 {list(_G7_CANDIDATES)} 均未发现"
        "「seed_demo_data() 调用 + 守卫链含 not-in(production,prod)」。"
        f"明细：{missing}"
    )


def assert_g9_workers_gt1_fail_fast() -> None:
    """G9: UVICORN_WORKERS/WEB_CONCURRENCY > 1 时 raise RuntimeError（ADR-007 单写者）。

    与 G7 同源：守卫随 M-4 拆分搬到 app/lifespan.py（`_assert_single_worker`），
    故按序并查承载位置，不绑定单一文件名。
    判定用「守卫链共现」：raise 的守卫链须含与 1 的比较，且所在函数须引用
    UVICORN_WORKERS/WEB_CONCURRENCY —— 避免被无关 raise 撑成假绿。
    """
    for path in _G7_CANDIDATES:  # 同为「生命周期守卫」的承载位置集合
        try:
            src = _load(path)
        except FileNotFoundError:
            continue
        tree = ast.parse(src)
        for fn in _iter_functions(tree):
            fn_dump = ast.dump(fn)
            if "UVICORN_WORKERS" not in fn_dump and "WEB_CONCURRENCY" not in fn_dump:
                continue
            for stmt, conds in _guard_chains(fn):
                if not any(isinstance(n, ast.Raise) for n in ast.walk(stmt)):
                    continue
                for cond in conds:
                    if not isinstance(cond, ast.Compare):
                        continue
                    if not isinstance(cond.ops[0], (ast.Gt, ast.GtE)):
                        continue
                    if (
                        isinstance(cond.comparators[0], ast.Constant)
                        and cond.comparators[0].value == 1
                    ):
                        return

    raise AssertionError(
        "G9 缺少 workers>1 fail-fast；已排查 "
        f"{list(_G7_CANDIDATES)}，未发现任何 raise 的守卫链同时满足"
        "「所在函数引用 UVICORN_WORKERS/WEB_CONCURRENCY + 与 1 比较控制该 raise」。"
        "（注意：仅全文存在 raise 不算通过——无关 raise 不能替代受守卫的 fail-fast）"
    )


def assert_g11_html_escape_called() -> None:
    """G11: SVG 注入转义 —— xfyun_multimodal.py 必须**实际调用** html.escape()。

    判定（AST 调用点，2026-10-08 由 grep 升级）：模块内至少存在一处
    `Call(func=Attribute(value=Name("html"), attr="escape"))`。

    原实现是 shell 里两条 `grep -q`，实测有两处弱点：
      1) 模式 `html.escape` 的 `.` 未转义 → 同形名 `html_escape(...)` 也命中，
         于是「把转义函数改名成不转义的实现」照样全绿；
      2) 纯存在性检查 → 把调用**注释掉**（`# title = html.escape(...)`）仍命中。
    即「看起来还在转义、实际已不转义」这类回归会被静默放行。故改为 AST 调用点判定：
    注释与字符串中的出现一律不计。
    """
    tree = ast.parse(_load("py-server/db/xfyun_multimodal.py"))

    has_import = any(
        isinstance(n, ast.Import) and any(a.name == "html" for a in n.names)
        for n in ast.walk(tree)
    )
    if not has_import:
        raise AssertionError("G11 缺少 import html")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if (
            isinstance(fn, ast.Attribute)
            and fn.attr == "escape"
            and isinstance(fn.value, ast.Name)
            and fn.value.id == "html"
        ):
            return

    raise AssertionError(
        "G11 未发现 html.escape( ... ) 的实际调用（注释 / 字符串中的出现不算）。"
        "SVG 模板必须转义外部输入，否则存在注入风险。"
    )


def main() -> int:
    assert_g2_rate_limit_fail_closed()
    assert_g5_auth_secret_fail_fast()
    assert_g7_demo_non_production()
    assert_g9_workers_gt1_fail_fast()
    assert_g11_html_escape_called()
    print("SECURITY AST ASSERTIONS PASSED (G2/G5/G7/G9/G11)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
