#!/usr/bin/env python3
"""品牌一致性门禁（gate:brand）

产品对外可见层不得出现旧品牌名（MARS-408 及其变体）或旧赛事名
（火山杯 / 软件杯 / 三创赛 / huoshan），一律统一为「芒得很职」，且不展示任何赛事名称。

覆盖范围（产品对外可见层）：
  - 前端：src/、public/、index.html、package.json
  - 后端：py-server/{app,api,services,agents,db,engines,tools,scripts} 下的 .py
          + py-server/config.py、py-server/main.py

排除（历史记录 / 生成产物 / 冻结副本 —— 有意保留原名）：
  - docs/ documents/ deliverables/ diagnostics/（历史与交付快照）
  - */crypto_platform/**（AGENTS.md:20 冻结的嵌套副本，未经确认不得改动）
  - dist/ node_modules/ .git/ __pycache__/，以及非文本扩展名

特例白名单：仓库/站点真实 URL（GitHub 仓名尚未更名，属功能性引用，非品牌展示）
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 旧品牌 / 旧赛事令牌（MARS 同时覆盖 MARS-408 / MARS408 / 拆分 span 写法）
TOKENS = ["MARS", "火山杯", "软件杯", "三创赛", "huoshan", "火星杯"]

# 功能性 URL 白名单（仓名未更名前必须保留）
ALLOW_SUBSTRINGS = [
    "truefurina.github.io/MARS-408",
    "github.com/TrueFurina/MARS-408",
    "TrueFurina/MARS-408",
]

SCAN_DIRS = ["src", "public"]
SCAN_FILES = ["index.html", "package.json"]
BACKEND_DIRS = ["app", "api", "services", "agents", "db", "engines", "tools", "scripts"]
BACKEND_FILES = ["config.py", "main.py"]

EXCLUDE_PARTS = {"node_modules", ".git", "dist", "crypto_platform", "__pycache__", ".pytest_cache"}

TEXT_EXT = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".json", ".html", ".htm",
    ".css", ".md", ".txt", ".py", ".yml", ".yaml", ".webmanifest", ".sh", ".bat", ".ps1",
}


def _iter_files():
    for d in SCAN_DIRS:
        p = ROOT / d
        if p.exists():
            yield from (f for f in p.rglob("*") if f.is_file())
    for f in SCAN_FILES:
        p = ROOT / f
        if p.exists():
            yield p
    for d in BACKEND_DIRS:
        p = ROOT / "py-server" / d
        if p.exists():
            yield from (f for f in p.rglob("*") if f.is_file())
    for f in BACKEND_FILES:
        p = ROOT / "py-server" / f
        if p.exists():
            yield p


def _excluded(path: Path) -> bool:
    if set(path.parts) & EXCLUDE_PARTS:
        return True
    if path.suffix.lower() not in TEXT_EXT:
        return True
    return False


def _allowed(line: str) -> bool:
    return any(s in line for s in ALLOW_SUBSTRINGS)


def main() -> int:
    hits = []
    for f in _iter_files():
        if _excluded(f):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if _allowed(line):
                continue
            for tok in TOKENS:
                if tok in line:
                    rel = f.relative_to(ROOT).as_posix()
                    hits.append((rel, i, tok, line.strip()[:120]))
                    break

    if hits:
        print("[gate:brand] FAIL — 产品可见层仍含旧品牌 / 旧赛事名：")
        for rel, i, tok, snippet in hits:
            print(f"  {rel}:{i}  [{tok}]  {snippet}")
        print(f"\n共 {len(hits)} 处。请统一为「芒得很职」，并移除任何赛事名称。")
        return 1

    print("[gate:brand] PASS — 产品可见层无旧品牌 / 旧赛事名残留。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
