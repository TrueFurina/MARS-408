@echo off
title MARS-408 - 停止服务
echo ============================================================
echo   MARS-408 停止脚本 (Windows)
echo ============================================================
echo.
echo 正在停止 MARS-408 前后端进程...
taskkill /FI "WINDOWTITLE eq MARS-408-Backend" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq MARS-408-Frontend" /F >nul 2>&1
echo.
echo [完成] 已向 MARS-408 前后端发送停止信号。
echo   若仍有残留（如孤立的 vite/node/python 子进程），
echo   请在任务管理器中手动结束 python.exe / node.exe。
echo.
pause