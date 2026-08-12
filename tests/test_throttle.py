import asyncio

from cancer_claw.config import settings
from cancer_claw.db import close_db, init_db
from cancer_claw.services.identity import throttle


async def _isolated_db(tmp_path):
    old_path, old_secret = settings.database.path, settings.auth.secret
    settings.database.path = str(tmp_path / "throttle.db")
    settings.auth.secret = "throttle-test-secret-0123456789"
    await init_db()
    try:
        yield
    finally:
        await close_db()
        settings.database.path = old_path
        settings.auth.secret = old_secret


async def test_lock_after_max_failures(tmp_path):
    async for _ in _isolated_db(tmp_path):
        ident = "u:alice"
        for _ in range(4):
            assert await throttle.record_failure(ident, max_failures=5) == 0
        locked = await throttle.record_failure(ident, max_failures=5)
        assert locked > 0
        assert await throttle.check_lock(ident) > 0


async def test_success_clears_failures(tmp_path):
    async for _ in _isolated_db(tmp_path):
        ident = "u:bob"
        await throttle.record_failure(ident, max_failures=5)
        await throttle.record_failure(ident, max_failures=5)
        await throttle.record_success(ident)
        assert await throttle.failure_count(ident) == 0
        assert await throttle.check_lock(ident) == 0


async def test_failures_expire_after_window(tmp_path):
    async for _ in _isolated_db(tmp_path):
        ident = "u:carol"
        await throttle.record_failure(ident, max_failures=5, window_seconds=1)
        await asyncio.sleep(1.1)
        assert await throttle.failure_count(ident, window_seconds=1) == 0


async def test_register_attempt_counting(tmp_path):
    async for _ in _isolated_db(tmp_path):
        ident = "ip:127.0.0.1"
        for _ in range(3):
            await throttle.record_attempt(ident, kind="register")
        assert (
            await throttle.count_attempts(ident, "register", window_seconds=3600) == 3
        )
