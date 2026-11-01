#!/usr/bin/env python3
"""前端 HTML 注入门禁（防 XSS）

覆盖两类注入面，缺一不可：
    A. 模板里的 `v-html` 绑定
    B. 脚本里的 `innerHTML` / `outerHTML` / `insertAdjacentHTML` / `document.write`

为什么必须同时覆盖 B：
    本门禁原先只扫 `.vue` 的 `v-html`，而 `src/**/*.ts` 与 `.vue` 的 `<script>`
    里可以直接 `el.innerHTML = ...`，**完全绕过扫描**。实测 `ChatView.vue` 有两处
    这样的赋值（当前是硬编码 SVG 字面量，安全，但门禁对此一无所知）——
    「今天安全」与「门禁能发现明天不安全」是两件事，后者才是门禁的意义。

背景：
    项目纪律要求「所有 v-html 必须净化」（竞赛评审要求）。历史上
    WrongQuestionsView 曾以 `v-html="getQuestionText(q)"` 直插后端题目文本
    （LLM 可能生成，不可信），存在 XSS 风险。本门禁把该纪律固化为可复跑检查，
    使未来任何新增的未净化绑定都被自动拦下，而非依赖人工逐个发现。

判定规则（精确、零误报设计）：

  A. v-html 绑定表达式
      1. 以净化函数开头（renderMarkdownSafe / sanitizeSvg / safeIcon）
         → 安全（整体经净化，内层数据访问被净化函数包裹）。
      2. 否则若表达式**包含函数调用**（`ident(...)`）
         → 阻断：函数可能返回后端/LLM 数据，未经净化即注入 HTML。
      3. 其余（纯属性访问 icons.xxx / 索引 icons[key] / 三元 / 字面量 / 本地常量）
         → 安全（自建硬编码内容，非外部数据）。
    该规则在现状代码上零误报：本地图标（icons.*、p.icon、step.icon、it.icon 等）
    均为属性访问，不会被判阻断；唯一命中的是已修复的 getQuestionText 调用。

  B. 命令式 HTML 赋值
      1. 右值以净化函数开头 → 安全。
      2. 右值是不含插值的单个字符串字面量（'...' / "..." / `...` 且无 ${}）
         → 安全（编译期常量，不可能携带外部数据）。
      3. 其余（变量、函数调用、字符串拼接、含 ${} 的模板串）→ 阻断。
    说明：含 `${}` 的模板串即便当前只插本地常量也会被阻断——静态分析无法证明
    插值来源，宁可要求改成 sanitizeSvg(...) 包裹，也不要留一个「看起来安全」的口子。

退出码：
    0 = 通过
    1 = 发现未净化的注入点（阻断）

用法：
    python scripts/xss_scan.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from _gate_selftest import report_selftest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

# 视为"已净化 / 本地可信"的表达式前缀：
#   - 净化函数调用：renderMarkdownSafe( / sanitizeSvg( / safeIcon(
#   - 自建图标集访问：icons.xxx / icons[...]（结果为本地硬编码 SVG，非外部数据；
#     方括号内的函数只用于"算键"，不改变取值域，故安全）
SAFE_PREFIX_RE = re.compile(r"^(?:renderMarkdownSafe|sanitizeSvg|safeIcon)\s*\(|^icons\s*[.\[]")

V_HTML_RE = re.compile(r"""v-html\s*=\s*(["'])(.*?)\1""")
CALL_RE = re.compile(r"([A-Za-z_$][\w$]*)\s*\(")

# 命令式注入面。右值取到行尾（或分号），必要时拼接后续 2 行（应对换行书写）。
IMPERATIVE_RE = re.compile(
    r"\.(?:innerHTML|outerHTML)\s*=\s*|\.insertAdjacentHTML\s*\(\s*(['\"])(?:beforebegin|afterbegin|beforeend|afterend)\1\s*,\s*|document\.write(?:ln)?\s*\("
)

# 单个字符串字面量（无拼接）：'...' / "..." / `...` 且模板串内无 ${}
_LITERAL_RE = re.compile(r"^(?:'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`(?:[^`\\$]|\\.)*`)$", re.S)

# 测试与类型声明不参与扫描：它们不进入生产包
_EXCLUDE_DIR_NAMES = {"__tests__", "node_modules", "dist"}
_EXCLUDE_SUFFIXES = (".spec.ts", ".test.ts", ".spec.vue", ".test.vue", ".d.ts")


def _starts_with_safe(expr: str) -> bool:
    return bool(SAFE_PREFIX_RE.match(expr.strip()))


def _is_pure_literal(expr: str) -> bool:
    return bool(_LITERAL_RE.match(expr.strip()))


def _iter_source_files():
    for pattern in ("*.vue", "*.ts"):
        for f in sorted(SRC.rglob(pattern)):
            if any(part in _EXCLUDE_DIR_NAMES for part in f.parts):
                continue
            if f.name.endswith(_EXCLUDE_SUFFIXES):
                continue
            yield f


# 行尾出现这些记号 ⇒ 表达式跨行，需要续下一行再判
_CONT_ENDINGS = ("+", "-", "*", "/", "&&", "||", "?", ":", ",", "(", "[", "{", "=")


def _unterminated(code: str) -> bool:
    """引号数量为奇数 ⇒ 字符串未闭合（该行只是表达式的一部分）。"""
    for q in ("'", '"', "`"):
        if len(re.findall(rf"(?<!\\){q}", code)) % 2 == 1:
            return True
    return False


def _rhs_of(text: str, start: int) -> str:
    """取赋值语句右值（按行聚合，遇到跨行才续行）。

    两次实测修正：
      1. 早期版本无条件把后续 3 行拼进来 ⇒ `el.innerHTML = '<svg .../>'` 后面
         紧跟的下一行语句被当成右值，字面量判定必然失败（把 ChatView 两处硬编码
         SVG 误报为阻断）。
      2. 只取到闭合引号为止 ⇒ `'<b>' + userInput` 会被截成 `'<b>'` 判为「纯字面量」，
         **漏报字符串拼接型注入**。故必须取整行表达式后再判。
    正确做法：从赋值点取到「行尾且表达式完整」为止（行尾是运算符或引号未闭合则续行）。
    """
    raw_lines = text[start : start + 2000].split("\n")
    acc = ""
    for idx, raw in enumerate(raw_lines[:4]):
        acc = f"{acc} {raw.strip()}".strip() if idx else raw.strip()
        code = re.split(r"\s//", acc, maxsplit=1)[0].rstrip(";").strip()
        if not code:
            return ""
        if _unterminated(code) or code.endswith(_CONT_ENDINGS):
            continue
        return code
    return acc.strip()


def scan_v_html(text: str, rel: str, hits: list[tuple[str, int, str, str]]) -> None:
    for m in V_HTML_RE.finditer(text):
        expr = m.group(2)
        if _starts_with_safe(expr):
            continue
        if CALL_RE.search(expr):
            line = text[: m.start()].count("\n") + 1
            hits.append((rel, line, "v-html", expr.strip()[:120]))


def scan_imperative(text: str, rel: str, hits: list[tuple[str, int, str, str]]) -> None:
    for m in IMPERATIVE_RE.finditer(text):
        expr = _rhs_of(text, m.end())
        if not expr:
            continue
        if _starts_with_safe(expr) or _is_pure_literal(expr):
            continue
        line = text[: m.start()].count("\n") + 1
        sink = m.group(0).strip().rstrip("=(").strip()
        hits.append((rel, line, sink, expr[:120]))


def scan() -> int:
    hits: list[tuple[str, int, str, str]] = []
    scanned = 0
    for f in _iter_source_files():
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        scanned += 1
        rel = f.relative_to(ROOT).as_posix()
        scan_v_html(text, rel, hits)
        scan_imperative(text, rel, hits)

    print("=" * 72)
    print("HTML 注入门禁（防 XSS：v-html + innerHTML / outerHTML / insertAdjacentHTML / document.write）")
    print("=" * 72)
    print(f"扫描文件: {scanned} 个（src/**/*.vue, src/**/*.ts；排除测试与类型声明）")

    if not hits:
        print("[PASS] 未发现未净化的 HTML 注入点。")
        return 0

    print(f"[FAIL] 发现 {len(hits)} 处未净化的 HTML 注入点：")
    print()
    for rel, line, sink, expr in hits:
        print(f"  {rel}:{line}")
        print(f"      {sink} ← {expr}")
    print()
    print("修复：用 renderMarkdownSafe(...) / sanitizeSvg(...) / safeIcon(...) 包裹；")
    print("若内容确为本地硬编码，请改为纯字符串字面量或属性访问形式（如 icons.xxx）。")
    return 1


# ============================================================================
# 自检（--selftest）
# ============================================================================
# 为什么要有：门禁最容易的失效形态不是"漏报"，而是**自己被改坏后仍然输出 PASS**
# —— 一条永远绿的闸门比没有闸门更危险（本项目 gates.yml 的文件头已记录过同类事故）。
# 自检用内存样本断言「该拦的拦住、该放的放行」，不依赖仓库当前状态。
_SELFTEST_SAMPLE = """
const el = document.createElement('div')
el.innerHTML = userInput
el.innerHTML = '<b>' + userInput + '</b>'
el.innerHTML = `<b>${userInput}</b>`
el.outerHTML = renderUnsafe(x)
el.insertAdjacentHTML('beforeend', payload)
document.write(evil)
el.innerHTML = '<b>safe literal</b>'
el.innerHTML = sanitizeSvg(unsafe)
"""

# 样本里应被拦下的行号（1-based，对应上面字符串；空行占了第 1 行）
_SELFTEST_EXPECTED_LINES = [3, 4, 5, 6, 7, 8]


def selftest() -> int:
    hits: list[tuple[str, int, str, str]] = []
    scan_v_html(_SELFTEST_SAMPLE, "selftest", hits)
    scan_imperative(_SELFTEST_SAMPLE, "selftest", hits)
    got = sorted(line for _rel, line, _sink, _expr in hits)

    return report_selftest(
        title="HTML 注入门禁 · 自检（验证门禁本身没被改坏）",
        expected=_SELFTEST_EXPECTED_LINES,
        got=got,
        ok_msg="6 类注入点全部命中，2 类安全写法正确放行。",
        fail_msg="自检不符：门禁已失效（可能漏报，也可能误报），不要相信它的 PASS。",
    )


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else scan())
