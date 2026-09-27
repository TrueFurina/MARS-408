# -*- coding: utf-8 -*-
"""JWT 签发 / 校验 / 角色守门单测 —— shared/auth.py（此前 64% 覆盖）

这是全站认证的底座，未覆盖的正是**攻击面**相关分支：
签名校验失败、payload 篡改、Token 过期、非 Bearer 头、角色越权。
把这些固化成回归断言，比补任何"凑数测试"都更有价值。
"""

import time

import pytest
from fastapi import HTTPException

import shared.auth as auth


@pytest.fixture(autouse=True)
def fixed_secret(monkeypatch):
    """固定密钥，避免依赖环境变量与模块级缓存状态。"""
    monkeypatch.setattr(auth, "_SECRET", "unit-test-secret-" + "x" * 20)


class TestBase64UrlHelpers:
    def test_round_trip(self):
        raw = b"hello-\x00\xff-bytes"
        assert auth._b64url_decode(auth._b64url_encode(raw)) == raw

    def test_encoding_has_no_padding(self):
        assert "=" not in auth._b64url_encode(b"abc")

    def test_decode_restores_missing_padding(self):
        """URL-safe base64 去掉 '=' 后仍须能解回（否则 payload 解析会随机失败）。"""
        encoded = auth._b64url_encode(b"12345")
        assert auth._b64url_decode(encoded) == b"12345"


class TestTokenRoundTrip:
    def test_verify_returns_original_claims(self):
        token = auth.create_token("u1", role="teacher")
        payload = auth.verify_token(token)
        assert payload["sub"] == "u1" and payload["role"] == "teacher"

    def test_payload_carries_iat_and_exp(self):
        payload = auth.verify_token(auth.create_token("u2"))
        assert payload["exp"] > payload["iat"] >= 0
        assert payload["role"] == "student", "默认角色应为 student"

    def test_token_has_three_segments(self):
        assert len(auth.create_token("u3").split(".")) == 3


class TestTokenRejection:
    """以下每条都是一次真实攻击手法的负例。"""

    def test_tampered_signature_rejected(self):
        token = auth.create_token("attacker")
        head, payload, sig = token.split(".")
        # ⚠️ 必须**确定性地**改坏签名：早先写成 'A' + sig[1:]，当签名恰好以 'A' 开头时
        # 篡改后的串与原串完全相同（base64url 首字符，约 1/64 概率）→ 用例偶发失败。
        tampered_sig = sig[:-1] + ("A" if sig[-1] != "A" else "B")
        assert tampered_sig != sig, "篡改必须真的改变签名"
        with pytest.raises(HTTPException) as exc:
            auth.verify_token(f"{head}.{payload}.{tampered_sig}")
        assert exc.value.status_code == 401

    def test_privilege_escalation_via_payload_edit_rejected(self):
        """把 payload 里的 role 改成 admin —— 签名不匹配必须拒绝。"""
        token = auth.create_token("student-user", role="student")
        head, payload, sig = token.split(".")
        decoded = auth._b64url_decode(payload).decode("utf-8")
        forged_payload = auth._b64url_encode(decoded.replace("student", "admin").encode("utf-8"))
        with pytest.raises(HTTPException):
            auth.verify_token(f"{head}.{forged_payload}.{sig}")

    def test_expired_token_rejected(self, monkeypatch):
        monkeypatch.setattr(auth, "_TOKEN_TTL", -10)
        token = auth.create_token("u-expired")
        with pytest.raises(HTTPException) as exc:
            auth.verify_token(token)
        assert exc.value.status_code == 401

    @pytest.mark.parametrize("token", ["", "abc", "a.b", "a.b.c.d", "not-a-token"])
    def test_malformed_token_rejected(self, token):
        with pytest.raises(HTTPException):
            auth.verify_token(token)

    def test_signature_from_other_secret_rejected(self):
        """换密钥（模拟被签发的旧密钥失效）后旧 token 必须失效。"""
        token = auth.create_token("u-old")
        auth._SECRET = "another-secret-" + "y" * 20
        try:
            with pytest.raises(HTTPException):
                auth.verify_token(token)
        finally:
            auth._SECRET = "unit-test-secret-" + "x" * 20


class TestGetCurrentUser:
    def test_missing_header_rejected(self):
        with pytest.raises(HTTPException) as exc:
            auth.get_current_user(None)
        assert exc.value.status_code == 401

    @pytest.mark.parametrize("header", ["", "Token abc", "Bearer", "bearer abc"])
    def test_non_bearer_header_rejected(self, header):
        with pytest.raises(HTTPException):
            auth.get_current_user(header)

    def test_valid_bearer_returns_user(self):
        token = auth.create_token("u9", role="admin")
        user = auth.get_current_user(f"Bearer {token}")
        assert user == {"user_id": "u9", "role": "admin"}

    def test_role_defaults_to_student_when_absent(self, monkeypatch):
        """payload 缺 role 字段时按最小权限处理。"""
        monkeypatch.setattr(auth, "verify_token", lambda token: {"sub": "u10"})
        assert auth.get_current_user("Bearer x")["role"] == "student"


class TestRoleGuards:
    def test_admin_guard_rejects_student(self):
        with pytest.raises(HTTPException) as exc:
            auth.require_admin({"role": "student"})
        assert exc.value.status_code == 403

    def test_admin_guard_allows_admin(self):
        assert auth.require_admin({"role": "admin"})["role"] == "admin"

    @pytest.mark.parametrize("role", ["admin", "teacher"])
    def test_teacher_guard_allows_staff(self, role):
        assert auth.require_teacher({"role": role})["role"] == role

    def test_teacher_guard_rejects_student(self):
        with pytest.raises(HTTPException) as exc:
            auth.require_teacher({"role": "student"})
        assert exc.value.status_code == 403

    def test_teacher_guard_defaults_missing_role_to_student(self):
        with pytest.raises(HTTPException):
            auth.require_teacher({})


class TestDemoTeacherSwitch:
    def test_flag_off_by_default(self, monkeypatch):
        monkeypatch.delenv("NETLEARN_DEMO_TEACHER_OPEN", raising=False)
        assert auth._is_demo_teacher_open() is False

    def test_flag_on_recognizes_truthy_values(self, monkeypatch):
        monkeypatch.setenv("NETLEARN_DEMO_TEACHER_OPEN", "1")
        assert auth._is_demo_teacher_open() is True

    def test_expiry_is_in_the_future(self):
        token = auth.create_token("u-ttl")
        payload = auth.verify_token(token)
        assert payload["exp"] > int(time.time()), "新签发的 token 不应立即过期"
