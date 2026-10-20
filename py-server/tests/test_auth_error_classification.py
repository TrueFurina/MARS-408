# -*- coding: utf-8 -*-
"""注册错误文案分类回归 —— 内部 ValueError 原文禁直出用户（REA 实践 #12）

背景：/api/auth/register 原样 `ValidationError(detail=str(e))` 透出 db 层
create_user 的 ValueError 原文。已登记的三条业务文案（"用户名已存在"等）
确实是写给用户看的，但**任何**未登记的 ValueError（内部异常被包装成
ValueError、未来新增分支、底层驱动错误串）都会把内部细节写进 HTTP
响应体 —— 属于信息泄露面（表名/SQL/文件路径/驱动版本都可能外泄）。

本测试锁定两条契约：
1. 登记内的业务文案原样透出（用户体验不变，回归不破坏现有行为）；
2. 未登记的 ValueError 按通用文案对外，且原始文本不出现在响应体
   （服务端 log_event/logger 仍保留完整原文，可追溯性不降级）。

运行：python -m pytest tests/test_auth_error_classification.py -q
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.auth as auth_api  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)

# 典型"内部细节"样本：任何一条出现在响应体里都算泄露
_INTERNAL_SAMPLES = [
    "UNIQUE constraint failed: users.username",
    "sqlite3.OperationalError: no such table: users",
    "db path E:\\Program\\MARL\\study-help-pro\\py-server\\data\\netlearn.db is locked",
    "PBKDF2 iteration mismatch: expected 600000, got 1",
]


@pytest.fixture(autouse=True)
def bypass_rate_limit(monkeypatch):
    """本测试聚焦错误分类，与限流无关；绕过注册限流避免跨文件共享 IP 预算。"""
    monkeypatch.setattr(auth_api, "_check_rate_limit", lambda key, max_requests, window: None)


def _register(username: str, password: str = "pw_123456") -> dict:
    r = client.post(
        "/api/auth/register",
        json={"username": username, "password": password, "display_name": "err-cls"},
    )
    assert r.status_code == 422, f"期望 ValidationError(422)，实际 {r.status_code}: {r.text}"
    return r.json()["error"]


class TestAllowlistedMessagesPassThrough:
    """登记内的业务文案必须原样透出 —— 修复不得破坏现有用户体验。"""

    def test_duplicate_username_message_passes_through(self, monkeypatch):
        monkeypatch.setattr(
            auth_api, "create_user",
            lambda u, p, d="": (_ for _ in ()).throw(ValueError("用户名已存在")),
        )
        err = _register(f"dup_{os.urandom(4).hex()}")
        assert err["code"] == "VALIDATION_ERROR"
        assert err["message"] == "用户名已存在"

    def test_empty_credentials_message_passes_through(self, monkeypatch):
        monkeypatch.setattr(
            auth_api, "create_user",
            lambda u, p, d="": (_ for _ in ()).throw(ValueError("用户名和密码不能为空")),
        )
        err = _register(f"empty_{os.urandom(4).hex()}")
        assert err["message"] == "用户名和密码不能为空"

    def test_password_length_message_passes_through(self, monkeypatch):
        """动态文案按前缀准入（MIN_PASSWORD_LENGTH 生成，无法静态登记）。"""
        monkeypatch.setattr(
            auth_api, "create_user",
            lambda u, p, d="": (_ for _ in ()).throw(ValueError("密码长度至少 8 位")),
        )
        err = _register(f"pwlen_{os.urandom(4).hex()}")
        assert err["message"] == "密码长度至少 8 位"


class TestUnregisteredErrorsAreClassified:
    """未登记的 ValueError：通用文案对外 + 原文不得出现在响应体。"""

    @pytest.mark.parametrize("internal_text", _INTERNAL_SAMPLES)
    def test_internal_text_never_reaches_client(self, monkeypatch, internal_text):
        def _boom(u, p, d=""):
            raise ValueError(internal_text)

        monkeypatch.setattr(auth_api, "create_user", _boom)
        err = _register(f"leak_{os.urandom(4).hex()}")
        assert err["message"] == "注册失败，请稍后重试"
        assert internal_text not in err["message"]

    def test_response_body_contains_no_internal_fragments(self, monkeypatch):
        """端到端断言：整段响应文本（不只是 message 字段）无内部片段。"""
        internal = _INTERNAL_SAMPLES[2]  # 含 Windows 绝对路径的样本

        def _boom(u, p, d=""):
            raise ValueError(internal)

        monkeypatch.setattr(auth_api, "create_user", _boom)
        r = client.post(
            "/api/auth/register",
            json={"username": f"body_{os.urandom(4).hex()}", "password": "pw_123456"},
        )
        assert r.status_code == 422
        assert internal not in r.text
        assert "netlearn.db" not in r.text

    def test_helper_classifies_directly(self):
        """原语级断言：映射函数本身的登记/兜底行为。"""
        assert auth_api._user_safe_register_error(ValueError("用户名已存在")) == "用户名已存在"
        assert auth_api._user_safe_register_error(
            ValueError("UNIQUE constraint failed: users.username")
        ) == "注册失败，请稍后重试"
        # 近似但不等于登记项的文案（前缀伪装）不得准入
        assert auth_api._user_safe_register_error(
            ValueError("用户名已存在（internal: users.id）")
        ) == "注册失败，请稍后重试"
