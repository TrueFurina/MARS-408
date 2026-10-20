# -*- coding: utf-8 -*-
"""限流边界回归：恰好 N 次放行、第 N+1 次拦截（REA #175 边界测试 / #30 常量原语）

为什么单独写一条：此前的限流用例只证明「能拦」，没证明「在第几次开始拦」。
阈值写错（20 写成 200）、窗口单位写错（3600 写成 60）时，功能性用例照样绿，
只有真人试用时才会以「一个班注册到第 4 个人被卡」的形式暴露
（2026-10-15 真实发生过，见 api/auth.py register 的 docstring）。

本测试的三条契约：
  1. 注册面：同一 IP 连续 REGISTER_PER_HOUR_PER_IP 次放行，第 N+1 次 422
     「操作过于频繁」；**阈值从 shared/limits.py 读取**，实现改 30 时本测试
     自动跟着变成 31 次——不会出现"测试测的是旧数字"。
  2. 计数主体是 IP 而非全局：A 出口打满后，B 出口仍放行
     （否则一个班共用出口时第 21 人之后的**全校**都被锁死）。
  3. 三个认证阈值都只有一处定义：api/auth.py 源码里不得再出现
     `max_requests=20` / `window=3600` 之类的字面量。

运行：python -m pytest tests/test_rate_limit_boundary.py -q
"""

import asyncio
import os
import sys

import pytest
from starlette.requests import Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.auth as auth_api  # noqa: E402
from shared import limits  # noqa: E402
from shared.errors import ValidationError  # noqa: E402


def _request(ip: str) -> Request:
    """构造最小 ASGI Request：只需要 request.client.host。"""
    return Request({"type": "http", "method": "POST", "path": "/api/auth/register",
                    "headers": [], "client": (ip, 12345)})


@pytest.fixture
def fake_user(monkeypatch):
    """把注册落库替换成内存用户：本测试只关心限流闸门，不关心持久化。"""
    monkeypatch.setattr(auth_api, "create_user",
                        lambda username, password, display_name="": {
                            "id": f"id-{username}", "username": username,
                            "role": "student", "display_name": display_name,
                        })
    monkeypatch.setattr(auth_api, "create_token", lambda uid, role: f"token-{uid}")
    monkeypatch.setattr(auth_api, "log_event", lambda *a, **kw: None)
    return True


def _register(ip: str, n: int):
    """以 IP 身份连续注册 n 次，返回每次的结果码（'ok' 或异常 message）。"""
    codes = []
    for i in range(n):
        req = auth_api.RegisterRequest(username=f"stu_{abs(hash(ip)) % 10**6}_{i}",
                                       password="Passw0rd!x")
        try:
            asyncio.run(auth_api.register(req, _request(ip)))
            codes.append("ok")
        except ValidationError as e:
            codes.append(e.message)
    return codes


def test_threshold_is_named_not_literal():
    """阈值必须是具名常量，且默认值与「一个班能同时注册」的现场结论一致。"""
    assert limits.REGISTER_PER_HOUR_PER_IP == 20, (
        "注册阈值默认值变了：现场结论是一个班 5–10 人 + 重试余量 = 20。"
        "改之前请先确认 api/auth.py register 的阈值来历段落同步更新。"
    )
    assert limits.WINDOW_REGISTER_SECONDS == 3600
    assert limits.LOGIN_PER_MINUTE_PER_IP == 10
    assert limits.LOGIN_PER_15MIN_PER_USER == 5


def test_register_allows_exactly_n_then_blocks(fake_user):
    """第 N 次放行、第 N+1 次拦截——边界值本身是断言语义。"""
    ip = "203.0.113.7"          # TEST-NET-3，专用于文档示例，不会撞真实 IP 预算
    n = limits.REGISTER_PER_HOUR_PER_IP
    codes = _register(ip, n + 1)

    assert codes[:n] == ["ok"] * n, f"前 {n} 次应全部放行，实测 {codes[:n]}"
    assert codes[n] != "ok", f"第 {n + 1} 次应被拦，实测放行"
    assert "频繁" in codes[n], f"超限文案应为『操作过于频繁，请稍后再试』，实测 {codes[n]!r}"
    # 再补两次：窗口内必须持续拦截，不能"拦一次就放行"（非滑动窗口的典型 bug）
    assert _register(ip, 2) == [codes[n], codes[n]]


def test_limit_is_per_ip_not_global(fake_user):
    """A 出口打满后，B 出口仍放行——限流主体是 IP，不是进程。"""
    a = "198.51.100.11"
    b = "198.51.100.12"
    assert _register(a, limits.REGISTER_PER_HOUR_PER_IP)[-1] == "ok"
    assert _register(a, 1)[0] != "ok", "同一 IP 第 N+1 次应被拦"
    assert _register(b, 1) == ["ok"], "另一 IP 不应被 A 的计数牵连"


def test_auth_source_has_no_rate_limit_magic_numbers():
    """静态守卫：阈值字面量不得回流到 api/auth.py。

    允许出现的数字是 HTTP 状态码/字段长度等**非限流**语义；
    限流参数只认 shared/limits.py 里的具名常量。
    """
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "api", "auth.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    for bad in ("max_requests=20", "window=3600", "max_requests=10",
                "window=60", "max_requests=5", "window=900"):
        assert bad not in src, (
            f"api/auth.py 出现限流字面量 {bad!r}——请改用 shared/limits.py 的常量，"
            "否则测试无法确认自己测的是生产值。"
        )
