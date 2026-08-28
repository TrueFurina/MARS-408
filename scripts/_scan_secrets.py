#!/usr/bin/env python3
# 一次性精准密钥扫描器：复用 .gitleaks.toml 的 4 条 XFyun 正则，
# 只在历史中找"真实密钥形状"的值（输出脱敏，避免打印明文）。
import subprocess, re, sys

REPO = "E:/Program/MARL/study-help-pro"

RULES = [
    ("xfyun-api-secret", r"""(?i)(?:xfyun|api[_-]?secret|secret)[^0-9A-Za-z]{0,20}["']?([A-Za-z0-9+/]{32,}={0,2})["']?"""),
    ("xfyun-api-key",    r"""(?i)(?:xfyun|api[_-]?key|key)[^0-9A-Za-z]{0,20}["']?([a-f0-9]{32})["']?"""),
    ("xfyun-app-id",     r"""(?i)(?:xfyun|app[_-]?id|appid)[^0-9A-Za-z]{0,20}["']?([a-f0-9]{8})["']?"""),
    ("xfyun-api-password", r"""(?i)(?:api[_-]?password|apipassword|password)[^0-9A-Za-z]{0,20}["']?([A-Za-z0-9]{10,30}:[A-Za-z0-9]{10,30})["']?"""),
]

def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, errors="ignore")

def scan_text(text, src_label):
    hits = []
    for rid, rgx in RULES:
        for m in re.finditer(rgx, text):
            val = m.group(1)
            hits.append(f"  [{rid}] {src_label} -> {val[:4]}*** (len={len(val)})")
    return hits

def scan_commit_tree(commit):
    print(f"\n##### 扫描提交树 {commit} #####")
    r = git("ls-tree", "-r", "--name-only", commit)
    files = r.stdout.splitlines()
    for f in files:
        try:
            content = git("show", f"{commit}:{f}").stdout or ""
        except Exception:
            continue
        if "\x00" in content[:2000]:
            continue
        for h in scan_text(content, f):
            print(h)

def scan_path_history(path):
    print(f"\n##### 扫描路径历史 {path} #####")
    r = git("log", "--all", "--format=%H", "--", path)
    commits = [c for c in r.stdout.splitlines() if c]
    for c in commits:
        try:
            content = git("show", f"{c}:{path}").stdout or ""
        except Exception:
            continue
        for h in scan_text(content, f"{c[:8]}"):
            print(h)

if __name__ == "__main__":
    # 已知嫌疑点
    scan_commit_tree("a47e8e4")
    scan_path_history("SECURITY_AUDIT_REPORT.md")
    scan_path_history("config.json")
    print("\n##### 扫描结束 #####")
