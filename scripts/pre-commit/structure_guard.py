#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""目录结构守卫 — pre-commit 门禁
用法：python scripts/pre-commit/structure_guard.py [--all]
退出码：0=通过，1=命中违规（fail-closed）

规则来源：西湖论剑 CTF-Agent _structure_guard.py（通用化）
默认只检查本次新增文件（--diff-filter=A），不误伤重命名/既有文件。
"""
import subprocess
import sys

# 受管后缀（这些类型的散落文件必须归位）
MANAGED_EXT = {"md", "txt", "html", "json", "csv", "pdf", "png", "jpg", "jpeg", "xlsx", "yml", "yaml"}

# 根级白名单（各项目可按需修改此集合）
ROOT_ALLOW = {
    "README.md", "README.zh.md", "README_EN.md", "CLAUDE.md", "AGENTS.md",
    "LICENSE", "requirements.txt", "package.json", "pyproject.toml",
    "setup.py", "Dockerfile", "docker-compose.yml", ".gitignore",
    ".pre-commit-config.yaml", "CHANGELOG.md", "Makefile",
}


def git(*args):
    """git 调用，关闭 quotePath 以免中文路径被转义导致漏判。"""
    cmd = ["git", "-c", "core.quotePath=false"] + list(args)
    return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode("utf-8", "ignore")


def unquote_path(p: str) -> str:
    p = p.strip()
    if p.startswith('"') and p.endswith('"'):
        p = p[1:-1]
    if "\\" in p:
        try:
            p = p.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")
        except Exception:
            pass
    return p


def staged_added_files() -> list:
    out = git("diff", "--cached", "--name-only", "--diff-filter=A")
    return [unquote_path(f) for f in out.splitlines() if f.strip()]


def all_tracked_files() -> list:
    out = git("ls-files")
    return [unquote_path(f) for f in out.splitlines() if f.strip()]


def violations_for(path: str) -> str | None:
    """返回违规描述，None=合规。"""
    p = path.replace("\\", "/")
    if "/" not in p:
        # 根级平铺文件
        ext = p.rsplit(".", 1)[-1].lower() if "." in p else ""
        if ext in MANAGED_EXT and p not in ROOT_ALLOW:
            return f"根级平铺文件 {p!r} 不在白名单，请移入对应子目录（docs/ deliverables/ data/ 等）"
    return None


def _injected_files() -> list | None:
    """外部注入的文件集（CI / 编排器场景）。

    为什么不能一路用 --all：本守卫的规则是"新增文件不许平铺在根目录"，
    全树模式会把**历史上早已存在的散落文件**一起算成违规（本仓库根级确有
    INSTALL.md / index.html / tsconfig.json 等），CI 一接就是永久红，
    等于一次性挂上一笔还不清的历史债、只能靠 CI 全红倒逼清理——那不是门禁的本意。

    故 CI 与本地保持**同一语义**：只判本次变更里新增的那几个文件。
    全树模式（--all）保留，但定位为人工体检，不进 CI。
    """
    try:
        from _gate_files import injected_files
    except ImportError:  # 被 import 而非直接执行时，脚本目录不一定在 sys.path
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _gate_files import injected_files
    return injected_files()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="检查全部已跟踪文件（默认只查新增）")
    parser.add_argument("files", nargs="*", help="显式指定文件列表")
    args = parser.parse_args()

    # 注入通道（GATE_FILES / GATE_FILES_FILE）由编排器决定「本次要检查什么」，
    # 是编排器→门禁的**确定性契约**：它坏了必须 fail-closed。
    # 2026-10-08 修：此前整段（**含注入解析**）被下面的 try 包住、异常统一 return 0，
    # 于是注入被损坏时本道会静默放行 —— 零覆盖假绿。
    # 现在把注入解析移到 try 之外：解析失败直接向上抛（非 0 退出 = 拦截提交）。
    injected = _injected_files()

    try:
        if injected is not None:
            files = injected
        elif args.files:
            files = list(args.files)
        else:
            files = all_tracked_files() if args.all else staged_added_files()
    except Exception as exc:
        # 仅「本地取文件集」这一段保持 fail-open（git 不可用等场景不阻断本地提交），
        # 但打印告警，不静默。
        print(f"⚠️ structure_guard 自身异常，跳过检查: {exc}")
        return 0

    bad = []
    for f in files:
        v = violations_for(f)
        if v:
            bad.append(v)

    if bad:
        print("❌ 目录结构守卫：以下文件违规平铺")
        for v in bad:
            print(f"  {v}")
        return 1

    print("✅ 结构守卫通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())