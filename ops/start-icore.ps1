# Start iCore C/S desktop client: local FastAPI + WebView (full B/S workbench).
# Desktop shortcut may point here or directly at pythonw.exe.

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo
$env:PYTHONPATH = $Repo

$LogDir = Join-Path $env:USERPROFILE ".icore"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir "launch.log"

function Write-LaunchLog([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $Log -Value $line -Encoding UTF8
}

function Test-RealPython([string]$Path) {
    if (-not $Path) { return $false }
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    if ($Path -match "WindowsApps") { return $false }
    return $true
}

function Find-PythonW {
    $names = @(
        (Join-Path $Repo ".venv\Scripts\pythonw.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\pythonw.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\pythonw.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\pythonw.exe")
    )
    foreach ($p in $names) {
        if (Test-RealPython $p) { return $p }
    }
    $pyLauncher = Join-Path $env:LOCALAPPDATA "Programs\Python\Launcher\py.exe"
    if (Test-RealPython $pyLauncher) {
        try {
            $exe = & $pyLauncher -3 -c "import sys; print(sys.executable)" 2>$null
            if ($exe) {
                $w = Join-Path (Split-Path $exe.Trim()) "pythonw.exe"
                if (Test-RealPython $w) { return $w }
            }
        } catch {
        }
    }
    return $null
}

try {
    $PythonW = Find-PythonW
    if (-not $PythonW) {
        Write-LaunchLog "pythonw not found"
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show("找不到本机 Python（已跳过 Microsoft Store 占位程序）。", "iCore")
        exit 1
    }
    Write-LaunchLog ("start " + $PythonW + " -m cancer_claw.desktop cwd=" + $Repo)
    Start-Process -FilePath $PythonW -ArgumentList "-m", "cancer_claw.desktop" -WorkingDirectory $Repo
} catch {
    Write-LaunchLog ("launch failed: " + $_)
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("启动 iCore 失败。`n$_`n`n详见 $Log", "iCore")
    exit 1
}
