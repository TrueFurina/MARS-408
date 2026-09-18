# ============================================================
# L1/L2/L3 三层学情记忆 — 单元测试
#
# 覆盖：
#   L1 工作记忆：写入/读取/合并/TTL过期清理/清空
#   L2 语义记忆：画像合并/掌握度更新/薄弱点去重
#   L3 情景记忆：追加/批量/查询/过期清理
#   聚合查询：get_full_memory / build_memory_context
# ============================================================

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

# 隔离测试：使用临时 DB 文件，避免污染真实用户库
_TEST_DB = os.path.join(os.path.dirname(__file__), "_test_memory.db")
os.environ.setdefault("NETLEARN_USER_DB", _TEST_DB)


@pytest.fixture(autouse=True)
def _clean_db():
    """每个用例前重置 memory 表（复用 user_store 连接，建表幂等）"""
    from db import memory_store as ms
    conn = ms._get_conn()
    conn.execute("DELETE FROM memory_l1_working")
    conn.execute("DELETE FROM memory_l2_semantic")
    conn.execute("DELETE FROM memory_l3_episodic")
    conn.commit()
    yield
    # 清理测试残留（保留表结构）
    conn.execute("DELETE FROM memory_l1_working")
    conn.execute("DELETE FROM memory_l2_semantic")
    conn.execute("DELETE FROM memory_l3_episodic")
    conn.commit()


# ── L1 工作记忆 ──

def test_l1_save_and_get():
    from db import memory_store as ms
    ms.save_working_memory("u_test", "s1", {"current_topic": "TCP三次握手", "focus": "握手顺序"})
    ctx = ms.get_working_memory("u_test", "s1")
    assert ctx is not None
    assert ctx["current_topic"] == "TCP三次握手"


def test_l1_merge_keeps_old_fields():
    from db import memory_store as ms
    ms.save_working_memory("u_test", "s1", {"current_topic": "TCP"})
    merged = ms.merge_working_memory("u_test", "s1", {"focus": "拥塞控制"})
    assert merged["current_topic"] == "TCP"
    assert merged["focus"] == "拥塞控制"


def test_l1_ttl_expiry():
    from db import memory_store as ms
    ms.save_working_memory("u_test", "s1", {"current_topic": "TCP"}, ttl_seconds=1)
    assert ms.get_working_memory("u_test", "s1") is not None
    time.sleep(1.2)
    assert ms.get_working_memory("u_test", "s1") is None


def test_l1_clear():
    from db import memory_store as ms
    ms.save_working_memory("u_test", "s1", {"current_topic": "TCP"})
    ms.clear_working_memory("u_test", "s1")
    assert ms.get_working_memory("u_test", "s1") is None


# ── L2 语义记忆 ──

def test_l2_save_and_get():
    from db import memory_store as ms
    ms.save_semantic_memory(
        "u_test",
        profile={"knowledge_base": "beginner", "goal": "exam"},
        mastery={"tcp": 0.3},
        weak_points=["TCP"],
    )
    mem = ms.get_semantic_memory("u_test")
    assert mem["profile"]["goal"] == "exam"
    assert mem["mastery"]["tcp"] == 0.3
    assert "TCP" in mem["weak_points"]


def test_l2_merge_profile():
    from db import memory_store as ms
    ms.save_semantic_memory("u_test", profile={"knowledge_base": "beginner"})
    ms.save_semantic_memory("u_test", profile={"goal": "exam"})
    mem = ms.get_semantic_memory("u_test")
    assert mem["profile"]["knowledge_base"] == "beginner"
    assert mem["profile"]["goal"] == "exam"


def test_l2_weak_points_dedup():
    from db import memory_store as ms
    ms.save_semantic_memory("u_test", weak_points=["TCP", "路由"])
    ms.save_semantic_memory("u_test", weak_points=["TCP", "拥塞控制"])
    mem = ms.get_semantic_memory("u_test")
    assert mem["weak_points"].count("TCP") == 1
    assert set(mem["weak_points"]) == {"TCP", "路由", "拥塞控制"}


def test_l2_update_mastery_clamp():
    from db import memory_store as ms
    ms.update_mastery("u_test", "tcp", 1.5)  # 超上限 → 钳位
    assert ms.get_semantic_memory("u_test")["mastery"]["tcp"] == 1.0
    ms.update_mastery("u_test", "udp", -0.5)  # 超下限 → 钳位
    assert ms.get_semantic_memory("u_test")["mastery"]["udp"] == 0.0


# ── L3 情景记忆 ──

def test_l3_append_and_query():
    from db import memory_store as ms
    ms.append_episode("u_test", "quiz", {"topic": "TCP", "correct": True})
    ms.append_episode("u_test", "quiz", {"topic": "UDP", "correct": False})
    episodes = ms.get_episodes("u_test")
    assert len(episodes) == 2
    assert episodes[0]["event_type"] == "quiz"  # 倒序，最新的在前


def test_l3_filter_by_type():
    from db import memory_store as ms
    ms.append_episode("u_test", "quiz", {"topic": "TCP"})
    ms.append_episode("u_test", "behavior", {"event_type": "dwell"})
    quiz_only = ms.get_episodes("u_test", event_type="quiz")
    assert len(quiz_only) == 1
    assert quiz_only[0]["event_type"] == "quiz"


def test_l3_batch():
    from db import memory_store as ms
    ms.append_episodes_batch("u_test", "quiz", [
        {"topic": "TCP", "correct": True},
        {"topic": "UDP", "correct": False},
        {"topic": "IP", "correct": True},
    ])
    assert ms.count_episodes("u_test") == 3


# ── 聚合与服务层 ──

def test_get_full_memory():
    from db import memory_store as ms
    ms.save_semantic_memory("u_test", profile={"goal": "exam"})
    ms.save_working_memory("u_test", "s1", {"current_topic": "TCP"})
    ms.append_episode("u_test", "quiz", {"topic": "TCP", "correct": True})
    full = ms.get_full_memory("u_test", "s1")
    assert full["l2_semantic"]["profile"]["goal"] == "exam"
    assert full["l1_working"]["current_topic"] == "TCP"
    assert full["l3_episodic_count"] == 1


def test_build_memory_context():
    from services import memory_service as svc
    svc.init_student_memory("u_test", profile={"goal": "exam", "knowledge_base": "beginner"})
    svc.record_quiz_result("u_test", "TCP", True)
    svc.record_quiz_result("u_test", "路由", False)
    ctx = svc.build_memory_context("u_test", max_episodes=5)
    assert "【学生长期画像】" in ctx
    assert "TCP" in ctx
    # 答错的路由应出现在掌握度薄弱里（0.5 - 0.075 = 0.425 < 0.5）
    assert "路由" in ctx


def test_record_quiz_updates_mastery():
    from services import memory_service as svc
    svc.record_quiz_result("u_test", "TCP", True)
    svc.record_quiz_result("u_test", "TCP", True)
    mem = svc.get_memory_overview("u_test")
    assert mem["mastery_points"] >= 1


def test_memory_overview_shape():
    from services import memory_service as svc
    ov = svc.get_memory_overview("u_test")
    assert "has_profile" in ov
    assert "episodic_count" in ov
    assert "memory_level" in ov
