# ============================================================
# WS1 覆盖率补全 — shared/audit.py（安全审计日志）
#
# 此前在测试套件中零引用（grep shared.<mod> 无命中），却直接支撑
# GET /api/audit/logs（admin/teacher 可查）与看板统计，属高价值盲区。
# 纯标准库（logging/time/threading/collections），可脱离 conftest 独立运行：
#   py-server/.venv/Scripts/python.exe -m pytest tests/test_shared_audit.py --noconftest -q
#
# 覆盖：log_event 字段/默认值/超长 detail 截断/结果→日志级别、
#       环形缓冲上界 500、query_audit_logs 倒序+过滤+limit 封顶、
#       get_audit_stats 计数
# ================================================================

import logging

from shared.audit import (
    _AUDIT_BUFFER,
    get_audit_stats,
    log_event,
    query_audit_logs,
)


def _reset():
    """清空进程级环形缓冲（单线程测试下无需持锁），保证用例间隔离。"""
    _AUDIT_BUFFER.clear()


# ───────────────────────────── log_event ─────────────────────────────

def test_log_event_appends_with_fields():
    _reset()
    log_event("login", user_id="u1", ip="1.2.3.4", result="success", detail="ok")
    assert len(_AUDIT_BUFFER) == 1
    e = _AUDIT_BUFFER[-1]
    assert e["user_id"] == "u1"
    assert e["ip"] == "1.2.3.4"
    assert e["action"] == "login"
    assert e["result"] == "success"
    assert e["detail"] == "ok"
    assert e["timestamp"] > 0
    assert isinstance(e["time_str"], str)


def test_log_event_defaults():
    _reset()
    log_event("act")
    e = _AUDIT_BUFFER[-1]
    assert e["user_id"] == "anonymous"
    assert e["ip"] == "unknown"
    assert e["result"] == "success"
    assert e["detail"] == ""


def test_log_event_truncates_long_detail():
    _reset()
    log_event("x", detail="A" * 1000)
    assert len(_AUDIT_BUFFER[-1]["detail"]) == 500


def test_failure_uses_warning_level(caplog):
    _reset()
    with caplog.at_level(logging.WARNING, logger="netlearn.audit"):
        log_event("login", result="failure")
    assert any("result=failure" in r.message for r in caplog.records)


def test_blocked_uses_warning_level(caplog):
    _reset()
    with caplog.at_level(logging.WARNING, logger="netlearn.audit"):
        log_event("sandbox_exec", result="blocked")
    assert any("result=blocked" in r.message for r in caplog.records)


def test_success_uses_info_level(caplog):
    _reset()
    with caplog.at_level(logging.INFO, logger="netlearn.audit"):
        log_event("login", result="success")
    assert any("result=success" in r.message for r in caplog.records)


# ────────────────────── 环形缓冲上界 ──────────────────────

def test_buffer_is_ring_capped_at_500():
    _reset()
    for i in range(600):
        log_event(f"a{i}")
    assert len(_AUDIT_BUFFER) == 500


# ────────────────────── query_audit_logs ──────────────────────

def test_query_returns_newest_first():
    _reset()
    for i in range(5):
        log_event(f"a{i}")
    assert [e["action"] for e in query_audit_logs()] == ["a4", "a3", "a2", "a1", "a0"]


def test_query_filters_by_action():
    _reset()
    log_event("login")
    log_event("logout")
    log_event("login")
    assert len(query_audit_logs(action="login")) == 2


def test_query_filters_by_result():
    _reset()
    log_event("a", result="success")
    log_event("b", result="blocked")
    assert len(query_audit_logs(result="blocked")) == 1


def test_query_respects_limit():
    _reset()
    for i in range(10):
        log_event(f"a{i}")
    assert len(query_audit_logs(limit=3)) == 3


def test_query_limit_capped_at_500():
    _reset()
    for i in range(600):
        log_event(f"a{i}")
    assert len(query_audit_logs(limit=10000)) == 500


def test_query_empty_buffer():
    _reset()
    assert query_audit_logs() == []


# ────────────────────── get_audit_stats ──────────────────────

def test_stats_counts_by_result_and_action():
    _reset()
    log_event("a", result="success")
    log_event("b", result="failure")
    log_event("c", result="blocked")
    log_event("d", result="success")
    s = get_audit_stats()
    assert s["total"] == 4
    assert s["blocked"] == 1
    assert s["failure"] == 1
    assert s["success"] == 2
    assert s["by_action"] == {"a": 1, "b": 1, "c": 1, "d": 1}


def test_stats_empty_buffer():
    _reset()
    s = get_audit_stats()
    assert s["total"] == 0
    assert s["success"] == 0
    assert s["by_action"] == {}
