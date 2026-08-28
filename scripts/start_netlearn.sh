#!/usr/bin/env bash
# NetLearn 一键启动 (Git Bash / WSL 不适用，仅 Windows Git Bash)
# 用法: 在仓库根目录执行  ./start_netlearn.sh
set -u
cd "$(dirname "$0")"

BPORT=8002
FPORT=5173
VENV_PY="py-server/.venv/Scripts/python.exe"

echo "=== NetLearn 一键启动 (后端 :$BPORT  +  前端 :$FPORT) ==="

# 1) 清理端口占用（含可能复活的 server_proxy.py）
echo "[1/4] 停止旧实例 / 端口占用..."
powershell.exe -NoProfile -Command "\$procs=@();foreach(\$p in @($BPORT,$FPORT)){\$c=Get-NetTCPConnection -LocalPort \$p -State Listen -EA SilentlyContinue;if(\$c){\$procs+=\$c.OwningProcess}};\$sp=Get-CimInstance Win32_Process -EA SilentlyContinue|Where-Object{\$_.CommandLine -like '*server_proxy*'};if(\$sp){\$sp|ForEach-Object{\$procs+=\$_.ProcessId}};\$procs|Sort-Object -Unique|ForEach-Object{Stop-Process -Id \$_ -Force -EA SilentlyContinue;Write-Host ('  killed PID '+ \$_)}}" 2>/dev/null || true
sleep 2

# 2) 启动后端（后台）
echo "[2/4] 启动后端 uvicorn :$BPORT ..."
if [ ! -f "$VENV_PY" ]; then echo "  错误: 未找到 $VENV_PY，请先创建 venv"; exit 1; fi
nohup "$VENV_PY" -m uvicorn main:app --host 127.0.0.1 --port "$BPORT" > _backend_run.log 2>&1 &
BACK_PID=$!
disown "$BACK_PID" 2>/dev/null || true

# 3) 启动前端（后台）
echo "[3/4] 启动前端 vite :$FPORT ..."
if ! command -v npm >/dev/null 2>&1; then echo "  错误: 未找到 npm，请先安装 Node.js"; kill "$BACK_PID" 2>/dev/null; exit 1; fi
nohup npm run dev > _vite_run.log 2>&1 &
FRONT_PID=$!
disown "$FRONT_PID" 2>/dev/null || true

# 4) 等待后端就绪
echo "[4/4] 等待后端就绪（最多 ~90s）..."
for i in $(seq 1 45); do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://127.0.0.1:$BPORT/api/knowledge/stats" 2>/dev/null)
  if [ "$code" = "200" ] || [ "$code" = "401" ]; then echo "  后端已就绪 (HTTP $code)"; break; fi
  sleep 2
done
if curl -s -o /dev/null --max-time 3 "http://127.0.0.1:$FPORT/" 2>/dev/null; then echo "  前端已就绪"; else echo "  前端仍在启动，稍候刷新即可"; fi

echo
echo "完成！浏览器打开:  http://127.0.0.1:$FPORT/"
echo "(后端 PID=$BACK_PID 前端 PID=$FRONT_PID；停止请用任务管理器或关闭终端)"
