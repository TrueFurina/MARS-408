# -*- coding: utf-8 -*-
"""career 终评异步化后的测试等待助手

背景（2026-10-16 公网实测）
--------------------------------------------------------------------------
终评 = 六维 ECD 评估(max_tokens=2000) + 提升路径，两次串行 LLM 调用。
公网实测首题 26s / 单轮 20s，终评稳定超过发布平台网关的 ~60s 超时 ⇒
同步返回时用户拿到 504（后端其实算完了，随后 report 200）。

故 `end_session` / 末轮 `answer_turn` 改为：**立即回 generating，后台落库**。
这打破了测试里"end 之后报告必然就绪"的隐含前提，测试必须显式等它落库 ——
不等待 = 竞态红（CI 上偶发，本地几乎必绿，最难查的那种）。

用法
--------------------------------------------------------------------------
    from _career_report_wait import wait_report_ready
    client.post(f"/api/career/session/{sid}/end", json={"force": True})
    rep = wait_report_ready(client, sid)
"""
from __future__ import annotations

import time


def wait_report_ready(client, session_id: str, timeout: float = 20.0,
                      interval: float = 0.05) -> dict:
    """轮询 /report 直到后台终评落库（或失败/超时）。

    - 无 LLM 的测试环境走规则兜底，终评是纯本地计算，通常几十毫秒内完成；
    - 超时抛 AssertionError 而不是静默返回空报告 —— 空报告会让断言"恰好通过"。
    """
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = client.get(f"/api/career/session/{session_id}/report")
        if r.status_code == 200:
            last = r.json()
            status = last.get("status")
            if status == "failed":
                raise AssertionError(f"后台终评失败：{last.get('message')}")
            if status != "generating" and (last.get("assessment") or last.get("evidence_chain")):
                return last
        time.sleep(interval)
    raise AssertionError(
        f"报告在 {timeout}s 内未生成（终评异步化后的等待超时）：{str(last)[:200]}"
    )
