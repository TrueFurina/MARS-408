# -*- coding: utf-8 -*-
# ============================================================
# career_nodes · 两个 LLM 节点失败安全（fallback）单测
#
# 立论：career_nodes 每个节点都是 async 纯函数，契约是"LLM 失败安全兜底、
# 闭环不崩"。既有测试（test_career_evidence / test_career_assessment /
# test_career_p0）只覆盖 collect_evidence / assess_session / improvement 的
# 兜底，**没有**对下列两个真正发起 LLM 调用的节点做"LLM 抛异常"降级断言：
#
#   节点 1  build_scenario_script     —— 情景脚本生成（L97-133）
#   节点 3  generate_adversary_question —— 下一轮对抗问题（L239-269）
#
# 本文件 monkeypatch `db.llm_provider.LLMProvider.text_completion` 使其抛异常
# （模拟 LLM 全通道宕机），断言两节点降级到**确定性兜底**：不崩溃、字段完整、
# 且内容取自种子/规则（而非伪造成模型判断）。
#
# 运行：python -m pytest tests/test_career_nodes_fallback.py -q
# ============================================================

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from agents.career_nodes import build_scenario_script, generate_adversary_question


# career_nodes 失败安全属 P0（LLM 宕机不得击穿实训闭环），进 CI 必跑门禁。
pytestmark = pytest.mark.p0_regression


class _RaisingLLM:
    """替换 LLMProvider 的桩：任何 text_completion/chat 调用都抛异常。

    模拟"讯飞 X2 / DeepSeek / Qwen 三通道全部不可用"，用于验证节点兜底路径。
    """

    def __init__(self, *args, **kwargs):
        pass

    async def text_completion(self, *args, **kwargs):
        raise RuntimeError("simulated LLM outage（所有通道不可用）")

    async def chat(self, *args, **kwargs):
        raise RuntimeError("simulated LLM outage（所有通道不可用）")


@pytest.fixture()
def llm_down(monkeypatch):
    """把 db.llm_provider.LLMProvider 换成必抛异常的桩（节点内 `from ... import` 时生效）。"""
    monkeypatch.setattr("db.llm_provider.LLMProvider", _RaisingLLM)


# 一个最小但完整的情景种子（build_scenario_script 入参）
_SEED = {
    "title": "技术方案评审",
    "setting": "某公司答辩现场，评委轮番追问。",
    "student_role": "候选人",
    "interviewer_role": "技术面试官",
    "opening_question": "请先介绍你的方案与关键取舍。",
    "probe_tree": ["关键资源冲突时如何取舍", "风险与回滚预案是什么"],
    "focus_points": ["结构", "具体性"],
    "dimension_weights": {"problem_solving": 1.0, "expression": 1.0},
}


# ── 节点 1：情景脚本生成 ──

def test_build_scenario_script_falls_back_on_llm_failure(llm_down):
    """LLM 抛异常 → 用情景种子兜底，返回可开场的结构化脚本。"""
    result = asyncio.run(build_scenario_script(_SEED, "medium"))

    assert isinstance(result, dict), "兜底必须返回 dict（下游节点按 dict 取值）"
    # 兜底必须保留种子的可开场要素（不得丢失/伪造）
    assert result["opening_question"] == _SEED["opening_question"]
    assert result["probe_plan"] == _SEED["probe_tree"]
    assert result["dimension_weights"] == _SEED["dimension_weights"]
    assert result["setting"] == _SEED["setting"]
    # 结构完整性（下游 generate_adversary_question 依赖这些键）
    for key in ("student_role", "interviewer_role", "success_signals", "template_warnings"):
        assert key in result, f"兜底结构缺键: {key}"


# ── 节点 3：生成下一轮对抗问题 ──

def _script():
    return {
        "setting": _SEED["setting"],
        "interviewer_role": _SEED["interviewer_role"],
        "probe_plan": _SEED["probe_tree"],
    }


def test_generate_adversary_question_falls_back_on_llm_failure(llm_down):
    """LLM 抛异常 → 按 probe_plan 规则兜底提问，返回结构化问题（第 0 轮取 plan[0]）。"""
    result = asyncio.run(generate_adversary_question(_script(), [], "（学生作答）", "normal"))

    assert isinstance(result, dict)
    assert result["question"], "兜底问题不得为空"
    assert result["question"] == _SEED["probe_tree"][0], "normal 兜底应取 probe_plan[0]"
    assert result["mode"] == "normal"
    assert result["probe_dimension"] == "problem_solving"


def test_generate_adversary_question_catfish_fallback(llm_down):
    """catfish 模式兜底 → 使用高压反事实追问，mode 标记正确、不崩溃。"""
    result = asyncio.run(generate_adversary_question(_script(), [], "（学生作答）", "catfish"))

    assert result["mode"] == "catfish"
    assert result["question"], "应对抗追问不得为空"
    # _fallback_question 对 catfish 返回固定的极端反事实追问
    assert ("失效" in result["question"]) or ("成立" in result["question"]), result["question"]
