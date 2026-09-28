#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诚实口径扫描器 — pre-commit 门禁
用法：python scripts/pre-commit/honesty_scan.py [--cached] [文件列表...]
退出码：0=通过，1=命中假水位（fail-closed）

规则来源：西湖论剑 CTF-Agent 诚实口径扫描器
核心原则：平台 accepted=0 时，任何"解出数递增/真实解出 flag/自主X/X"均为假水位

此外本文件还承载 **MARS-408 对外口径红线**（见下方 _EXTERNAL_REDLINE_PATTERNS）：
对**已被实测证伪/无据**的对外宣称做 fail-closed 拦截，防止它们从归档快照回流。
"""
import re
import sys
from pathlib import Path

# 命中即报错的短语（历史违规样本）
FORBIDDEN_PHRASES = (
    "冲第一", "真实水位 89%", "真实水位 92%", "真实水位 100%",
    "自主 7/7", "将功补过", "解出数提升",
    "5→13", "13→15", "15→16", "16→26",
    "解出数 16", "解出数 26",
)

# 命中即报错的正则
FORBIDDEN_PATTERNS = (
    re.compile(r"解出数\s*\d+\s*→\s*\d+"),
    re.compile(r"\+\d+\s*真实解出"),
    re.compile(r"真实解出[^。\n]*flag"),
)

# 引号包裹的内容是「提及」非「使用」，剥离后再匹配
_QUOTE_RE = re.compile("「[^」]*」|『[^』]*』|\"[^\"]*\"|'[^']*'")


# ============================================================================
# MARS-408 对外口径红线：已被实测证伪 / 无证据支撑的宣称，命中即 fail-closed。
#
# 出处与判定依据：deliverables/engineering-assurance/metrics-integrity-audit-2026-08-29.md
#   - 「检索成本降低 45%」：实测 token −0.14%（基本持平）、延迟 −3.59%（略降）→ 证伪
#   - 「仅需 500 条标注样本」：FrugalRAG 原文只给**低资源场景**概念论证，无 500/200 这类数字
#   - 「GOMARL 升 15%」：同批被判 🔴
#
# 为什么要落成机器拦截：这些宣称删掉后**反复回流**。2026-09-28 又在活动代码
# src/views/ShowcaseView.vue 里发现了「检索成本降低 45%」（7 月已删、8 月核过零残留），
# 而两份归档快照里至今仍原样写着它。只靠人工记忆挡不住。
#
# 作用域：**仅活动代码**。豁免三类路径（这些地方出现红线是"记录/定义"，不是"使用"）：
#   ① deliverables/ submission/ —— 归档快照与治理文档（把红线当反面清单引用）；
#   ② .workbuddy/ —— 内部记忆，记载"哪些数字被禁"；
#   ③ **规则定义文件自身**（scripts/pre-commit/ 下的钩子）—— 它必须把红线写成注释与正则字面量，
#      否则无从匹配。本文件自己加规则时就被自己拦下来过一次（每组规则都免不了这个自指），
#      故对规则目录整体豁免。
# ============================================================================
_EXTERNAL_REDLINE_PATTERNS = (
    re.compile(r"检索成本降低\s*45\s*%"),
    re.compile(r"检索成本\s*降低\s*45"),
    re.compile(r"成本降\s*45\s*%"),
    re.compile(r"成本降低\s*45\s*%"),
    re.compile(r"仅需\s*500\s*条"),
    re.compile(r"500\s*条标注样本"),
    re.compile(r"(?:GOMARL|GoMARL)\s*升\s*15\s*%"),
)

# 上述三类豁免：归档/记忆根目录 + 规则定义目录
_REDLINE_SKIP_ROOTS = ("deliverables", "submission", ".workbuddy")
_REDLINE_SKIP_DIR_HINTS = ("pre-commit",)


def _path_redline_exempt(path: str) -> bool:
    """该文件是否豁免对外红线检查（其中的红线出现是有意记录或规则定义，不得判为违规）。"""
    parts = Path(path).parts
    if set(parts) & set(_REDLINE_SKIP_ROOTS):
        return True
    return bool(set(parts) & set(_REDLINE_SKIP_DIR_HINTS))


# 排除目录
_SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", "dist", "build"}
_SKIP_PREFIX = ("_archive", "race_attachments", "work_web", "platform_downloads")


def is_skipped(path: Path) -> bool:
    parts = set(path.parts)
    if parts & {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", "dist", "build"}:
        return True
    for part in path.parts:
        if part.startswith(_SKIP_PREFIX):
            return True
    return False


def scan_text(text: str, path: str = "") -> list:
    hits = []
    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = re.sub(r"「[^」]*」|『[^』]*』|\"[^\"]*\"|'[^']*'", "", line)
        for phrase in ("冲第一", "真实水位 89%", "真实水位 92%", "真实水位 100%",
                       "自主 7/7", "将功补过", "解出数提升",
                       "5→13", "13→15", "15→16", "16→26",
                       "解出数 16", "解出数 26"):
            if phrase in stripped:
                hits.append(f"{path}:{idx}: 假水位短语 {phrase!r}")
        for pat in (re.compile(r"解出数\s*\d+\s*→\s*\d+"),
                    re.compile(r"\+\d+\s*真实解出"),
                    re.compile(r"真实解出[^。\n]*flag")):
            if pat.search(stripped):
                hits.append(f"{path}:{idx}: 假水位正则 {pat.pattern!r}")

        # ⚠️ 对外红线必须匹配**原始行**，不能用 stripped（引号剥离后的文本）：
        #    展示页正是把该宣称写在 JS 单引号字符串里（desc: '...检索成本降低 45%'），
        #    一旦走剥离，整条 JS 串会被当成"引用"抹掉 —— 拦截等于虚设。
        #    宁可承担少量误报，也不要让红线漏过去。
        if not _path_redline_exempt(path):
            for pat in _EXTERNAL_REDLINE_PATTERNS:
                if pat.search(line):
                    hits.append(f"{path}:{idx}: 已证伪的对外红线 {pat.pattern!r}")
    return hits


def scan_file(filepath: Path) -> list:
    if is_skipped(filepath):
        return []
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return []
    return scan_text(content, str(filepath))


def get_staged_files() -> list:
    import subprocess
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            stderr=subprocess.DEVNULL, text=True
        )
        return [Path(f) for f in out.strip().split() if f]
    except Exception:
        return []


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--cached", action="store_true", help="扫描暂存区文件")
    parser.add_argument("files", nargs="*", help="指定文件列表")
    args = parser.parse_args()

    if args.cached:
        files = get_staged_files()
    elif args.files:
        files = [Path(f) for f in args.files]
    else:
        files = [p for p in Path('.').rglob('*') if p.is_file()]

    all_hits = []
    for f in files:
        if any(ign in str(f) for ign in ['.git', '__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build']):
            continue
        hits = scan_file(Path(f))
        all_hits.extend(hits)

    if all_hits:
        for h in all_hits:
            print(f"❌ {h}")
        return 1

    print("✅ 诚实口径扫描通过")
    return 0


if __name__ == '__main__':
    import re
    sys.exit(main())