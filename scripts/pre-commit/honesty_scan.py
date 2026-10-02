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

# scan_text 每处理一行都要剥离一次引号，若在函数体内现场 re.compile，
# 每行一次构造 + 命中 re 内部缓存在大仓库（数万行）上是实打实的开销，
# 且与上面同形态的正则会变成**两处定义**（改一处忘另一处就漂移）。
# 故统一提为单一模块级常量，避免两处定义漂移。


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

# ────────────────────────────────────────────────────────────────────────────
# 精准文件级豁免（比目录豁免更窄）
#
# 设计取舍：宁可逐个文件放行并写明理由，也不放行整个 docs/ 或 py-server/ ——
# 目录级放行会让将来的**真实回流**无法被打到（pre-commit 只扫增量，靠的就是全量扫描兜底）。
# 每条豁免必须写清「为什么这个文件里的红线不是违规」，便于事后审计。
# ────────────────────────────────────────────────────────────────────────────
_REDLINE_SKIP_FILES = frozenset({
    # ── ① docs/ 中的「证伪记录」文档 ──
    # 这三处的红线都出现在「禁止使用 / 已实测证伪」的语境中被**引用**（例如
    # 「已把『检索成本降低 45%』列为 🔴 禁止使用」「实测数据直接证伪『成本降45%』」），
    # 是治理与证伪记录，不是对外宣称。判为违规等于惩罚正确的自我纠错。
    "docs/adr/ADR-019-jev-tech-selection.md",
    "docs/overview_jiaogai_preserved_2026-08-29.md",
    "docs/system_design.md",

    # ── ② py-server 中「500 条 LoRA 样本」相关 ──
    # 「仅需 500 条标注样本」这条红线禁的是：把具体的 500 挂在 **FrugalRAG 论文能力**名下
    # （原文只给低资源场景的概念论证，并无 500 这类数字，属无出处宣称）。
    # 而这里的 500 是**本项目自己 LoRA 少样本适配模块的工程设定**——数百条正是 LoRA 的常规量级，
    # 技术上完全可行，属合理设计目标，不是「挂在论文名下的无出处宣称」，故不适用该红线。
    #
    # ⚠️ 但必须同时记住事实状态（勿把「可行」当成「已达成」）：
    #    · data/labeled_samples.py 里真实标注样本目前仅 **20 条**（query 全唯一，非重复凑数）；
    #    · LoRAAdapter 目前**只有配置/模板接口**，无 peft/torch 依赖、无真实训练实现。
    #   ⇒ 若将来对外写成「已用 500 条完成 LoRA 学科适配」，则属**发生型证据造假**（从未跑通）。
    #     本豁免只放行「设计目标」语境下的数字，不放行「已达成」宣称；出现后者请手工拦下。
    "py-server/data/labeled_samples.py",
    "py-server/engines/frugal_rag_stop.py",
})


def _path_redline_exempt(path: str) -> bool:
    """该文件是否豁免对外红线检查（其中的红线出现是有意记录或规则定义，不得判为违规）。"""
    parts = Path(path).parts
    if set(parts) & set(_REDLINE_SKIP_ROOTS):
        return True
    if set(parts) & set(_REDLINE_SKIP_DIR_HINTS):
        return True
    # 文件级精准豁免：路径分隔符统一 normalize 成 '/'，兼容 Windows 反斜杠与 git 正斜杠两种来源
    try:
        return Path(path).as_posix() in _REDLINE_SKIP_FILES
    except Exception:
        return False


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
    exempt = _path_redline_exempt(path)
    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = _QUOTE_RE.sub("", line)
        for phrase in FORBIDDEN_PHRASES:
            if phrase in stripped:
                hits.append(f"{path}:{idx}: 假水位短语 {phrase!r}")
        for pat in FORBIDDEN_PATTERNS:
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
    """本次暂存的 A/C/M 文件（pre-commit 场景）。

    ⚠️ 必须按**行**读取，不能用 `.strip().split()`：后者按空白拆词，而本仓库
    确有带空格的路径（deliverables/MARS-408 考研…/…），会被拆成两个不存在的文件名
    从而**静默漏扫**——这正是 pre-commit.sh 里已经修过的同款坑。
    """
    import subprocess
    try:
        out = subprocess.check_output(
            ["git", "-c", "core.quotePath=false", "diff", "--cached",
             "--name-only", "--diff-filter=ACM"],
            stderr=subprocess.DEVNULL, text=True
        )
        return [Path(f) for f in out.splitlines() if f.strip()]
    except Exception:
        return []


def get_tracked_files() -> list:
    """全部已跟踪文件（CI / 人工全量场景）。

    为什么不 `Path('.').rglob('*')`：那样会遍历 node_modules / archive /
    deliverables 等数万乃至十几万个文件，实测 **4 分 50 秒仍未跑完**，直接接 CI
    必然超时，本地也无从人工触发全量体检。
    `git ls-files` 只返回版本库内的文件（这些目录基本未被跟踪），实测 ~56 秒扫完，
    且天然与「进仓库的东西」这一守护边界对齐：未跟踪文件本来也进不了 CI。
    git 不可用（非仓库 / 未装 git）时退回全树扫描，宁慢勿漏。
    """
    import subprocess
    try:
        out = subprocess.check_output(
            ["git", "-c", "core.quotePath=false", "ls-files"],
            stderr=subprocess.DEVNULL, text=True
        )
        files = [Path(f) for f in out.splitlines() if f.strip()]
        if files:
            return files
    except Exception:
        pass
    return [p for p in Path('.').rglob('*') if p.is_file()]


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--cached", action="store_true", help="扫描暂存区文件")
    parser.add_argument("--all", action="store_true",
                        help="扫描全部已跟踪文件（CI 全量模式；无参时亦为此行为）")
    parser.add_argument("files", nargs="*", help="指定文件列表")
    args = parser.parse_args()

    if args.cached:
        files = get_staged_files()
    elif args.files:
        files = [Path(f) for f in args.files]
    else:
        # 无参 = 全量：走 git ls-files（见 get_tracked_files 注释），
        # 不再用会拖垮 CI 的 rglob 全树。
        files = get_tracked_files()

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