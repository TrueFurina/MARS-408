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
from pathlib import Path

import pytest

# 本文件位于 py-server/tests/system/ 下，需向上 3 层才到 py-server/（main.py 所在处）：
#   tests/system/test_concurrent_writes.py → tests/system → tests → py-server
# 原先只 dirname 两层，算出的是 py-server/tests，导致 uvicorn 子进程报
# "Error loading ASGI app. Could not import module \"main\"."，三条 system 用例
# 全部以「启动超时」失败（子进程输出被管道吞掉，此前一直看不到这句错误）。
_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PY)
# 必须 >= 32 字符，否则 shared.auth.resolve_auth_secret() 在 startup 触发 fail-fast，
# 真实 uvicorn 子进程起不来 -> system 测试「启动超时」失败（D14 之前 CI 一直红的根因）。
AUTH_SECRET = "test-secret-import-queue-system-0123456789"

# import_worker.DOCS_DIR = py-server/documents/教材（由 import_worker 模块路径推导，
# 与子进程 cwd 无关）。系统测试起真实 uvicorn 子进程，monkeypatch 无法穿透到子进程，
# 故测试 PDF 必须真实落盘到该目录（documents/教材 已被 .gitignore 忽略，不污染提交）；
# 提交时 source 用该绝对路径即可通过 api/imports 的路径越界护栏（F-012）。
_DOCS_DIR = os.path.join(_PY, "documents", "教材")

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


# 超时放宽：CIRunner 上首次请求会触发 embedding 模型加载（数秒~数十秒），
# 原 5s 会在慢机/冷缓存下误判为 ReadTimeout，属于测试脆弱性而非产品缺陷。
_HTTP_TIMEOUT = 120.0


def _count_kb(base, token):
    r = httpx.get(f"{base}/api/knowledge/stats",
                  headers={"Authorization": f"Bearer {token}"}, timeout=_HTTP_TIMEOUT)
    return r.json()["total_docs"]


def _list_kb(base, token):
    """分页取回全量条目。

    /api/knowledge/list 的 limit 约束为 Query(20, ge=1, le=100)（api/knowledge.py:85），
    原先请求 limit=10000 会触发 FastAPI 422 校验失败，响应体是 {"detail": [...]}，
    导致 `data["items"]` 抛 KeyError —— 这是测试缺陷，不是产品缺陷（限流上限本身合理）。
    这里按 100/页翻页取全量，并显式断言响应结构，避免断言只覆盖首页而漏掉跨页重复。
    """
    page_size = 100
    items, total, skip = [], 0, 0
    while True:
        r = httpx.get(f"{base}/api/knowledge/list?skip={skip}&limit={page_size}",
                      headers={"Authorization": f"Bearer {token}"}, timeout=_HTTP_TIMEOUT)
        data = r.json()
        assert "items" in data, (
            f"/api/knowledge/list 返回异常：HTTP {r.status_code}，"
            f"响应={str(data)[:300]}（注意 limit 上限为 100）"
        )
        batch = data["items"]
        items.extend(batch)
        total = data["total"]
        skip += page_size
        if len(batch) < page_size or skip >= total:
            break
    return items, total


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
    a_pdf = b_pdf = None
    try:
        base = "http://127.0.0.1:8123"
        assert _wait_status(base, proc=proc), "single-worker 启动超时"
        token = _admin_token()
        client = httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=120.0)

        # 基线：启动后（含种子数据）的初始条目数，隔离"导入贡献"
        baseline = _count_kb(base, token)

        # PDF 必须落在 import_worker.DOCS_DIR（py-server/documents/教材）内，
        # 否则 api/imports 的路径越界护栏会以 400 拒绝（F-012）。
        os.makedirs(_DOCS_DIR, exist_ok=True)
        a_pdf = Path(_DOCS_DIR) / "a.pdf"
        b_pdf = Path(_DOCS_DIR) / "b.pdf"
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
        for _p in (a_pdf, b_pdf):
            try:
                if _p and _p.exists():
                    _p.unlink()
            except Exception:
                pass
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
    pdf = None
    try:
        base = "http://127.0.0.1:8125"
        assert _wait_status(base, proc=proc), "single-worker 启动超时"
        token = _admin_token()
        client = httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=120.0)

        baseline = _count_kb(base, token)

        # PDF 必须落在 import_worker.DOCS_DIR 内，否则路径越界护栏会以 400 拒绝（F-012）。
        os.makedirs(_DOCS_DIR, exist_ok=True)
        pdf = Path(_DOCS_DIR) / "w.pdf"
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
        try:
            if pdf and Path(pdf).exists():
                Path(pdf).unlink()
        except Exception:
            pass
    assert "Traceback (most recent call last)" not in out


# ── TC-14（负向）：--workers 2 必须被 ADR-007 硬约束 fail-fast 拒绝 ──
def test_tc14_multiworker_lww_regression(tmp_path):
    """负向：uvicorn --workers 2（>1）必须被 ADR-007 硬约束在启动期 fail-fast 拒绝。

    多进程 → 各自独立 InMemory 单写者锁 → 跨进程无共享锁 → 重新引入
    last-writer-wins（2026-07-08 P0 事故根因）。因此 ADR-007 要求 uvicorn 必须
    --workers 1，main.py:270-274 在 lifespan 检测到 >1 worker 时直接 raise
    RuntimeError fail-fast。本用例验证该拒绝确实发生（应用绝不健康、日志含违规文案），
    而非旧版的「仅告警」。这是单写者保证的安全底线，绝不能退化成可绕过。
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
        # 负向断言：多 worker 必须被启动期 fail-fast 拒绝，/api/status 永远不应 200。
        # proc=None → _wait_status 不在超时后自杀（由 finally 的 _stop 统一回收）。
        healthy = _wait_status(base, timeout=45, proc=None)
        assert not healthy, (
            "ADR-007 硬约束失效：--workers 2 竟启动成功"
            "（多写者 last-writer-wins 风险重现，P0 回归）"
        )
    finally:
        out = _stop(proc)

    # 核心断言：启动期检测到 >1 worker 并 fail-fast 拒绝（含 ADR-007 违规文案）
    lowered = out.lower()
    assert "adr-007" in lowered, (
        "未检测到 ADR-007 硬约束拒绝日志（guard 缺失或日志未转发）:\n" + out[-2000:]
    )
    assert (
        "硬约束" in out
        or "workers数量" in out
        or "last-writer-wins" in out
        or "必须 --workers 1" in out
    ), (
        "ADR-007 拒绝日志缺少关键违规文案"
        "（workers数量 / last-writer-wins / 必须 --workers 1）:\n"
        + out[-2000:]
    )
