#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产调用点审计：找出定义但从未被调用的函数（stub/orphan 候选）。

设计目标（与 scripts/audit_api_contract.py 同风格）：
- 纯 stdlib，秒级，report-only（本脚本不删任何代码，只产线索）；
- 三层分类：
  T1 全仓零引用（生产/测试/实验/脚本均无调用）——最强孤儿候选；
  T2 仅测试引用（生产零调用）——测试专属代码，信息项；
  T3 动态分发豁免（装饰器/字符串/抽象方法/框架入口）。
- 入口豁免：FastAPI 路由装饰器、任意装饰器函数、dunder、抽象方法、
  名字出现在字符串字面量中的函数（getattr / importlib / 注册表动态分发）。

用法：
    python scripts/audit_orphan_functions.py            # 报告
    python scripts/audit_orphan_functions.py --gate     # T1 非空即 exit 1（不接 CI，
                                                       # 供人工裁定后决定是否接）
"""
from __future__ import annotations

import ast
import os
import sys
from collections import defaultdict

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
                rel = os.path.relpath(dirpath, root)
                top = rel.split(os.sep)[0] if rel != "." else ""
                if top not in PROD_DIRS:
                    continue
            yield fp


def rel(fp: str) -> str:
    return os.path.relpath(fp, REPO).replace(os.sep, "/")


class FuncInfo:
    __slots__ = ("qualname", "name", "file", "line", "decorated",
                 "abstract", "is_dunder")

    def __init__(self, qualname, name, file, line, decorated, abstract,
                 is_dunder):
        self.qualname = qualname
        self.name = name
        self.file = file
        self.line = line
        self.decorated = decorated
        self.abstract = abstract
        self.is_dunder = is_dunder


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
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qual = f"{prefix}{node.name}" if prefix else node.name
            decorated = bool(node.decorator_list)
            abstract = False
            for dec in node.decorator_list:
                seg = ast.dump(dec)
                if "abstractmethod" in seg or "abstractproperty" in seg:
                    abstract = True
            defs.append(FuncInfo(
                qual, node.name, fp, node.lineno, decorated, abstract,
                node.name.startswith("__") and node.name.endswith("__")))


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


def main() -> None:
    prod_files = list(iter_py(PY_SERVER, prod_only=True))
    all_files = list(iter_repo_py())
    if not prod_files or not all_files:
        print("🔴 [orphan] 扫描面为空——目录结构异常？fail-closed", file=sys.stderr)
        sys.exit(2)

    defs, prod_strings = collect_defs(prod_files)
    called, all_strings = collect_refs(all_files)
    prod_called, _ = collect_refs(prod_files)
    dyn = prod_strings | all_strings

    t1, t2, t3 = [], [], []
    for d in defs:
        if d.decorated or d.is_dunder or d.abstract or d.name in dyn:
            t3.append(d)          # 入口/动态分发/抽象方法——不作为孤儿候选
        elif d.name in prod_called:
            continue              # 生产在用——非孤儿，直接排除
        elif d.name in called:
            t2.append(d)          # 仅测试/实验/脚本引用，生产零调用
        else:
            t1.append(d)          # 全仓零引用

    print(f"扫描：生产文件 {len(prod_files)} / 全仓 {len(all_files)}，"
          f"生产函数定义 {len(defs)} 个")
    print(f"T3 动态分发/入口豁免：{len(t3)} 个（不列为孤儿）")
    print(f"\n=== T1 全仓零引用（最强孤儿候选，{len(t1)} 个）===")
    for d in sorted(t1, key=lambda x: (x.file, x.line)):
        print(f"  {rel(d.file)}:{d.line}  {d.qualname}")
    print(f"\n=== T2 仅测试/脚本引用（生产零调用，{len(t2)} 个）===")
    for d in sorted(t2, key=lambda x: (x.file, x.line)):
        print(f"  {rel(d.file)}:{d.line}  {d.qualname}")

    print("\n口径说明：")
    print("- T1/T2 是线索不是结论：多态接口方法、字符串注册、框架回调可能漏判；")
    print("- 本脚本 report-only，不删任何代码（红线：零不可逆操作）；")
    print("- 每条候选须人工 grep 反查后才可下结论。")
    if "--gate" in sys.argv and t1:
        print(f"\n🔴 [orphan] T1 孤儿候选 {len(t1)} 个（未接 CI，供人工裁定）",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
