#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test-file-guard — "测试文件禁改" 下沉为 hook
用法（两种入口，同一逻辑）：
  1) git pre-commit hook：  python test_file_guard.py --staged
  2) CodeBuddy PreToolUse： python test_file_guard.py --pretooluse   （stdin: tool_input.command）
判定逻辑（tdd-discipline 红线的机制化）：
  - 暂存区同时含 测试文件 + 实现文件（测试目录之外的 .py/.js/.ts）→
    ⚠️ 警告（退出 1）：实现"恰好通过"且测试同 commit 被改 = 逃逸信号；
    修复建议：测试改动单独提交（git reset HEAD <测试文件> 后分两次 commit），或在 message 中显式说明测试变更理由。
  - 只改测试文件（如重构测试/加新测试，实现未动）→ 放行（合法：TDD 红灯阶段）。
  - 只改实现 → 放行。
退出码：0=放行；1=警告拦截（stderr 给出建议）
"""
import re
import subprocess
import sys

TEST_PATTERNS = [
    re.compile(r"(^|/)tests?/", re.I),
    re.compile(r"(^|/)test_[^/]+\.py$", re.I),
    re.compile(r"(^|/)[^/]+_test\.py$", re.I),
    re.compile(r"(^|/)[^/]+\.test\.(js|ts|tsx)$", re.I),
    re.compile(r"(^|/)spec/", re.I),
]

IMPL_EXT = re.compile(r"\.(py|js|ts|tsx|jsx|go|java|rs)$", re.I)


def is_test(path: str) -> bool:
    return any(p.search(path) for p in TEST_PATTERNS)


def staged_files() -> list:
    out = subprocess.check_output(
        ["git", "-c", "core.quotePath=false", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        stderr=subprocess.DEVNULL, text=True,
    )
    return [f.strip().replace("\\", "/") for f in out.splitlines() if f.strip()]


def check(files: list) -> int:
    tests = [f for f in files if is_test(f)]
    impls = [f for f in files if (not is_test(f)) and IMPL_EXT.search(f)]
    if tests and impls:
        print("⚠️ 测试与实现同 commit 变更（tdd-discipline 红线）：", file=sys.stderr)
        for t in tests[:5]:
            print(f"   测试: {t}", file=sys.stderr)
        for i in impls[:5]:
            print(f"   实现: {i}", file=sys.stderr)
        print(
            "   实现『恰好通过』且测试同 commit 被改 = 逃逸信号（可能为过测试而改测试）。\n"
            "   建议：拆分提交——先提交实现+原测试通过的证据，再单独提交测试变更并说明理由；\n"
            "   或确认本次是合法的 TDD 红灯→绿灯（新测试+新实现），在 commit message 中写明。",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> int:
    args = sys.argv[1:]
    if "--pretooluse" in args:
        import json
        try:
            data = json.load(sys.stdin)
        except Exception:
            return 0
        cmd = (data.get("tool_input") or {}).get("command", "")
        if "git commit" not in cmd:
            return 0
        try:
            return check(staged_files())
        except Exception:
            return 0  # 不在 git 仓库等场景 fail-open
    elif "--staged" in args:
        return check(staged_files())
    else:
        print(__doc__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
