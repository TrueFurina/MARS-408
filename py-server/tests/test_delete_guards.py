"""删除类端点的权限与护栏测试。

必须在 no_mock_auth 下跑：conftest 的 mock_auth（autouse）会把
get_current_user / require_admin 顶成 admin 假用户，权限断言会全部假绿
（2026-10-16 曾因此让 /knowledge/clear 在测试里删掉真实 2245 条语料）。

覆盖两类护栏：
  1. DELETE /api/admin/users/{username}  —— admin 专属 + 禁自删 + 不存在 404
  2. DELETE /api/career/classes/{class_id} —— 教师专属 + 归属隔离 + 只删空班
"""

import uuid

import pytest

from db import career_store
from db import user_store
from shared.auth import create_token

_PW = "Tp#2026pwguard"  # 满足 MIN_PASSWORD_LENGTH
_PREFIX = "delg"


def _uname(tag=""):
    return f"{_PREFIX}_{tag}_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def identities(no_mock_auth):
    """造三个真实用户（student/teacher/admin）并返回其 token；用完级联删除。

    依赖 no_mock_auth：让后续请求走真实鉴权，token 才真的决定角色。
    """
    made = {}
    for role in ("student", "teacher", "admin"):
        name = _uname(role[:3])
        user_store.create_user(name, _PW, f"guard-{role}", role=role)
        u = user_store.get_user_by_username(name)
        made[role] = {"username": name, "id": u["id"], "token": create_token(u["id"], role)}
    yield made
    for role in ("student", "teacher", "admin"):
        try:
            user_store.delete_user(made[role]["username"])
        except Exception:
            pass


# ────────────────────────────────────────────────────────────
# 1. 用户删除
# ────────────────────────────────────────────────────────────

def test_delete_user_requires_admin(client, identities):
    tgt = _uname("victim")
    user_store.create_user(tgt, _PW, "victim", role="student")
    try:
        assert client.delete(
            f"/api/admin/users/{tgt}",
            headers={"X-App-Token": identities["student"]["token"]},
        ).status_code == 403
        assert client.delete(
            f"/api/admin/users/{tgt}",
            headers={"X-App-Token": identities["teacher"]["token"]},
        ).status_code == 403
        # 未被删除（403 是拒绝，不是"删了但拒绝"）
        assert user_store.get_user_by_username(tgt) is not None
    finally:
        user_store.delete_user(tgt)


def test_delete_user_requires_credentials(client, no_mock_auth):
    """GATE：无凭据必须被鉴权闸门拦下（401/403），且绝不是 404/200"""
    r = client.delete(f"/api/admin/users/{_uname()}")
    assert r.status_code in (401, 403)


def test_delete_user_refuses_self(client, identities):
    admin = identities["admin"]
    r = client.delete(
        f"/api/admin/users/{admin['username']}",
        headers={"X-App-Token": admin["token"]},
    )
    assert r.status_code == 403
    # 自删被拒后自己必须还在——否则整站再无管理员
    assert user_store.get_user_by_username(admin["username"]) is not None


def test_delete_user_not_found_is_404(client, identities):
    r = client.delete(
        f"/api/admin/users/{_uname('ghost')}",
        headers={"X-App-Token": identities["admin"]["token"]},
    )
    assert r.status_code == 404


def test_delete_user_removes_it(client, identities):
    tgt = _uname("doomed")
    user_store.create_user(tgt, _PW, "doomed", role="student")
    r = client.delete(
        f"/api/admin/users/{tgt}",
        headers={"X-App-Token": identities["admin"]["token"]},
    )
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    assert user_store.get_user_by_username(tgt) is None


def test_self_guard_compares_user_id_not_username():
    """契约闸：鉴权只产出 user_id/role，不含 username。

    若实现里写成 admin.get("username") == target，恒为 None == target ⇒
    自删护栏永不触发。本闸锁死「鉴权对象上没有 username 这个键」这一事实，
    逼实现必须用 user_id 比较（由 test_delete_user_refuses_self 兜住行为）。
    """
    token = create_token("u_fakeadmin", "admin")
    from shared.auth import verify_token
    payload = verify_token(token)
    assert payload["sub"] == "u_fakeadmin"
    assert "username" not in payload


# ────────────────────────────────────────────────────────────
# 2. 班级删除
# ────────────────────────────────────────────────────────────

@pytest.fixture
def two_teachers(no_mock_auth):
    """两个互不隶属的教师，各带一个空班"""
    made = {}
    for tag in ("a", "b"):
        name = _uname("t" + tag)
        user_store.create_user(name, _PW, "teacher-" + tag, role="teacher")
        u = user_store.get_user_by_username(name)
        cls = career_store.create_class(u["id"], f"空班-{tag}")
        made[tag] = {
            "username": name, "id": u["id"],
            "token": create_token(u["id"], "teacher"),
            "class_id": cls["class_id"],
        }
    yield made
    for tag in ("a", "b"):
        try:
            career_store.delete_empty_class(made[tag]["class_id"], made[tag]["id"])
        except Exception:
            pass
        try:
            user_store.delete_user(made[tag]["username"])
        except Exception:
            pass


def test_delete_class_requires_teacher_role(client, two_teachers, identities):
    r = client.delete(
        f"/api/career/classes/{two_teachers['a']['class_id']}",
        headers={"X-App-Token": identities["student"]["token"]},
    )
    assert r.status_code == 403


def test_delete_class_requires_credentials(client, no_mock_auth):
    r = client.delete("/api/career/classes/cls_notexist")
    assert r.status_code in (401, 403)


def test_delete_class_isolates_owner(client, two_teachers):
    """教师 A 删教师 B 的班 → 404（归属隔离：不是你的就当它不存在）"""
    r = client.delete(
        f"/api/career/classes/{two_teachers['b']['class_id']}",
        headers={"X-App-Token": two_teachers["a"]["token"]},
    )
    assert r.status_code == 404
    # B 的班必须还在
    assert career_store.get_class(
        two_teachers["b"]["class_id"], two_teachers["b"]["id"]) is not None


def test_delete_class_refuses_non_empty(client, two_teachers):
    """非空班一律 409：班级下挂着名册/任务/实训记录，都是发生型证据"""
    cid = two_teachers["a"]["class_id"]
    tid = two_teachers["a"]["id"]
    career_store.add_students(cid, tid, [{"student_no": "9901", "name": "探测学生"}])
    r = client.delete(
        f"/api/career/classes/{cid}",
        headers={"X-App-Token": two_teachers["a"]["token"]},
    )
    assert r.status_code == 409
    assert career_store.get_class(cid, tid) is not None


def test_delete_class_ok_for_owner(client, two_teachers):
    cid = two_teachers["a"]["class_id"]
    tid = two_teachers["a"]["id"]
    r = client.delete(
        f"/api/career/classes/{cid}",
        headers={"X-App-Token": two_teachers["a"]["token"]},
    )
    assert r.status_code == 200
    assert career_store.get_class(cid, tid) is None
