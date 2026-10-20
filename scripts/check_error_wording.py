#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""check_error_wording.py — 禁止把内部异常原文直出给客户端（2026-10-20，REA #170）

背景
----
``api/auth.py`` 曾用 ``ValidationError(detail=str(e))`` 把 db 层的原始异常
（含字段名、约束名，甚至库版本特征）原样透给前端。2026-10-20 已改为
「白名单分类文案 + 原文只进 log_event」。但**修一次不等于守住**：下一个人
复制粘贴旧写法，泄露面就回来了，而代码评审不总会盯着 detail。

本门禁把这条红线变成可执行的静态检查：命中即拦截，并给出改法。

判定口径（只拦确定的直出，不猜）
--------------------------------
  1. ``ValidationError(detail=str(...))``        —— 异常原文直出
  2. ``HTTPException(... detail=str(...) ...)``  —— 同上，FastAPI 另一出口
  3. ``detail=f"...{e}..."`` / ``detail=f"...{exc}..."`` —— f-string 拼接原文

不拦：``detail="固定文案"``、``detail=exc.args[0]``（需人工看，静态无法判定
是否有害）、日志调用（log_event/logger 本就该记原文）。

用法::

    python scripts/check_error_wording.py --root py-server
    python scripts/check_error_wording.py --root py-server --strict   # 存量也拦
    python scripts/check_error_wording.py --root py-server --write-baseline
    python scripts/check_error_wording.py --self-test     # 自测（变异式夹具）

基线制（2026-10-20 首次扫描有 38 处存量）
-----------------------------------------
门禁一旦上线就永久红，等于逼人 `--no-verify` 绕过——那比没有门禁更糟。
故采用基线：存量登记在 ``scripts/error_wording_baseline.json``（带生成日期），
**只拦新增**；存量清零后把 ``--strict`` 打开，基线文件即可删除。

退出码：0 干净（或仅存量） / 1 有新增命中（--strict 下含存量） / 2 用法错误。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

PATTERNS = [
    (re.compile(r"ValidationError\s*\(\s*detail\s*=\s*str\s*\("),
     "ValidationError(detail=str(...))：异常原文直出"),
    (re.compile(r"HTTPException\s*\([^)]*detail\s*=\s*str\s*\("),
     "HTTPException(detail=str(...))：异常原文直出"),
    (re.compile(r"detail\s*=\s*f[\"'][^\"']*\{e(xc)?\b"),
     "detail=f\"...{e}...\"：f-string 拼接异常原文"),
]

SKIP_DIR_NAMES = {".git", "__pycache__", "node_modules", ".venv", "venv",
                  "dist", "build", ".mypy_cache", ".pytest_cache", "tests"}

FIX_HINT = (
    "改法：对外只给分类文案（如「用户名已被占用」「输入不合法」），"
    "原文写进 log_event(..., detail=str(e)) 供服务端排查——"
    "客户端不该看到内部异常文本。参考 api/auth.py 的 _register_error_message。"
)


def sha12(text: str) -> str:
    """行内容指纹：基线按「文件 + 行内容」登记，行号漂移不影响判定。"""
    return sha256(text.encode("utf-8")).hexdigest()[:12]


def iter_files(root: Path, include_tests: bool):
    for p in root.rglob("*.py"):
        if any(part in SKIP_DIR_NAMES for part in p.parts):
            if not (include_tests and "tests" in p.parts):
                continue
            if any(part in SKIP_DIR_NAMES - {"tests"} for part in p.parts):
                continue
        yield p


def scan_text(text: str, name: str = "<inline>"):
    """返回 [(name, lineno, pattern_desc, line_text)]。"""
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        for pat, desc in PATTERNS:
            if pat.search(line):
                hits.append((name, lineno, desc, line.strip()))
                break
    return hits


def scan_root(root: Path, include_tests: bool = False):
    hits = []
    for f in iter_files(root, include_tests):
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits.extend(scan_text(text, str(f)))
    return hits


# ---------------------------------------------------------------- 自测
_SELFTEST_CASES = {
    "bad_validation.py": (
        "def f(e):\n"
        "    raise ValidationError(detail=str(e))\n", 1),
    "bad_http.py": (
        "def f(e):\n"
        "    raise HTTPException(status_code=400, detail=str(e))\n", 1),
    "bad_fstring.py": (
        "def f(e):\n"
        "    raise HTTPException(status_code=400, detail=f\"失败: {e}\")\n", 1),
    "ok_fixed.py": (
        "def f(e):\n"
        "    log_event('x', detail=str(e))\n"
        "    raise ValidationError(detail='输入不合法')\n", 0),
}


def self_test() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for name, (body, expected) in _SELFTEST_CASES.items():
            (root / name).write_text(body, encoding="utf-8")
            hits = scan_root(root)
            got = len([h for h in hits if h[0].endswith(name)])
            mark = "✅" if got == expected else "❌"
            if got != expected:
                failures += 1
            print(f"{mark} {name}: 命中 {got}（期望 {expected}）")
    print(f"\n自测{'通过' if failures == 0 else f'失败 {failures} 项'}（{len(_SELFTEST_CASES)} 例）")
    return 0 if failures == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="错误文案直出静态守卫")
    ap.add_argument("--root", default="py-server", help="扫描根目录（默认 py-server）")
    ap.add_argument("--include-tests", action="store_true", help="也扫 tests/（默认跳过）")
    ap.add_argument("--baseline", default="scripts/error_wording_baseline.json",
                    help="存量基线文件（默认 scripts/error_wording_baseline.json；不存在=无存量）")
    ap.add_argument("--write-baseline", action="store_true", help="把当前命中写成基线后退出")
    ap.add_argument("--strict", action="store_true", help="存量也算失败（债务清零后启用）")
    ap.add_argument("--self-test", action="store_true", help="跑内置自测后退出")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    root = Path(args.root)
    if not root.is_dir():
        print(f"[FAIL] 扫描根不存在: {root}", file=sys.stderr)
        return 2

    hits = scan_root(root, args.include_tests)
    baseline_path = Path(args.baseline)

    if args.write_baseline:
        payload = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "note": "存量登记（REA #144/#170）：只拦新增；清零后改用 --strict 并删除本文件",
            "entries": sorted({f"{h[0].replace(chr(92), '/')}#{sha12(h[3])}" for h in hits}),
        }
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        print(f"[ok] 基线已写入 {baseline_path}（{len(payload['entries'])} 条，"
              f"生成日期 {payload['generated_at']}）")
        return 0

    legacy: set[str] = set()
    if baseline_path.is_file():
        try:
            legacy = set(json.loads(baseline_path.read_text(encoding="utf-8")).get("entries", []))
        except Exception as e:  # noqa: BLE001
            print(f"[FAIL] 基线文件损坏（{e}）——先修复或重新 --write-baseline", file=sys.stderr)
            return 2

    def key(h):
        return f"{h[0].replace(chr(92), '/')}#{sha12(h[3])}"

    new_hits = [h for h in hits if key(h) not in legacy]
    known_hits = [h for h in hits if key(h) in legacy]
    stale = legacy - {key(h) for h in hits}

    if not hits:
        print(f"[ok] 未发现异常原文直出（扫描 {root}，"
              f"{'含' if args.include_tests else '不含'} tests/）")
        if stale:
            print(f"[note] 基线有 {len(stale)} 条已不存在（可 --write-baseline 收缩）")
        return 0

    if new_hits:
        print(f"[FAIL] 发现 {len(new_hits)} 处**新增**异常原文直出：")
        for name, lineno, desc, text in new_hits:
            print(f"  {Path(name).as_posix()}:{lineno}  {desc}")
            print(f"      {text}")
        print("\n" + FIX_HINT)
        print(f"\n（另有存量 {len(known_hits)} 处已登记在基线，不阻断；"
              f"清单见 {baseline_path}）")
        return 1

    msg = f"[ok] 无新增（存量 {len(known_hits)} 处已在基线登记，生成于基线文件）"
    print(msg)
    if stale:
        print(f"[note] 基线有 {len(stale)} 条已不存在（债务在减少，可 --write-baseline 收缩）")
    if args.strict and known_hits:
        print(f"[FAIL] --strict：存量 {len(known_hits)} 处也计失败")
        for name, lineno, desc, _t in known_hits:
            print(f"  {Path(name).as_posix()}:{lineno}  {desc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
