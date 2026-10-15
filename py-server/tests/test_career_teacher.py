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
    # 8) 六维均分必须真的解析出来 —— 2026-10-14 浏览器走查抓到的回归：
    #    career_assessments.dimension_scores 存的是**嵌套** {"dimensions": {dim: {…}}}，
    #    直接遍历顶层键会让 dimension_avg 恒为空（且不报错）。此前断言只覆盖
    #    summary 的计数与排序口径，漏了"六维到底有没有值"，故此处补上。
    assert stu["dimension_avg"], "学生六维均分不得为空（dimension_scores 是嵌套形态）"
    assert all(isinstance(v, (int, float)) and 1 <= v <= 5 for v in stu["dimension_avg"].values())
    assert summ["dimension_avg"], "全班各维均分不得为空"
    assert wd, "存在评估数据时最弱维度不得为空"


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


# ────────────────────────────────────────────────────────────
# F1 学生个体下钻 / F2 任务管理中心 / F3 学生任务中心（2026-10-15）
# ────────────────────────────────────────────────────────────

def _setup_class_task(client, class_name="功能拓展班", roster="01 张三\n02 李四"):
    """夹具：建班 + 导花名册 + 发任务，返回 (class_id, task)"""
    cls = client.post("/api/career/classes", json={"class_name": class_name}).json()
    client.post(f"/api/career/classes/{cls['class_id']}/students", json={"roster": roster})
    sc = client.get("/api/career/scenarios").json()["scenarios"]
    task = client.post("/api/career/tasks", json={
        "class_id": cls["class_id"], "scenario_id": sc[0]["id"], "max_turns": 4}).json()
    return cls["class_id"], task


def _student_finish_one(client, task):
    """夹具：学生凭码加入并完整跑一场（返回 user_id）"""
    uid = "stu_feature_x"
    _student_override(client, uid)
    try:
        joined = client.post("/api/career/task/join",
                             json={"join_code": task["join_code"]}).json()
        start = client.post("/api/career/session/start", json={
            "scenario_id": joined["scenario_id"], "max_turns": 4,
            "task_id": joined["task_id"]}).json()
        sid = start["session_id"]
        client.post(f"/api/career/session/{sid}/answer",
                    json={"answer": "先看监控指标确认爆炸半径，再查最近发布记录，回滚后补压测与告警预案。"})
        client.post(f"/api/career/session/{sid}/end", json={"force": True})
    finally:
        _restore_auth(client)
    return uid


def test_student_detail_drilldown(client, teacher_id):
    """F1：教师下钻班内学生 → 全部会话明细（六维分/overall/轮数/状态/起止时间）"""
    cid, task = _setup_class_task(client)
    uid = _student_finish_one(client, task)
    detail = client.get(f"/api/career/classes/{cid}/students/{uid}/detail")
    assert detail.status_code == 200
    d = detail.json()
    assert d["user_id"] == uid and d["name"] == "张三"
    assert d["session_count"] == 1 and d["finished_count"] == 1
    assert d["dimension_avg"], "下钻明细必须解析出六维分（嵌套 dimension_scores 回归守护）"
    assert d["overall_best"] is not None
    sess = d["sessions"][0]
    assert sess["status"] == "finished" and sess["turn_count"] >= 1
    assert sess["finished_at"] and sess["started_at"]
    assert sess["overall"] is not None


def test_student_detail_permission_and_missing(client, teacher_id):
    """F1 边界：花名册外的用户 → 404；他人班级 → 404；学生调教师端点 → 403"""
    cid, task = _setup_class_task(client, class_name="下钻权限班")
    # 花名册里没有这个 user_id
    r = client.get(f"/api/career/classes/{cid}/students/ghost_user/detail")
    assert r.status_code == 404
    # 另一个教师的班级 → 404（不是越权可见）
    from db.user_store import create_user, get_user_by_username
    other = "teacher_other_f1"
    if not get_user_by_username(other):
        create_user(other, "pw_123456", "另一位教师", "teacher")
    from main import app
    from shared.auth import get_current_user
    other_id = get_user_by_username(other)["id"]
    app.dependency_overrides[get_current_user] = lambda: {"user_id": other_id, "role": "teacher"}
    try:
        assert client.get(f"/api/career/classes/{cid}/students/x/detail").status_code == 404
        assert client.post(f"/api/career/tasks/{task['task_id']}/close").status_code == 404
    finally:
        _restore_auth(client)
    # 学生调下钻/关闭端点 → 403
    _student_override(client, "stu_f1_403")
    try:
        assert client.get(f"/api/career/classes/{cid}/students/x/detail").status_code == 403
        assert client.post(f"/api/career/tasks/{task['task_id']}/close").status_code == 403
    finally:
        _restore_auth(client)


def test_task_center_stats_and_close(client, teacher_id):
    """F2：任务列表附场景标题+参与进度；关闭后学生端不可见但历史数据不动"""
    cid, task = _setup_class_task(client, class_name="任务管理班")
    uid = _student_finish_one(client, task)
    # 教师任务列表：状态/标题/统计
    tasks = client.get(f"/api/career/tasks?class_id={cid}").json()["tasks"]
    t = next(t for t in tasks if t["task_id"] == task["task_id"])
    assert t["status"] == "open" and t["scenario_title"]
    assert t["stats"]["started_count"] == 1 and t["stats"]["finished_count"] == 1
    # 学生任务中心：加入后可见（F3）
    _student_override(client, uid)
    try:
        myt = client.get("/api/career/my-tasks").json()["tasks"]
        row = next(t for t in myt if t["task_id"] == task["task_id"])
        assert row["join_code"] == task["join_code"] and row["scenario_title"]
    finally:
        _restore_auth(client)
    # 关闭任务
    close = client.post(f"/api/career/tasks/{task['task_id']}/close")
    assert close.status_code == 200 and close.json()["status"] == "closed"
    # 再次关闭 → 幂等（不报错、不产生第二份数据）
    assert client.post(f"/api/career/tasks/{task['task_id']}/close").status_code == 200
    # 关闭后学生端不可见
    _student_override(client, uid)
    try:
        myt2 = client.get("/api/career/my-tasks").json()["tasks"]
        assert all(t["task_id"] != task["task_id"] for t in myt2)
    finally:
        _restore_auth(client)
    # 历史数据不动：看板仍能看到该生的完成会话（关闭≠删数据）
    dash = client.get(f"/api/career/classes/{cid}/dashboard").json()
    stu = next(s for s in dash["students"] if s["user_id"] == uid)
    assert stu["finished_count"] == 1 and stu["dimension_avg"]


def test_my_tasks_empty_before_join(client):
    """F3 边界：未加入任何班级的学生 → 任务中心为空列表（不报错、不编造）"""
    _student_override(client, "stu_no_class")
    try:
        assert client.get("/api/career/my-tasks").json()["tasks"] == []
    finally:
        _restore_auth(client)
