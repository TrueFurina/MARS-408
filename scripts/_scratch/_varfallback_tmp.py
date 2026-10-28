#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""临时 codemod：删除 var(--token, <raw>) 中【令牌已在 _variables.css 定义】的冗余回退值。
仅作用于 .css（除 _variables.css）与 .vue 的 <style> 段。含嵌套 var() 的回退值一律跳过（保守）。
用法：  python scripts/_varfallback_tmp.py           # 空跑，只统计
        python scripts/_varfallback_tmp.py --apply    # 实际写入
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARS = os.path.join(ROOT, "src", "assets", "styles", "_variables.css")
STYLE_DIR = os.path.join(ROOT, "src", "assets", "styles")
SRC_DIR = os.path.join(ROOT, "src")
EXCLUDE = {"_variables.css"}

defined = set(re.findall(r"(--[\w-]+)\s*:", open(VARS, encoding="utf-8").read()))
VAR_START = re.compile(r"var\(\s*(--[\w-]+)\s*,")


def strip_one(s: str):
    """返回 (新串, 删除数, 跳过数)。"""
    out, i, removed, skipped = [], 0, 0, 0
    while True:
        m = VAR_START.search(s, i)
        if not m:
            out.append(s[i:])
            break
        out.append(s[i:m.start()])
        name = m.group(1)
        op = s.index("(", m.start())
        depth, k = 0, op
        while k < len(s):
            if s[k] == "(":
                depth += 1
            elif s[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        inner = s[op + 1:k]              # --name, fallback
        comma = top_comma(inner)
        fallback = inner[comma + 1:] if comma != -1 else ""
        if name in defined and "var(" not in fallback and comma != -1:
            out.append(f"var({name})")
            removed += 1
        else:
            out.append(s[m.start():k + 1])
            skipped += 1
        i = k + 1
    return "".join(out), removed, skipped


def top_comma(inner: str) -> int:
    depth = 0
    for idx, ch in enumerate(inner):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            return idx
    return -1


def style_span(text: str):
    m = re.search(r"<style[^>]*>", text, re.I)
    if not m:
        return None
    end = text.lower().find("</style>", m.end())
    return (m.end(), end) if end != -1 else None


def main() -> int:
    apply = "--apply" in sys.argv
    total_r = total_s = 0
    rows = []
    targets = []
    for fn in sorted(os.listdir(STYLE_DIR)):
        if fn.endswith(".css") and fn not in EXCLUDE:
            targets.append(("css", os.path.join(STYLE_DIR, fn)))
    for dp, _d, fs in os.walk(SRC_DIR):
        for fn in fs:
            if fn.endswith(".vue"):
                targets.append(("vue", os.path.join(dp, fn)))

    for kind, p in targets:
        text = open(p, encoding="utf-8").read()
        if kind == "vue":
            span = style_span(text)
            if not span:
                continue
            a, b = span
            new_seg, r, s = strip_one(text[a:b])
            changed = r > 0
            if apply and changed:
                open(p, "w", encoding="utf-8").write(text[:a] + new_seg + text[b:])
        else:
            new_seg, r, s = strip_one(text)
            changed = r > 0
            if apply and changed:
                open(p, "w", encoding="utf-8").write(new_seg)
        if r or s:
            rows.append((os.path.relpath(p, ROOT), r, s))
        total_r += r
        total_s += s

    for row, r, s in rows:
        if r:
            print(f"  {row}: 可删 {r}" + (f" · 跳过 {s}" if s else ""))
    print(f"\n=== {'已写入' if apply else '空跑'}：可删回退值 {total_r} 处，跳过(嵌套/未定义) {total_s} 处 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
