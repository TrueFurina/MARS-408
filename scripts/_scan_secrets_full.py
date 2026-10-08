#!/usr/bin/env python3
# 终极精准扫描：遍历全部历史提交的文本 blob（按 blob hash 去重），
# 复用 .gitleaks.toml 的 4 条 XFyun 正则，输出脱敏，定位任何真实密钥值。
#
# 退出码：0 = 已扫到对象且无命中；1 = 命中真实密钥值；2 = 环境/零覆盖（fail-closed）。
#
# REPO 必须由本文件位置推导。此前硬编码为 "E:/Program/MARL/study-help-pro"：
#   在其它机器/CI 上所有 git 调用都失败 → commits 为空 → 直接打印
#   "真实密钥值命中总数 = 0"，把"一个对象都没扫"伪装成"历史干净"。
#   这正是本项目已修 9 次的「零覆盖 → 肯定性结论」失效形态，故此处 fail-closed。
import os, re, subprocess, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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

# fail-closed：拿不到提交列表时"0 命中"无意义，必须报环境错误而不是报干净。
if not commits:
    print(
        f"[scan] 零覆盖：{REPO} 未返回任何提交（git 失败 / 非 git 仓库）→ 拒绝给出结论",
        file=sys.stderr,
    )
    sys.exit(2)

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

print(
    f"\n##### 终极扫描结束：已扫 {len(commits)} 个提交 / {len(cache)} 个唯一 blob；"
    f"真实密钥值命中总数 = {hits} #####"
)
sys.exit(1 if hits else 0)
