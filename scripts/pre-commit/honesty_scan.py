#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诚实口径扫描器 — pre-commit 门禁
用法：python scripts/pre-commit/honesty_scan.py [--cached] [文件列表...]
退出码：0=通过，1=命中假水位（fail-closed）

规则来源：西湖论剑 CTF-Agent 诚实口径扫描器
核心原则：平台 accepted=0 时，任何"解出数递增/真实解出 flag/自主X/X"均为假水位
"""
import re
import sys
from pathlib import Path

# 命中即报错的短语（历史违规样本）
FORBIDDEN_PHRASES = (
    "冲第一", "真实水位 89%", "真实水位 92%", "真实水位 100%",
    "自主 7/7", "将功补过", "解出数提升",
    "5→13", "13→15", "15→16", "16→26",
    "解出数 16", "解出数 26",
)

# 命中即报错的正则
FORBIDDEN_PATTERNS = (
    re.compile(r"解出数\s*\d+\s*→\s*\d+"),
    re.compile(r"\+\d+\s*真实解出"),
    re.compile(r"真实解出[^。\n]*flag"),
)

# 引号包裹的内容是「提及」非「使用」，剥离后再匹配
_QUOTE_RE = re.compile("「[^」]*」|『[^』]*』|\"[^\"]*\"|'[^']*'")


# 排除目录
_SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", "dist", "build"}
_SKIP_PREFIX = ("_archive", "race_attachments", "work_web", "platform_downloads")


def is_skipped(path: Path) -> bool:
    parts = set(path.parts)
    if parts & {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", "dist", "build"}:
        return True
    for part in path.parts:
        if part.startswith(_SKIP_PREFIX):
            return True
    return False


def scan_text(text: str, path: str = "") -> list:
    hits = []
    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = re.sub(r"「[^」]*」|『[^』]*』|\"[^\"]*\"|'[^']*'", "", line)
        for phrase in ("冲第一", "真实水位 89%", "真实水位 92%", "真实水位 100%",
                       "自主 7/7", "将功补过", "解出数提升",
                       "5→13", "13→15", "15→16", "16→26",
                       "解出数 16", "解出数 26"):
            if phrase in stripped:
                hits.append(f"{path}:{idx}: 假水位短语 {phrase!r}")
        for pat in (re.compile(r"解出数\s*\d+\s*→\s*\d+"),
                    re.compile(r"\+\d+\s*真实解出"),
                    re.compile(r"真实解出[^。\n]*flag")):
            if pat.search(stripped):
                hits.append(f"{path}:{idx}: 假水位正则 {pat.pattern!r}")
    return hits


def scan_file(filepath: Path) -> list:
    if is_skipped(filepath):
        return []
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return []
    return scan_text(content, str(filepath))


def get_staged_files() -> list:
    import subprocess
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            stderr=subprocess.DEVNULL, text=True
        )
        return [Path(f) for f in out.strip().split() if f]
    except Exception:
        return []


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--cached", action="store_true", help="扫描暂存区文件")
    parser.add_argument("files", nargs="*", help="指定文件列表")
    args = parser.parse_args()

    if args.cached:
        files = get_staged_files()
    elif args.files:
        files = [Path(f) for f in args.files]
    else:
        files = [p for p in Path('.').rglob('*') if p.is_file()]

    all_hits = []
    for f in files:
        if any(ign in str(f) for ign in ['.git', '__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build']):
            continue
        hits = scan_file(Path(f))
        all_hits.extend(hits)

    if all_hits:
        for h in all_hits:
            print(f"❌ {h}")
        return 1

    print("✅ 诚实口径扫描通过")
    return 0


if __name__ == '__main__':
    import re
    sys.exit(main())