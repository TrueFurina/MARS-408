import os, secrets, sys, subprocess, time, httpx

PY = "E:/Program/MARL/study-help-pro/py-server"
run = os.path.join(PY, "iq_run_tmp")
os.makedirs(os.path.join(run, "vectordb_data"), exist_ok=True)
envf = os.path.join(run, ".env.test")
# AUTH_SECRET 每次运行随机生成（>=32 字符，满足 shared.auth.resolve_auth_secret()
# 的 fail-fast 下限）。旧版硬编码 "test-secret-import-queue-system" 仅 31 字符，
# 会在 startup 直接抛 RuntimeError——与 tests 侧 D14 坑同源：该常量后来补了
# "-0123456789" 后缀到 42 字符，本脚本的副本没跟上（曾误提交入库的 .env.test
# 即此陈旧值，已 git rm + gitignore，见 2026-10-12 日志）。
# 本脚本只探活 /api/status，不签发跨进程 token，随机密钥无副作用。
# ADMIN_USERNAME/ADMIN_PASSWORD 不再硬编码（dev 模式下 app/lifespan.py 会
# 自动生成随机管理员口令并告警）；仅在宿主环境已注入时透传。
lines = [
    "HF_HUB_OFFLINE=1",
    "TRANSFORMERS_OFFLINE=1",
    "VECTORDB_DATA_DIR=%s" % os.path.join(run, "vectordb_data").replace("\\", "/"),
    "AUTH_SECRET=%s" % secrets.token_urlsafe(32),
]
for _k in ("ADMIN_USERNAME", "ADMIN_PASSWORD"):
    _v = os.environ.get(_k)
    if _v:
        lines.append("%s=%s" % (_k, _v))
with open(envf, "w") as f:
    f.write("\n".join(lines) + "\n")
logfile = os.path.join(PY, "iq_uvicorn.log")
env = os.environ.copy()
env["PYTHONPATH"] = PY + os.pathsep + env.get("PYTHONPATH", "")

cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
       "--port", "8123", "--workers", "1", "--env-file", envf]
with open(logfile, "w") as lf:
    proc = subprocess.Popen(cmd, cwd=run, env=env, stdout=lf, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:8123"
    t0 = time.time()
    up = False
    last_err = None
    for _ in range(180):
        try:
            r = httpx.get(f"{base}/api/status", timeout=2)
            if r.status_code == 200:
                up = True
                break
        except Exception as e:
            last_err = repr(e)
        time.sleep(1)
    elapsed = round(time.time() - t0, 1)
    print(f"UP={up} elapsed={elapsed} last_err={last_err}", file=lf)
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
print("DONE")
