# ============================================================
# 安全审计日志 — 记录所有安全相关事件
# 格式: [timestamp] LEVEL | user=<user_id> ip=<client_ip>
#       action=<action> result=<result> detail=<detail>
#
# 增强（审计日志页）：log_event 同时写入内存环形缓冲区，
# 供 GET /api/audit/logs 查询近期拦截/告警事件（admin/teacher 可查）。
# ============================================================

import logging
import time
import threading
from collections import deque

audit_logger = logging.getLogger("netlearn.audit")
audit_logger.setLevel(logging.INFO)

# 确保审计日志有独立文件 handler（如果已配置 root logger 则自动继承）
_audit_handler = logging.StreamHandler()
_audit_handler.setFormatter(logging.Formatter(
    "%(asctime)s [AUDIT] %(levelname)s | %(message)s"
))
if not audit_logger.handlers:
    audit_logger.addHandler(_audit_handler)

# ── 内存环形缓冲区：存储近期审计事件（供 API 查询）──
_AUDIT_BUFFER: deque = deque(maxlen=500)
_BUFFER_LOCK = threading.Lock()


def log_event(
    action: str,
    user_id: str = "anonymous",
    ip: str = "unknown",
    result: str = "success",
    detail: str = "",
):
    """记录安全事件

    参数:
        action:   事件类型（如 login, config_change, sandbox_exec, knowledge_modify）
        user_id:  用户标识
        ip:       客户端 IP
        result:   success / failure / blocked
        detail:   补充说明
    """
    timestamp = time.time()
    msg = f"user={user_id} ip={ip} action={action} result={result}"
    if detail:
        msg += f" detail={detail}"

    if result == "failure":
        audit_logger.warning(msg)
    elif result == "blocked":
        audit_logger.warning(msg)
    else:
        audit_logger.info(msg)

    # 写入环形缓冲区（供审计日志页查询）
    event = {
        "timestamp": timestamp,
        "time_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)),
        "user_id": user_id,
        "ip": ip,
        "action": action,
        "result": result,
        "detail": detail[:500] if detail else "",
    }
    with _BUFFER_LOCK:
        _AUDIT_BUFFER.append(event)


def query_audit_logs(limit: int = 100, action: str = None, result: str = None) -> list[dict]:
    """查询近期审计日志（供 GET /api/audit/logs 调用）。

    参数:
        limit:  返回条数上限（默认 100，最大 500）
        action: 按事件类型过滤（可选）
        result: 按结果过滤（可选：success/failure/blocked）
    返回:
        按时间倒序排列的事件列表
    """
    with _BUFFER_LOCK:
        events = list(_AUDIT_BUFFER)
    # 过滤
    if action:
        events = [e for e in events if e.get("action") == action]
    if result:
        events = [e for e in events if e.get("result") == result]
    # 倒序（最新在前）
    events.reverse()
    return events[:min(limit, 500)]


def get_audit_stats() -> dict:
    """审计事件统计摘要（供看板）。"""
    with _BUFFER_LOCK:
        events = list(_AUDIT_BUFFER)
    total = len(events)
    blocked = sum(1 for e in events if e.get("result") == "blocked")
    failure = sum(1 for e in events if e.get("result") == "failure")
    # 按事件类型分组计数
    by_action: dict[str, int] = {}
    for e in events:
        a = e.get("action", "unknown")
        by_action[a] = by_action.get(a, 0) + 1
    return {
        "total": total,
        "blocked": blocked,
        "failure": failure,
        "success": total - blocked - failure,
        "by_action": by_action,
    }
