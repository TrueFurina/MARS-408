"""定位 seed_demo_data.py L28 同源字面量：打印掩码上下文 + 配置侧来源标签。

仍然**不打印原值**：所有 >=12 字符的字符串字面量一律替换为 <sha:xxxx len=n>。
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "py-server" / "seed_demo_data.py"
ENV = ROOT / "py-server" / ".env"
CFG = ROOT / "py-server" / "config.json"
TARGET_SHA = sys.argv[1] if len(sys.argv) > 1 else "7716e7a3f7c1"

LIT = re.compile(r"""(['"])((?:\\.|(?!\1)[^\\]){12,})\1""")


def sh(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "surrogatepass")).hexdigest()[:12]


def mask_line(line: str) -> str:
    def repl(m: re.Match) -> str:
        v = m.group(2)
        return f"<sha:{sh(v)} len={len(v)}>"

    return LIT.sub(repl, line)


def config_labels_for(target: str) -> list[str]:
    hits: list[str] = []

    def reg(val, label):
        if isinstance(val, str) and len(val.strip()) >= 12 and sh(val.strip()) == target:
            hits.append(label)

    if CFG.exists():
        try:
            raw = json.loads(io.open(CFG, encoding="utf-8", errors="replace").read())
        except Exception:  # noqa: BLE001
            raw = None
        if isinstance(raw, dict):
            def walk(node, path):
                if isinstance(node, dict):
                    for k, v in node.items():
                        walk(v, f"{path}.{k}" if path else str(k))
                elif isinstance(node, list):
                    for i, v in enumerate(node):
                        walk(v, f"{path}[{i}]")
                else:
                    reg(str(node), f"config.json:{path}")
            walk(raw, "")

    if ENV.exists():
        for ln, line in enumerate(io.open(ENV, encoding="utf-8", errors="replace"), 1):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                reg(v.strip().strip('"').strip("'"), f".env:{k.strip()} (line {ln})")

    return hits


def main() -> int:
    print(f"目标指纹: {TARGET_SHA}")
    print("=" * 90)
    labels = config_labels_for(TARGET_SHA)
    print(f"配置侧同源标签: {labels if labels else '(无)'}")
    print("=" * 90)

    text = io.open(SEED, encoding="utf-8", errors="replace").read()
    lines = text.splitlines()
    # 找命中的行号
    hit_lines = [
        i for i, ln_ in enumerate(lines, 1)
        if any(sh(m.group(2)) == TARGET_SHA for m in LIT.finditer(ln_))
    ]
    print(f"seed 中命中行号: {hit_lines}")
    print("=" * 90)

    for hl in hit_lines:
        lo, hi = max(1, hl - 8), min(len(lines), hl + 6)
        for i in range(lo, hi + 1):
            mark = ">>" if i == hl else "  "
            print(f"{mark}{i:>4}| {mask_line(lines[i - 1])}")
        print("-" * 90)

    print("附带：py-server 全树中同指纹字面量分布（只列文件与行号，不打印值）")
    for p in (ROOT / "py-server").rglob("*.py"):
        if "crypto_platform" in p.parts or "node_modules" in p.parts:
            continue
        try:
            t = io.open(p, encoding="utf-8", errors="replace").read()
        except Exception:  # noqa: BLE001
            continue
        found = [
            i for i, ln_ in enumerate(t.splitlines(), 1)
            if any(sh(m.group(2)) == TARGET_SHA for m in LIT.finditer(ln_))
        ]
        if found:
            print(f"  {p.relative_to(ROOT)} :: lines {found[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
