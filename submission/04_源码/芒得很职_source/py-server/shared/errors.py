# ============================================================
# 统一错误处理 — 领域异常层级 + 全局处理器
# 消除 HTTPException / JSON error / SSE error 三种模式混用
# ============================================================

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("netlearn.errors")


class DomainError(Exception):
    """领域异常基类 — 所有业务错误继承此类"""

    def __init__(self, code: str, message: str, status: int = 400):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


class KnowledgeNotFoundError(DomainError):
    def __init__(self, query: str = ""):
        super().__init__("KNOWLEDGE_NOT_FOUND", f"未找到相关知识: {query}" if query else "未找到相关知识", 404)


class LLMUnavailableError(DomainError):
    def __init__(self, detail: str = "所有LLM通道不可用"):
        super().__init__("LLM_UNAVAILABLE", detail, 503)


class VectorDBError(DomainError):
    def __init__(self, detail: str = "向量数据库操作失败"):
        super().__init__("VECTOR_DB_ERROR", detail, 500)


class ValidationError(DomainError):
    def __init__(self, detail: str = "参数校验失败"):
        super().__init__("VALIDATION_ERROR", detail, 422)


class SandboxError(DomainError):
    def __init__(self, detail: str = "代码执行失败"):
        super().__init__("SANDBOX_ERROR", detail, 400)


class ResourceNotFoundError(DomainError):
    def __init__(self, resource: str = "资源"):
        super().__init__("RESOURCE_NOT_FOUND", f"{resource}不存在", 404)


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """全局领域异常处理器 — 统一错误响应格式"""
    return JSONResponse(
        status_code=exc.status,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
            }
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局兜底异常处理器 — 防止堆栈信息泄露"""
    logger.error(f"未处理异常: {type(exc).__name__}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "服务器内部错误，请稍后重试",
            }
        },
    )
