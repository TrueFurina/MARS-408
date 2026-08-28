@echo off
REM ============================================================
REM guardian.bat — Windows 进程守护（D8，不依赖第三方）
REM 循环检测 py-server(uvicorn :8002) 是否存活，崩溃则自动重启。
REM 用法：在 py-server 目录下双击或 `guardian.bat`；Ctrl+C 退出本守护。
REM 检测方式：netstat 探活 :8002 是否 LISTENING（仅本机足够）。
REM ============================================================

setlocal EnableDelayedExpansion
set "PORT=8002"
REM 优先使用项目 venv（本机为 C: 符号链接），否则退回系统 python
if exist ".venv\Scripts\python.exe" (
    set "PY=.\.venv\Scripts\python.exe"
) else (
    set "PY=python"
)
REM 确保后端模块（main.py）可被 -m 方式导入
set "PYTHONPATH=%~dp0"

:loop
    REM 探活：:PORT 处于 LISTENING 状态即视为存活
    netstat -an 2>nul | findstr /i "LISTENING" | findstr /i ":%PORT%" >nul
    if errorlevel 1 (
        echo [%date% %time%] py-server 未运行（:!PORT! 无 LISTENING），正在启动...
        REM /min 后台最小窗口启动；崩溃后本守护会在下轮检测重启
        start "py-server-guardian" /min "!PY!" -m uvicorn main:app --host 127.0.0.1 --port !PORT!
        echo [%date% %time%] 已发起启动（窗口标题 py-server-guardian）。
    ) else (
        echo [%date% %time%] py-server 存活（:!PORT! LISTENING），无需重启。
    )

    REM 等待 15 秒后再检测
    timeout /t 15 /nobreak >nul
goto loop
