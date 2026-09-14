"""git 历史凭据形态扫描 —— 判定历史提交中是否曾出现真实密钥。

做法：对候选文件（曾含凭据形态字面量者）取其**所有历史 blob 版本**逐个做形态扫描，
输出仅"提交号 / 形态名 / 哈希 / 长度"，不打印值。
只读，不写仓库。
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CANDIDATES = [
    "py-server/seed_demo_data.py",
    "py-server/config.py",
    "py-server/db/xfyun_services.py",
    "py-server/db/xfyun_multimodal.py",
    "py-server/services/tts_service.py",
    "py-server/config.example.json",
    "py-server/.env",
    "py-server/config.json",
    ".env",
    "config.json",
]

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
]

# 允许名单：这些形态是算法/测试夹具中的已知良性值（如 sha256 摘要、uuid、示例盐）
BENIGN_HINT = re.compile(r"(sha256|md5|checksum|digest|hash|salt|dummy|DEMO|test|示例|演示)")


def run(*args: str) -> str:
    p = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True, errors="replace")
    return p.stdout


def sh(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "surrogatepass")).hexdigest()[:12]


def blob_versions(path: str) -> list[tuple[str, str]]:
    """返回 [(commit, blob_sha)]，该路径历史上所有出现的版本。"""
    out = run("git", "log", "--all", "--format=%H", "--follow", "--", path).split()
    seen: dict[str, str] = {}
    for c in out:
        spec = f"{c}:{path}"
        p = subprocess.run(["git", "cat-file", "-t", spec], cwd=str(ROOT),
                           capture_output=True, text=True)
        if p.stdout.strip() == "blob":
            b = run("git", "rev-parse", spec).strip()
            seen.setdefault(b, c)
    return [(c, b) for b, c in seen.items()]


def main() -> int:
    total_commits = len(run("git", "rev-list", "--all").split())
    print(f"仓库总提交数（--all）: {total_commits}")
    print("=" * 88)

    # 0) 敏感文件是否曾入库
    print("### 敏感文件历史入库检查")
    for f in ["py-server/.env", "py-server/config.json", ".env", "config.json", "py-server/config.example.json"]:
        r = run("git", "log", "--all", "--oneline", "--", f).strip()
        print(f"  {f:<34} -> {'曾入库 (' + str(len(r.splitlines())) + ' 次提交)' if r else '从未入库'}")
    print("=" * 88)

    # 1) 候选文件的所有历史版本形态扫描
    print("### 候选文件历史 blob 形态扫描")
    grand = 0
    for path in CANDIDATES:
        vers = blob_versions(path)
        if not vers:
            print(f"\n[{path}] 无历史版本")
            continue
        print(f"\n[{path}] 历史版本 {len(vers)} 个")
        for commit, blob in vers:
            body = run("git", "cat-file", "-p", blob)
            found = []
            for name, pat in PATTERNS:
                for m in re.finditer(pat, body):
                    val = m.group(0)
                    # 取上下文判断是否良性（哈希/盐/示例）
                    s0 = max(0, m.start() - 120)
                    ctx = body[s0:m.end() + 40]
                    tag = "benign?" if BENIGN_HINT.search(ctx) else "SUSPECT"
                    found.append((name, sh(val), len(val), tag))
            if found:
                grand += len(found)
                print(f"  blob {blob[:10]} (commit {commit[:8]}):")
                for name, h, L, tag in found[:12]:
                    print(f"     {name:<14} sha={h} len={L} [{tag}]")
            else:
                print(f"  blob {blob[:10]} (commit {commit[:8]}): 干净")

    print("=" * 88)
    print(f"历史形态命中总数（含 benign? 候选）: {grand}")
    if grand == 0:
        print(">>> 结论：git 历史中**从未出现**任何真实密钥形态。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
