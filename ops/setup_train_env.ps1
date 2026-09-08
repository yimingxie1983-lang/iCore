# Create / repair the isolated GPU training env on D: (default D:\icore-ml).
# Do NOT install torch into the iCore app .venv.
# Do NOT use C:\Users\...\AppData for pip cache or unpack temp.
#
# Usage (repo root):
#   powershell -File ops/setup_train_env.ps1
#   powershell -File ops/setup_train_env.ps1 -TargetRoot D:\icore-ml
param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$TargetRoot = "D:\icore-ml"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $ProjectRoot

if (-not (Test-Path -LiteralPath "D:\")) {
    throw "Drive D: is required for the GPU training env."
}

function Invoke-RobocopyOk {
    param([string]$From, [string]$To)
    New-Item -ItemType Directory -Force -Path $To | Out-Null
    $saved = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & robocopy $From $To /E /COPY:DAT /R:2 /W:2 /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
    $code = $LASTEXITCODE
    $ErrorActionPreference = $saved
    if ($code -ge 8) {
        throw "robocopy failed ($code): $From -> $To"
    }
}

function Get-PythonHome {
    param([string]$PythonExe)
    $cfg = Join-Path (Split-Path (Split-Path $PythonExe -Parent) -Parent) "pyvenv.cfg"
    if (Test-Path -LiteralPath $cfg) {
        $line = Select-String -LiteralPath $cfg -Pattern "^home\s*=\s*(.+)$" | Select-Object -First 1
        if ($line) {
            return $line.Matches[0].Groups[1].Value.Trim()
        }
    }
    return Split-Path $PythonExe -Parent
}

$venvDir = Join-Path $TargetRoot "venv"
$pyHome = Join-Path $TargetRoot "python"
$cacheRoot = Join-Path $TargetRoot "cache"
$pipCache = Join-Path $cacheRoot "pip"
$hfCache = Join-Path $cacheRoot "huggingface"
$torchCache = Join-Path $cacheRoot "torch"
$tmpDir = Join-Path $TargetRoot "tmp"
$py = Join-Path $venvDir "Scripts\python.exe"

foreach ($dir in @($pyHome, $pipCache, $hfCache, $torchCache, $tmpDir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

$env:PIP_CACHE_DIR = $pipCache
$env:TEMP = $tmpDir
$env:TMP = $tmpDir
$env:TMPDIR = $tmpDir
$env:HF_HOME = $hfCache
$env:TORCH_HOME = $torchCache
$env:XDG_CACHE_HOME = $cacheRoot

Write-Host ">>> training root $TargetRoot (pip/temp/hf on D:)"

$cPip = Join-Path $env:LOCALAPPDATA "pip\Cache"
if (Test-Path -LiteralPath $cPip) {
    Write-Host ">>> migrate pip cache off C: -> $pipCache"
    Invoke-RobocopyOk $cPip $pipCache
    Remove-Item -LiteralPath $cPip -Recurse -Force -ErrorAction SilentlyContinue
}

$bootstrap = $null
$appVenv = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$legacyVenv = Join-Path $ProjectRoot ".venv-train\Scripts\python.exe"
if (Test-Path -LiteralPath (Join-Path $pyHome "python.exe")) {
    $bootstrap = Join-Path $pyHome "python.exe"
} elseif (Test-Path -LiteralPath $legacyVenv) {
    $bootstrap = $legacyVenv
} elseif (Test-Path -LiteralPath $appVenv) {
    $bootstrap = $appVenv
} else {
    $bootstrap = "python"
}

$homeSrc = $null
try {
    $homeSrc = Get-PythonHome $bootstrap
} catch {
    $homeSrc = $null
}
if (-not $homeSrc -or -not (Test-Path -LiteralPath (Join-Path $homeSrc "python.exe"))) {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $homeSrc = (& py -3.12 -c "import sys; print(sys.base_prefix)").Trim()
    }
}
if (-not $homeSrc -or -not (Test-Path -LiteralPath (Join-Path $homeSrc "python.exe"))) {
    throw "Cannot find a CPython home to copy onto D:."
}

$dstPy = Join-Path $pyHome "python.exe"
if (-not (Test-Path -LiteralPath $dstPy)) {
    Write-Host ">>> copy base Python to $pyHome"
    Invoke-RobocopyOk $homeSrc $pyHome
}
$bootstrap = $dstPy

if (-not (Test-Path -LiteralPath $py)) {
    $legacyDir = Join-Path $ProjectRoot ".venv-train"
    if (Test-Path -LiteralPath $legacyDir) {
        Write-Host ">>> move $legacyDir -> $venvDir"
        Move-Item -LiteralPath $legacyDir -Destination $venvDir
    } else {
        Write-Host ">>> create $venvDir"
        & $bootstrap -m venv $venvDir
    }
}

$cfgPath = Join-Path $venvDir "pyvenv.cfg"
@(
    "home = $pyHome"
    "include-system-site-packages = false"
    "executable = $py"
    "command = $bootstrap -m venv $venvDir"
) | Set-Content -LiteralPath $cfgPath -Encoding ASCII

$siteCustomize = Join-Path $venvDir "Lib\site-packages\sitecustomize.py"
$siteCustomizeBody = @"
import os
from pathlib import Path
_root = Path(r"$TargetRoot")
os.environ["PIP_CACHE_DIR"] = str(_root / "cache" / "pip")
os.environ["HF_HOME"] = str(_root / "cache" / "huggingface")
os.environ["TRANSFORMERS_CACHE"] = str(_root / "cache" / "huggingface")
os.environ["TORCH_HOME"] = str(_root / "cache" / "torch")
os.environ["XDG_CACHE_HOME"] = str(_root / "cache")
"@
Set-Content -LiteralPath $siteCustomize -Value $siteCustomizeBody -Encoding ASCII

if (-not (Test-Path -LiteralPath $py)) {
    throw "Training python missing: $py"
}

Write-Host ">>> upgrade pip"
& $py -m pip install --upgrade pip wheel "setuptools>=70,<82"
if ($LASTEXITCODE -ne 0) {
    throw "pip upgrade failed"
}

$needTorch = $true
& $py -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 2)"
if ($LASTEXITCODE -eq 0) {
    $needTorch = $false
    Write-Host ">>> CUDA torch already available, skip reinstall"
}

if ($needTorch) {
    $indexes = @(
        "https://download.pytorch.org/whl/cu128",
        "https://download.pytorch.org/whl/cu126",
        "https://download.pytorch.org/whl/cu124"
    )
    $torchOk = $false
    foreach ($idx in $indexes) {
        Write-Host ">>> try CUDA torch from $idx"
        & $py -m pip install torch torchvision --index-url $idx
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    install failed, try next index"
            continue
        }
        & $py -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 2)"
        if ($LASTEXITCODE -eq 0) {
            $torchOk = $true
            break
        }
        Write-Host "    torch installed but CUDA not visible, try next index"
    }
    if (-not $torchOk) {
        throw "Failed to install a CUDA-enabled PyTorch. Check nvidia-smi, then rerun this script."
    }
}

Write-Host ">>> install sklearn / pandas / matplotlib"
& $py -m pip install "scikit-learn>=1.4" "pandas>=2.2" "numpy>=1.26" "matplotlib>=3.8" pillow
if ($LASTEXITCODE -ne 0) {
    throw "sklearn stack install failed"
}

Write-Host ">>> verify"
$verify = @'
import torch, sklearn, pandas, numpy, sys
print("python", sys.executable)
print("prefix", sys.prefix)
print("torch", torch.__version__)
print("cuda", torch.cuda.is_available())
print("gpu", torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)
print("sklearn", sklearn.__version__)
raise SystemExit(0 if torch.cuda.is_available() else 2)
'@
$verifyFile = Join-Path $tmpDir "verify_cuda.py"
Set-Content -LiteralPath $verifyFile -Value $verify -Encoding ASCII
& $py $verifyFile
$verifyCode = $LASTEXITCODE
Remove-Item -LiteralPath $verifyFile -ErrorAction SilentlyContinue
if ($verifyCode -ne 0) {
    throw "Verification failed: torch.cuda.is_available() is not True."
}

$oldTemp = Join-Path $env:LOCALAPPDATA "Temp"
if (Test-Path -LiteralPath $oldTemp) {
    Get-ChildItem -LiteralPath $oldTemp -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^(pip-|pip-unpack-|pip-install-|tmp.*torch|wheel-)' } |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
}

Write-Host "Training env ready: $py"
Write-Host "Caches: $cacheRoot"
Write-Host "Temp:   $tmpDir"
