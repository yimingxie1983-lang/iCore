

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import structlog
from fastapi import APIRouter, Depends

from cancer_claw.services.identity.deps import require_admin
from cancer_claw.config import settings

logger = structlog.get_logger()
router = APIRouter()

try:
    import psutil

    _PSUTIL = True
    _PROC = psutil.Process(os.getpid())

    psutil.cpu_percent(interval=None)
    _PROC.cpu_percent(interval=None)
except Exception:
    _PSUTIL = False
    _PROC = None

_WORKER_START = time.time()
_WORKER_PID = os.getpid()

_net_last: tuple[float, int, int] | None = None

def _disk_target() -> str:

    p = os.path.abspath(settings.paths.data_dir or ".")
    return p if os.path.exists(p) else os.path.abspath(".")

def _collect_system_sync() -> dict[str, Any]:

    if not _PSUTIL:
        return {"available": False}

    global _net_last


    per_core = psutil.cpu_percent(interval=0.15, percpu=True)
    cpu_overall = round(sum(per_core) / len(per_core), 1) if per_core else 0.0

    try:
        load1, load5, load15 = psutil.getloadavg()
    except Exception:
        load1 = load5 = load15 = None

    vm = psutil.virtual_memory()
    du = psutil.disk_usage(_disk_target())
    net = psutil.net_io_counters()

    now = time.time()
    sent_rate = recv_rate = None
    if _net_last is not None:
        dt = now - _net_last[0]
        if dt > 0:
            sent_rate = max(0, int((net.bytes_sent - _net_last[1]) / dt))
            recv_rate = max(0, int((net.bytes_recv - _net_last[2]) / dt))
    _net_last = (now, net.bytes_sent, net.bytes_recv)

    proc_rss = _PROC.memory_info().rss if _PROC else None
    proc_cpu = _PROC.cpu_percent(interval=None) if _PROC else None
    proc_threads = _PROC.num_threads() if _PROC else None

    return {
        "available": True,
        "cpu": {
            "percent": cpu_overall,
            "per_core": [round(x, 1) for x in per_core],
            "cores": len(per_core),
            "load_avg": [load1, load5, load15],
        },
        "memory": {
            "total": vm.total,
            "used": vm.used,
            "available": vm.available,
            "percent": vm.percent,
        },
        "disk": {
            "path": _disk_target(),
            "total": du.total,
            "used": du.used,
            "free": du.free,
            "percent": du.percent,
        },
        "network": {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
            "sent_rate": sent_rate,
            "recv_rate": recv_rate,
        },
        "process": {
            "pid": _WORKER_PID,
            "rss": proc_rss,
            "cpu_percent": proc_cpu,
            "threads": proc_threads,
        },
    }

def _rate_key(sec: int) -> str:
    from cancer_claw.services.platform.redis_client import rkey

    return rkey("metrics", "req", str(sec))

async def record_request() -> None:

    if not settings.redis.enabled:
        return
    try:
        from cancer_claw.services.platform.redis_client import get_redis

        r = await get_redis()
        key = _rate_key(int(time.time()))
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, 180)
        await pipe.execute()
    except Exception:
        pass

async def _request_rate(window: int = 60) -> dict[str, Any] | None:
    if not settings.redis.enabled:
        return None
    try:
        from cancer_claw.services.platform.redis_client import get_redis

        r = await get_redis()
        now = int(time.time())

        keys = [_rate_key(now - i) for i in range(1, window + 1)]
        vals = await r.mget(keys)
        nums = [int(v) for v in vals if v]
        total = sum(nums)
        return {
            "per_sec_avg": round(total / window, 2),
            "last_sec": int(vals[0]) if vals and vals[0] else 0,
            "peak_sec": max(nums) if nums else 0,
            "window": window,
        }
    except Exception:
        return None

async def _service_health() -> dict[str, str]:
    components: dict[str, str] = {}
    try:
        from cancer_claw.db import get_read_db

        db = await get_read_db()
        await db.execute("SELECT 1")
        components["database"] = "ok"
    except Exception as e:
        components["database"] = f"error: {e}"

    if settings.redis.enabled:
        try:
            from cancer_claw.services.platform.redis_client import get_redis

            r = await get_redis()
            await r.ping()
            components["redis"] = "ok"
        except Exception as e:
            components["redis"] = f"error: {e}"
    return components

async def _active_sessions() -> int | None:
    try:
        from cancer_claw.agent.engine.session_hub import get_session_hub

        hub = get_session_hub()
        return len(await hub.running_session_ids())
    except Exception:
        return None

@router.get("/admin/metrics", tags=["系统监控"])
async def system_metrics(_user: dict = Depends(require_admin)) -> dict[str, Any]:

    system, components, active, rate = await asyncio.gather(
        asyncio.to_thread(_collect_system_sync),
        _service_health(),
        _active_sessions(),
        _request_rate(),
    )

    bad = [k for k, v in components.items() if v != "ok"]
    return {
        "timestamp": time.time(),
        "system": system,
        "services": {
            "status": "healthy" if not bad else "degraded",
            "components": components,
            "backend": "postgres" if settings.database.is_postgres else "sqlite",
            "multi_worker": settings.redis.enabled,
        },
        "app": {
            "version": settings.app.version,
            "active_sessions": active,
            "request_rate": rate,
            "worker_pid": _WORKER_PID,
            "worker_uptime_seconds": round(time.time() - _WORKER_START, 1),
            "configured_workers": int(os.environ.get("WEB_CONCURRENCY", "0")) or None,
        },
    }
