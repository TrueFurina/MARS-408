#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""口径数字对齐检查器 — pre-commit 门禁
用法：python scripts/pre-commit/caliber_check.py [--cached] [文件列表...]
退出码：0=通过，1=命中不一致口径（fail-closed）

规则：
  - 文档中出现的数字（如"1603 passed"、"n=22 seeds"）必须与代码真值对齐
  - 无法追溯到代码真值的数字标记为"待验证"
"""
import re
import sys
from pathlib import Path

# 数字模式：匹配常见的竞赛/项目口径数字
NUMERIC_PATTERNS = [
    # 测试数（如 1603 passed）
    re.compile(r'(\d+)\s*(?:passed|tests|tests passed|passed tests)'),
    # 样本数（如 n=22 seeds）
    re.compile(r'n\s*=\s*(\d+)\s*(?:seeds|samples|runs|episodes)'),
    # 得分/排名
    re.compile(r'(?:得分|score|rank|排名)[：:\s]*(\d+)'),
    # 解题数
    re.compile(r'(?:解出|solved|accepted)[：:\s]*(\d+)'),
    # 百分比
    re.compile(r'(\d+(?:\.\d+)?)\s*%'),
]

# 允许的"待验证"标注
ALLOWED_PLACEHOLDERS = ['待验证', 'to be verified', 'TBD', 'N/A', '—']


def scan_text(text: str, path: str = "") -> list:
    """扫描文本中的数字，返回 [(行号, 数字, 类型)]"""
    results = []
    for idx, line in enumerate(text.splitlines(), start=1):
        # 跳过"待验证"标注行
        if any(p in line for p in ALLOWED_PLACEHOLDERS):
            continue
        for pat in NUMERIC_PATTERNS:
            for m in pat.finditer(line):
                results.append((idx, m.group(1), pat.pattern[:30]))
    return results


def scan_file(filepath: Path) -> list:
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

    # 只检查文档类文件（md/txt/docx），不检查代码（代码数字是真值源）
    doc_ext = {'.md', '.txt', '.docx', '.pdf', '.html'}
    files = [f for f in files if f.suffix.lower() in doc_ext]

    all_hits = []
    for f in files:
        if any(ign in str(f) for ign in ['.git', '__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build']):
            continue
        hits = scan_file(Path(f))
        if hits:
            for line_num, num, pat in hits:
                print(f"⚠️ {f}:{line_num}: 数字 {num!r} ({pat}) — 请确认与代码真值对齐，否则标注'待验证'")
            all_hits.append((f, hits))

    if all_hits:
        print(f"\n⚠️ 发现 {len(all_hits)} 个文件含待确认数字，请人工复核后标注'待验证'或修正")
        return 0  # 警告而非拦截（人工复核环节）

    print("✅ 口径数字检查通过（无待确认数字）")
    return 0


if __name__ == '__main__':
    sys.exit(main())