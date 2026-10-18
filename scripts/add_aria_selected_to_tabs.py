#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 tab 类切换按钮补 :aria-selected（复用 :class 的 active 条件）

模式：<button class="*-tab" :class="{ active: COND }" @click="...">
改为：<button class="*-tab" :class="{ active: COND }" :aria-selected="COND" @click="...">

安全性依据：
  1. COND 就是从 :class 里原样取出的「是否选中」表达式，零逻辑改动
  2. 语义自洽性已逐条核验：COND 与同标签 @click 的效果一致
     （如 detailTab==='info' ↔ @click="detailTab='info'"；
       !adaptiveMode ↔ @click="setMode(false)"）
  3. 已有状态类 aria（六大状态属性，见 STATE 正则）的跳过
  4. 只在 <style> 块之外替换（模板区）

用法：--dry-run 预览；--apply 落盘
"""
import argparse
import glob
import re
import sys
from pathlib import Path

ROOT = Path(r"E:\Program\MARL\study-help-pro")
PAT = re.compile(
    r'(<button\b[^>]*?class="[^"]*\btab\b[^"]*"[^>]*?)'
    r':class="\{\s*active:\s*([^{}]+?)\s*\}"'
    r'([^>]*?>)'
)
# 状态类 aria 属性名（表达选中/展开/按压等状态，而非仅名字）
_STATE_PROPS = ('pressed', 'selected', 'current', 'expanded', 'checked', 'busy')
STATE = re.compile('aria-(?:' + '|'.join(_STATE_PROPS) + ')')


def strip_styles(src: str) -> str:
    return re.sub(r'<style[^>]*>[\s\S]*?</style>', '', src)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    if not args.apply and not args.dry_run:
        print('请指定 --dry-run 或 --apply')
        return 1

    n = 0
    for p in sorted(ROOT.glob('src/**/*.vue')):
        if '__tests__' in p.parts:
            continue
        src = p.read_text(encoding='utf-8')
        tmpl = strip_styles(src)
        out, last, changed = [], 0, False
        for m in PAT.finditer(tmpl):
            pre, cond, post = m.group(1), m.group(2), m.group(3)
            if STATE.search(pre + post):
                continue
            repl = f'{pre}:class="{{ active: {cond} }}" :aria-selected="{cond}"{post}'
            out.append(src[last:m.start()])
            out.append(repl)
            last = m.end()
            n += 1
            changed = True
            print(f'  {p.relative_to(ROOT).as_posix()}: aria-selected="{cond}"')
        if changed:
            out.append(src[last:])
            new = ''.join(out)
            if args.apply:
                p.write_text(new, encoding='utf-8')
    print(f'--- {"已应用" if args.apply else "预览"} {n} 处 ---')
    return 0


if __name__ == '__main__':
    sys.exit(main())
