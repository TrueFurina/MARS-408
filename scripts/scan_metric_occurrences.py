#!/usr/bin/env python
"""scan_metric_occurrences.py — 活文档面「规模指标副本」防漂移（单位锚定）

为什么需要
--------------------------------------------------------------------------
`docs/METRICS_CURRENT.md` 的围栏表（`<!-- METRICS_TABLE_START -->…END`）是机检
SSOT，由 `scripts/verify_metrics.py` 守护——但**只有那一张表**被守护。同一批指标
在 README / README_EN / 前端统计块 / 提交清单里还有若干「手抄副本」，它们**不在
任何闸门之下**，于是悄悄漂移成互相矛盾的值（views 一度同时存在 45 / 46 / 47）。

这正是「闸绿 ≠ 这句绿」：SSOT 那张表全绿，不代表引用它的这一句是对的。

本脚本把"活文档面"里的规模指标副本一并纳入机检：**重算 SSOT 真值 → 扫描活文档面
中每个带单位锚定的指标出现 → 与真值逐处比对**。

口径与 SSOT 同源
--------------------------------------------------------------------------
真值**不另立口径**：直接从 `scripts/verify_metrics.py` 复用 `measure()`（与其
`--print` 完全同源）。`verify_metrics.measure()` 用 `git ls-files` 取跟踪文件，
保证 Windows / Linux / CI 三端结果一致。

只认「带单位锚定」的出现，绝不扫裸数字
--------------------------------------------------------------------------
匹配一律要求数字**紧挨单位**（如 `48 个 views` / `48 pages` / `361 个 Python 文件`）。
好处：`ShowcaseView.vue` 里的 `45% 评分权重`（赛题功能权重，**事实正确**）这类裸
数字天然不会被命中，从根上避免误伤合规数字。

fail-closed（"照不到" ≠ "干净"）
--------------------------------------------------------------------------
- 任一目标文件不存在 → exit 2；
- 任一「(规则 × 目标文件)」组合命中 0 处 → exit 2（说明该句被改写过、或扫描器坏了，
  静默放行比报错更危险）；
- 全对齐 → exit 0，并打印命中总数（让人看得出它真的扫到了东西）。

用法
--------------------------------------------------------------------------
    python scripts/scan_metric_occurrences.py

退出码：0=全对齐；1=有副本与 SSOT 不符；2=fail-closed（文件缺失 / 规则零命中 / 环境错误）。
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 复用 SSOT 口径（同一 module）。verify_metrics 只依赖标准库 + git + openapi.json。
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import verify_metrics  # noqa: E402
except Exception as exc:  # pragma: no cover - 环境级失败，显式 exit 2
    print(f"[scan_metric_occurrences] ❌ 无法导入 SSOT 口径模块 verify_metrics：{exc}")
    sys.exit(2)

# 「活文档面」——同一批指标在这些文件里各有手抄副本。
TARGET_FILES = (
    "README.md",
    "README_EN.md",
    "src/views/PlatformHomeView.vue",
    "submission/00_提交清单.md",
    # 2026-10-22 扩面：对外材料 + 两份真值记录。它们同样含现行值手抄副本，
    # 其中证据页是**对外材料**——漂移不会有人发现，故必须纳管。
    "deliverables/芒得很职-国创赛证据页.md",
    "docs/ci-backend-test-result.md",
    "docs/TEST_TRUTH.md",
)

# SSOT 散文（**不在** TARGET_FILES 内 —— 它是权威源而不是"副本"，不能被当副本校验）。
# 认证覆盖率分子 / CI 测试通过数的权威真值写在这里，本脚本只**解析**它，不重算。
SSOT_DOC = "docs/METRICS_CURRENT.md"


class Rule:
    """一条扫描规则：正则 + 期望值来源 + 必须命中的文件。

    `pattern` 必须把「数值」放进**第 1 个捕获组**，且要求数字紧挨单位锚（见模块 docstring）。
    `key` 指 `verify_metrics.measure()` 返回的指标键——真值从那里取，不另立口径。
    `files` 为本规则**必须命中**的目标文件（相对仓库根）；任一文件命中 0 处即 fail-closed。
    """

    def __init__(self, name: str, pattern: str, key: str, files: tuple[str, ...],
                 as_str: bool = False) -> None:
        self.name = name
        self.regex = re.compile(pattern)
        self.key = key
        self.files = files
        # True = 该指标不是整数（如认证覆盖率百分比 95.02），按**字符串**比对。
        # 显式开关而非让 int() 抛错或做浮点近似——避免"小数进 int 键"的类型混淆。
        self.as_str = as_str


# 单位锚定规则集。每条都能同时吃到中/英两种写法：
#   - views：`48%20views`（badge，空格被 URL 编码）/ `48 个 views` / `48 views`
#   - pages / 页面：`48 pages` / `48 个页面` / `48 页面`
#   - .vue：`87 个 .vue` / `87 个 \`.vue\``
#   - Python 文件：`361 个 Python 文件`
#   - 路由模块：`42 路由模块`（README）/ 表格行 `后端路由模块 | 42 个`（提交清单）
#   - 前端视图统计块：`<b>48</b><span>前端视图`
#   - API 端点：`约 245 个 API 端点` / `~245 API endpoints`
#   - 前端代码量格（README「代码量」行）：`88 .vue + 71 .ts` / `159 文件（`
RULES: tuple[Rule, ...] = (
    Rule(
        "views 计数",
        r"(\d+)(?:%20|\s+(?:个\s+)?)views\b",
        "frontend_views",
        ("README.md", "README_EN.md", "submission/00_提交清单.md"),
    ),
    Rule(
        "pages 计数",
        r"(\d+)\s+(?:个\s+)?pages\b",
        "frontend_views",
        ("README_EN.md",),
    ),
    Rule(
        "个页面 计数",
        r"(\d+)\s*(?:个\s*)?页面",
        "frontend_views",
        ("README.md",),
    ),
    Rule(
        ".vue 计数",
        r"(\d+)\s*个\s*`?\s*\.vue",
        "frontend_vue_total",
        ("README.md", "submission/00_提交清单.md"),
    ),
    Rule(
        ".ts 计数（README「代码量」格句式）",
        r"\.vue\s*\+\s*(\d+)\s*\.ts",
        "frontend_ts_total",
        ("README.md",),
    ),
    Rule(
        "前端文件总数（README「代码量」格句式）",
        r"(\d+)\s*文件（",
        "frontend_file_total",
        ("README.md",),
    ),
    Rule(
        "Python 文件计数",
        r"(\d+)\s*个\s*Python\s*文件",
        "backend_py",
        ("README.md",),
    ),
    Rule(
        "路由模块计数（数值前置）",
        r"(\d+)\s*路由模块",
        "api_modules",
        ("README.md",),
    ),
    Rule(
        "路由模块计数（提交清单表格行）",
        r"后端路由模块\s*\|\s*(\d+)",
        "api_modules",
        ("submission/00_提交清单.md",),
    ),
    Rule(
        "PlatformHomeView 前端视图统计块",
        r">(\d+)</b>\s*<span>前端视图",
        "frontend_views",
        ("src/views/PlatformHomeView.vue",),
    ),
    Rule(
        "API 端点数（中文）",
        r"约\s*(\d+)\s*个\s*API\s*端点",
        "api_operations",
        ("README.md",),
    ),
    Rule(
        "API endpoints（英文）",
        r"~(\d+)\s*API\s*endpoints",
        "api_operations",
        ("README_EN.md",),
    ),
    Rule(
        "API 路径数（中文）",
        r"(\d+)\s*(?:条\s*路由)?路径",
        "api_paths",
        ("README.md", "submission/00_提交清单.md"),
    ),
    Rule(
        "API 路径数（英文）",
        r"(\d+)\s*paths",
        "api_paths",
        ("README_EN.md",),
    ),
    Rule(
        "CI 测试通过数（中文）",
        r"(\d+)\s*项测试通过",
        "ci_test_passed",
        ("README.md",),
    ),
    Rule(
        "CI 测试通过数（英文）",
        r"(\d+)\s*tests passing",
        "ci_test_passed",
        ("README_EN.md",),
    ),
    Rule(
        "CI 测试通过数（提交清单表格行）",
        r"项：(\d+)\s*通过",
        "ci_test_passed",
        ("submission/00_提交清单.md",),
    ),
    # 认证覆盖率分子必须用「认证覆盖率」这个语义短语锚定，不能只写 `（(\d+)/(\d+)）`：
    # 实测宽松写法会额外命中 `测试覆盖率 …（22587/9670）`（本机 fresh 覆盖率，不同指标）
    # 与 `残留 … 94.69%（232/245）`（历史作废值的**记述**，不是当前值）——两者都会误判。
    Rule(
        "认证覆盖率分子（全角括号）",
        r"认证覆盖率[^\n]{0,60}?（(\d+)/(\d+)）",
        "auth_protected",
        ("submission/00_提交清单.md",),
    ),
    Rule(
        "认证覆盖率分子（提交清单表格行）",
        r"\|\s*(\d+)/(\d{3})\s*\|",
        "auth_protected",
        ("submission/00_提交清单.md",),
    ),
    # ==== 2026-10-22 扩面：对外材料（证据页）+ 两份真值记录 ==================
    # 每条都先用实测收敛过：宁可窄、宁可少声明文件，也不误命中历史值。
    Rule(
        "认证覆盖率分子（分数写法，容空格）",
        r"认证覆盖率[^\n]{0,80}?（(\d+)\s*/\s*(\d+)）",
        "auth_protected",
        ("deliverables/芒得很职-国创赛证据页.md", "docs/ci-backend-test-result.md"),
    ),
    # TEST_TRUTH 的覆盖率写成「（261 端点 / 248 受保护 / 13 公开）」——第 1 个数字是
    # **分母**不是分子，分数写法必误抓，故该文件改用 `protected=` 写法单独守。
    Rule(
        "认证覆盖率分子（protected= 写法）",
        r"protected=(\d+)",
        "auth_protected",
        ("docs/TEST_TRUTH.md",),
    ),
    Rule(
        "认证覆盖率百分比",
        r"认证覆盖率[^\n]{0,80}?\*\*(\d+\.\d+)%",
        "auth_coverage_pct",
        ("deliverables/芒得很职-国创赛证据页.md", "docs/ci-backend-test-result.md"),
        as_str=True,
    ),
    Rule(
        "API 操作数（表格 bold 写法）",
        r"\*\*(\d+)\*\*（method 级",
        "api_operations",
        ("deliverables/芒得很职-国创赛证据页.md",),
    ),
    Rule(
        "API 操作数（ops 写法）",
        r"(\d+)\s*ops",
        "api_operations",
        ("docs/ci-backend-test-result.md",),
    ),
    # ci-backend-test-result.md 是**按 run 倒序的日志**：同一句式在历史段落里
    # 还有 1524（:41）/ 1389（:52）两份，裸 `(\d+) passed, ... skipped` 会全抓。
    # 该文件自带「**当前权威值**」标记（全文件唯一）且明写「只有本节第一段是当前权威」，
    # 用它做锚才能只咬住当前那一行。（不是 max(数字)：数字不单调，且是显式禁止的假设。）
    Rule(
        "CI 测试通过数（英文句式，锚『当前权威值』）",
        r"当前权威值(?:.|\n){0,240}?\*\*(\d+)\s*passed,\s*\d+\s*skipped",
        "ci_test_passed",
        ("docs/ci-backend-test-result.md",),
    ),
    # TEST_TRUTH.md:19 是「本机 Windows 实测」的 1325 —— 同一句式、不同平台剖面，
    # 不是 CI 真值。故用口径短语锚定，只认「权威对外口径 / CI 默认档 / CI/Linux 默认档」。
    Rule(
        "CI 测试通过数（中文句式，锚口径短语）",
        r"(?:权威对外口径|CI(?:/Linux)? 默认档)[^\n]{0,80}?"
        r"(\d+)\s*通过\s*/\s*\d+\s*跳过\s*/\s*1\s*xfailed",
        "ci_test_passed",
        ("deliverables/芒得很职-国创赛证据页.md", "docs/TEST_TRUTH.md"),
    ),
    # 证据页 :35 的「去重路径 243」是 api_paths 在**对外材料**里最后一个未守护副本。
    # 实测：该文件里 `去重路径` 只出现 1 次、值为 243；而更宽的 `(\d+)\s*路径` 在该文件
    # 命中 0 处（它写作「去重路径 243」而非「243 路径」），故必须按本文件句式定制。
    Rule(
        "API 路径数（证据页「去重路径」句式）",
        r"去重路径\s*(\d+)",
        "api_paths",
        ("deliverables/芒得很职-国创赛证据页.md",),
    ),
)


class SSOTParseError(Exception):
    """SSOT 散文解析失败。

    fail-closed：解析不到权威真值 = 无法守护，必须 exit 2，
    绝不能当"没漂移"放行（"照不到" ≠ "干净"）。
    """


def _read_ssot_doc() -> str:
    """读 SSOT 散文全文；文件缺失即 fail-closed。"""
    p = ROOT / SSOT_DOC
    if not p.is_file():
        raise SSOTParseError(f"SSOT 文档不存在：{SSOT_DOC}")
    return p.read_text(encoding="utf-8", errors="replace")


def _parse_auth_protected(text: str) -> tuple[int, str]:
    """解析认证覆盖率**分子**（protected 数），SSOT 派生、**非重算**。

    code 级重算由 `py-server/scripts/verify_auth_coverage.py` 负责（已挂 CI），
    本脚本只取它写进 SSOT 散文的权威值，再拿去校验活文档里的手抄副本。
    """
    hits = re.findall(r"protected=(\d+)", text)
    if not hits:
        raise SSOTParseError(
            f"{SSOT_DOC} 未找到 `protected=<n>`（认证覆盖率段缺失或被改写）")
    if len(set(hits)) > 1:
        raise SSOTParseError(
            f"{SSOT_DOC} 中 `protected=` 出现多个不同取值 {sorted(set(hits))}，口径不唯一")
    return int(hits[0]), f"SSOT 派生（非重算）：{SSOT_DOC} 认证覆盖率段 protected="


def _parse_auth_coverage_pct(text: str) -> tuple[str, str]:
    """解析认证覆盖率**百分比**（SSOT 派生、**非重算**）。

    百分比是 248/261 的显示派生值，单独成键是为了让「只改百分比、不改分子分母」
    这种文档内部自相矛盾的编辑也能被拦下（对外材料尤其需要）。
    """
    hits = re.findall(r"coverage=\*\*(\d+\.\d+)%\*\*", text)
    if not hits:
        raise SSOTParseError(
            f"{SSOT_DOC} 未找到 `coverage=**<n.nn>%**`（认证覆盖率段缺失或被改写）")
    if len(set(hits)) > 1:
        raise SSOTParseError(
            f"{SSOT_DOC} 中 `coverage=` 出现多个不同取值 {sorted(set(hits))}，口径不唯一")
    return hits[0], f"SSOT 派生（非重算）：{SSOT_DOC} 认证覆盖率段 coverage="


def _parse_ci_test_passed(text: str) -> tuple[int, str]:
    """解析 CI 测试**通过数**，SSOT 派生、**非重算**。

    code 级重算要真跑一遍 pytest，由 CI 的 Backend Test job 守护；本脚本只取
    SSOT 散文里标注的最新时点值。

    ⚠️ 必须按**日期**取最新的一条，不能用 `max(所有数字)`：
      · 数字本身不单调（历史上既有增长也有因剖面错位回落）；
      · 该段还混着「1776 运行项」「1785 collected」这类**同是数字却不是通过数**
        的干扰项。故正则必须同时锚定日期 + `N 通过 / M 跳过` 句式。
    """
    pat = re.compile(
        r"(\d{4}-\d{2}-\d{2})[^0-9]{0,120}?(\d+)\s*通过\s*/\s*(\d+)\s*跳过")
    hits = pat.findall(text)
    if not hits:
        raise SSOTParseError(
            f"{SSOT_DOC} 未找到「日期 + N 通过 / M 跳过」句式的测试真值")
    # ISO 日期字符串比较 == 时间序比较；取时点最新的一条。
    date, passed, _skipped = max(hits, key=lambda h: h[0])
    return int(passed), f"SSOT 派生（非重算）：{SSOT_DOC} 测试数段 最新时点 {date}"


def _line_of(text: str, pos: int) -> int:
    """把字符偏移换算成 1 起的行号。"""
    return text.count("\n", 0, pos) + 1


def main() -> int:
    # 1) 取 SSOT 真值（与 verify_metrics 同源）。
    try:
        truth = verify_metrics.measure()
    except Exception as exc:  # pragma: no cover - 环境级失败
        print(f"[scan_metric_occurrences] ❌ 无法计算 SSOT 真值（verify_metrics.measure）：{exc}")
        return 2

    # `frontend_file_total` 不是 verify_metrics 的独立指标，而是 SSOT 两个键的派生值
    # （.vue 总数 + .ts 总数，二者均按「含顶层 App.vue / main.ts」口径）——仍与 SSOT
    # 同源，只是不必为文档里的一行去改动 verify_metrics 的口径与 METRICS 表。
    truth["frontend_file_total"] = (
        truth["frontend_vue_total"][0] + truth["frontend_ts_total"][0],
        "SSOT 派生：.vue 总数 + .ts 总数（含顶层）",
    )

    # `auth_protected` / `ci_test_passed` 同样与 SSOT 同源，但它们是**解析 SSOT 散文**
    # 得到的权威值、**不是本脚本重算**（code 级重算分别由 verify_auth_coverage 与
    # CI 的 Backend Test job 守护）。解析不到即 fail-closed exit 2。
    try:
        ssot_text = _read_ssot_doc()
        truth["auth_protected"] = _parse_auth_protected(ssot_text)
        truth["auth_coverage_pct"] = _parse_auth_coverage_pct(ssot_text)
        truth["ci_test_passed"] = _parse_ci_test_passed(ssot_text)
    except SSOTParseError as exc:
        print(f"[scan_metric_occurrences] ❌ fail-closed：无法从 SSOT 取得权威真值：{exc}")
        return 2

    print("[scan_metric_occurrences] SSOT 真值（来源 scripts/verify_metrics.py::measure"
          f" / {SSOT_DOC}）：")
    for key in ("frontend_views", "frontend_vue_total", "frontend_ts_total",
                "frontend_file_total", "backend_py", "api_modules",
                "api_paths", "api_operations", "ci_test_passed",
                "auth_protected", "auth_coverage_pct"):
        print(f"    - {key} = {truth[key][0]}")

    # 2) 读目标文件（缺失即 fail-closed）。
    texts: dict[str, str] = {}
    missing: list[str] = []
    for rel in TARGET_FILES:
        p = ROOT / rel
        if not p.is_file():
            missing.append(rel)
            continue
        texts[rel] = p.read_text(encoding="utf-8", errors="replace")
    if missing:
        print("[scan_metric_occurrences] ❌ fail-closed：以下目标文件不存在，无法守护：")
        for rel in missing:
            print(f"    - {rel}")
        return 2

    # 3) 逐规则 × 逐文件扫描。
    mismatches: list[str] = []
    zero_hits: list[str] = []
    total_hits = 0
    per_rule: list[str] = []

    for rule in RULES:
        expect = truth[rule.key][0]
        rule_hits = 0
        for rel in rule.files:
            text = texts[rel]
            matches = list(rule.regex.finditer(text))
            if not matches:
                # fail-closed：规则在该文件里命中 0 处 → 这句要么被改写、要么扫描器坏了。
                zero_hits.append(f"    - [{rule.name}] {rel}：命中 0 处（期望 ≥1）")
                continue
            rule_hits += len(matches)
            for m in matches:
                total_hits += 1
                # as_str 规则（覆盖率百分比）按字符串比对，其余按 int 比对。
                got: object = m.group(1) if rule.as_str else int(m.group(1))
                if got != expect:
                    # 定位到**数值所在行**（不是锚点所在行）：带前置锚的规则
                    # 匹配起点在锚上，报锚的行号会让人找不到要改的数字。
                    mismatches.append(
                        f"    {rel}:{_line_of(text, m.start(1))}  "
                        f"[{rule.name}] 现值 {got} → 期望 {expect}"
                    )
        # 逐条列出命中数：只报一个总数的话，无法分辨"每条规则都真的扫到了东西"
        # 与"某条规则其实 0 命中、被总数掩盖"（后者正是零覆盖假绿）。
        per_rule.append(f"    {rule.name}: {rule_hits} 处")

    if zero_hits:
        print("[scan_metric_occurrences] ❌ fail-closed：以下规则在目标文件里命中 0 处"
              "（「照不到」不得当作「干净」）：")
        print("\n".join(zero_hits))
        return 2

    if mismatches:
        print("[scan_metric_occurrences] ❌ 活文档面规模指标副本与 SSOT 不符：")
        print("\n".join(mismatches))
        print("  修正文档，或先跑 `python scripts/verify_metrics.py --print` 确认真值。")
        return 1

    print(f"[scan_metric_occurrences] ✅ 活文档面规模指标副本全部对齐 SSOT"
          f"（命中 {total_hits} 处 / {len(RULES)} 条规则 / {len(TARGET_FILES)} 个文件）")
    print("逐条命中：")
    print("\n".join(per_rule))
    return 0


if __name__ == "__main__":
    sys.exit(main())
