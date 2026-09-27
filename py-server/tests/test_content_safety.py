# -*- coding: utf-8 -*-
"""统一内容安全审核单测 —— shared/content_safety.py（此前 59% 覆盖）

审核链：本地敏感词（始终执行）→ 讯飞文本合规（有凭证才走，任何失败都降级）
→ 知识性错误检查（本地）。核心契约有两条，也正是本文件的断言重点：
  1. **永不抛异常** —— 安全审核不得把主流程打挂；
  2. **降级必须留痕** —— 合规服务不可用时要有审计记录，否则"以为审过了"。
"""

import types

import pytest

import shared.content_safety as cs


def _fake_compliance_result(*, success=True, passed=True, suggest="", hits=(), error=None):
    return types.SimpleNamespace(
        success=success, passed=passed, suggest=suggest, hits=list(hits), error=error
    )


@pytest.fixture
def audit_spy(monkeypatch):
    """记录审计调用（审计日志本身写文件，测试里只观察是否被触发）。"""
    calls = []
    monkeypatch.setattr(cs, "_audit_log", lambda **kw: calls.append(kw))
    return calls


@pytest.fixture
def no_llm_guard(monkeypatch):
    """默认：无敏感词命中、无幻觉告警、讯飞无凭证（绿色基线）。"""
    monkeypatch.setattr(cs, "filter_sensitive", lambda text: (text, []))
    monkeypatch.setattr(cs, "check_hallucination", lambda text: [])
    import db.xfyun_services as xs
    monkeypatch.setattr(xs, "has_credentials", lambda: False)


class TestBaseline:
    async def test_clean_text_passes_untouched(self, no_llm_guard):
        text = "TCP 三次握手依次是 SYN、SYN-ACK、ACK。"
        filtered, notes = await cs.audit_output(text, source="unit")
        assert filtered == text
        assert notes == []

    async def test_empty_text_short_circuits(self):
        assert await cs.audit_output("", source="unit") == ("", [])

    async def test_no_credentials_does_not_touch_compliance(self, no_llm_guard, monkeypatch):
        import db.xfyun_services as xs
        called = {"n": 0}
        monkeypatch.setattr(xs, "has_credentials", lambda: False)
        monkeypatch.setattr(xs, "check_compliance", lambda t: called.update(n=1))
        await cs.audit_output("正常内容", source="unit")
        assert called["n"] == 0, "无凭证时不得发起合规请求"


class TestSensitiveWords:
    async def test_hit_is_filtered_annotated_and_audited(self, monkeypatch, audit_spy):
        import db.xfyun_services as xs
        monkeypatch.setattr(xs, "has_credentials", lambda: False)
        monkeypatch.setattr(cs, "check_hallucination", lambda text: [])
        monkeypatch.setattr(cs, "filter_sensitive", lambda text: (text.replace("敏感", "**"), ["敏感"]))

        filtered, notes = await cs.audit_output("这里有敏感内容", source="chat")
        assert "敏感" not in filtered
        assert notes and "敏感词过滤" in notes[0]
        assert [c["action"] for c in audit_spy] == ["content_safety_sensitive"]
        assert audit_spy[0]["result"] == "blocked"

    async def test_no_hit_produces_no_audit(self, no_llm_guard, audit_spy):
        await cs.audit_output("干净内容", source="chat")
        assert audit_spy == []


class TestComplianceChannel:
    async def test_blocked_by_compliance_records_note(self, monkeypatch, audit_spy):
        import db.xfyun_services as xs
        monkeypatch.setattr(cs, "filter_sensitive", lambda text: (text, []))
        monkeypatch.setattr(cs, "check_hallucination", lambda text: [])
        monkeypatch.setattr(xs, "has_credentials", lambda: True)

        # check_compliance 是 async 接口 —— 替身必须也是协程，否则被视为异常而降级
        async def fake_compliance(text):
            return _fake_compliance_result(success=True, passed=False, suggest="涉政", hits=[1, 2])

        monkeypatch.setattr(xs, "check_compliance", fake_compliance)
        filtered, notes = await cs.audit_output("待审文本", source="resource")
        assert any("讯飞合规审核" in n for n in notes)
        assert any(c["action"] == "content_safety_compliance" for c in audit_spy)

    async def test_compliance_passed_adds_nothing(self, monkeypatch, audit_spy):
        import db.xfyun_services as xs
        monkeypatch.setattr(cs, "filter_sensitive", lambda text: (text, []))
        monkeypatch.setattr(cs, "check_hallucination", lambda text: [])
        monkeypatch.setattr(xs, "has_credentials", lambda: True)

        async def fake_compliance(text):
            return _fake_compliance_result()

        monkeypatch.setattr(xs, "check_compliance", fake_compliance)
        _, notes = await cs.audit_output("正常文本", source="resource")
        assert notes == []

    async def test_compliance_unavailable_degrades_and_audits(self, monkeypatch, audit_spy):
        """合规服务返回 success=False（不可用）→ 降级为本地过滤，且必须留痕。"""
        import db.xfyun_services as xs
        monkeypatch.setattr(cs, "filter_sensitive", lambda text: (text, []))
        monkeypatch.setattr(cs, "check_hallucination", lambda text: [])
        monkeypatch.setattr(xs, "has_credentials", lambda: True)

        async def fake_compliance(text):
            return _fake_compliance_result(success=False, error="service 500")

        monkeypatch.setattr(xs, "check_compliance", fake_compliance)
        _, notes = await cs.audit_output("待审文本", source="resource")
        actions = [c["action"] for c in audit_spy]
        assert "content_safety_compliance_degrade" in actions
        assert notes == [], "不可用属降级而非拦截，不应误报为内容问题"

    async def test_sync_compliance_stub_would_be_treated_as_failure(self, monkeypatch, audit_spy):
        """反向契约断言：若合规接口退化成同步实现，会被降级路径捕获而非静默通过。"""
        import db.xfyun_services as xs
        monkeypatch.setattr(cs, "filter_sensitive", lambda text: (text, []))
        monkeypatch.setattr(cs, "check_hallucination", lambda text: [])
        monkeypatch.setattr(xs, "has_credentials", lambda: True)
        monkeypatch.setattr(xs, "check_compliance", lambda text: _fake_compliance_result())
        _, notes = await cs.audit_output("待审文本", source="resource")
        assert notes == []
        assert any(c["result"] == "failure" for c in audit_spy), "接口形态不符必须留痕"

    async def test_compliance_exception_never_propagates(self, monkeypatch, audit_spy):
        """核心契约：讯飞调用抛异常时不得把主流程打挂，且要记录 failure。"""
        import db.xfyun_services as xs
        monkeypatch.setattr(cs, "filter_sensitive", lambda text: (text, []))
        monkeypatch.setattr(cs, "check_hallucination", lambda text: [])

        def boom():
            raise RuntimeError("credentials broken")

        monkeypatch.setattr(xs, "has_credentials", boom)
        filtered, notes = await cs.audit_output("文本", source="unit")
        assert filtered == "文本" and notes == []
        assert any(c["result"] == "failure" for c in audit_spy)


class TestHallucinationChannel:
    async def test_warnings_merged_into_notes(self, monkeypatch, audit_spy):
        import db.xfyun_services as xs
        monkeypatch.setattr(xs, "has_credentials", lambda: False)
        monkeypatch.setattr(cs, "filter_sensitive", lambda text: (text, []))
        monkeypatch.setattr(cs, "check_hallucination", lambda text: ["疑似知识性错误：三次握手是两次"])

        _, notes = await cs.audit_output("三次握手是两次交互", source="quiz")
        assert any("疑似知识性错误" in n for n in notes)
        assert any(c["action"] == "content_safety_hallucination" for c in audit_spy)

    async def test_hallucination_checked_on_filtered_text(self, monkeypatch):
        """必须检查"已过滤"的文本，否则敏感词残留会被下游看到。"""
        import db.xfyun_services as xs
        monkeypatch.setattr(xs, "has_credentials", lambda: False)
        monkeypatch.setattr(cs, "filter_sensitive", lambda text: ("已过滤文本", ["x"]))
        seen = {}
        monkeypatch.setattr(cs, "check_hallucination", lambda text: seen.update(text=text) or [])
        await cs.audit_output("原始文本", source="unit")
        assert seen["text"] == "已过滤文本"
