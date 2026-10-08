#!/usr/bin/env python3
"""禁止 CI 调用的脚本里出现**本机绝对路径**字面量。

────────────────────────────────────────────────────────────────────────────
背景（真实 CI 红，run 37812723531）
────────────────────────────────────────────────────────────────────────────
`py-server/scripts/verify_core_lock_unification.py:25` 曾写着

    ROOT = r"E:\\Program\\MARL\\study-help-pro\\py-server"

它是被 `.github/workflows/verify-structural.yml` 的 `structural` job 在
ubuntu-latest 上执行的。在 Linux 上该字符串被拼成

    <repo>/py-server/E:\\Program\\MARL\\study-help-pro\\py-server/db/core.py

⇒ `FileNotFoundError` ⇒ exit 1 ⇒ 整个 structural job 变红。

**为什么本机发现不了**：开发机上那个绝对路径**真的存在**，脚本本地跑全 PASS；
只有在另一种文件系统布局下才暴露。这是「本地绿、CI 红」的一个新形态 ——
与"缺二进制产物"(models/) 和"浅克隆缺历史对象"并列。

**为什么它长期潜伏**：该 job 用 `set -u`（非 `-e`）+ 累积 `fail`，9 个脚本都跑；
但失败是按顺序披露的 —— 更前面的 `verify_app_wiring`（浅克隆）先红，
修好之后这一条才浮出水面。**修一个红会露出下一个红，必须一次扫全链。**

────────────────────────────────────────────────────────────────────────────
本门禁的判定
────────────────────────────────────────────────────────────────────────────
对象：`.github/workflows/*.yml` 里被 `python[3] .../*.py` 调用、且**已被 git 跟踪**的
脚本（未跟踪的本地一次性脚本不在 CI 上，故意不扫，避免噪音）。

判据：AST 扫字符串常量（**排除 docstring**），命中以下形态即失败
  - Windows 绝对路径：`^[A-Za-z]:[\\/]`
  - POSIX 家目录绝对路径：`^/(home|Users|mnt|opt|root)/`
  - UNC：`^\\\\<host>\\`

设计取舍：
  - 用 AST 而非 grep —— `design-system/check_raw_values.py` 里有 `'\\b(rgba?...'`
    这类**正则字面量**，grep 会假阳（首版扫描器实测踩过）。
  - 排除 docstring —— 文档里举例说明"不要写 E:\\..."是正当的。
  - `/tmp/...` **只告警不失败**：它属"Linux 可跑、Windows 不可跑"的可移植性不对称，
    在 ubuntu-latest 上不构成 CI 红（`verify_gold_candidates.py` 即此情形）。

退出码：0=通过；1=发现硬编码绝对路径；2=覆盖率/环境错误（**fail-closed**）。
    ┌ 零覆盖必须红：workflow 引用列表解析出 0 个脚本时 exit 2，
    └ 否则"没扫到对象"会被打印成"合规"——本仓库已累计踩过 9 次该形态。

用法：
    python scripts/check_hardcoded_paths.py                  # 默认：从 workflows 推导
    python scripts/check_hardcoded_paths.py <file.py> [...]   # 注入通道，供负向验证
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF_DIR = ROOT / ".github" / "workflows"

WINDOWS_ABS = re.compile(r"^[A-Za-z]:[\\/]")
POSIX_HOME_ABS = re.compile(r"^/(?:home|Users|mnt|opt|root)/")
UNC_ABS = re.compile(r"^\\\\[A-Za-z0-9._-]+\\")
POSIX_TMP = re.compile(r"^/tmp/")

# `python script.py` / `python3 ./scripts/x.py` / `python ../scripts/y.py`
PY_INVOCATION = re.compile(r"[\w./\\-]+\.py")


def tracked_python_files() -> set[str]:
    """已跟踪的 .py 文件（相对仓库根的 posix 路径）。CI 只看得见这些。"""
    out = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        print(
            "[check_hardcoded_paths] FATAL: `git ls-files` 失败，无法确定扫描对象。"
            f"\n{out.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(2)
    return {line.strip() for line in out.stdout.splitlines() if line.strip()}


def is_test_file(rel_posix: str) -> bool:
    """测试文件刻意排除。

    理由：测试夹具里的绝对路径是**数据**（如 mock 掉的服务返回的 results_dir），
    不是「被拿去做文件系统访问的本机路径」。本门禁无法做污点分析区分二者，
    故整类排除，避免用假阳逼人加 noqa —— 那会让门禁失去公信力。
    （`tests/benchmark_evidence_gate.py` 不匹配下列模式，仍在覆盖内。）
    """
    name = Path(rel_posix).name
    if "/tests/" in f"/{rel_posix}" or rel_posix.startswith("tests/"):
        return True
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def workflow_referenced_scripts() -> tuple[list[Path], int]:
    """从 workflows 推导「CI 会执行」的脚本清单（按 basename 匹配已跟踪文件）。"""
    if not WF_DIR.is_dir():
        print(
            f"[check_hardcoded_paths] FATAL: 找不到 workflow 目录 {WF_DIR}。"
            "零覆盖会导致误报合规，故 fail-closed。",
            file=sys.stderr,
        )
        sys.exit(2)

    wfs = sorted(WF_DIR.glob("*.yml")) + sorted(WF_DIR.glob("*.yaml"))
    if not wfs:
        print(
            f"[check_hardcoded_paths] FATAL: {WF_DIR} 下无任何 workflow 文件，fail-closed。",
            file=sys.stderr,
        )
        sys.exit(2)

    wanted: dict[str, list[str]] = {}
    for wf in wfs:
        text = wf.read_text(encoding="utf-8", errors="replace")
        for m in PY_INVOCATION.finditer(text):
            name = Path(m.group(0).replace("\\", "/")).name
            wanted.setdefault(name, []).append(wf.name)

    tracked = tracked_python_files()
    by_name: dict[str, list[str]] = {}
    for rel in tracked:
        by_name.setdefault(Path(rel).name, []).append(rel)

    found: list[Path] = []
    for name in sorted(wanted):
        for rel in sorted(by_name.get(name, [])):
            if is_test_file(rel):
                continue
            found.append(ROOT / rel)
    return found, len(wfs)


def classify(value: str) -> str | None:
    """返回 'hard' / 'warn' / None。"""
    if WINDOWS_ABS.match(value) or POSIX_HOME_ABS.match(value) or UNC_ABS.match(value):
        return "hard"
    if POSIX_TMP.match(value):
        return "warn"
    return None


def scan_file(path: Path) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """返回 (hard_hits, warn_hits)，跳过 docstring。"""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))

    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add(id(first.value))

    hard: list[tuple[int, str]] = []
    warn: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            kind = classify(node.value)
            if kind == "hard":
                hard.append((node.lineno, node.value))
            elif kind == "warn":
                warn.append((node.lineno, node.value))
    return hard, warn


def main(argv: list[str]) -> int:
    if argv:
        # 注入通道：仅供负向验证使用（避免为验证而改写已跟踪文件）。
        targets = [Path(a).resolve() for a in argv]
        n_wf = 0
        src = "命令行注入"
    else:
        targets, n_wf = workflow_referenced_scripts()
        src = f"{n_wf} 个 workflow 引用"

    if not targets:
        print(
            "[check_hardcoded_paths] ❌ 零覆盖：未解析出任何待检脚本。\n"
            "  这通常意味着 workflow 目录/文件名约定变了，本门禁已失效 —— 按 fail-closed 判红。",
            file=sys.stderr,
        )
        return 2

    hard_total = 0
    warn_total = 0
    scanned = 0
    for path in targets:
        if not path.exists():
            print(f"  [SKIP] {path} 不存在", file=sys.stderr)
            continue
        scanned += 1
        try:
            hard, warn = scan_file(path)
        except SyntaxError as exc:
            # 扫不了 = 不能声称合规。CI 引用一个连语法都不合法的脚本本身就是缺陷，
            # 且 fail-closed 优于打印 traceback 后静默放行。
            rel = path.relative_to(ROOT) if str(path).startswith(str(ROOT)) else path
            print(f"  ❌ {rel}  语法错误，无法解析：{exc}")
            hard_total += 1
            continue
        rel = path.relative_to(ROOT) if str(path).startswith(str(ROOT)) else path
        if hard:
            print(f"  ❌ {rel}")
            for ln, v in sorted(hard):
                print(f"       L{ln}: {v!r}  ← 本机绝对路径，在 CI 上必然解析失败")
            hard_total += len(hard)
        if warn:
            print(f"  ⚠️  {rel}  /tmp 绝对路径 {len(warn)} 处（Linux OK、Windows 不可跑，仅告警）")
            warn_total += len(warn)

    print(
        f"[scan] 已扫描 {scanned} 个 CI 引用脚本（来源：{src}）；"
        f"硬编码 {hard_total} 处，/tmp 告警 {warn_total} 处"
    )
    if scanned == 0:
        # 解析出清单但一个都没读到（路径全不存在）⇒ 与"零覆盖"等价，必须红。
        print(
            "[check_hardcoded_paths] ❌ 零覆盖：清单非空但无一个可读文件，按 fail-closed 判红。",
            file=sys.stderr,
        )
        return 2
    if hard_total:
        print("\n❌ 存在硬编码绝对路径：请改为由 __file__ 推导，例如")
        print("   ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))")
        return 1
    print("✅ 未发现硬编码绝对路径")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
