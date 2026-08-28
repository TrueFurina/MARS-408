# ============================================================
# 结构化日志（D11）
# JSON formatter：每条日志输出 {ts, level, logger, msg[, exc]}。
# 与现有 logger.info(...) / logger.error(...) 调用完全兼容（包装而非破坏）：
#   仅替换「netlearn」根日志器的处理器与格式，其余代码无需改动。
# ============================================================

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """将 LogRecord 序列化为单行 JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        log: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            log["exc"] = self.formatException(record.exc_info)
        return json.dumps(log, ensure_ascii=False)


def setup_structured_logging(level: int = logging.INFO):
    """将 ``netlearn`` 层级日志器切换为结构化(JSON)输出。

    仅作用于名为 ``netlearn`` 的日志器（及其后代 ``netlearn.*``），
    不影响 uvicorn 等第三方日志器。返回配置后的 logger。
    """
    logger = logging.getLogger("netlearn")
    # 清掉已有 handler，避免重复输出
    for h in list(logger.handlers):
        logger.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    logger.setLevel(level)
    # 阻止向 root 冒泡（root 默认无 handler，但防止第三方 root 配置重复输出）
    logger.propagate = False
    return logger
