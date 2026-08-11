

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager

import structlog

from cancer_claw.config import settings
from cancer_claw.services.platform.redis_client import get_redis, rkey

logger = structlog.get_logger()

_SLOT_TTL = 180

_CONC_RETRY = 0.05

_RPM_MAX_WAIT = 5.0

_local_sem: asyncio.Semaphore | None = None

def _get_local_sem() -> asyncio.Semaphore | None:
    global _local_sem
    limit = settings.concurrency.llm_max_concurrency
    if limit <= 0:
        return None
    if _local_sem is None:
        _local_sem = asyncio.Semaphore(limit)
    return _local_sem

_LUA_CONC_ACQUIRE = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - ttl)
local count = redis.call('ZCARD', key)
if count < limit then
  redis.call('ZADD', key, now, member)
  redis.call('EXPIRE', key, ttl + 60)
  return 1
else
  return 0
end
"""

_LUA_TOKEN_BUCKET = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then tokens = burst; ts = now end
local delta = now - ts
if delta < 0 then delta = 0 end
tokens = math.min(burst, tokens + delta * rate)
local allowed = 0
local wait = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  wait = (1 - tokens) / rate
end
redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, 120)
return {allowed, tostring(wait)}
"""

async def _rpm_gate(r, provider_id: str) -> None:

    rpm = settings.concurrency.llm_rpm
    if rpm <= 0:
        return
    rate = rpm / 60.0
    burst = float(rpm)
    key = rkey("rl", "rpm", provider_id)
    while True:
        res = await r.eval(_LUA_TOKEN_BUCKET, 1, key, str(rate), str(burst), str(time.time()))
        allowed = int(res[0])
        if allowed == 1:
            return
        try:
            wait = float(res[1])
        except (TypeError, ValueError):
            wait = 0.2
        await asyncio.sleep(min(_RPM_MAX_WAIT, max(0.01, wait)))

async def _conc_acquire(r, key: str, member: str) -> None:

    limit = settings.concurrency.llm_max_concurrency
    if limit <= 0:
        return
    attempt = 0
    while True:
        got = await r.eval(
            _LUA_CONC_ACQUIRE, 1, key, str(time.time()), str(_SLOT_TTL), str(limit), member
        )
        if int(got) == 1:
            return
        attempt += 1

        await asyncio.sleep(_CONC_RETRY * (1 + (attempt % 5) * 0.2))

@asynccontextmanager
async def llm_slot(provider_id: str = "default"):

    r = await get_redis()
    if r is None:

        sem = _get_local_sem()
        if sem is None:
            yield
            return
        async with sem:
            yield
        return


    await _rpm_gate(r, provider_id)
    key = rkey("rl", "conc", provider_id)
    member = uuid.uuid4().hex
    await _conc_acquire(r, key, member)
    try:
        yield
    finally:
        try:
            await r.zrem(key, member)
        except Exception:
            pass
