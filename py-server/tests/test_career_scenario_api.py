# -*- coding: utf-8 -*-
# ============================================================
# 6 方向新增后端 API · 端到端契约测试（活体 app + 真 store，非 mock）
#
# 覆盖本轮第二梯队新增的三个能力在真实路由层的闭环：
#   ④ 场景生成器：岗位方向 → 生成 draft → 激活 → 进入可选列表 + 学生 403
#   ⑤ 回溯重评：跑完一场实训 → reassess 返回新旧版本/分数对比
#   ⑥ 学习资源：终评报告 improvement 含 learning_resources
#
# mock_llm(autouse) 让全链路走规则兜底，恰好验证「无 LLM 环境闭环不崩」。
# 运行：python -m pytest tests/test_career_scenario_api.py -q
# ============================================================

import uuid

import pytest
from fastapi.testclient import TestClient

from tests._career_report_wait import wait_report_ready

pytestmark = pytest.mark.p0_regression

# 唯一后缀：共享回退库上固定 uid 会被上一轮数据污染
_RUN = uuid.uuid4().hex[:6]


@pytest.fixture()
def client():
    from main import app
    return TestClient(app)


def _student_override(client, user_id):
    from main import app
    from shared.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {"user_id": user_id, "role": "student"}
    return user_id


def _restore_auth(client):
    from main import app
    from db.user_store import authenticate
    from shared.auth import get_current_user
    user = authenticate("test_admin", "test_pw_123")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": user["id"], "role": "admin"}


def test_scenario_generate_activate_flow(client):
    """④ 场景生成器闭环：岗位方向 → 生成 draft → 激活 → 进入可选列表。"""
    dirs = client.get("/api/career/scenario-job-directions").json()["directions"]
    assert {d["key"] for d in dirs} == {"frontend", "backend", "algorithm", "product", "ops"}

    gen = client.post("/api/career/scenarios/generate",
                      json={"job_direction": "backend", "difficulty": "hard"})
    assert gen.status_code == 200
    sc = gen.json()["scenario"]
    assert gen.json()["status"] == "draft"
    # 结构对齐黄金样本（无论 LLM 还是规则兜底，字段必须齐全）
    assert sc["id"] and sc["title"] and sc["setting"] and sc["opening_question"]
    assert sc["student_role"] and sc["interviewer_role"]
    assert len(sc["probe_tree"]) >= 3
    assert sc["bars_anchor"] and sc["rubric_version"]
    assert sc["job_direction"] == "backend"

    # 草稿列表可见
    drafts = client.get("/api/career/scenarios/drafts").json()["drafts"]
    assert any(d["id"] == sc["id"] for d in drafts)

    # 激活
    act = client.post(f"/api/career/scenarios/{sc['id']}/activate")
    assert act.status_code == 200 and act.json()["status"] == "active"

    # 激活后进入可选场景列表（发任务可选用）
    scenarios = client.get("/api/career/scenarios").json()["scenarios"]
    assert any(s["id"] == sc["id"] for s in scenarios)


def test_scenario_generate_forbidden_for_student(client):
    """④ 权限：学生调用场景生成 → 403。"""
    _student_override(client, "stu_gen_" + _RUN)
    try:
        r = client.post("/api/career/scenarios/generate", json={"job_direction": "backend"})
        assert r.status_code == 403
    finally:
        _restore_auth(client)


def test_reassess_and_learning_resources(client):
    """⑤⑥ 闭环：跑完一场实训 → 回溯重评对比 → 报告含学习资源。"""
    scenarios = client.get("/api/career/scenarios").json()["scenarios"]
    sid = None
    for s in scenarios:
        if s["id"] == "review_requirement_alignment":  # 黄金样本，稳定存在
            start = client.post("/api/career/session/start",
                                json={"scenario_id": s["id"], "max_turns": 4})
            assert start.status_code == 200
            sid = start.json()["session_id"]
            break
    assert sid, "黄金样本 review_requirement_alignment 未找到"

    # 答满 4 轮触发终评（后台异步生成报告）
    for _ in range(4):
        ans = client.post(f"/api/career/session/{sid}/answer",
                          json={"answer": "我先对齐诉求，把功能拆成 MVP 和二期，用数据说话，两周先上核心。"})
        assert ans.status_code == 200
    report = wait_report_ready(client, sid)

    # ⑤ 回溯重评：字段完整、幂等可调
    re = client.post(f"/api/career/session/{sid}/reassess")
    assert re.status_code == 200
    body = re.json()
    assert body["reassessed"] is True
    assert "rubric_version_before" in body and "rubric_version_after" in body
    assert "previous_overall" in body and "new_overall" in body

    # ⑥ 报告 improvement 含学习资源（规则兜底六维方法论卡，非空）
    improvement = report.get("improvement") or {}
    assert improvement.get("learning_resources"), "报告应含 learning_resources"
    for r in improvement["learning_resources"]:
        assert r["dimension"] and r["title"] and r["points"]
