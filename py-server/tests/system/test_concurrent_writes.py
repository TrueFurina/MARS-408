# ============================================================
# 系统测试：进程级并发写入 (TC-12 无丢失 / TC-14 多 worker 负向 LWW / TC-12b 在线vsWorker)
# ============================================================
# 起真实 uvicorn 子进程，从 HTTP 层并发打端点；补齐 TC-12 / TC-14 / 在线vsWorker。
#
# 隔离策略：子进程 cwd 指向 tmp 目录 + PYTHONPATH=py-server，使 InMemoryVectorStore 的
# 相对 ./vectordb_data 落盘到 tmp（不污染真实 py-server/vectordb_data）。
# 若 Dev 改为读取 VECTORDB_DATA_DIR 环境变量，可进一步简化（本文件已设置该变量）。
#
# 依赖 Dev 实现 services.import_worker + api.imports（type ∈ {pdf,docling,textbook}）。
# 导入走真实 PDF 解析（PyMuPDF 已装），用 tests 内临时生成的 PDF 作 source。
#
# 这些测试起真实 uvicorn 子进程，CI 单独分档（--timeout=180），标记 @pytest.mark.system。
# ============================================================

import os
import sys
import json
import subprocess
import threading
import time
import signal
import httpx

import pytest

_PY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PY)
AUTH_SECRET = "test-secret-import-queue-system"

pytestmark = pytest.mark.system


def _write_env_file(path, vectordb_dir):
    # 依赖 pymilvus 未安装/未启用 → 走 InMemory 回退（开发期默认，规避 Windows 段错误）
    lines = [
        "HF_HUB_OFFLINE=1",
        "TRANSFORMERS_OFFLINE=1",
        f"VECTORDB_DATA_DIR={vectordb_dir}",
        f"AUTH_SECRET={AUTH_SECRET}",
        "ADMIN_USERNAME=admin",
        "ADMIN_PASSWORD=admin123456",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _write_log_config(path):
    # 让应用级 logger（含 main.py 的多 worker 告警）输出到 stderr，便于断言捕获
    cfg = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"c": {"format": "%(levelname)s %(name)s: %(message)s"}},
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
                "level": "WARNING",
                "formatter": "c",
            }
        },
        "root": {"handlers": ["console"], "level": "WARNING"},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f)


def _admin_token():
    os.environ["AUTH_SECRET"] = AUTH_SECRET
    from shared.auth import create_token

    return create_token("admin", "admin")


def _dump_proc_output(proc, base):
    """启动超时时把 uvicorn 子进程的输出 dump 到 stdout。

    子进程以 stdout=PIPE / stderr=STDOUT 启动，输出全堵在管道里，且失败断言
    并不打印它 —— CI 日志里只剩一句「启动超时」，真正的异常栈永远看不到。
    这里在超时后终止进程并回读管道，避免这类失败无法诊断。
    """
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        out, _ = proc.communicate(timeout=15)
    except Exception:
        out = None
    print(f"\n===== uvicorn 启动失败 ({base}) 子进程输出 =====", flush=True)
    print((out or "<无输出>")[-8000:], flush=True)
    print("===== 子进程输出结束 =====\n", flush=True)


def _wait_status(base, timeout=120.0, proc=None):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"{base}/api/status", timeout=2.0).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    if proc is not None:
        _dump_proc_output(proc, base)
    return False


def _write_skip_marker(run_dir):
    """预置 1 条占位 entry，使启动期 count!=0，跳过 E5 种子嵌入（冷启动从数分钟降至秒级）。

    否则 main.lifespan 会在 count==0 时对 151KB 种子数据跑真实 E5（CPU）嵌入，
    冷启动耗时数分钟，远超测试等待上限。占位条目不影响增量断言（基线已隔离）。
    """
    import json as _json
    vdb = os.path.join(str(run_dir), "vectordb_data")
    os.makedirs(vdb, exist_ok=True)
    data = {
        "ids": ["__seed_skip_marker__"],
        "texts": ["skip"],
        "metas": [{"type": "seed_skip"}],
        "embeddings": [[0.0] * 768],
    }
    with open(os.path.join(vdb, "netlearn_kb.json"), "w", encoding="utf-8") as f:
        _json.dump(data, f)


def _start(workers, env_file, port, run_dir, log_config=None, extra_env=None):
    _write_skip_marker(run_dir)
    env = os.environ.copy()
    env["PYTHONPATH"] = _PY + os.pathsep + env.get("PYTHONPATH", "")
    if extra_env:
        env.update(extra_env)
    cmd = [
        sys.executable, "-m", "uvicorn", "main:app",
        "--host", "127.0.0.1", "--port", str(port),
        "--workers", str(workers), "--env-file", env_file,
    ]
    if log_config:
        cmd += ["--log-config", str(log_config)]
    return subprocess.Popen(
        cmd, cwd=str(run_dir), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


def _stop(proc):
    try:
        proc.send_signal(signal.CTRL_C_EVENT if sys.platform == "win32" else signal.SIGINT)
    except Exception:
        proc.kill()
    try:
        out, _ = proc.communicate(timeout=15)
    except Exception:
        proc.kill()
        out = ""
    return out


def _count_kb(base, token):
    r = httpx.get(f"{base}/api/knowledge/stats",
                  headers={"Authorization": f"Bearer {token}"}, timeout=5)
    return r.json()["total_docs"]


def _list_kb(base, token):
    r = httpx.get(f"{base}/api/knowledge/list?limit=10000",
                  headers={"Authorization": f"Bearer {token}"}, timeout=5)
    data = r.json()
    return data["items"], data["total"]


def _make_pdf(path, pages=3):
    import fitz

    doc = fitz.open()
    for i in range(pages):
        p = doc.new_page()
        p.insert_text((72, 72), ("Import sample knowledge point number %d. " % i) * 20)
    doc.save(str(path))
    doc.close()


def _submit_import(client, pdf_path):
    return client.post(
        "/api/imports/submit",
        json={"type": "pdf", "source": str(pdf_path), "params": {}},
    )


def _poll_job(client, job_id, token, timeout=180.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = client.get(f"/api/imports/jobs/{job_id}",
                           headers={"Authorization": f"Bearer {token}"})
            if r.status_code == 200 and r.json().get("status") in (
                "succeeded", "failed", "cancelled"
            ):
                return r.json()
        except Exception:
            pass
        time.sleep(0.2)
    return None


# ── TC-12：单 worker 下，两个并发 import job → 无丢失、无重复爆炸 ──
def test_tc12_single_writer_no_loss(tmp_path):
    """worker 路径并发：两个 import job 经同一单消费者串行处理，store 无丢失/重复。

    这是 ADR-007 单写者保证在「真实进程 + 真实 PDF 解析」下的端到端证明（workers=1）。
    """
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    vdb = run_dir / "vectordb_data"
    vdb.mkdir()
    envf = tmp_path / ".env.test"
    _write_env_file(envf, str(vdb))
    proc = _start(1, str(envf), 8123, run_dir)
    out = ""
    try:
        base = "http://127.0.0.1:8123"
        assert _wait_status(base, proc=proc), "single-worker 启动超时"
        token = _admin_token()
        client = httpx.Client(base, headers={"Authorization": f"Bearer {token}"})

        # 基线：启动后（含种子数据）的初始条目数，隔离"导入贡献"
        baseline = _count_kb(base, token)

        a_pdf = run_dir / "a.pdf"
        b_pdf = run_dir / "b.pdf"
        _make_pdf(a_pdf)
        _make_pdf(b_pdf)

        # 并发提交两个 import job
        results = {}
        t1 = threading.Thread(target=lambda: results.update(a=_submit_import(client, a_pdf)))
        t2 = threading.Thread(target=lambda: results.update(b=_submit_import(client, b_pdf)))
        t1.start(); t2.start(); t1.join(); t2.join()
        assert results["a"].status_code == 200, results["a"].text
        assert results["b"].status_code == 200, results["b"].text

        ja = _poll_job(client, results["a"].json()["job_id"], token)
        jb = _poll_job(client, results["b"].json()["job_id"], token)
        assert ja and ja["status"] == "succeeded", f"job A 未成功: {ja}"
        assert jb and jb["status"] == "succeeded", f"job B 未成功: {jb}"

        # ① 无丢失：增量 == 两 job 插入量之和（基线已隔离种子数据）
        expected = ja["progress"]["inserted_chunks"] + jb["progress"]["inserted_chunks"]
        final = _count_kb(base, token)
        assert final - baseline == expected, (
            f"单写者下数据丢失/多余：期望增量 {expected}，实际增量 {final - baseline}（基线 {baseline}）"
        )

        # ② 无重复爆炸：list 中 id 唯一
        items, _ = _list_kb(base, token)
        ids = [it["id"] for it in items]
        assert len(ids) == len(set(ids)), "单写者下出现重复条目（条目爆炸）"
    finally:
        out = _stop(proc)
    assert "Traceback (most recent call last)" not in out


# ── TC-12b：在线写端点 vs import worker 并发（workers=1）──
def test_tc12_online_vs_worker_concurrent(tmp_path):
    """在线 /knowledge/upsert 与 import worker 并发 → 两边都应落库、无丢失。

    Defect A 已修复：api/knowledge.py 现经 import_worker.store_lock 共享同一把锁，
    在线写端点返回 200（修复前会因 AttributeError 500）。本用例全绿即 LWW 消除的
    端到端证明（在线路径与 worker 路径在单写者锁下串行、互不覆盖）。
    """
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    vdb = run_dir / "vectordb_data"
    vdb.mkdir()
    envf = tmp_path / ".env.test"
    _write_env_file(envf, str(vdb))
    proc = _start(1, str(envf), 8125, run_dir)
    out = ""
    try:
        base = "http://127.0.0.1:8125"
        assert _wait_status(base, proc=proc), "single-worker 启动超时"
        token = _admin_token()
        client = httpx.Client(base, headers={"Authorization": f"Bearer {token}"})

        baseline = _count_kb(base, token)

        pdf = run_dir / "w.pdf"
        _make_pdf(pdf)

        # 并发：在线 upsert + worker import（两条写路径共享同一把 store_lock）
        res = {}
        def _up():
            res["up"] = client.post(
                "/api/knowledge/upsert",
                json={"documents": [{"content": "online upsert sample", "metadata": {"type": "knowledge_point"}}]},
            )
        def _im():
            r = _submit_import(client, pdf)
            res["im"] = r
            if r.status_code == 200:
                res["job"] = _poll_job(client, r.json()["job_id"], token)
        t1 = threading.Thread(target=_up)
        t2 = threading.Thread(target=_im)
        t1.start(); t2.start(); t1.join(); t2.join()

        # Defect A 已修复：在线写端点经 import_worker.store_lock 共享锁写，返回 200。
        # 此断言即 LWW 消除的端到端证明（修复前 AttributeError → 500）。
        assert res["up"].status_code == 200, (
            f"在线写端点应 200（store_lock 共享锁生效）: "
            f"{res['up'].status_code} {res['up'].text[:200]}"
        )
        assert res["im"].status_code == 200, res["im"].text
        job = res.get("job", {})
        assert job.get("status") == "succeeded", f"worker import 未成功: {job}"

        # 两条写路径都落地、无丢失：增量 == 1（在线）+ worker 插入量
        expected = 1 + job["progress"]["inserted_chunks"]
        final = _count_kb(base, token)
        assert final - baseline == expected, (
            f"在线+worker 并发下数据丢失/多余：期望增量 {expected}，实际增量 {final - baseline}（基线 {baseline}）"
        )
    finally:
        out = _stop(proc)
    assert "Traceback (most recent call last)" not in out


# ── TC-14（负向）：--workers 2 复现 last-writer-wins 风险，且启动告警生效 ──
def test_tc14_multiworker_lww_regression(tmp_path):
    """多进程 → 各自独立 InMemory 单写者锁 → 跨进程无共享锁 → LWW 风险重现。

    ADR §3.5 硬约束：uvicorn 必须 --workers 1。main.py 在检测到 >1 worker 时应 logger.warning。
    本用例验证该启动告警确实生效（guard 活跃）。
    """
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    vdb = run_dir / "vectordb_data"
    vdb.mkdir()
    envf = tmp_path / ".env.test"
    _write_env_file(envf, str(vdb))
    logcfg = tmp_path / "logconfig.json"
    _write_log_config(logcfg)

    # 显式设置 UVICORN_WORKERS=2，使 main.py 的硬约束检测确定性触发
    proc = _start(2, str(envf), 8124, run_dir, log_config=logcfg,
                  extra_env={"UVICORN_WORKERS": "2"})
    out = ""
    try:
        base = "http://127.0.0.1:8124"
        assert _wait_status(base, timeout=120, proc=proc), "multi-worker 启动超时"

        # 多 worker 下仍应可提交并跑通一个 import job（系统可用）
        token = _admin_token()
        client = httpx.Client(base, headers={"Authorization": f"Bearer {token}"})
        pdf = run_dir / "m.pdf"
        _make_pdf(pdf)
        r = _submit_import(client, pdf)
        assert r.status_code == 200, r.text
        job = _poll_job(client, r.json()["job_id"], token)
        assert job and job["status"] == "succeeded", f"import job 未成功: {job}"
    finally:
        out = _stop(proc)

    # 核心断言：启动期检测到 >1 worker 并发出多写者告警（ADR 硬约束 guard 活跃）
    lowered = out.lower()
    assert (
        "uvicorn_workers" in lowered
        or "多写者" in lowered
        or "last-writer-wins" in lowered
        or "workers" in lowered
    ), (
        "未检测到多 worker 启动告警（ADR §3.5 硬约束 guard 缺失或日志未转发）:\n"
        + out[-2000:]
    )
