"""MARS-408 前后端守护启动器（DETACHED_PROCESS，脱离 bash 会话存活）

用法: python scripts/launch_detached.py
用 CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS 标志启动后端+前端，
使其完全脱离 bash 进程树，供 Playwright 等外部工具连接。
"""
import subprocess
import sys
import os
import time

DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable  # miniconda python（本脚本由它执行）

LOG_DIR = os.environ.get("TEMP", "/tmp")

def launch(cmd, logname):
    log = os.path.join(LOG_DIR, logname)
    with open(log, "w", encoding="utf-8") as f:
        p = subprocess.Popen(
            cmd,
            stdout=f,
            stderr=subprocess.STDOUT,
            cwd=ROOT,
            creationflags=DETACHED,
            close_fds=True,
        )
    return p.pid

# 后端：py-server/main.py
be_pid = launch(
    [PY, "-u", os.path.join(ROOT, "py-server", "main.py")],
    "mars_be_detached.log",
)
print(f"后端 PID={be_pid}")

# 前端：vite dev（node 直接调 vite.js，避免 npx 包装）
vite_js = os.path.join(ROOT, "node_modules", "vite", "bin", "vite.js")
fe_pid = launch(
    ["node", vite_js, "--port", "5173", "--strictPort"],
    "mars_fe_detached.log",
)
print(f"前端 PID={fe_pid}")

print("等待就绪...")
time.sleep(15)

# 自检
import urllib.request
for port, name in [(8002, "后端"), (5173, "前端")]:
    try:
        r = urllib.request.urlopen(f"http://127.0.0.1:{port}", timeout=3)
        print(f"✅ {name} {port}: {r.status}")
    except Exception as e:
        print(f"⚠️ {name} {port}: {e}")
