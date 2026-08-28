# ============================================================
# P0 回归：F6 — 跨进程单写者锁 fail-fast
# ============================================================
# F6 用 filelock 在进程级抢 writer 锁：抢不到（已存在其它写者/多 worker）= 运行时
# fail-fast 拒绝启动，从根消除 last-writer-wins。另补 _resolve_uvicorn_workers 解析
# `uvicorn --workers N` CLI 形式（main.py 的环境变量软守卫覆盖不到），作为启动期前置拒绝。
#
# 两个用例：
#   - test_f6_unit_resolve_uvicorn_workers：纯函数单测（本地+CI，最快）。
#   - test_f6_unit_start_rejects_cli_workers_via_parser：start() 前置解析 --workers 并拒绝。
#   - test_f6_system_uvicorn_workers_4_rejected：真实 uvicorn --workers 4 必须被拒
#     （仅 Linux CI，需 subprocess 起真 uvicorn）。标记 system + p0_regression。
#     行为断言：服务不得成为健康多写者（HTTP /api/status 不得 200），与日志格式无关。
# ============================================================

import asyncio
import json
import os
import signal
import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.p0_regression

_PY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTH_SECRET = "test-secret-f6-system"


# ── 单元：_resolve_uvicorn_workers 解析 CLI / 环境变量 ──
def test_f6_unit_resolve_uvicorn_workers():
    from services.import_worker import _resolve_uvicorn_workers

    assert _resolve_uvicorn_workers(["uvicorn", "main:app", "--workers", "4"]) == 4
    assert _resolve_uvicorn_workers(["uvicorn", "--workers=8", "main:app"]) == 8
    assert _resolve_uvicorn_workers(["uvicorn", "main:app"]) == 1
    assert _resolve_uvicorn_workers(["uvicorn", "--workers", "1", "main:app"]) == 1
    # 解析异常安全回退 1（不抛错）
    assert _resolve_uvicorn_workers(["uvicorn", "--workers", "notanint"]) == 1


def test_f6_unit_start_rejects_cli_workers_via_parser(monkeypatch):
    """start() 应前置解析 --workers N 并拒绝（与 filelock 兜底互补）。"""
    import services.import_worker as iw_mod
    from services.import_worker import ImportWorker

    # 强制 Worker 进入启用分支：config.json 可能 import_worker.enabled=false，
    # 否则 start() 在 enabled 检查处提前 return，永远走不到 CLI workers 解析。
    monkeypatch.setattr(iw_mod, "load_config", lambda: {"import_worker": {"enabled": True}})
    monkeypatch.setattr(sys, "argv", ["uvicorn", "main:app", "--workers", "4"])
    w = ImportWorker()

    with pytest.raises(RuntimeError, match="F6 硬约束违规"):
        asyncio.run(w.start())


# ── 系统：真实 uvicorn --workers 4 必须被拒（仅 Linux CI）──
@pytest.mark.system
def test_f6_system_uvicorn_workers_4_rejected(tmp_path):
    """起真实 `uvicorn main:app --workers 4`：多写者必须被拒（filelock / CLI 解析兜底）。

    行为断言（与日志格式无关，避免 uvnicorn 不回显 traceback 导致的脆弱匹配）：
    服务在观察窗口内【不得】成为健康多写者 —— 即 HTTP /api/status 不得返回 200。
    若 F6 失效（多 worker 抢到 writer 锁并存），服务会健康启动 → 断言失败 = 正确捕获回归。
    """
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    vdb = run_dir / "vectordb_data"
    vdb.mkdir()

    # 预置 1 条占位 entry：跳过冷启动对种子数据的真实 E5 嵌入（从数分钟降到秒级）
    with open(vdb / "netlearn_kb.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "ids": ["__seed_skip_marker__"],
                "texts": ["skip"],
                "metas": [{"type": "seed_skip"}],
                "embeddings": [[0.0] * 768],
            },
            f,
        )

    envf = tmp_path / ".env.test"
    envf.write_text(
        "\n".join(
            [
                "HF_HUB_OFFLINE=1",
                "TRANSFORMERS_OFFLINE=1",
                f"VECTORDB_DATA_DIR={vdb}",
                f"AUTH_SECRET={AUTH_SECRET}",
                "ADMIN_USERNAME=admin",
                "ADMIN_PASSWORD=admin123456",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = _PY + os.pathsep + env.get("PYTHONPATH", "")
    # 走 InMemory 回退（规避原生库；F6 与存储后端无关，只看 writer 锁）
    env["MILVUS_ENABLED"] = "false"

    port = 8137
    base = f"http://127.0.0.1:{port}"
    cmd = [
        sys.executable, "-m", "uvicorn", "main:app",
        "--host", "127.0.0.1", "--port", str(port),
        "--workers", "4", "--env-file", str(envf),
    ]
    proc = subprocess.Popen(
        cmd, cwd=str(run_dir), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    healthy = False
    out = ""
    deadline = time.time() + 50
    try:
        while time.time() < deadline:
            # 任一时刻服务健康（多写者已抢到锁并存）→ 立即判定 F6 失效
            try:
                import httpx

                if httpx.get(f"{base}/api/status", timeout=1.0).status_code == 200:
                    healthy = True
                    break
            except Exception:
                pass
            line = proc.stdout.readline() if proc.stdout else ""
            if line:
                out += line
            elif proc.poll() is not None:
                # 进程已退出：读尽剩余输出
                rest, _ = proc.communicate(timeout=2)
                out += rest or ""
                break
            else:
                time.sleep(0.3)
    finally:
        try:
            proc.send_signal(signal.SIGINT if sys.platform != "win32" else signal.CTRL_C_EVENT)
        except Exception:
            proc.kill()
        try:
            rest, _ = proc.communicate(timeout=10)
            out += rest or ""
        except Exception:
            proc.kill()

    assert not healthy, (
        "F6 回归失败：uvicorn --workers 4 启动成功（多写者未被拒，last-writer-wins 风险）。"
        f"\n--- output tail ---\n{out[-2000:]}"
    )
