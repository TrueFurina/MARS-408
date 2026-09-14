"""按真实密钥形态扫描 seed_demo_data.py：JWT / hex / base64 / 各类 provider key 前缀 / PII。

仍然只输出哈希与形态标签，绝不打印原值（哪怕是疑似占位）。
"""
from __future__ import annotations

import hashlib
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [ROOT / "py-server" / "seed_demo_data.py", ROOT / "py-server" / "config.example.json"]

PATTERNS: list[tuple[str, str]] = [
    ("jwt", r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}\b"),
    ("hex32+", r"\b[0-9a-fA-F]{32,}\b"),
    ("base64ish40+", r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),
    ("sk-dash", r"\bsk-[A-Za-z0-9_\-]{16,}"),
    ("ak-live", r"\bak_(live|test)_[A-Za-z0-9]{8,}"),
    ("aws-akid", r"\b(AKIA|ASIA)[0-9A-Z]{12,}"),
    ("xfyun-32hex", r"\b[0-9a-f]{32}\b"),
    ("bearer", r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
    ("uuid", r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
    ("pwd-field", r"(?i)(password|passwd|pwd|secret|api_?key|access_?token)\s*[:=]\s*['\"][^'\"]{6,}['\"]"),
    ("cn-phone", r"\b1[3-9]\d{9}\b"),
    ("email", r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    ("cn-id", r"\b\d{17}[\dXx]\b"),
]


def sh(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "surrogatepass")).hexdigest()[:12]


def scan(path: Path) -> int:
    if not path.exists():
        print(f"[skip] {path.name} 不存在")
        return 0
    text = io.open(path, encoding="utf-8", errors="replace").read()
    lines = text.splitlines()
    total = 0
    print(f"### {path.relative_to(ROOT)} （{len(lines)} 行）")
    for name, pat in PATTERNS:
        rx = re.compile(pat)
        hits = []
        for ln, line in enumerate(lines, 1):
            for m in rx.finditer(line):
                val = m.group(0)
                hits.append((ln, sh(val), len(val)))
        if hits:
            total += len(hits)
            print(f"  [{name}] {len(hits)} 命中:")
            for ln, h, L in hits[:10]:
                print(f"     L{ln} sha={h} len={L}")
        else:
            print(f"  [{name}] 0")
    print("-" * 84)
    return total


def main() -> int:
    grand = 0
    for p in TARGETS:
        grand += scan(p)
    print(f"总命中: {grand}")
    if grand == 0:
        print(">>> 结论：两份文件中**不存在任何真实密钥形态**（JWT/hex32/base64/前缀式/明文密码/PII 全 0）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
