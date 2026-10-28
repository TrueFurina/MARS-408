#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""临时 codemod：把 v7/v8 旧调色板裸值精确映射到 v10 语义令牌。
仅映射「已知旧值 → 现行令牌」，不猜色；作用域同 check_raw_values（.css 除 _variables.css + .vue 的 <style>）。
用法：python scripts/_palettemap_tmp.py [--apply]
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STYLE_DIR = os.path.join(ROOT, "src", "assets", "styles")
SRC_DIR = os.path.join(ROOT, "src")
EXCLUDE = {"_variables.css"}

# 旧 hex → 现行令牌
HEX_MAP = {
    "#7c6af2": "var(--color-accent)", "#6b5cdb": "var(--color-accent-active)",
    "#22c55e": "var(--color-success)", "#ef4444": "var(--color-danger)",
    "#f59e0b": "var(--color-warning)", "#d97706": "var(--color-warning)",
    "#a78bfa": "var(--color-accent-text)", "#5b8bd8": "var(--color-info)",
    "#06b6d4": "var(--subject-co)", "#8b5cf6": "var(--subject-ds)",
    "#3b82f6": "var(--subject-cn)", "#f472b6": "var(--subject-os)",
    "#52c41a": "var(--color-success)", "#1677ff": "var(--color-info)",
    "#c4b5fd": "var(--color-accent-text)", "#15803d": "var(--color-success)",
    "#eef": "var(--color-surface-2)", "#eee": "var(--color-border)",
    "#ddd": "var(--color-border)", "#999": "var(--color-text-3)", "#888": "var(--color-text-3)",
    "#0a0a1a": "var(--color-canvas)", "#0d0d2b": "var(--color-canvas)", "#1a1a3e": "var(--color-surface)",
}
# 旧 rgb 三元组 → 现行 -rgb 基名
RGB_MAP = {
    "124,106,242": "accent", "34,197,94": "success", "239,68,68": "danger",
    "245,158,11": "warning", "139,92,246": "subject-ds", "59,130,246": "subject-cn",
    "6,182,212": "subject-co", "244,114,182": "subject-os", "91,139,216": "info",
    "82,196,26": "success", "255,193,7": "warning",
    "16,185,129": "success", "234,88,12": "warning",
}
HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
FUNC_RE = re.compile(r"\b(rgba?)\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*([,)])")


def convert(seg: str):
    n = [0]

    def hex_sub(m):
        t = HEX_MAP.get(m.group(0).lower())
        if t:
            n[0] += 1
            return t
        return m.group(0)

    def rgb_sub(m):
        trip = f"{int(m.group(2))},{int(m.group(3))},{int(m.group(4))}"
        base = RGB_MAP.get(trip)
        if not base:
            return m.group(0)
        n[0] += 1
        if m.group(5) == ")":
            return f"{m.group(1)}(var(--{base}-rgb))"
        return f"{m.group(1)}(var(--{base}-rgb),"

    seg = FUNC_RE.sub(rgb_sub, seg)
    seg = HEX_RE.sub(hex_sub, seg)
    return seg, n[0]


def style_span(text):
    m = re.search(r"<style[^>]*>", text, re.I)
    if not m:
        return None
    e = text.lower().find("</style>", m.end())
    return (m.end(), e) if e != -1 else None


def main():
    apply = "--apply" in sys.argv
    total = 0
    targets = [("css", os.path.join(STYLE_DIR, f)) for f in sorted(os.listdir(STYLE_DIR))
               if f.endswith(".css") and f not in EXCLUDE]
    for dp, _d, fs in os.walk(SRC_DIR):
        targets += [("vue", os.path.join(dp, f)) for f in fs if f.endswith(".vue")]
    for kind, p in targets:
        text = open(p, encoding="utf-8").read()
        if kind == "vue":
            sp = style_span(text)
            if not sp:
                continue
            a, b = sp
            seg, c = convert(text[a:b])
            if apply and c:
                open(p, "w", encoding="utf-8").write(text[:a] + seg + text[b:])
        else:
            seg, c = convert(text)
            if apply and c:
                open(p, "w", encoding="utf-8").write(seg)
        if c:
            print(f"  {os.path.relpath(p, ROOT)}: {c}")
        total += c
    print(f"\n=== {'已写入' if apply else '空跑'}：映射 {total} 处旧调色板裸值 ===")


if __name__ == "__main__":
    main()
