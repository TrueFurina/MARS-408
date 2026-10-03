"""启动后端（后台进程）"""
import subprocess, sys, os, time, socket

cwd = os.path.dirname(os.path.abspath(__file__))
proc = subprocess.Popen(
    [sys.executable, 'main.py'],
    cwd=cwd,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
)
print(f'Backend started: PID={proc.pid}')

# 等待启动
for i in range(30):
    time.sleep(1)
    try:
        s = socket.socket()
        s.settimeout(2)
        s.connect(('127.0.0.1', 8002))
        s.close()
        print('Backend ready')
        sys.exit(0)
    except (ConnectionRefusedError, socket.timeout, OSError):
        continue
print('Backend failed to start')
sys.exit(1)