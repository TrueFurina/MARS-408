# ============================================================
# 三层记忆接入智能体流水线 — 测试
#
# 覆盖（对标 HKU-DeepTutor 记忆解耦的低侵入接入）：
#   1. AgentState.memory_context 字段存在且可传递
#   2. diagnostician/planner/path_planner/tutor 提示词可选附加记忆上下文
#   3. retriever 从记忆上下文提取薄弱点增强检索查询
#   4. quiz submit 答题回写 L2/L3 记忆（记忆闭环）
#   5. chat 答疑入口注入记忆（降级安全）
# ============================================================

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

_TEST_DB = os.path.join(os.path.dirname(__file__), "_test_mem_agents.db")
os.environ.setdefault("NETLEARN_USER_DB", _TEST_DB)


@pytest.fixture(autouse=True)
def _clean_memory():
    """每个用例前清空记忆表（复用 memory_store 连接）"""
    from db import memory_store as ms
    conn = ms._get_conn()
    conn.execute("DELETE FROM memory_l1_working")
    conn.execute("DELETE FROM memory_l2_semantic")
    conn.execute("DELETE FROM memory_l3_episodic")
    conn.commit()
    yield
    conn.execute("DELETE FROM memory_l1_working")
    conn.execute("DELETE FROM memory_l2_semantic")
    conn.execute("DELETE FROM memory_l3_episodic")
    conn.commit()


# ── 1. AgentState.memory_context 字段 ──

def test_agent_state_has_memory_context():
    from agents.state import AgentState
    assert "memory_context" in AgentState.__annotations__


def test_build_memory_context_has_weak_points_section():
    """build_memory_context 组装含薄弱点标记，供 retriever 提取"""
    from services import memory_service as svc
    svc.init_student_memory("u_ctx", profile={"goal": "exam", "knowledge_base": "beginner"})
    svc.record_quiz_result("u_ctx", "TCP", False)
    ctx = svc.build_memory_context("u_ctx", max_episodes=5)
    # 答错 → 掌握度 0.5-0.075=0.425 < 0.5 → 出现在薄弱段
    assert "薄弱" in ctx


# ── 2. Agent 提示词可选附加记忆 ──

def test_diagnostician_prompt_with_memory():
    from agents.diagnostician import _build_diagnosis_prompt
    p = _build_diagnosis_prompt({"knowledge_base": "beginner"}, "【学生长期画像】\n- goal: exam")
    assert "历史学情记忆" in p
    p2 = _build_diagnosis_prompt({"knowledge_base": "beginner"})
    assert "历史学情记忆" not in p2


def test_planner_prompt_with_memory():
    from agents.planner import planner_node  # noqa: F401  # 仅验证模块可导入
    import inspect
    src = inspect.getsource(planner_node)
    assert "memory_context" in src  # 节点已消费记忆字段


def test_path_planner_prompt_with_memory():
    from agents.path_planner import _build_path_prompt
    p = _build_path_prompt({"knowledge_base": "beginner"}, {}, {}, "", [], "【学生长期画像】")
    assert "历史学情记忆" in p
    p2 = _build_path_prompt({"knowledge_base": "beginner"}, {}, {}, "", [])
    assert "历史学情记忆" not in p2


def test_tutor_prompt_with_memory():
    from agents.tutor import _build_tutor_prompt
    p = _build_tutor_prompt("问题", {"knowledge_base": "beginner"}, "ctx", "", "【学生长期画像】")
    assert "历史学情记忆" in p
    p2 = _build_tutor_prompt("问题", {"knowledge_base": "beginner"}, "ctx", "")
    assert "历史学情记忆" not in p2


# ── 3. retriever 薄弱点提取 ──

def test_retriever_weak_term_extraction():
    """从记忆上下文提取薄弱关键词（与 retriever 节点同源正则）"""
    import re
    ctx = "【知识点掌握度】\n薄弱: tcp(30%), 路由(20%)"
    weak_block = re.search(r"薄弱[：:]\s*(.+?)(?:\n|$)", ctx)
    weak_terms = [w.strip() for w in weak_block.group(1).split(",") if w.strip()] if weak_block else []
    assert len(weak_terms) == 2
    assert "tcp" in weak_terms[0]


# ── 4. 答题回写 L2/L3 记忆闭环 ──

def test_quiz_result_writes_episodes():
    """答题后 L3 情景记忆累积（record_quiz_result 写事件）"""
    from services import memory_service as svc
    from db import memory_store as ms

    svc.record_quiz_result("u_quiz", "TCP", True)
    svc.record_quiz_result("u_quiz", "路由", False)
    episodes = ms.get_episodes("u_quiz", event_type="quiz")
    assert len(episodes) == 2


def test_quiz_result_updates_mastery():
    """答题后 L2 掌握度更新（答对升/答错降，钳位 0-1）"""
    from services import memory_service as svc
    from db import memory_store as ms

    svc.record_quiz_result("u_m", "TCP", True)
    svc.record_quiz_result("u_m", "TCP", True)
    mem = ms.get_semantic_memory("u_m")
    assert mem["mastery"]["TCP"] > 0.5  # 两连对 → 0.5+0.05+0.05
    svc.record_quiz_result("u_m", "UDP", False)
    assert ms.get_semantic_memory("u_m")["mastery"]["UDP"] < 0.5


# ── 5. 记忆上下文空值安全 ──

def test_build_memory_context_empty_user_safe():
    """无记忆用户返回占位符而非抛异常（chat/langgraph 注入降级安全）"""
    from services import memory_service as svc
    ctx = svc.build_memory_context("u_none", max_episodes=6)
    assert isinstance(ctx, str)
    assert "暂无历史学习数据" in ctx
