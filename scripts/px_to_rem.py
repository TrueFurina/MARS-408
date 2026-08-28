#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
px -> rem 安全迁移脚本 (MARS-408 / MARS-408 设计系统)
- root font-size = 16px (浏览器默认, 未重置) -> px/16 = rem, 渲染尺寸不变
- 只转换"尺寸类属性"的 px; 严格排除断点/阴影/hairline/动画/变量定义
- 每个被改文件自动备份到 %TEMP%/pxrem_backup, 验证 OK 后可删
"""
import re, os, sys, shutil, glob

ROOT = r'E:\Program\MARL\study-help-pro'
BACKUP = os.path.join(os.environ.get('TEMP', r'C:\Users\Lenovo\AppData\Local\Temp'), 'pxrem_backup')
DIVISOR = 16.0

# 这些属性的 px 值转换为 rem (用户可见尺寸)
CONVERT_PROPS = {
    'font-size', 'line-height', 'width', 'height', 'min-width', 'max-width',
    'min-height', 'max-height', 'padding', 'padding-top', 'padding-right',
    'padding-bottom', 'padding-left', 'margin', 'margin-top', 'margin-right',
    'margin-bottom', 'margin-left', 'top', 'bottom', 'left', 'right', 'inset',
    'gap', 'row-gap', 'column-gap', 'border-radius', 'border-top-left-radius',
    'border-top-right-radius', 'border-bottom-left-radius', 'border-bottom-right-radius',
    'border-width', 'border-top-width', 'border-right-width', 'border-bottom-width',
    'border-left-width', 'letter-spacing', 'word-spacing', 'flex-basis',
    'max-block-size', 'min-block-size', 'block-size',
}

# 含这些词的整行跳过 (保留 px): 响应式断点 / 阴影 / hairline outline / 动画 / 变量定义
SKIP_RE = re.compile(
    r'@media|box-shadow|text-shadow|\boutline\b|\btransform\b|\bfilter\b|'
    r'clip-path|\bz-index\b|grid-template|aspect-ratio|--[\w-]+\s*:',
    re.IGNORECASE,
)

DECL_RE = re.compile(r'([a-zA-Z-]+)\s*:\s*([^;{}]+);')


def px2rem(m: re.Match) -> str:
    v = float(m.group(1))
    if v == 0:
        return '0'
    rem = v / DIVISOR
    s = ('%.4f' % rem).rstrip('0').rstrip('.')
    if s in ('', '-0'):
        s = '0'
    return s + 'rem'


def convert_line(line: str) -> str:
    if SKIP_RE.search(line):
        return line

    def repl(m: re.Match) -> str:
        prop = m.group(1).strip().lower()
        val = m.group(2)
        if prop in CONVERT_PROPS:
            newval = re.sub(r'(-?\d+\.?\d*)px', px2rem, val)
            return f'{m.group(1)}:{newval};'
        return m.group(0)

    return DECL_RE.sub(repl, line)


STYLE_RE = re.compile(r'(<style[^>]*>)(.*?)(</style>)', re.S)


def process_file(path: str, is_vue: bool) -> bool:
    with open(path, 'r', encoding='utf-8') as f:
        orig = f.read()
    if is_vue:
        def repl(m: re.Match) -> str:
            block = m.group(2)
            newblock = '\n'.join(convert_line(l) for l in block.split('\n'))
            return m.group(1) + newblock + m.group(3)
        new = STYLE_RE.sub(repl, orig)
    else:
        lines = orig.split('\n')
        new = '\n'.join(convert_line(l) for l in lines)
    if new != orig:
        rel = os.path.relpath(path, ROOT)
        bdir = os.path.join(BACKUP, os.path.dirname(rel))
        os.makedirs(bdir, exist_ok=True)
        shutil.copy2(path, os.path.join(BACKUP, rel))
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new)
        return True
    return False


def main() -> None:
    count = 0
    for f in sorted(glob.glob(os.path.join(ROOT, 'src', '**', '*.vue'), recursive=True)):
        if process_file(f, True):
            count += 1
            print('vue  modified:', os.path.relpath(f, ROOT))
    css = os.path.join(ROOT, 'src', 'assets', 'styles', 'main.css')
    if process_file(css, False):
        count += 1
        print('css  modified: src/assets/styles/main.css')
    print(f'\nTotal modified files: {count}')
    print(f'Backups at: {BACKUP}')


if __name__ == '__main__':
    main()
