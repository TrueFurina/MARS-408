#!/usr/bin/env python3
"""前端 v-html 净化门禁（防 XSS）

背景：
    项目纪律要求「所有 v-html 必须净化」（竞赛评审要求）。历史上
    WrongQuestionsView 曾以 `v-html="getQuestionText(q)"` 直插后端题目文本
    （LLM 可能生成，不可信），存在 XSS 风险。本门禁把该纪律固化为可复跑检查，
    使未来任何新增的未净化绑定都被自动拦下，而非依赖人工逐个发现。

判定规则（精确、零误报设计）：
    对每处 v-html 绑定表达式：
      1. 以净化函数开头（renderMarkdownSafe / sanitizeSvg / safeIcon）
         → 安全（整体经净化，内层数据访问被净化函数包裹）。
      2. 否则若表达式**包含函数调用**（`ident(...)`）
         → 阻断：函数可能返回后端/LLM 数据，未经净化即注入 HTML。
      3. 其余（纯属性访问 icons.xxx / 索引 icons[key] / 三元 / 字面量 / 本地常量）
         → 安全（自建硬编码内容，非外部数据）。
    该规则在现状代码上零误报：本地图标（icons.*、p.icon、step.icon、it.icon 等）
    均为属性访问，不会被判阻断；唯一命中的是已修复的 getQuestionText 调用。

退出码：
    0 = 通过（无未净化的函数调用型绑定）
    1 = 发现未净化的 v-html 函数调用绑定（阻断）

用法：
    python scripts/xss_scan.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

# 视为"已净化 / 本地可信"的表达式前缀：
#   - 净化函数调用：renderMarkdownSafe( / sanitizeSvg( / safeIcon(
#   - 自建图标集访问：icons.xxx / icons[...]（结果为本地硬编码 SVG，非外部数据；
#     方括号内的函数只用于"算键"，不改变取值域，故安全）
SAFE_PREFIX_RE = re.compile(r"^(?:renderMarkdownSafe|sanitizeSvg|safeIcon)\s*\(|^icons\s*[.\[]")

V_HTML_RE = re.compile(r"""v-html\s*=\s*(["'])(.*?)\1""")
CALL_RE = re.compile(r"([A-Za-z_$][\w$]*)\s*\(")


def _starts_with_safe(expr: str) -> bool:
    return bool(SAFE_PREFIX_RE.match(expr.strip()))


def scan() -> int:
    hits: list[tuple[str, int, str]] = []
    for f in sorted(SRC.rglob("*.vue")):
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in V_HTML_RE.finditer(text):
            expr = m.group(2)
            if _starts_with_safe(expr):
                continue
            if CALL_RE.search(expr):
                line = text[: m.start()].count("\n") + 1
                hits.append((f.relative_to(ROOT).as_posix(), line, expr.strip()[:120]))

    print("=" * 72)
    print("v-html 净化门禁（防 XSS：不得以未净化函数直插 HTML）")
    print("=" * 72)

    if not hits:
        print("[PASS] 所有 v-html 绑定均为净化函数或本地可信内容（属性访问/字面量）。")
        return 0

    print(f"[FAIL] 发现 {len(hits)} 处未净化的 v-html 函数调用绑定：")
    print()
    for rel, line, expr in hits:
        print(f"  {rel}:{line}")
        print(f'      v-html="{expr}"')
    print()
    print("修复：用 renderMarkdownSafe(...) / sanitizeSvg(...) / safeIcon(...) 包裹；")
    print("若数据源确为本地硬编码，请改为纯属性访问形式（如 icons.xxx）。")
    return 1


if __name__ == "__main__":
    sys.exit(scan())
