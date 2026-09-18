@echo off
chcp 65001 >nul
title MARS-408 考研智能学习系统

echo ============================================
echo   MARS-408 — 408考研个性化学习系统
echo   第十五届中国软件杯 A3 赛题参赛作品
echo ============================================
echo.

:: 切换到项目根目录
cd /d "%~dp0"

:: 检查 Python 是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请安装 Python 3.12 或更高版本
    pause
    exit /b 1
)

:: 检查 Node.js 是否安装（前端构建需要）
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [警告] 未检测到 Node.js，将使用预构建的前端文件
)

:: 创建并激活虚拟环境
if not exist "py-server\.venv" (
    echo [1/4] 正在创建 Python 虚拟环境...
    cd py-server
    python -m venv .venv
    cd ..
) else (
    echo [1/4] 虚拟环境已存在，跳过
)

:: 安装依赖
echo [2/4] 正在安装后端依赖...
cd py-server
call .venv\Scripts\activate.bat
pip install -e .
if %errorlevel% neq 0 (
    echo [错误] 后端依赖安装失败，请检查网络连接或Python环境配置
    pause
    exit /b 1
)
cd ..

:: 构建前端（如果 dist 不存在）
if not exist "dist\index.html" (
    echo [3/4] 正在构建前端...
    if exist "package.json" (
        call npm install --silent 2>nul
        call npm run build-only 2>nul
    )
) else (
    echo [3/4] 前端已构建，跳过
)

:: 启动后端
echo [4/4] 正在启动后端服务...
echo.
echo ============================================
echo   启动完成！请访问：http://localhost:8002
echo   演示账号：demo / demo123456
echo   按 Ctrl+C 停止服务
echo ============================================
echo.

cd py-server
call .venv\Scripts\activate.bat

:: ── P0-A 端口守护：清理已占用 8002 的残留后端进程，避免 WinError 10048 后端起不来 ──
echo [端口守护] 检查 8002 端口占用...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8002" 2^>nul') do (
    if not "%%a"=="" (
        echo [端口守护] 发现占用进程 PID=%%a，尝试清理...
        taskkill /f /pid %%a >nul 2>&1 && echo [端口守护] 已结束 PID=%%a || echo [端口守护] 结束 PID=%%a 失败（可能需手动处理）
    )
)

python main.py --workers 1

pause