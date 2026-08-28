#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_tokens.py — MARS-408 设计系统 · 单一真相源(SSOT)漂移检测器

权威源(canonical): src/assets/styles/_variables.css 的 :root 块（解析 var() 链后的值）
消费者(consumers):  public/showcase/*.html 的内联 :root  +  design-system/showcase.html

判定规则:
- 同名 token: 比对 权威解析值 vs 消费者解析值（均解析 var() 链 + 归一化后）。
    - 值相同           -> OK（对齐）
    - 值不同           -> DRIFT（真漂移，须修复）
- 仅存在于消费者       -> EXT（表面扩展 token，预期，不报错）
- 仅存在于权威         -> SUB（消费者子集，预期，不报错）

归一化（视觉等价视为相同）:
- 去空格/换行、转小写
- CSS 数值简写：`.03` == `0.03`、`.2s` == `0.2s`（`(?<!digit).digit` 前补 0）
- CSS 十六进制简写：`#fff` == `#ffffff`（3 位展开为 6 位）
- 渐变默认停靠位 0%/100% 视为冗余并剥离

退出码: 0 = 零漂移； 1 = 发现漂移； 2 = 解析失败。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARS_CSS = os.path.join(ROOT, "src", "assets", "styles", "_variables.css")
CONSUMER_DIRS = [
    os.path.join(ROOT, "public", "showcase"),
    os.path.join(ROOT, "design-system"),
]


def norm(v: str) -> str:
    """归一化 CSS 值用于比对（视觉等价视为相同）。"""
    v = v.strip().lower().replace(" ", "").replace("\n", "").replace("\r", "")
    # CSS 数值简写 .03 -> 0.03 / .2s -> 0.2s（仅当前面不是数字时补 0）
    v = re.sub(r"(?<![\d])\.(\d)", r"0.\1", v)
    # CSS 十六进制简写 #fff -> #ffffff（3 位展开为 6 位，视觉等价）
    v = re.sub(r"#([0-9a-f])([0-9a-f])([0-9a-f])\b", r"#\1\1\2\2\3\3", v)
    # 剥离渐变默认停靠位（视觉等价）
    v = v.replace("0%,", ",").replace(",100%", "").replace("100%)", ")").replace("0%)", ")")
    return v


def extract_root_block(text: str, marker: str = ":root") -> str:
    """提取第一个 :root { ... } 块内容（扁平，无嵌套花括号）。"""
    idx = text.find(marker)
    if idx == -1:
        return ""
    b = text.find("{", idx)
    if b == -1:
        return ""
    depth = 0
    for i in range(b, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[b + 1:i]
    return ""


def parse_tokens(block: str) -> dict:
    """解析 :root 块为 {name: raw_value}。"""
    out = {}
    for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;]+)", block):
        out[m.group(1)] = m.group(2).strip()
    return out


def resolve_vars(tokens: dict) -> dict:
    """解析 var(--x) 链，返回 {name: resolved_value}。"""
    resolved = {}
    for name, val in tokens.items():
        cur = val
        for _ in range(6):
            refs = re.findall(r"var\((--[\w-]+)\)", cur)
            if not refs:
                break
            for ref in refs:
                cur = cur.replace(f"var({ref})", tokens.get(ref, "UNDEFINED"))
        resolved[name] = cur
    return resolved


def main() -> int:
    # ---- 1) 解析权威源 ----
    with open(VARS_CSS, "r", encoding="utf-8") as f:
        css = f.read()
    canonical_raw = parse_tokens(extract_root_block(css, ":root"))
    canonical = resolve_vars(canonical_raw)
    if not canonical:
        print(f"[ERROR] 无法从 {VARS_CSS} 解析 :root", file=sys.stderr)
        return 2
    print(f"[canonical] _variables.css :root 解析到 {len(canonical)} 个令牌\n")

    # ---- 2) 遍历消费者 ----
    consumers = []
    for d in CONSUMER_DIRS:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".html"):
                consumers.append(os.path.join(d, fn))

    total_drift = 0
    for path in consumers:
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        block = extract_root_block(html, ":root")
        if not block:
            print(f"  ! 跳过（无 :root）: {os.path.relpath(path, ROOT)}")
            continue
        cons = resolve_vars(parse_tokens(block))

        matched = 0
        ext = 0
        drifts = []
        for name, cval in cons.items():
            if name in canonical:
                if norm(canonical[name]) == norm(cval):
                    matched += 1
                else:
                    drifts.append((name, canonical[name], cval))
            else:
                ext += 1

        rel = os.path.relpath(path, ROOT)
        if drifts:
            total_drift += len(drifts)
            print(f"  [DRIFT] {rel}")
            for name, cv, ov in drifts:
                print(f"          {name}")
                print(f"             canonical: {cv}")
                print(f"             consumer: {ov}")
        else:
            print(f"  [OK]    {rel}  (对齐 {matched} · 扩展 {ext})")

    print()
    if total_drift == 0:
        print("=== 结论: 零漂移 (ZERO DRIFT) — 所有消费者与 _variables.css 对齐 ===")
        return 0
    else:
        print(f"=== 结论: 发现 {total_drift} 处漂移，需修复 ===")
        return 1


if __name__ == "__main__":
    sys.exit(main())
