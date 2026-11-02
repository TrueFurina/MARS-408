#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 HEAD 版本重建「仅含我（设计系统）改动」的内容并暂存到 index。
原理：工作树 = HEAD + 并发会话改动 + 我的改动。把我的两个变换（var 回退删除 + 旧调色板映射）
+ 手工修复重新作用到 HEAD 内容上，即得 HEAD+我的改动（不含并发改动），hash-object -w + update-index 暂存。
不改动工作树文件。用法：python scripts/_reconstruct_tmp.py [path ...]
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARS = os.path.join(ROOT, "src", "assets", "styles", "_variables.css")
defined = set(re.findall(r"(--[\w-]+)\s*:", open(VARS, encoding="utf-8").read()))

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
RGB_MAP = {
    "124,106,242": "accent", "34,197,94": "success", "239,68,68": "danger",
    "245,158,11": "warning", "139,92,246": "subject-ds", "59,130,246": "subject-cn",
    "6,182,212": "subject-co", "244,114,182": "subject-os", "91,139,216": "info",
    "82,196,26": "success", "255,193,7": "warning", "16,185,129": "success", "234,88,12": "warning",
}
VAR_START = re.compile(r"var\(\s*(--[\w-]+)\s*,")
HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
FUNC_RE = re.compile(r"\b(rgba?)\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*([,)])")

MANUAL = {
    "src/assets/styles/_components.css": [("#fca5a5;font-size:0.8125rem}", "var(--color-danger);font-size:0.8125rem}")],
    "src/views/AchievementView.vue": [("rgba(250,204,21,", "rgba(var(--warning-rgb),")],
    "src/views/CreatorDashboardView.vue": [("background: rgba(148,163,184,0.12); color: var(--color-text-2); }", "background: color-mix(in srgb, var(--color-text-2) 12%, transparent); color: var(--color-text-2); }")],
    "src/views/ResourceView.vue": [("85%, #000)", "85%, var(--color-text-invert))")],
    "src/views/LoginView.vue": [
        ("  background: rgba(16,16,36,0.92);", "  background: var(--color-surface);"),
        ("border-radius: 10px; color: #fca5a5; font-size: 13px; }", "border-radius: 10px; color: var(--color-danger); font-size: 13px; }"),
        ("background: linear-gradient(135deg,var(--color-accent),#6d5ae6);", "background: linear-gradient(135deg,var(--color-accent),var(--color-accent-solid));"),
    ],
}


def top_comma(inner):
    d = 0
    for i, ch in enumerate(inner):
        if ch == "(":
            d += 1
        elif ch == ")":
            d -= 1
        elif ch == "," and d == 0:
            return i
    return -1


def strip_fallback(s):
    out, i = [], 0
    while True:
        m = VAR_START.search(s, i)
        if not m:
            out.append(s[i:])
            break
        out.append(s[i:m.start()])
        name = m.group(1)
        op = s.index("(", m.start())
        d, k = 0, op
        while k < len(s):
            if s[k] == "(":
                d += 1
            elif s[k] == ")":
                d -= 1
                if d == 0:
                    break
            k += 1
        inner = s[op + 1:k]
        cm = top_comma(inner)
        fb = inner[cm + 1:] if cm != -1 else ""
        if name in defined and "var(" not in fb and cm != -1:
            out.append(f"var({name})")
        else:
            out.append(s[m.start():k + 1])
        i = k + 1
    return "".join(out)


def palette_map(s):
    def rgb_sub(m):
        base = RGB_MAP.get(f"{int(m.group(2))},{int(m.group(3))},{int(m.group(4))}")
        if not base:
            return m.group(0)
        return f"{m.group(1)}(var(--{base}-rgb))" if m.group(5) == ")" else f"{m.group(1)}(var(--{base}-rgb),"
    s = FUNC_RE.sub(rgb_sub, s)
    return HEX_RE.sub(lambda m: HEX_MAP.get(m.group(0).lower(), m.group(0)), s)


def transform(content, is_vue):
    if not is_vue:
        return palette_map(strip_fallback(content))
    out, last = [], 0
    for m in re.finditer(r"<style[^>]*>.*?</style>", content, re.S | re.I):
        out.append(content[last:m.start()])
        blk = m.group(0)
        open_m = re.match(r"<style[^>]*>", blk, re.I)
        head = open_m.group(0)
        body = blk[len(head):blk.lower().rfind("</style>")]
        out.append(head + palette_map(strip_fallback(body)) + "</style>")
        last = m.end()
    out.append(content[last:])
    return "".join(out)


def main():
    paths = sys.argv[1:]
    for p in paths:
        rel = p.replace("\\", "/")
        head = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT,
                              capture_output=True, text=True, encoding="utf-8").stdout
        new = transform(head, rel.endswith(".vue"))
        for old, rep in MANUAL.get(rel, []):
            if old in new:
                new = new.replace(old, rep)
        tmp = os.path.join(ROOT, ".workbuddy", "_recon_tmp_file")
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(new)
        sha = subprocess.run(["git", "hash-object", "-w", tmp], cwd=ROOT,
                             capture_output=True, text=True).stdout.strip()
        rc = subprocess.run(["git", "update-index", "--cacheinfo", "100644", sha, rel], cwd=ROOT,
                            capture_output=True, text=True)
        changed = sum(1 for a, b in zip(head.splitlines(), new.splitlines()) if a != b)
        print(f"  {rel}: staged {sha[:10]} (~{changed} 行与我相关)  rc={rc.returncode}")
    os.remove(os.path.join(ROOT, ".workbuddy", "_recon_tmp_file"))


if __name__ == "__main__":
    main()
