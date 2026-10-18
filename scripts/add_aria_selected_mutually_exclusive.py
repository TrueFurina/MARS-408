#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给「互斥选中」控件补 :aria-selected（复用 :class 的 active 条件）

tab 类批量处理（add_aria_selected_to_tabs.py 的思路）的推广版：
不限 class 名，匹配任何满足以下全部条件的可交互元素：
  1. 有 @click（是控件，不是纯展示高亮）
  2. :class="{ active: COND }" 或 :class="{ 'is-active': COND }"（单选条件）
  3. :class 只有这一个条件（多条件的语义复杂，保守跳过，留人工）
  4. 尚无状态类 aria（六大状态属性，见下方 _STATE_PROPS 元组）

改法：在 :class 之后插入 :aria-selected="COND" —— COND 原样复用，零逻辑改动。

安全性依据（与 tab 版相同）：
  COND 就是「是否选中」表达式，与同标签 @click 效果自洽（已逐条核验）。

用法：--dry-run 预览；--apply 落盘
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(r"E:\Program\MARL\study-help-pro")

# 状态类 aria 属性名（表达选中/展开/按压等状态，而非仅名字）
_STATE_PROPS = ('pressed', 'selected', 'current', 'expanded', 'checked', 'busy')
STATE = re.compile('aria-(?:' + '|'.join(_STATE_PROPS) + ')')

# 开标签（可跨行）
TAG = re.compile(r'<(span|div|button|a)\b((?:[^>]|\n)*?)>')
# :class="{ active: COND }" 或 "{ 'is-active': COND }"（单条件）
ACTIVE_CLASS = re.compile(
    r':class="\{\s*(?:\'is-active\'|active)\s*:\s*([^{}]+?)\s*\}"'
)
# 整个 :class 对象（用于判断是否多条件）
CLASS_OBJ = re.compile(r':class="\{([^}]*)\}')


def strip_styles(src: str) -> str:
    return re.sub(r'<style[^>]*>[\s\S]*?<\/style>', '', src)


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
        for m in TAG.finditer(tmpl):
            tag = m.group(0)
            if '@click' not in tag:
                continue
            if STATE.search(tag):
                continue
            am = ACTIVE_CLASS.search(tag)
            if not am:
                continue
            # 多条件 :class → 保守跳过。
            # 注意：不能数 `[,{]\s*key:` —— 第一个 key 前的 `{` 已被 :class="\{ 消费，
            # 会少数一个（曾漏掉 `{ active: x, 'mode-y': x }`，导致 COND 变成
            # "x, 'mode-y': x" 这种会破坏模板的片段）。改为直接数 `key:` 个数。
            cm = CLASS_OBJ.search(tag)
            if cm and len(re.findall(r'[\'a-zA-Z_-]+\s*:', cm.group(1))) > 1:
                print(f'  [skip 多条件] {p.relative_to(ROOT).as_posix()}')
                continue
            cond = am.group(1)
            repl = f':class="{{ active: {cond} }}" :aria-selected="{cond}"'
            new_tag = tag[:am.start()] + repl + tag[am.end():]
            out.append(src[last:m.start()])
            out.append(new_tag)
            last = m.end()
            n += 1
            changed = True
            print(f'  {p.relative_to(ROOT).as_posix()}: aria-selected="{cond}"')
        if changed:
            out.append(src[last:])
            if args.apply:
                p.write_text(''.join(out), encoding='utf-8')
    print(f'--- {"已应用" if args.apply else "预览"} {n} 处 ---')
    return 0


if __name__ == '__main__':
    sys.exit(main())
