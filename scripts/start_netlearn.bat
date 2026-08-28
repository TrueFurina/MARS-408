@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "BPORT=8002"
set "FPORT=5173"
set "VENV_PY=py-server\.venv\Scripts\python.exe"

echo ============================================================
echo   NetLearn 一键启动  (后端 :%BPORT%  +  前端 :%FPORT%)
echo ============================================================

REM ---------- 1) 清理端口占用（含可能复活的 server_proxy.py）----------
echo [1/4] 停止旧实例 / 端口占用...
powershell -NoProfile -Command "$procs=@();foreach($p in @(%BPORT%,%FPORT%)){$c=Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue;if($c){$procs+=$c.OwningProcess}};$sp=Get-CimInstance Win32_Process -ErrorAction SilentlyContinue|Where-Object{$_.CommandLine -like '*server_proxy*'};if($sp){$sp|ForEach-Object{$procs+=$_.ProcessId}};$procs|Sort-Object -Unique|ForEach-Object{try{Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue;Write-Host ('  killed PID '+$_)}catch{}}"
timeout /t 2 >nul

REM ---------- 2) 启动后端 ----------
echo [2/4] 启动后端 uvicorn :%BPORT% ...
if not exist "%VENV_PY%" (
  echo   错误: 未找到虚拟环境 %VENV_PY%，请先创建 py-server/.venv
  pause
  exit /b 1
)
start "NetLearn-Backend" cmd /k "cd /d %~dp0py-server && %VENV_PY% -m uvicorn main:app --host 127.0.0.1 --port %BPORT%"

REM ---------- 3) 启动前端 ----------
echo [3/4] 启动前端 vite :%FPORT% ...
where npm >nul 2>&1 || (echo   错误: 未找到 npm，请先安装 Node.js & pause & exit /b 1)
start "NetLearn-Frontend" cmd /k "cd /d %~dp0 && npm run dev"

REM ---------- 4) 等待后端就绪 ----------
echo [4/4] 等待后端就绪（最多 ~90s）...
set "tries=0"
:wait
curl.exe -s -o nul --max-time 3 "http://127.0.0.1:%BPORT%/api/knowledge/stats" >nul 2>&1
if not errorlevel 1 goto backend_ok
set /a tries+=1
if %tries% geq 45 (
  echo   后端启动超时，请查看 "NetLearn-Backend" 窗口日志
  goto end
)
timeout /t 2 >nul
goto wait

:backend_ok
echo   后端已就绪 (HTTP 401 = 需登录，服务正常)
curl.exe -s -o nul --max-time 3 "http://127.0.0.1:%FPORT%/" >nul 2>&1
if not errorlevel 1 (echo   前端已就绪) else (echo   前端仍在启动，稍候刷新即可)

echo.
echo 完成！浏览器打开:  http://127.0.0.1:%FPORT%/
echo （两个黑色窗口 = 后端 / 前端日志，请勿关闭）
echo.
pause

:end
endlocal
