#!/usr/bin/env python3
"""
cleanup_tokens_3.py — P2 死 fallback 清零 (Step 4 of audit-report roadmap)

仅剥离「变量已恒定义」的 var(--token, <hardcoded>) 死 fallback，
改为纯 var(--token)。对 __未定义__ 的 token 保留其 fallback（防御性，不误伤）。

安全策略：
1. 先扫描 _variables.css 提取所有已定义 token 名。
2. 对每个 .vue 文件，正则表达式替换 var(--NAME, VAL) -> var(--NAME)，
   仅当 NAME 在已定义集合内。
3. 不触碰未定义 token 的 fallback（那是真·防御性写法）。
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARS_CSS = os.path.join(ROOT, "src", "assets", "styles", "_variables.css")
SRC_DIR = os.path.join(ROOT, "src")

# 1) 提取已定义 token 名
with open(VARS_CSS, "r", encoding="utf-8") as f:
    css = f.read()
defined = set(re.findall(r"--([\w-]+)\s*:", css))
print(f"[scan] defined tokens in _variables.css: {len(defined)}")

# 2) 匹配 var(--NAME, VAL)，VAL 允许一层嵌套括号 (如 rgba(...))
pattern = re.compile(r"var\(--([\w-]+),\s*((?:[^()]|\([^()]*\))*)\)")

total_files = 0
total_subs = 0
report = []

for dirpath, _, filenames in os.walk(SRC_DIR):
    for fn in filenames:
        if not fn.endswith(".vue"):
            continue
        path = os.path.join(dirpath, fn)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        subs = 0

        def repl(m):
            global subs
            name = m.group(1)
            if name in defined:
                subs += 1
                return f"var(--{name})"
            return m.group(0)  # 未定义 -> 保留原 fallback

        new_content = pattern.sub(repl, content)
        if subs:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            total_files += 1
            total_subs += subs
            report.append((os.path.relpath(path, ROOT), subs))

print(f"[done] {total_files} files, {total_subs} dead-fallback substitutions")
for rel, n in report:
    print(f"  {rel}: {n}")
