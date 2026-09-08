# iCore 网页版启动 / 停止 / 重启 / 安装桌面快捷方式
#
# 用法:
#   .\start-icore.ps1                 启动后端 + 前端，并打开浏览器
#   .\start-icore.ps1 -Restart        重启
#   .\start-icore.ps1 -Stop           停止
#   .\start-icore.ps1 -InstallShortcut  把明亮版图标快捷方式放到桌面
#
param(
    [string]$ProjectRoot = $PSScriptRoot,
    [switch]$Stop,
    [switch]$Restart,
    [switch]$InstallShortcut,
    [int]$Port = 0,
    [int]$WebPort = 5180
)

$ErrorActionPreference = "Stop"

function Get-AppPort {
    param([string]$Root, [int]$Fallback = 8010)
    $cfg = Join-Path $Root "config.yaml"
    if (-not (Test-Path -LiteralPath $cfg)) { return $Fallback }
    $inApp = $false
    foreach ($line in Get-Content -LiteralPath $cfg -Encoding UTF8) {
        if ($line -match '^\s*app\s*:') { $inApp = $true; continue }
        if ($inApp -and $line -match '^\S') { break }
        if ($inApp -and $line -match '^\s*port\s*:\s*(\d+)') { return [int]$Matches[1] }
    }
    return $Fallback
}

if ($Port -le 0) { $Port = Get-AppPort -Root $ProjectRoot }

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$webDir = Join-Path $ProjectRoot "web"
$viteJs = Join-Path $webDir "node_modules\vite\bin\vite.js"
$logDir = Join-Path $ProjectRoot "cancer_claw\var"
$outLog = Join-Path $logDir "server.stdout.log"
$errLog = Join-Path $logDir "server.stderr.log"
$webOut = Join-Path $logDir "web.stdout.log"
$webErr = Join-Path $logDir "web.stderr.log"
$pidFile = Join-Path $logDir "server.pid"
$webPidFile = Join-Path $logDir "web.pid"
$health = "http://127.0.0.1:$Port/healthz"
$webUrl = "http://localhost:$WebPort/"
$ico = Join-Path $ProjectRoot "ops\icore-bright.ico"
if (-not (Test-Path -LiteralPath $ico)) {
    $ico = Join-Path $ProjectRoot "ops\icore.ico"
}

function Get-ListenPid {
    param([int]$CheckPort)
    $conns = Get-NetTCPConnection -LocalPort $CheckPort -State Listen -ErrorAction SilentlyContinue
    if ($conns) { return [int]@($conns)[0].OwningProcess }
    return $null
}

function Test-IsICore {
    param([int]$CheckPort)
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$CheckPort/healthz" -TimeoutSec 4
        return ($r.StatusCode -eq 200 -and $r.Content -match '"ok"')
    } catch {
        return $false
    }
}

function Test-IsWeb {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri $webUrl -TimeoutSec 4
        return ($r.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Wait-Url {
    param([string]$Uri, [int]$TimeoutSeconds = 90)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 3
            if ($r.StatusCode -eq 200) { return $true }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    return $false
}

function Stop-ICoreStack {
    $be = Get-ListenPid -CheckPort $Port
    if ($be) {
        if (Test-IsICore -CheckPort $Port) {
            Stop-Process -Id $be -Force -ErrorAction SilentlyContinue
            Write-Host "[OK] 后端已停止 (pid $be, :$Port)" -ForegroundColor Green
        } else {
            Write-Host "[警告] 端口 :$Port 被其他程序占用（pid $be），未结束该进程" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[信息] 后端未在运行" -ForegroundColor Yellow
    }

    $fe = Get-ListenPid -CheckPort $WebPort
    if ($fe) {
        if (Test-IsWeb) {
            Stop-Process -Id $fe -Force -ErrorAction SilentlyContinue
            Write-Host "[OK] 前端已停止 (pid $fe, :$WebPort)" -ForegroundColor Green
        } else {
            Write-Host "[警告] 端口 :$WebPort 被其他程序占用（pid $fe），未结束该进程" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[信息] 前端未在运行" -ForegroundColor Yellow
    }
}

function Install-DesktopShortcut {
    if (-not (Test-Path -LiteralPath $ico)) {
        throw "找不到图标: $ico"
    }
    $cmd = Join-Path $ProjectRoot "start-icore.cmd"
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $LnkPath = Join-Path $Desktop "iCore.lnk"
    $Wsh = New-Object -ComObject WScript.Shell
    $Lnk = $Wsh.CreateShortcut($LnkPath)
    $Lnk.TargetPath = $cmd
    $Lnk.WorkingDirectory = $ProjectRoot
    $Lnk.IconLocation = "$ico,0"
    $Lnk.Hotkey = "Ctrl+Alt+I"
    $Lnk.Description = "启动 iCore 网页版工作台"
    $Lnk.WindowStyle = 1
    $Lnk.Save()
    Write-Host "[OK] 桌面快捷方式: $LnkPath" -ForegroundColor Green
    Write-Host "     图标: 明亮版  快捷键: Ctrl+Alt+I" -ForegroundColor Green
}

if ($InstallShortcut) {
    Install-DesktopShortcut
    if (-not $Stop -and -not $Restart) { exit 0 }
}

if ($Stop -and -not $Restart) {
    Stop-ICoreStack
    exit 0
}

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "[错误] 未找到虚拟环境: $python" -ForegroundColor Red
    Write-Host "请先执行: python -m venv .venv; .\.venv\Scripts\pip install -e ."
    exit 1
}
if (-not (Test-Path -LiteralPath $viteJs)) {
    Write-Host "[错误] 未找到前端依赖: $viteJs" -ForegroundColor Red
    Write-Host "请先执行: cd web; npm install"
    exit 1
}

$bePid = Get-ListenPid -CheckPort $Port
if ($bePid -and -not (Test-IsICore -CheckPort $Port)) {
    Write-Host "[错误] 端口 :$Port 已被其他程序占用（pid $bePid），无法启动 iCore 后端" -ForegroundColor Red
    exit 1
}

$fePid = Get-ListenPid -CheckPort $WebPort
if ($fePid -and -not (Test-IsWeb) -and $Restart) {
    Write-Host "[警告] 端口 :$WebPort 被其他程序占用（pid $fePid）" -ForegroundColor Yellow
}

if ($Restart) {
    Write-Host "[信息] 重启 iCore ..."
    Stop-ICoreStack
    Start-Sleep -Seconds 2
}

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

if (-not (Test-IsICore -CheckPort $Port)) {
    Write-Host "[信息] 启动后端 :$Port ..."
    $env:CANCER_CLAW_APP_PORT = "$Port"
    $proc = Start-Process -FilePath $python -ArgumentList "run_server.py" `
        -WorkingDirectory $ProjectRoot -WindowStyle Hidden `
        -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
    $proc.Id | Set-Content -LiteralPath $pidFile -Encoding ascii
    if (-not (Wait-Url -Uri $health -TimeoutSeconds 90)) {
        Write-Host "[错误] 后端启动超时，日志: $errLog" -ForegroundColor Red
        exit 1
    }
    Write-Host "[OK] 后端就绪 http://127.0.0.1:$Port" -ForegroundColor Green
} else {
    Write-Host "[信息] 后端已在运行 http://127.0.0.1:$Port" -ForegroundColor Yellow
}

$node = (Get-Command node -ErrorAction SilentlyContinue).Source
if (-not $node) {
    Write-Host "[错误] 找不到 node，无法启动前端" -ForegroundColor Red
    exit 1
}

if (-not (Test-IsWeb)) {
    Write-Host "[信息] 启动前端 :$WebPort ..."
    $fe = Start-Process -FilePath $node -ArgumentList "`"$viteJs`"" `
        -WorkingDirectory $webDir -WindowStyle Hidden `
        -RedirectStandardOutput $webOut -RedirectStandardError $webErr -PassThru
    $fe.Id | Set-Content -LiteralPath $webPidFile -Encoding ascii
    if (-not (Wait-Url -Uri $webUrl -TimeoutSeconds 60)) {
        Write-Host "[错误] 前端启动超时，日志: $webErr" -ForegroundColor Red
        exit 1
    }
    Write-Host "[OK] 前端就绪 $webUrl" -ForegroundColor Green
} else {
    Write-Host "[信息] 前端已在运行 $webUrl" -ForegroundColor Yellow
}

Start-Process $webUrl
Write-Host "[OK] 已打开浏览器 $webUrl" -ForegroundColor Green
