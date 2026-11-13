# -*- coding: utf-8 -*-
"""学生自助改密接口 —— POST /api/auth/change-password

课堂现实：48 张登录卡上的 `Mg#xxxxxx` 是一次性明文口令，学生换设备/忘记后
只能找教师手工重设。本接口把这件事交还学生本人，因此必须在测试里钉死三条：
① 没带对当前口令不许改（防 token 泄漏后被静默换密）；
② 新口令长度与「不得与旧口令相同」两道校验；
③ 改完之后**新口令能登录、旧口令登不上**，而不是只返回一个 ok。

⚠️ 测试会真的改 `test_admin` 的口令（autouse 的 mock_auth 用它冒充登录用户），
所以每个成功用例都用 try/finally 把口令恢复成 `test_pw_123`——否则同一次
pytest 进程里后续用例 authenticate 会拿到 None，mock_auth 的 user_id 变
"unknown"，一批无关用例会连带红。
"""

import pytest

from db.user_store import set_password

ORIGINAL_PASSWORD = "test_pw_123"
NEW_PASSWORD = "NewPw#2026x"


def _login(client, username: str, password: str):
    return client.post("/api/auth/login", json={"username": username, "password": password})


@pytest.fixture()
def restore_test_admin_password():
    """用例结束后无条件恢复 test_admin 口令（无论断言是否失败）。"""
    yield
    set_password("test_admin", ORIGINAL_PASSWORD)


class TestChangePasswordValidation:
    def test_wrong_old_password_rejected(self, client, restore_test_admin_password):
        resp = client.post("/api/auth/change-password",
                           json={"old_password": "not-my-password", "new_password": NEW_PASSWORD})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert "当前口令不正确" in body["error"]["message"]

    def test_new_password_too_short_rejected(self, client, restore_test_admin_password):
        resp = client.post("/api/auth/change-password",
                           json={"old_password": ORIGINAL_PASSWORD, "new_password": "short"})
        assert resp.status_code == 422
        # 长度由 Pydantic 拦下，口令本身不能被改动
        assert _login(client, "test_admin", ORIGINAL_PASSWORD).status_code == 200

    def test_same_password_rejected(self, client, restore_test_admin_password):
        resp = client.post("/api/auth/change-password",
                           json={"old_password": ORIGINAL_PASSWORD,
                                 "new_password": ORIGINAL_PASSWORD})
        assert resp.status_code == 422
        assert "不能与当前口令相同" in resp.json()["error"]["message"]

    def test_unauthenticated_rejected(self, client, no_mock_auth):
        resp = client.post("/api/auth/change-password",
                           json={"old_password": ORIGINAL_PASSWORD, "new_password": NEW_PASSWORD})
        assert resp.status_code == 401


class TestChangePasswordEffect:
    def test_new_password_works_and_old_password_stops(self, client, restore_test_admin_password):
        try:
            resp = client.post("/api/auth/change-password",
                               json={"old_password": ORIGINAL_PASSWORD, "new_password": NEW_PASSWORD})
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "ok"

            # 真的换过来了：新口令能登录，旧口令登不上
            assert _login(client, "test_admin", NEW_PASSWORD).status_code == 200
            assert _login(client, "test_admin", ORIGINAL_PASSWORD).status_code == 422
        finally:
            set_password("test_admin", ORIGINAL_PASSWORD)

        # 复原后旧口令恢复可用（证明清理有效，不会污染同批次其他用例）
        assert _login(client, "test_admin", ORIGINAL_PASSWORD).status_code == 200
