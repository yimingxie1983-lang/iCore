import pytest_asyncio
from httpx import ASGITransport, AsyncClient


def pytest_configure(config):
    import os
    from pathlib import Path

    base = Path(".pytest-tmp") / f"run-{os.getpid()}"
    base.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = str(base)


@pytest_asyncio.fixture
async def app(tmp_path):
    from cancer_claw.config import settings
    from cancer_claw.db import close_db, init_db

    old = {
        "db": settings.database.path,
        "secret": settings.auth.secret,
        "reg": settings.auth.allow_registration,
        "mail_host": settings.mail.host,
        "mail_from": settings.mail.from_addr,
        "mail_base": settings.mail.public_base_url,
        "projects": settings.paths.projects_dir,
        "invite": settings.auth.registration_invite_code,
        "captcha_threshold": settings.auth.captcha_threshold,
        "captcha_ttl": settings.auth.captcha_ttl_seconds,
    }
    settings.database.path = str(tmp_path / "test.db")
    settings.auth.secret = "test-secret-0123456789abcdef0123456789abcdef"
    settings.auth.allow_registration = True
    settings.mail.host = ""
    settings.mail.from_addr = ""
    settings.mail.public_base_url = ""
    settings.paths.projects_dir = str(tmp_path / "workspaces")
    settings.auth.registration_invite_code = ""
    settings.auth.captcha_threshold = 3
    settings.auth.captcha_ttl_seconds = 120
    await init_db()

    from cancer_claw.app import app as fastapi_app

    try:
        yield fastapi_app
    finally:
        await close_db()
        settings.database.path = old["db"]
        settings.auth.secret = old["secret"]
        settings.auth.allow_registration = old["reg"]
        settings.mail.host = old["mail_host"]
        settings.mail.from_addr = old["mail_from"]
        settings.mail.public_base_url = old["mail_base"]
        settings.paths.projects_dir = old["projects"]
        settings.auth.registration_invite_code = old["invite"]
        settings.auth.captcha_threshold = old["captcha_threshold"]
        settings.auth.captcha_ttl_seconds = old["captcha_ttl"]


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
