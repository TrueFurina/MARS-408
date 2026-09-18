#!/usr/bin/env python3
"""
MARS-408 · 设计令牌收敛 codemod（P1）

目标
----
把 .vue <style> 块里绕开令牌的字面值，批量替换为 _variables.css 里**值完全等价**的令牌。

安全边界（本脚本只做"零视觉风险"替换）
--------------------------------------
1. **只替换等价映射**：11px → var(--text-2xs) 因为 --text-2xs = 0.6875rem = 11px。
   凡是 token 值与原值不等的一律不动（如 10px / 22px / 28px / 48px），
   它们涉及真实的视觉微调，需人工决策后单独处理。
2. **按属性区分映射表**：1rem 在 font-size 下是 --text-lg(16px)，在 gap 下是 --space-4(16px)，
   同一数值映射到不同令牌，绝不混用。
3. **只改 <style> 块**，不碰 <template> 的内联 style 与 <script> 的 Canvas 调色板。
4. **默认 dry-run**，必须显式 --apply 才落盘。

令牌真值（取自 _variables.css，均为 px 或 16px 根字号下的等价 px）
------------------------------------------------------------------
字号 --text-*   : 2xs11 xs12 sm13 base14 md15 lg16 xl18 2xl20 3xl24 4xl30 5xl36 6xl44
间距 --space-*  : 1=4 2=8 3=12 4=16 5=20 6=24 7=28 8=32 9=36 10=40 11=44 12=48
                  14=56 16=64 20=80 24=96 32=128

用法
----
    python scripts/codemod_tokens.py                        # dry-run，出统计
    python scripts/codemod_tokens.py --top 20               # 看 TOP N 文件
    python scripts/codemod_tokens.py --file views/X.vue     # 只处理指定文件
    python scripts/codemod_tokens.py --apply                # 落盘
    python scripts/codemod_tokens.py --apply --file a.vue   # 单文件试跑
"""

import argparse
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")

STYLE_RE = re.compile(r"(<style[^>]*>)(.*?)(</style>)", re.S)

# ---- 字号映射：px 值 -> 令牌（仅收录 token 值与 px 完全相等的）----
FONT_PX = {
    11: "--text-2xs", 12: "--text-xs", 13: "--text-sm", 14: "--text-base",
    15: "--text-md", 16: "--text-lg", 18: "--text-xl", 20: "--text-2xl",
    24: "--text-3xl", 30: "--text-4xl", 36: "--text-5xl", 44: "--text-6xl",
}
# rem 形式（组件里大量手写 rem）
FONT_REM = {
    "0.6875": "--text-2xs", "0.75": "--text-xs", "0.8125": "--text-sm",
    "0.875": "--text-base", "0.9375": "--text-md", "1": "--text-lg",
    "1.125": "--text-xl", "1.25": "--text-2xl", "1.5": "--text-3xl",
    "1.875": "--text-4xl", "2.25": "--text-5xl", "2.75": "--text-6xl",
}

# ---- 间距映射 ----
SPACE_PX = {
    4: "--space-1", 8: "--space-2", 12: "--space-3", 16: "--space-4",
    20: "--space-5", 24: "--space-6", 28: "--space-7", 32: "--space-8",
    36: "--space-9", 40: "--space-10", 44: "--space-11", 48: "--space-12",
    56: "--space-14", 64: "--space-16", 80: "--space-20", 96: "--space-24",
    128: "--space-32",
}
SPACE_REM = {
    "0.25": "--space-1", "0.5": "--space-2", "0.75": "--space-3", "1": "--space-4",
    "1.25": "--space-5", "1.5": "--space-6", "1.75": "--space-7", "2": "--space-8",
    "2.25": "--space-9", "2.5": "--space-10", "2.75": "--space-11", "3": "--space-12",
    "3.5": "--space-14", "4": "--space-16", "5": "--space-20", "6": "--space-24",
    "8": "--space-32",
}

FONT_PROP_RE = re.compile(r"(font-size\s*:\s*)([^;}]+)", re.I)
SPACE_PROP_RE = re.compile(
    r"((?:gap|row-gap|column-gap|padding|padding-(?:top|right|bottom|left)|"
    r"margin|margin-(?:top|right|bottom|left))\s*:\s*)([^;}]+)",
    re.I,
)

# ---- 字重 / 行高映射（同样只收录等价项）----
# 注意：font-weight 800/900 与 line-height 1.6/1.5/1.4/1.8 不在令牌刻度内，
# 强行替换会造成视觉微变，属人工决策范畴，本脚本一律不动。
WEIGHT_MAP = {
    "400": "--weight-regular", "500": "--weight-medium",
    "600": "--weight-semibold", "700": "--weight-bold",
}
LEADING_MAP = {
    "1": "--leading-none", "1.2": "--leading-tight", "1.35": "--leading-snug",
    "1.55": "--leading-normal", "1.7": "--leading-relaxed",
}

NUM_PX_RE = re.compile(r"(?<![\w.-])(\d+(?:\.\d+)?)px(?![\w])")
NUM_REM_RE = re.compile(r"(?<![\w.-])(\d+(?:\.\d+)?)rem(?![\w])")


def conv_value(value: str, px_map: dict, rem_map: dict):
    """把值里的等价字面值换成 var()，返回 (新值, 替换次数)"""
    n = 0

    def rep_px(m):
        nonlocal n
        raw = m.group(1)
        try:
            v = float(raw)
        except ValueError:
            return m.group(0)
        iv = int(v) if v.is_integer() else v
        tok = px_map.get(iv)
        if tok:
            n += 1
            return f"var({tok})"
        return m.group(0)

    def rep_rem(m):
        nonlocal n
        raw = m.group(1)
        tok = rem_map.get(raw)
        if tok:
            n += 1
            return f"var({tok})"
        return m.group(0)

    out = NUM_PX_RE.sub(rep_px, value)
    out = NUM_REM_RE.sub(rep_rem, out)
    return out, n


def process_style(body: str):
    """处理一个 style 块内容，返回 (新内容, 替换次数, 明细Counter)"""
    detail = Counter()
    total = 0

    def font_sub(m):
        nonlocal total
        val, n = conv_value(m.group(2), FONT_PX, FONT_REM)
        total += n
        detail["font-size"] += n
        return m.group(1) + val

    def space_sub(m):
        nonlocal total
        val, n = conv_value(m.group(2), SPACE_PX, SPACE_REM)
        total += n
        detail["spacing"] += n
        return m.group(1) + val

    def exact_sub_factory(prop: str, mapping: dict):
        def sub(m):
            nonlocal total
            raw = m.group(2).strip()
            tok = mapping.get(raw)
            if not tok:
                return m.group(0)
            total += 1
            detail[prop] += 1
            return f"{m.group(1)}var({tok})"
        return sub

    out = FONT_PROP_RE.sub(font_sub, body)
    out = SPACE_PROP_RE.sub(space_sub, out)
    out = re.sub(r"(font-weight\s*:\s*)([^;}]+)", exact_sub_factory("font-weight", WEIGHT_MAP), out, flags=re.I)
    out = re.sub(r"(line-height\s*:\s*)([^;}]+)", exact_sub_factory("line-height", LEADING_MAP), out, flags=re.I)
    return out, total, detail


def walk(target=None):
    for dp, dn, fn in os.walk(SRC):
        for f in sorted(fn):
            if not f.endswith(".vue"):
                continue
            rel = os.path.relpath(os.path.join(dp, f), SRC).replace("\\", "/")
            if target and rel != target:
                continue
            yield rel, os.path.join(dp, f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正写盘（默认 dry-run）")
    ap.add_argument("--file", help="只处理指定相对路径，如 views/DashboardView.vue")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    per_file = []
    grand = Counter()
    changed_files = 0

    for rel, abs_p in walk(args.file):
        # newline="" —— 必须原样保留 CRLF。否则 Windows 下会把整个文件重写成 LF，
        # 产生"全文件变更"的假 diff，污染 git 并与并发会话撞车。
        text = open(abs_p, encoding="utf-8", errors="ignore", newline="").read()

        out_parts = []
        file_n = 0
        file_detail = Counter()
        last = 0
        for m in STYLE_RE.finditer(text):
            out_parts.append(text[last : m.start()])
            new_body, n, detail = process_style(m.group(2))
            file_n += n
            file_detail.update(detail)
            out_parts.append(m.group(1) + new_body + m.group(3))
            last = m.end()
        out_parts.append(text[last:])

        if file_n:
            changed_files += 1
            per_file.append((rel, file_n, file_detail))
            grand.update(file_detail)
            if args.apply:
                new_text = "".join(out_parts)
                if new_text != text:
                    with open(abs_p, "w", encoding="utf-8", newline="") as fp:
                        fp.write(new_text)

    mode = "APPLY 已落盘" if args.apply else "DRY-RUN 预览"
    print(f"[codemod-tokens] {mode}")
    print(f"[codemod-tokens] 可改文件 {changed_files} 个，等价替换总数 {sum(grand.values())}")
    for k, v in grand.most_common():
        print(f"    {k:12} {v}")

    print(f"\n--- TOP {args.top} ---")
    for rel, n, d in sorted(per_file, key=lambda x: -x[1])[: args.top]:
        det = " ".join(f"{k}={v}" for k, v in sorted(d.items()))
        print(f"  {n:5}  {rel}   {det}")

    if not args.apply:
        print("\n[hint] 以上均为**值完全等价**的替换，零视觉风险。")
        print("[hint] 确认后加 --apply 落盘；建议先 --file 单文件试跑。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
