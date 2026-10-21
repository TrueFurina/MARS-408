#!/usr/bin/env python3
"""双落地页数字族一致性机检（site/ ↔ website/ ↔ SSOT）。

为什么存在
---------------------------------------------------------------------------
Pages 部署的是 ``site/``（``.github/workflows/deploy-pages.yml``：site/ → 根路径），
而 ``website/`` 是同源手工维护副本。两页各自手改，没有机检时必然漂移：

- 2026-10-21 实测：``site/`` 停在 2026-10-17 族（1524 测试 / 254 端点），
  而 ``website/`` 已对齐 1693 族 —— 线上官网展示旧数字数日无人察觉。
- 同轮还发现两页各自的 hero 区与正文卡片数字互相矛盾（45 vs 49 视图）。

本闸门断言三件事
---------------------------------------------------------------------------
1. 两页声明的数字族**逐项相等**（测试通过数 / API 操作数 / 前端视图数）；
2. API 操作数与前端视图数与 ``scripts/verify_metrics.py::measure()`` 实测一致；
3. 测试通过数与 ``docs/TEST_TRUTH.md`` 权威口径一致（SSOT 明文裁定）。

只依赖标准库；在 gates.yml（纯 python 3.11）上运行。

用法::

    python scripts/check_landing_sync.py            # 检查
    python scripts/check_landing_sync.py --quiet    # 只在失败时输出
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGES = {
    "site/index.html": ROOT / "site" / "index.html",
    "website/index.html": ROOT / "website" / "index.html",
}

# 数字族 → 提取规则（对「剥标签后的纯文本」应用）
# 每条规则返回捕获组 1 为整数；一页内同一指标允许命中多次，但取值必须唯一。
FACT_PATTERNS: dict[str, list[str]] = {
    "tests_passed": [
        r"(\d+)\s*测试通过",          # hero: "1693 测试通过（2026-10-20 CI 口径）"
        r"(\d+)\s*条通过用例",        # 证据段: "96 条样本、1693 条通过用例"
        r"通过用例\s*(\d+)\s*条",     # 证据卡: "通过用例 1693 条"
    ],
    "api_operations": [
        r"(\d+)\s*(?:个\s*)?API 端点",  # "约 261 个 API 端点" / "261 API 端点（约）"
        r"(\d+)\s*operations",          # "261 operations / 243 paths"
    ],
    "frontend_views": [
        r"(\d+)\s*个视图",              # "约 49 个视图"
        r"(\d+)\s*前端教学视图",        # hero stat: "49 前端教学视图"
    ],
}


def _plain_text(path: pathlib.Path) -> str:
    html = path.read_text(encoding="utf-8")
    html = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", html)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html)


def _extract(path: pathlib.Path, label: str, quiet: bool) -> dict[str, int]:
    text = _plain_text(path)
    facts: dict[str, int] = {}
    for fact, patterns in FACT_PATTERNS.items():
        values: set[int] = set()
        for pat in patterns:
            values.update(int(m) for m in re.findall(pat, text))
        if not values:
            raise AssertionError(f"{label}: 未找到「{fact}」的数字（提取规则需随版面更新）")
        if len(values) > 1:
            raise AssertionError(
                f"{label}: 「{fact}」出现多个互相矛盾的取值 {sorted(values)} —— "
                "页面内部已漂移，先统一再提交"
            )
        facts[fact] = values.pop()
    if not quiet:
        print(f"  {label}: " + ", ".join(f"{k}={v}" for k, v in facts.items()))
    return facts


def _ssot() -> dict[str, int]:
    """工程指标取 verify_metrics.measure()；测试数取 TEST_TRUTH「权威对外口径」句。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    from verify_metrics import measure  # noqa: PLC0415  (同目录脚本，动态导入)

    measured = measure()
    truth = (ROOT / "docs" / "TEST_TRUTH.md").read_text(encoding="utf-8")
    # 只认 §1「权威对外口径 = CI 全量回归 …」这一句；TEST_TRUTH 里还有本机 Windows
    # 剖面（1325 通过）等历史行，不能一网打尽，否则会把旧剖面当成权威。
    m = re.search(r"权威对外口径\s*=\s*CI 全量回归\s*`?(\d+)\s*通过", truth)
    if not m:
        raise AssertionError("TEST_TRUTH.md 未找到「权威对外口径 = CI 全量回归 …」句，解析规则需随文档更新")
    return {
        "tests_passed": int(m.group(1)),
        "api_operations": measured["api_operations"][0],
        "frontend_views": measured["frontend_views"][0],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="双落地页数字族一致性机检")
    ap.add_argument("--quiet", action="store_true", help="只在失败时输出")
    args = ap.parse_args()

    if not args.quiet:
        print("=== 双落地页数字族一致性机检 ===")

    try:
        page_facts = {label: _extract(path, label, args.quiet) for label, path in PAGES.items()}
        truth = _ssot()
    except AssertionError as exc:
        print(f"❌ {exc}")
        return 1

    errors: list[str] = []

    # 判据 1：两页互相一致
    names = list(page_facts)
    for fact in FACT_PATTERNS:
        values = {page_facts[n][fact] for n in names}
        if len(values) > 1:
            detail = " vs ".join(f"{n}={page_facts[n][fact]}" for n in names)
            errors.append(f"两页「{fact}」不一致：{detail}")

    # 判据 2/3：与 SSOT 一致（只对能机器实测的两项强校验；测试数对 TEST_TRUTH）
    for fact, expected in truth.items():
        for name in names:
            got = page_facts[name][fact]
            if got != expected:
                errors.append(f"{name}「{fact}」={got}，与 SSOT={expected} 不一致")

    if errors:
        print("❌ 落地页数字族未对齐：")
        for e in errors:
            print(f"   - {e}")
        print("   修复：同步数字或跑生成器重刷；改完 `git add` 两页一起提交。")
        return 1

    if not args.quiet:
        print(f"✅ 两页一致且对齐 SSOT：" + ", ".join(f"{k}={v}" for k, v in truth.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
