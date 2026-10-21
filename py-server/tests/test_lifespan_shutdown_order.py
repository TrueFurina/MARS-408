# -*- coding: utf-8 -*-
"""关停有序回归：后台任务必须**真的退出**之后才释放连接（REA #15）

此前 lifespan 的关停只做 `cleanup_task.cancel()`——cancel 只是"请求退出"，
任务要到下一个 await 点才真的结束；关停随后立刻 disconnect 向量库/PG/Redis，
于是存在「清理任务还在跑、它依赖的资源已经没了」的窗口，进程退出时还会打
"Task was destroyed but it is pending!"。

本文件用 asyncio 的同步原语把这条时序钉死（不用 sleep 猜时序）：

  [started] ──(主协程进入 shutdown)──> cancel ──> task 在 await 点收到
  CancelledError ──> 记录 [exited] ──> _cancel_and_wait 返回 ──> 才 disconnect

三条契约：
  1. 退出顺序：任务 [exited] 必须早于任何 disconnect（用事件序列断言，不看耗时）；
  2. 不残留：lifespan 返回后 `task.done()` 为真（此前为假，属真实缺陷）；
  3. 有界：任务吞掉取消（模拟卡在同步 IO）时，关停必须在超时后继续，
     且**不抛异常**——否则后续 release 全被跳过，故障面扩大。

运行：python -m pytest tests/test_lifespan_shutdown_order.py -q
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.lifespan as L  # noqa: E402


async def _noop(*args, **kwargs):
    return None


class _Timeline:
    """记录事件顺序。比"看耗时"稳：断言的是因果顺序，不是机器快慢。"""

    def __init__(self):
        self.events: list[str] = []

    def mark(self, what: str) -> None:
        self.events.append(what)

    def index(self, what: str) -> int:
        assert what in self.events, f"事件 {what!r} 未发生，实测 {self.events}"
        return self.events.index(what)


@pytest.fixture
def stub_lifespan(monkeypatch):
    """把启动期外部依赖全部替身化，只保留关停时序可观测。"""
    import shared.auth as auth
    monkeypatch.setattr(auth, "resolve_auth_secret", lambda: "s" * 40)

    tl = _Timeline()
    monkeypatch.setattr(L.vector_db, "connect", lambda: True)
    monkeypatch.setattr(L.vector_db, "count", lambda name: 999)
    monkeypatch.setattr(L.vector_db, "disconnect", lambda: tl.mark("disconnect:vector"))
    monkeypatch.setattr(L.pg_client, "disconnect", lambda: tl.mark("disconnect:pg"))
    monkeypatch.setattr(L.redis_client, "disconnect", lambda: tl.mark("disconnect:redis"))

    for name in ("_init_pg", "_init_redis", "_init_admin",
                 "_run_migrations", "_seed_demo_data", "_check_llm_credentials"):
        monkeypatch.setattr(L, name, _noop)
    monkeypatch.setattr(L, "_assert_single_worker", lambda: None)

    import services.import_worker as iw
    monkeypatch.setattr(iw.import_worker, "start", _noop)

    async def _stop():
        tl.mark("stop:import_worker")

    monkeypatch.setattr(iw.import_worker, "stop", _stop)

    import db.llm_provider as llm_provider
    monkeypatch.setattr(llm_provider, "_close_http_clients", _noop)
    return tl


def test_shutdown_waits_for_cleanup_task(stub_lifespan, monkeypatch):
    """正常路径：任务在 await 点响应取消 → 关停等它退出后才 disconnect。"""
    tl = stub_lifespan
    started = asyncio.Event()

    async def blocking_loop():
        started.set()
        try:
            await asyncio.Event().wait()   # 永不 set：只能靠取消退出
        except asyncio.CancelledError:
            tl.mark("exit:cleanup")
            raise

    monkeypatch.setattr(L, "_artifact_lifecycle_loop", blocking_loop)
    captured = {}

    async def run():
        async with L.lifespan(app=None):
            await asyncio.wait_for(started.wait(), timeout=2)   # barrier：确保任务确实起来了
            captured["task"] = next(
                t for t in asyncio.all_tasks() if getattr(t, "get_coro", None)
                and t.get_coro().__qualname__.endswith("blocking_loop"))
            assert not captured["task"].done(), "进入 shutdown 前任务应仍在运行（前提条件）"

    asyncio.run(run())

    assert captured["task"].done(), "lifespan 返回后清理任务必须已结束（此前为 pending）"
    # 因果顺序：清理任务退出 早于 任何 disconnect
    assert tl.index("exit:cleanup") < tl.index("disconnect:vector")
    assert tl.index("exit:cleanup") < tl.index("disconnect:pg")
    assert tl.index("exit:cleanup") < tl.index("disconnect:redis")


def test_shutdown_is_bounded_when_task_ignores_cancel(stub_lifespan, monkeypatch):
    """异常路径：任务吞掉一次取消（卡在同步 IO）→ 关停超时后继续，不抛异常。"""
    tl = stub_lifespan
    started = asyncio.Event()

    async def stubborn_loop():
        started.set()
        swallows = 0
        while True:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                swallows += 1
                tl.mark(f"cancel:swallowed#{swallows}")
                if swallows >= 2:
                    # 第二次取消才退：模拟"忽略一次取消"的真实坏任务，
                    # 同时保证事件循环关闭时不会被这个任务永久挂住。
                    tl.mark("exit:cleanup-late")
                    raise

    monkeypatch.setattr(L, "_artifact_lifecycle_loop", stubborn_loop)
    monkeypatch.setattr(L, "SHUTDOWN_TASK_TIMEOUT_SECONDS", 0.2)

    async def run():
        async with L.lifespan(app=None):
            await asyncio.wait_for(started.wait(), timeout=2)

    asyncio.run(run())   # 不抛：关停必须完成

    assert "cancel:swallowed#1" in tl.events, "任务应真的收到了取消请求"
    # 其余资源仍被释放（这正是"有界"的意义：一处卡住不拖垮全部释放）
    assert "disconnect:vector" in tl.events
    assert "stop:import_worker" in tl.events


def test_cancel_and_wait_returns_false_on_timeout(monkeypatch):
    """原语单测：超时返回 False 且不抛；已完成任务直接返回 True。"""
    async def run():
        swallows = {"n": 0}

        async def stubborn():
            while True:
                try:
                    await asyncio.sleep(3600)
                except asyncio.CancelledError:
                    swallows["n"] += 1
                    if swallows["n"] >= 2:
                        # 只吞第一次取消：第二次退出，保证本用例自己不会挂住
                        # 事件循环（否则 asyncio.run 关闭阶段会等它到天荒地老）。
                        raise

        t = asyncio.create_task(stubborn())
        await asyncio.sleep(0)
        ok = await L._cancel_and_wait(t, name="probe", timeout=0.1)
        t.cancel()                                    # 第二次取消 → 真正退出
        await asyncio.wait({t}, timeout=1)

        done = asyncio.create_task(asyncio.sleep(0))
        await done
        return ok, await L._cancel_and_wait(done, name="done-probe", timeout=0.1)

    timed_out, already_done = asyncio.run(run())
    assert timed_out is False
    assert already_done is True


def test_import_worker_stop_is_bounded(monkeypatch):
    """stop() 必须有界：Worker 永不退出时不能把关停挂死。

    事实分两层（2026-10-21 实机核实，勿凭印象表述）：
      · 任务能响应取消 → 裸 `await task` 会等它真正退出（0.2s 清理实测等满
        0.2s），旧实现这条路径**是对的**；
      · 任务吞掉取消且永不退出 → 裸 `await task` 无上界（实测挂死 >2 分钟，
        只能外部 kill），关停卡死、后续 httpx/向量库/PG/Redis 释放全跳过。

    本用例钉的是第二层：超时后 stop() 必须返回（不抛异常）、清空 `_task`，
    并留下 error 日志——否则这类挂死事后完全无法诊断。
    """
    pytest.importorskip("services.import_worker")
    import logging
    import services.import_worker as W

    monkeypatch.setattr(W, "_STOP_TIMEOUT_SECONDS", 0.1, raising=True)

    messages: list[str] = []

    class _Collect(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())

    handler = _Collect(level=logging.DEBUG)
    W.logger.addHandler(handler)
    try:
        async def run():
            worker = W.ImportWorker()
            allow_exit = {"v": False}

            async def stubborn():
                while True:
                    try:
                        await asyncio.sleep(3600)
                    except asyncio.CancelledError:
                        if allow_exit["v"]:
                            raise
                        # 吞掉取消，继续跑（模拟清理器自行重试 / 卡在同步 IO）

            task = asyncio.create_task(stubborn())
            await asyncio.sleep(0)
            worker._task = task

            t0 = asyncio.get_event_loop().time()
            await worker.stop()          # 旧实现会在这里永久挂住
            elapsed = asyncio.get_event_loop().time() - t0
            still_running = not task.done()
            cleared = worker._task is None

            allow_exit["v"] = True       # 收尾：放它退出，避免孤儿任务卡住事件循环
            task.cancel()
            await asyncio.wait({task}, timeout=1)
            return elapsed, still_running, cleared

        elapsed, still_running, cleared = asyncio.run(run())
    finally:
        W.logger.removeHandler(handler)

    assert elapsed < 2, f"stop() 未被有界化，耗时 {elapsed:.2f}s"
    assert still_running is True, "超时路径应留下孤儿任务，不能假装它已退出"
    assert cleared is True
    assert any("关停超时" in m for m in messages), f"超时未留 error 日志，实收 {messages}"
