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
import tempfile
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

    ⚠️ added_only 只在 diff / staged 模式生效：all 模式返回 `git ls-files` 全树，
    而全树没有「本次新增」的概念，故该参数在 all 分支被**忽略**（2026-10-08 注明；
    调用方若在 all 模式下需要「只判新增」，必须先自行分派，见 [4/6] 的处理）。
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


def resolve_commits(mode: str, ref: str | None) -> list[str]:
    """本次范围内的 commit 列表 —— 供「提交粒度」语义的门禁使用。

    为什么需要：push 事件的 `before..HEAD` 可能跨越**多个 commit**。若把这些
    commit 的文件合成一个集合，粒度就错了：原本分两次提交（先实现、后测试）
    是合规的，合并视角下却变成"同集合含测试+实现"而被判违规。
    2026-10-03 CI 首次运行即因此误伤（commit 19f1738 / d7e5817 恰是刻意拆开的）。
    """
    if mode != "diff" or not ref:
        return []  # staged（尚未 commit）/ all（无范围）都没有 commit 概念
    try:
        out = _git("rev-list", f"{ref}..HEAD")
        return [s.strip() for s in out.splitlines() if s.strip()]
    except Exception:
        return []


def _run_per_commit(py: str, script: str, commits: list[str], extra: list[str]) -> tuple[int, list[str]]:
    """逐个 commit 判定（而不是把整个范围当一个变更集）。"""
    worst = 0
    bad = []
    for sha in commits:
        try:
            out = _git("show", "--name-only", "--format=", sha)
        except Exception:
            continue
        cfiles = [f.strip().replace("\\", "/") for f in out.splitlines() if f.strip()]
        if not cfiles:
            continue
        rc, _ = _run_with_injection(py, script, cfiles, extra)
        if rc != 0:
            worst = max(worst, rc)
            bad.append(sha[:8])
    note = f"{len(commits)} 个 commit 逐个判定"
    if bad:
        note += f"（触发于：{', '.join(bad)}）"
    return worst, [note]


def _chunks(files: list[str]):
    """把文件集切成命令行放得下的批次。

    2026-10-08 修：本函数体此前**重复了两遍**（复制粘贴残留）。它是 generator，
    第一段 yield 完后**继续执行第二段**，于是每个批次被 yield 两次 ——
    实测 `list(_chunks(500 个文件))` 得到 `[200,200,100,200,200,100]`（6 批，应为 3 批）。
    后果：可分批的门禁每批跑两遍（耗时翻倍），且 record 的「N 文件 / M 批」把 M 报成两倍。
    结论不影响（重复执行同一判定），故一直未被发现。
    """
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
    """可分批改用的门禁：把文件分批喂给它。返回 (最坏 rc, 备注)。

    显式清掉 GATE_FILES：本函数用 argv 传文件，而各门禁的 `_changed_files()` 会
    **优先**读 GATE_FILES 环境变量。若外层环境残留了它（例如人工 export 调试后
    忘了 unset），argv 会被静默覆盖 —— 判定口径随环境漂移，且没有任何提示。
    """
    if not files:
        return 0, ["无待检查文件（零覆盖）"]
    worst = 0
    n = 0
    env = dict(os.environ)
    env.pop("GATE_FILES", None)
    for chunk in _chunks(files):
        n += 1
        rc = _run(py, [str(GATES_DIR / script), *(extra or []), *chunk], env=env)
        worst = max(worst, rc)
    note = f"{len(files)} 文件 / {n} 批"
    return worst, [note]


def _run_with_injection(py: str, script: str, files: list[str], extra: list[str]) -> tuple[int, list[str]]:
    """语义上不可分批改用的门禁（它判断的是"这批文件整体"的性质）。

    文件集通过两条通道交给门禁，**判定一律真正执行**：
      - payload <= 20000 字符：环境变量 GATE_FILES（快，无临时文件）
      - payload >  20000 字符：临时文件 GATE_FILES_FILE（无长度限制）

    2026-10-08 修：此前超长时 `return 0`（放行）—— 与本函数 docstring 的
    「绝不静默当成通过」**直接矛盾**，且已在真实仓库复现后果：
      · `--all` 下 structure_guard 被喂 2222 个文件（payload 126477 字符）→ 跳过；
      · 待 push 的 42 个 commit 里有 2 个超限（`07338559` 852 文件 / 132102 字符，
        `8565085d` 160 文件 / 25276 字符）→ 它们的 test_file_guard 判定从未执行。
    现改用临时文件通道，判定真正跑起来；读取失败时 `_gate_files.injected_files()`
    显式抛错（fail-closed），不再退化成"空集 -> 通过"。
    """
    if str(GATES_DIR) not in sys.path:
        sys.path.insert(0, str(GATES_DIR))
    from _gate_files import GATE_FILES_ENV, GATE_FILES_FILE_ENV

    env = dict(os.environ)
    env.pop(GATE_FILES_ENV, None)
    env.pop(GATE_FILES_FILE_ENV, None)

    payload = "\n".join(files)
    if len(payload) > 20000:
        fd, tmp_path = tempfile.mkstemp(prefix="gate_files_", suffix=".txt")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(payload)
            env[GATE_FILES_FILE_ENV] = tmp_path
            rc = _run(py, [str(GATES_DIR / script), *extra], env=env)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return rc, [f"{len(files)} 文件（整体注入临时文件，{len(payload)} 字符）"]

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

    results: list[tuple[str, int, str, bool]] = []

    def record(name: str, rc: int, note: str, effective: bool = True):
        """effective=False 表示本道**在本次模式下未实际检查任何文件**。

        2026-10-08 新增：此前 record 只有 rc 一个维度，「检查过且放行」与
        「一道都没检查」在日志里都是 `✅ 通过`，无从分辨（零覆盖假绿）。
        """
        results.append((name, rc, note, effective))
        if rc != 0:
            mark = f"{Colors.FAIL}❌ 拦截{Colors.RESET}"
        elif not effective:
            mark = f"{Colors.DIM}—  未生效{Colors.RESET}"
        else:
            mark = f"{Colors.OK}✅ 通过{Colors.RESET}"
        say(f"[{len(results)}/6] {name}: {mark}  {Colors.DIM}{note}{Colors.RESET}", always=True)

    t0 = time.time()

    say("=== [1/6] 密钥扫描 ===")
    rc, notes = _run_over_files(py, "secrets_scan.py", files)
    record("密钥扫描", rc, " ".join(notes), effective=bool(files))

    say("=== [2/6] 诚实口径（含对外红线） ===")
    rc, notes = _run_over_files(py, "honesty_scan.py", files)
    record("诚实口径", rc, " ".join(notes), effective=bool(files))

    say("=== [3/6] 口径数字（告警，不阻断） ===")
    rc, notes = _run_over_files(py, "caliber_check.py", files)
    record("口径数字", rc, " ".join(notes), effective=bool(files))

    say("=== [4/6] 结构守卫（只判本次新增） ===")
    # 只拦「本次新增」的平铺文件，不做全树清算 —— 全树会把历史遗留的根级散落
    # 一起算违规，CI 一接就永久红；历史债请另行清理，不应由一个门禁在 CI 上引爆。
    # 2026-10-08 修两处（原实现有零覆盖缺口）：
    #  1) 原用 _run_with_injection（环境变量整体注入）→ 实测 --all 下喂 2222 个文件、
    #     payload 达 126477 字符，命中 20000 上限被放行。而本门禁的 violations_for()
    #     是**逐文件**判定，本就支持分批 —— 改用 _run_over_files 后不再有超长问题。
    #  2) --all 模式无法判定「本次新增」（resolve_files 的 all 分支返回全树，
    #     added_only 在该分支不生效）→ 显式标记「未生效」并打 ::warning::，
    #     而不是靠 payload 超长"意外"跳过、还在日志里显示 ✅ 通过。
    if mode == "all":
        print("::warning::结构守卫在 --all（全量）模式下不生效：该模式无法判定"
              "「本次新增」，而本道只拦本次新增的根级平铺文件。"
              "需要本道覆盖时请用 --diff <base>（PR 主路径）。")
        record("结构守卫", 0,
               "全量模式无法判定「本次新增」，本道未实际检查（见上方 ::warning::）",
               effective=False)
    else:
        added = resolve_files(mode, args.diff, added_only=True)
        rc, notes = _run_over_files(py, "structure_guard.py", added)
        record("结构守卫", rc, f"新增 {len(added)} 文件" + ("；" + " ".join(notes) if notes else ""),
               effective=bool(added))

    say("=== [5/6] ruff 潜在缺陷 ===")
    # f401_gate 的判定语义是「只阻断**本次新增**的潜在缺陷，不回溯整树历史债务」
    # （脚本 docstring 原话）。--all 喂的是全树，必然命中历史存量 ——
    # 2026-10-08 实测 30+ 处 F841（api/chat.py:206 `rem_bits`、engines/gomarl.py:331、
    # py-server/tests/* 多处…），那是"体检结果"，不是"本次改动的问题"。
    # 故与 [4] 结构守卫 / [6] 测试文件禁改 采用**同一口径**：全量模式下标记未生效
    # （显式、可见），而不是让它以一道"与设计语义冲突的红"出现在 CI 的兜底路径上。
    # 全量体检查历史债请直接跑：
    #     cd py-server && ruff check --select F401,F811,F821,F822,F841 .
    if mode == "all":
        print("::warning::ruff 潜在缺陷门禁在 --all（全量）模式下不生效：本道的判定语义是"
              "「只阻断本次新增的缺陷、不回溯整树历史债务」，而全量模式必然命中历史存量"
              "（2026-10-08 实测 30+ 处 F841），那不是本次改动的问题。"
              "全量体检查历史债请用：cd py-server && ruff check "
              "--select F401,F811,F821,F822,F841 .", file=sys.stderr)
        record("ruff 潜在缺陷", 0,
               "全量模式与「只查本次新增」的判定语义冲突，本道未实际检查（见上方 ::warning::）",
               effective=False)
    else:
        rc, notes = _run_over_files(py, "f401_gate.py", files)
        record("ruff 潜在缺陷", rc, " ".join(notes), effective=bool(files))

    say("=== [6/6] 测试文件禁改（粒度=单次 commit） ===")
    commits = resolve_commits(mode, args.diff)
    if commits:
        # push 事件可能跨多个 commit；必须逐个判，合并视角会造成误判（见 resolve_commits）
        rc, notes = _run_per_commit(py, "test_file_guard.py", commits, ["--staged"])
        record("测试文件禁改", rc, " ".join(notes))
    elif mode == "all":
        record("测试文件禁改", 0,
               "全量模式不适用：本规则判定粒度是「单次变更」，全树必然同时含"
               "测试与实现、判则恒红（逐 commit 检查请用 --diff）",
               effective=False)
    else:
        rc, notes = _run_with_injection(py, "test_file_guard.py", files, ["--staged"])
        record("测试文件禁改", rc, " ".join(notes), effective=bool(files))

    dt = time.time() - t0

    say("")
    failed = [r for r in results if r[1] != 0]
    ineffective = [r for r in results if r[1] == 0 and not r[3]]
    effective_n = len(results) - len(ineffective)

    say("=" * 56, always=True)
    if failed:
        say(f"❌ 六道门禁：{len(failed)} 道未通过（耗时 {dt:.1f}s）", always=True)
        for name, rc, _, _ in failed:
            say(f"   - {name} (exit {rc})", always=True)
        return 1

    # 2026-10-08 修：空文件集原本与「全部通过」打印成同一句话 —— 日志里无从分辨
    # 「六道闸门都检查过且放行」与「一道都没检查」。实测 `--diff HEAD`（无差异）
    # 得到 `待检文件: 0` + `✅ 六道门禁全部通过`，是彻底的零覆盖假绿。
    if effective_n == 0:
        print("::warning::本次解析到的待检文件为 0 → 六道门禁均未实际检查任何文件。"
              "请确认 base ref 是否正确；即使本次变更确实为空，"
              "本结果也**不等于「已通过检查」**。", file=sys.stderr)
        say(f"⚠️ 六道门禁：无待检文件（{effective_n}/6 道生效，耗时 {dt:.1f}s）"
            f"—— 这**不等于「已通过检查」**", always=True)
        return 0

    if ineffective:
        say(f"⚠️ 六道门禁：{effective_n}/6 道实际生效并通过，"
            f"{len(ineffective)} 道在本模式下未生效（耗时 {dt:.1f}s）", always=True)
        for name, _, note, _ in ineffective:
            say(f"   - {name}: 未生效 —— {note}", always=True)
        return 0

    say(f"✅ 六道门禁全部通过（{effective_n}/6 道实际生效，耗时 {dt:.1f}s）", always=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
