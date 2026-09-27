# ============================================================
# app/env.py — 进程级环境引导（M-4 拆分，自 main.py 头部下沉）
#
# 必须在 import 任何业务模块之前调用 bootstrap()，顺序不可换：
#   1) HF / Transformers 离线标记：本机无外网时，重排模型 (BAAI/bge-reranker-base)
#      会在每次请求尝试下载并超时重试约 90s，同步阻塞事件循环导致
#      LangGraph 协作流（retriever→rerank）卡死。必须在可能加载 transformers
#      的任何模块之前设置。
#   2) .env 加载：必须在 import 任何模块级读取 os.environ 的模块（如 shared.auth）
#      之前，否则 AUTH_SECRET 为空 → 每次启动生成临时密钥 → 重启后已签发
#      Token 全部失效。
#   3) 结构化日志：尽早启用以覆盖启动期与关键错误（D11）。
#
# 本模块刻意只依赖标准库 + config + shared.logging_config，
# 不得引入 FastAPI / db / torch 等重依赖（否则会破坏上述「最先执行」保证）。
# ============================================================

import logging
import os

__all__ = ["bootstrap", "logger", "is_production", "ENV"]

logger = logging.getLogger("netlearn")


def _env_value() -> str:
    """读取 NETLEARN_ENV（每次调用都重读 os.environ，便于测试 monkeypatch）。"""
    return os.environ.get("NETLEARN_ENV", "development").lower()


# 兼容旧引用：模块级快照语义保留为「首次读取」，但所有消费方一律走 is_production()
ENV = _env_value()


def bootstrap() -> logging.Logger:
    """执行启动时环境变量与日志的一次性引导，返回应用级 logger。"""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    from config import _load_dotenv
    _load_dotenv()

    from shared.logging_config import setup_structured_logging
    _log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    setup_structured_logging(getattr(logging, _log_level, logging.INFO))
    return logger


def is_production() -> bool:
    """是否生产环境（production / prod）。

    动态读取而非导入期快照：与 shared.auth 等模块的既有约定一致，
    也便于安全类测试用 monkeypatch.setenv("NETLEARN_ENV", ...) 直接生效。
    """
    return _env_value() in ("production", "prod")
