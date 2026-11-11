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
