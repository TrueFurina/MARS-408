#!/usr/bin/env python3
"""前端性能门禁：禁止"输入事件直接同步触发整图重绘"的反模式。

反模式示例（会造成输入卡顿 / 损害 INP）：
    <input v-model="searchQuery" @input="draw" />
其中 draw() 是对 canvas / SVG 的整图重绘（力导布局、图渲染等），逐字同步
重绘代价高昂。正确做法是用防抖（@input="debouncedDraw"）或 requestAnimationFrame 收敛。

扫描规则（窄而精确，避免误报）：
    仅匹配 `@input="<单一标识符>"` 且该标识符落在重绘函数黑名单
    （draw / render / redraw / drawGraph / renderGraph / updateGraph / layout /
     repaint / paint）。
    不匹配 `@input="debouncedDraw"`（已防抖）、`@input="(e) => ..."`（内联）、
    `@input="onInput"`（非重绘）等合法写法。

退出码：发现违规 -> 1；全部通过 -> 0。
"""
from __future__ import annotations

import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 整图重绘函数黑名单：直接绑到 @input 即视为反模式
REDRAW_FUNCS = {
    "draw", "render", "redraw", "drawgraph", "rendergraph",
    "updategraph", "layout", "repaint", "paint",
}

# 匹配 @input="xxx"（xxx 为单一 token，可能前后有空格）
INPUT_RE = re.compile(r'@input\s*=\s*"([A-Za-z_][A-Za-z0-9_]*)"\s*')


def scan_file(path: str) -> list[str]:
    """返回该文件中的违规行（带行号）。"""
    violations: list[str] = []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        return violations
    for i, line in enumerate(lines, start=1):
        for m in INPUT_RE.finditer(line):
            token = m.group(1)
            if token.lower() in REDRAW_FUNCS:
                violations.append(f"  {os.path.relpath(path, ROOT)}:{i}: @input=\"{token}\"")
    return violations


def main() -> int:
    files = glob.glob(os.path.join(ROOT, "src", "**", "*.vue"), recursive=True)
    files += glob.glob(os.path.join(ROOT, "src", "**", "*.ts"), recursive=True)
    all_viol: list[str] = []
    for f in files:
        if "__tests__" in f or "node_modules" in f:
            continue
        all_viol.extend(scan_file(f))

    if all_viol:
        print("❌ perf_scan: 发现输入直接触发整图重绘的反模式（应使用防抖）：")
        for v in all_viol:
            print(v)
        print("\n修复：用 debounce(() => draw(), 120) 包裹，@input 绑定防抖后的函数。")
        return 1
    print("✅ perf_scan: 未检出 @input 直接整图重绘反模式")
    return 0


if __name__ == "__main__":
    sys.exit(main())
