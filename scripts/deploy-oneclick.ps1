<#
一键部署（免密 SSH）— study-help-pro / 芒得很职
用法：
  .\scripts\deploy-oneclick.ps1 -HealthOnly
  .\scripts\deploy-oneclick.ps1 -Files api/auth.py,api/career_training.py
  .\scripts\deploy-oneclick.ps1 -Frontend
  .\scripts\deploy-oneclick.ps1 -Files api/auth.py -NoRestart -DryRun

做的事：预检免密通道 → 远端暂存并 py_compile → 备份 → 覆盖 → sha256 回读 →
重启 mango-backend → 轮询 /api/status；上传/编译/校验/重启任一步失败都会自动回滚并重启。
前端：本地 dist 打包上传 → 校验文件数 → 备份并整体替换两处 dist。
2026-11-13 加固：部署动作整体纳入 try/catch；重启后严格校验 degraded/llm/embedding
（紧急跳过用 -SkipHealthGate）；-DryRun 不再触发真实重启；收尾打印备份清单供人工清理。
#>
param(
    [string[]]$Files = @(),
    [switch]$Frontend,
    [switch]$HealthOnly,
    [switch]$NoRestart,
    [switch]$DryRun,
    [switch]$SkipHealthGate,
    [int]$TimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"

$Server    = "ubuntu@175.178.234.11"
$Key       = Join-Path $env:USERPROFILE ".ssh\id_ed25519"
$Repo      = "E:\Program\MARL\study-help-pro"
$PyDir     = Join-Path $Repo "py-server"
$DistDir   = Join-Path $Repo "dist"
$RemotePy  = "/home/ubuntu/app/py-server"
$RemoteDist = @("/home/ubuntu/app/dist", "/home/ubuntu/app/py-server/dist")
$Stamp     = Get-Date -Format "yyyyMMdd-HHmmss"

function Invoke-Ssh([string]$Command) {
    # -n：stdin 接 /dev/null。后台/无控制台执行时，ssh 不带 -n 会一直等 stdin，表现为脚本卡死。
    $out = & ssh -n -i $Key -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new $Server $Command 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { throw "SSH 失败：$Command`n$out" }
    return $out.Trim()
}

function Get-RemoteDir([string]$Path) {
    $i = $Path.LastIndexOf("/")
    if ($i -le 0) { return "/" }
    return $Path.Substring(0, $i)
}

function Invoke-CopyUp([string]$LocalPath, [string]$RemotePath) {
    & scp -i $Key -o BatchMode=yes -o ConnectTimeout=10 -q $LocalPath "${Server}:$RemotePath" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "scp 失败：$LocalPath -> $RemotePath" }
}

function Get-BackendHealth {
    $raw = & ssh -n -i $Key -o BatchMode=yes -o ConnectTimeout=10 $Server "curl -s -m 8 http://127.0.0.1:8002/api/status" 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($raw -join "")) ) { return $null }
    try { $j = ($raw -join "`n") | ConvertFrom-Json } catch { return $null }
    return $j
}

function Wait-Healthy {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $h = Get-BackendHealth
        if ($null -ne $h -and $h.status -eq "ok") { return $h }
        Start-Sleep -Seconds 2
    }
    return $null
}

function Restart-Backend {
    Invoke-Ssh "sudo -n systemctl reset-failed mango-backend; sudo -n systemctl restart mango-backend" | Out-Null
    $h = Wait-Healthy
    if ($null -eq $h) { throw "重启后 /api/status 未恢复 ok（$TimeoutSeconds 秒内）" }
    if (-not $SkipHealthGate) {
        $issues = @()
        $deg = @($h.degraded_reasons | Where-Object { $_ })
        if ($deg.Count -gt 0) { $issues += ("degraded=" + ($deg -join ",")) }
        if ("$($h.health.llm.available)" -ne "True") { $issues += "llm.available=false" }
        if ("$($h.health.embedding.loaded)" -ne "True") { $issues += "embedding.loaded=false" }
        if ($issues.Count -gt 0) {
            throw ("重启后健康检查降级：{0}（多为 LLM 通道/配置问题，回滚代码不修 key；请查 /home/ubuntu/backend.log 与 LLM_CHAIN，紧急时可加 -SkipHealthGate 跳过）" -f ($issues -join "; "))
        }
    }
    return $h
}

function Invoke-Rollback {
    param([object[]]$Backups, [string]$Reason)
    Write-Warning $Reason
    Write-Output "开始回滚…"
    foreach ($pair in $Backups) {
        $t = $pair[0]; $bak = $pair[1]
        try {
            Invoke-Ssh "if [ -f '$bak' ]; then cp -p '$bak' '$t'; fi; if [ -d '$bak' ]; then rm -rf '$t' && mv '$bak' '$t'; fi" | Out-Null
            Write-Output "已回滚 $t"
        } catch {
            Write-Warning ("回滚失败：{0} -> {1}" -f $bak, $_.Exception.Message)
        }
    }
    try { Invoke-Ssh "sudo -n systemctl restart mango-backend; sleep 3; curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8002/api/status" } catch { }
}

Write-Output "== 预检 =="
if (-not (Test-Path -LiteralPath $Key)) { throw "找不到私钥：$Key" }
Invoke-Ssh "echo KEY_OK" | Out-Null
Write-Output "免密通道 OK（$Server）"

if ($HealthOnly) {
    $h = Wait-Healthy
    if ($null -eq $h) { throw "健康检查失败：/api/status 非 ok" }
    Write-Output ("健康：status={0} degraded={1} llm={2} embedding={3} 向量库={4}条" -f `
        $h.status, ($h.degraded_reasons -join ","), $h.health.llm.available,
        $h.health.embedding.loaded, $h.health.vector_db.collection_size)
    exit 0
}

if ($Files.Count -eq 0 -and -not $Frontend) {
    Write-Output "没有指定 -Files 或 -Frontend，只做了连通性预检。"
    exit 0
}

$uploaded = @()
$backed   = @()
$stage    = "/home/ubuntu/app/.deploy-stage-$Stamp"

try {
if ($Files.Count -gt 0) {
    Write-Output "== 后端文件 =="
    Invoke-Ssh "mkdir -p '$stage'" | Out-Null
    foreach ($f in $Files) {
        $rel = $f -replace '\\', '/'
        $local = Join-Path $PyDir ($rel -replace '/', '\')
        if (-not (Test-Path -LiteralPath $local -PathType Leaf)) { throw "本地文件不存在：$local" }

        $remote = "$stage/$rel"
        $remoteDir = Get-RemoteDir $remote
        $localSha = (Get-FileHash -LiteralPath $local -Algorithm SHA256).Hash.ToLower()

        if ($DryRun) { Write-Output ("[dry-run] 会上传 {0} -> {1}" -f $rel, "$RemotePy/$rel"); continue }

        Invoke-Ssh "mkdir -p '$remoteDir'" | Out-Null
        Invoke-CopyUp $local $remote
        Write-Output ("  已上传 {0}" -f $rel)
        $stageSha = ((Invoke-Ssh "sha256sum '$remote'") -split '\s+')[0]
        if ($stageSha -ne $localSha) { throw "上传校验不符：$rel" }

        Invoke-Ssh "cd '$RemotePy' && .venv/bin/python -m py_compile '$remote'" | Out-Null
        Write-Output ("  远端编译通过 {0}" -f $rel)

        $target = "$RemotePy/$rel"
        $bak = "$target.bak.$Stamp"
        $had = (Invoke-Ssh "if [ -f '$target' ]; then cp -p '$target' '$bak' && echo yes; else echo no; fi")
        Write-Output ("  已备份 {0}" -f $(if ($had -eq "yes") { $bak } else { "（无原文件）" }))
        if ($had -eq "yes") { $backed += ,@($target, $bak) }
        Invoke-Ssh "mkdir -p '$(Get-RemoteDir $target)' && cp '$remote' '$target'" | Out-Null
        $nowSha = ((Invoke-Ssh "sha256sum '$target'") -split '\s+')[0]
        if ($nowSha -ne $localSha) { throw "落位校验不符：$rel" }
        $uploaded += ,@($target, $had)
        Write-Output ("  已部署 {0}（备份见上）" -f $rel)
    }
    Invoke-Ssh "rm -rf '$stage'" | Out-Null
}

if ($Frontend) {
    Write-Output "== 前端 dist =="
    if (-not (Test-Path -LiteralPath $DistDir)) { throw "本地 dist 不存在：$DistDir" }
    $tarLocal = Join-Path $env:TEMP "dist-deploy-$Stamp.tar.gz"
    $tarRemote = "/tmp/dist-deploy-$Stamp.tar.gz"
    & tar -czf $tarLocal -C $DistDir . 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "打包 dist 失败" }
    $fileCount = (Get-ChildItem -LiteralPath $DistDir -Recurse -File | Measure-Object).Count
    $tarSha = (Get-FileHash -LiteralPath $tarLocal -Algorithm SHA256).Hash.ToLower()
    if ($DryRun) { Write-Output ("[dry-run] 会发布 dist：{0} 个文件" -f $fileCount) }
    else {
        Invoke-CopyUp $tarLocal $tarRemote
        $remoteSha = ((Invoke-Ssh "sha256sum '$tarRemote'") -split '\s+')[0]
        if ($remoteSha -ne $tarSha) { throw "dist 上传校验不符" }
        Invoke-Ssh "rm -rf /tmp/distx-$Stamp && mkdir -p /tmp/distx-$Stamp && tar xzf '$tarRemote' -C /tmp/distx-$Stamp" | Out-Null
        $remoteCount = ((Invoke-Ssh "find /tmp/distx-$Stamp -type f | wc -l")).Trim()
        if ([int]$remoteCount -ne $fileCount) { throw "dist 解压文件数不符：$remoteCount vs $fileCount" }
        foreach ($t in $RemoteDist) {
            $bak = "$t.bak.$Stamp"
            Invoke-Ssh "if [ -d '$t' ]; then rm -rf '$bak'; mv '$t' '$bak'; fi" | Out-Null
            $backed += ,@($t, $bak)
        }
        Invoke-Ssh "mv /tmp/distx-$Stamp /home/ubuntu/app/dist && cp -r /home/ubuntu/app/dist '$($RemoteDist[1])' && rm -rf '$tarRemote'" | Out-Null
        Write-Output ("已发布 dist：{0} 个文件（备份后缀 .bak.{1}）" -f $fileCount, $Stamp)
    }
}
} catch {
    try { Invoke-Ssh "rm -rf '$stage'" | Out-Null } catch { }
    Invoke-Rollback -Backups $backed -Reason $_.Exception.Message
    throw "部署失败，已回滚到部署前状态：$($_.Exception.Message)"
}

if ($DryRun) {
    Write-Output "[dry-run] 预演结束：未修改远端、未重启服务。"
    exit 0
}

if ($NoRestart) {
    Write-Output "已按要求跳过重启（-NoRestart）。改动需手动重启后生效。"
    exit 0
}

Write-Output "== 重启并探活 =="
Write-Output "  正在重启 mango-backend…"
try {
    $h = Restart-Backend
} catch {
    Invoke-Rollback -Backups $backed -Reason $_.Exception.Message
    throw "部署失败，已回滚到部署前状态：$($_.Exception.Message)"
}

Write-Output ("完成：status={0} degraded={1} llm={2} embedding={3} 向量库={4}条" -f `
    $h.status, (@($h.degraded_reasons | Where-Object { $_ }) -join ","), $h.health.llm.available, $h.health.embedding.loaded, $h.health.vector_db.collection_size)
Write-Output ("备份时间戳：{0}" -f $Stamp)
if ($backed.Count -gt 0) {
    Write-Output "本次备份（确认无误后再人工清理，脚本不自动删除）："
    foreach ($pair in $backed) { Write-Output ("  {0}" -f $pair[1]) }
}
