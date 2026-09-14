"""对全历史扫描中的高价值命中做掩码上下文取证（判断是密钥还是良性常量）。

输入：路径 + 形态 + 目标哈希。输出：命中行的变量名/结构完整可见，
但**目标值本身被替换为 <HIT sha=... len=...>**，不打印原值。
"""
from __future__ import annotations

import hashlib
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (文件, 目标子串的哈希前缀, 说明, 是否为十六进制形态)
TARGETS = [
    ("py-server/db/user_store.py", "c6e10d0dc8b8", "hex32 x5 —— 疑似硬编码盐/密钥", True),
    ("py-server/prompts_career.py", "bc5c5a1b8ce0", "len48 长串", False),
    ("py-server/prompts.py", "4028d4dc9c31", "len48 长串", False),
    ("scripts/eval_retrieval_real.py", "181f1f5644a5", "len59 长串", False),
    ("py-server/tests/test_f015_extension.py", "726155beb498", "len53 长串", False),
    ("docs/reports/PRODUCTION_READINESS_2026-07-12.md", "c7c961b66a3b", "len55 长串", False),
]

HEX32 = re.compile(r"\b[0-9a-fA-F]{32}\b")
B64LIKE = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")


def sh(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "surrogatepass")).hexdigest()[:12]


def mask(line: str, target: str, is_hex: bool) -> str:
    pattern = HEX32 if is_hex else B64LIKE

    def repl(m: re.Match) -> str:
        v = m.group(0)
        if sh(v) == target:
            return f"<HIT sha={target} len={len(v)}>"
        return f"<other sha={sh(v)} len={len(v)}>"

    return pattern.sub(repl, line)


def config_hashes() -> set[str]:
    out: set[str] = set()
    for p in [ROOT / "py-server" / ".env", ROOT / "py-server" / "config.json"]:
        if not p.exists():
            continue
        for line in io.open(p, encoding="utf-8", errors="replace"):
            s = line.strip()
            if "=" in s and not s.startswith("#"):
                _, _, v = s.partition("=")
                v = v.strip().strip('"').strip("'")
                if v:
                    out.add(sh(v))
    return out


def main() -> int:
    cfg = config_hashes()
    for path, target, note, is_hex in TARGETS:
        p = ROOT / path
        print("=" * 92)
        print(f"[{path}] {note}  目标 sha={target}")
        if not p.exists():
            print("  文件不存在，跳过")
            continue
        lines = io.open(p, encoding="utf-8", errors="replace").read().splitlines()
        pattern = HEX32 if is_hex else B64LIKE
        hit_lines = [
            i for i, ln in enumerate(lines, 1)
            if any(sh(m.group(0)) == target for m in pattern.finditer(ln))
        ]
        print(f"  命中行: {hit_lines[:12]}{' ...' if len(hit_lines) > 12 else ''}")
        shown = set()
        for hl in hit_lines[:4]:
            for i in range(max(1, hl - 3), min(len(lines), hl + 2) + 1):
                if i in shown:
                    continue
                shown.add(i)
                mark = ">>" if i == hl else "  "
                print(f"  {mark}{i:>4}| {mask(lines[i-1], target, is_hex)[:130]}")
            print("  " + "-" * 60)
        same_as_prod = target in cfg
        print(f"  是否与 .env/config.json 中某个值同源: {'是 *** 真凭据 ***' if same_as_prod else '否'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
