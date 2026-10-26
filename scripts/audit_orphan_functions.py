#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产调用点审计：找出定义但从未被调用的函数（stub/orphan 候选）。

设计目标（与 scripts/audit_api_contract.py 同风格）：
- 纯 stdlib，秒级，report-only（本脚本不删任何代码，只产线索）；
- 四层分类：
  T1 全仓零引用（生产/测试/实验/脚本均无调用）——最强孤儿候选；
  T2 仅测试引用（生产零调用）——测试专属代码，信息项；
  T3 动态分发豁免（装饰器/字符串/抽象方法/框架入口）；
  T4 __all__ 公开导出面（零内部调用方，但函数名或宿主类出现在**同文件模块级**
     __all__ 里 = 对外承诺的公开 API，不是孤儿）。
- 入口豁免：FastAPI 路由装饰器、任意装饰器函数、dunder、抽象方法、
  名字出现在字符串字面量中的函数（getattr / importlib / 注册表动态分发）。

裁定层（2026-10-26 引入，照 scripts/token_scan_exemptions.json 的先例：
「理由枚举 + 僵尸检测 + 拒绝刷新基线」）：
- scripts/orphan_adjudicated.json = 已裁定清单 + 已裁定基线。
  · verdict=keep / planned-use → 人工裁定「保留，不删」，从 T1 跳过；
  · verdict=defer-delete       → 人工裁定「本轮不删」，**仍计入 T1**，
                                 但其 (file, name) 登记进基线名册；
  · 清单缺失 / JSON 坏 / 字段缺 / verdict 不在枚举 / 重复条目 / 基线自相矛盾
    → **exit 2**（fail-closed：判据本身坏了必须响，绝不当空清单放行）；
  · 清单条目指向的函数在对应文件里已不存在 = 僵尸条目 → **exit 1**，
    且**不提供 --update / 自动刷新**入口（照 token_scan「拒绝刷新基线」口径：
    要改基线必须人工编辑 JSON，禁止用一次运行把当前状态洗白）。
- --gate 的红绿：T1 中出现**基线名册未登记**的项（= 新增零引用函数）→ exit 1；
  基线内已裁定的存量项不阻断。闸门由此从「永远红的待办」变成「有裁定的准入」：
  存量有账可查，新增必红且点名。T4 与 allowlist 均不参与红绿分母。

刻意不加的东西（已评估，别再提议）：
- 「动态路由 / getattr 反射豁免」：现有 dyn 判据（生产面 + 全仓 .py 里所有
  identifier 形态的字符串字面量）**已经覆盖**这类成因——任何以字符串形式出现
  的函数名都会被判 T3。再加一层「疑似反射就豁免」只会引入假阴性，把真孤儿洗白。
  2026-10-26 评估结论：不加。
- `__all__` 跨模块 `from m import *` 追踪：任一条 star-import 就能让整模块脱罪，
  公开面被无限放大，同样只增假阴性。T4 只认**同文件模块级** __all__。

守卫自身曾失效的两个缺陷（2026-10-26 实测踩到，已修，留档——改这里前请先读一遍）：
- `rel()` 跨盘符抛 ValueError。Windows 下 pytest 的 tmp_path 在 C:、仓库在 E:，
  `os.path.relpath` 跨盘符必然抛错。后果不是「某次调用失败」这么轻：它发生在
  `_fail()` **格式化报错文案的路径上**，于是「已裁定清单坏了」这条 fail-closed 报错
  被一条完全无关的 traceback 顶掉——**守卫看起来在、实际没生效**（fail-closed 静默失效）。
  已兜底（失败时回退绝对路径）。这类「判据自己先崩了」的洞，只有**给 fail-closed 路径
  本身写单测**才会暴露；改动本文件的报错路径时，必须同步
  `py-server/tests/test_orphan_function_audit.py` 里的 4 条 fail-closed 用例。
- 测试夹具写真实函数名会污染被测对象。引用面覆盖全仓 `.py`（含 `py-server/tests/`），
  夹具里的字符串 `"agent_reflection"` 会被 `dyn` 判据当成调用证据，
  **当场把该函数从 T1 抹掉**（实测 allowlist 命中数 6→5）。故夹具必须用中性名
  （详见测试文件 `_valid_entry` 的 docstring）。这条同时是「不需要再补反射豁免」的
  反向证据：字符串层已经敏感到会被测试自己带偏，再放宽只会更假。

退出码：
  0 = 无新增未裁定孤儿、无僵尸条目；
  1 = --gate 下 T1 存在未登记项 / 存在僵尸条目（清单与代码不一致，与 --gate 无关）；
  2 = 扫描面为空 / 已裁定清单加载失败或格式错 / 显式传入被禁的刷新参数。

用法：
    python scripts/audit_orphan_functions.py            # 报告
    python scripts/audit_orphan_functions.py --gate     # 准入闸（见上）
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_SERVER = os.path.join(REPO, "py-server")

# 生产面 = app 运行时真正 import 的代码（root .py + 这些包）
PROD_DIRS = ("", "agents", "api", "app", "app_config", "db", "engines",
             "schemas", "services", "shared", "tools", "utils")
# 引用面 = 全仓任意 .py（tests/experiments/scripts 均计入，用于 T2 分层）
SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
             ".pytest_tmp", "node_modules", "vectordb_data", "data",
             "sessions", "milvus_lite_data", "models", "media", "documents",
             "plots", "assets", "seed", "egg-info"}

# ── 已裁定清单（allowlist + 已裁定基线）────────────────────────────────────
ADJUDICATED_FILE = os.path.join(REPO, "scripts", "orphan_adjudicated.json")
VERDICT_KEEP = "keep"            # 保留：语义/契约/安全价值，不删（跳过 T1）
VERDICT_PLANNED = "planned-use"  # 保留：已排期接入，暂未接线（跳过 T1）
VERDICT_DEFER = "defer-delete"   # 待删：本轮不删（仍计入 T1，登记进基线名册）
SKIP_VERDICTS = {VERDICT_KEEP, VERDICT_PLANNED}
ALLOWED_VERDICTS = SKIP_VERDICTS | {VERDICT_DEFER}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# 被禁的「一键洗白」参数：照 token_scan「拒绝刷新基线」口径，改基线只能人工编辑 JSON
REFRESH_ARGS = ("--update", "--update-baseline", "--update-allowlist",
                "--bless", "--accept-new", "--rebaseline")


def _skip(path: str) -> bool:
    parts = set(os.path.normpath(path).split(os.sep))
    return bool(parts & SKIP_DIRS)


def iter_py(root: str, prod_only: bool = False):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            fp = os.path.join(dirpath, fn)
            if prod_only:
                rel_dir = os.path.relpath(dirpath, root)
                top = rel_dir.split(os.sep)[0] if rel_dir != "." else ""
                if top not in PROD_DIRS:
                    continue
            yield fp


def rel(fp: str) -> str:
    try:
        return os.path.relpath(fp, REPO).replace(os.sep, "/")
    except ValueError:
        # 跨盘符（Windows：仓库在 E: 而传入路径在 C:，如 pytest 的 tmp_path）
        # 时 os.path.relpath 抛 ValueError。若不兜住，清单损坏的 fail-closed 报错
        # 会变成一条与此无关的 traceback，把排查方向带偏 —— 实测踩到，故显式兜底。
        return fp.replace(os.sep, "/")


def _fail(msg: str) -> None:
    """fail-closed 统一出口：判据本身坏了（清单/扫描面）→ exit 2。"""
    print(f"🔴 [orphan] {msg}", file=sys.stderr)
    sys.exit(2)


class FuncInfo:
    __slots__ = ("qualname", "name", "file", "line", "decorated",
                 "abstract", "is_dunder", "owners")

    def __init__(self, qualname, name, file, line, decorated, abstract,
                 is_dunder, owners=()):
        self.qualname = qualname
        self.name = name
        self.file = file
        self.line = line
        self.decorated = decorated
        self.abstract = abstract
        self.is_dunder = is_dunder
        # 宿主类链（outermost → innermost）；模块级函数为空元组。
        # T4 判定需要它：方法是否属于某个被 __all__ 导出的公开类。
        self.owners = tuple(owners)


def collect_defs(prod_files):
    """AST 采集生产面函数定义 + 字符串字面量（动态分发判据）。"""
    defs: list[FuncInfo] = []
    strings: set[str] = set()
    for fp in prod_files:
        try:
            tree = ast.parse(open(fp, encoding="utf-8", errors="replace").read())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                s = node.value.strip()
                if s.isidentifier():
                    strings.add(s)
        _walk_defs(tree, prefix="", fp=fp, defs=defs)
    return defs, strings


def _walk_defs(tree, prefix, fp, defs):
    """采集任意嵌套层级的 def/async def，并同步记录宿主类链。

    为什么不用 ast.walk：ast.walk 是扁平遍历，拿不到「这个函数属于哪个类」，
    而 T4（__all__ 公开导出面）判定需要宿主类名。本递归与 ast.walk 采集范围
    等价（含函数内嵌套函数），只多带一条 owners 链。
    """
    _walk_children(tree, prefix, fp, defs, ())


def _walk_children(node, prefix, fp, defs, owners):
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qual = f"{prefix}{child.name}" if prefix else child.name
            decorated = bool(child.decorator_list)
            abstract = False
            for dec in child.decorator_list:
                seg = ast.dump(dec)
                if "abstractmethod" in seg or "abstractproperty" in seg:
                    abstract = True
            defs.append(FuncInfo(
                qual, child.name, fp, child.lineno, decorated, abstract,
                child.name.startswith("__") and child.name.endswith("__"),
                owners))
            # 函数体内再嵌套的 def：宿主类链不变
            _walk_children(child, prefix, fp, defs, owners)
        elif isinstance(child, ast.ClassDef):
            _walk_children(child, prefix, fp, defs, owners + (child.name,))
        else:
            _walk_children(child, prefix, fp, defs, owners)


def collect_refs(all_files):
    """全仓 .py 的被调用名集合：Name/Attribute 调用 + 导入别名 + 装饰器引用 + 字符串。"""
    called: set[str] = set()
    str_literals: set[str] = set()
    for fp in all_files:
        try:
            tree = ast.parse(open(fp, encoding="utf-8", errors="replace").read())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    called.add(f.id)
                elif isinstance(f, ast.Attribute):
                    called.add(f.attr)
            elif isinstance(node, ast.Attribute):
                # 非调用属性访问也算引用（传给回调、赋值别名等）
                called.add(node.attr)
            elif isinstance(node, ast.Name):
                called.add(node.id)
            elif isinstance(node, ast.alias):
                # from m import f as g：f 与 g 都算被引用（别名导入是调用点的常见形态）
                called.add(node.name)
                if node.asname:
                    called.add(node.asname)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                s = node.value.strip()
                if s.isidentifier():
                    str_literals.add(s)
    return called, str_literals


# 引用面额外跳过的仓目录（非代码调用方）
REPO_SKIP_DIRS = SKIP_DIRS | {"archive", "deploy", "dist", ".git", "node_modules",
                              "submission", "deliverables"}


def iter_repo_py():
    """全仓 .py（排除 venv/归档/部署副本/git），作为引用面。"""
    for dirpath, dirnames, filenames in os.walk(REPO):
        dirnames[:] = [d for d in dirnames if d not in REPO_SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


# ── __all__ 公开导出面（T4 判据）──────────────────────────────────────────
def collect_module_exports(prod_files) -> dict[str, dict]:
    """采集每个生产文件的模块级 __all__。

    返回 {仓库相对路径: {"exports": {导出名: 行号}, "defined": {本文件定义过的名字}}}。

    支持形态：`__all__ = [...]` / `__all__ += [...]` / `__all__.extend([...])` /
    `__all__.append("x")`。不支持 `__all__ = some_list`（名字间接来源，宁可漏判
    T4 也不凭空放大公开面——漏判只是多列一个候选，误判会让真孤儿脱罪）。

    "defined" 用于「__all__ 导出名僵尸对照」（仅报告）：本文件里出现过的所有
    def/async def/class 名 + 模块级赋值与导入绑定的名字。
    """
    modules: dict[str, dict] = {}
    for fp in prod_files:
        try:
            tree = ast.parse(open(fp, encoding="utf-8", errors="replace").read())
        except (SyntaxError, ValueError, OSError):
            continue
        exports: dict[str, int] = {}
        for node in tree.body:                      # 只认模块级语句
            for value in _all_assign_values(node):
                for name, line in _iter_str_seq(value):
                    exports.setdefault(name, line)
        if not exports:
            continue
        defined: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(node.name)
        for node in tree.body:                      # 模块级绑定（变量/导入别名）
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Name):
                        defined.add(t.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    defined.add(alias.asname or alias.name.split(".")[0])
        modules[rel(fp)] = {"exports": exports, "defined": defined}
    return modules


def _all_assign_values(node):
    """抽出「写入 __all__」的那些 RHS 值节点。"""
    values = []
    if isinstance(node, ast.Assign):
        if any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            values.append(node.value)
    elif isinstance(node, ast.AugAssign):
        if isinstance(node.target, ast.Name) and node.target.id == "__all__":
            values.append(node.value)
    elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        call = node.value
        func = call.func
        if (isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "__all__"
                and func.attr in ("extend", "append")):
            values.extend(call.args)
    return values


def _iter_str_seq(node):
    """从 List/Tuple/Set/常量字符串里取出 (字符串, 行号)。"""
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                yield elt.value, elt.lineno
    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value, node.lineno


def export_hit(d: FuncInfo, modules: dict[str, dict]):
    """T4 判定：函数是否属于本模块的 __all__ 公开面。

    两种命中（保守，只认同文件模块级 __all__）：
      1. 顶层函数（owners 为空）且函数名本身在 __all__；
      2. 方法的任一宿主类名在 __all__（宿主类被公开导出 ⇒ 其方法是公开面的一部分）。
    命中返回 (导出名, 行号, 说明)；否则返回 None。
    """
    mod = modules.get(rel(d.file))
    if not mod:
        return None
    exports = mod["exports"]
    if d.name in exports:
        return (d.name, exports[d.name], "函数名直接导出")
    for owner in d.owners:
        if owner in exports:
            return (owner, exports[owner], f"宿主类 {owner} 被导出，方法属其公开面")
    return None


# ── 已裁定清单加载（fail-closed）──────────────────────────────────────────
def load_adjudicated(path: str = ADJUDICATED_FILE) -> tuple[list[dict], dict]:
    """读已裁定清单（allowlist + 已裁定基线）。任何格式/一致性问题 → exit 2。

    为什么「文件不存在」也 exit 2：本清单是门禁的组成部分。静默当空清单时
    allowlist 会悄悄失效，表现成「T1 计数暴涨 → 新增未登记 → exit 1」，
    把一个「裁定被抹掉」的运维事故伪装成「代码新增了 6 个孤儿」，排查方向被带偏。
    """
    if not os.path.isfile(path):
        _fail(f"已裁定清单不存在：{rel(path)}（门禁组成部分，缺失即 fail-closed，"
              f"不得静默当空清单放行）")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        _fail(f"已裁定清单 JSON 解析失败：{rel(path)} 第 {exc.lineno} 行第 {exc.colno} 列"
              f"（{exc.msg}）→ 人工修好再跑，禁止静默当空清单")
    except OSError as exc:
        _fail(f"已裁定清单读取失败：{rel(path)}：{exc}")
    if not isinstance(data, dict):
        _fail(f"已裁定清单顶层必须是对象：{rel(path)}")
    raw = data.get("adjudicated")
    if not isinstance(raw, list) or not raw:
        _fail(f"已裁定清单 adjudicated 必须是非空数组：{rel(path)}")

    entries: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for idx, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            _fail(f"已裁定清单第 {idx} 条不是对象：{item!r}")
        missing = [k for k in ("file", "name", "line", "verdict", "reason", "date")
                   if k not in item]
        if missing:
            _fail(f"已裁定清单第 {idx} 条缺字段 {missing}：{item!r}")
        verdict = str(item["verdict"]).strip()
        if verdict not in ALLOWED_VERDICTS:
            _fail(f"已裁定清单第 {idx} 条 verdict='{verdict}' 不在允许集合 "
                  f"{sorted(ALLOWED_VERDICTS)}：{item!r}")
        line = item["line"]
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            _fail(f"已裁定清单第 {idx} 条 line 必须是正整数：{item!r}")
        date = str(item["date"]).strip()
        if not DATE_RE.match(date):
            _fail(f"已裁定清单第 {idx} 条 date 必须是 YYYY-MM-DD：{item!r}")
        reason = str(item["reason"]).strip()
        if not reason:
            _fail(f"已裁定清单第 {idx} 条 reason 为空（裁定必须写明理由，不得空白放行）")
        fkey = str(item["file"]).strip().replace("\\", "/")
        nkey = str(item["name"]).strip()
        if not fkey or not nkey:
            _fail(f"已裁定清单第 {idx} 条 file/name 为空：{item!r}")
        # 唯一性按 (file, name, line)：同文件同名多实现（如 graph_db 的接口+实现
        # 两处 get_dependents）是合法登记，行号才是唯一定位。
        key = (fkey, nkey, line)
        if key in seen:
            _fail(f"已裁定清单第 {idx} 条重复（同 file+name+line 已有登记）：{key}")
        seen.add(key)
        entries.append({
            "file": fkey, "name": nkey, "line": line, "verdict": verdict,
            "group": str(item.get("group", "")).strip(),
            "reason": reason, "date": date,
        })

    base = data.get("baseline")
    if not isinstance(base, dict):
        _fail(f"已裁定清单 baseline 必须是对象：{rel(path)}")
    base_t1 = base.get("t1")
    if not isinstance(base_t1, int) or isinstance(base_t1, bool) or base_t1 < 0:
        _fail(f"已裁定清单 baseline.t1 必须是非负整数：{base!r}")
    base_date = str(base.get("date", "")).strip()
    if not DATE_RE.match(base_date):
        _fail(f"已裁定清单 baseline.date 必须是 YYYY-MM-DD：{base!r}")
    # 基线名册由 defer-delete 条目推导 —— 两处数字必须一致，否则基线自相矛盾
    defer_n = sum(1 for e in entries if e["verdict"] == VERDICT_DEFER)
    if base_t1 != defer_n:
        _fail(f"已裁定基线自相矛盾：baseline.t1={base_t1} 与 defer-delete 条目数 "
              f"{defer_n} 不等（名册由后者推导，两者必须一致）→ 人工编辑修正")
    baseline = {
        "t1": base_t1,
        "date": base_date,
        "doc": str(base.get("adjudication_doc", "")).strip(),
        "note": str(base.get("note", "")).strip(),
    }
    return entries, baseline


_DEFINED_CACHE: dict[str, set[str]] = {}


def defined_func_names(repo_rel_path: str) -> set[str]:
    """文件里所有 def/async def 的名字（带缓存；文件缺失/解析失败 → 空集 = 僵尸）。"""
    if repo_rel_path in _DEFINED_CACHE:
        return _DEFINED_CACHE[repo_rel_path]
    fp = os.path.join(REPO, repo_rel_path.replace("/", os.sep))
    names: set[str] = set()
    try:
        with open(fp, encoding="utf-8", errors="replace") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError, ValueError):
        _DEFINED_CACHE[repo_rel_path] = names
        return names
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    _DEFINED_CACHE[repo_rel_path] = names
    return names


def main() -> None:
    args = sys.argv[1:]
    gate = "--gate" in args
    banned = [a for a in args if a in REFRESH_ARGS]
    if banned:
        _fail(f"本脚本不提供刷新入口（{', '.join(banned)}）：已裁定清单与基线只能人工编辑 "
              f"{rel(ADJUDICATED_FILE)}（照 token_scan「拒绝刷新基线」口径——"
              f"禁止用一次运行把当前状态洗白）")

    prod_files = list(iter_py(PY_SERVER, prod_only=True))
    all_files = list(iter_repo_py())
    if not prod_files or not all_files:
        print("🔴 [orphan] 扫描面为空——目录结构异常？fail-closed", file=sys.stderr)
        sys.exit(2)

    defs, prod_strings = collect_defs(prod_files)
    called, all_strings = collect_refs(all_files)
    prod_called, _ = collect_refs(prod_files)
    dyn = prod_strings | all_strings
    modules = collect_module_exports(prod_files)
    entries, baseline = load_adjudicated()
    skip_map = {(e["file"], e["name"]): e for e in entries
                if e["verdict"] in SKIP_VERDICTS}
    baseline_counts = Counter((e["file"], e["name"]) for e in entries
                              if e["verdict"] == VERDICT_DEFER)

    t1, t2, t3 = [], [], []
    t4: list[tuple[FuncInfo, tuple]] = []
    allowed_hits: list[tuple[FuncInfo, dict]] = []
    for d in defs:
        if d.decorated or d.is_dunder or d.abstract or d.name in dyn:
            t3.append(d)          # 入口/动态分发/抽象方法——不作为孤儿候选
        elif d.name in prod_called:
            continue              # 生产在用——非孤儿，直接排除
        elif d.name in called:
            t2.append(d)          # 仅测试/实验/脚本引用，生产零调用
        else:
            key = (rel(d.file), d.name)
            if key in skip_map:   # 已人工裁定保留（keep / planned-use）
                allowed_hits.append((d, skip_map[key]))
                continue
            hit = export_hit(d, modules)
            if hit:               # T4：__all__ 公开导出面，无内部调用方
                t4.append((d, hit))
                continue
            t1.append(d)          # 全仓零引用

    # ── 基线对照：新增未登记项（红）/ 已消解项（提示）────────────────────
    observed: Counter = Counter()
    unregistered: list[FuncInfo] = []
    for d in sorted(t1, key=lambda x: (x.file, x.line)):
        key = (rel(d.file), d.name)
        observed[key] += 1
        if observed[key] > baseline_counts.get(key, 0):
            unregistered.append(d)
    t1_counts = Counter((rel(d.file), d.name) for d in t1)
    vanished = sorted((k, baseline_counts[k] - t1_counts.get(k, 0))
                      for k in baseline_counts
                      if t1_counts.get(k, 0) < baseline_counts[k])

    # ── 僵尸检测（清单与代码不一致）──────────────────────────────────────
    skip_entries = [e for e in entries if e["verdict"] in SKIP_VERDICTS]
    defer_entries = [e for e in entries if e["verdict"] == VERDICT_DEFER]
    zombies = [e for e in skip_entries
               if e["name"] not in defined_func_names(e["file"])]
    hit_keys = {(rel(d.file), d.name) for d, _ in allowed_hits}
    resolved_keep = [e for e in skip_entries
                     if e["name"] in defined_func_names(e["file"])
                     and (e["file"], e["name"]) not in hit_keys]
    resolved_defer = [e for e in defer_entries
                      if e["name"] not in defined_func_names(e["file"])]

    # ── 报告 ────────────────────────────────────────────────────────────
    verdict_mix = Counter(e["verdict"] for e in entries)
    print(f"扫描：生产文件 {len(prod_files)} / 全仓 {len(all_files)}，"
          f"生产函数定义 {len(defs)} 个")
    print(f"T3 动态分发/入口豁免：{len(t3)} 个（不列为孤儿）")
    print(f"已裁定清单 {rel(ADJUDICATED_FILE)}：{len(entries)} 条"
          f"（" + " / ".join(f"{k} {v}" for k, v in sorted(verdict_mix.items())) + "）"
          f"，基线 T1={baseline['t1']}（{baseline['date']}）")

    print(f"\n=== allowlist 已裁定保留（命中跳过 {len(allowed_hits)} 项，不计入 T1）===")
    for d, e in sorted(allowed_hits, key=lambda x: (x[0].file, x[0].line)):
        reason = e["reason"] if len(e["reason"]) <= 52 else e["reason"][:52] + "…"
        print(f"  {rel(d.file)}:{d.line}  {d.name:<28} [{e['verdict']}] {reason}")

    print(f"\n=== T4 __all__ 公开导出面（无内部调用方但属对外承诺，{len(t4)} 个；"
          f"不参与 --gate 红绿）===")
    for d, hit in sorted(t4, key=lambda x: (x[0].file, x[0].line)):
        print(f"  {rel(d.file)}:{d.line}  {d.name:<28} ← {hit[2]}"
              f"（{hit[0]} ∈ __all__:{hit[1]}）")

    print(f"\n=== T1 全仓零引用（最强孤儿候选，{len(t1)} 个）===")
    for d in sorted(t1, key=lambda x: (x.file, x.line)):
        print(f"  {rel(d.file)}:{d.line}  {d.qualname}")
    print(f"\n=== T2 仅测试/脚本引用（生产零调用，{len(t2)} 个）===")
    for d in sorted(t2, key=lambda x: (x.file, x.line)):
        print(f"  {rel(d.file)}:{d.line}  {d.qualname}")

    print(f"\n裁定台账：零引用候选 {len(t1) + len(t4) + len(allowed_hits)} 个 "
          f"= T1 {len(t1)} + T4 公开面 {len(t4)} + allowlist 跳过 {len(allowed_hits)}")
    exp_total = sum(len(m["exports"]) for m in modules.values())
    exp_zombie = sorted(
        (f, n) for f, m in modules.items()
        for n in m["exports"] if n not in m["defined"])
    print("已裁定清单对照（非红绿，仅报告）：")
    print(f"  · allowlist 僵尸条目 {len(zombies)} 项"
          f"（函数已不存在却仍被裁定保留 → 红）；"
          f"已消解 {len(resolved_keep)} 项（已有调用方/已挪位 → 建议人工清理条目）")
    for e in resolved_keep:
        print(f"    ⚪ {e['file']}:{e['line']} {e['name']} [{e['verdict']}] "
              f"已不再命中 T1（函数被删 / 已接线 / 被判 T3）→ 建议人工核对后清理该条目")
    print(f"  · 基线名册 {len(baseline_counts)} 个键 / {baseline['t1']} 项："
          f"仍在 T1 {sum(t1_counts.get(k, 0) for k in baseline_counts)} 项，"
          f"已消解 {len(vanished)} 项（其中 {len(resolved_defer)} 项函数已不在源文件中 = 真删除，"
          f"其余为已接线/被判 T3 → 均建议人工收紧基线）")
    for k, n in vanished:
        print(f"    ⚪ {k[0]} {k[1]}：基线登记 {baseline_counts[k]} 项、T1 现存 "
              f"{t1_counts.get(k, 0)} 项（少 {n} 项）→ 建议人工收紧基线")
    print(f"__all__ 对照（非红绿，仅报告）：生产面 {len(modules)} 个模块声明 __all__ / "
          f"{exp_total} 个导出名，其中 {len(exp_zombie)} 个在本模块内找不到同名定义")
    for f, n in exp_zombie:
        print(f"    ⚠ {f}: __all__ 导出 '{n}' 在本模块内无定义（拼写错误或已删除）")

    print("\n口径说明：")
    print("- T1/T2 是线索不是结论：多态接口方法、字符串注册、框架回调可能漏判；")
    print("- 本脚本 report-only，不删任何代码（红线：零不可逆操作）；")
    print("- 每条候选须人工 grep 反查后登记进已裁定清单，方可从闸门红绿中豁免；")
    print("- 刻意不加「动态路由/getattr 反射豁免」：现有 dyn 字符串字面量判据已覆盖，"
          "再补只会引入假阴性（2026-10-26 评估结论，见模块 docstring）。")

    # ── 红绿 ────────────────────────────────────────────────────────────
    rc = 0
    if zombies:
        rc = 1
        for e in zombies:
            print(f"🔴 [orphan] 僵尸裁定条目：{e['file']}:{e['line']} {e['name']}"
                  f"（verdict={e['verdict']}，该文件已无同名函数定义 → 人工编辑 "
                  f"{rel(ADJUDICATED_FILE)} 删除该条或恢复函数）", file=sys.stderr)
        print(f"🔴 [orphan] 已裁定清单存在 {len(zombies)} 条僵尸条目 → exit 1"
              f"（清单与代码不一致，与是否 --gate 无关）", file=sys.stderr)
    if gate:
        if unregistered:
            rc = 1
            print(f"🔴 [orphan] --gate：T1 出现 {len(unregistered)} 项未登记的新增零引用函数"
                  f"（已裁定基线 {baseline['t1']} 项）", file=sys.stderr)
            for d in unregistered:
                print(f"    {rel(d.file)}:{d.line}  {d.name}", file=sys.stderr)
            print(f"🔴 [orphan] 新增孤儿须人工裁定后登记进 {rel(ADJUDICATED_FILE)}"
                  f"（verdict={VERDICT_DEFER} 登记基线 / {VERDICT_KEEP} 保留）→ exit 1",
                  file=sys.stderr)
        else:
            print(f"\n🟢 [orphan] --gate：T1 {len(t1)} 项全部在已裁定基线内"
                  f"（无新增未裁定孤儿），allowlist 无僵尸 → 放行")
    if rc:
        sys.exit(rc)


if __name__ == "__main__":
    main()
