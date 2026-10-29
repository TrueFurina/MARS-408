#!/usr/bin/env python3
"""`any` 棘轮门禁（只许降，不许升）。

背景
----
`src/` 里曾有 366 处 `any` / `as any`，其中 67 处是 `catch (e: any)`。
catch 那一批已在 2026-10-29 全部收敛为 `unknown`（strict 下 `catch (e)` 的默认类型），
暴露并修掉了 47 处「抛出物不是 Error 时 e.message 静默得 undefined」的隐患。

但**修完不等于不会退回去**。本项目已经吃过这个亏：品牌旧名、证伪口径都曾
「删掉又回流」。所以把当前水位钉成基线，只允许往下走。

为什么不做成「清零」
--------------------
剩下约 299 处主要是 `api.get<any>(...)` 这类响应体未定型的位置。它们不能机械替换：
换类型要逐个核对后端响应结构，改错就是运行时崩。用「必须清零」当门禁，
只会逼出 `as unknown as T` 这种绕过写法 —— 比 `any` 更糟，因为连搜索都搜不到。

所以判据是两条：
  1. `catch (e: any)` 必须为 **0**（已达成，零容忍）；
  2. `any` 总量不得高于基线（棘轮，只降不升）。

退出码
------
    0 = 通过
    1 = 违规（catch any 出现，或 any 总量高于基线）
    2 = fail-closed（扫描面为 0 个文件，无法判定）

用法
----
    python scripts/any_ratchet.py                # 校验
    python scripts/any_ratchet.py --update       # 收紧基线到当前实测值
    python scripts/any_ratchet.py --show         # 打印分布 Top 文件
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
BASELINE = ROOT / "scripts" / "any_ratchet.baseline.json"

# `: any` / `<any>` / `as any`。刻意不匹配注释里的示例：先剥掉注释行再统计，
# 否则本脚本自己的文档、以及 errorMessage.ts 里的反面示例都会被算进去。
ANY_RE = re.compile(r":\s*any\b|<any>|\bas\s+any\b")
CATCH_ANY_RE = re.compile(r"catch\s*\(\s*\w+\s*:\s*any\s*\)")
LINE_COMMENT_RE = re.compile(r"^\s*(?://|\*|/\*)")


def _iter_files():
    for pattern in ("*.ts", "*.vue"):
        for f in sorted(SRC.rglob(pattern)):
            if "__tests__" in f.parts:
                continue  # 测试不参与：里面大量 as any 是刻意的桩
            yield f


def scan() -> tuple[int, list[tuple[str, int, str]], int, list[tuple[int, str]]]:
    """一次遍历同时给出：总量、catch 违规点、扫描文件数、按文件的分布。

    刻意只遍历一遍 —— 早期版本让 `--show` 自己又写了一个计数循环，两处逻辑
    必然漂移（一处改了另一处忘改，就会出现"总量和分布对不上"），而且当场被
    pre-push 的克隆检测判为重复块。
    """
    total = 0
    catch_hits: list[tuple[str, int, str]] = []
    files = 0
    per_file: list[tuple[int, str]] = []
    for f in _iter_files():
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        files += 1
        rel = f.relative_to(ROOT).as_posix()
        file_count = 0
        for i, line in enumerate(text.splitlines(), 1):
            if LINE_COMMENT_RE.match(line):
                continue
            # 去掉行尾注释，避免把注释里的示例算进总量
            code = line.split("//")[0] if "//" in line and "://" not in line else line
            n = len(ANY_RE.findall(code))
            total += n
            file_count += n
            if CATCH_ANY_RE.search(code):
                catch_hits.append((rel, i, line.strip()[:100]))
        if file_count:
            per_file.append((file_count, rel))
    per_file.sort(reverse=True)
    return total, catch_hits, files, per_file


def main() -> int:
    ap = argparse.ArgumentParser(description="`any` 棘轮门禁（只许降不许升）")
    ap.add_argument("--update", action="store_true", help="把基线收紧到当前实测值")
    ap.add_argument("--show", action="store_true", help="打印 any 分布 Top 文件")
    args = ap.parse_args()

    total, catch_hits, files, per_file = scan()

    if files == 0:
        print("[FAIL-CLOSED] 扫描面为 0 个 .ts/.vue 文件：无法判定（exit 2，不放行）")
        return 2

    if args.show:
        print(f"any 总量 {total}，分布 Top 15：")
        for n, rel in per_file[:15]:
            print(f"  {n:4d}  {rel}")

    base = {"total": 0, "catch_any": 0}
    if BASELINE.exists():
        try:
            base = json.loads(BASELINE.read_text(encoding="utf-8"))
        except Exception:
            print(f"[WARN] 基线文件无法解析，按 0 处理：{BASELINE}")

    if args.update:
        new = {"total": total, "catch_any": len(catch_hits)}
        if new["total"] > base.get("total", 0) and base.get("total", 0) > 0:
            print(
                f"[REFUSE] 拒绝把基线从 {base['total']} 抬高到 {new['total']}："
                "棘轮只许降。若确有正当理由，请手工改基线文件并在提交信息里说明。"
            )
            return 1
        BASELINE.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"已更新基线：total={new['total']} catch_any={new['catch_any']}")
        return 0

    print("=" * 72)
    print("`any` 棘轮门禁（catch any 零容忍 + 总量只降不升）")
    print("=" * 72)
    print(f"扫描文件: {files} 个（src/**/*.ts, src/**/*.vue；排除 __tests__ 与注释行）")
    print(f"catch (x: any): {len(catch_hits)} 处（要求 0）")
    print(f"any 总量      : {total} 处（基线 {base.get('total', 0)}）")

    rc = 0
    if catch_hits:
        rc = 1
        print("\n[FAIL] catch 变量不允许标 any（strict 下 catch (e) 已是 unknown）：")
        for rel, line, text in catch_hits:
            print(f"  {rel}:{line}  {text}")
        print("  修法：去掉 `: any`，用 errMessage(e, '兜底') 取文案、isAbortError(e) 判中断。")

    if total > base.get("total", 0):
        rc = 1
        print(
            f"\n[FAIL] any 总量上升：{base.get('total', 0)} → {total}。"
            "棘轮只许降；确需新增请先降别处，或手工改基线并在提交信息里说明理由。"
        )

    if rc == 0:
        print(f"\n[PASS] catch any 为 0；any 总量未超过基线 {base.get('total', 0)}。")
    return rc


if __name__ == "__main__":
    sys.exit(main())
