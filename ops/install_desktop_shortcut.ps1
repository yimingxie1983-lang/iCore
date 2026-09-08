# Install iCore C/S desktop shortcut (custom icon + Ctrl+Alt+I).
# Usage: powershell -File ops/install_desktop_shortcut.ps1

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Ico = Join-Path $Repo "ops\icore.ico"
$Launcher = Join-Path $Repo "ops\start-icore.ps1"
if (-not (Test-Path $Ico)) { throw "Missing icon: $Ico" }
if (-not (Test-Path $Launcher)) { throw "Missing launcher: $Launcher" }

function Test-RealPython([string]$Path) {
    if (-not $Path) { return $false }
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    if ($Path -match "WindowsApps") { return $false }
    return $true
}

$PythonW = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\pythonw.exe"
if (-not (Test-RealPython $PythonW)) {
    $PythonW = Join-Path $Repo ".venv\Scripts\pythonw.exe"
}
$UsePythonW = Test-RealPython $PythonW

$Desktop = [Environment]::GetFolderPath("Desktop")
$LnkPath = Join-Path $Desktop "iCore.lnk"
$Wsh = New-Object -ComObject WScript.Shell
$Lnk = $Wsh.CreateShortcut($LnkPath)
if ($UsePythonW) {
    $Lnk.TargetPath = $PythonW
    $Lnk.Arguments = "-m cancer_claw.desktop"
} else {
    $Pwsh = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $Lnk.TargetPath = $Pwsh
    $Lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Launcher`""
}
$Lnk.WorkingDirectory = $Repo
$Lnk.IconLocation = "$Ico,0"
$Lnk.Hotkey = "Ctrl+Alt+I"
$Lnk.Description = "iCore desktop client (C/S, full workbench)"
$Lnk.WindowStyle = 1
$Lnk.Save()

$Check = $Wsh.CreateShortcut($LnkPath)
Write-Output ("lnk=" + $Check.FullName)
Write-Output ("target=" + $Check.TargetPath)
Write-Output ("args=" + $Check.Arguments)
Write-Output ("icon=" + $Check.IconLocation)
Write-Output ("hotkey=" + $Check.Hotkey)
