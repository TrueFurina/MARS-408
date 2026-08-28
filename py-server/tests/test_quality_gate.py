# ============================================================
# 单元测试：产物验收闸门 (Quality Gate) 纯逻辑
#
# 只覆盖 agents/quality_gate.py 的判定逻辑，不触发任何 LLM / DB / 网络。
# 可在 CI 干净环境直接 pytest 收集并运行。
#
# 覆盖点：
#   - 全部通过 (PASS)
#   - 各项硬性失败 (REJECT/FIX)
#   - 软性失败 (FIX)
#   - 重试耗尽 (REJECT/PASS降级)
#   - 空数据 / 默认值 (PASS)
#   - 异常降级 (PASS)
# ============================================================

import pytest

pytestmark = pytest.mark.unit

from agents.quality_gate import quality_gate_node, route_after_quality_gate
from agents.state import AgentState


# ── 辅助：构建最小 AgentState ──

def _make_state(**overrides) -> AgentState:
    """构建最小可用的 AgentState，默认值为全部通过的情况。"""
    defaults = {
        "messages": [],
        "user_request": "test",
        "student_profile": {},
        "topic": "test",
        "difficulty": "medium",
        "course": "computer_network",
        "diagnosis": None,
        "plan": None,
        "retrieved_chunks": None,
        "teacher_doc": "讲解内容",
        "quiz": "练习题内容",
        "media_plan": None,
        "extension": None,
        "mindmap": None,
        "code_practice": None,
        "ppt_outline": None,
        "video_script": None,
        "consensus": {"status": "passed"},
        "critic_report": None,
        "evidence_report": {
            "consistency_score": 95,
            "conflicts": [],
            "grounding_flagged": False,
            "resolved": 0,
            "grounding_score": 80,
        },
        "path_plan": None,
        "gate_result": None,
        "gate_verdict": "",
        "gate_reasons": [],
        "gate_retry_count": 0,
        "current_agent": "quality_gate",
        "error": None,
        "status": "gate_checking",
        "regenerate_round": 0,
    }
    defaults.update(overrides)
    return defaults


# ────────────────────────────────────────────────────────────
# 全部通过 (PASS)
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_all_pass():
    state = _make_state()
    result = await quality_gate_node(state)
    assert result.get("gate_verdict") == "pass"
    assert result.get("gate_passed") is True
    assert result.get("gate_retry_count") == 0


@pytest.mark.asyncio
async def test_gate_all_pass_no_soft_failures():
    state = _make_state(evidence_report={
        "consistency_score": 100,
        "conflicts": [],
        "grounding_flagged": False,
        "resolved": 0,
        "grounding_score": 90,
    })
    result = await quality_gate_node(state)
    assert result.get("gate_verdict") == "pass"
    assert "所有硬性指标和软性指标均通过" in result.get("gate_reasons", [])


# ────────────────────────────────────────────────────────────
# 硬性失败：一致性分数过低
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_consistency_too_low_first_retry():
    state = _make_state(evidence_report={
        "consistency_score": 25,
        "conflicts": [],
        "grounding_flagged": False,
        "resolved": 0,
        "grounding_score": 80,
    }, gate_retry_count=0)
    result = await quality_gate_node(state)
    assert result.get("gate_verdict") == "fix"
    assert result.get("gate_retry_count") == 1


@pytest.mark.asyncio
async def test_gate_consistency_too_low_retry_exhausted():
    state = _make_state(evidence_report={
        "consistency_score": 25,
        "conflicts": [],
        "grounding_flagged": False,
        "resolved": 0,
        "grounding_score": 80,
    }, gate_retry_count=2)
    result = await quality_gate_node(state)
    assert result.get("gate_verdict") == "reject"


# ────────────────────────────────────────────────────────────
# 硬性失败：高危冲突
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_high_severity_conflict():
    state = _make_state(evidence_report={
        "consistency_score": 90,
        "conflicts": [
            {"severity": "high", "description": "事实错误"},
            {"severity": "low", "description": "格式问题"},
        ],
        "grounding_flagged": False,
        "resolved": 0,
        "grounding_score": 80,
    }, gate_retry_count=0)
    result = await quality_gate_node(state)
    assert result.get("gate_verdict") == "fix"


@pytest.mark.asyncio
async def test_gate_high_severity_retry_exhausted():
    state = _make_state(evidence_report={
        "consistency_score": 90,
        "conflicts": [{"severity": "high", "description": "事实错误"}],
        "grounding_flagged": False,
        "resolved": 0,
        "grounding_score": 80,
    }, gate_retry_count=2)
    result = await quality_gate_node(state)
    assert result.get("gate_verdict") == "reject"


# ────────────────────────────────────────────────────────────
# 硬性失败：知识支撑度不足（幻觉标记）
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_grounding_flagged():
    state = _make_state(evidence_report={
        "consistency_score": 90,
        "conflicts": [],
        "grounding_flagged": True,
        "resolved": 0,
        "grounding_score": 25,
    }, gate_retry_count=0)
    result = await quality_gate_node(state)
    assert result.get("gate_verdict") == "fix"


# ────────────────────────────────────────────────────────────
# 硬性失败：Critic 审阅未通过
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_critic_not_passed():
    state = _make_state(consensus={"status": "flagged"})
    result = await quality_gate_node(state)
    assert result.get("gate_verdict") == "fix"


@pytest.mark.asyncio
async def test_gate_critic_regenerate():
    state = _make_state(consensus={"status": "regenerate"}, gate_retry_count=2)
    result = await quality_gate_node(state)
    assert result.get("gate_verdict") == "reject"


# ────────────────────────────────────────────────────────────
# 硬性失败：核心资源缺失
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_teacher_doc_empty():
    state = _make_state(teacher_doc="")
    result = await quality_gate_node(state)
    assert result.get("gate_verdict") == "fix"


@pytest.mark.asyncio
async def test_gate_quiz_empty():
    state = _make_state(quiz="")
    result = await quality_gate_node(state)
    assert result.get("gate_verdict") == "fix"


@pytest.mark.asyncio
async def test_gate_both_empty_retry_exhausted():
    state = _make_state(teacher_doc="", quiz="", gate_retry_count=2)
    result = await quality_gate_node(state)
    assert result.get("gate_verdict") == "reject"


# ────────────────────────────────────────────────────────────
# 软性失败：一致性分数在可修复范围
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_consistency_fixable():
    state = _make_state(evidence_report={
        "consistency_score": 50,
        "conflicts": [],
        "grounding_flagged": False,
        "resolved": 0,
        "grounding_score": 80,
    }, gate_retry_count=0)
    result = await quality_gate_node(state)
    assert result.get("gate_verdict") == "fix"


@pytest.mark.asyncio
async def test_gate_consistency_fixable_retry_exhausted_degrade():
    state = _make_state(evidence_report={
        "consistency_score": 50,
        "conflicts": [],
        "grounding_flagged": False,
        "resolved": 0,
        "grounding_score": 80,
    }, gate_retry_count=2)
    result = await quality_gate_node(state)
    assert result.get("gate_verdict") == "pass"


# ────────────────────────────────────────────────────────────
# 软性失败：有可消解冲突
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_resolved_conflicts():
    state = _make_state(evidence_report={
        "consistency_score": 95,
        "conflicts": [],
        "grounding_flagged": False,
        "resolved": 3,
        "grounding_score": 80,
    }, gate_retry_count=0)
    result = await quality_gate_node(state)
    assert result.get("gate_verdict") == "fix"


# ────────────────────────────────────────────────────────────
# 空数据 / 默认值
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_empty_evidence_report():
    state = _make_state(evidence_report={})
    result = await quality_gate_node(state)
    assert result.get("gate_verdict") == "pass"


@pytest.mark.asyncio
async def test_gate_no_evidence_report():
    state = _make_state(evidence_report=None)
    result = await quality_gate_node(state)
    assert result.get("gate_verdict") == "pass"


# ────────────────────────────────────────────────────────────
# 异常降级
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_exception_fail_open():
    state = _make_state(evidence_report={"consistency_score": "bad_value"})
    result = await quality_gate_node(state)
    assert result.get("gate_verdict") == "pass"


# ────────────────────────────────────────────────────────────
# 路由函数测试
# ────────────────────────────────────────────────────────────

def test_route_pass():
    state = _make_state(gate_verdict="pass")
    assert route_after_quality_gate(state) == "path_planner"


def test_route_fix():
    state = _make_state(gate_verdict="fix")
    assert route_after_quality_gate(state) == "generator_cluster"


def test_route_reject():
    state = _make_state(gate_verdict="reject")
    assert route_after_quality_gate(state) == "__end__"


def test_route_default():
    state = _make_state(gate_verdict="")
    assert route_after_quality_gate(state) == "__end__"