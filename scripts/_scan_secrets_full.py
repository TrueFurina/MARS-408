#!/usr/bin/env python3
# 终极精准扫描：遍历全部历史提交的文本 blob（按 blob hash 去重），
# 复用 .gitleaks.toml 的 4 条 XFyun 正则，输出脱敏，定位任何真实密钥值。
import subprocess, re

REPO = "E:/Program/MARL/study-help-pro"
RULES = [
    ("xfyun-api-secret", r"""(?i)(?:xfyun|api[_-]?secret|secret)[^0-9A-Za-z]{0,20}["']?([A-Za-z0-9+/]{32,}={0,2})["']?"""),
    ("xfyun-api-key",    r"""(?i)(?:xfyun|api[_-]?key|key)[^0-9A-Za-z]{0,20}["']?([a-f0-9]{32})["']?"""),
    ("xfyun-app-id",     r"""(?i)(?:xfyun|app[_-]?id|appid)[^0-9A-Za-z]{0,20}["']?([a-f0-9]{8})["']?"""),
    ("xfyun-api-password", r"""(?i)(?:api[_-]?password|apipassword|password)[^0-9A-Za-z]{0,20}["']?([A-Za-z0-9]{10,30}:[A-Za-z0-9]{10,30})["']?"""),
]

def git(*a):
    return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True, errors="ignore")

cache = {}
hits = 0
commits = git("rev-list", "--all").stdout.splitlines()
print(f"待扫描提交数: {len(commits)}")
for ci, c in enumerate(commits):
    files = git("ls-tree", "-r", "--name-only", c).stdout.splitlines()
    for f in files:
        bh = git("rev-parse", f"{c}:{f}").stdout.strip()
        if not bh or bh in cache:
            continue
        try:
            content = git("cat-file", "-p", bh).stdout
        except Exception:
            cache[bh] = None
            continue
        cache[bh] = content
        if "\x00" in content[:2000]:
            continue
        for rid, rgx in RULES:
            for m in re.finditer(rgx, content):
                val = m.group(1)
                # 跳过明显占位
                if re.search(r"(?i)your[_-]?|xxx|redacted|\*{3,}", val):
                    continue
                hits += 1
                print(f"[{rid}] {c[:8]} | {f} | {val[:4]}*** (len={len(val)})")
    if (ci + 1) % 20 == 0:
        print(f"  ...已扫 {ci+1}/{len(commits)} 提交, 命中 {hits}")

print(f"\n##### 终极扫描结束：真实密钥值命中总数 = {hits} #####")
