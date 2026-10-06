#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenAPI 契约漂移闸：冻结快照必须与运行时真实能力逐项一致。

背景（这道闸是为了治哪种病）
--------------------------------------------------------------------------
`py-server/openapi.json` 是 **随源码包发给评委**的对外契约快照。它历史上两次
悄悄落后于运行时：

    * 2026-09-28 审查记录：快照比运行时少 4 条 `/api/cn-distinction` 路径；
    * 2026-10-06 交付前实测：快照 223 paths / 240 operations，
      而 `app.openapi()` 已经是 227 / 244。

两次的共同点是**完全静默**：源码改了、测试全绿、门禁全绿，只有评委拿快照
核对接口清单时才会发现对不上。而"快照"一旦落后，所有对外材料引用的数字
就与包内契约自相矛盾。

设计取舍
--------------------------------------------------------------------------
* **fail-closed，不设"警告但通过"的中间态**。漂移就是漂移，放行等于假绿 ——
  这与仓库既有立场一致（见 `run_gates.py` 关于"假绿是最坏失败模式"的说明）。
* **必须报出具体差异**，而不是"不一致"三个字。维护者要能据此判断是"忘了
  重生成快照"还是"路由真的删了"，所以逐条列出：缺/多哪条路径、哪个 method、
  哪个 operation 的哪个字段、info 哪个字段、哪个 schema。
* **比对深度到 operation 详情**，不只比路径集合：改一个 operation 的
  description（对外文案）、增删一个 query 参数、请求体换 schema 引用，
  在路径集合层面完全看不出来，但同样会让评委按契约核对时对不上。
  仅比 paths 集合的版本已实测漏掉了这类漂移（变异测试2 因此被抓住并补上）。
* **--snapshot 供打包器复用于包内文件**：`build_portable.py` 打包完成后把
  包内那份抽出来比对，从而把"改了没到包内"变成打包失败（exit 1），
  而不是等评委发现。
* **不 import 业务逻辑之外的任何东西**，只依赖 fastapi/pydantic（应用自身
  必需依赖），故在只有 venv 的干净环境同样可跑。

用法
--------------------------------------------------------------------------
    # 用法 A：校验仓库内快照（默认路径）
    py-server/.venv/Scripts/python.exe scripts/verify_openapi_snapshot.py

    # 用法 B：校验任意一份快照文件（打包器对包内文件用这个）
    py-server/.venv/Scripts/python.exe scripts/verify_openapi_snapshot.py \\
        --snapshot <解压出来的 openapi.json>

退出码
--------------------------------------------------------------------------
    0 = 一致
    1 = 存在漂移（已打印逐条差异）
    2 = 用法/环境错误（快照文件不存在、JSON 非法、无法导入 app 等）
        —— 与"被漂移拦下"区分开，避免把环境问题误读成契约问题。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = REPO_ROOT / "py-server" / "openapi.json"
PY_SERVER_DIR = REPO_ROOT / "py-server"

# OpenAPI 里表示「操作」的 method 键。其余键（parameters/summary/...）不是操作。
HTTP_METHODS = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)

# info 里必须逐字一致的字段。title/description 是**对外身份口径**——
# 历史上出现过"快照写 408 老身份、main.py 已改"的不一致（提交 a6502d4 修的），
# 所以这两个字段进闸，避免身份回退无人察觉。
INFO_FIELDS = ("title", "description", "version")

# 单次最多打印多少条差异，避免一次漂移刷出上千行把 CI 日志淹掉。
MAX_REPORTED = 40


def _fail_env(msg: str) -> int:
    """环境/用法类问题：exit 2，与"漂移"（exit 1）严格区分。"""
    print(f"❌ [openapi漂移] 环境错误：{msg}", file=sys.stderr)
    return 2


def load_snapshot(path: Path) -> dict[str, Any]:
    """读取并解析快照文件。失败即 exit 2（环境问题，不是漂移）。"""
    if not path.is_file():
        raise FileNotFoundError(f"快照文件不存在：{path}")
    raw = path.read_text(encoding="utf-8-sig")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"快照不是合法 JSON：{path}（{e}）") from e
    if not isinstance(data, dict) or "paths" not in data:
        raise ValueError(f"快照结构异常（缺 paths）：{path}")
    return data


def load_runtime() -> dict[str, Any]:
    """导入真实应用并取运行时 OpenAPI。

    必须在 py-server/ 下导入 `main`，故临时前置 sys.path。
    导入失败属环境问题（缺依赖 / 没装 venv）→ 由调用方转成 exit 2。
    """
    py_dir = str(PY_SERVER_DIR)
    if py_dir not in sys.path:
        sys.path.insert(0, py_dir)
    # 切换工作目录：部分模块用相对路径读 app_config/ 等资源。
    import os

    prev_cwd = os.getcwd()
    try:
        os.chdir(py_dir)
        from main import app  # noqa: PLC0415  (需在 chdir 之后导入)

        return app.openapi()
    finally:
        os.chdir(prev_cwd)


def _ops(doc: dict[str, Any]) -> dict[str, set[str]]:
    """{路径: 该路径上的 method 集合}，只认 HTTP method 键。"""
    out: dict[str, set[str]] = {}
    for path, item in (doc.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        out[path] = {m.lower() for m in item if m.lower() in HTTP_METHODS}
    return out


def diff_snapshots(snap: dict[str, Any], live: dict[str, Any]) -> list[str]:
    """返回人类可读的差异条目列表；空列表表示一致。"""
    diffs: list[str] = []

    # --- 1. info：对外身份口径 ---
    s_info = snap.get("info") or {}
    l_info = live.get("info") or {}
    for field in INFO_FIELDS:
        sv, lv = s_info.get(field), l_info.get(field)
        if sv != lv:
            diffs.append(
                f"info.{field} 不一致\n"
                f"      快照: {_short(sv)}\n"
                f"      运行时: {_short(lv)}"
            )

    s_ops, l_ops = _ops(snap), _ops(live)

    # --- 2. 路径级：缺 / 多 ---
    only_snap = sorted(set(s_ops) - set(l_ops))
    only_live = sorted(set(l_ops) - set(s_ops))
    for p in only_live:
        diffs.append(
            f"路径缺失（运行时有、快照无）: {p}"
            f"  [methods: {', '.join(sorted(l_ops[p])) or '无'}]"
        )
    for p in only_snap:
        diffs.append(
            f"路径多余（快照有、运行时无）: {p}"
            f"  [methods: {', '.join(sorted(s_ops[p])) or '无'}]"
        )

    # --- 3. method 级：共有路径上的方法集合差异 ---
    for p in sorted(set(s_ops) & set(l_ops)):
        sm, lm = s_ops[p], l_ops[p]
        if sm == lm:
            continue
        for m in sorted(lm - sm):
            diffs.append(f"方法缺失: {m.upper()} {p}")
        for m in sorted(sm - lm):
            diffs.append(f"方法多余: {m.upper()} {p}")

    # --- 4. operation 级：路径与方法都齐了，但**详情**漂了 ---
    # 只比路径/方法集合是不够的：改一个 operation 的 description（对外文案）、
    # 增删一个 query 参数、请求体 schema 换引用，集合层面完全看不出来，
    # 而这些同样会让评委按契约核对时对不上。故逐个 operation 深比对。
    for p in sorted(set(s_ops) & set(l_ops)):
        s_item = (snap.get("paths") or {}).get(p) or {}
        l_item = (live.get("paths") or {}).get(p) or {}
        for m in sorted(s_ops[p] & l_ops[p]):
            s_op, l_op = s_item.get(m), l_item.get(m)
            if not isinstance(s_op, dict) or not isinstance(l_op, dict):
                continue
            changed = _changed_keys(s_op, l_op)
            if changed:
                diffs.append(
                    f"operation 详情不一致: {m.upper()} {p}"
                    f"  [字段: {', '.join(changed)}]"
                )

    # --- 5. components/schemas：schema 改名/增删也属契约变更 ---
    # 2026-10-06 实锤：新增一条同名 AnswerRequest 后，FastAPI 的冲突消歧把
    # 旧 schema 重命名为 `api__career_training__AnswerRequest`，
    # 若只比 paths 数量则完全不可见。
    s_schemas = ((snap.get("components") or {}).get("schemas") or {})
    l_schemas = ((live.get("components") or {}).get("schemas") or {})
    for name in sorted(set(l_schemas) - set(s_schemas)):
        diffs.append(f"schema 缺失（运行时有、快照无）: components/schemas/{name}")
    for name in sorted(set(s_schemas) - set(l_schemas)):
        diffs.append(f"schema 多余（快照有、运行时无）: components/schemas/{name}")

    return diffs


def _changed_keys(s_op: dict[str, Any], l_op: dict[str, Any]) -> list[str]:
    """返回该 operation 内**值不一致**的字段名（用规范化 JSON 比，避免键序误报）。"""
    changed: list[str] = []
    keys = set(s_op) | set(l_op)
    for k in sorted(keys):
        sv = _canon(s_op.get(k))
        lv = _canon(l_op.get(k))
        if sv != lv:
            changed.append(k)
    return changed


def _canon(value: Any) -> str:
    """规范化 JSON 文本，用于"值相等"判断（键序无关）。"""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _short(value: Any, limit: int = 160) -> str:
    """把值压成单行可打印形式（description 是整段 markdown，必须截断）。"""
    if value is None:
        return "<缺失>"
    text = str(value).replace("\n", "\\n")
    if len(text) > limit:
        text = text[:limit] + f"…（共 {len(str(value))} 字符）"
    return repr(text)


def _counts(doc: dict[str, Any]) -> tuple[int, int]:
    ops = _ops(doc)
    return len(ops), sum(len(v) for v in ops.values())


def main() -> int:
    ap = argparse.ArgumentParser(
        description="OpenAPI 契约漂移闸：快照必须与运行时真实能力一致（fail-closed）"
    )
    ap.add_argument(
        "--snapshot",
        metavar="PATH",
        default=None,
        help="要校验的快照文件路径（默认 py-server/openapi.json）；"
             "打包器可用它校验包内那份",
    )
    args = ap.parse_args()

    snap_path = Path(args.snapshot).resolve() if args.snapshot else DEFAULT_SNAPSHOT

    # --- 载入快照 ---
    try:
        snap = load_snapshot(snap_path)
    except FileNotFoundError as e:
        return _fail_env(str(e))
    except ValueError as e:
        return _fail_env(str(e))

    # --- 载入运行时 ---
    try:
        live = load_runtime()
    except ModuleNotFoundError as e:
        return _fail_env(
            f"无法导入应用依赖（{e}）。请用项目虚拟环境运行："
            f"py-server/.venv/Scripts/python.exe scripts/verify_openapi_snapshot.py"
        )
    except Exception as e:  # noqa: BLE001 - 任何导入期异常都属环境问题
        return _fail_env(f"导入 main 失败：{type(e).__name__}: {e}")

    sp, so = _counts(snap)
    lp, lo = _counts(live)

    diffs = diff_snapshots(snap, live)

    if not diffs:
        print(
            f"✅ [openapi漂移] 快照与运行时一致："
            f"{lp} paths / {lo} operations"
            f"（{snap_path.name}）"
        )
        return 0

    print(
        f"❌ [openapi漂移] 快照已漂移："
        f"{len(diffs)} 处差异（快照 {sp} paths / {so} ops"
        f" vs 运行时 {lp} paths / {lo} ops）",
        file=sys.stderr,
    )
    print(f"   快照文件：{snap_path}", file=sys.stderr)
    shown = diffs[:MAX_REPORTED]
    for i, d in enumerate(shown, 1):
        print(f"   {i:>2}. {d}", file=sys.stderr)
    if len(diffs) > MAX_REPORTED:
        print(
            f"   …（另有 {len(diffs) - MAX_REPORTED} 处差异未显示）",
            file=sys.stderr,
        )
    print(
        "\n   处置：若运行时是对的（新增/删除了路由），重新生成快照：\n"
        "     cd py-server && python -c \"import json;from main import app;"
        "open('openapi.json','w',encoding='utf-8',newline='').write("
        "json.dumps(app.openapi(),ensure_ascii=False,indent=2))\"\n"
        "   注意：重生成后必须同步重打包（scripts/build_portable.py），"
        "否则包内仍是旧快照。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
