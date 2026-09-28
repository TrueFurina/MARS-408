#!/usr/bin/env python3
"""
前端可访问性静态扫描（a11y gate）

为什么需要它：
    图标按钮（关闭 ×、发送 ➤、勾选 ✓ …）在模板里通常只有一个 <button> 加一个空的
    <span>，视觉上有图标、但对屏幕阅读器**完全没有可读名称** —— 读屏只会念"按钮"。
    这类缺陷静态检查容易漏、评审也不易发现，因此固化为可复跑脚本。

判定规则（保守，宁可漏报也不误报）：
    一个 <button> 被判为"无可读名称"，需**同时**满足：
      1. 属性中没有 aria-label / aria-labelledby / title
      2. 去掉所有标签、注释、mustache 插值后，内部没有残留可见文本
    —— 若内部文本由 v-if / 插值动态产生（保守起见无法静态判定），则**不**计入。

退出码：
    0 = 无缺陷（或仅告警级别问题）
    1 = 发现无可读名称的按钮（阻断）

用法：
    python scripts/a11y_scan.py            # 扫描 src/
    python scripts/a11y_scan.py --strict   # 同时检查 <a> 链接空文本
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

BTN_RE = re.compile(r"<button\b([^>]*)>([\s\S]*?)</button>", re.M)
A_RE = re.compile(r"<a\b([^>]*)>([\s\S]*?)</a>", re.M)

NAMING_ATTRS = re.compile(r"aria-label|aria-labelledby|title=")


def has_visible_text(inner: str) -> bool:
    """剥离标签/注释/插值后，是否还有静态可见文本。"""
    s = re.sub(r"<!--[\s\S]*?-->", "", inner)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\{[^{}]*\}", "", s)  # mustache / JSX 表达式：动态内容不算静态保证
    s = s.replace("&nbsp;", " ").strip()
    return bool(s)


def scan(kind: str, pattern: re.Pattern[str], strict_links: bool) -> list[tuple[str, int, str]]:
    if kind == "a" and not strict_links:
        return []
    found: list[tuple[str, int, str]] = []
    for f in sorted(SRC.rglob("*.vue")):
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in pattern.finditer(text):
            attrs, inner = m.group(1), m.group(2)
            if NAMING_ATTRS.search(attrs):
                continue
            if has_visible_text(inner):
                continue
            line = text[: m.start()].count("\n") + 1
            rel = f.relative_to(ROOT).as_posix()
            found.append((rel, line, attrs.strip()[:100]))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description="扫描无可读名称的交互元素（可访问性门禁）")
    ap.add_argument("--strict", action="store_true", help="同时检查无文本的 <a> 链接")
    args = ap.parse_args()

    if not SRC.is_dir():
        print(f"[skip] 未找到 {SRC}")
        return 0

    btn_bad = scan("button", BTN_RE, True)
    a_bad = scan("a", A_RE, args.strict)

    total_bad = len(btn_bad) + len(a_bad)

    print("=" * 72)
    print("可访问性扫描：无可读名称的交互元素")
    print("=" * 72)
    print(f"扫描目录: {SRC.relative_to(ROOT).as_posix()}/**/*.vue")
    print(f"<button> 缺陷: {len(btn_bad)}")
    if args.strict:
        print(f"<a> 缺陷: {len(a_bad)}")
    print()

    if total_bad == 0:
        print("[PASS] 未发现无可读名称的按钮/链接。")
        return 0

    print("[FAIL] 以下元素对屏幕阅读器没有可读名称，请补 aria-label（或 title）：")
    print()
    for rel, line, attrs in btn_bad + a_bad:
        print(f"  {rel}:{line}")
        print(f"      <button {attrs}>")
    print()
    print("修复示例：<button class=\"x\" @click=\"close\" aria-label=\"关闭对话\">")
    return 1


if __name__ == "__main__":
    sys.exit(main())
