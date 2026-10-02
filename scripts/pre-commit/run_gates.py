#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""六道门禁的**统一编排器** —— 本地与 CI 跑同一套闸门。

为什么要有它
--------------------------------------------------------------------------
门禁本体在 `scripts/pre-commit/*.py`，触发点在 `pre-commit.sh`（安装到 .git/hooks）。
这条链路只覆盖 **本地提交**，CI 上一片空白。直接把 pre-commit.sh 搬进 CI 是错的：

    pre-commit.sh 的每一步都从 **git 暂存区** 取文件（`--cached`）。
    CI checkout 之后工作区 == HEAD，**暂存区永远为空**
    → 每道门禁都拿到空列表 → 什么都没检查却返回 0
    → CI 上挂六个永远绿的假闸门（比没有更糟：它制造虚假安全感）

本编排器把「待检查文件集从哪来」作为唯一变量，六个脚本本身不动、语义不变：

    文件集来源            适用场景                    用途
    --------------------  --------------------------  ------------------------
    --diff <ref>          PR（对比 base）             CI 主路径：只查本次改动
    --all                 push 兜底 / 首次全量体检      全树已跟踪文件
    --staged              本地等价于 pre-commit.sh     在本机复现 CI 结论

用法
--------------------------------------------------------------------------
    python scripts/pre-commit/run_gates.py --all              # 全量体检
    python scripts/pre-commit/run_gates.py --diff origin/main # 只查相对 main 的改动
    python scripts/pre-commit/run_gates.py --staged           # 本机查暂存区（等价于提交时）
    python scripts/pre-commit/run_gates.py --diff HEAD~1 --quiet

退出码：0=六道全通过；1=至少一道拦截；2=用法/环境错误（与被门禁拦下区分开）。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

GATES_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATES_DIR.parents[1]

# 单次命令行 / 环境变量的长度上限（Windows 命令行 ~8191、环境变量块 ~32K，取保守值）。
# 超限则分批（可分批的门禁）或显式跳过（语义不允许分批的门禁）——
# **绝不静默当成通过**，见 _run_with_injection。
_MAX_ARGV_CHARS = 6000
_MAX_ARGV_N = 200


class Colors:
    """CI 日志无颜色需求，仅在 TTY 下着色，避免日志里混 ANSI 转义。"""
    OK = "\033[32m" if sys.stdout.isatty() and os.name != "nt" else ""
    FAIL = "\033[31m" if sys.stdout.isatty() and os.name != "nt" else ""
    DIM = "\033[2m" if sys.stdout.isatty() and os.name != "nt" else ""
    RESET = "\033[0m" if OK else ""


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=REPO_ROOT, stderr=subprocess.DEVNULL, text=True
    )


def resolve_files(mode: str, ref: str | None, added_only: bool = False) -> list[str]:
    """按模式解析待检查文件集。返回 posix 风格路径。

    added_only=True 时只取 **新增（A）** 文件——结构守卫专用，见 [4/6] 处的说明。
    """
    filt = "--diff-filter=A" if added_only else "--diff-filter=ACMR"
    try:
        if mode == "diff":
            out = _git("-c", "core.quotePath=false", "diff", "--name-only", filt, ref)
        elif mode == "staged":
            out = _git("-c", "core.quotePath=false", "diff", "--cached",
                       "--name-only", filt)
        else:  # all
            out = _git("-c", "core.quotePath=false", "ls-files")
    except Exception as e:
        print(f"❌ 无法解析文件集（mode={mode} ref={ref}）：{e}", file=sys.stderr)
        sys.exit(2)
    return [f.strip().replace("\\", "/") for f in out.splitlines() if f.strip()]


def _chunks(files: list[str]):
    """把文件集切成命令行放得下的批次。"""
    cur: list[str] = []
    cur_len = 0
    for f in files:
        if cur and (cur_len + len(f) + 1 > _MAX_ARGV_CHARS or len(cur) >= _MAX_ARGV_N):
            yield cur
            cur, cur_len = [], 0
        cur.append(f)
        cur_len += len(f) + 1
    if cur:
        yield cur


def _run(py: str, argv: list[str], env: dict | None = None) -> int:
    r = subprocess.run([py, *argv], cwd=str(REPO_ROOT), env=env)
    return r.returncode


def _run_over_files(py: str, script: str, files: list[str], extra: list[str] | None = None) -> tuple[int, list[str]]:
    """可分批改用的门禁：把文件分批喂给它。返回 (最坏 rc, 备注)。"""
    if not files:
        return 0, ["无待检查文件"]
    worst = 0
    n = 0
    for chunk in _chunks(files):
        n += 1
        rc = _run(py, [str(GATES_DIR / script), *(extra or []), *chunk])
        worst = max(worst, rc)
    note = f"{len(files)} 文件 / {n} 批"
    return worst, [note]


def _run_with_injection(py: str, script: str, files: list[str], extra: list[str]) -> tuple[int, list[str]]:
    """语义上不可分批改用的门禁（它判断的是"这批文件整体"的性质）。

    通过环境变量整体注入。注入体超长时**显式跳过并告警**，不静默当通过——
    假绿是这类门禁最坏的失败模式。
    """
    if str(GATES_DIR) not in sys.path:
        sys.path.insert(0, str(GATES_DIR))
    from _gate_files import GATE_FILES_ENV

    payload = "\n".join(files)
    if len(payload) > 20000:
        return 0, [f"⚠️ 跳过：文件集过大（{len(payload)} 字符 > 20000），环境变量放不下；"
                   f"本门禁需整体判定，无法分批。请改用 --diff 缩小改动范围"]
    env = dict(os.environ)
    env[GATE_FILES_ENV] = payload
    rc = _run(py, [str(GATES_DIR / script), *extra], env=env)
    return rc, [f"{len(files)} 文件（整体注入 {GATE_FILES_ENV}）"]


def main() -> int:
    ap = argparse.ArgumentParser(description="六道门禁编排器（本地 / CI 两用）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--diff", metavar="REF", help="对比该 ref 的改动（PR 场景：传 base sha）")
    g.add_argument("--all", action="store_true", help="全量：所有已跟踪文件")
    g.add_argument("--staged", action="store_true", help="暂存区（等价于本地提交时）")
    ap.add_argument("--quiet", action="store_true", help="只输出结论行")
    args = ap.parse_args()

    mode = "diff" if args.diff else ("staged" if args.staged else "all")
    files = resolve_files(mode, args.diff)

    py = ""
    for cand in (os.environ.get("PYTHON"), "python3", "python"):
        if not cand:
            continue
        try:
            subprocess.run([cand, "-c", "pass"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
            py = cand
            break
        except Exception:
            continue
    if not py:
        print("❌ 未找到可用的 python 解释器（可用 PYTHON=/path/to/python 指定）", file=sys.stderr)
        return 2

    def say(msg: str, always: bool = False):
        if always or not args.quiet:
            print(msg)

    say(f"== 门禁编排器 ==")
    say(f"模式       : {mode}" + (f"（base={args.diff}）" if args.diff else ""))
    say(f"待检文件   : {len(files)}")
    say(f"解释器     : {py}")
    say("")

    results: list[tuple[str, int, str]] = []

    def record(name: str, rc: int, note: str):
        results.append((name, rc, note))
        mark = f"{Colors.OK}✅ 通过{Colors.RESET}" if rc == 0 else f"{Colors.FAIL}❌ 拦截{Colors.RESET}"
        say(f"[{len(results)}/6] {name}: {mark}  {Colors.DIM}{note}{Colors.RESET}", always=True)

    t0 = time.time()

    say("=== [1/6] 密钥扫描 ===")
    rc, notes = _run_over_files(py, "secrets_scan.py", files)
    record("密钥扫描", rc, " ".join(notes))

    say("=== [2/6] 诚实口径（含对外红线） ===")
    rc, notes = _run_over_files(py, "honesty_scan.py", files)
    record("诚实口径", rc, " ".join(notes))

    say("=== [3/6] 口径数字（告警，不阻断） ===")
    rc, notes = _run_over_files(py, "caliber_check.py", files)
    record("口径数字", rc, " ".join(notes))

    say("=== [4/6] 结构守卫（只判本次新增） ===")
    # ⚠️ 这里刻意不用 --all：那是全树清算，会把历史遗留的根级散落一起算违规，
    #    CI 一接就永久红。CI 必须与本地同语义——只拦"本次新增"的平铺文件。
    #    历史债请另行清理，不应由一个门禁在 CI 上引爆。
    added = resolve_files(mode, args.diff, added_only=True)
    rc, notes = _run_with_injection(py, "structure_guard.py", added, [])
    record("结构守卫", rc, f"新增 {len(added)} 文件" + ("；" + " ".join(notes) if notes else ""))

    say("=== [5/6] ruff 潜在缺陷 ===")
    rc, notes = _run_with_injection(py, "f401_gate.py", files, [])
    record("ruff 潜在缺陷", rc, " ".join(notes))

    say("=== [6/6] 测试文件禁改 ===")
    rc, notes = _run_with_injection(py, "test_file_guard.py", files, ["--staged"])
    record("测试文件禁改", rc, " ".join(notes))

    dt = time.time() - t0

    say("")
    failed = [r for r in results if r[1] != 0]
    say("=" * 56, always=True)
    if failed:
        say(f"❌ 六道门禁：{len(failed)} 道未通过（耗时 {dt:.1f}s）", always=True)
        for name, rc, _ in failed:
            say(f"   - {name} (exit {rc})", always=True)
        return 1
    say(f"✅ 六道门禁全部通过（耗时 {dt:.1f}s）", always=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
