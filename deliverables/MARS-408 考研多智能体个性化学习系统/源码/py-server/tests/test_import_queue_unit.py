# ============================================================
# 单元测试：导入队列（ADR-007）—— 单写者保证 + 任务生命周期
# ============================================================
# 仅依赖 services.import_worker（轻量：db.milvus_client / config，无 torch / 真实 E5）。
# 真实的“解析 / 嵌入 / 向量库”均以 monkeypatch 替换，CI 干净环境可直接跑。
# 标记：@pytest.mark.import_queue
#
# 本文件基于 services.import_worker 的真实签名编写：
#   - submit(type_, source, params, submitted_by) -> 12-hex job_id
#   - job 是 dict（job["status"] / job["id"] ...）
#   - 单写者锁经 import_worker.store_lock（公开属性，返回内部 _store_lock）
# ============================================================

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

pytest.importorskip("services.import_worker")

pytestmark = pytest.mark.import_queue

from services.import_worker import (
    import_worker,
    STATUS_CANCELLED,
    STATUS_QUEUED,
)


@pytest.fixture
def started_worker(isolate_vectordb):
    """最小启动：仅设置 loop / executor / queue，不拉起后台 _consume 消费者任务，
    避免跨测试干扰；由测试手动驱动 _run_job / _process_file。

    isolate_vectordb（conftest 提供）会把 journal 落盘到 tmp，避免污染真实目录。

    注意：_loop 必须在 async 测试体内用 asyncio.get_running_loop() 设置，
    因为 sync fixture 上下文中无法可靠取到 pytest-asyncio 的当前事件循环。
    """
    import_worker._enabled = True
    import_worker._executor = ThreadPoolExecutor(max_workers=2)
    import_worker._queue = asyncio.Queue()
    yield import_worker
    if import_worker._executor is not None:
        import_worker._executor.shutdown(wait=False)
    import_worker._executor = None
    import_worker._queue = None
    import_worker._jobs.clear()


# ────────────────────────────────────────────────────────────
# TC-1：单写者保证 —— store_lock 是 asyncio.Lock 且严格串行（无交织）
# ────────────────────────────────────────────────────────────
async def test_single_writer_lock_is_asyncio_lock_and_serializes():
    # 不变式前提：store_lock 必须是 asyncio.Lock（在线写端点与 Worker 共享同一把锁）
    assert isinstance(import_worker.store_lock, asyncio.Lock)

    log: list[str] = []
    running = {"count": 0, "max": 0}

    async def critical(tag: str):
        async with import_worker.store_lock:
            running["count"] += 1
            # 进入临界区时绝不允许另一协程同时在内（否则单写者保证被破坏）
            assert running["count"] == 1, "两个协程同时进入临界区（单写者保证被破坏）"
            running["max"] = max(running["max"], running["count"])
            log.append(f"{tag}_in")
            await asyncio.sleep(0.01)  # 持锁期间主动让出，模拟真实写入耗时
            # 让出后仍在锁内，仍不允许并发进入
            assert running["count"] == 1, "持锁让出期间出现并发进入"
            log.append(f"{tag}_out")
            running["count"] -= 1

    # 两个协程争用同一把锁
    await asyncio.gather(critical("A"), critical("B"))

    # 核心证据：临界区并发进入峰值恒为 1（无交织）
    assert running["max"] == 1, f"临界区并发峰值应为 1，实际={running['max']}"
    # 无交织：每条日志都是完整的 in/out 紧邻（不会出现 A_in B_in ...）
    assert len(log) == 4, f"日志条数异常：{log}"
    for i in range(0, 4, 2):
        assert log[i].endswith("_in") and log[i + 1].endswith("_out"), (
            f"临界区被交织：{log}"
        )


# ────────────────────────────────────────────────────────────
# TC-2：submit 返回 12-hex job_id，job 可检索且出现在 list_jobs
# ────────────────────────────────────────────────────────────
async def test_submit_returns_12hex_and_job_listed(started_worker):
    import_worker._loop = asyncio.get_running_loop()

    job_id = await import_worker.submit("pdf", None, {})

    # 12 位小写十六进制
    assert re.fullmatch(r"[0-9a-f]{12}", job_id), f"job_id 格式不符: {job_id}"

    # 可经 get_job 检索
    job = import_worker.get_job(job_id)
    assert job is not None
    assert job["id"] == job_id
    assert job["status"] == STATUS_QUEUED

    # 出现在 list_jobs
    ids = [j["id"] for j in import_worker.list_jobs()]
    assert job_id in ids


# ────────────────────────────────────────────────────────────
# TC-3：cancel —— _process_file 中途翻转 cancel_requested，最终 cancelled
# ────────────────────────────────────────────────────────────
async def test_cancel_flips_midway_and_final_status_cancelled(started_worker, monkeypatch):
    import_worker._loop = asyncio.get_running_loop()

    calls = {"n": 0}

    async def fake_process_file(filepath, job):
        calls["n"] += 1
        # 第一个文件处理完即请求取消（模拟用户中途取消）
        job["cancel_requested"] = True
        return 0

    # 注入 2 个假文件 + 假 _process_file
    monkeypatch.setattr(import_worker, "_process_file", fake_process_file)
    monkeypatch.setattr(
        import_worker,
        "_gather_files",
        lambda job: [Path("/fake/a.pdf"), Path("/fake/b.pdf")],
    )

    job_id = await import_worker.submit("pdf", None, {})
    await import_worker._run_job(job_id)

    job = import_worker.get_job(job_id)
    assert job["cancel_requested"] is True
    assert job["status"] == STATUS_CANCELLED, (
        f"应 cancelled，实际 {job['status']} error={job.get('error')}"
    )
    # 在文件间隙停止：第二个文件不应被处理
    assert calls["n"] == 1, f"取消后不应继续处理文件，实际处理 {calls['n']} 个"


# ────────────────────────────────────────────────────────────
# TC-4：_gather_files 去重（保持顺序）
# ────────────────────────────────────────────────────────────
def test_gather_files_dedup_preserves_order(monkeypatch, tmp_path):
    from services import import_worker as iw_mod

    # 让扫描分支（os.walk）产出含重复 Path 的原始结果（同一 str(p) 视为重复）
    monkeypatch.setattr(iw_mod, "DOCS_DIR", tmp_path)  # 确保扫描分支进入

    def fake_walk(root, *a, **k):
        # 返回含重复文件名的扫描结果（经 _gather_files 内 Path 化后成为重复 Path 对象）
        yield ("d", [], ["a.pdf", "b.pdf", "a.pdf", "c.pdf", "b.pdf"])

    monkeypatch.setattr(iw_mod.os, "walk", fake_walk)

    job = {"type": "pdf", "source": "scan", "params": {}}
    result = import_worker._gather_files(job)

    expected = [Path("d/a.pdf"), Path("d/b.pdf"), Path("d/c.pdf")]
    assert result == expected, f"去重/顺序错误: {result}"
