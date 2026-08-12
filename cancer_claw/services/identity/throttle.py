from __future__ import annotations

import time
from datetime import datetime, timezone

from cancer_claw.db import get_db, get_read_db

USER_MAX_FAILURES = 5
IP_MAX_FAILURES = 20
WINDOW_SECONDS = 15 * 60
LOCK_SECONDS = 15 * 60
SOFT_CAPTCHA_THRESHOLD = 3
REGISTER_MAX_PER_IP = 5
REGISTER_WINDOW_SECONDS = 3600


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ago_iso(seconds: float) -> str:
    return datetime.fromtimestamp(time.time() - seconds, timezone.utc).isoformat()


async def _prune(identity: str, window_seconds: int) -> None:

    db = await get_db()
    await db.execute(
        "DELETE FROM login_attempts WHERE identity = ? AND locked_until IS NULL "
        "AND attempted_at < ?",
        (identity, _ago_iso(window_seconds)),
    )
    await db.commit()


async def check_lock(identity: str) -> float:

    db = await get_read_db()
    cur = await db.execute(
        "SELECT MAX(locked_until) FROM login_attempts "
        "WHERE identity = ? AND locked_until > ?",
        (identity, _now_iso()),
    )
    row = await cur.fetchone()
    if not row or not row[0]:
        return 0.0
    locked = datetime.fromisoformat(str(row[0])).timestamp()
    return max(0.0, locked - time.time())


async def failure_count(identity: str, *, window_seconds: int = WINDOW_SECONDS) -> int:

    db = await get_read_db()
    cur = await db.execute(
        "SELECT COUNT(*) FROM login_attempts "
        "WHERE identity = ? AND kind = 'fail' AND attempted_at >= ?",
        (identity, _ago_iso(window_seconds)),
    )
    row = await cur.fetchone()
    return int(row[0]) if row else 0


async def record_failure(
    identity: str,
    *,
    max_failures: int = USER_MAX_FAILURES,
    window_seconds: int = WINDOW_SECONDS,
    lock_seconds: int = LOCK_SECONDS,
) -> float:

    db = await get_db()
    await _prune(identity, window_seconds)
    now = datetime.now(timezone.utc)
    await db.execute(
        "INSERT INTO login_attempts (identity, kind, attempted_at) "
        "VALUES (?, 'fail', ?)",
        (identity, now.isoformat()),
    )
    cur = await db.execute(
        "SELECT COUNT(*) FROM login_attempts "
        "WHERE identity = ? AND kind = 'fail' AND attempted_at >= ?",
        (identity, _ago_iso(window_seconds)),
    )
    count = int((await cur.fetchone())[0])
    if count >= max_failures:
        locked_until = datetime.fromtimestamp(
            now.timestamp() + lock_seconds, timezone.utc
        ).isoformat()
        await db.execute(
            "UPDATE login_attempts SET locked_until = ? "
            "WHERE identity = ? AND locked_until IS NULL",
            (locked_until, identity),
        )
        await db.commit()
        return float(lock_seconds)
    await db.commit()
    return 0.0


async def record_success(identity: str) -> None:

    db = await get_db()
    await db.execute("DELETE FROM login_attempts WHERE identity = ?", (identity,))
    await db.commit()


async def record_attempt(identity: str, kind: str) -> None:

    db = await get_db()
    await db.execute(
        "INSERT INTO login_attempts (identity, kind, attempted_at) VALUES (?, ?, ?)",
        (identity, kind, _now_iso()),
    )
    await db.commit()


async def count_attempts(
    identity: str, kind: str, *, window_seconds: int
) -> int:

    db = await get_read_db()
    cur = await db.execute(
        "SELECT COUNT(*) FROM login_attempts "
        "WHERE identity = ? AND kind = ? AND attempted_at >= ?",
        (identity, kind, _ago_iso(window_seconds)),
    )
    row = await cur.fetchone()
    return int(row[0]) if row else 0
