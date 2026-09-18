#Requires -Version 5.0
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  MARS-408 — 408考研个性化学习系统" -ForegroundColor Cyan
Write-Host "  第十五届中国软件杯 A3 赛题参赛作品" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 切换到项目根目录
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

# 检查 Python
try {
    $pyVer = python --version 2>&1
    Write-Host "[OK] $pyVer" -ForegroundColor Green
} catch {
    Write-Host "[错误] 未检测到 Python，请安装 Python 3.12 或更高版本" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

# 创建虚拟环境
if (-not (Test-Path "py-server\.venv")) {
    Write-Host "[1/4] 正在创建 Python 虚拟环境..." -ForegroundColor Yellow
    Set-Location py-server
    python -m venv .venv
    Set-Location $ProjectRoot
} else {
    Write-Host "[1/4] 虚拟环境已存在，跳过" -ForegroundColor Green
}

# 安装依赖
Write-Host "[2/4] 正在安装后端依赖..." -ForegroundColor Yellow
$venvActivate = Join-Path $ProjectRoot "py-server\.venv\Scripts\Activate.ps1"
. $venvActivate
pip install -e . -q 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[警告] 部分依赖安装失败，尝试安装核心依赖..." -ForegroundColor Yellow
    pip install fastapi uvicorn pydantic -q
}
Deactivate

# 构建前端
if (-not (Test-Path "dist\index.html")) {
    Write-Host "[3/4] 正在构建前端..." -ForegroundColor Yellow
    if (Test-Path "package.json") {
        npm install --silent 2>$null
        npm run build-only 2>$null
    }
} else {
    Write-Host "[3/4] 前端已构建，跳过" -ForegroundColor Green
}

# 启动后端
Write-Host "[4/4] 正在启动后端服务..." -ForegroundColor Yellow
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  启动完成！请访问：http://localhost:8002" -ForegroundColor White
Write-Host "  演示账号：demo / demo123456" -ForegroundColor White
Write-Host "  按 Ctrl+C 停止服务" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

Set-Location py-server
. $venvActivate
python main.py

Read-Host "按回车退出"