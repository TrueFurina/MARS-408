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
)


class Rule:
    """一条扫描规则：正则 + 期望值来源 + 必须命中的文件。

    `pattern` 必须把「数值」放进**第 1 个捕获组**，且要求数字紧挨单位锚（见模块 docstring）。
    `key` 指 `verify_metrics.measure()` 返回的指标键——真值从那里取，不另立口径。
    `files` 为本规则**必须命中**的目标文件（相对仓库根）；任一文件命中 0 处即 fail-closed。
    """

    def __init__(self, name: str, pattern: str, key: str, files: tuple[str, ...]) -> None:
        self.name = name
        self.regex = re.compile(pattern)
        self.key = key
        self.files = files


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
)


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

    print("[scan_metric_occurrences] SSOT 真值（来源 scripts/verify_metrics.py::measure）：")
    for key in ("frontend_views", "frontend_vue_total", "frontend_ts_total",
                "frontend_file_total", "backend_py", "api_modules", "api_operations"):
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

    for rule in RULES:
        expect = truth[rule.key][0]
        for rel in rule.files:
            text = texts[rel]
            matches = list(rule.regex.finditer(text))
            if not matches:
                # fail-closed：规则在该文件里命中 0 处 → 这句要么被改写、要么扫描器坏了。
                zero_hits.append(f"    - [{rule.name}] {rel}：命中 0 处（期望 ≥1）")
                continue
            for m in matches:
                total_hits += 1
                got = int(m.group(1))
                if got != expect:
                    mismatches.append(
                        f"    {rel}:{_line_of(text, m.start())}  "
                        f"[{rule.name}] 现值 {got} → 期望 {expect}"
                    )

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
