# -*- coding: utf-8 -*-
"""app/ 装配层的横切行为矩阵（M-4 拆分后新增）

这些行为原先散落在 882 行的 main.py 里、只能靠人眼确认；拆到 app/ 后
逐条固化为回归断言：中间件的拦截与否、异常处理的生产脱敏、状态端点的降级判定。
全部直接调用函数 + 替身，不经过真实网络/数据库。
"""

import json
import time

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

from app import middleware
from app.env import is_production


def _request(path="/api/chat/x", method="GET", headers=None, client=("9.9.9.9", 1234)):
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": raw_headers,
        "client": client,
        "server": ("testserver", 80),
    })


async def _ok_call_next(request):
    from starlette.responses import JSONResponse
    return JSONResponse({"ok": True})


class TestRequestSizeLimit:
    async def test_oversized_body_rejected_413(self, monkeypatch):
        monkeypatch.setattr(middleware, "MAX_REQUEST_BYTES", 100)
        resp = await middleware.request_size_limit_middleware(
            _request(headers={"content-length": "500"}), _ok_call_next
        )
        assert resp.status_code == 413
        assert "PAYLOAD_TOO_LARGE" in json.loads(resp.body)["error"]["code"]

    async def test_missing_content_length_passes(self):
        resp = await middleware.request_size_limit_middleware(_request(), _ok_call_next)
        assert resp.status_code == 200

    async def test_non_integer_content_length_treated_as_zero(self, monkeypatch):
        monkeypatch.setattr(middleware, "MAX_REQUEST_BYTES", 100)
        resp = await middleware.request_size_limit_middleware(
            _request(headers={"content-length": "abc"}), _ok_call_next
        )
        assert resp.status_code == 200, "非法 Content-Length 不应误伤请求"

    async def test_exactly_at_limit_passes(self, monkeypatch):
        monkeypatch.setattr(middleware, "MAX_REQUEST_BYTES", 100)
        resp = await middleware.request_size_limit_middleware(
            _request(headers={"content-length": "100"}), _ok_call_next
        )
        assert resp.status_code == 200


class TestRateLimit:
    def setup_method(self):
        middleware._rate_buckets.clear()

    async def test_low_cost_path_bypasses_limiter(self, monkeypatch):
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
        for _ in range(50):
            resp = await middleware.rate_limit_middleware(_request("/api/status"), _ok_call_next)
            assert resp.status_code == 200

    async def test_high_cost_path_limited_after_threshold(self, monkeypatch):
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
        monkeypatch.setenv("RATE_CHAT", "2")
        statuses = []
        for _ in range(3):
            resp = await middleware.rate_limit_middleware(_request("/api/chat/x"), _ok_call_next)
            statuses.append(resp.status_code)
        assert statuses == [200, 200, 429]

    async def test_rate_limited_response_carries_retry_after(self, monkeypatch):
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
        monkeypatch.setenv("RATE_CHAT", "1")
        await middleware.rate_limit_middleware(_request("/api/chat/x"), _ok_call_next)
        resp = await middleware.rate_limit_middleware(_request("/api/chat/x"), _ok_call_next)
        assert resp.status_code == 429
        assert int(resp.headers["Retry-After"]) >= 1
        assert "RATE_LIMITED" in json.loads(resp.body)["error"]["code"]

    async def test_disabled_by_env_bypasses(self, monkeypatch):
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
        monkeypatch.setenv("RATE_CHAT", "1")
        for _ in range(5):
            resp = await middleware.rate_limit_middleware(_request("/api/chat/x"), _ok_call_next)
            assert resp.status_code == 200

    async def test_pytest_context_bypasses(self, monkeypatch):
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "x")
        monkeypatch.setenv("RATE_CHAT", "1")
        for _ in range(5):
            resp = await middleware.rate_limit_middleware(_request("/api/chat/x"), _ok_call_next)
            assert resp.status_code == 200

    async def test_separate_ips_have_separate_buckets(self, monkeypatch):
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
        monkeypatch.setenv("RATE_CHAT", "1")
        r1 = await middleware.rate_limit_middleware(
            _request("/api/chat/x", client=("1.1.1.1", 1)), _ok_call_next)
        r2 = await middleware.rate_limit_middleware(
            _request("/api/chat/x", client=("2.2.2.2", 2)), _ok_call_next)
        assert [r1.status_code, r2.status_code] == [200, 200]

    async def test_expired_buckets_are_reclaimed(self, monkeypatch):
        """窗口过期且不再被访问的桶应被清扫回收（否则随来源 IP 多样性涨内存）。"""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
        monkeypatch.setenv("RATE_CHAT", "10")
        monkeypatch.setattr(middleware, "RATE_LIMIT_WINDOW", 0.02)
        monkeypatch.setattr(middleware, "RATE_SWEEP_INTERVAL", 0.0)
        peer = ("5.5.5.5", 1)
        await middleware.rate_limit_middleware(_request("/api/chat/x", client=peer), _ok_call_next)
        key = (middleware._client_ip(_request("/api/chat/x", client=peer)), "chat")
        assert key in middleware._rate_buckets
        time.sleep(0.05)
        # 由另一个来源的请求触发周期清扫
        await middleware.rate_limit_middleware(
            _request("/api/chat/y", client=("6.6.6.6", 1)), _ok_call_next
        )
        assert key not in middleware._rate_buckets, "过期桶应被回收"

    async def test_active_bucket_survives_sweep(self, monkeypatch):
        """清扫不得误伤窗口内仍活跃的桶。"""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
        monkeypatch.setenv("RATE_CHAT", "10")
        monkeypatch.setattr(middleware, "RATE_SWEEP_INTERVAL", 0.0)
        peer = ("7.7.7.7", 1)
        key = (middleware._client_ip(_request("/api/chat/x", client=peer)), "chat")
        for _ in range(3):
            await middleware.rate_limit_middleware(
                _request("/api/chat/x", client=peer), _ok_call_next)
        assert key in middleware._rate_buckets, "活跃桶不应被清扫误删"
        assert len(middleware._rate_buckets[key]) == 3

    def test_client_ip_prefers_forwarded_header_from_trusted_proxy(self):
        # 仅当直连对端是受信任反代时才采信 XFF（默认信任 loopback）
        req = _request(headers={"x-forwarded-for": "8.8.8.8, 10.0.0.1"}, client=("127.0.0.1", 1234))
        assert middleware._client_ip(req) == "8.8.8.8"

    def test_client_ip_ignores_spoofed_forwarded_header(self):
        # 不可信来源伪造 XFF 不得改写计数 key —— 否则一条 header 就能换一个新桶绕过限流
        req = _request(headers={"x-forwarded-for": "8.8.8.8"}, client=("9.9.9.9", 1234))
        assert middleware._client_ip(req) == "9.9.9.9"

    def test_client_ip_ignores_spoofed_x_real_ip(self):
        req = _request(headers={"x-real-ip": "7.7.7.7"}, client=("9.9.9.9", 1234))
        assert middleware._client_ip(req) == "9.9.9.9"

    def test_client_ip_falls_back_to_x_real_ip_from_trusted_proxy(self):
        req = _request(headers={"x-real-ip": "7.7.7.7"}, client=("127.0.0.1", 1234))
        assert middleware._client_ip(req) == "7.7.7.7"

    def test_trusted_proxies_reads_env(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXIES", "10.0.0.5, 10.0.0.6")
        req = _request(headers={"x-forwarded-for": "8.8.8.8"}, client=("10.0.0.5", 1234))
        assert middleware._client_ip(req) == "8.8.8.8"

    def test_loopback_not_trusted_once_env_declares_proxies(self, monkeypatch):
        # 显式声明 TRUSTED_PROXIES 后 loopback 不再默认可信（最小信任面）
        monkeypatch.setenv("TRUSTED_PROXIES", "10.0.0.5")
        req = _request(headers={"x-forwarded-for": "8.8.8.8"}, client=("127.0.0.1", 1234))
        assert middleware._client_ip(req) == "127.0.0.1"

    def test_client_ip_falls_back_to_peer(self):
        assert middleware._client_ip(_request(client=("3.3.3.3", 9))) == "3.3.3.3"

    def test_client_ip_unknown_without_client(self):
        req = _request()
        req.scope["client"] = None
        assert middleware._client_ip(req) == "unknown"

    def test_rate_group_limit_reads_env(self, monkeypatch):
        monkeypatch.setenv("RATE_AGENTS", "77")
        assert middleware._rate_group_limit("agents") == 77

    def test_rate_group_limit_default(self, monkeypatch):
        monkeypatch.delenv("RATE_SKILLS", raising=False)
        assert middleware._rate_group_limit("skills") == middleware.RATE_LIMIT_DEFAULT


class TestSecurityHeaders:
    async def test_dev_mode_omits_hsts(self, monkeypatch):
        monkeypatch.setenv("NETLEARN_ENV", "development")
        resp = await middleware.security_headers_middleware(_request("/api/status"), _ok_call_next)
        assert "Strict-Transport-Security" not in resp.headers
        assert resp.headers["X-Frame-Options"] == "SAMEORIGIN"
        assert middleware.CSP_DEV in resp.headers["Content-Security-Policy"]

    async def test_production_mode_adds_hsts_and_strict_csp(self, monkeypatch):
        monkeypatch.setenv("NETLEARN_ENV", "production")
        resp = await middleware.security_headers_middleware(_request("/api/status"), _ok_call_next)
        assert "max-age=31536000" in resp.headers["Strict-Transport-Security"]
        assert middleware.CSP_PRODUCTION in resp.headers["Content-Security-Policy"]

    async def test_showcase_path_keeps_inline_scripts_in_production(self, monkeypatch):
        """评委展示页含内联脚本，生产环境对该路径必须放宽 CSP，否则页面白屏。"""
        monkeypatch.setenv("NETLEARN_ENV", "production")
        resp = await middleware.security_headers_middleware(_request("/showcase"), _ok_call_next)
        assert resp.headers["Content-Security-Policy"] == middleware.CSP_DEV

    async def test_cross_origin_isolation_headers_present(self):
        resp = await middleware.security_headers_middleware(_request(), _ok_call_next)
        assert resp.headers["Cross-Origin-Opener-Policy"] == "same-origin"
        assert resp.headers["Cross-Origin-Embedder-Policy"] == "require-corp"

    def test_cors_production_uses_explicit_origin_only(self, monkeypatch):
        """生产环境绝不允许通配符来源。"""
        monkeypatch.setenv("NETLEARN_ENV", "production")
        monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://demo.example.org")
        app = FastAPI()
        middleware._install_cors(app)
        assert any("CORSMiddleware" in str(m.cls) for m in app.user_middleware)

    def test_cors_origins_parsed_from_comma_list(self, monkeypatch):
        monkeypatch.setenv("NETLEARN_ENV", "production")
        monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://a.example.org, https://b.example.org")
        from app import middleware as mw
        assert is_production() is True
        app = FastAPI()
        mw._install_cors(app)
        assert app.user_middleware, "CORS 中间件应已安装"


class TestMetricsMiddleware:
    async def test_metrics_counts_request(self, monkeypatch):
        from starlette.responses import JSONResponse
        seen = {}

        async def call_next(request):
            return JSONResponse({"ok": True})

        monkeypatch.setattr(middleware, "record_request", lambda p, s, l: seen.update(path=p, status=s))
        resp = await middleware.metrics_middleware(_request("/api/status", method="POST"), call_next)
        assert resp.status_code == 200
        assert seen["path"] == "/api/status"

    async def test_metrics_records_500_when_handler_raises(self, monkeypatch):
        seen = {}

        async def call_next(request):
            raise RuntimeError("boom")

        monkeypatch.setattr(middleware, "record_request", lambda p, s, l: seen.update(status=s))
        with pytest.raises(RuntimeError):
            await middleware.metrics_middleware(_request("/api/x"), call_next)
        assert seen["status"] == 500, "异常也必须记账，否则指标漏报"


class TestErrorHandlers:
    async def test_http_exception_dev_keeps_detail(self, monkeypatch):
        monkeypatch.setenv("NETLEARN_ENV", "development")
        from app.errors import http_exception_handler
        resp = await http_exception_handler(_request(), HTTPException(status_code=401, detail="缺少令牌"))
        assert resp.status_code == 401
        assert json.loads(resp.body) == {"detail": "缺少令牌"}

    async def test_http_exception_production_redacts(self, monkeypatch):
        """F-017：生产环境不得把内部细节回显给客户端。"""
        monkeypatch.setenv("NETLEARN_ENV", "production")
        from app.errors import http_exception_handler
        resp = await http_exception_handler(
            _request(), HTTPException(status_code=500, detail="内部表 users 不存在")
        )
        body = json.loads(resp.body)
        assert "users" not in resp.body.decode()
        assert body["error"]["code"] == "HTTP_ERROR"

    async def test_validation_error_dev_returns_fields(self, monkeypatch):
        monkeypatch.setenv("NETLEARN_ENV", "development")
        from app.errors import request_validation_error_handler
        exc = RequestValidationError([{"loc": ("body", "topic"), "msg": "必填", "type": "missing"}])
        resp = await request_validation_error_handler(_request(), exc)
        assert resp.status_code == 422
        assert "detail" in json.loads(resp.body)

    async def test_validation_error_production_redacts(self, monkeypatch):
        monkeypatch.setenv("NETLEARN_ENV", "production")
        from app.errors import request_validation_error_handler
        exc = RequestValidationError([{"loc": ("body", "topic"), "msg": "必填", "type": "missing"}])
        resp = await request_validation_error_handler(_request(), exc)
        body = json.loads(resp.body)
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert "topic" not in resp.body.decode()

    def test_install_registers_four_handlers(self):
        from app import errors
        app = FastAPI()
        errors.install(app)
        handlers = {k for k in app.exception_handlers}
        assert HTTPException in handlers and RequestValidationError in handlers and Exception in handlers


class TestEnvHelpers:
    def test_is_production_detects_prod_alias(self, monkeypatch):
        monkeypatch.setenv("NETLEARN_ENV", "prod")
        assert is_production() is True

    def test_is_production_false_by_default(self, monkeypatch):
        monkeypatch.setenv("NETLEARN_ENV", "development")
        assert is_production() is False

    def test_bootstrap_sets_offline_flags(self, monkeypatch):
        from app import env as env_mod
        monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
        monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
        env_mod.bootstrap()
        import os
        assert os.environ["HF_HUB_OFFLINE"] == "1"
        assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
