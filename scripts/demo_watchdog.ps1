#Requires -Version 5.0
<#
.SYNOPSIS
  NetLearn 后端进程守护脚本（省赛 Demo 专用）
.DESCRIPTION
  包裹 uvicorn (python main.py) 进程，崩溃后自动重启。
  解决 ADR-013 指出的 30s 冷启动风险：进程崩溃后 watchdog 自动拉起，
  无需人工干预。配合 demo 前预热，确保演示期间后端持续可用。
.NOTES
  用法: powershell -ExecutionPolicy Bypass -File scripts\demo_watchdog.ps1
  停止: Ctrl+C（watchdog 会终止子进程后退出）
#>

$ErrorActionPreference = "Stop"

# ── 配置 ──
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$PyServerDir = Join-Path $ProjectRoot "py-server"
$VenvPython = Join-Path $PyServerDir ".venv\Scripts\python.exe"
$SystemPython = "python"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { $SystemPython }
$MaxRestarts = 5          # 最大自动重启次数（省赛 demo 期间足够）
$RestartDelay = 3          # 崩溃后等待秒数（避免疯狂重启）
$HealthCheckUrl = "http://127.0.0.1:8002/api/status"
$HealthCheckTimeout = 45   # 冷启动健康检查超时（30s 启动 + 15s 余量）

$RestartCount = 0
$StartTime = Get-Date

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  NetLearn 后端进程守护 (Demo Watchdog)" -ForegroundColor Cyan
Write-Host "  项目根目录: $ProjectRoot" -ForegroundColor Gray
Write-Host "  Python: $Python" -ForegroundColor Gray
Write-Host "  最大重启次数: $MaxRestarts" -ForegroundColor Gray
Write-Host "  健康检查超时: ${HealthCheckTimeout}s" -ForegroundColor Gray
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

function Wait-For-Health {
    param([int]$TimeoutSec)
    $elapsed = 0
    $interval = 2
    while ($elapsed -lt $TimeoutSec) {
        try {
            $resp = Invoke-WebRequest -Uri $HealthCheckUrl -UseBasicParsing -TimeoutSec 3
            if ($resp.StatusCode -eq 200) {
                Write-Host "[Watchdog] 健康检查通过 (HTTP 200, ${elapsed}s)" -ForegroundColor Green
                return $true
            }
        } catch {
            # 还没启动完成，继续等
        }
        Start-Sleep -Seconds $interval
        $elapsed += $interval
        Write-Host "`r[Watchdog] 等待后端就绪... ${elapsed}s/${TimeoutSec}s" -NoNewline -ForegroundColor Yellow
    }
    Write-Host ""
    return $false
}

function Stop-ExistingBackend {
    # 清理 8002 端口占用（复用 start.bat 的端口守护逻辑）
    Write-Host "[Watchdog] 检查 8002 端口占用..." -ForegroundColor Yellow
    $connections = Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue
    if ($connections) {
        foreach ($conn in $connections) {
            $pid = $conn.OwningProcess
            if ($pid -and $pid -ne $PID) {
                Write-Host "[Watchdog] 发现占用进程 PID=$pid，尝试清理..." -ForegroundColor Yellow
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            }
        }
        Start-Sleep -Seconds 2
    }
}

# ── 主循环 ──
while ($RestartCount -le $MaxRestarts) {
    $iteration = $RestartCount + 1
    $procStartTime = Get-Date

    Write-Host "`n[Watchdog] === 第 $iteration 次启动 (重启计数: $RestartCount/$MaxRestarts) ===" -ForegroundColor Cyan

    Stop-ExistingBackend

    # 启动后端进程
    Set-Location $PyServerDir
    Write-Host "[Watchdog] 启动后端: $Python main.py" -ForegroundColor Green

    $proc = Start-Process -FilePath $Python `
        -ArgumentList "main.py" `
        -WorkingDirectory $PyServerDir `
        -PassThru -NoNewWindow

    Write-Host "[Watchdog] 后端进程 PID=$($proc.Id)，等待健康检查..." -ForegroundColor Yellow

    # 等待健康检查通过
    $healthy = Wait-For-Health -TimeoutSec $HealthCheckTimeout

    if ($healthy) {
        $uptime = ((Get-Date) - $procStartTime).TotalSeconds
        Write-Host "[Watchdog] 后端运行中 (PID=$($proc.Id), 启动耗时 ${uptime}s)" -ForegroundColor Green
        Write-Host "[Watchdog] 监控中... 如进程异常退出将自动重启 (Ctrl+C 停止守护)" -ForegroundColor Gray

        # 等待进程退出
        $proc.WaitForExit()
        $exitCode = $proc.ExitCode
        $uptime = ((Get-Date) - $procStartTime).ToString('hh\:mm\:ss')
        Write-Host "[Watchdog] 后端进程退出 (ExitCode=$exitCode, 运行时长=$uptime)" -ForegroundColor Red
    } else {
        Write-Host "[Watchdog] 健康检查超时，后端可能启动失败" -ForegroundColor Red
        if (-not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }

    $RestartCount++

    if ($RestartCount -gt $MaxRestarts) {
        Write-Host "`n[Watchdog] 已达最大重启次数 ($MaxRestarts)，停止守护。" -ForegroundColor Red
        Write-Host "[Watchdog] 请人工排查后端启动日志后重新运行此脚本。" -ForegroundColor Yellow
        break
    }

    Write-Host "[Watchdog] ${RestartDelay}s 后自动重启..." -ForegroundColor Yellow
    Start-Sleep -Seconds $RestartDelay
}

$totalUptime = ((Get-Date) - $StartTime).ToString('hh\:mm\:ss')
Write-Host "`n[Watchdog] 守护结束，总运行时长=$totalUptime，重启次数=$RestartCount" -ForegroundColor Cyan
