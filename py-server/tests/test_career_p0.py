# ============================================================
# Career P0-P3 补强测试（CTO 盘点短板①：tests/ 零 career 测试）
# 覆盖：5 表建表 / 鲶鱼模式决策规则 / 六维规则兜底评估 /
#       评估归一化 / API 端点挂载与越权 403 / 提升路径兜底
# 运行：python -m pytest tests/test_career_p0.py -q
# ============================================================

import pytest
from fastapi.testclient import TestClient

from agents.career_nodes import (
    decide_adversary_mode,
    _rule_based_assessment,
    _normalize_assessment,
    _fallback_improvement,
)
from agents.career_state import (
    DIMENSIONS,
    CATFISH_MAX_CONTINUE,
    ADVERSARY_MODES,
)
from db import career_store


# ────────────────────────────────────────────────────────────
# 领域常量
# ────────────────────────────────────────────────────────────

def test_six_dimensions_defined():
    """六维口径完整且唯一"""
    assert len(DIMENSIONS) == 6
    assert len(set(DIMENSIONS)) == 6


def test_adversary_modes_defined():
    """三模式常量齐全，鲶鱼连压上限为 2"""
    assert set(ADVERSARY_MODES) == {"normal", "escalating", "catfish"}
    assert CATFISH_MAX_CONTINUE == 2


# ────────────────────────────────────────────────────────────
# 5 表建表
# ────────────────────────────────────────────────────────────

def test_ensure_tables_creates_five_tables():
    assert career_store.ensure_tables() is True
    tables = {r[0] if isinstance(r, tuple) else r.get("name")
              for r in pg_tables()}
    for t in ("career_classes", "career_tasks", "career_sessions",
              "career_dialogue_turns", "career_assessments"):
        assert t in tables, f"缺表: {t}"


def pg_tables():
    from db.pg_client import pg_client
    rows = pg_client.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'career_%'"
        if pg_client.is_sqlite else
        "SELECT tablename FROM pg_tables WHERE tablename LIKE 'career_%'"
    )
    return rows


# ────────────────────────────────────────────────────────────
# 鲶鱼模式决策（规则版核心）
# ────────────────────────────────────────────────────────────

def _turn(i, template=False, density=0.6):
    return {"turn_index": i,
            "evidence": {"template_suspect": template, "density": density}}


def test_catfish_not_triggered_on_empty():
    assert decide_adversary_mode([], "normal", 0) == ("normal", False, 0)


def test_catfish_triggers_on_double_template():
    """连续 2 轮模板嫌疑 → 触发鲶鱼"""
    mode, triggered, cont = decide_adversary_mode(
        [_turn(1, template=True), _turn(2, template=True)], "normal", 0)
    assert mode == "catfish" and triggered is True and cont == 1


def test_escalating_triggers_on_low_density():
    """信息密度过低 → 加压（非鲶鱼）"""
    mode, triggered, _ = decide_adversary_mode(
        [_turn(1, density=0.2), _turn(2, density=0.2)], "normal", 0)
    assert mode == "escalating" and triggered is True


def test_catfish_backoff_after_max_continue():
    """鲶鱼连压达上限 → 回 normal 清零"""
    mode, triggered, cont = decide_adversary_mode(
        [_turn(1)], "catfish", CATFISH_MAX_CONTINUE)
    assert mode == "normal" and triggered is False and cont == 0


def test_catfish_extends_while_condition_holds():
    """未达上限且仍满足条件 → 延续并 +1"""
    mode, triggered, cont = decide_adversary_mode(
        [_turn(2, template=True)], "catfish", 1)
    assert mode == "catfish" and triggered is False and cont == 2


def test_no_trigger_below_two_turns():
    """不足 2 轮不触发（避免开场误判）"""
    mode, triggered, _ = decide_adversary_mode(
        [_turn(1, template=True)], "normal", 0)
    assert mode == "normal" and triggered is False


# ────────────────────────────────────────────────────────────
# 六维规则兜底评估 / 归一化
# ────────────────────────────────────────────────────────────

def _script():
    return {"dimension_weights": {d: 1.0 for d in DIMENSIONS}}


def test_rule_based_assessment_scores_probed_dimensions():
    """被考察维度按信息密度给保守中性分，来源标注 rule_fallback"""
    turns = [{"turn_index": 1, "probe_dimension": "expression",
              "answer": "用结论-理由-例子结构说明，包含具体步骤与风险预案" * 2,
              "evidence": {"density": 0.7, "template_suspect": False,
                           "dimension_hits": []}}]
    result = _rule_based_assessment(turns, _script())
    assert result["assessment_source"] == "rule_fallback"
    assert result["dimensions"]["expression"]["score"] is not None
    assert result["dimensions"]["collab"]["level"] == "insufficient"


def test_rule_based_assessment_marks_template_detected():
    turns = [{"turn_index": 1, "probe_dimension": "expression",
              "answer": "我觉得挺好的", "evidence": {"density": 0.3,
                                                     "template_suspect": True,
                                                     "dimension_hits": []}}]
    assert _rule_based_assessment(turns, _script())["template_detected"] is True


def test_normalize_assessment_clamps_and_weights():
    """非法分数夹到 [1,5]、中文维度键归一、overall 加权计算"""
    data = {"dimensions": {"表达逻辑": {"score": 9, "confidence": 0.8,
                                        "evidence_turns": [1, "x"]},
                           "collab": {"score": "bad"}},
            "strength": "s"}
    norm = _normalize_assessment(data, _script())
    assert norm["dimensions"]["expression"]["score"] == 5.0
    assert norm["dimensions"]["collab"]["score"] is None
    assert norm["dimensions"]["expression"]["evidence_turns"] == [1]
    assert norm["overall"] is not None
    assert norm["assessment_source"] == "llm"


# ────────────────────────────────────────────────────────────
# 提升路径兜底
# ────────────────────────────────────────────────────────────

def test_fallback_improvement_targets_weakest():
    dims = {d: {"score": 5.0 if d == "expression" else 2.0}
            for d in DIMENSIONS}
    plan = _fallback_improvement({"dimensions": dims})
    assert plan["priority_dimensions"][0] != "expression"
    assert len(plan["actions"]) >= 1
    assert all("do" in a for a in plan["actions"])


# ────────────────────────────────────────────────────────────
# API 端点：挂载 / 最窄闭环 / 越权 403
# ────────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    from main import app
    return TestClient(app)


def test_career_routes_mounted(client):
    paths = {r.path for r in client.app.routes}
    for p in ("/api/career/scenarios", "/api/career/session/start",
              "/api/career/sessions"):
        assert p in paths, f"路由未挂载: {p}"


def test_start_answer_end_closed_loop(client):
    """最窄闭环：列表 → 启动 → 作答 → 强制结束出报告"""
    sc = client.get("/api/career/scenarios").json()["scenarios"]
    assert len(sc) >= 1
    sid = client.post("/api/career/session/start",
                      json={"scenario_id": sc[0]["id"], "max_turns": 4}
                      ).json()["session_id"]
    ans = client.post(f"/api/career/session/{sid}/answer",
                      json={"answer": "先定位日志时间线，再查最近变更，最后回滚验证。"})
    assert ans.status_code == 200
    end = client.post(f"/api/career/session/{sid}/end", json={"force": True})
    assert end.status_code == 200
    rep = client.get(f"/api/career/session/{sid}/report")
    assert rep.status_code == 200
    body = rep.json()
    assert "assessment" in body and "improvement" in body


def test_answer_unknown_session_404(client):
    assert client.post("/api/career/session/no-such-id/answer",
                       json={"answer": "x"}).status_code == 404


def test_other_user_session_403(client):
    """非归属且非教师/管理员角色 → 403"""
    from main import app
    from shared.auth import get_current_user
    sc = client.get("/api/career/scenarios").json()["scenarios"]
    sid = client.post("/api/career/session/start",
                      json={"scenario_id": sc[0]["id"], "max_turns": 4}
                      ).json()["session_id"]
    student = {"user_id": "other-user-000", "role": "student"}
    app.dependency_overrides[get_current_user] = lambda: student
    try:
        r = client.post(f"/api/career/session/{sid}/answer",
                        json={"answer": "x"})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
