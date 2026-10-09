#!/usr/bin/env python3
"""
前端可访问性静态扫描（a11y gate）

== 硬门禁（默认，阻断 CI）==
    图标按钮（关闭 ×、发送 ➤、勾选 ✓ …）在模板里通常只有一个 <button> 加一个空的
    <span>，视觉上有图标、但对屏幕阅读器**完全没有可读名称** —— 读屏只会念"按钮"。
    这类缺陷静态检查容易漏、评审也不易发现，因此固化为可复跑脚本，发现即阻断（exit 1）。

== 深度审计（--audit，咨询级，不阻断）==
    在硬门禁之外，提供一组**保守的咨询级**检测，用于评审走查清单的自动化初筛：
      A. 浮层/沙箱组件（modal/dialog/drawer/overlay/sandbox）是否具备焦点管理信号
         （focus-trap / .focus() / @keydown.esc / tabindex）——缺则 WCAG 2.4.3 焦点顺序风险。
      B. 流式/对话组件（chat/stream/conversation/markdown）是否声明 aria-live，
         让读屏用户感知增量内容（WCAG 4.1.3）。
      C. 自定义可点击元素（role="button" / <div @click>）是否配套键盘事件（@keydown/tabindex），
         否则仅鼠标可达（WCAG 2.1.1）。
      D. 含动画（@keyframes/animation/transition）的组件是否提供 prefers-reduced-motion 守卫，
         否则前庭功能障碍用户会不适（WCAG 2.3.3）。
    审计结果一律 report-only，exit 0，不在冻结期影响 CI；待 10-28 窗口后可将其中成熟规则提升为硬门禁。

判定规则（保守，宁可漏报也不误报）：
    一个 <button> 被判为"无可读名称"，需**同时**满足：
      1. 属性中没有 aria-label / aria-labelledby / title
      2. 去掉所有标签、注释、mustache 插值后，内部没有残留可见文本
    —— 若内部文本由 v-if / 插值动态产生（保守起见无法静态判定），则**不**计入。

退出码：
    0 = 无硬门禁缺陷（审计发现不计入）
    1 = 发现无可读名称的按钮（阻断）

用法：
    python scripts/a11y_scan.py            # 仅硬门禁
    python scripts/a11y_scan.py --strict   # 硬门禁 + 检查 <a> 空文本
    python scripts/a11y_scan.py --audit    # 硬门禁 + 深度咨询级审计（不阻断）
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


# ─────────────────────────────────────────────────────────────────────────────
# 深度审计（咨询级，report-only，不阻断 CI）
# ─────────────────────────────────────────────────────────────────────────────

# A. 浮层/沙箱组件识别
OVERLAY_NAME = re.compile(r"(modal|dialog|drawer|overlay|sandbox|playground|codelab|terminal|wasm)", re.I)
OVERLAY_BODY = re.compile(r'role="dialog"|<teleport|\.modal\b|\.drawer\b|\.overlay\b|Transition name="modal"', re.I)
FOCUS_SIGNALS = re.compile(
    r"focus-trap|focusTrap|trapFocus|\.focus\(\)|@keydown\.esc|tabindex|v-focus|"
    r"firstFocusable|focusFirst|restoreFocus",
    re.I,
)

# B. 流式/对话组件识别
STREAM_NAME = re.compile(r"(chat|stream|conversation|message)", re.I)
STREAM_BODY = re.compile(
    r"streaming|EventSource|\bSSE\b|onmessage|progressive|appendChunk|fetchStream|"
    r"readableStream|readablestream",
    re.I,
)
ARIA_LIVE = re.compile(r"aria-live")

# C. 自定义可点击元素
CLICKABLE = re.compile(r'role="button"|<div\b[^>]*@click')
KEYBOARD = re.compile(r"@keydown|@keyup|tabindex|@key\.|@keypress", re.I)

# D. 动画 / reduced-motion（仅关键帧与显式 animation，hover 过渡通常无需守卫，避免误报）
ANIM = re.compile(r"@keyframes|animation\s*:", re.I)
REDUCED_MOTION = re.compile(r"prefers-reduced-motion", re.I)

VUE_FILES = sorted(SRC.rglob("*.vue"))


def _read(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return None


def audit_overlays() -> list[str]:
    """A. 浮层/沙箱组件是否具备焦点管理信号（WCAG 2.4.3）。"""
    hits: list[str] = []
    for f in VUE_FILES:
        text = _read(f)
        if not text:
            continue
        is_overlay = OVERLAY_NAME.search(f.stem) or OVERLAY_BODY.search(text)
        if not is_overlay:
            continue
        if FOCUS_SIGNALS.search(text):
            continue
        rel = f.relative_to(ROOT).as_posix()
        hits.append(
            f"  [A] {rel}  —— 浮层/沙箱组件疑似缺焦点管理信号（无 focus-trap/.focus()/"
            f"@keydown.esc/tabindex），WCAG 2.4.3"
        )
    return hits


def audit_streaming() -> list[str]:
    """B. 流式/对话组件是否声明 aria-live（WCAG 4.1.3）。"""
    hits: list[str] = []
    for f in VUE_FILES:
        text = _read(f)
        if not text:
            continue
        is_stream = STREAM_NAME.search(f.stem) or STREAM_BODY.search(text)
        if not is_stream:
            continue
        if ARIA_LIVE.search(text):
            continue
        rel = f.relative_to(ROOT).as_posix()
        hits.append(
            f"  [B] {rel}  —— 流式/对话组件未声明 aria-live，增量内容对读屏不可感知，WCAG 4.1.3"
        )
    return hits


def audit_custom_clickable() -> list[str]:
    """C. 自定义可点击元素是否配套键盘事件（WCAG 2.1.1）。"""
    hits: list[str] = []
    for f in VUE_FILES:
        text = _read(f)
        if not text:
            continue
        if not CLICKABLE.search(text):
            continue
        if KEYBOARD.search(text):
            continue
        rel = f.relative_to(ROOT).as_posix()
        hits.append(
            f"  [C] {rel}  —— 含自定义可点击元素(role=button/<div @click)但全文件无键盘事件，"
            f"仅鼠标可达，WCAG 2.1.1"
        )
    return hits


def audit_reduced_motion() -> list[str]:
    """D. 含动画的组件是否提供 prefers-reduced-motion 守卫（WCAG 2.3.3）。"""
    hits: list[str] = []
    for f in VUE_FILES:
        text = _read(f)
        if not text:
            continue
        if not ANIM.search(text):
            continue
        if REDUCED_MOTION.search(text):
            continue
        rel = f.relative_to(ROOT).as_posix()
        hits.append(
            f"  [D] {rel}  —— 含 @keyframes/animation/transition 但本文件无 prefers-reduced-motion "
            f"守卫，WCAG 2.3.3"
        )
    return hits


def run_audit() -> None:
    a = audit_overlays()
    b = audit_streaming()
    c = audit_custom_clickable()
    d = audit_reduced_motion()
    print()
    print("=" * 72)
    print("可访问性深度审计（--audit · 咨询级 · 不阻断 CI）")
    print("=" * 72)
    print(f"\n[A] 浮层/沙箱焦点管理    待人工走查: {len(a)}")
    for x in a:
        print(x)
    print(f"\n[B] 流式输出 aria-live   待人工走查: {len(b)}")
    for x in b:
        print(x)
    print(f"\n[C] 自定义可点击键盘可达 待人工走查: {len(c)}")
    for x in c:
        print(x)
    print(f"\n[D] reduced-motion 守卫 待人工走查: {len(d)}")
    for x in d:
        print(x)
    print(
        "\n说明：以上为静态初筛，可能含误报（如全局守卫或运行时处理），需人工走查确认；"
    )
    print("      待 10-28 窗口后可将成熟规则提升为硬门禁（改 exit 1）。")


def main() -> int:
    ap = argparse.ArgumentParser(description="扫描无可读名称的交互元素（可访问性门禁）")
    ap.add_argument("--strict", action="store_true", help="同时检查无文本的 <a> 链接")
    ap.add_argument(
        "--audit",
        action="store_true",
        help="输出深度咨询级审计（焦点陷阱/流式 aria-live/键盘可达/reduced-motion），不阻断",
    )
    args = ap.parse_args()

    if not SRC.is_dir():
        print(f"[skip] 未找到 {SRC}")
        return 0

    btn_bad = scan("button", BTN_RE, True)
    a_bad = scan("a", A_RE, args.strict)

    total_bad = len(btn_bad) + len(a_bad)

    print("=" * 72)
    print("可访问性扫描：无可读名称的交互元素（硬门禁）")
    print("=" * 72)
    print(f"扫描目录: {SRC.relative_to(ROOT).as_posix()}/**/*.vue")
    print(f"<button> 缺陷: {len(btn_bad)}")
    if args.strict:
        print(f"<a> 缺陷: {len(a_bad)}")
    print()

    if total_bad == 0:
        print("[PASS] 硬门禁：未发现无可读名称的按钮/链接。")
    else:
        print("[FAIL] 以下元素对屏幕阅读器没有可读名称，请补 aria-label（或 title）：")
        print()
        for rel, line, attrs in btn_bad + a_bad:
            print(f"  {rel}:{line}")
            print(f"      <button {attrs}>")
        print()
        print("修复示例：<button class=\"x\" @click=\"close\" aria-label=\"关闭对话\">")

    if args.audit:
        run_audit()

    return 1 if total_bad else 0


if __name__ == "__main__":
    sys.exit(main())
