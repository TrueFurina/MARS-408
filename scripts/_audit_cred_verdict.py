"""最终判定 seed_demo_data.py 的凭据字段：是演示口令还是生产凭据。

输出仅哈希与形态，不打印值。
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

# 常见演示/占位口令（用于哈希比对，判"是否为人尽皆知的 demo 值"）
COMMON = [
    "password", "Password", "passw0rd", "123456", "12345678", "123456789",
    "admin", "admin123", "demo", "demo123", "demo1234", "demo123456",
    "test", "test123", "test1234", "test123456", "testpass",
    "netlearn", "netlearn123", "netlearn123456", "mars408", "mars-408",
    "changeme", "secret", "default", "example", "student", "student123",
    "demo-password", "demo_password", "123456abc", "abc123456", "a123456",
]

KEYVAL = re.compile(
    r"""(?i)(password|passwd|pwd|secret|api_?key|access_?token|token)\s*[:=]\s*(['"])([^'"]{4,})\2"""
)


def sh(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "surrogatepass")).hexdigest()[:12]


def classes(s: str) -> str:
    k = []
    if re.search(r"[a-z]", s):
        k.append("a-z")
    if re.search(r"[A-Z]", s):
        k.append("A-Z")
    if re.search(r"[0-9]", s):
        k.append("0-9")
    if re.search(r"[^A-Za-z0-9]", s):
        k.append("sym")
    return ",".join(k) or "empty"


def config_hashes() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}

    def reg(v, label):
        if isinstance(v, str) and len(v.strip()) >= 4:
            out.setdefault(sh(v.strip()), []).append(label)

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
                reg(v.strip().strip('"').strip("'"), f".env:{k.strip()}(L{ln})")
    return out


def main() -> int:
    common_h = {sh(c): c for c in COMMON}  # 只用于"是否为常见演示值"判定，命中时不打印值本身
    cfg = config_hashes()

    print("=== seed_demo_data.py 中 键=值 形式的凭据字段 ===")
    lines = io.open(SEED, encoding="utf-8", errors="replace").read().splitlines()
    hits = []
    for ln, line in enumerate(lines, 1):
        for m in KEYVAL.finditer(line):
            hits.append((ln, m.group(1), m.group(3)))

    if not hits:
        print("(无凭据字段赋值)")
    for ln, key, val in hits:
        h = sh(val)
        verdict = []
        if h in cfg:
            verdict.append(f"*** 与生产配置同源: {cfg[h]} ***")
        if h in common_h:
            verdict.append("命中常见演示口令清单(人尽皆知,无保密价值)")
        # 弱口令形态
        if len(val) < 12 and not any(x in verdict for x in ["命中"]):
            verdict.append("弱口令/短值")
        print(f"  L{ln} key={key} sha={h} len={len(val)} [{classes(val)}]")
        print(f"      判定: {'; '.join(verdict) if verdict else '未知，需人工'}")
        print(f"      同行结构(掩码): {KEYVAL.sub(lambda mm: mm.group(1) + '=<sha:' + sh(mm.group(3)) + '>', lines[ln-1]).strip()[:110]}")

    print()
    print("=== 全文件短凭据字面量(<16)复查：与生产配置同源的任何字符串 ===")
    LIT = re.compile(r"""(['"])((?:\\.|(?!\1)[^\\]){6,})\1""")
    same = []
    for ln, line in enumerate(lines, 1):
        for m in LIT.finditer(line):
            v = m.group(2)
            if sh(v) in cfg:
                same.append((ln, sh(v), len(v), cfg[sh(v)]))
    if same:
        for ln, h, L, labels in same:
            print(f"  L{ln} sha={h} len={L} <- {labels}")
    else:
        print("(无)")

    print()
    print(">>> 总判定：")
    real = [h for h in hits if sh(h[2]) in cfg]
    if real:
        print("    存在与生产配置完全一致的凭据 => 真凭据，需轮换")
    else:
        print("    无任何字段与 .env/config.json 中的生产值一致 => 非生产凭据")
    return 0


if __name__ == "__main__":
    sys.exit(main())
