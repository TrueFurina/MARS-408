# ============================================================
# WS1 覆盖率补全 — shared/review_scheduler.py（艾宾浩斯间隔复习排程）
#
# 此前在测试套件中零引用（grep shared.<mod> 无命中）。本模块为**纯规则、零外部
# 依赖**（仅 datetime/typing），离线可复现，故可脱离 conftest 独立运行：
#   py-server/.venv/Scripts/python.exe -m pytest tests/test_shared_review_scheduler.py --noconftest -q
#
# 覆盖：_coerce_dt 多格式容错 / next_review_after 阶段钳位 / advance_stage /
#       is_due / compute_initial_review / graduate_if_done / schedule_after_review
# ================================================================

from datetime import datetime, timedelta

from shared.review_scheduler import (
    MAX_STAGE,
    REVIEW_INTERVALS_DAYS,
    _coerce_dt,
    advance_stage,
    compute_initial_review,
    graduate_if_done,
    is_due,
    next_review_after,
    schedule_after_review,
)


def _base() -> datetime:
    return datetime(2026, 1, 1, 12, 0, 0)


# ────────────────────────── _coerce_dt ──────────────────────────

def test_coerce_none():
    assert _coerce_dt(None) is None


def test_coerce_datetime_passthrough():
    d = _base()
    assert _coerce_dt(d) is d


def test_coerce_timestamp():
    assert isinstance(_coerce_dt(0), datetime)


def test_coerce_invalid_timestamp_returns_none():
    # 超大时间戳应触发 OverflowError/OSError，保守回退 None 而非让调用方炸
    assert _coerce_dt(float("1e30")) is None


def test_coerce_str_space_format():
    assert _coerce_dt("2026-08-29 12:00:00") == datetime(2026, 8, 29, 12, 0, 0)


def test_coerce_str_iso_format():
    assert _coerce_dt("2026-08-29T12:00:00") == datetime(2026, 8, 29, 12, 0, 0)


def test_coerce_str_date_only():
    assert _coerce_dt("2026-08-29") == datetime(2026, 8, 29)


def test_coerce_str_iso_with_trailing_z():
    assert _coerce_dt("2026-08-29T12:00:00Z") is not None


def test_coerce_str_empty_returns_none():
    assert _coerce_dt("   ") is None


def test_coerce_str_garbage_returns_none():
    assert _coerce_dt("not-a-date") is None


# ──────────────────────── next_review_after ────────────────────────

def test_next_review_stage_zero_is_one_day():
    assert next_review_after(0, _base()) == _base() + timedelta(days=1)


def test_next_review_clamps_negative_stage():
    assert next_review_after(-5, _base()) == _base() + timedelta(days=REVIEW_INTERVALS_DAYS[0])


def test_next_review_clamps_above_max():
    assert next_review_after(999, _base()) == _base() + timedelta(days=REVIEW_INTERVALS_DAYS[MAX_STAGE])


def test_next_review_max_stage_is_30_days():
    assert next_review_after(MAX_STAGE, _base()) == _base() + timedelta(days=30)


# ────────────────────────── advance_stage ──────────────────────────

def test_advance_correct_increments():
    assert advance_stage(0, True) == 1


def test_advance_incorrect_resets_to_zero():
    assert advance_stage(3, False) == 0


def test_advance_at_max_stays_max():
    assert advance_stage(MAX_STAGE, True) == MAX_STAGE


# ────────────────────────────── is_due ──────────────────────────────

def test_is_due_past_is_true():
    assert is_due(_base() - timedelta(days=1), _base()) is True


def test_is_due_future_is_false():
    assert is_due(_base() + timedelta(days=1), _base()) is False


def test_is_due_none_means_due():
    assert is_due(None, _base()) is True


def test_is_due_accepts_string():
    assert is_due("2020-01-01 00:00:00", _base()) is True


# ─────────────────────── compute_initial_review ───────────────────────

def test_initial_review_stage_zero_and_plus_one_day():
    out = compute_initial_review(_base())
    assert out["review_stage"] == 0
    assert out["next_review_at"] == (_base() + timedelta(days=1)).isoformat(sep=" ")


def test_initial_review_without_base_returns_string():
    out = compute_initial_review(None)
    assert out["review_stage"] == 0
    assert isinstance(out["next_review_at"], str)


# ───────────────────────── graduate_if_done ─────────────────────────

def test_graduate_at_max_and_correct():
    assert graduate_if_done(MAX_STAGE, True) is True


def test_no_graduate_below_max():
    assert graduate_if_done(MAX_STAGE - 1, True) is False


def test_no_graduate_when_wrong():
    assert graduate_if_done(MAX_STAGE, False) is False


# ──────────────────────── schedule_after_review ────────────────────────

def test_schedule_advances_and_sets_next():
    out = schedule_after_review(0, None, True, _base())
    assert out["review_stage"] == 1
    assert out["next_review_at"] == (_base() + timedelta(days=REVIEW_INTERVALS_DAYS[1])).isoformat(sep=" ")
    assert out["graduated"] is False


def test_schedule_graduates_at_max():
    out = schedule_after_review(MAX_STAGE, None, True, _base())
    assert out["graduated"] is True
    assert out["review_stage"] == MAX_STAGE


def test_schedule_wrong_resets_stage():
    out = schedule_after_review(3, None, False, _base())
    assert out["review_stage"] == 0
    assert out["graduated"] is False
