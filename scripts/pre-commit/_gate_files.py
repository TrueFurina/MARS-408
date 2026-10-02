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

# 注入变更文件集的环境变量。分隔：**换行**（文件名含换行的极端情况不予考虑，
# 而不能用空格/NUL——前者会拆错带空格的路径，后者在 env 里不便读写）。
GATE_FILES_ENV = "GATE_FILES"


def injected_files() -> list[str] | None:
    """外部注入的变更文件集；未注入返回 None（调用方据此回退到暂存区）。

    返回的路径统一为 posix 形态（反斜杠转正斜杠），与各门禁的内部表示一致。
    """
    raw = os.environ.get(GATE_FILES_ENV)
    if raw is None:
        return None
    files = [f.strip().replace("\\", "/") for f in raw.splitlines()]
    return [f for f in files if f]
