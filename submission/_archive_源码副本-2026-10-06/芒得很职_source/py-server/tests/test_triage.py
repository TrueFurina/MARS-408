# -*- coding: utf-8 -*-
"""M1 · Triage 分级路由单测（三评审集成·增量一）。

覆盖：低风险短路（寒暄/致谢/确认）、高风险分流（知识讲解/习题/机制）、
安全默认（空输入/无信号/指定课程/高难度）、triage_node 状态写入。
纯函数测试，无外部依赖。
"""
import pytest

from agents.triage import classify_request, triage_node, LEVEL_LOW, LEVEL_HIGH


class TestClassifyRequest:
    """classify_request 纯函数行为"""

    @pytest.mark.parametrize("text", [
        "你好", "您好", "谢谢老师", "感谢", "加油", "好的", "明白了", "收到",
        "嗯", "晚安", "在吗", "辛苦了",
    ])
    def test_low_social_short(self, text):
        """短寒暄/致谢/确认 → low"""
        r = classify_request(text)
        assert r.level == LEVEL_LOW
        assert r.reason

    @pytest.mark.parametrize("text", [
        "什么是TCP三次握手", "讲一下TCP和UDP的区别", "为什么TCP是可靠的",
        "请解释操作系统的进程调度机制", "来一道排序算法练习题", "帮我做这道考研真题",
        "TCP协议的详细工作原理", "408数据结构大题怎么解",
    ])
    def test_high_knowledge_requests(self, text):
        """知识讲解/习题/机制 → high"""
        r = classify_request(text)
        assert r.level == LEVEL_HIGH
        assert r.hit_high

    def test_empty_input_safe_default_high(self):
        """空输入 → 安全默认 high"""
        r = classify_request("")
        assert r.level == LEVEL_HIGH

    def test_no_signal_safe_default_high(self):
        """无明确信号（如"随便聊聊"）→ 安全默认 high"""
        r = classify_request("随便聊聊")
        assert r.level == LEVEL_HIGH

    def test_course_forces_high(self):
        """指定课程 → high（正式学习请求）"""
        r = classify_request("你好", course="computer_network")
        assert r.level == LEVEL_HIGH

    def test_difficulty_forces_high(self):
        """非 easy 难度 → high"""
        r = classify_request("你好", difficulty="hard")
        assert r.level == LEVEL_HIGH

    def test_topic_participates_judgement(self):
        """topic 参与判定：主题含高风险信号 → high"""
        r = classify_request("帮我看看", topic="什么是ARP协议")
        assert r.level == LEVEL_HIGH


class TestTriageNode:
    """triage_node LangGraph 节点状态写入"""

    def test_writes_high_state(self):
        state = {"user_request": "什么是TCP", "topic": "", "course": "",
                 "difficulty": "", "student_profile": {}}
        out = triage_node(dict(state))
        assert out["triage_level"] == LEVEL_HIGH
        assert out["triage_reason"]
        assert out["triage_hits"]["high"]

    def test_writes_low_state(self):
        state = {"user_request": "你好", "topic": "", "course": "",
                 "difficulty": "", "student_profile": {}}
        out = triage_node(dict(state))
        assert out["triage_level"] == LEVEL_LOW
        assert out["triage_reason"]

    def test_failure_safe_default_high(self, monkeypatch):
        """异常 → 安全默认 high，绝不中断流水线"""
        import agents.triage as triage_mod

        def boom(*a, **k):
            raise RuntimeError("classifier crash")
        monkeypatch.setattr(triage_mod, "classify_request", boom)
        state = {"user_request": "x", "topic": "", "course": "",
                 "difficulty": "", "student_profile": {}}
        out = triage_node(dict(state))
        assert out["triage_level"] == LEVEL_HIGH
        assert "安全默认 high" in out["triage_reason"]
