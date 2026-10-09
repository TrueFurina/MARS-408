#!/usr/bin/env python3
"""
芒得很职 · 设计令牌防回归机检（token_scan）

设计纪律（src/assets/styles/_variables.css 第 24 行）：
    "组件只引用语义层（--color-* / --subject-*），绝不在组件里写死颜色。"

本脚本静态扫描 src 下**除 _variables.css（令牌定义源）之外**的所有源码，
检出"硬编码颜色字面量"——即违反上述纪律、未能收敛到令牌的漂移候选。

判定（保守，分类上报）：
  - 命中 hex(#RGB/#RRGGBB/#RRGGBBAA) / rgb(a)() / hsl(a)() 字面量
  - 排除：① 注释；② CSS id 选择器（`#id {` 非颜色）；③ 令牌定义文件本身

分类：
  - brand-violet  品牌紫族已知变体（#7c6af2 / #6b5cdb / #8B5CF6 / #A98CDD 及其 rgb 等价）
  - known-token-eq 与 _variables.css 中已定义语义色值完全等价的其它硬编码（如 #E6E9ED 正文）
  - untracked     其余未追踪硬编码（最该优先收敛；含 .ts 中 Canvas/图表调色板，需人工确认）

退出码：
  0 = 未超过阈值（或默认咨询级不阻断）
  1 = 命中数超过 --max / 品牌紫超过 --max-brand（防回归门禁）

用法：
  python scripts/token_scan.py                 # 咨询级，仅 stdout 摘要
  python scripts/token_scan.py --json out.json # 写机器可读报告
  python scripts/token_scan.py --by-color      # 附带按颜色值聚合 TOP 表
  python scripts/token_scan.py --max 50        # 硬门禁：总硬编码超 50 处则 exit 1
  python scripts/token_scan.py --max-brand 0   # 硬门禁：品牌紫未清零则 exit 1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
TOKEN_DEF = SRC / "assets" / "styles" / "_variables.css"
SCAN_EXTS = {".vue", ".ts", ".js", ".css"}

# 品牌紫族已知变体（与设计令牌审计 2026-10-09 口径一致）
BRAND_VIOLET_HEX = {"7c6af2", "6b5cdb", "8b5cf6", "a98cdd"}
BRAND_VIOLET_RGB = {"124,106,242", "107,92,219", "139,92,246", "169,140,221"}

# 颜色字面量组合正则（hex 8/6/3 位；rgb/rgba；hsl/hsla）
COLOR_RE = re.compile(
    r"#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])"
    r"|rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)"
    r"|hsla?\(\s*(\d+)\s*,\s*(\d+)%?\s*,\s*(\d+)%?\s*(?:,\s*([\d.]+)\s*)?\)"
)


def strip_comments(text: str, suffix: str) -> str:
    """保守剥离注释，保留 URL（http(s):// 不被当行注释）。"""
    if suffix == ".vue":
        text = re.sub(r"<!--[\s\S]*?-->", "", text)
    # 行注释：排除协议分隔符前的 //
    text = re.sub(r"(?<!:)//[^\n]*", "", text)
    # 块注释
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)
    return text


def expand_hex(h: str) -> str:
    h = h.lower()
    if len(h) == 3:
        return "".join(c * 2 for c in h)
    if len(h) == 8:
        return h[:6]
    return h


def normalize_rgb(r: str, g: str, b: str, a: str | None = None) -> str:
    key = f"{int(r)},{int(g)},{int(b)}"
    if a is not None:
        key += f",{float(a)}"
    return key


def extract_known_from_def() -> set[str]:
    """从 _variables.css 抽取所有已定义色值（hex6 + rgb 归一），作为 known 真值集。"""
    known: set[str] = set()
    if not TOKEN_DEF.exists():
        return known
    text = strip_comments(TOKEN_DEF.read_text(encoding="utf-8"), ".css")
    for m in COLOR_RE.finditer(text):
        if m.group(1):
            known.add(expand_hex(m.group(1)))
        elif m.group(2) is not None:
            known.add(normalize_rgb(m.group(2), m.group(3), m.group(4), m.group(5)))
    return known


KNOWN = extract_known_from_def()


def classify(hex6: str | None, rgb_key: str | None) -> str:
    if hex6 is not None:
        if hex6 in BRAND_VIOLET_HEX:
            return "brand-violet"
        if hex6 in KNOWN:
            return "known-token-eq"
        return "untracked"
    if rgb_key is not None:
        if rgb_key in BRAND_VIOLET_RGB:
            return "brand-violet"
        if rgb_key in KNOWN:
            return "known-token-eq"
        return "untracked"
    return "untracked"


def scan() -> list[dict]:
    findings: list[dict] = []
    for f in sorted(SRC.rglob("*")):
        if f.suffix not in SCAN_EXTS:
            continue
        if f.resolve() == TOKEN_DEF.resolve():
            continue
        try:
            raw = f.read_text(encoding="utf-8")
        except Exception:
            continue
        stripped = strip_comments(raw, f.suffix)
        for m in COLOR_RE.finditer(stripped):
            line = stripped[: m.start()].count("\n") + 1
            if m.group(1):
                val = "#" + m.group(1).lower()
                # 排除 CSS id 选择器（#xxx {）
                nxt = stripped[m.end():].lstrip()
                if nxt.startswith("{"):
                    continue
                hex6 = expand_hex(m.group(1))
                rgb_key = None
                display = val
            else:
                r = m.group(2) or m.group(6)
                g = m.group(3) or m.group(7)
                b = m.group(4) or m.group(8)
                a = m.group(5) or m.group(9)
                hex6 = None
                rgb_key = normalize_rgb(r, g, b, a)
                display = (
                    f"rgb({r},{g},{b})" if a is None
                    else f"rgba({r},{g},{b},{a})"
                )
            cat = classify(hex6, rgb_key)
            findings.append({
                "file": f.relative_to(ROOT).as_posix(),
                "line": line,
                "value": display,
                "category": cat,
            })
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="设计令牌硬编码颜色防回归机检")
    ap.add_argument("--json", metavar="PATH", help="写机器可读 JSON 报告")
    ap.add_argument("--by-color", action="store_true", help="附带按颜色值聚合 TOP 表")
    ap.add_argument("--max", type=int, default=None,
                    help="总硬编码超此阈值则 exit 1（防回归门禁）")
    ap.add_argument("--max-brand", type=int, default=None,
                    help="品牌紫未清零（超此值）则 exit 1")
    args = ap.parse_args()

    findings = scan()
    by_cat = Counter(f["category"] for f in findings)
    by_ext = Counter(f["file"].rsplit(".", 1)[-1] for f in findings)
    by_file = Counter(f["file"] for f in findings)

    total = len(findings)
    brand = by_cat.get("brand-violet", 0)
    known = by_cat.get("known-token-eq", 0)
    untracked = by_cat.get("untracked", 0)

    print("=" * 64)
    print("设计令牌防回归机检 · token_scan")
    print("=" * 64)
    print(f"扫描目标 : {SRC}")
    print(f"排除定义 : {TOKEN_DEF.relative_to(ROOT).as_posix()}")
    print("-" * 64)
    print(f"硬编码颜色总数      : {total}")
    print(f"  ├ brand-violet   : {brand}   (品牌紫族，归一明确待办)")
    print(f"  ├ known-token-eq : {known}   (与令牌等价，应改 var())")
    print(f"  └ untracked      : {untracked}   (未追踪，需人工确认)")
    print("-" * 64)
    print("按扩展名 : " + ", ".join(f".{e}={c}" for e, c in sorted(by_ext.items())))
    print("TOP 文件 :")
    for fn, c in by_file.most_common(12):
        print(f"  {c:4d}  {fn}")
    if args.by_color:
        by_color = Counter(f["value"] for f in findings)
        print("-" * 64)
        print("TOP 颜色值 :")
        for v, c in by_color.most_common(20):
            print(f"  {c:4d}  {v}")
    print("=" * 64)

    if args.json:
        report = {
            "summary": {
                "total": total,
                "by_category": dict(by_cat),
                "by_ext": dict(by_ext),
            },
            "top_files": by_file.most_common(50),
            "findings": findings,
        }
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"JSON 报告已写 : {args.json}")

    rc = 0
    if args.max is not None and total > args.max:
        print(f"[门禁] 总硬编码 {total} 超过 --max {args.max} → exit 1")
        rc = 1
    if args.max_brand is not None and brand > args.max_brand:
        print(f"[门禁] 品牌紫 {brand} 超过 --max-brand {args.max_brand} → exit 1")
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
