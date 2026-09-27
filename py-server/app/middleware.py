# ============================================================
# app/middleware.py — HTTP 中间件（M-4 拆分，自 main.py 下沉）
#
# 注册顺序即 Starlette 的包装顺序，改动前请确认是否影响：
#   CORSMiddleware → GZip → metrics → security_headers → request_size_limit → rate_limit
# （SPAFallback 由 app/static_sites.py 最后安装，属 SPA 路由职责，不在此处。）
#
# CORS 策略（D3）：production 仅允许 CORS_ALLOW_ORIGINS 白名单；
# dev 用 allow_origin_regex 放行本机 loopback 与 LAN（覆盖 vite 端口 5173-5181）。
# ⚠️ 安全测试的 CORS 静态复查以本文件为单一真值源
#    （tests/test_wave_a_security.py::TestCORSStaticReview）。
# ============================================================

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response

from app.env import is_production, logger

# ── D5：进程内指标收集（/metrics，Prometheus 文本格式）──
from shared.metrics import record_request, inc_inflight

__all__ = [
    "install", "metrics_middleware", "security_headers_middleware",
    "request_size_limit_middleware", "rate_limit_middleware",
    "CSP_PRODUCTION", "CSP_DEV", "PERMISSIONS_POLICY",
]

# ── 安全响应头 (F-016: CSP / X-Frame-Options / HSTS / Permissions-Policy) ──
# 合理默认值：生产构建 Vite 无内联脚本（Vue SFC 编译后独立 .js），
# 开发模式 HMR 需要 unsafe-inline；此处仅生产加固 script-src。
# style-src 保留 unsafe-inline：Vue SFC scoped style 和 Google Fonts 内联依赖。
# 注：完整的 nonce/hash CSP 需服务端动态注入，属后续加固项。
CSP_PRODUCTION = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "media-src 'self' blob:; "
    "connect-src 'self' ws: wss:; "
    "frame-ancestors 'self';"
)
CSP_DEV = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "   # Vite HMR 热重载需要内联脚本
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "media-src 'self' blob:; "
    "connect-src 'self' ws: wss:; "
    "frame-ancestors 'self';"
)
# 限制敏感浏览器特性（摄像头/麦克风/地理位置/支付等），降低被滥用于越权采集的风险
PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
    "magnetometer=(), microphone=(), payment=(), usb=(), interest-cohort=()"
)

# ── 请求体大小限制 (F-018: 防超大请求体 / DoS) ──
# 仅拦截带 Content-Length 且超标的请求；chunked/流式（无 Content-Length）不受影响。
MAX_REQUEST_BYTES = int(os.environ.get("MAX_REQUEST_BYTES", str(50 * 1024 * 1024)))

# ── API 速率限制 (#11: 防高成本 LLM/生成端点滥用 · 成本失控 · DoS) ──
# 进程内滑动窗口计数器（单进程部署，无需 Redis）。按 (客户端 IP, 路由组) 限流。
# 仅对高成本生成/LLM 端点（chat/agents/langgraph/xfyun/sandbox/multimodal/skills）
# 生效；只读、静态资源、健康检查路径一律放行。多进程/多实例部署应改用 Redis 共享计数。
RATE_LIMIT_WINDOW = float(os.environ.get("RATE_LIMIT_WINDOW", "60"))  # 滑动窗口秒数
RATE_LIMIT_DEFAULT = int(os.environ.get("RATE_LIMIT_PER_MIN", "30"))  # 默认每窗口令牌数

# 路径前缀 → 限流组（命中即限流）
RATE_GROUPS = {
    "/api/chat": "chat",
    "/api/agents": "agents",
    "/api/langgraph": "langgraph",
    "/api/xfyun": "xfyun",
    "/api/sandbox": "sandbox",
    "/api/multimodal": "multimodal",
    "/api/skills": "skills",
}

_rate_buckets: "defaultdict[tuple, deque[float]]" = defaultdict(deque)
_rate_lock = threading.Lock()


def _rate_group_limit(group: str) -> int:
    return int(os.environ.get(f"RATE_{group.upper()}", str(RATE_LIMIT_DEFAULT)))


def _client_ip(request: Request) -> str:
    # 前置反代可能通过 X-Forwarded-For / X-Real-IP 传递真实客户端 IP
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"


# ── 各中间件实现 ──
# 注：以下函数由 install() 注册到 app；独立成具名函数是为了可单测（不必起 HTTP 服务）。


async def metrics_middleware(request: Request, call_next):
    inc_inflight(1)
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        inc_inflight(-1)
        latency = time.perf_counter() - start
        record_request(request.url.path, status, latency)
        logger.info(
            "request %s %s -> %s (%.0fms)",
            request.method, request.url.path, status, latency * 1000,
        )


async def security_headers_middleware(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "no-referrer"
    # 浏览器 WASI（/code-lab 的 C/C++ 编译实验室）依赖跨源隔离，
    # 需同时返回 COOP/COEP；与 vite dev server headers 保持一致，
    # 生产网关/反向代理不可移除这两个头（移除后 SharedArrayBuffer 不可用）。
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"

    production = is_production()
    csp = CSP_PRODUCTION if production else CSP_DEV
    # /showcase 路径放行 unsafe-inline：评委展示用原型 HTML 含内联脚本，
    # 生产 CSP `script-src 'self'` 会阻断其运行，故对该路径沿用开发 CSP。
    if production and request.url.path.startswith("/showcase"):
        csp = CSP_DEV

    response.headers["Content-Security-Policy"] = csp
    response.headers["Permissions-Policy"] = PERMISSIONS_POLICY
    # 仅生产环境（HTTPS）强制 HSTS；开发环境不发送，避免本地 http 被浏览器拒掉
    if production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


async def request_size_limit_middleware(request: Request, call_next) -> Response:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            body_len = int(content_length)
        except ValueError as _e:
            logger.debug("Content-Length 非整数，按 0 处理: %s", _e)
            body_len = 0
        if body_len > MAX_REQUEST_BYTES:
            logger.warning(
                "请求体过大被拒绝 path=%s bytes=%d limit=%d",
                request.url.path, body_len, MAX_REQUEST_BYTES,
            )
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "PAYLOAD_TOO_LARGE",
                        "message": "请求体过大，请减小上传内容后重试",
                    }
                },
            )
    return await call_next(request)


async def rate_limit_middleware(request: Request, call_next) -> Response:
    # 测试态或显式关闭时放行：测试流量非真实流量，不计入滑动窗口限流；
    # 生产环境默认 RATE_LIMIT_ENABLED=true，限流器始终生效，不受影响。
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("RATE_LIMIT_ENABLED", "true").lower() != "true":
        return await call_next(request)
    path = request.url.path
    group = next((g for p, g in RATE_GROUPS.items() if path.startswith(p)), None)
    if group is None:
        return await call_next(request)

    now = time.monotonic()
    ip = _client_ip(request)
    limit = _rate_group_limit(group)
    key = (ip, group)
    with _rate_lock:
        dq = _rate_buckets[key]
        # 丢弃窗口外的旧时间戳
        while dq and now - dq[0] >= RATE_LIMIT_WINDOW:
            dq.popleft()
        if len(dq) >= limit:
            retry_after = max(int(RATE_LIMIT_WINDOW - (now - dq[0])) + 1, 1)
            logger.warning("速率限制触发 group=%s ip=%s path=%s", group, ip, path)
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": f"请求过于频繁，请 {retry_after} 秒后重试",
                    }
                },
            )
        dq.append(now)
    return await call_next(request)


def _install_cors(app: FastAPI) -> None:
    """安装 CORS 中间件。

    生产环境（NETLEARN_ENV==production）才允许显式白名单；
    dev 用 allow_origin_regex 放行本机 loopback 与 LAN，覆盖 vite 端口 5173-5181。
    """
    cors_env = (
        os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
        or os.environ.get("CORS_ORIGINS", "").strip()
    )
    cors_origins = [o.strip() for o in cors_env.split(",") if o.strip()] if cors_env else []
    cors_kwargs = {
        "allow_credentials": True,
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Authorization", "Content-Type"],
    }
    if is_production():
        # 生产：仅显式白名单；缺失则不允许任何跨域（最小权限，杜绝通配 *）
        cors_kwargs["allow_origins"] = cors_origins
    else:
        # 开发：regex 放行 localhost / 127.0.0.1 / IPv6 loopback / 本机 LAN（含 vite 5173-5181）
        # 注意：allow_credentials=True 时不可使用 "*"，故用正则 + 可选显式白名单
        cors_kwargs["allow_origin_regex"] = (
            r"^https?://(localhost|127\.0\.0\.1|\[::1\]"
            r"|192\.168\.\d{1,3}\.\d{1,3}"
            r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})"
            r"(:(\d{1,5}))?$"
        )
        cors_kwargs["allow_origins"] = cors_origins
    app.add_middleware(CORSMiddleware, **cors_kwargs)


def install(app: FastAPI) -> None:
    """按顺序安装全部全局中间件（不含 SPA fallback，见 app/static_sites.py）。"""
    _install_cors(app)

    # ── GZip 压缩（对所有 ≥1KB 的 API 响应启用，减少传输体积）──
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # 以下 http 中间件的注册顺序 = Starlette 包装顺序，保持与拆分前一致
    app.middleware("http")(metrics_middleware)
    app.middleware("http")(security_headers_middleware)
    app.middleware("http")(request_size_limit_middleware)
    app.middleware("http")(rate_limit_middleware)
