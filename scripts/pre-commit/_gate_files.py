#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""门禁脚本共用：变更文件集的来源解析（本地 / CI 两用）。

为什么需要这个模块
--------------------------------------------------------------------------
六道门禁里有几道默认从 **git 暂存区**（`git diff --cached`）取待检查文件。
这在 pre-commit 场景是对的，但一旦把门禁接到 CI 就会静默失效：

    actions/checkout 之后工作区 == HEAD，暂存区必然为空
    → `git diff --cached` 返回空列表
    → 门禁"什么都没检查"却返回 0（通过）
    → CI 上挂着一个永远绿的假闸门（比没有更糟：它制造了安全感）

处置：把「文件集从哪来」从各脚本内部解耦出来，由调用方注入。
约定通过一个环境变量传递，CI 编排器 `run_gates.py` 负责计算并设置它；
本地 pre-commit 不设置 → 各脚本回退到原来的暂存区行为，零影响。

为什么不各自实现一遍：这是一条**约定**（环境变量名 + 分隔方式 + 回退语义），
两处以上重复定义后必漂移（这一点在本仓库已经发生过一次：pre-commit.sh 修了
带空格路径的拆词坑，而 honesty_scan.py 里同款的 `.strip().split()` 直到
2026-10-03 才被发现）。
"""
from __future__ import annotations

import os
from pathlib import Path

# 注入变更文件集的两条通道。分隔均为**换行**（文件名含换行的极端情况不予考虑，
# 而不能用空格/NUL——前者会拆错带空格的路径，后者在 env 里不便读写）。
#
# 通道 1（小文件集）：环境变量。Windows 的环境变量块上限约 32K，实测编排器
#   在 20000 字符处设阈；本仓库一次"源码副本归档"提交含 852 个文件、路径拼起来
#   达 132102 字符，直接顶穿。
# 通道 2（大文件集）：临时文件。无长度限制，供编排器在 payload 超阈值时使用。
#
# 2019→2026-10-08：此前超限时编排器**静默放行**（`return 0`），即该门禁对超大
# commit 完全不检查 —— 又一处「零覆盖伪装成通过」。现改为文件通道，判定真正执行。
GATE_FILES_ENV = "GATE_FILES"
GATE_FILES_FILE_ENV = "GATE_FILES_FILE"


def _parse(raw: str) -> list[str]:
    """把「换行分隔的路径文本」解析为 posix 形态的列表。"""
    files = [f.strip().replace("\\", "/") for f in raw.splitlines()]
    return [f for f in files if f]


def injected_files() -> list[str] | None:
    """外部注入的变更文件集；未注入返回 None（调用方据此回退到暂存区）。

    返回的路径统一为 posix 形态（反斜杠转正斜杠），与各门禁的内部表示一致。
    空字符串表示**确实没有待检文件**（返回 `[]`），与"未注入"（`None`）语义不同。
    """
    fp = os.environ.get(GATE_FILES_FILE_ENV)
    if fp:
        # 读取失败**显式抛错**而非回退：编排器既然指定了文件通道，读不到就说明
        # 注入链路坏了。此时静默退到"空集"会让门禁在零覆盖下返回通过。
        try:
            raw = Path(fp).read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(
                f"{GATE_FILES_FILE_ENV} 指向的文件无法读取：{fp}（{exc}）"
            ) from exc
        return _parse(raw)

    raw = os.environ.get(GATE_FILES_ENV)
    if raw is None:
        return None
    return _parse(raw)
