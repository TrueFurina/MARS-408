# ============================================================
# P4 教师端测试：建班→花名册→发任务→学生 join→start(task_id)
#   →answer→end→dashboard 聚合闭环 + 教师角色校验 403
# 运行：python -m pytest tests/test_career_teacher.py -q
# ============================================================

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from main import app
    return TestClient(app)


@pytest.fixture()
def teacher_id():
    """conftest mock_auth 的 admin 用户即教师身份"""
    from db.user_store import authenticate
    return authenticate("test_admin", "test_pw_123")["id"]


def _student_override(client, user_id):
    from main import app
    from shared.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": user_id, "role": "student"}
    return user_id


def _restore_auth(client):
    from main import app
    from db.user_store import authenticate
    from shared.auth import get_current_user
    user = authenticate("test_admin", "test_pw_123")
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": user["id"], "role": "admin"}


def test_teacher_full_closed_loop(client, teacher_id):
    """建班→导花名册→发任务→join→start(task_id)→answer→end→dashboard"""
    # 1) 建班
    cls = client.post("/api/career/classes",
                      json={"class_name": "信息安全1班"}).json()
    assert cls["class_id"]
    # 2) 导花名册（学号 姓名 / 纯姓名混合）
    imp = client.post(f"/api/career/classes/{cls['class_id']}/students",
                      json={"roster": "01 张三\n02 李四\n王五"}).json()
    assert imp["imported"] == 3
    assert {s["name"] for s in imp["students"]} == {"张三", "李四", "王五"}
    # 3) 发任务拿任务码
    sc = client.get("/api/career/scenarios").json()["scenarios"]
    task = client.post("/api/career/tasks", json={
        "class_id": cls["class_id"], "scenario_id": sc[0]["id"],
        "difficulty": "medium", "max_turns": 4}).json()
    assert len(task["join_code"]) == 6
    # 4) 学生凭码加入（花名册绑定）
    _student_override(client, "stu_user_p4")
    try:
        joined = client.post("/api/career/task/join",
                             json={"join_code": task["join_code"]})
        assert joined.status_code == 200
        body = joined.json()
        assert body["scenario_id"] == sc[0]["id"] and body["roster_bound"] is True
        # 5) 带 task_id 开局 → 作答 → 强制终评
        start = client.post("/api/career/session/start", json={
            "scenario_id": body["scenario_id"], "max_turns": 4,
            "task_id": body["task_id"]})
        assert start.status_code == 200
        sess_id = start.json()["session_id"]
        ans = client.post(f"/api/career/session/{sess_id}/answer",
                          json={"answer": "先定位日志时间线，再查最近变更，最后回滚验证，并补监控预案。"})
        assert ans.status_code == 200
        end = client.post(f"/api/career/session/{sess_id}/end",
                          json={"force": True})
        assert end.status_code == 200
    finally:
        _restore_auth(client)
    # 6) 教师看板聚合：能看到该学生的完成会话与评估
    dash = client.get(f"/api/career/classes/{cls['class_id']}/dashboard").json()
    assert dash["student_count"] == 3
    stu = next(s for s in dash["students"] if s["user_id"] == "stu_user_p4")
    assert stu["session_count"] >= 1 and stu["bound"] is True
    assert any(s["status"] == "finished" for s in stu["sessions"])
    # 7) 班级级聚合（2026-10-14 新增）：完成率与"最弱维度"的相对排序口径
    summ = dash["summary"]
    assert summ["student_count"] == 3 and summ["assessed_count"] == 1
    assert summ["finished_count"] == 1
    assert summ["completion_rate"] == round(1 / 3, 2)
    wd = summ["weakest_dimensions"]
    assert wd == sorted(wd, key=lambda x: x["avg"]), "最弱维度必须是按均分升序的相对排序"
    assert len(wd) <= 3
    reasons = {a["reason"] for a in dash["attention"]}
    assert "not_started" in reasons, "未参与的学生应进 attention"
    assert all(a["detail"] for a in dash["attention"]), "attention 每条都必须有可反查的说明"


def test_dashboard_class_aggregation_empty_class(client, teacher_id):
    """边界：全班无人开始实训时，聚合指标不得凭空产生数字（0/空 而非 None 或编造）。"""
    cls = client.post("/api/career/classes", json={"class_name": "零学情班"}).json()
    client.post(f"/api/career/classes/{cls['class_id']}/students",
                json={"roster": "01 甲\n02 乙"})
    dash = client.get(f"/api/career/classes/{cls['class_id']}/dashboard").json()
    summ = dash["summary"]
    assert summ["student_count"] == 2
    assert summ["started_count"] == 0 and summ["finished_count"] == 0
    assert summ["assessed_count"] == 0
    assert summ["completion_rate"] == 0.0
    assert summ["dimension_avg"] == {} and summ["weakest_dimensions"] == []
    assert {a["reason"] for a in dash["attention"]} == {"not_started"}
    assert len(dash["attention"]) == 2


def test_student_forbidden_on_teacher_endpoints(client):
    """student 调教师端点 → 403（建班/列表/看板/发任务）"""
    _student_override(client, "stu_user_403")
    try:
        assert client.post("/api/career/classes",
                           json={"class_name": "x"}).status_code == 403
        assert client.get("/api/career/classes").status_code == 403
        assert client.get("/api/career/classes/nope/dashboard").status_code == 403
        assert client.post("/api/career/tasks", json={
            "class_id": "x", "scenario_id": "y"}).status_code == 403
    finally:
        _restore_auth(client)


def test_join_binds_roster_row_by_name(client, teacher_id):
    """学生姓名与花名册一致时，应按**姓名**绑定（而非取第一个未绑定行）。

    背景：bind_student 原 docstring 称「按姓名匹配」，实现却是直接取第一个未绑定行
    ——多人同时凭码加入会张冠李戴。2026-10-14 补上真实姓名匹配，本用例守护之。
    """
    from db.user_store import create_user, get_user_by_username

    uname = "p4_lisi"
    if not get_user_by_username(uname):
        create_user(uname, "pw_123456", "李四", "student")
    u = get_user_by_username(uname)

    cls = client.post("/api/career/classes", json={"class_name": "按名绑定班"}).json()
    client.post(f"/api/career/classes/{cls['class_id']}/students",
                json={"roster": "01 张三\n02 李四\n03 王五"})
    sc = client.get("/api/career/scenarios").json()["scenarios"]
    task = client.post("/api/career/tasks", json={
        "class_id": cls["class_id"], "scenario_id": sc[0]["id"], "max_turns": 4}).json()

    _student_override(client, u["id"])
    try:
        body = client.post("/api/career/task/join",
                           json={"join_code": task["join_code"]}).json()
    finally:
        _restore_auth(client)

    assert body["roster_bound"] is True
    assert body["bound_match"] == "name", "姓名一致时应按姓名绑定，而不是取第一个未绑定行"
    assert body["bound_name"] == "李四"


def test_join_falls_back_to_first_unbound_when_name_unmatched(client, teacher_id):
    """姓名无法匹配时退回「第一个未绑定行」——如实回传 bound_match，不假装按姓名命中。

    （保持历史行为：宁可绑定位置可能不准，也不能让花名册里的学生完全绑不上。）
    """
    cls = client.post("/api/career/classes", json={"class_name": "退回绑定班"}).json()
    client.post(f"/api/career/classes/{cls['class_id']}/students",
                json={"roster": "01 张三"})
    sc = client.get("/api/career/scenarios").json()["scenarios"]
    task = client.post("/api/career/tasks", json={
        "class_id": cls["class_id"], "scenario_id": sc[0]["id"], "max_turns": 4}).json()

    # 该 user_id 在用户表中不存在 → 取不到姓名 → 走退回路径
    _student_override(client, "stu_no_name_p4")
    try:
        body = client.post("/api/career/task/join",
                           json={"join_code": task["join_code"]}).json()
    finally:
        _restore_auth(client)

    assert body["roster_bound"] is True
    assert body["bound_match"] == "first_unbound"
    assert body["bound_name"] == "张三"


def test_join_invalid_code_404(client):
    assert client.post("/api/career/task/join",
                       json={"join_code": "ZZZZZZ"}).status_code == 404


def test_import_roster_empty_400(client, teacher_id):
    cls = client.post("/api/career/classes",
                      json={"class_name": "空名单班"}).json()
    r = client.post(f"/api/career/classes/{cls['class_id']}/students",
                    json={"roster": "  \n  "})
    assert r.status_code == 400


def test_roster_on_other_teachers_class_404(client, teacher_id):
    """教师不能给他人班级导名单（teacher_id 归属校验）"""
    cls = client.post("/api/career/classes",
                      json={"class_name": "甲的班"}).json()
    from main import app
    from shared.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "teacher_other", "role": "teacher"}
    try:
        r = client.post(f"/api/career/classes/{cls['class_id']}/students",
                        json={"roster": "01 张三"})
        assert r.status_code == 404
    finally:
        _restore_auth(client)
