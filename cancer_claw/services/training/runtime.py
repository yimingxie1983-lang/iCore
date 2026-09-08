from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from cancer_claw.config import settings


class GpuInfo(BaseModel):
    name: str = ""
    memory_total_mb: int = 0
    driver: str = ""
    compute_cap: str = ""


class TrainingRuntime(BaseModel):
    python: str = ""
    python_ready: bool = False
    setup_hint: str = "powershell -File ops/setup_train_env.ps1"
    torch_version: str = ""
    cuda_available: bool = False
    cuda_version: str = ""
    gpu: GpuInfo | None = None
    max_vram_mb: int = 7168
    sklearn_ready: bool = False
    hint: str = ""


def training_root() -> Path:
    raw = (getattr(settings.training, "root", "") or "").strip()
    if raw:
        return Path(raw)
    py = resolve_training_python()
    # .../venv/Scripts/python.exe -> root
    if py.name.lower() == "python.exe" and py.parent.name.lower() == "scripts":
        venv = py.parent.parent
        if venv.name.lower() == "venv":
            return venv.parent
    dedicated = Path(r"D:\icore-ml")
    if dedicated.exists():
        return dedicated
    return Path(settings.project_root)


def training_cache_env() -> dict[str, str]:
    root = training_root()
    cache = root / "cache"
    tmp = root / "tmp"
    for path in (
        cache / "pip",
        cache / "huggingface",
        cache / "torch",
        tmp,
    ):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    return {
        "PIP_CACHE_DIR": str(cache / "pip"),
        "HF_HOME": str(cache / "huggingface"),
        "TRANSFORMERS_CACHE": str(cache / "huggingface"),
        "TORCH_HOME": str(cache / "torch"),
        "XDG_CACHE_HOME": str(cache),
        "TMPDIR": str(tmp),
        "TEMP": str(tmp),
        "TMP": str(tmp),
    }


def resolve_training_python() -> Path:
    raw = (settings.training.python or "").strip()
    if raw:
        p = Path(raw)
        if p.exists():
            return p
    root = (getattr(settings.training, "root", "") or "").strip()
    if root:
        p = Path(root) / "venv" / "Scripts" / "python.exe"
        if p.exists():
            return p
    dedicated = Path(r"D:\icore-ml") / "venv" / "Scripts" / "python.exe"
    if dedicated.exists():
        return dedicated
    return Path(settings.project_root) / ".venv-train" / "Scripts" / "python.exe"


def _nvidia_smi() -> GpuInfo | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [
                exe,
                "--query-gpu=name,memory.total,driver_version,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return None
    line = proc.stdout.strip().splitlines()[0]
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 2:
        return None
    try:
        mem = int(float(parts[1]))
    except ValueError:
        mem = 0
    return GpuInfo(
        name=parts[0],
        memory_total_mb=mem,
        driver=parts[2] if len(parts) > 2 else "",
        compute_cap=parts[3] if len(parts) > 3 else "",
    )


def _probe_python(python: Path) -> dict[str, Any]:
    code = (
        "import json,sys\n"
        "out={'torch':'','cuda':False,'cuda_ver':'','gpu':'','sklearn':False}\n"
        "try:\n"
        " import torch\n"
        " out['torch']=getattr(torch,'__version__','')\n"
        " out['cuda']=bool(torch.cuda.is_available())\n"
        " out['cuda_ver']=str(getattr(torch.version,'cuda',None) or '')\n"
        " if out['cuda'] and torch.cuda.device_count():\n"
        "  out['gpu']=torch.cuda.get_device_name(0)\n"
        "except Exception:\n"
        " pass\n"
        "try:\n"
        " import sklearn  # noqa: F401\n"
        " out['sklearn']=True\n"
        "except Exception:\n"
        " pass\n"
        "sys.stdout.write(json.dumps(out))\n"
    )
    try:
        proc = subprocess.run(
            [str(python), "-c", code],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            env={**os.environ, **training_cache_env()},
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return {}
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def probe_runtime() -> TrainingRuntime:
    python = resolve_training_python()
    ready = python.exists()
    gpu = _nvidia_smi()
    torch_info: dict[str, Any] = _probe_python(python) if ready else {}
    cuda = bool(torch_info.get("cuda"))
    sklearn_ready = bool(torch_info.get("sklearn"))
    gpu_name = str(torch_info.get("gpu") or "")
    if gpu and not gpu.name:
        gpu.name = gpu_name
    elif gpu_name and gpu is None:
        gpu = GpuInfo(name=gpu_name)

    hint = ""
    if not ready:
        hint = (
            "训练环境尚未创建。请在仓库根目录运行 "
            "powershell -File ops/setup_train_env.ps1 ，"
            "不要把 torch 装进 iCore 应用 .venv。"
        )
    elif not cuda:
        hint = (
            "训练 Python 已就绪，但当前是 CPU 版或看不到 GPU。"
            "请重跑 ops/setup_train_env.ps1 安装 CUDA 版 PyTorch。"
        )
        if gpu:
            hint += f" 本机已检测到 {gpu.name}。"
    else:
        hint = "CUDA 可用，可以开始本机训练。"

    return TrainingRuntime(
        python=str(python) if ready else str(python),
        python_ready=ready,
        torch_version=str(torch_info.get("torch") or ""),
        cuda_available=cuda,
        cuda_version=str(torch_info.get("cuda_ver") or ""),
        gpu=gpu,
        max_vram_mb=int(settings.training.max_vram_mb or 7168),
        sklearn_ready=sklearn_ready,
        hint=hint,
    )
