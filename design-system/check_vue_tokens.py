#!/usr/bin/env python3
"""
MARS-408 · Vue 侧设计令牌漂移门禁

背景
----
既有的 design-system/check_tokens.py 只校验 public/showcase/*.html 与
design-system/showcase.html，对 src/**/*.vue 的匹配次数为 0 —— 即 Vue 应用侧
73 个组件完全处于盲区，导致 _variables.css 定义的 343 个令牌中 183 个零引用。

本脚本补上这一层：**扫描 .vue 的 <style> 块，检测绕开令牌的字面值**。

检查项
------
H1  裸 hex 颜色（应改 var(--color-*) / var(--accent-*) / var(--subject-*)）
H2  font-size 字面值（应改 var(--text-*)，当前 22 种档位 → 目标 12 档）
H3  间距字面值 gap/padding/margin（应改 var(--space-*)，当前 28 种 → 目标 9 档）

合规例外（不报错）
------------------
1. 文件头样式块内出现 `@a11y-exempt: canvas-palette` 注释 → 该文件裸 hex 豁免
   （Canvas / SVG 绘图需要具体色值，属设计系统规范 §6 明文允许的例外）
2. 值为 0 / auto / inherit / 100% 等关键字
3. 1px / 2px 用于 border-width 与 hairline（规范允许）

用法
----
    python design-system/check_vue_tokens.py                # 报告当前违规
    python design-system/check_vue_tokens.py --baseline     # 写入基线
    python design-system/check_vue_tokens.py --strict       # 与基线比，新增违规即失败
    python design-system/check_vue_tokens.py --top 20       # 显示 TOP N 文件

退出码：0 通过 / 1 有新增违规（仅 --strict）/ 2 解析失败
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
BASELINE = os.path.join(ROOT, "design-system", "vue_token_baseline.json")

STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.S)
EXEMPT_RE = re.compile(r"@a11y-exempt:\s*canvas-palette")

HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")

# font-size: 0.875rem / 13px / var(--text-base)
FONT_SIZE_RE = re.compile(
    r"font-size\s*:\s*([^;}]+?)\s*(?:;|$)", re.I
)
# gap / padding / margin（含 -top/-bottom/... ）里的 px 值
SPACING_RE = re.compile(
    r"\b(?:gap|row-gap|column-gap|padding|padding-(?:top|right|bottom|left)|"
    r"margin|margin-(?:top|right|bottom|left))\s*:\s*([^;}]+?)\s*(?:;|$)",
    re.I,
)

KEYWORDS = {"0", "auto", "inherit", "initial", "unset", "100%", "50%", "none"}
# 允许的 hairline / border 场景：值出现在 border 相关属性里时不计入
BORDER_CTX_RE = re.compile(r"border(-width)?\s*:", re.I)

# 已知的合规 palette 文件（Canvas/SVG 绘图，规范 §6 例外）
KNOWN_PALETTE_FILES = {
    "components/KnowledgeGraph.vue",
    "components/ForceGraph.vue",
    "components/KnowledgeGraph3D.vue",
    "views/CareerTrainingView.vue",
}


def extract_style_blocks(path):
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return []
    return [(m.start(), m.group(1)) for m in STYLE_RE.finditer(text)]


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def check_file(rel_path):
    """返回 {kind: [(line, value), ...]}"""
    abs_path = os.path.join(SRC, rel_path.replace("/", os.sep))
    try:
        text = open(abs_path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return {}

    findings = defaultdict(list)
    blocks = extract_style_blocks(abs_path)
    exempt = (
        any(EXEMPT_RE.search(body) for _, body in blocks)
        or rel_path in KNOWN_PALETTE_FILES
    )

    for start, body in blocks:
        for m in HEX_RE.finditer(body):
            findings["hex"].append((line_of(text, start + m.start()), m.group(0)))
        if exempt:
            findings.pop("hex", None)

        for m in FONT_SIZE_RE.finditer(body):
            val = m.group(1).strip()
            if "var(" in val:
                continue
            if val.lower() in KEYWORDS:
                continue
            if re.search(r"\d", val):
                findings["font-size"].append((line_of(text, start + m.start()), val))

        for m in SPACING_RE.finditer(body):
            prop_and_val = m.group(0)
            if "var(" in prop_and_val:
                continue
            if BORDER_CTX_RE.search(prop_and_val):
                continue
            val = m.group(1).strip()
            nums = re.findall(r"(\d+(?:\.\d+)?)px", val)
            for n in nums:
                if float(n) <= 2:  # hairline
                    continue
                findings["spacing"].append((line_of(text, start + m.start()), f"{n}px"))

    return dict(findings)


def collect():
    results = {}
    for dp, dn, fn in os.walk(SRC):
        for f in fn:
            if not f.endswith(".vue"):
                continue
            abs_p = os.path.join(dp, f)
            rel = os.path.relpath(abs_p, SRC).replace("\\", "/")
            got = check_file(rel)
            if got:
                results[rel] = got
    return results


def summarize(results):
    totals = Counter()
    for f, kinds in results.items():
        for k, items in kinds.items():
            totals[k] += len(items)
    return totals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", action="store_true", help="写入基线文件")
    ap.add_argument("--strict", action="store_true", help="与基线比对，新增违规则失败")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    results = collect()
    totals = summarize(results)
    total = sum(totals.values())

    print(f"[vue-token-gate] 扫描 {len(results)} 个含违规的 .vue 文件")
    print(f"[vue-token-gate] 违规总数 {total}")
    for k in ("hex", "font-size", "spacing"):
        print(f"    {k:12} {totals.get(k, 0)}")

    if args.baseline:
        payload = {
            "totals": dict(totals),
            "total": total,
            "files": {
                f: {k: len(v) for k, v in kinds.items()} for f, kinds in results.items()
            },
        }
        with open(BASELINE, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
        print(f"\n[baseline] 已写入 {BASELINE}")
        print("[baseline] 基线含义：存量违规被冻结，CI 只拦截**新增**违规。")
        return 0

    print(f"\n--- 违规最集中的 TOP {args.top} 文件 ---")
    order = sorted(
        results.items(),
        key=lambda kv: -sum(len(v) for v in kv[1].values()),
    )
    for f, kinds in order[: args.top]:
        n = sum(len(v) for v in kinds.values())
        detail = " ".join(f"{k}={len(v)}" for k, v in sorted(kinds.items()))
        exempt = " [palette 豁免]" if f in KNOWN_PALETTE_FILES else ""
        print(f"  {n:5}  {f}{exempt}   {detail}")

    if args.strict:
        if not os.path.exists(BASELINE):
            print("\n[ERROR] 缺少基线，请先运行 --baseline", file=sys.stderr)
            return 2
        base = json.load(open(BASELINE, encoding="utf-8"))
        regressions = []
        for f, kinds in results.items():
            b = base["files"].get(f, {})
            for k, items in kinds.items():
                if len(items) > b.get(k, 0):
                    regressions.append((f, k, b.get(k, 0), len(items)))
        if regressions:
            print(f"\n[FAIL] {len(regressions)} 项新增违规：")
            for f, k, old, new in regressions:
                print(f"    {f}  {k}: {old} → {new}")
            return 1
        print("\n[PASS] 无新增违规（存量冻结在基线内）")
        return 0

    print("\n[hint] 存量清理前请先 --baseline 冻结，再用 --strict 拦截增量。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
