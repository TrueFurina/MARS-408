@echo off
chcp 65001 >nul
title MARS-408 事故恢复脚本 (Emergency Recover)
setlocal EnableDelayedExpansion

set ROOT=%~dp0
set BACK=%ROOT%py-server

echo ============================================================
echo   MARS-408 事故恢复脚本
echo   1. 杀除孤儿前后端进程   2. 清临时物   3. 干净启动
echo ============================================================
echo.

REM ── 步骤1：杀除占用 5173-5181 / 8002 的进程 ──
echo [1/4] 清理孤儿进程与占用端口...
for %%P in (5173 5174 5175 5176 5177 5178 5179 5180 5181 8002) do (
    for /f "tokens=5" %%A in ('netstat -ano 2^>nul ^| findstr ":%%P "') do (
        if not "%%A"=="" (
            echo   释放端口 %%P (PID %%A)
            taskkill /F /PID %%A >nul 2>&1
        )
    )
)
REM 兜底：按镜像名杀（仅限 netlearn 相关）
taskkill /F /IM uvicorn.exe >nul 2>&1
echo   端口清理完成
echo.

REM ── 步骤2：清临时物 ──
echo [2/4] 清理 __pycache__ 与临时文件...
if exist "%BACK%\.venv\Scripts\python.exe" (
    "%BACK%\.venv\Scripts\python.exe" -c "import pathlib,shutil;[shutil.rmtree(p) for p in pathlib.Path(r'%ROOT%').rglob('__pycache__')]" 2>nul
)
echo   __pycache__ 已清理（Python 会自动重建，零风险）
echo.

REM ── 步骤3：启动后端 ──
echo [3/4] 启动后端 (FastAPI :8002)...
if not exist "%BACK%\.venv\Scripts\python.exe" (
    echo   [ERROR] .venv 不存在，先 cd py-server ^&^& uv sync
    pause & exit /b 1
)
cd /d "%BACK%"
start "MARS-408-Backend" "%BACK%\.venv\Scripts\python.exe" main.py
echo   后端启动中，等待 8 秒...
timeout /t 8 /nobreak >nul

REM ── 步骤4：启动前端 ──
echo [4/4] 启动前端 (Vite :5173)...
cd /d "%ROOT%"
if not exist "%ROOT%node_modules" (
    echo   [ERROR] node_modules 不存在，先 npm install
    pause & exit /b 1
)
start "MARS-408-Frontend" npm run dev
echo.
echo ============================================================
echo   恢复完成！
echo   前端: http://localhost:5173
echo   后端: http://127.0.0.1:8002  (API 文档 /docs)
echo ============================================================
echo.
echo 提示: 关闭标题为 MARS-408-Backend / MARS-408-Frontend 的窗口来停止
echo       如需一键停止，可再运行本脚本（会先清理旧实例）
echo.
pause
