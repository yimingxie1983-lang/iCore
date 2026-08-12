from datetime import datetime, timedelta, timezone

from cancer_claw.config import settings
from cancer_claw.db import close_db, init_db
from cancer_claw.services.identity import repo
from cancer_claw.services.identity.security import hash_token, verify_password


async def _isolated_db(tmp_path):
    old_path, old_secret = settings.database.path, settings.auth.secret
    settings.database.path = str(tmp_path / "repo.db")
    settings.auth.secret = "repo-test-secret-0123456789abcdef"
    await init_db()
    try:
        yield
    finally:
        await close_db()
        settings.database.path = old_path
        settings.auth.secret = old_secret


async def test_token_version_bump_and_password_update(tmp_path):
    async for _ in _isolated_db(tmp_path):
        user = await repo.create_user(username="alice", password="OldPass123!")
        v0 = user["token_version"]
        v1 = await repo.bump_token_version(user["id"])
        assert v1 == v0 + 1
        await repo.update_password(user["id"], "NewPass456!")
        fresh = await repo.get_user_with_hash("alice")
        assert fresh["token_version"] == v1 + 1
        assert verify_password("NewPass456!", fresh["password_hash"])


async def test_auth_token_consume_once(tmp_path):
    async for _ in _isolated_db(tmp_path):
        user = await repo.create_user(username="bob", password="OldPass123!")
        raw = "reset-token-abc"
        await repo.create_auth_token(
            user["id"],
            "password_reset",
            hash_token(raw),
            datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        assert (
            await repo.consume_auth_token(hash_token(raw), "password_reset")
            == user["id"]
        )
        assert (
            await repo.consume_auth_token(hash_token(raw), "password_reset") is None
        )


async def test_email_verified_flag(tmp_path):
    async for _ in _isolated_db(tmp_path):
        user = await repo.create_user(
            username="carol", password="OldPass123!", email="carol@example.com"
        )
        assert user["email_verified"] is False
        await repo.set_email_verified(user["id"])
        fresh = await repo.get_user_by_email("carol@example.com")
        assert fresh and fresh["email_verified"] is True


async def test_auth_events_recorded_and_listed(tmp_path):
    async for _ in _isolated_db(tmp_path):
        user = await repo.create_user(username="dave", password="OldPass123!")
        await repo.record_auth_event(
            user["id"], "dave", "login_success", "127.0.0.1"
        )
        await repo.record_auth_event(
            user["id"], "dave", "login_failed", "127.0.0.1", "bad pw"
        )
        total, items = await repo.list_auth_events(limit=10, offset=0)
        assert total == 2
        assert items[0]["event_type"] == "login_failed"
        assert {e["event_type"] for e in items} == {"login_success", "login_failed"}
