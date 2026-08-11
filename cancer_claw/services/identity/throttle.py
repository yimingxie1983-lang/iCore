

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

MAX_FAILURES = 5

WINDOW_SECONDS = 15 * 60

LOCK_SECONDS = 15 * 60

@dataclass
class _Bucket:


    failures: list[float] = field(default_factory=list)
    locked_until: float = 0.0

class LoginThrottle:


    def __init__(
        self,
        *,
        max_failures: int = MAX_FAILURES,
        window_seconds: int = WINDOW_SECONDS,
        lock_seconds: int = LOCK_SECONDS,
    ) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._lock_for = lock_seconds
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    def _prune_locked(self, now: float) -> None:

        stale = [
            k
            for k, b in self._buckets.items()
            if b.locked_until <= now
            and not [t for t in b.failures if now - t < self._window]
        ]
        for k in stale:
            self._buckets.pop(k, None)

    async def check(self, identity: str) -> float:

        now = time.time()
        async with self._lock:
            self._prune_locked(now)
            bucket = self._buckets.get(identity)
            if bucket and bucket.locked_until > now:
                return bucket.locked_until - now
            return 0.0

    async def record_failure(self, identity: str) -> float:

        now = time.time()
        async with self._lock:
            bucket = self._buckets.setdefault(identity, _Bucket())

            bucket.failures = [t for t in bucket.failures if now - t < self._window]
            bucket.failures.append(now)
            if len(bucket.failures) >= self._max:
                bucket.locked_until = now + self._lock_for
                bucket.failures.clear()
                return self._lock_for
            return 0.0

    async def record_success(self, identity: str) -> None:

        async with self._lock:
            self._buckets.pop(identity, None)

login_throttle = LoginThrottle()
