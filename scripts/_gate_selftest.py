#!/usr/bin/env python3
"""门禁自检的公共壳。

为什么需要：`xss_scan.py` 与 `a11y_scan.py` 的 `--selftest` 逻辑完全相同
（打印样本、对比期望与实际、给出 PASS/FAIL 与退出码），各自内联一份会被
pre-push 的克隆检测判为重复块（2026-10-29 实测命中）。

更实际的理由：自检的价值在于**格式与退出码语义统一**。如果某个门禁的
自检写成了「打印 FAIL 但 return 0」，它就成了新的假绿灯 —— 收在一处能从
结构上排除这种写法。

用法：
    from _gate_selftest import report_selftest
    return report_selftest(
        title="HTML 注入门禁 · 自检",
        expected=[3, 4, 5],
        got=got_lines,
        ok_msg="6 类注入点全部命中，2 类安全写法正确放行。",
        fail_msg="门禁已失效（可能漏报，也可能误报），不要相信它的 PASS。",
    )
"""

from __future__ import annotations

_WIDTH = 72


def report_selftest(
    title: str,
    expected: list[int],
    got: list[int],
    ok_msg: str,
    fail_msg: str,
) -> int:
    """统一的自检输出与退出码：一致返回 0，不一致返回 1（**不允许**返回 0）。"""
    print("=" * _WIDTH)
    print(title)
    print("=" * _WIDTH)
    print(f"样本应拦下行号: {expected}")
    print(f"实际拦下行号  : {got}")

    if got == expected:
        print(f"[PASS] {ok_msg}")
        return 0

    print(f"[FAIL] {fail_msg}")
    return 1
