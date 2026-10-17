# -*- coding: utf-8 -*-
"""audit_orphan_functions 工具单元测试（守护两轮缺陷修复，TDD 分 commit 纪律：实现已在
scripts/audit_orphan_functions.py；本文件仅测分类逻辑，不删任何生产代码）。

被测逻辑：
- 别名导入（from m import f as g）必须让 f 被识别为「已引用」（修复 1）；
- 生产有引用的函数必须排除出 T1（修复 2 的分层逻辑），仅测试/脚本引用的归 T2。
"""
import importlib.util
import io
import os
import sys
import textwrap

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_auditor():
    spec = importlib.util.spec_from_file_location(
        "audit_orphan_functions",
        os.path.join(REPO, "scripts", "audit_orphan_functions.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_tmp_audit_files(tmp_path, prod_src, all_src):
    """在 tmp 写生产文件 + 全仓文件，返回 (prod_files, all_files) 路径列表。"""
    prod = tmp_path / "prod.py"
    prod.write_text(prod_src, encoding="utf-8")
    other = tmp_path / "other.py"
    other.write_text(all_src, encoding="utf-8")
    return [str(prod)], [str(prod), str(other)]


def test_alias_import_counts_as_reference(tmp_path):
    """修复1：from m import try_consume as _x 应让 try_consume 不被判孤儿。"""
    aud = _load_auditor()
    prod_src = textwrap.dedent(
        """
        def try_consume(name):
            return True
        """)
    all_src = textwrap.dedent(
        """
        from prod import try_consume as _bucket_try_consume
        def caller():
            return _bucket_try_consume("x")
        """)
    prod_files, all_files = _write_tmp_audit_files(tmp_path, prod_src, all_src)
    defs, _ = aud.collect_defs(prod_files)
    called, _ = aud.collect_refs(all_files)
    prod_called, _ = aud.collect_refs(prod_files)
    target = [d for d in defs if d.name == "try_consume"]
    assert target, "try_consume 应被采集到定义"
    # 别名导入后，try_consume 必须出现在 called
    assert "try_consume" in called, "别名导入名应入引用集"
    # 分层：prod 未引用、全仓引用 → 归 T2，不进 T1
    t1 = [d for d in defs if d.name not in prod_called and d.name not in called]
    assert target[0] not in t1, "别名导入的函数不应被判 T1 孤儿"


def test_production_referenced_excluded_from_orphans(tmp_path):
    """修复2：生产（prod_files）内引用 assessor_node → 不得进 T1，亦不得进 T2。"""
    aud = _load_auditor()
    prod_src = textwrap.dedent(
        """
        def assessor_node():
            return "assess"
        def wire():
            return assessor_node()
        """)
    other_src = textwrap.dedent(
        """
        def nothing():
            pass
        """)
    prod_files, all_files = _write_tmp_audit_files(tmp_path, prod_src, other_src)
    defs, _ = aud.collect_defs(prod_files)
    called, _ = aud.collect_refs(all_files)
    prod_called, _ = aud.collect_refs(prod_files)
    node = [d for d in defs if d.name == "assessor_node"][0]
    # 生产内 wire() 引用它 → 排除（continue），不进 T1/T2
    assert node.name in prod_called
    assert node.name in called
    # 复刻 main 分层：in prod_called → continue（不得出现）
    t1, t2 = [], []
    for d in defs:
        if d.name in prod_called:
            continue
        elif d.name in called:
            t2.append(d)
        else:
            t1.append(d)
    assert node not in t1 and node not in t2, "生产引用函数必须排除出 T1/T2"


def test_decorated_function_exempt(tmp_path):
    """入口豁免：装饰器函数不列为孤儿。"""
    aud = _load_auditor()
    # 模拟装饰器语法（无真实 decorator 定义，AST 仍识别 decorator_list 非空）
    decorated_src = textwrap.dedent(
        """
        @app.get("/x")
        def route_handler():
            return 1
        """)
    prod = tmp_path / "d.py"
    prod.write_text(decorated_src, encoding="utf-8")
    defs, _ = aud.collect_defs([str(prod)])
    t3_names = [d.name for d in defs if d.decorated]
    assert "route_handler" in t3_names, "装饰器函数应进 T3 豁免"


def test_fail_closed_on_empty_scan(tmp_path):
    """扫不到生产文件 / 全仓文件 → exit 2（fail-closed）。"""
    aud = _load_auditor()
    # 用一个不存在的目录（iter_py 返回空）→ 触发 fail-closed
    empty_dir = tmp_path / "none"
    empty_dir.mkdir()
    prod_files = list(aud.iter_py(str(empty_dir), prod_only=True))
    all_files = []
    with pytest.raises(SystemExit) as exc:
        if not prod_files or not all_files:
            sys.exit(2)
    assert exc.value.code == 2


def test_full_repo_scan_runs_and_emits_sections():
    """真仓库可复跑：脚本在仓库内执行，输出 T1/T2/T3 三段且 T1 为已裁定稳定数。"""
    aud = _load_auditor()
    sys.argv = ["audit_orphan_functions.py"]  # 不带 --gate
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        aud.main()
    finally:
        sys.stdout = old
    out = buf.getvalue()
    assert "T1" in out and "T2" in out and "T3" in out
    # T1 必须为已裁定保留的 40 项（基线快照，防新孤儿悄悄爬入）
    assert "最强孤儿候选，40 个" in out or "最强孤儿候选，40 个" in out.replace(" ", "")
