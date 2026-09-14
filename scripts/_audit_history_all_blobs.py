"""全仓库 git 历史 blob 级凭据形态扫描（覆盖所有曾入库文件，不止候选清单）。

枚举 `git rev-list --all --objects` 的去重 blob，用 --batch 批量取内容，
对全量历史做一次密钥形态扫描。只输出 路径/形态/哈希，不打印值。
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PATTERNS = [
    ("jwt", r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}\b"),
    ("hex32", r"\b[0-9a-fA-F]{32}\b"),
    ("hex40", r"\b[0-9a-fA-F]{40}\b"),
    ("hex64", r"\b[0-9a-fA-F]{64}\b"),
    ("sk-dash20+", r"\bsk-[A-Za-z0-9_\-]{20,}"),
    ("ak-live", r"\bak_(live|test)_[A-Za-z0-9]{8,}"),
    ("aws-akid", r"\b(AKIA|ASIA)[0-9A-Z]{12,}"),
    ("bearer24+", r"(?i)bearer\s+[A-Za-z0-9._\-]{24,}"),
    ("base64like48+", r"\b[A-Za-z0-9+/]{48,}={0,2}\b"),
    ("privkey", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]

# 只关心可能承载凭据的文件类型
INTERESTING_EXT = (
    ".py", ".json", ".env", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf",
    ".sh", ".bat", ".ps1", ".ts", ".js", ".vue", ".md", ".txt",
)

BENIGN_HINT = re.compile(
    r"(sha256|md5|checksum|digest|hash|salt|dummy|DEMO|demo|test|fixture|mock|示例|演示|example)",
    re.I,
)


def sh(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "surrogatepass")).hexdigest()[:12]


def main() -> int:
    out = subprocess.run(
        ["git", "rev-list", "--all", "--objects"],
        cwd=str(ROOT), capture_output=True, text=True, errors="replace",
    ).stdout

    blobs: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        sha, path = parts
        if not path.endswith(INTERESTING_EXT):
            continue
        blobs.setdefault(sha, path)

    print(f"历史中相关类型的去重 blob 数: {len(blobs)}")
    print("=" * 90)

    keys = "\n".join(blobs.keys())
    p = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=str(ROOT), input=keys.encode(), capture_output=True,
    )
    data = p.stdout

    # 逐个解析 batch 输出
    pos = 0
    hits: list[tuple[str, str, str, int, str]] = []
    scanned = 0
    while pos < len(data):
        nl = data.find(b"\n", pos)
        if nl < 0:
            break
        header = data[pos:nl].decode("utf-8", "replace")
        parts = header.split()
        if len(parts) < 3:
            pos = nl + 1
            continue
        sha, typ, size = parts[0], parts[1], int(parts[2])
        body = data[nl + 1: nl + 1 + size]
        pos = nl + 1 + size + 1
        if typ != "blob":
            continue
        scanned += 1
        text = body.decode("utf-8", "replace")
        path = blobs.get(sha, "?")
        for name, pat in PATTERNS:
            for m in re.finditer(pat, text):
                val = m.group(0)
                ctx = text[max(0, m.start() - 140): m.end() + 60]
                tag = "benign?" if BENIGN_HINT.search(ctx) else "SUSPECT"
                hits.append((path, name, sh(val), len(val), tag))

    print(f"实际扫描 blob 数: {scanned}")
    print("=" * 90)

    if not hits:
        print(">>> 结论：全部历史 blob 中 **零** 密钥形态命中。")
    else:
        agg: dict[str, list] = defaultdict(list)
        for path, name, h, L, tag in hits:
            agg[path].append((name, h, L, tag))
        print(f"命中文件数 {len(agg)}，命中条目 {len(hits)}")
        suspect = 0
        for path, items in sorted(agg.items(), key=lambda kv: -len(kv[1])):
            tags = {t for *_, t in items}
            mark = "  <<< 需人工看" if "SUSPECT" in tags else ""
            suspect += sum(1 for *_, t in items if t == "SUSPECT")
            print(f"  {path}  ({len(items)} 条){mark}")
            for name, h, L, tag in items[:6]:
                print(f"      {name:<14} sha={h} len={L} [{tag}]")
        print("-" * 90)
        print(f"SUSPECT（非哈希/示例上下文）条目数: {suspect}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
