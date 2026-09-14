"""枚举演示口令在仓库中的全部硬编码点（按哈希判定，不打印值），并标注跟踪状态与用途类别。

输出：文件 / 行号 / 是否被 git 跟踪 / 是否会被部署或打包 / 用途推断。
"""
from __future__ import annotations

import hashlib
import io
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = hashlib.sha256(b"demo123456").hexdigest()[:12]

SKIP_DIRS = ("node_modules", ".git", "archive", ".venv", "__pycache__")
SCAN_EXT = (
    ".py", ".json", ".md", ".ts", ".js", ".vue", ".yml", ".yaml",
    ".sh", ".bat", ".ps1", ".html", ".css",
)
LIT = re.compile(r"""(['"=:\s])([A-Za-z0-9_@.\-]{6,40})(['"\s]?)""")

CATEGORY = [
    ("前端源码", ("src/",)),
    ("前端构建产物", ("dist/", "dist-verify/")),
    ("后端源码", ("py-server/",)),
    ("启动脚本", ("start.", "scripts/start", "scripts/build_portable")),
    ("工具/探针", ("tools/", "_debug_smoke", "scripts/bench")),
    ("文档/备份", (".md",)),
    ("其它", ()),
]


def tracked(path: str) -> bool:
    p = subprocess.run(["git", "ls-files", "--error-unmatch", path],
                       cwd=str(ROOT), capture_output=True, text=True)
    return p.returncode == 0


def ignored(path: str) -> bool:
    p = subprocess.run(["git", "check-ignore", path],
                       cwd=str(ROOT), capture_output=True, text=True)
    return p.returncode == 0


def classify(rel: str) -> str:
    for name, keys in CATEGORY:
        if any(k in rel for k in keys):
            return name
    return "其它"


def main() -> int:
    hits: list[tuple[str, int, bool, bool]] = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        s = str(p.relative_to(ROOT)).replace("\\", "/")
        if any(d in p.parts for d in SKIP_DIRS):
            continue
        if p.suffix not in SCAN_EXT:
            continue
        try:
            text = io.open(p, encoding="utf-8", errors="replace").read()
        except Exception:  # noqa: BLE001
            continue
        for ln, line in enumerate(text.splitlines(), 1):
            for m in LIT.finditer(line):
                v = m.group(2)
                if hashlib.sha256(v.encode()).hexdigest()[:12] == TARGET:
                    hits.append((s, ln, tracked(s), ignored(s)))
                    break

    print(f"演示口令硬编码点总数: {len(hits)}")
    print("=" * 96)
    groups: dict[str, list] = {}
    for h in hits:
        groups.setdefault(classify(h[0]), []).append(h)

    for cat in [c[0] for c in CATEGORY]:
        items = groups.get(cat, [])
        if not items:
            continue
        print(f"\n### {cat}（{len(items)} 处）")
        for rel, ln, tr, ig in items[:14]:
            flags = []
            flags.append("tracked" if tr else "untracked")
            if ig:
                flags.append("gitignored")
            print(f"   {rel:<58} L{ln:<5} [{', '.join(flags)}]")
        if len(items) > 14:
            print(f"   ... 其余 {len(items) - 14} 处同类")

    print("=" * 96)
    ship = [h for h in hits if "dist/" in h[0] or "dist-verify" in h[0]]
    src_fe = [h for h in hits if h[0].startswith("src/")]
    print(f"汇总：构建产物命中 {len(ship)} 处；前端源码命中 {len(src_fe)} 处；"
          f"被 git 跟踪 {sum(1 for h in hits if h[2])} 处。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
