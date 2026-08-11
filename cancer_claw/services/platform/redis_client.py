

# lazy init
from __future__ import annotations

import asyncio
from typing import Any

import structlog

from cancer_claw.config import settings

logger = structlog.get_logger()

_redis: Any = None
_lock: asyncio.Lock | None = None

def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock

def redis_enabled() -> bool:

    return settings.redis.enabled

def rkey(*parts: str) -> str:

    return ":".join([settings.redis.key_prefix, *parts])

async def get_redis():

    global _redis
    if not settings.redis.enabled:
        return None
    if _redis is not None:
        return _redis
    async with _get_lock():
        if _redis is not None:
            return _redis
        import redis.asyncio as aioredis

        _redis = aioredis.from_url(
            settings.redis.url,
            decode_responses=True,
            health_check_interval=30,
            socket_keepalive=True,
        )

        await _redis.ping()
        logger.info("redis_connected", url=settings.redis.url)
        return _redis

async def close_redis() -> None:

    global _redis
    if _redis is not None:
        try:
            await _redis.aclose()
        except Exception:
            pass
        _redis = None
