# -*- coding: utf-8 -*-
"""career 分支测试 · 终评超时的防回归闸（防"静默退回规则兜底"）

为什么需要这道闸
--------------------------------------------------------------------------
2026-10-20 公网实测到一个**不报错**的退化：追问是真实 LLM 生成的，但六维
评估 `assessment_source=rule_fallback` —— 页面上只是把标签显示成"规则评估"，
没有任何错误提示，用户/评委完全看不出 AI 评估其实没跑。

根因：免费档 glm-4-flash 生成六维 JSON 实测 **64.2s**（返回仅 2461 字符，
慢在生成速度而非输出长度），而 `LLMProvider.text_completion` 默认 timeout=60
⇒ 稳定 ReadTimeout ⇒ `assess_session` 的 try/except 吞掉异常 → 规则兜底。

修复是给终评显式加长超时（`career_nodes.ASSESS_TIMEOUT`），而终评已后台异步、
不受发布平台 ~60s 网关超时限制，所以这个放宽是安全的。

本测试锁死的是**超时下限**：一旦有人把超时改回 60（或默认值回退），
线上会立刻退回规则兜底而不报错 —— 故必须是硬断言。
"""
import pytest

from agents import career_nodes


def test_assess_timeout_must_exceed_measured_llm_latency():
    """终评超时必须显著大于实测延迟（64.2s），否则必然超时兜底。"""
    assert career_nodes.ASSESS_TIMEOUT >= 90, (
        f"终评超时 {career_nodes.ASSESS_TIMEOUT}s 过小：免费档实测 64.2s，"
        "<=60s 会稳定超时并静默退回规则兜底"
    )


def test_improvement_timeout_must_exceed_default():
    assert career_nodes.IMPROVEMENT_TIMEOUT > 60


def test_assess_session_passes_explicit_timeout(monkeypatch):
    """assess_session 必须把加长后的超时**真的传下去**（改常量不算改完）。

    用探针替换 LLMProvider：只要调用没带 timeout=ASSESS_TIMEOUT，就是没接上。
    """
    import agents.career_nodes as nodes

    captured = {}

    class _FakeLLM:
        def __init__(self, *a, **kw):
            pass

        async def text_completion(self, system, user, temperature=0.2,
                                  max_tokens=2000, timeout=None, **kw):
            captured["timeout"] = timeout
            # 返回合法 JSON，避免走解析失败分支干扰本断言
            return '{"dimensions": {"expression": {"score": 4, "confidence": 0.8}}, "overall": 4.0}'

    class _FakeProviderModule:
        LLMProvider = _FakeLLM

    import sys
    monkeypatch.setitem(sys.modules, "db.llm_provider", _FakeProviderModule)

    import asyncio
    res = asyncio.run(nodes.assess_session(
        {"dimension_weights": {}, "bars_anchor": {}}, "答辩", "题目",
        [{"turn_index": 1, "question": "q", "answer": "a", "evidence": {}}],
    ))
    assert captured.get("timeout") == nodes.ASSESS_TIMEOUT, (
        f"assess_session 未传 ASSESS_TIMEOUT（实际传了 {captured.get('timeout')}）"
    )
    assert res.get("assessment_source") == "llm"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
