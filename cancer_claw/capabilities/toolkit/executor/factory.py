

from __future__ import annotations

import asyncio
import sys
from threading import Lock
from typing import Optional

import structlog

from cancer_claw.config import settings
from cancer_claw.capabilities.toolkit.executor.base import (
    ProjectExecutor,
    SandboxError,
    SandboxPolicy,
    SandboxUnavailable,
)

logger = structlog.get_logger()

_DEFAULT_SANDBOX_MODE = "native"

def sandbox_mode() -> str:

    raw = getattr(settings, "sandbox", None)
    mode = _DEFAULT_SANDBOX_MODE
    if raw is not None:
        mode = str(getattr(raw, "mode", _DEFAULT_SANDBOX_MODE)).lower().strip()

    if mode not in ("native", "off"):
        logger.warning("sandbox_mode_invalid", received=mode, fallback=_DEFAULT_SANDBOX_MODE)
        return _DEFAULT_SANDBOX_MODE
    return mode

def _policy_from_settings() -> SandboxPolicy:

    sb = getattr(settings, "sandbox", None)
    if sb is None:
        return SandboxPolicy()
    return SandboxPolicy(
        max_memory_bytes=int(getattr(sb, "max_memory_mb", 2048)) * 1024 * 1024,
        max_processes=int(getattr(sb, "max_processes", 64)),
        cpu_time_seconds=int(getattr(sb, "cpu_time_seconds", 3600)),
        low_integrity=bool(getattr(sb, "low_integrity", True)),
        redirect_env_dirs=bool(getattr(sb, "redirect_env_dirs", True)),
    )

def is_sandbox_enabled() -> bool:

    return sandbox_mode() == "native"

def _build_executor(project_id: str, policy: SandboxPolicy) -> ProjectExecutor:

    if sys.platform == "win32":

        from cancer_claw.capabilities.toolkit.executor.win_executor import WinProjectExecutor
        return WinProjectExecutor(project_id, policy)


    if sys.platform.startswith("linux"):
        raise SandboxUnavailable(
            "Linux sandbox (unshare + seccomp) not implemented yet; "
            "set config.yaml sandbox.mode: off to fall back"
        )
    if sys.platform == "darwin":
        raise SandboxUnavailable(
            "macOS sandbox (sandbox-exec) not implemented yet; "
            "set config.yaml sandbox.mode: off to fall back"
        )

    raise SandboxUnavailable(f"unsupported platform: {sys.platform}")

_cache: dict[str, ProjectExecutor] = {}
_cache_lock = Lock()
_creation_locks: dict[str, asyncio.Lock] = {}

def _get_creation_lock(project_id: str) -> asyncio.Lock:

    with _cache_lock:
        lock = _creation_locks.get(project_id)
        if lock is None:
            lock = asyncio.Lock()
            _creation_locks[project_id] = lock
        return lock

async def get_project_executor(
    project_id: str,
    *,
    policy: SandboxPolicy | None = None,
) -> Optional[ProjectExecutor]:

    if not is_sandbox_enabled():
        return None


    existing = _cache.get(project_id)
    if existing is not None and existing.is_alive:
        return existing


    lock = _get_creation_lock(project_id)
    async with lock:

        existing = _cache.get(project_id)
        if existing is not None and existing.is_alive:
            return existing


        effective_policy = policy or _policy_from_settings()
        executor = _build_executor(project_id, effective_policy)
        try:


            executor.prepare()
        except SandboxUnavailable:

            logger.error("sandbox_unavailable", project_id=project_id, exc_info=True)
            raise
        except Exception as e:
            logger.error("sandbox_prepare_failed", project_id=project_id, error=str(e), exc_info=True)
            raise SandboxError(f"failed to prepare sandbox for {project_id}: {e}") from e

        with _cache_lock:
            _cache[project_id] = executor
        logger.info("sandbox_created", project_id=project_id, kind=executor.kind)
        return executor

async def close_project_executor(project_id: str) -> bool:

    with _cache_lock:
        executor = _cache.pop(project_id, None)
        _creation_locks.pop(project_id, None)

    if executor is None:
        return True

    try:
        await executor.close()
        logger.info("sandbox_closed", project_id=project_id)
        return True
    except Exception as e:
        logger.error("sandbox_close_failed", project_id=project_id, error=str(e), exc_info=True)
        return False

async def close_all_executors() -> None:

    with _cache_lock:
        items = list(_cache.items())
        _cache.clear()
        _creation_locks.clear()

    for project_id, executor in items:
        try:
            await executor.close()
            logger.info("sandbox_closed_on_shutdown", project_id=project_id)
        except Exception as e:
            logger.error("sandbox_shutdown_close_failed",
                         project_id=project_id, error=str(e), exc_info=True)

def _debug_list_projects() -> list[str]:

    with _cache_lock:
        return list(_cache.keys())

__all__ = [
    "close_all_executors",
    "close_project_executor",
    "get_project_executor",
    "is_sandbox_enabled",
    "sandbox_mode",
]
