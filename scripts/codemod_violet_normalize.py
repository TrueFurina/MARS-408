#!/usr/bin/env python3
"""
芒得很职 · 品牌紫族归一 codemod（10-28 窗口用，冻结期请勿执行）

背景：设计令牌审计 2026-10-09 发现 src/ 下品牌紫写死（4 个已知变体
#7c6af2 / #6b5cdb / #8B5CF6 / #A98CDD 及其 rgb 等价），违反
`src/assets/styles/_variables.css` 第 24 行纪律：组件只引用语义层
（--color-* / --subject-*），绝不在组件里写死颜色。

本脚本把品牌紫统一收敛到 `--accent-primary`（已在令牌源定义）。

安全性约束（重要）
--------------------------------------------------------------------------
1) CSS 变量 `var(--accent-primary)` **仅在样式上下文有效**：
     · .vue 的 <style> / <template style=> / .css  → 直接替换安全（AUTO）
     · .ts / .js（Canvas 调色板、JS 字符串）        → `var()` 无效，禁止自动替换
2) 带透明度的写法 `rgba(...,a)` / `#RRGGBBAA` 不得直接换成不透明 var()，
   **否则丢失透明度造成视觉回归** → 一律归为 MANUAL，需人工用
   `color-mix(in srgb, var(--accent-primary) a%, transparent)` 或等价方案处理。

故 `--apply` 只改写「不透明的 .vue/.css 品牌紫」；其余（带透明度、.ts/.js）
**仅列出、不改动**，需人工收敛。

用法
--------------------------------------------------------------------------
    python scripts/codemod_violet_normalize.py            # 默认 dry-run，仅打印计划
    python scripts/codemod_violet_normalize.py --apply    # 实际改写不透明 .vue/.css
    python scripts/codemod_violet_normalize.py --by-ext  # 按扩展名聚合计数

退出码：0（dry-run 或成功改写）。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
TOKEN_DEF = SRC / "assets" / "styles" / "_variables.css"
AUTO_EXTS = {".vue", ".css"}
REPORT_EXTS = {".ts", ".js"}

# 品牌紫族 4 已知变体（与设计令牌审计 2026-10-09 口径一致）
BRAND_HEX = {"7c6af2", "6b5cdb", "8b5cf6", "a98cdd"}
BRAND_RGB = {
    "124,106,242": "7c6af2",
    "107,92,219": "6b5cdb",
    "139,92,246": "8b5cf6",
    "169,140,221": "a98cdd",
}

# 6 位 hex（大小写不敏感，且后不跟第 7 位 hex，避免误吞 8 位）
HEX_RE = re.compile(r"#([0-9a-fA-F]{6})(?![0-9a-fA-F])")
# rgb / rgba：捕获三组 + 可选 alpha
RGB_RE = re.compile(
    r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*([\d.]+)\s*)?\)"
)


def is_brand_hex(token: str) -> bool:
    return token.lower() in BRAND_HEX


def is_brand_rgb(r: str, g: str, b: str) -> bool:
    return f"{int(r)},{int(g)},{int(b)}" in BRAND_RGB


def scan() -> list[dict]:
    """返回每文件命中列表，每条含 (原始文本, 是否可自动替换)。"""
    out: list[dict] = []
    for f in sorted(SRC.rglob("*")):
        if f.suffix not in (AUTO_EXTS | REPORT_EXTS):
            continue
        if f.resolve() == TOKEN_DEF.resolve():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        found = []
        for m in HEX_RE.finditer(text):
            if not is_brand_hex(m.group(1)):
                continue
            # 6 位 hex 总是不透明 → 自动与否仅取决于扩展名
            auto = f.suffix in AUTO_EXTS
            found.append({"raw": m.group(0), "auto": auto, "alpha": False})
        for m in RGB_RE.finditer(text):
            if not is_brand_rgb(m.group(1), m.group(2), m.group(3)):
                continue
            alpha = m.group(4)
            # 带透明度（alpha 存在且非 1）→ 一律 MANUAL（防视觉回归）
            is_opaque = alpha is None or alpha in ("1", "1.0")
            if not is_opaque:
                found.append({"raw": m.group(0), "auto": False, "alpha": True})
            else:
                found.append({"raw": m.group(0), "auto": f.suffix in AUTO_EXTS, "alpha": False})
        if found:
            out.append({
                "file": f.relative_to(ROOT).as_posix(),
                "ext": f.suffix,
                "matches": found,
            })
    return out


def apply_fixes(items: list[dict]) -> tuple[int, int]:
    """只改写「不透明且属 .vue/.css」的命中。返回 (改动文件数, 替换处数)。"""
    changed_files = 0
    replaced = 0
    for it in items:
        auto_matches = [m for m in it["matches"] if m["auto"]]
        if not auto_matches:
            continue
        p = ROOT / it["file"]
        text = p.read_text(encoding="utf-8")
        new_text, n = _replace_text(text)
        if n:
            p.write_text(new_text, encoding="utf-8")
            changed_files += 1
            replaced += n
    return changed_files, replaced


def _replace_text(text: str) -> tuple[str, int]:
    n = 0

    def hex_sub(m: re.Match) -> str:
        nonlocal n
        if is_brand_hex(m.group(1)):
            n += 1
            return "var(--accent-primary)"
        return m.group(0)

    text = HEX_RE.sub(hex_sub, text)

    def rgb_sub(m: re.Match) -> str:
        nonlocal n
        if is_brand_rgb(m.group(1), m.group(2), m.group(3)):
            alpha = m.group(4)
            is_opaque = alpha is None or alpha in ("1", "1.0")
            if is_opaque:
                n += 1
                return "var(--accent-primary)"
        return m.group(0)

    text = RGB_RE.sub(rgb_sub, text)
    return text, n


def main() -> int:
    ap = argparse.ArgumentParser(description="品牌紫族归一 codemod（10-28 窗口用）")
    ap.add_argument("--apply", action="store_true",
                    help="实际改写不透明的 .vue/.css；默认仅 dry-run 打印计划")
    ap.add_argument("--by-ext", action="store_true", help="按扩展名聚合计数")
    args = ap.parse_args()

    items = scan()
    if not items:
        print("[codemod] 未发现品牌紫硬编码，无需处理。")
        return 0

    auto = [m for it in items for m in it["matches"] if m["auto"]]
    manual = [m for it in items for m in it["matches"] if not m["auto"]]
    manual_alpha = [m for m in manual if m["alpha"]]
    manual_ts = [m for m in manual if not m["alpha"]]  # .ts/.js 不透明，需提取常量

    print("=" * 64)
    print("品牌紫族归一 codemod")
    print("=" * 64)
    print(f"模式           : {'APPLY（改写不透明 .vue/.css）' if args.apply else 'dry-run（仅报告）'}")
    print(f"可自动改写     : {len(auto)} 处（不透明 .vue/.css）")
    print(f"需人工·透明度  : {len(manual_alpha)} 处（rgba 带 alpha，防视觉回归）")
    print(f"需人工·.ts/.js : {len(manual_ts)} 处（var() 无效，提取常量）")
    print("-" * 64)
    for it in items:
        tags = []
        for m in it["matches"]:
            if m["auto"]:
                tags.append(f"  [AUTO]   {m['raw']} -> var(--accent-primary)")
            elif m["alpha"]:
                tags.append(f"  [ALPHA]  {m['raw']}  (需 color-mix)")
            else:
                tags.append(f"  [TS/JS]  {m['raw']}  (提取常量)")
        if tags:
            print(f"{it['file']}")
            if args.by_ext:
                print(f"    ({len(it['matches'])} 处)")
            else:
                print("\n".join(tags))
    print("=" * 64)

    if args.apply:
        cf, rp = apply_fixes(items)
        print(f"[codemod] 已改写 {cf} 个文件、{rp} 处（不透明 .vue/.css）→ var(--accent-primary)")
        remain = len(manual_alpha) + len(manual_ts)
        if remain:
            print(f"[codemod] ⚠️ 仍有 {remain} 处需人工处理"
                  f"（透明度 {len(manual_alpha)} + .ts/.js {len(manual_ts)}，见上方列表）。")
        print("[codemod] 改写后请跑：python scripts/token_scan.py --update-baseline "
              "scripts/token_scan.baseline.json")
        return 0

    print("[codemod] dry-run 完成，未改动任何文件。加 --apply 实际改写。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
