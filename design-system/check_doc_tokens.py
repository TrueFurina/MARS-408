#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_doc_tokens.py — 芒得很职 设计系统 · 文档漂移门禁（dependency-free）

背景：本次事故的根因是「文档不被门禁守护 → 自由漂移」。check_tokens.py 只校验
showcase HTML，check_raw_values.py 只校验代码。本脚本补最后一块：**prose 规范文档
不得引用「非令牌色值」**，从源头堵住「文档写旧调色板颜色 → AI 照抄生成错 UI」。

权威源：src/assets/styles/_variables.css 中出现的所有 hex（= 现行令牌值全集）。
被检对象：docs/reports/DESIGN.md（唯一现行 prose 规范）。

判定：
- 文档中的 hex ∉ 权威集 且 非白/黑中性 且 所在行无「废弃/旧/历史/retired/superseded」标记
  → DRIFT（须修正为令牌值，或在该处显式标注为"已废弃"）。

用法：python design-system/check_doc_tokens.py
退出码：0 = 无漂移；1 = 有漂移；2 = 环境/零覆盖错误（权威源或全部被检文档缺失）。

零覆盖纪律（2026-10-08 补）
--------------------------------------------------------------------------
原实现把「文档不存在」当作 `跳过` 处理，随后 `total == 0` → 打印
「零漂移 (DOC IN SYNC) — prose 文档不引用非令牌色值」并 exit 0。
实测复现（隔离树内不创建 DESIGN.md）：门禁 exit 0 且输出该结论 ——
即**它对自己从未读过的文档下了肯定性结论**。
`DOCS` 是硬编码路径，文档一旦改名/移位，本门禁就会永久静默通过，
而「文档不被门禁守护 → 自由漂移」正是本脚本当初要治的病。
故：零覆盖必须 fail-closed（exit 2），且不再声称任何同步结论。
（同口径先例：`scripts/pre-commit/run_gates.py` 的 `record()` 区分
「检查过且放行」与「一道都没检查」。）
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARS = os.path.join(ROOT, "src", "assets", "styles", "_variables.css")
DOCS = [os.path.join(ROOT, "docs", "reports", "DESIGN.md")]

HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
WHITE_BLACK = {"#fff", "#ffffff", "#000", "#000000"}
RETIRED_MARK = ("废弃", "旧", "历史", "retired", "superseded", "已被", "token-exception")


def norm(h):
    h = h.lower()
    if len(h) == 4:  # #abc -> #aabbcc
        h = "#" + h[1] * 2 + h[2] * 2 + h[3] * 2
    return h


def main() -> int:
    if not os.path.exists(VARS):
        print(f"[ERROR] 权威源不存在: {os.path.relpath(VARS, ROOT)} —— "
              f"无法建立「现行令牌值全集」，拒绝在无基准的情况下判定", file=sys.stderr)
        return 2
    canonical = {norm(h) for h in HEX_RE.findall(open(VARS, encoding="utf-8").read())}
    print(f"[canonical] _variables.css 提供 {len(canonical)} 个 hex 令牌值\n")

    total = 0
    examined = 0  # 真正被读入并比对的文档数（区别于「存在于列表中」）
    missing = []
    for doc in DOCS:
        if not os.path.exists(doc):
            missing.append(os.path.relpath(doc, ROOT))
            print(f"  ! 跳过（不存在）: {os.path.relpath(doc, ROOT)}")
            continue
        examined += 1
        text = open(doc, encoding="utf-8").read()
        rel = os.path.relpath(doc, ROOT)
        hits = []
        for i, line in enumerate(text.splitlines(), 1):
            if any(m in line for m in RETIRED_MARK):
                continue
            for h in HEX_RE.findall(line):
                n = norm(h)
                if n in canonical or n in WHITE_BLACK:
                    continue
                hits.append((i, h, line.strip()[:110]))
        if hits:
            total += len(hits)
            print(f"  [DRIFT] {rel}")
            for ln, h, snip in hits:
                print(f"      L{ln}  {h}")
                print(f"          {snip}")
        else:
            print(f"  [OK]    {rel}  (文档色值全部为现行令牌值)")

    print()
    if examined == 0:
        print(f"[ERROR] 零覆盖: {len(missing)}/{len(DOCS)} 个被检文档都不存在 -> {missing}\n"
              f"        本门禁未比对任何文档，故不能声称「文档与令牌同步」（那是它无从得知的结论）。\n"
              f"        请检查 DOCS 路径是否已失效（文档改名/移位），或恢复该文档。", file=sys.stderr)
        return 2
    if total == 0:
        print(f"=== 结论: 零漂移 (DOC IN SYNC) — {examined}/{len(DOCS)} 份文档的色值全部为现行令牌值 ===")
        return 0
    print(f"=== 结论: 文档引用 {total} 处非令牌色值，需修正或标注 ===")
    return 1


if __name__ == "__main__":
    sys.exit(main())
