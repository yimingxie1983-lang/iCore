# Pack iCore C/S desktop client: WebView window + local FastAPI (full B/S UI).
# Usage: powershell -File ops/build_client.ps1

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

python -m pip install -q "pywebview>=5.0" "pyinstaller>=6.0"

$webDist = Join-Path $Repo "web\dist\index.html"
if (-not (Test-Path $webDist)) {
    Push-Location (Join-Path $Repo "web")
    npm run build
    Pop-Location
}

$ico = Join-Path $Repo "ops\icore.ico"
$out = Join-Path $Repo "ops\client"
New-Item -ItemType Directory -Force -Path $out | Out-Null

$iconArgs = @()
if (Test-Path $ico) {
    $iconArgs = @("--icon", $ico)
}

python -m PyInstaller --noconfirm --clean --windowed --name iCore @iconArgs `
    --paths $Repo `
    --hidden-import cancer_claw.desktop.shell `
    --hidden-import cancer_claw.desktop.menu `
    --hidden-import yaml `
    --hidden-import webview `
    --distpath $out `
    --workpath (Join-Path $out "build") `
    --specpath $out `
    (Join-Path $Repo "cancer_claw\desktop\__main__.py")

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed (exit $LASTEXITCODE). Close iCore.exe and retry."
}

$built = Join-Path $out "iCore\iCore.exe"
if (-not (Test-Path $built)) {
    throw "Missing build output: $built"
}
Write-Host "built $built"
