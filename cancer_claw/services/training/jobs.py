from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import structlog

from cancer_claw.capabilities.toolkit.executor import get_project_executor, is_sandbox_enabled
from cancer_claw.capabilities.toolkit.executor.bg_log import HEADER_RESERVED_BYTES
from cancer_claw.capabilities.toolkit.workspace import get_project_workspace_root
from cancer_claw.services.training import repo
from cancer_claw.services.training.runtime import resolve_training_python, training_cache_env
from cancer_claw.services.training.schema import DesignDoc

logger = structlog.get_logger()

_FALLBACK: dict[str, subprocess.Popen] = {}
_EPOCH_RE = re.compile(r"epoch\s*=\s*(\d+)\s*/\s*(\d+)", re.I)
_STREAM_PREFIX_RE = re.compile(
    r"^\[\d{4}-\d{2}-\d{2}T[^\]]+\]\s*\[(?:stdout|stderr)\]\s*"
)


def _run_root(project_id: str, run_id: str) -> Path:
    return get_project_workspace_root(project_id) / "runs" / run_id


def _script_file(project_id: str, run: dict[str, Any]) -> Path:
    raw = (run.get("script_path") or "").strip()
    ws = get_project_workspace_root(project_id)
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            rel = raw[10:] if raw.startswith("workspace/") else raw
            p = ws / rel
        if p.exists():
            return p
    return _run_root(project_id, run["id"]) / "train.py"


def _python_exe(run: dict[str, Any]) -> Path:
    raw = (run.get("python_exe") or "").strip()
    if raw and Path(raw).exists():
        return Path(raw)
    resolved = resolve_training_python()
    if resolved.exists():
        return resolved
    return Path(sys.executable)


def _pid_alive(pid: Any) -> bool:
    try:
        value = int(pid)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, value
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(value, 0)
        return True
    except OSError:
        return False


def _log_looks_done(text: str) -> bool:
    return "TRAINING DONE" in (text or "")


async def refresh_run(project_id: str, run_id: str) -> dict[str, Any] | None:
    run = await repo.get_run(project_id, run_id)
    if run is None:
        return None
    if run.get("status") != "running":
        _attach_metrics(project_id, run)
        _attach_progress(run)
        return run

    alive = False
    exit_code: int | None = None
    pid = run.get("pid")
    executor = None
    if is_sandbox_enabled():
        try:
            executor = await get_project_executor(project_id)
        except Exception:
            executor = None
    if executor is not None and pid:
        try:
            infos = await executor.list_background()
            cur = next((i for i in infos if i.pid == int(pid)), None)
            if cur is None:
                alive = _pid_alive(pid)
            elif cur.status == "running":
                alive = True
            else:
                alive = False
                exit_code = cur.returncode
        except Exception as e:
            logger.warning("train_refresh_sandbox_failed", error=str(e))
            alive = _pid_alive(pid)
    proc = _FALLBACK.get(run_id)
    if proc is not None:
        code = proc.poll()
        if code is None:
            alive = True
        else:
            alive = False
            exit_code = code
            _FALLBACK.pop(run_id, None)
    elif not alive:
        alive = _pid_alive(pid)

    if alive:
        _attach_metrics(project_id, run)
        _attach_progress(run)
        return run

    metrics = _read_metrics(project_id, run_id)
    log_text, _ = read_log(run.get("log_path") or "", offset=0, limit=64000)
    succeeded = (
        exit_code == 0
        or bool(metrics)
        or _log_looks_done(log_text)
    )
    status = "succeeded" if succeeded else "failed"
    error = ""
    if not succeeded:
        error = (
            f"训练进程退出码 {exit_code}"
            if exit_code not in (None, 0)
            else "训练进程已结束，但没有指标产物"
        )
    updated = await repo.update_run(
        project_id,
        run_id,
        status=status,
        error=error,
        metrics_json=metrics or "",
        finished_at=_now(),
    )
    result = updated or run
    _attach_progress(result)
    return result


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _read_metrics(project_id: str, run_id: str) -> dict[str, Any] | None:
    path = _run_root(project_id, run_id) / "results" / "metrics.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _attach_metrics(project_id: str, run: dict[str, Any]) -> None:
    metrics = _read_metrics(project_id, run["id"])
    if metrics:
        run["metrics"] = metrics


def _attach_progress(run: dict[str, Any]) -> None:
    text, _ = read_log(run.get("log_path") or "", offset=0, limit=64000)
    run["progress"] = parse_progress(text, run)


async def start_run(project_id: str, run: dict[str, Any]) -> dict[str, Any]:
    design = run.get("design") or {}
    doc = DesignDoc.model_validate(design) if design else None
    if doc is not None and not doc.can_train():
        raise ValueError(doc.feasibility_reason or "当前方案不可在本机训练")

    script = _script_file(project_id, run)
    if not script.exists():
        raise FileNotFoundError(f"找不到训练脚本: {script}")
    python = _python_exe(run)
    cwd = str(script.parent)
    cmd = [str(python), "-u", str(script)]
    train_env = {**os.environ, **training_cache_env()}
    train_env["PYTHONUNBUFFERED"] = "1"

    pid = 0
    log_path = str(script.parent / "train.log")
    executor = None
    if is_sandbox_enabled():
        try:
            executor = await get_project_executor(project_id)
        except Exception as e:
            logger.warning("train_sandbox_unavailable", error=str(e))
            executor = None

    if executor is not None:
        info = await executor.run_background(cmd, cwd=cwd, env=train_env)
        pid = int(info.pid)
        found = executor.get_background_log_path(pid)
        if found:
            log_path = found
    else:
        log_file = Path(log_path)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handle = log_file.open("ab")
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=train_env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )
        _FALLBACK[run["id"]] = proc
        pid = int(proc.pid)

    updated = await repo.update_run(
        project_id,
        run["id"],
        status="running",
        pid=pid,
        log_path=log_path,
        python_exe=str(python),
        error="",
    )
    result = updated or run
    _attach_progress(result)
    return result


async def cancel_run(project_id: str, run: dict[str, Any]) -> dict[str, Any]:
    pid = run.get("pid")
    killed = False
    if is_sandbox_enabled() and pid:
        try:
            executor = await get_project_executor(project_id)
            if executor is not None:
                killed = await executor.kill_background(int(pid))
        except Exception as e:
            logger.warning("train_cancel_sandbox_failed", error=str(e))
    proc = _FALLBACK.pop(run["id"], None)
    if proc is not None and proc.poll() is None:
        proc.kill()

        def _wait() -> None:
            try:
                proc.wait(timeout=5)
            except Exception:
                pass

        await asyncio.to_thread(_wait)
        killed = True

    if not killed and pid:
        try:
            import os
            import signal

            os.kill(int(pid), signal.SIGTERM)
            killed = True
        except OSError:
            pass

    updated = await repo.update_run(
        project_id,
        run["id"],
        status="cancelled",
        error="用户取消",
        finished_at=_now(),
    )
    return updated or run


def _body_start(data: bytes) -> int:
    reserved = int(HEADER_RESERVED_BYTES)
    if (
        len(data) >= reserved
        and data.startswith(b"---")
        and data[reserved - 1 : reserved] == b"\n"
    ):
        return reserved
    return 0


def _decode_chunk(chunk: bytes) -> str:
    text = chunk.decode("utf-8", errors="replace")
    if not text:
        text = chunk.decode("gbk", errors="replace")
    lines: list[str] = []
    for raw in text.splitlines(keepends=True):
        ended = raw.endswith("\n")
        line = raw[:-1] if ended else raw
        line = _STREAM_PREFIX_RE.sub("", line)
        lines.append(line + ("\n" if ended else ""))
    return "".join(lines)


def parse_progress(text: str, run: dict[str, Any] | None = None) -> dict[str, Any]:
    last_line = ""
    for line in reversed((text or "").splitlines()):
        stripped = line.strip()
        if stripped:
            last_line = stripped[-240:]
            break
    epoch = 0
    epochs = 0
    for match in _EPOCH_RE.finditer(text or ""):
        epoch = int(match.group(1))
        epochs = int(match.group(2))
    status = str((run or {}).get("status") or "")
    percent = 0
    if status == "succeeded" or _log_looks_done(text):
        percent = 100
    elif epoch and epochs:
        percent = max(1, min(99, round(100 * epoch / epochs)))
    elif status == "running" and last_line:
        percent = 8
    return {
        "last_line": last_line,
        "epoch": epoch,
        "epochs": epochs,
        "percent": percent,
        "done": percent >= 100 or status == "succeeded",
    }


def read_log(log_path: str, *, offset: int = 0, limit: int = 8000) -> tuple[str, int]:
    path = Path(log_path) if log_path else None
    if path is None or not path.exists():
        return "", 0
    data = path.read_bytes()
    body = _body_start(data)
    start = max(body, int(offset))
    chunk = data[start : start + max(1, int(limit))]
    return _decode_chunk(chunk), start + len(chunk)


def list_artifacts(project_id: str, run_id: str) -> list[dict[str, str]]:
    root = _run_root(project_id, run_id)
    if not root.exists():
        return []
    items: list[dict[str, str]] = []
    ws = get_project_workspace_root(project_id)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name.endswith(".log") or path.suffix == ".py":
            continue
        try:
            rel = path.resolve().relative_to(ws.resolve()).as_posix()
        except ValueError:
            continue
        items.append(
            {
                "name": path.name,
                "path": f"workspace/{rel}",
            }
        )
    items.sort(key=lambda x: x["path"])
    return items
