#!/usr/bin/env python3
"""扫描"活文档"是否残留已作废的 benchmark 旧口径数字。

设计目标：把"人肉发现口径漂移"变成 CI 门禁。命中即红，定位到 文件:行。

- 只扫描 LIVE 文档面（src/ docs/ deliverables/frontend/ 证据页），不扫全树，
  避免误伤其它赛道（大创/main、审计、溯源）的时点留档。
- 已作废数字见 `docs/METRICS_CURRENT.md` 的"已作废旧口径"表。
- `--verify-ssot`：校验 SSOT（docs/METRICS_CURRENT.md）的 sha256 与真产物是否同步。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 只扫这些"活文档面"，其余赛道/留档默认排除
SCAN_ROOTS = [
    "src",
    "docs",
    "deliverables/frontend",
    "deliverables/证据索引-2026-09-16.md",
    "deliverables/证据索引-2026-09-16.html",
    "deliverables/证据一页图-2026-09-16.html",
]

# 路径包含以下子串的，视为时点留档/其它赛道/SSOT 自身，跳过（不扫描）
EXCLUDE_PATH_SUBSTR = (
    "system_design.md",       # 设计史校正留痕
    "METRICS_CURRENT.md",     # SSOT 自身需列出已作废旧口径作参考
    "archive",                # 归档
    "engineering-assurance",  # 08-29 时点审计
    "MARS-408",               # 大创/main 线材料 dump（513 文件）
    "闽江申报材料归档",          # 大创/main 线
    "平台现状摸底",             # 大创/main 线规划稿
    "gstack",
    "product-strategy",
    "mangde_online_screenshots",
    "待办交接",                # 交接单 §4 旧列对比属有意
)

# 已作废的旧 benchmark 口径（出现即漂移）
OBSOLETE_PATTERNS = [
    r"83\.3[0-9]?%?",          # 旧 NeuralMixer 准确率 83.3%
    r"0\.776(?![\d])",         # 旧 κ 0.776（不误伤 0.7763→仍算旧，但 0.776 已作废）
    r"\+10\.7pp",              # 旧召回 Δ
    r"≈?20\s*×",              # 旧延迟倍数 ≈20×
    r"(?<![\d])0?\.14%",      # 旧 token −0.14%（排除 82.14% 等当前真值）
    r"78\.6%",                # 旧 FrugalRAG recall@5
    r"67\.9%",                # 旧 全量 recall@5
    r"108\.2ms",              # 旧 FrugalRAG 延迟
]
OBSOLETE_RE = [re.compile(p) for p in OBSOLETE_PATTERNS]

SCAN_EXT = (".md", ".html", ".vue", ".ts", ".txt")

TRUTH_ARTIFACT = "py-server/experiments/results/benchmark_2026-09-18.json"
SSOT_DOC = "docs/METRICS_CURRENT.md"


def _iter_targets() -> list[str]:
    out: list[str] = []
    for root in SCAN_ROOTS:
        abs_root = os.path.join(ROOT, root)
        if os.path.isfile(abs_root):
            out.append(abs_root)
            continue
        for dirpath, _dirs, files in os.walk(abs_root):
            for f in files:
                if f.lower().endswith(SCAN_EXT):
                    out.append(os.path.join(dirpath, f))
    return out


def _is_excluded(rel: str) -> bool:
    low = rel.lower()
    return any(s.lower() in low for s in EXCLUDE_PATH_SUBSTR)


def scan() -> int:
    hits = 0
    scanned = 0
    for path in _iter_targets():
        rel = os.path.relpath(path, ROOT)
        if _is_excluded(rel):
            continue
        scanned += 1
        try:
            lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            for rx in OBSOLETE_RE:
                for m in rx.finditer(line):
                    snippet = line.strip()[:120]
                    print(f"  ❌ {rel}:{i} 命中作废口径 [{m.group(0)}] → {snippet}")
                    hits += 1
    print(f"\n扫描活文档 {scanned} 个，命中作废口径 {hits} 处。")
    if hits:
        print("→ 这些数字已作废（见 docs/METRICS_CURRENT.md）。请更新为当前真值或加产物版本注明。")
    return 1 if hits else 0


def verify_ssot() -> int:
    artifact = os.path.join(ROOT, TRUTH_ARTIFACT)
    ssot = os.path.join(ROOT, SSOT_DOC)
    if not os.path.exists(artifact):
        print(f"❌ 真产物缺失：{TRUTH_ARTIFACT}")
        return 1
    data = open(artifact, "rb").read()
    sha = hashlib.sha256(data).hexdigest()
    size = len(data)
    if not os.path.exists(ssot):
        print(f"❌ SSOT 缺失：{SSOT_DOC}")
        return 1
    text = open(ssot, encoding="utf-8").read()
    if sha[:16] not in text:
        print(f"❌ SSOT 的 sha256 与真产物不一致。")
        print(f"   真产物 sha256 = {sha}")
        print(f"   → 请更新 {SSOT_DOC} 的 sha256 / 大小 / 关键数字。")
        return 1
    # 顺带校验关键数字在 SSOT 中
    e1 = json.loads(data.decode("utf-8"))["experiment1"]["summary"]
    d_recall = f"{e1['deltas']['recall_delta']*100:.2f}".rstrip("0").rstrip(".")
    need = [f"+{d_recall}pp", f"{size} 字节" if False else f"{size}"]
    missing = [n for n in need if n not in text]
    print(f"✅ SSOT 与真产物同步：sha256={sha[:16]}…  size={size}B")
    if missing:
        print(f"⚠️  SSOT 未含关键数字：{missing}（建议补）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-ssot", action="store_true", help="仅校验 SSOT 与真产物同步")
    args = ap.parse_args()
    if args.verify_ssot:
        return verify_ssot()
    print("=== benchmark 口径漂移扫描（活文档面）===")
    return scan()


if __name__ == "__main__":
    sys.exit(main())
