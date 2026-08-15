# iCore 启动 / 停止 / 重启脚本
#
# 用法:
#   .\start-icore.ps1            启动（已在运行则提示并检查健康状态）
#   .\start-icore.ps1 -Restart   重启
#   .\start-icore.ps1 -Stop      停止
#   .\start-icore.ps1 -Port 9000 指定端口
#
param(
    [string]$ProjectRoot = $PSScriptRoot,
    [switch]$Stop,
    [switch]$Restart,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$python  = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$logDir  = Join-Path $ProjectRoot "cancer_claw\var"
$outLog  = Join-Path $logDir "server.stdout.log"
$errLog  = Join-Path $logDir "server.stderr.log"
$pidFile = Join-Path $logDir "server.pid"
$health  = "http://127.0.0.1:$Port/healthz"
$baseUrl = "http://localhost:$Port"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "[错误] 未找到虚拟环境: $python" -ForegroundColor Red
    Write-Host "请先执行: cd $ProjectRoot; python -m venv .venv; .\.venv\Scripts\pip install -e ."
    exit 1
}

function Get-ICorePid {
    $lines = netstat -ano | Select-String ":$Port" | Select-String "LISTENING"
    foreach ($line in $lines) {
        $parts = ($line.ToString() -split "\s+") | Where-Object { $_ }
        if ($parts.Count -ge 5) { return [int]$parts[-1] }
    }
    return $null
}

function Test-IsICore {
    param([int]$CheckPort)
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$CheckPort/healthz" -TimeoutSec 4
        return $r.Content -match '"ok"'
    } catch {
        return $false
    }
}

function Wait-Healthy {
    param([int]$TimeoutSeconds = 90)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing -Uri $health -TimeoutSec 3
            if ($r.StatusCode -eq 200) { return $true }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    return $false
}

if ($Stop) {
    $pid8000 = Get-ICorePid
    if ($pid8000 -and (Test-IsICore -CheckPort $Port)) {
        Stop-Process -Id $pid8000 -Force
        Write-Host "[OK] iCore 已停止 (pid $pid8000)" -ForegroundColor Green
    } elseif ($pid8000) {
        Write-Host "[警告] 端口 :$Port 被其他程序占用（pid $pid8000），未做任何操作" -ForegroundColor Red
    } else {
        Write-Host "[信息] iCore 未在运行" -ForegroundColor Yellow
    }
    exit 0
}

$running = Get-ICorePid
if ($running -and -not (Test-IsICore -CheckPort $Port)) {
    Write-Host "[错误] 端口 :$Port 已被其他程序占用（pid $running），无法启动 iCore" -ForegroundColor Red
    Write-Host "       请先停止占用程序，或用 -Port 指定其他端口，例如: .\start-icore.ps1 -Port 8010"
    exit 1
}

if ($running -and -not $Restart) {
    Write-Host "[信息] iCore 已在运行 (pid $running): $baseUrl" -ForegroundColor Yellow
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri $health -TimeoutSec 5
        Write-Host "[OK] 健康检查 $($r.StatusCode) $($r.Content)" -ForegroundColor Green
    } catch {
        Write-Host "[警告] 健康检查失败: $($_.Exception.Message)" -ForegroundColor Red
    }
    exit 0
}

if ($running) {
    Write-Host "[信息] 停止旧实例 pid $running ..."
    Stop-Process -Id $running -Force
    Start-Sleep -Seconds 3
}

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

Write-Host "[信息] 启动 iCore（后台运行，端口 $Port）..."
$env:CANCER_CLAW_APP_PORT = "$Port"
$proc = Start-Process -FilePath $python -ArgumentList "run_server.py" `
    -WorkingDirectory $ProjectRoot -WindowStyle Hidden `
    -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
$proc.Id | Set-Content -LiteralPath $pidFile -Encoding ascii
Write-Host "[信息] 进程 pid $($proc.Id)，日志: $outLog / $errLog"

if (Wait-Healthy) {
    Write-Host "[OK] iCore 启动成功: $baseUrl" -ForegroundColor Green
} else {
    Write-Host "[错误] 启动超时（90 秒），请查看日志: $errLog" -ForegroundColor Red
    exit 1
}
