# ============================================================
# 教师端「一键生成学生账号」测试：
#   建号 + 按学号确定性绑定 + 幂等 + 缺学号跳过 + 学生 403
# 运行：python -m pytest tests/test_career_provision_accounts.py -q
# ============================================================

import uuid

import pytest
from fastapi.testclient import TestClient

_RUN = uuid.uuid4().hex[:6]
# 学号必须是纯数字：_parse_roster 对「首列非数字」的整行按姓名处理（产品既有口径）
_SN_BASE = 20260000 + (int(_RUN, 16) % 900) * 10


@pytest.fixture()
def client():
    from main import app
    return TestClient(app)


def _roster(base=None):
    # 学号带 run 偏移，避免共享回退库上的用户名冲突；每个用例用不同偏移
    b = _SN_BASE if base is None else base
    return f"{b} 张三\n{b + 1} 李四\n王五"


def _make_class(client, name):
    return client.post("/api/career/classes", json={"class_name": name}).json()["class_id"]


def _import(client, cid, roster):
    return client.post(f"/api/career/classes/{cid}/students",
                       json={"roster": roster}).json()


def test_provision_creates_accounts_and_binds(client):
    cid = _make_class(client, f"建号班{_RUN}一")
    _import(client, cid, _roster())

    res = client.post(f"/api/career/classes/{cid}/provision-accounts")
    assert res.status_code == 200
    body = res.json()
    assert body["created"] == 2
    assert body["bound"] == 2
    # 缺学号的「王五」必须被如实跳过，不能猜账号名
    assert len(body["skipped"]) == 1 and body["skipped"][0]["name"] == "王五"

    created = [a for a in body["accounts"] if a["status"] == "created"]
    assert len(created) == 2
    for a in created:
        assert a["username"] == a["student_no"]
        assert a["password"] == f"Mc{a['student_no'][-4:]}#2026"

    # 绑定必须真落库：名单行 user_id 不再是空
    students = client.get(f"/api/career/classes/{cid}/students").json()["students"]
    bound = {s["student_no"]: s["user_id"] for s in students}
    assert bound[created[0]["student_no"]] and bound[created[1]["student_no"]]

    # 新账号能用「学号 + 初始口令」真实登录
    from db.user_store import authenticate
    for a in created:
        assert authenticate(a["username"], a["password"]) is not None


def test_provision_is_idempotent(client):
    cid = _make_class(client, f"建号班{_RUN}二")
    _import(client, cid, _roster(_SN_BASE + 2))

    first = client.post(f"/api/career/classes/{cid}/provision-accounts").json()
    assert first["created"] == 2
    second = client.post(f"/api/career/classes/{cid}/provision-accounts").json()
    assert second["created"] == 0
    assert second["bound"] == 2
    assert all(a["status"] == "already_bound" for a in second["accounts"])
    # 幂等路径不回传口令
    assert all(a["password"] == "" for a in second["accounts"])


def test_provision_rejects_student_role(client):
    from main import app
    from shared.auth import get_current_user
    cid = _make_class(client, f"建号班{_RUN}三")
    _import(client, cid, _roster(_SN_BASE + 4))

    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "stu_no_rights", "role": "student"}
    try:
        res = client.post(f"/api/career/classes/{cid}/provision-accounts")
        assert res.status_code == 403
    finally:
        from db.user_store import authenticate
        user = authenticate("test_admin", "test_pw_123")
        app.dependency_overrides[get_current_user] = lambda: {
            "user_id": user["id"], "role": "admin"}


def test_provision_unknown_class_404(client):
    res = client.post("/api/career/classes/cls_not_exist/provision-accounts")
    assert res.status_code == 404


def test_provision_does_not_count_as_joined(client):
    """教师一键建号 ≠ 学生已加入：看板必须把两个口径分开报。

    2026-11-12 真实班实测：48 行名册由教师批量绑定账号后，看板显示「已加入 48/48」，
    而实际 0 人登录过。若把「已建号」算成「已加入」，教师课上会以为全班到齐。
    """
    cid = _make_class(client, f"建号班{_RUN}四")
    _import(client, cid, _roster(_SN_BASE + 6))

    body = client.post(f"/api/career/classes/{cid}/provision-accounts").json()
    assert body["bound"] == 2

    dash = client.get(f"/api/career/classes/{cid}/dashboard").json()
    summ = dash["summary"]
    assert summ["provisioned_count"] == 2, "已建号人数必须单独给出"
    assert summ["joined_count"] == 0, "教师建号不得计入「已加入」"
    assert summ["started_count"] == 0
    assert all(not s["joined"] for s in dash["students"]), "建号后不得有任何一行算作已加入"
    assert sum(1 for s in dash["students"] if s["bound"]) == 2  # 缺学号的「王五」不建号
    assert "已建号但本人尚未加入" in summ["coverage_note"]


def test_join_after_provision_binds_existing_row(client):
    """教师先建号，学生后凭任务码加入：必须认出「这行就是我」，并记真实加入时间。

    旧实现只在 ``user_id IS NULL`` 的行里找，教师已把全班绑完后学生 join 会一行都找
    不到而回 ``roster_bound=False``（2026-11-12 真实班实测的连带风险）。
    """
    from main import app
    from shared.auth import get_current_user
    from db.user_store import get_user_by_username

    cid = _make_class(client, f"建号班{_RUN}五")
    _import(client, cid, _roster(_SN_BASE + 8))
    body = client.post(f"/api/career/classes/{cid}/provision-accounts").json()

    created = [a for a in body["accounts"] if a["status"] == "created"]
    sn = created[0]["student_no"]
    user = get_user_by_username(sn)
    assert user is not None

    sc = client.get("/api/career/scenarios").json()["scenarios"]
    task = client.post("/api/career/tasks", json={
        "class_id": cid, "scenario_id": sc[0]["id"],
        "difficulty": "medium", "max_turns": 4}).json()

    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": user["id"], "role": "student"}
    try:
        joined = client.post("/api/career/task/join", json={"join_code": task["join_code"]})
    finally:
        from db.user_store import authenticate
        admin = authenticate("test_admin", "test_pw_123")
        app.dependency_overrides[get_current_user] = lambda: {
            "user_id": admin["id"], "role": "admin"}

    assert joined.status_code == 200
    payload = joined.json()
    assert payload["roster_bound"] is True, "教师已建号的学生 join 也必须绑定成功"
    assert payload["bound_match"] == "already_bound"
    assert payload["bound_name"] == "张三"

    dash = client.get(f"/api/career/classes/{cid}/dashboard").json()
    assert dash["summary"]["joined_count"] == 1
    joined_row = next(s for s in dash["students"] if s["student_no"] == sn)
    assert joined_row["joined"] is True and joined_row["joined_at"]
