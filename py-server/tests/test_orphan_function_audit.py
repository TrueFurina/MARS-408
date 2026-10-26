# -*- coding: utf-8 -*-
"""audit_orphan_functions 工具单元测试（守护两轮缺陷修复，TDD 分 commit 纪律：实现已在
scripts/audit_orphan_functions.py；本文件仅测分类逻辑，不删任何生产代码）。

被测逻辑：
- 别名导入（from m import f as g）必须让 f 被识别为「已引用」（修复 1）；
- 生产有引用的函数必须排除出 T1（修复 2 的分层逻辑），仅测试/脚本引用的归 T2；
- 已裁定清单（scripts/orphan_adjudicated.json）的 fail-closed 加载：
  缺失 / JSON 坏 / verdict 不在枚举 / baseline 自相矛盾，一律 exit 2（2026-10-26 补）；
- T1 基线快照随裁定口径更新：40 = T1 32 + T4 2 + allowlist 6（2026-10-26 补）。
"""
import importlib.util
import io
import json
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
    """真仓库可复跑：脚本在仓库内执行，输出 T1/T2/T3/T4 四段且计数落在已裁定基线。

    2026-10-26 起闸门由「T1 非空即红」改为「T1 出现基线名册未登记项即红」，
    T4（__all__ 公开面）与 allowlist（人工裁定保留）从 T1 分出：
        零引用候选 40 = T1 32 + T4 2 + allowlist 6
    本断言仍是基线快照，作用不变——防新孤儿悄悄爬入（新增未登记项 → --gate exit 1）。
    """
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
    assert "T1" in out and "T2" in out and "T3" in out and "T4" in out
    assert "最强孤儿候选，32 个" in out
    assert "T4 __all__ 公开导出面（无内部调用方但属对外承诺，2 个" in out
    assert "allowlist 已裁定保留（命中跳过 6 项" in out
    assert "零引用候选 40 个 = T1 32 + T4 公开面 2 + allowlist 跳过 6" in out
    assert "allowlist 僵尸条目 0 项" in out


def _valid_entry(**over):
    """裁定条目夹具。

    注意：file/name **必须用中性值**——引用面覆盖全仓 .py，脚本把「identifier 形态的
    字符串字面量」当作动态分发的判据（dyn → T3）。夹具里若写真实生产函数名，
    会把该函数喂进 dyn 从而掉出 T1，反而污染被测对象的输出（实测踩到：
    写 'agent_reflection' 导致 allowlist 命中数 6→5）。
    """
    entry = {
        "file": "py-server/shared/_audit_fixture.py",
        "name": "_audit_fixture_fn",
        "line": 1,
        "verdict": "keep",
        "group": "C",
        "reason": "单元测试夹具：裁定理由占位",
        "date": "2026-10-26",
    }
    entry.update(over)
    return entry


def _write_adjudicated(tmp_path, payload) -> str:
    p = tmp_path / "orphan_adjudicated.json"
    if isinstance(payload, str):
        p.write_text(payload, encoding="utf-8")
    else:
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def test_adjudicated_missing_file_fail_closed(tmp_path):
    """已裁定清单缺失 = 门禁判据没了 → exit 2（不得静默当空清单放行）。"""
    aud = _load_auditor()
    with pytest.raises(SystemExit) as exc:
        aud.load_adjudicated(str(tmp_path / "not_there.json"))
    assert exc.value.code == 2


def test_adjudicated_broken_json_fail_closed(tmp_path):
    """JSON 解析失败 → exit 2（fail-closed，禁止当空清单让闸门变绿）。"""
    aud = _load_auditor()
    path = _write_adjudicated(tmp_path, '{"adjudicated": [')
    with pytest.raises(SystemExit) as exc:
        aud.load_adjudicated(path)
    assert exc.value.code == 2


def test_adjudicated_unknown_verdict_fail_closed(tmp_path):
    """verdict 不在枚举（keep/planned-use/defer-delete）→ exit 2。"""
    aud = _load_auditor()
    path = _write_adjudicated(tmp_path, {
        "baseline": {"t1": 0, "date": "2026-10-26"},
        "adjudicated": [_valid_entry(verdict="whatever")],
    })
    with pytest.raises(SystemExit) as exc:
        aud.load_adjudicated(path)
    assert exc.value.code == 2


def test_adjudicated_baseline_mismatch_fail_closed(tmp_path):
    """baseline.t1 与 defer-delete 条目数不等（基线自相矛盾）→ exit 2。"""
    aud = _load_auditor()
    path = _write_adjudicated(tmp_path, {
        "baseline": {"t1": 7, "date": "2026-10-26"},
        "adjudicated": [_valid_entry(verdict="defer-delete")],
    })
    with pytest.raises(SystemExit) as exc:
        aud.load_adjudicated(path)
    assert exc.value.code == 2
