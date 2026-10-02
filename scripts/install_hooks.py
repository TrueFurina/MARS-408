#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 scripts/pre-commit/ 的六道门禁挂载进 git hooks —— 幂等安装 / 校验器。

背景（为什么需要这个脚本）
--------------------------------------------------------------------------
门禁本体在 `scripts/pre-commit/*.py` 里，但**触发它的钩子**必须落在
`git rev-parse --git-path hooks`（默认 `.git/hooks/pre-commit`）——那个位置
**不受版本控制**，且本地提交可被 `git commit --no-verify` 绕过。于是：

    新克隆 = 没有任何门禁；这批护栏只活在"当初手工建过钩子的那台机器"上。

CI 侧自 2026-10-03 起由 `.github/workflows/gates.yml` + 编排器 `run_gates.py`
闭环（CI 不执行 pre-commit.sh，而是由编排器把文件集来源换成 PR diff 后
调用同一批脚本 —— 直接跑 pre-commit.sh 会因暂存区为空而全部假通过）。

处置：把钩子内容变成入库真源 `scripts/pre-commit/pre-commit.sh`，
本脚本负责「真源 → 实际安装位置」的幂等同步与一致性校验。

用法
--------------------------------------------------------------------------
    python scripts/install_hooks.py             # 安装 / 更新（幂等）
    python scripts/install_hooks.py --check     # 只校验；drift 则 exit 1
    python scripts/install_hooks.py --dry-run   # 只说不做
    python scripts/install_hooks.py --quiet     # 减少输出（配合 --check 用于脚本）

退出码：0=一致 / 安装成功；1=drift 或安装失败。

设计取舍
--------------------------------------------------------------------------
* **只写不删**：本脚本永不删除文件；遇到非本真源安装的既有钩子，先备份到
  `pre-commit.preinstall.bak`（仅当该备份尚不存在时，避免覆盖最早的那份），
  再覆盖。与本仓库"绝不删除"的红线一致。
* **行尾归一**：本仓库 `core.autocrlf=true` 且无 `.gitattributes`，入库脚本
  被检出时可能带 CRLF；shell 脚本带 `\r` 会让参数变成 `xxx.py\r` → 每次提交
  都报"文件不存在"，且极难归因。故写入前统一 CRLF→LF、去 BOM、补尾换行。
* **不假设钩子路径**：走 `git rev-parse --git-path hooks`，兼容 worktree
  （`.git` 是文件）与自定义 `core.hooksPath`。
"""
from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

CANONICAL_REL = Path("scripts") / "pre-commit" / "pre-commit.sh"
BACKUP_NAME = "pre-commit.preinstall.bak"


def repo_root() -> Path:
    """仓库根：优先问 git，其次按本文件位置推。"""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
        if out:
            return Path(out)
    except Exception:
        pass
    return Path(__file__).resolve().parents[1]


def hooks_dir(root: Path) -> Path:
    """钩子目录：走 git（兼容 worktree / core.hooksPath），失败则退回 .git/hooks。"""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--git-path", "hooks"],
            cwd=root, stderr=subprocess.DEVNULL, text=True,
        ).strip()
        if out:
            p = Path(out)
            return p if p.is_absolute() else (root / p)
    except Exception:
        pass
    return root / ".git" / "hooks"


def normalize(text: str) -> str:
    """行尾归一 + 去 BOM + 补尾换行。两侧都用它，才谈得上"内容一致"。"""
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


def read_text(p: Path) -> str | None:
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


# Windows 的 NTFS 无法表示 POSIX 执行位（Python chmod 只会动只读标志），
# 因此"执行位"这一条在 Windows 上永远是假红灯 —— 只校验而不要求，
# 否则本地每次 `--check` 都会因平台差异失败，属典型的机验假红灯。
CHECK_EXEC_BIT = os.name == "posix"


def is_executable(p: Path) -> bool:
    """POSIX 执行位。Windows 上 os.access(X_OK) 不可信，故直接看 st_mode。"""
    try:
        return bool(p.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    except Exception:
        return False


def make_executable(p: Path) -> None:
    try:
        mode = p.stat().st_mode
        p.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass  # Windows 上执行位无意义，git 自己会处理


def diff_summary(want: str, got: str, limit: int = 20) -> str:
    """只打印前若干处差异行，避免刷屏。"""
    wl, gl = want.splitlines(), got.splitlines()
    lines: list[str] = []
    for i in range(max(len(wl), len(gl))):
        w = wl[i] if i < len(wl) else "<缺失>"
        g = gl[i] if i < len(gl) else "<缺失>"
        if w != g:
            lines.append(f"    L{i + 1:>3} 真源: {w}")
            lines.append(f"    L{i + 1:>3} 实际: {g}")
        if len(lines) >= limit:
            lines.append("    …（差异过多，已截断）")
            break
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="安装 / 校验 pre-commit 门禁钩子")
    ap.add_argument("--check", action="store_true", help="只校验一致性，drift 则 exit 1")
    ap.add_argument("--dry-run", action="store_true", help="只展示将要做的动作")
    ap.add_argument("--quiet", action="store_true", help="仅输出必要的单行结果")
    args = ap.parse_args()

    def say(msg: str, *, always: bool = False) -> None:
        if always or not args.quiet:
            print(msg)

    root = repo_root()
    canonical = root / CANONICAL_REL
    target = hooks_dir(root) / "pre-commit"

    say(f"仓库根   : {root}")
    say(f"真源     : {canonical}")
    say(f"安装目标 : {target}")

    if not canonical.is_file():
        print(f"❌ 找不到门禁真源 {canonical}", file=sys.stderr)
        return 1

    want = normalize(read_text(canonical) or "")
    got_raw = read_text(target)

    # ---- 情形一：目标不存在 ----
    if got_raw is None:
        if args.check:
            print("❌ 未安装钩子：目标不存在（跑一次 `python scripts/install_hooks.py`）", file=sys.stderr)
            return 1
        if args.dry_run:
            say("DRY-RUN 将写入新钩子")
            return 0
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(want, encoding="utf-8", newline="\n")
        make_executable(target)
        say(f"✅ 已安装钩子（{len(want.encode('utf-8'))} 字节，LF）", always=args.quiet)
        return 0

    # ---- 情形二：目标已存在 ----
    got = normalize(got_raw)
    same_content = want == got
    exec_ok = (not CHECK_EXEC_BIT) or is_executable(target)
    exec_note = "内容 + 执行位" if CHECK_EXEC_BIT else "内容，本平台不校验执行位"
    if not same_content:
        if args.check:
            print("❌ 钩子与真源不一致（drift）：", file=sys.stderr)
            print(diff_summary(want, got), file=sys.stderr)
            print(
                "\n修复：python scripts/install_hooks.py（幂等，会先备份既有钩子）",
                file=sys.stderr,
            )
            return 1
        if args.dry_run:
            say("DRY-RUN 内容不一致，将覆盖")
            print(diff_summary(want, got))
            return 0

        # 覆盖前先备份"非本真源"的既有钩子（只备份一次，保住最早那份）。
        backup = target.parent / BACKUP_NAME
        if not backup.exists():
            shutil.copy2(target, backup)
            say(f"ℹ️ 已备份既有钩子 → {backup.name}")
        else:
            say(f"ℹ️ 既有备份已存在，保留最早的 {backup.name}")

        target.write_text(want, encoding="utf-8", newline="\n")
        make_executable(target)
        say("✅ 钩子已同步为真源内容（LF）", always=args.quiet)
        return 0

    # 内容一致，只剩执行位（仅 POSIX 有意义）
    if args.check and not exec_ok:
        print("❌ 钩子缺少可执行位（POSIX 上 git 会拒绝执行）", file=sys.stderr)
        print("修复：chmod +x .git/hooks/pre-commit", file=sys.stderr)
        return 1
    if args.dry_run:
        say(f"DRY-RUN 仅需补执行位（{exec_note}）")
        return 0

    make_executable(target)
    say(f"✅ 钩子与真源一致（{exec_note}）", always=args.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
