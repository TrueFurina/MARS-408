# -*- coding: utf-8 -*-
"""OpenAPI 契约漂移守护：随包快照必须 == 运行时真实能力（2026-10-06 新增）

为什么需要它
--------------------------------------------------------------------------
`py-server/openapi.json` 是**随源码包发给评委**的对外契约快照。它已两次悄悄
落后于运行时：

    * 2026-09-28 审查记录：快照比运行时少 4 条 `/api/cn-distinction` 路径；
    * 2026-10-06 交付前实测：快照 223 paths / 240 operations，
      而 `app.openapi()` 已是 227 / 244，且**交付 zip 内那份也仍是旧的**。

两次都**完全静默**：源码改了、测试全绿、门禁全绿，只有评委拿快照核对接口
清单时才会发现对不上。而所有对外材料引用的是运行时数字，于是"材料"与"包内契约"
自相矛盾—— 这正是评委最容易当场抓住的破绽。

与其他"展示页不变量"守护同源：违反时没有任何报错。故用机器锁住。

**为什么必须 fail 而不是 skip**
--------------------------------------------------------------------------
skip 会让这道闸形同虚设：一旦某天环境问题（没装 venv / 缺依赖）导致 import
失败而静默跳过，恰恰在最需要它的时刻（别人改坏了）失去保护，且CI 上还是绿的。
故本文件在任何情况下都不 skip —— 环境不可用时**明确失败**并给出修复提示。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# tests/ → py-server/ →仓库根
REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = REPO_ROOT / "py-server" / "openapi.json"

# HTTP 方法键：paths 下的其余键（parameters/summary/...）不是"操作"。
HTTP_METHODS = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)

# info 里必须逐字一致的字段。title/description 是**对外身份口径**，
# 历史上出现过"快照写 408 老身份、main.py 早已改掉"的不一致（提交 a6502d4 修的）。
INFO_FIELDS = ("title", "description", "version")


@pytest.fixture(scope="module")
def runtime_spec() -> dict:
    """取运行时 OpenAPI。

    import 失败 → **明确失败**（不 skip）。理由见模块 docstring：
    环境问题若静默跳过，这道闸就成了永远绿的假闸门。
    """
    py_dir = str(REPO_ROOT / "py-server")
    if py_dir not in sys.path:
        sys.path.insert(0, py_dir)

    import os

    prev_cwd = os.getcwd()
    try:
        os.chdir(py_dir)
        try:
            from main import app  # noqa: PLC0415
        except Exception as e:  # noqa: BLE001
            pytest.fail(
                f"无法导入 py-server/main.py 的 app：{type(e).__name__}: {e}\n"
                "本测试**刻意不使用 skip**（skip 会让契约闸形同虚设）。\n"
                "请用项目虚拟环境运行：cd py-server && "
                ".venv/Scripts/python.exe -m pytest tests/test_openapi_snapshot_freshness.py"
            )
        return app.openapi()
    finally:
        os.chdir(prev_cwd)


@pytest.fixture(scope="module")
def snapshot_spec() -> dict:
    """读取随包快照。缺失/非法 → 明确失败。"""
    assert SNAPSHOT_PATH.is_file(), (
        f"契约快照缺失：{SNAPSHOT_PATH}；"
        "它是对外契约的冻结快照，必须入库并随源码包发出"
    )
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:  # pragma: no cover - 仅在文件损坏时触发
        pytest.fail(f"契约快照不是合法 JSON：{SNAPSHOT_PATH}（{e}）")


def _ops(spec: dict) -> dict[str, set[str]]:
    """{路径: 该路径上的 method 集合}，只认 HTTP method 键。"""
    return {
        path: {m.lower() for m in item if m.lower() in HTTP_METHODS}
        for path, item in (spec.get("paths") or {}).items()
        if isinstance(item, dict)
    }


def test_snapshot_path_count_matches_runtime(snapshot_spec, runtime_spec):
    """路径条数必须一致（227）。少一条就是"快照落后于路由"的经典形态。"""
    s_paths = set((snapshot_spec.get("paths") or {}))
    r_paths = set((runtime_spec.get("paths") or {}))

    missing = sorted(r_paths - s_paths)
    extra = sorted(s_paths - r_paths)

    assert not missing, (
        f"快照缺少 {len(missing)} 条运行时已存在的路径：{missing}\n"
        "处置：重生成快照 —— cd py-server && python -c \"import json;"
        "from main import app;open('openapi.json','w',encoding='utf-8',newline='')"
        ".write(json.dumps(app.openapi(),ensure_ascii=False,indent=2))\""
    )
    assert not extra, (
        f"快照多出 {len(extra)} 条运行时已不存在的路径（路由被删/改名？）：{extra}\n"
        "若确认是有意删除，请同步重生成快照"
    )


def test_snapshot_operation_count_matches_runtime(snapshot_spec, runtime_spec):
    """操作数必须一致（244）。同一路径上的 GET/POST 分别计。"""
    s_ops, r_ops = _ops(snapshot_spec), _ops(runtime_spec)
    s_total = sum(len(v) for v in s_ops.values())
    r_total = sum(len(v) for v in r_ops.values())

    assert s_total == r_total, (
        f"操作数不一致：快照 {s_total} vs 运行时 {r_total}（相差 {s_total - r_total}）\n"
        "路径数一致但操作数不一致，通常是某条路径少了/多了 method，"
        "请逐条核对后重生成快照"
    )


def test_snapshot_methods_match_runtime_per_path(snapshot_spec, runtime_spec):
    """每条路径的 method 集合必须逐一对应。"""
    s_ops, r_ops = _ops(snapshot_spec), _ops(runtime_spec)

    problems: list[str] = []
    for path in sorted(set(s_ops) & set(r_ops)):
        sm, rm = s_ops[path], r_ops[path]
        for m in sorted(rm - sm):
            problems.append(f"方法缺失: {m.upper()} {path}")
        for m in sorted(sm - rm):
            problems.append(f"方法多余: {m.upper()} {path}")

    assert not problems, "method 级漂移：\n  " + "\n  ".join(problems)


def test_snapshot_info_identity_matches_runtime(snapshot_spec, runtime_spec):
    """对外身份口径（title/description/version）必须与运行时逐字一致。

    这条最关键：快照会随包发给评委，身份一旦回退成"408 考研个性化学习系统"
    之类旧口径，就是对外材料自相矛盾。title/description 用 repr 比较并附上
    截断后的实际值，便于一眼看出差在哪。
    """
    s_info = snapshot_spec.get("info") or {}
    r_info = runtime_spec.get("info") or {}

    mismatches = [
        f"info.{field} 不一致\n      快照: {str(s_info.get(field))[:120]!r}\n"
        f"      运行时: {str(r_info.get(field))[:120]!r}"
        for field in INFO_FIELDS
        if s_info.get(field) != r_info.get(field)
    ]
    assert not mismatches, (
        "对外身份口径漂移：\n  " + "\n  ".join(mismatches)
        + "\n处置：重生成快照（它直接来自 main.py 的 FastAPI 配置）"
    )


def test_snapshot_identity_is_not_stale_408_wording(snapshot_spec):
    """快照身份不得回退到已废弃的"408 考研"旧口径。

    与上一条互补：上一条比"快照 vs 运行时"，本条直接钉死**已知坏值**。
    万一有人同时改了 main.py 和快照（本该被上一条抓住，但若两处都错则一起错），
    这条仍能拦住。
    """
    info = snapshot_spec.get("info") or {}
    title = str(info.get("title") or "")
    description = str(info.get("description") or "")

    for field, value in (("title", title), ("description", description)):
        assert "408" not in value, (
            f"info.{field} 含已废弃的『408 考研』旧口径：{value[:120]!r}\n"
            "当前对外身份应为『计算机类学生职业素养对抗实训平台』"
        )


def test_snapshot_operation_details_match_runtime(snapshot_spec, runtime_spec):
    """operation 详情（description/parameters/responses 等）也必须一致。

    只比路径数量是不够的：改一个 operation 的 description（对外文案）、
    增删一个 query 参数、请求体换 schema 引用，在路径集合层面完全看不出来，
    但同样会让评委按契约核对时对不上。
    """
    s_paths = snapshot_spec.get("paths") or {}
    r_paths = runtime_spec.get("paths") or {}
    canon = lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)  # noqa: E731

    problems: list[str] = []
    for path in sorted(set(s_paths) & set(r_paths)):
        s_item, r_item = s_paths[path], r_paths[path]
        for method in sorted(set(s_item) & set(r_item)):
            if method.lower() not in HTTP_METHODS:
                continue
            s_op, r_op = s_item[method], r_item[method]
            if not isinstance(s_op, dict) or not isinstance(r_op, dict):
                continue
            changed = sorted(
                k for k in set(s_op) | set(r_op)
                if canon(s_op.get(k)) != canon(r_op.get(k))
            )
            if changed:
                problems.append(f"{method.upper()} {path} 字段: {', '.join(changed)}")

    assert not problems, (
        "operation 详情漂移（对外文案/参数/请求体/响应变了）：\n  "
        + "\n  ".join(problems[:40])
        + ("\n  …（已截断）" if len(problems) > 40 else "")
    )


def test_snapshot_schemas_match_runtime(snapshot_spec, runtime_spec):
    """components/schemas 的键集合必须一致（改名也算漂移）。

    2026-10-06 实锤：新增一条同名 `AnswerRequest` 后，FastAPI 的冲突消歧把
    旧 schema 重命名为 `api__career_training__AnswerRequest`。这类变化若只比
    paths 数量则完全不可见，但前端 `src/types/api.generated.ts` 是从快照生成的，
    漂了就会类型不一致。
    """
    s_schemas = set(((snapshot_spec.get("components") or {}).get("schemas") or {}))
    r_schemas = set(((runtime_spec.get("components") or {}).get("schemas") or {}))

    missing = sorted(r_schemas - s_schemas)
    extra = sorted(s_schemas - r_schemas)

    assert not missing, f"快照缺少 schema：{missing}\n请重生成快照"
    assert not extra, f"快照多出 schema：{extra}\n请重生成快照"
