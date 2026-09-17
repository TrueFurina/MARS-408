# ============================================================
# P1-4 回归测试（2026-09-17）：WeakPointTracker 持久化 + 线程安全
#
# 修复前：进程内全局 dict，无锁、不跨 worker、重启即丢。
# 修复后：RLock 保护 + Redis 共享持久化（可注入 fake）+ 内存回退。
# ============================================================

import copy
import threading

import pytest

from engines.quiz_engine import (
    WeakPointTracker,
    StepQuestion,
    StepResult,
)


class FakeRedis:
    """内存版 Redis 替身：验证"跨实例共享同一份持久化数据"。"""

    def __init__(self):
        self.store = {}
        self.is_enabled = True

    def get_json(self, key):
        return copy.deepcopy(self.store.get(key))

    def set_json(self, key, data, ttl=3600):
        self.store[key] = copy.deepcopy(data)


def _q():
    return StepQuestion(
        id="q1", subject="computer_network", chapter="tcp_congestion",
        difficulty="hard", question_text="x", steps=[],
        error_type_map={"concept_confusion": "congestion"},
    )


def _wrong_step():
    return [StepResult(step_index=0, step_name="判断阶段", correct=False, error_type="concept_confusion")]


def test_in_memory_fallback_works_without_redis(monkeypatch):
    """Redis 不可用时必须回退进程内缓存，功能不受影响。"""
    import engines.quiz_engine as qe
    monkeypatch.setattr(qe, "redis_client", None)

    tracker = WeakPointTracker()
    tracker.record_error(_q(), _wrong_step(), "u1")
    weak = tracker.get_weak_topics("u1")
    assert len(weak) == 1
    assert weak[0].count == 1
    assert weak[0].concept == "congestion"


def test_count_increments_and_last_wrong_set(monkeypatch):
    import engines.quiz_engine as qe
    monkeypatch.setattr(qe, "redis_client", None)

    tracker = WeakPointTracker()
    tracker.record_error(_q(), _wrong_step(), "u1")
    tracker.record_error(_q(), _wrong_step(), "u1")
    tracker.record_error(_q(), _wrong_step(), "u1")
    weak = tracker.get_weak_topics("u1")
    assert weak[0].count == 3
    assert weak[0].last_wrong  # 时间戳被填充（原实现从不设置该字段）


def test_persists_across_instances_via_redis(monkeypatch):
    """核心回归：数据落 Redis 后，新实例（模拟另一 worker / 重启）能读到。"""
    import engines.quiz_engine as qe
    monkeypatch.setattr(qe, "redis_client", FakeRedis())

    t1 = WeakPointTracker()
    t1.record_error(_q(), _wrong_step(), "u1")

    t2 = WeakPointTracker()  # 全新实例，无进程内状态
    weak = t2.get_weak_topics("u1")
    assert len(weak) == 1
    assert weak[0].count == 1
    assert weak[0].concept == "congestion"


def test_mark_mastered_persists_and_filters_out(monkeypatch):
    import engines.quiz_engine as qe
    monkeypatch.setattr(qe, "redis_client", FakeRedis())

    t1 = WeakPointTracker()
    t1.record_error(_q(), _wrong_step(), "u1")
    assert len(t1.get_weak_topics("u1")) == 1

    t1.mark_mastered("u1", "computer_network", "tcp_congestion", "congestion")
    assert len(t1.get_weak_topics("u1")) == 0

    # 新实例也应看到"已掌握"状态（持久化生效）
    t2 = WeakPointTracker()
    assert len(t2.get_weak_topics("u1")) == 0


def test_user_isolation(monkeypatch):
    import engines.quiz_engine as qe
    monkeypatch.setattr(qe, "redis_client", FakeRedis())

    t = WeakPointTracker()
    t.record_error(_q(), _wrong_step(), "u1")
    t.record_error(_q(), _wrong_step(), "u2")
    t.record_error(_q(), _wrong_step(), "u2")
    assert t.get_weak_topics("u1")[0].count == 1
    assert t.get_weak_topics("u2")[0].count == 2


def test_concurrent_record_no_lost_update(monkeypatch):
    """并发写入不得丢更新（RLock 保护下的读-改-写）。"""
    import engines.quiz_engine as qe
    monkeypatch.setattr(qe, "redis_client", FakeRedis())

    tracker = WeakPointTracker()
    n = 50

    def worker():
        for _ in range(n):
            tracker.record_error(_q(), _wrong_step(), "u1")

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    weak = tracker.get_weak_topics("u1")
    assert weak[0].count == n * 4, f"期望 {n*4}，实际 {weak[0].count}（存在丢更新）"
