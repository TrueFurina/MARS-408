#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_raw_values.py — 芒得很职 设计系统 · 组件层裸值门禁（dependency-free）

目的：守护 SSOT 铁律「组件只引用语义令牌，禁止硬编码 hex/rgba」。
权威源 `src/assets/styles/_variables.css` 允许定义原始色值；其余位置一律不得出现裸色值。

扫描范围：
  - src/assets/styles/*.css         （排除 _variables.css —— 它是令牌定义处）
  - src/**/*.vue 的 <style> 块       （仅样式段；<template>/<script> 里的
                                       Canvas 调色板 / 内联 :style 运行时色属合规例外，不扫）

判定「裸值」：
  - hex 颜色 `#rgb/#rrggbb/#rgba/#rrggbbaa`（排除白色变体 #fff/#ffffff/#ffffffff/#ffff）
  - `rgb()/rgba()/hsl()/hsla()` 首参为数字字面量（`rgba(var(--x-rgb), α)` 视为合规）

合规例外（不报）：
  - mask 用的白色、有色底上的 `color:#fff`
  - `rgba(var(--…-rgb), α)` —— 走令牌的透明叠加
  - 单行内联注释 `/* token-exception */`（或 `raw-value-exception`）显式豁免

退出码：0 = 无裸值；1 = 发现裸值；2 = 环境/零覆盖错误（扫描根缺失，或 0 个样式对象被扫描）。

零覆盖纪律（2026-10-08 补）
--------------------------------------------------------------------------
原实现既**不报告扫了多少文件**，也在零文件时照样打印
「零裸值 (NO RAW VALUES) — 组件层全部引用语义令牌」并 exit 0。
实测复现（隔离树内 src 下不放任何 .css/.vue）：exit 0 且输出该结论 ——
**它是从「什么都没扫」推出「组件层全部合规」的**。
这与本仓库反复出现的「零覆盖伪装成通过」是同一类失效，故：
  · 显式报告扫描对象数（N 个 css + M 个 vue <style> 块）；
  · 扫描对象为 0 时 fail-closed（exit 2），不输出任何合规结论。
（同口径先例：`scripts/pre-commit/run_gates.py` 的 `record()`。）
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STYLE_DIR = os.path.join(ROOT, "src", "assets", "styles")
SRC_DIR = os.path.join(ROOT, "src")
EXCLUDE_CSS = {"_variables.css"}

HEX_RE = re.compile(r"#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9a-fA-F])")
FUNC_RE = re.compile(r"\b(rgba?|hsla?)\(\s*(?![^)]*var\()([0-9.]|%)", re.I)
# 中性半透明覆盖层/阴影（纯白 / 纯黑的 alpha）—— 非品牌/主题色，合规例外
NEUTRAL_FUNC = re.compile(r"\b(?:rgba?|hsla?)\(\s*(?:255\s*,\s*255\s*,\s*255|0\s*,\s*0\s*,\s*0)\s*[,)]", re.I)
WHITE = {"#fff", "#ffffff", "#ffff", "#ffffffff"}
EXCEPTION_MARK = ("token-exception", "raw-value-exception")
INLINE_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def scan_text(text: str):
    """返回 [(lineno, snippet)] 违规列表。"""
    hits = []
    for i, raw_line in enumerate(text.splitlines(), 1):
        if any(m in raw_line for m in EXCEPTION_MARK):
            continue
        line = INLINE_COMMENT.sub("", raw_line)
        bad = False
        for m in HEX_RE.finditer(line):
            if ("#" + m.group(1)).lower() in WHITE:
                continue
            bad = True
        line_no_neutral = NEUTRAL_FUNC.sub("", line)
        if FUNC_RE.search(line_no_neutral):
            bad = True
        if bad:
            hits.append((i, raw_line.strip()[:120]))
    return hits


def vue_style_segments(vue_text: str):
    """返回 [(seg_content, file_start_line)] —— <style> 块内容与其在文件中的起始行号。"""
    segs = []
    for m in re.finditer(r"<style[^>]*>(.*?)</style>", vue_text, re.S | re.I):
        start_line = vue_text[:m.start(1)].count("\n") + 1
        segs.append((m.group(1), start_line))
    return segs


def main() -> int:
    if not os.path.isdir(STYLE_DIR):
        print(f"[ERROR] 样式目录不存在: {os.path.relpath(STYLE_DIR, ROOT)}", file=sys.stderr)
        return 2
    if not os.path.isdir(SRC_DIR):
        print(f"[ERROR] 源码目录不存在: {os.path.relpath(SRC_DIR, ROOT)}", file=sys.stderr)
        return 2

    violations = []
    n_css = 0        # 被扫描的 .css 文件数
    n_vue_blocks = 0  # 被扫描的 .vue <style> 非空块数

    # 1) 原生 CSS（排除 _variables.css）
    for fn in sorted(os.listdir(STYLE_DIR)):
        if not fn.endswith(".css") or fn in EXCLUDE_CSS:
            continue
        p = os.path.join(STYLE_DIR, fn)
        with open(p, "r", encoding="utf-8") as f:
            text = f.read()
        n_css += 1
        for ln, snip in scan_text(text):
            violations.append((os.path.relpath(p, ROOT), ln, snip))

    # 2) .vue 的 <style> 段
    for dirpath, _dirs, files in os.walk(SRC_DIR):
        for fn in files:
            if not fn.endswith(".vue"):
                continue
            p = os.path.join(dirpath, fn)
            with open(p, "r", encoding="utf-8") as f:
                text = f.read()
            for seg, start_line in vue_style_segments(text):
                if not seg.strip():
                    continue
                n_vue_blocks += 1
                for ln, snip in scan_text(seg):
                    violations.append((os.path.relpath(p, ROOT), start_line + ln - 1, snip))

    scanned = n_css + n_vue_blocks
    print(f"[scan] 已扫描 {scanned} 个样式对象（{n_css} 个 .css 文件 + {n_vue_blocks} 个 .vue <style> 块）\n")

    if scanned == 0:
        print("[ERROR] 零覆盖: 没有任何样式对象被扫描 —— "
              "不能声称「组件层全部引用语义令牌」（那是它无从得知的结论）。\n"
              "        请检查 STYLE_DIR / SRC_DIR 是否已失效（目录改名/移位）。", file=sys.stderr)
        return 2

    if not violations:
        print(f"=== 结论: 零裸值 (NO RAW VALUES) — 已扫描的 {scanned} 个样式对象全部引用语义令牌 ===")
        return 0

    print(f"=== 发现 {len(violations)} 处组件层裸值（须改用 var/color-mix 令牌）===\n")
    for path, ln, snip in violations:
        print(f"  [RAW] {path}:{ln}")
        print(f"        {snip}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
