# -*- coding: utf-8 -*-
"""SAGE 分级提示 (Graded Hint) 单测。

覆盖：三级提示定义与 system prompt 构建、保留答案闸门（泄漏拦截/干净放行/
非法级别不校验）、graded_hint_answer 主流程（fake LLM 注入）、tutor_answer
的 hint_level 路由（默认行为不变）、API 契约（hint_level 越界 422）。

纯函数为主，LLM 一律 fake 注入，不触真实四通道。
"""
import pytest

from agents.graded_hint import (
    HINT_LEVELS,
    WITHHOLDING_FALLBACK,
    build_hint_system_prompt,
    enforce_withholding,
    graded_hint_answer,
    withholding_check,
)
from agents import tutor as tutor_mod


# ============================================================
# 提示层级定义
# ============================================================

class TestHintLevels:
    def test_three_levels_defined(self):
        """1/2/3 三级齐全, 且各级含 name/en/rule"""
        assert sorted(HINT_LEVELS.keys()) == [1, 2, 3]
        for lv in HINT_LEVELS.values():
            assert lv["name"] and lv["en"] and lv["rule"]

    def test_level_names(self):
        """级别名: 1=方向 2=前置 3=局部"""
        assert HINT_LEVELS[1]["name"] == "方向"
        assert HINT_LEVELS[2]["name"] == "前置"
        assert HINT_LEVELS[3]["name"] == "局部"

    def test_level3_rule_mentions_last_step(self):
        """局部级规则必须明确『停在最后一步之前』——保留答案的核心"""
        assert "最后一步" in HINT_LEVELS[3]["rule"]


# ============================================================
# system prompt 构建
# ============================================================

class TestBuildSystemPrompt:
    @pytest.mark.parametrize("lv", [1, 2, 3])
    def test_prompt_contains_level_rule(self, lv):
        """各级 prompt 均含对应级别规则与答案保留铁律"""
        p = build_hint_system_prompt(lv)
        assert HINT_LEVELS[lv]["name"] in p
        assert HINT_LEVELS[lv]["rule"] in p
        assert "答案保留" in p

    def test_invalid_level_raises(self):
        with pytest.raises(ValueError):
            build_hint_system_prompt(0)
        with pytest.raises(ValueError):
            build_hint_system_prompt(4)


# ============================================================
# 保留答案闸门
# ============================================================

class TestWithholdingCheck:
    @pytest.mark.parametrize("leak", [
        "推导到这里, 最终答案是 42。",
        "答案是：RSA 的安全性基于大数分解。",
        "答案为：O(n log n)。",
        "完整证明如下：第一步……",
        "所以答案为 128。",
        "综上所述，答案是 B。",
    ])
    def test_leak_caught(self, leak):
        """典型泄漏句式必须全部命中"""
        r = withholding_check(leak, 3)
        assert not r["ok"]
        assert r["violations"]

    @pytest.mark.parametrize("clean", [
        "## 卡点定位\n\n你可能卡在归约的方向上——想想从哪个问题归约过来。",
        "## 前置提示\n\n先回顾费马小定理: 若 p 为素数且 gcd(a,p)=1, 则 a^(p-1) ≡ 1 (mod p)。",
        "## 局部提示\n\n第二步可以把模幂拆成平方-乘链, 但最后一步需要你自己完成。",
        "如果学生问所以答案是什么, 提醒他自己收尾。",  # 引用规则本身不算泄漏
    ])
    def test_clean_passes(self, clean):
        """正常提示文本放行"""
        r = withholding_check(clean, 3)
        assert r["ok"], f"误拦: {r['violations']}"

    def test_invalid_level_no_check(self):
        """闸门只对 1/2/3 生效; 非法级别不校验（供普通答疑复用路径）"""
        r = withholding_check("最终答案是 42", 0)
        assert r["ok"] and r["violations"] == []


class TestEnforceWithholding:
    async def test_leak_replaced(self):
        """泄漏文本 → 整体替换为收束文案"""
        out = await enforce_withholding("推导完成, 最终答案是 42。", 3)
        assert out == WITHHOLDING_FALLBACK

    async def test_clean_unchanged(self):
        """干净文本原样返回"""
        src = "## 局部提示\n\n先拆平方-乘链。"
        assert await enforce_withholding(src, 3) == src


# ============================================================
# 主流程 (fake LLM 注入)
# ============================================================

class _FakeLLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = []

    async def text_completion(self, system_prompt, user_prompt, **kw):
        self.calls.append({"system": system_prompt, "user": user_prompt, **kw})
        return self.reply


class TestGradedHintAnswer:
    async def test_returns_structure_and_withheld(self):
        llm = _FakeLLM("## 卡点定位\n\n想想归约方向。")
        r = await graded_hint_answer(
            "如何证明 RSA 正确性?", {"knowledge_base": "beginner"}, 2, llm=llm
        )
        assert r["hint_level"] == 2
        assert r["hint_level_name"] == "前置"
        assert r["withheld"] is True
        assert "答案保留" in llm.calls[0]["system"]

    async def test_gate_blocks_leaking_llm(self):
        """LLM 不守规矩直接给答案 → 闸门替换"""
        llm = _FakeLLM("好, 最终答案是 42。")
        r = await graded_hint_answer(
            "这道题答案是啥?", {}, 3, llm=llm
        )
        assert r["answer"] == WITHHOLDING_FALLBACK

    async def test_invalid_level_raises(self):
        with pytest.raises(ValueError):
            await graded_hint_answer("q", {}, 5, llm=_FakeLLM("x"))

    async def test_llm_failure_degrades(self):
        class _BoomLLM:
            async def text_completion(self, *a, **kw):
                raise RuntimeError("llm down")

        r = await graded_hint_answer("q", {}, 1, llm=_BoomLLM())
        assert "提示生成失败" in r["answer"]
        assert r["withheld"] is True

    async def test_temperature_lower_than_tutor(self):
        """提示模式温度应低于答疑(0.5): 提示更收敛"""
        llm = _FakeLLM("ok")
        await graded_hint_answer("q", {}, 1, llm=llm)
        assert llm.calls[0]["temperature"] < 0.5


# ============================================================
# tutor_answer 路由
# ============================================================

class TestTutorAnswerRouting:
    async def test_hint_level_routes_to_graded(self, monkeypatch):
        """hint_level 非 None → 路由到 graded_hint_answer, 不走原答疑"""
        routed = {}

        async def _fake_graded(**kw):
            routed.update(kw)
            return {
                "answer": "hint", "question": kw["question"],
                "hint_level": kw["hint_level"], "hint_level_name": "方向",
                "withheld": True, "retrieved_context": "",
            }

        probe = {"tutor_body_entered": False}

        async def _boom(*a, **kw):  # 原答疑路径若被走到, 直接暴露
            probe["tutor_body_entered"] = True
            raise AssertionError("不应进入普通答疑路径")

        monkeypatch.setattr("agents.graded_hint.graded_hint_answer", _fake_graded)
        # tutors 检索与 LLM 都不该被触达: 让 frugal_rag 抛错即可暴露
        monkeypatch.setattr(tutor_mod, "frugal_rag", None)

        r = await tutor_mod.tutor_answer("q", {}, hint_level=1)
        assert r["withheld"] is True and r["hint_level"] == 1
        assert routed["hint_level"] == 1
        assert probe["tutor_body_entered"] is False

    async def test_default_mode_unchanged(self, monkeypatch):
        """不传 hint_level → 行为与原先一致（走检索+LLM, 不碰 graded）"""
        graded_called = {"n": 0}

        async def _no_graded(**kw):
            graded_called["n"] += 1
            raise AssertionError("默认模式不应路由到分级提示")

        monkeypatch.setattr("agents.graded_hint.graded_hint_answer", _no_graded)

        class _FakeRAG:
            async def retrieve(self, q, course=None):
                return []

        monkeypatch.setattr(tutor_mod, "frugal_rag", _FakeRAG())

        class _FakeLLM:
            async def text_completion(self, sys_p, user_p, **kw):
                return "---TUTOR_START---\n\n## 核心解答\n\nok"

        monkeypatch.setattr(tutor_mod, "LLMProvider", _FakeLLM)

        r = await tutor_mod.tutor_answer("q", {})
        assert "ok" in r["answer"]
        assert graded_called["n"] == 0


# ============================================================
# API 契约 (仅校验层; 完整流程由 agents 层用例覆盖)
# ============================================================

class TestApiContract:
    def _client(self):
        from fastapi.testclient import TestClient
        import main

        return TestClient(main.app)

    def test_hint_level_out_of_range_422(self):
        """hint_level=0/4 → pydantic 校验拒绝"""
        client = self._client()
        for bad in (0, 4, -1):
            resp = client.post("/api/tutor/answer", json={"question": "q", "hint_level": bad})
            assert resp.status_code == 422, f"hint_level={bad} 应 422"

    def test_default_request_schema_unchanged(self):
        """不传 hint_level 的请求体仍合法（向后兼容）——仅验证校验层放行到 401/404 之外的业务逻辑"""
        from api.tutor import TutorRequest
        req = TutorRequest(question="q")
        assert req.hint_level is None
        req2 = TutorRequest(question="q", hint_level=2)
        assert req2.hint_level == 2
