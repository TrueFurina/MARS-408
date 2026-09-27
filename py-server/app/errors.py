# ============================================================
# app/errors.py — 统一异常处理注册（M-4 拆分，自 main.py 下沉）
#
# 统一错误处理 (D-08) / F-017 错误消息脱敏：
#   - DomainError：由 shared.errors.domain_error_handler 映射为 4xx/5xx
#   - HTTPException：dev 返回 detail 原文（保持 {"detail": ...} 契约）；
#     production 返回通用文案、保留 status_code，完整 detail 写入结构化日志。
#   - RequestValidationError（422）：dev 返回字段级错误；production 脱敏为通用文案。
#   - 未捕获异常：unhandled_exception_handler 统一返回 500 通用文案并记完整堆栈。
# ============================================================

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.env import is_production, logger
from shared.errors import DomainError, domain_error_handler, unhandled_exception_handler

__all__ = [
    "install", "http_exception_handler", "request_validation_error_handler",
]


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    status_code = exc.status_code
    if is_production():
        logger.error(
            "HTTPException status=%s detail=%s path=%s",
            status_code, exc.detail, request.url.path,
        )
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": "HTTP_ERROR", "message": "请求处理失败，请稍后重试"}},
        )
    return JSONResponse(status_code=status_code, content={"detail": exc.detail})


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    status_code = getattr(exc, "status_code", 422)
    if is_production():
        logger.error(
            "请求参数校验失败 path=%s errors=%s",
            request.url.path, exc.errors(),
        )
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": "VALIDATION_ERROR", "message": "请求参数不合法"}},
        )
    return JSONResponse(status_code=status_code, content={"detail": exc.errors()})


def install(app: FastAPI) -> None:
    """安装全部异常处理器（注册顺序无关，此处沿用拆分前顺序）。"""
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
