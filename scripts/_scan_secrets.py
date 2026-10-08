#!/usr/bin/env python3
# 一次性精准密钥扫描器：复用 .gitleaks.toml 的 4 条 XFyun 正则，
# 只在历史中找"真实密钥形状"的值（输出脱敏，避免打印明文）。
#
# 退出码：0 = 已扫到对象且无命中；1 = 命中真实密钥值；2 = 环境/零覆盖（fail-closed）。
#
# REPO 由本文件位置推导。此前硬编码为 "E:/Program/MARL/study-help-pro"：
#   在其它机器上所有 git 调用都失败，却仍打印"扫描结束"并 exit 0，
#   把"一个对象都没扫"伪装成"干净"（本项目已修 9 次的「零覆盖 → 肯定性结论」形态）。
# 另：硬编码的嫌疑点会随历史重写失效（a47e8e4 已不存在），失效目标必须显式告警，
#   否则"跳过"与"扫过且干净"在输出上不可区分。
import os, re, subprocess, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RULES = [
    ("xfyun-api-secret", r"""(?i)(?:xfyun|api[_-]?secret|secret)[^0-9A-Za-z]{0,20}["']?([A-Za-z0-9+/]{32,}={0,2})["']?"""),
    ("xfyun-api-key",    r"""(?i)(?:xfyun|api[_-]?key|key)[^0-9A-Za-z]{0,20}["']?([a-f0-9]{32})["']?"""),
    ("xfyun-app-id",     r"""(?i)(?:xfyun|app[_-]?id|appid)[^0-9A-Za-z]{0,20}["']?([a-f0-9]{8})["']?"""),
    ("xfyun-api-password", r"""(?i)(?:api[_-]?password|apipassword|password)[^0-9A-Za-z]{0,20}["']?([A-Za-z0-9]{10,30}:[A-Za-z0-9]{10,30})["']?"""),
]

def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, errors="ignore")

# 覆盖台账：必须能区分「扫过且干净」与「一个都没扫」
_stats = {"objects": 0, "hits": 0, "dead": []}

def scan_text(text, src_label):
    hits = []
    for rid, rgx in RULES:
        for m in re.finditer(rgx, text):
            val = m.group(1)
            hits.append(f"  [{rid}] {src_label} -> {val[:4]}*** (len={len(val)})")
    _stats["hits"] += len(hits)
    return hits

def scan_commit_tree(commit):
    print(f"\n##### 扫描提交树 {commit} #####")
    if git("cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
        print("  [scan] 该提交不存在（历史被重写 / SHA 失效）—— 本目标覆盖 0 个对象")
        _stats["dead"].append(f"commit {commit}")
        return
    files = git("ls-tree", "-r", "--name-only", commit).stdout.splitlines()
    for f in files:
        try:
            content = git("show", f"{commit}:{f}").stdout or ""
        except Exception:
            continue
        if "\x00" in content[:2000]:
            continue
        _stats["objects"] += 1
        for h in scan_text(content, f):
            print(h)

def scan_path_history(path):
    print(f"\n##### 扫描路径历史 {path} #####")
    commits = [c for c in git("log", "--all", "--format=%H", "--", path).stdout.splitlines() if c]
    if not commits:
        print("  [scan] 该路径在全部历史中不存在 —— 本目标覆盖 0 个对象")
        _stats["dead"].append(f"path {path}")
        return
    for c in commits:
        try:
            content = git("show", f"{c}:{path}").stdout or ""
        except Exception:
            continue
        _stats["objects"] += 1
        for h in scan_text(content, f"{c[:8]}"):
            print(h)

if __name__ == "__main__":
    # 已知嫌疑点
    scan_commit_tree("a47e8e4")
    scan_path_history("SECURITY_AUDIT_REPORT.md")
    scan_path_history("config.json")

    n, hits, dead = _stats["objects"], _stats["hits"], _stats["dead"]
    print(f"\n##### 扫描结束：共扫描 {n} 个对象；失效目标 {len(dead)} 个；命中 {hits} 处 #####")
    if dead:
        print("  ⚠️ 以下目标已失效（覆盖为 0，勿当作「已扫且干净」）：", file=sys.stderr)
        for d in dead:
            print(f"     - {d}", file=sys.stderr)
    if n == 0:
        print("[scan] 零覆盖：一个对象都没扫到 → 拒绝给出结论", file=sys.stderr)
        sys.exit(2)
    sys.exit(1 if hits else 0)
