import os, sys, subprocess, time, httpx

PY = "E:/Program/MARL/study-help-pro/py-server"
run = os.path.join(PY, "iq_run_tmp")
os.makedirs(os.path.join(run, "vectordb_data"), exist_ok=True)
envf = os.path.join(run, ".env.test")
with open(envf, "w") as f:
    f.write(
        "HF_HUB_OFFLINE=1\nTRANSFORMERS_OFFLINE=1\nVECTORDB_DATA_DIR=%s\n"
        "AUTH_SECRET=test-secret-import-queue-system\nADMIN_USERNAME=admin\n"
        "ADMIN_PASSWORD=admin123456\n"
        % os.path.join(run, "vectordb_data").replace("\\", "/")
    )
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
