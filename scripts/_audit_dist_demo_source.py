"""查清 dist 构建产物中演示口令的来源，并检查部署文档是否已提示生产环境变量。

全部输出掩码（命中片段替换为 <HIT ...>）。
"""
from __future__ import annotations

import hashlib
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = hashlib.sha256(b"demo123456").hexdigest()[:12]
DEMO_USER = hashlib.sha256(b"demo").hexdigest()[:12]
LIT = re.compile(r"([A-Za-z0-9_@.\-]{4,40})")


def sh(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:12]


def mask_from_offsets(text: str, start: int, end: int, pad: int = 260) -> str:
    seg = text[max(0, start - pad): end + pad]

    def repl(m: re.Match) -> str:
        h = sh(m.group(1))
        if h == TARGET:
            return "<HIT_PW>"
        if h == DEMO_USER:
            return "<HIT_USER>"
        return m.group(1)

    return LIT.sub(repl, seg)


def report_dist() -> None:
    print("### dist 产物中的命中上下文（掩码）")
    for rel in ["dist/assets/LoginView-B7GTrOPd.js", "dist-verify/assets/LoginView-BNjrN72B.js"]:
        p = ROOT / rel
        if not p.exists():
            print(f"  {rel} 不存在")
            continue
        t = io.open(p, encoding="utf-8", errors="replace").read()
        idxs = [m.start() for m in re.finditer(r"[A-Za-z0-9_@.\-]{4,40}", t)
                if sh(m.group(0)) == TARGET]
        print(f"\n  [{rel}] 命中 {len(idxs)} 处")
        for i in idxs[:2]:
            print("   ..." + mask_from_offsets(t, i, i + 10).replace("\n", " ") + "...")
    print("=" * 92)


def report_src() -> None:
    print("### 前端源码中与 demo 登录相关的实现（看是否有意做成演示便捷入口）")
    for p in (ROOT / "src").rglob("*"):
        if p.suffix not in (".vue", ".ts", ".js"):
            continue
        try:
            t = io.open(p, encoding="utf-8", errors="replace").read()
        except Exception:  # noqa: BLE001
            continue
        for ln, line in enumerate(t.splitlines(), 1):
            low = line.lower()
            if "demo" in low and any(k in low for k in ("login", "password", "user", "演示", "账号", "vite_")):
                print(f"  {p.relative_to(ROOT)} L{ln}: {line.strip()[:120]}")
    print("=" * 92)


def report_env() -> None:
    print("### .env 中 VITE_ 变量名（只看名字，不看值）")
    p = ROOT / "py-server" / ".env"
    if not p.exists():
        print("  (无 py-server/.env)")
    else:
        for ln, line in enumerate(io.open(p, encoding="utf-8", errors="replace"), 1):
            s = line.strip()
            if s.startswith("VITE_") or "DEMO" in s.upper():
                k = s.split("=")[0]
                print(f"  L{ln}: {k}= <masked>")
    for f in [".env", ".env.local", ".env.production"]:
        q = ROOT / f
        if q.exists():
            print(f"  根目录 {f} 存在")
            for ln, line in enumerate(io.open(q, encoding="utf-8", errors="replace"), 1):
                s = line.strip()
                if s and not s.startswith("#"):
                    print(f"     L{ln}: {s.split('=')[0]}= <masked>")
    print("=" * 92)


def report_docs() -> None:
    print("### 部署文档是否已提示 NETLEARN_ENV")
    for rel in ["docs/deployment-checklist.md", "INSTALL.md", "docs/deployment.md", "README_EN.md"]:
        p = ROOT / rel
        if not p.exists():
            print(f"  {rel}: 不存在")
            continue
        t = io.open(p, encoding="utf-8", errors="replace").read()
        n = t.count("NETLEARN_ENV")
        print(f"  {rel}: NETLEARN_ENV 出现 {n} 次")
        for ln, line in enumerate(t.splitlines(), 1):
            if "NETLEARN_ENV" in line:
                print(f"     L{ln}: {line.strip()[:120]}")
    print("=" * 92)


def main() -> int:
    report_dist()
    report_src()
    report_env()
    report_docs()
    return 0


if __name__ == "__main__":
    sys.exit(main())
