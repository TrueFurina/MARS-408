# -*- coding: utf-8 -*-
"""pre-commit 门禁「唯一真源 ↔ 实际安装」一致性守护（2026-09-28 审查新增）

为什么需要它：门禁脚本放在 `scripts/pre-commit/*.py`，但真正触发它们的是 git 钩子，
而钩子本体**必须**落在 `git rev-parse --git-path hooks`（默认 `.git/hooks/pre-commit`）
—— 那个位置不受版本控制，CI 也没有跑这批门禁。于是存在两类**静默失效**：

  ① 新加了门禁脚本，却没人把它挂进钩子 → 脚本永远不跑，且没有任何报错；
  ② 钩子被手工改过，与入库真源分叉 → 本机跑的和仓库里写的不是一回事。

共同点与展示页那两条不变量一样：**违反时完全静默**。故用机器锁住。

真源：`scripts/pre-commit/pre-commit.sh`（入库）；安装器：`scripts/install_hooks.py`。
本文件全部断言都是纯文件读取（无网络、无第三方依赖、不依赖本机是否装过钩子），
跨环境恒定 —— 环境相关的东西不写死在这里。
"""

import re
import subprocess
from pathlib import Path

import pytest

# tests/ → py-server/ → 仓库根
REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL = REPO_ROOT / "scripts" / "pre-commit" / "pre-commit.sh"
GATE_DIR = REPO_ROOT / "scripts" / "pre-commit"

# 真源里对门禁脚本的引用（写全路径，故意不用 $变量 —— 那样机器就查不出来了）
GATE_REF_RE = re.compile(r"scripts/pre-commit/([A-Za-z0-9_]+\.py)")
# 形如 [1/6] 的进度标签
LABEL_RE = re.compile(r"\[(\d+)/(\d+)\]")
# 真源身份标记：安装器 --check 与本测试都靠它确认「看的是同一份东西」
MARKER = "NETLEARN-PRECOMMIT-HOOK"


def _canonical_text() -> str:
    # 真源缺失必须是 FAIL 而不是静默通过 —— 没有真源就没有一致性可查。
    assert CANONICAL.is_file(), f"门禁真源缺失，无法核对挂载关系: {CANONICAL}"
    return CANONICAL.read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    """行尾归一 + 去 BOM + 补尾换行，与 install_hooks.py 的 normalize 同口径。"""
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text if text.endswith("\n") else text + "\n"


def _referenced_gates() -> set:
    return set(GATE_REF_RE.findall(_canonical_text()))


def _actual_gate_scripts() -> set:
    """目录下真实存在的门禁脚本。

    以 `_` 开头的文件视为**内部辅助模块**（约定：不以 `_` 开头的才是独立门禁），
    不计入"必须被挂载"的集合，避免将来抽出公共工具时误报。
    """
    return {
        p.name
        for p in GATE_DIR.glob("*.py")
        if not p.name.startswith("_")
    }


def _installed_hook() -> Path:
    """实际安装位置。走 git（兼容 worktree / core.hooksPath），拿不到就按默认推。"""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--git-path", "hooks"],
            cwd=str(REPO_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            p = Path(out)
            return (p if p.is_absolute() else (REPO_ROOT / p)) / "pre-commit"
    except Exception:
        pass
    return REPO_ROOT / ".git" / "hooks" / "pre-commit"


# ---------------------------------------------------------------------------
# 1. 真源本身：是钩子 + 引用的门禁与目录实际一一对应
# ---------------------------------------------------------------------------


def test_canonical_hook_carries_identity_marker():
    """真源必须带身份标记，且确实是 shell 钩子（防止有人把说明文档放错位置）。"""
    text = _canonical_text()
    assert MARKER in text, f"真源缺少身份标记 {MARKER!r}，install_hooks.py --check 将无法识别"
    assert text.lstrip().startswith("#!"), "真源首行不是 shebang，无法作为钩子执行"


def test_referenced_gates_match_actual_gate_scripts():
    """真源引用的门禁集合，必须与 `scripts/pre-commit/` 下实际存在的脚本完全相等。

    两个方向都会静默出事：
      * 引用了不存在的脚本 → 每次提交都在调用一个不存在的文件（钩子会莫名拦下提交）；
      * 存在却没被引用 → 该门禁**永远不跑**，作者还以为它在生效。
    """
    referenced = _referenced_gates()
    actual = _actual_gate_scripts()

    missing = sorted(referenced - actual)
    unwired = sorted(actual - referenced)

    assert not missing, (
        f"真源引用了不存在的门禁脚本 {missing}；"
        "删脚本或改引用后必须让两者重新对齐（scripts/pre-commit/）"
    )
    assert not unwired, (
        f"这些门禁脚本没被真源挂载：{unwired}；"
        "新增门禁后必须同步写入 scripts/pre-commit/pre-commit.sh，否则它永远不会执行"
    )


def test_gate_labels_are_sequential_and_count_matches():
    """`[i/N]` 进度标签必须自洽：分母一致、序号 1..N 连续、出现次数等于 N，
    且 N 等于实际挂载的门禁道数。

    这条不是洁癖：修复前钩子实际挂了 **6** 道门禁，标签却写 `[1/5]…[5/5]`、
    `[5/5]` 还重复出现一次 —— 人肉一眼看不出门禁到底跑了几道，
    第 6 道（测试文件禁改）看上去像是"多余的一行"。
    """
    labels = [(int(a), int(b)) for a, b in LABEL_RE.findall(_canonical_text())]
    gates = _referenced_gates()

    assert labels, "真源里没有任何 [i/N] 标签，门禁道数无法机器核对"
    denominators = {b for _, b in labels}
    assert len(denominators) == 1, f"[i/N] 的分母不统一: {sorted(denominators)}（标签自述相互矛盾）"

    n = denominators.pop()
    assert n == len(gates), (
        f"标签自述 {n} 道门禁，实际挂载 {len(gates)} 道：{sorted(gates)}；"
        "自述与实际不符会让维护者漏掉/误判门禁"
    )
    assert [i for i, _ in labels] == list(range(1, n + 1)), (
        f"[i/N] 序号必须 1..{n} 且连续，实测 {[i for i, _ in labels]}"
    )
    assert len(labels) == n, f"[i/N] 标签出现 {len(labels)} 次，应为 {n} 次（重复即自述有误）"


# ---------------------------------------------------------------------------
# 2. 实际安装的钩子：不得与真源分叉
# ---------------------------------------------------------------------------


def test_installed_hook_matches_canonical_source():
    """已安装的钩子（行尾归一后）必须与真源逐字一致。

    新克隆的仓库没有钩子属正常状态（CI 也不会安装），此时 skip；
    一旦存在，它就是本机实际生效的门禁 —— 必须与仓库里写的同一份。
    """
    hook = _installed_hook()
    if not hook.is_file():
        pytest.skip(
            "本机未安装钩子（新克隆的正常状态）；"
            "安装：python scripts/install_hooks.py"
        )

    want = _normalize(_canonical_text())
    got = _normalize(hook.read_text(encoding="utf-8", errors="replace"))
    assert want == got, (
        f"已安装钩子与真源不一致（drift）: {hook}\n"
        "同步：python scripts/install_hooks.py（幂等，会先备份既有钩子）"
    )


def test_installed_hook_uses_lf_only():
    """已安装钩子不得含 CR。

    本仓库 core.autocrlf=true 且无 .gitattributes，脚本被检出时可能带 CRLF。
    shell 脚本带 `\\r` 会让参数变成 `secrets_scan.py\\r` → 「文件不存在」，
    表现是"每次提交都被门禁拦下，但报错和真实原因完全对不上"。
    """
    hook = _installed_hook()
    if not hook.is_file():
        pytest.skip("本机未安装钩子；安装：python scripts/install_hooks.py")

    raw = hook.read_bytes()
    assert b"\r" not in raw, (
        f"已安装钩子含 CR 字符: {hook}；"
        "用 python scripts/install_hooks.py 重新安装（会按 LF 写入）"
    )
