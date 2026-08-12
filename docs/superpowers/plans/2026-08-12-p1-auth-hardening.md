# P1 Auth Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复登录/鉴权 P1 问题：自助改密与找回密码、邮箱验证、密码策略与哈希迭代升级、JWT 库替换、登录审计、签名文件 URL、前端 token 校验与禁用账号登出。

**Architecture:** 后端在 `services/identity` 内扩展（security/mail/repo/deps），auth 路由新增改密、找回、验证、审计接口；`users` 表新增 `token_version`/`email_verified` 列，新增 `auth_tokens`、`auth_events` 表；文件 raw 接口支持短时 HMAC 签名 URL；前端增加账户设置页、登录页找回/重置/验证流程、启动时 `/auth/me` 校验和 403 禁用登出。

**Tech Stack:** FastAPI + Pydantic v2 + aiosqlite/asyncpg + PyJWT 2.13 + pytest + React 18 + zustand + axios

---

## Task 0: 分支与依赖

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 创建功能分支**

```bash
git switch -c codex/p1-auth-hardening
```

- [ ] **Step 2: 声明依赖**

`pyproject.toml` 的 `dependencies` 追加一行：

```toml
    "PyJWT>=2.8",
```

- [ ] **Step 3: 安装并验证基线**

```bash
.venv/Scripts/python.exe -m pip install pyjwt pytest pytest-asyncio
.venv/Scripts/python.exe -m pytest --collect-only -q
```

Expected: 无测试可收集（`tests/` 尚不存在），不报错。

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add PyJWT dependency for auth hardening"
```

---

## Task 1: 安全原语（哈希迭代 + 密码策略 + PyJWT）

**Files:**
- Modify: `cancer_claw/services/identity/security.py`
- Create: `tests/test_security.py`
- Modify: `cancer_claw/config.py`（`AuthConfig.min_password_length`）

- [ ] **Step 1: 写失败测试** `tests/test_security.py`

```python
import base64
import time

import pytest

from cancer_claw.services.identity import security


def test_hash_verify_roundtrip():
    h = security.hash_password("correct horse battery staple")
    assert h.startswith("pbkdf2_sha256$")
    assert security.verify_password("correct horse battery staple", h)
    assert not security.verify_password("wrong", h)


def test_legacy_iteration_hash_still_verifies():
    salt = base64.b64encode(b"0123456789abcdef").decode()
    dk = base64.b64encode(
        __import__("hashlib").pbkdf2_hmac(
            "sha256", b"oldpass", b"0123456789abcdef", 10_000
        )
    ).decode()
    stored = f"pbkdf2_sha256$10000${salt}${dk}"
    assert security.verify_password("oldpass", stored)
    assert security.needs_rehash(stored)


def test_needs_rehash_false_for_current_iterations():
    h = security.hash_password("newpass123")
    assert not security.needs_rehash(h)


def test_password_strength_rejects_weak():
    with pytest.raises(ValueError, match="8"):
        security.validate_password_strength("abc123", min_length=8)
    with pytest.raises(ValueError, match="常见"):
        security.validate_password_strength("password123", min_length=8)
    with pytest.raises(ValueError, match="相同字符"):
        security.validate_password_strength("aaaaaaaa", min_length=8)
    with pytest.raises(ValueError, match="用户名"):
        security.validate_password_strength("alice123", username="Alice", min_length=8)
    security.validate_password_strength("Kx9#mQ2!z", username="alice", min_length=8)


def test_token_roundtrip_contains_ver_and_jti():
    tok = security.create_access_token(
        user_id="u1",
        username="alice",
        role="user",
        secret="s3cret",
        ttl_hours=1,
        token_version=3,
    )
    payload = security.decode_access_token(tok, secret="s3cret")
    assert payload["sub"] == "u1"
    assert payload["ver"] == 3
    assert payload["iss"] == "icore"
    assert payload["jti"]


def test_token_rejects_tampered_signature():
    tok = security.create_access_token(
        user_id="u1", username="alice", role="user",
        secret="s3cret", ttl_hours=1,
    )
    parts = tok.split(".")
    payload = parts[1] + "x" if not parts[1].endswith("=") else parts[1][:-1]
    with pytest.raises(security.TokenError):
        security.decode_access_token(f"{parts[0]}.{payload}.{parts[2]}", secret="s3cret")


def test_expired_token_rejected():
    tok = security.create_access_token(
        user_id="u1", username="alice", role="user",
        secret="s3cret", ttl_hours=1,
        issued_at=time.time() - 7200,
    )
    with pytest.raises(security.TokenError, match="过期"):
        security.decode_access_token(tok, secret="s3cret")


def test_wrong_issuer_rejected():
    import jwt as pyjwt

    bad = pyjwt.encode(
        {"iss": "evil", "sub": "u1", "ver": 0, "iat": int(time.time()),
         "nbf": int(time.time()), "exp": int(time.time()) + 600},
        "s3cret", algorithm="HS256",
    )
    with pytest.raises(security.TokenError):
        security.decode_access_token(bad, secret="s3cret")


def test_verify_token_helpers():
    raw = security.generate_token()
    assert len(raw) >= 32
    h = security.hash_token(raw)
    assert h == security.hash_token(raw)
    assert h != raw
```

- [ ] **Step 2: 运行确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_security.py -q
```

Expected: 大量 FAIL（模块缺少 `validate_password_strength`/`needs_rehash`/`generate_token`/`hash_token`，PyJWT 行为不符）。

- [ ] **Step 3: 重写 `security.py`**

关键改动：

```python
import uuid
import jwt as pyjwt

_PBKDF2_ITERATIONS = 600_000

COMMON_PASSWORDS = frozenset({
    "password", "password1", "password123", "12345678", "123456789",
    "1234567890", "qwertyuiop", "qwerty123", "admin123", "admin888",
    "abc12345", "iloveyou", "11111111", "00000000", "letmein",
    "welcome1", "changeme", "monkey123", "dragon123", "66666666",
})

def validate_password_strength(password: str, *, username: str = "", min_length: int = 8) -> None:
    if len(password) < min_length:
        raise ValueError(f"密码至少需要 {min_length} 位")
    lower = password.lower()
    if username and lower == username.strip().lower():
        raise ValueError("密码不能与用户名相同")
    if lower in COMMON_PASSWORDS:
        raise ValueError("密码过于常见，请更换")
    if len(set(password)) == 1:
        raise ValueError("密码不能全部是相同字符")
    if lower.startswith("12345678"):
        raise ValueError("密码过于简单，请更换")

def needs_rehash(stored: str) -> bool:
    try:
        algo, iter_s, _salt, _dk = stored.split("$", 3)
        return algo == _PBKDF2_ALGO and int(iter_s) < _PBKDF2_ITERATIONS
    except (ValueError, TypeError):
        return False

def generate_token() -> str:
    return secrets.token_urlsafe(32)

def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def create_access_token(*, user_id, username, role, secret, ttl_hours,
                        issued_at=None, token_version: int = 0) -> str:
    if not secret:
        raise TokenError("缺少签名密钥（settings.auth.secret）")
    now = int(issued_at if issued_at is not None else time.time())
    payload = {
        "iss": "icore",
        "sub": user_id,
        "username": username,
        "role": role,
        "ver": int(token_version or 0),
        "iat": now,
        "nbf": now,
        "exp": now + int(ttl_hours) * 3600,
        "jti": uuid.uuid4().hex,
    }
    return pyjwt.encode(payload, secret, algorithm="HS256")

def decode_access_token(token: str, *, secret: str) -> dict[str, Any]:
    if not token:
        raise TokenError("空令牌")
    try:
        return pyjwt.decode(
            token, secret, algorithms=["HS256"], issuer="icore",
            options={"require": ["exp", "sub"]},
        )
    except pyjwt.ExpiredSignatureError as e:
        raise TokenError("令牌已过期") from e
    except pyjwt.InvalidTokenError as e:
        raise TokenError(f"令牌无效: {e}") from e
```

保留 `hash_password`/`verify_password`/`generate_secret`/`TokenError` 原行为（仅迭代数改为 600_000）。

- [ ] **Step 4: 运行确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_security.py -q
```

Expected: 全 PASS。

- [ ] **Step 5: `config.py` 增加密码长度配置**

`AuthConfig` 增加 `min_password_length: int = 8`；`_apply_env_overrides` 增加：

```python
if os.environ.get("CANCER_CLAW_AUTH_MIN_PASSWORD_LENGTH"):
    try:
        settings.auth.min_password_length = int(os.environ["CANCER_CLAW_AUTH_MIN_PASSWORD_LENGTH"])
    except ValueError:
        pass
```

- [ ] **Step 6: Commit**

```bash
git add cancer_claw/services/identity/security.py cancer_claw/config.py tests/test_security.py
git commit -m "feat(auth): PyJWT tokens, 600k PBKDF2, password strength policy"
```

---

## Task 2: 数据库迁移与 identity repo 扩展

**Files:**
- Modify: `cancer_claw/db.py`
- Modify: `cancer_claw/services/identity/repo.py`
- Create: `tests/test_repo.py`

- [ ] **Step 1: 写失败测试** `tests/test_repo.py`

```python
import asyncio

import pytest


async def test_token_version_bump_and_password_update(tmp_path):
    from cancer_claw.config import settings
    from cancer_claw.db import init_db, close_db
    from cancer_claw.services.identity import repo

    old_path, old_secret = settings.database.path, settings.auth.secret
    settings.database.path = str(tmp_path / "repo.db")
    settings.auth.secret = "repo-test-secret"
    await init_db()
    try:
        user = await repo.create_user(username="alice", password="OldPass123!")
        v0 = user["token_version"]
        v1 = await repo.bump_token_version(user["id"])
        assert v1 == v0 + 1
        await repo.update_password(user["id"], "NewPass456!")
        fresh = await repo.get_user_with_hash("alice")
        assert fresh["token_version"] == v1 + 1
        from cancer_claw.services.identity.security import verify_password
        assert verify_password("NewPass456!", fresh["password_hash"])
    finally:
        await close_db()
        settings.database.path = old_path
        settings.auth.secret = old_secret


async def test_auth_token_consume_once(tmp_path):
    from cancer_claw.config import settings
    from cancer_claw.db import init_db, close_db
    from cancer_claw.services.identity import repo
    from cancer_claw.services.identity.security import hash_token
    from datetime import datetime, timedelta, timezone

    old_path, old_secret = settings.database.path, settings.auth.secret
    settings.database.path = str(tmp_path / "repo.db")
    settings.auth.secret = "repo-test-secret"
    await init_db()
    try:
        user = await repo.create_user(username="bob", password="OldPass123!")
        raw = "reset-token-abc"
        await repo.create_auth_token(
            user["id"], "password_reset", hash_token(raw),
            datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        assert await repo.consume_auth_token(hash_token(raw), "password_reset") == user["id"]
        assert await repo.consume_auth_token(hash_token(raw), "password_reset") is None
    finally:
        await close_db()
        settings.database.path = old_path
        settings.auth.secret = old_secret


async def test_email_verified_flag(tmp_path):
    from cancer_claw.config import settings
    from cancer_claw.db import init_db, close_db
    from cancer_claw.services.identity import repo

    old_path, old_secret = settings.database.path, settings.auth.secret
    settings.database.path = str(tmp_path / "repo.db")
    settings.auth.secret = "repo-test-secret"
    await init_db()
    try:
        user = await repo.create_user(
            username="carol", password="OldPass123!", email="carol@example.com"
        )
        assert user["email_verified"] is False
        await repo.set_email_verified(user["id"])
        fresh = await repo.get_user_by_email("carol@example.com")
        assert fresh and fresh["email_verified"] is True
    finally:
        await close_db()
        settings.database.path = old_path
        settings.auth.secret = old_secret


async def test_auth_events_recorded_and_listed(tmp_path):
    from cancer_claw.config import settings
    from cancer_claw.db import init_db, close_db
    from cancer_claw.services.identity import repo

    old_path, old_secret = settings.database.path, settings.auth.secret
    settings.database.path = str(tmp_path / "repo.db")
    settings.auth.secret = "repo-test-secret"
    await init_db()
    try:
        user = await repo.create_user(username="dave", password="OldPass123!")
        await repo.record_auth_event(user["id"], "dave", "login_success", "127.0.0.1")
        await repo.record_auth_event(user["id"], "dave", "login_failed", "127.0.0.1", "bad pw")
        total, items = await repo.list_auth_events(limit=10, offset=0)
        assert total == 2
        assert items[0]["event_type"] == "login_success"
    finally:
        await close_db()
        settings.database.path = old_path
        settings.auth.secret = old_secret
```

- [ ] **Step 2: 运行确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_repo.py -q
```

Expected: FAIL（`token_version` 列不存在、repo 缺函数、表缺失）。

- [ ] **Step 3: `db.py` 迁移**

`_TABLE_SCHEMAS` 追加：

```python
    """
    CREATE TABLE IF NOT EXISTS auth_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        expires_at TIMESTAMP NOT NULL,
        used_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        username TEXT DEFAULT '',
        event_type TEXT NOT NULL,
        ip TEXT DEFAULT '',
        detail TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
```

`_INDEX_SCHEMAS` 追加：

```python
    "CREATE INDEX IF NOT EXISTS idx_auth_tokens_hash ON auth_tokens(token_hash)",
    "CREATE INDEX IF NOT EXISTS idx_auth_tokens_user ON auth_tokens(user_id, kind, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_auth_events_created ON auth_events(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_auth_events_user ON auth_events(user_id, created_at DESC)",
```

`_create_tables` 内、`_migrate_add_column_if_missing` 处追加：

```python
    await _migrate_add_column_if_missing(db, "users", "token_version", "INTEGER NOT NULL DEFAULT 0")
    await _migrate_add_column_if_missing(db, "users", "email_verified", "INTEGER NOT NULL DEFAULT 0")
```

`_PG_ADD_COLUMNS` 追加：

```python
    ("users", "token_version", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "email_verified", "INTEGER NOT NULL DEFAULT 0"),
```

- [ ] **Step 4: `repo.py` 扩展**

`_USER_PUBLIC_COLS` 变为：

```python
_USER_PUBLIC_COLS = (
    "id, username, email, display_name, role, status, "
    "COALESCE(credits_balance, 0), created_at, updated_at, "
    "COALESCE(email_verified, 0), COALESCE(token_version, 0)"
)
```

`_row_to_user` 增加：

```python
        "email_verified": bool(row[9]),
        "token_version": int(row[10] or 0),
```

`get_user_with_hash` 的 SELECT 改为：

```python
    cur = await db.execute(
        f"SELECT {_USER_PUBLIC_COLS}, password_hash FROM users WHERE username = ?",
        (username,),
    )
    ...
    user["password_hash"] = row[11]
```

新增函数：

```python
async def get_user_by_email(email: str) -> dict[str, Any] | None:
    if not email:
        return None
    db = await get_read_db()
    cur = await db.execute(
        f"SELECT {_USER_PUBLIC_COLS} FROM users WHERE email = ? COLLATE NOCASE",
        (email.strip(),),
    )
    row = await cur.fetchone()
    return _row_to_user(row) if row else None

async def get_user_by_username_or_email(username: str, email: str = "") -> dict[str, Any] | None:
    if email.strip():
        return await get_user_by_email(email) or await get_user_by_username(username)
    return await get_user_by_username(username)

async def bump_token_version(user_id: str) -> int:
    db = await get_db()
    await db.execute(
        "UPDATE users SET token_version = COALESCE(token_version, 0) + 1, updated_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), user_id),
    )
    await db.commit()
    cur = await db.execute("SELECT COALESCE(token_version, 0) FROM users WHERE id = ?", (user_id,))
    row = await cur.fetchone()
    return int(row[0]) if row else 0

async def update_password(user_id: str, password: str) -> dict[str, Any] | None:
    db = await get_db()
    await db.execute(
        "UPDATE users SET password_hash = ?, token_version = COALESCE(token_version, 0) + 1, updated_at = ? WHERE id = ?",
        (hash_password(password), datetime.now(timezone.utc).isoformat(), user_id),
    )
    await db.commit()
    return await get_user_by_id(user_id)

async def set_email_verified(user_id: str) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE users SET email_verified = 1, updated_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), user_id),
    )
    await db.commit()

async def create_auth_token(user_id: str, kind: str, token_hash: str, expires_at: datetime) -> None:
    db = await get_db()
    await db.execute(
        """INSERT INTO auth_tokens (user_id, kind, token_hash, expires_at, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, kind, token_hash, expires_at.isoformat(),
         datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()

async def consume_auth_token(token_hash: str, kind: str) -> str | None:
    db = await get_db()
    cur = await db.execute(
        """SELECT user_id FROM auth_tokens
           WHERE token_hash = ? AND kind = ? AND used_at IS NULL
             AND expires_at > ?""",
        (token_hash, kind, datetime.now(timezone.utc).isoformat()),
    )
    row = await cur.fetchone()
    if not row:
        return None
    await db.execute(
        "UPDATE auth_tokens SET used_at = ? WHERE token_hash = ?",
        (datetime.now(timezone.utc).isoformat(), token_hash),
    )
    await db.commit()
    return str(row[0])

async def record_auth_event(user_id: str | None, username: str, event_type: str,
                            ip: str = "", detail: str = "") -> None:
    db = await get_db()
    await db.execute(
        """INSERT INTO auth_events (user_id, username, event_type, ip, detail, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, username or "", event_type, ip or "", detail or "",
         datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()

async def list_auth_events(limit: int = 50, offset: int = 0) -> tuple[int, list[dict[str, Any]]]:
    db = await get_db()
    cur = await db.execute("SELECT COUNT(*) FROM auth_events")
    total = int((await cur.fetchone())[0])
    cur = await db.execute(
        """SELECT id, user_id, username, event_type, ip, detail, created_at
           FROM auth_events ORDER BY id DESC LIMIT ? OFFSET ?""",
        (limit, offset),
    )
    rows = await cur.fetchall()
    items = [
        {"id": r[0], "user_id": r[1], "username": r[2] or "", "event_type": r[3],
         "ip": r[4] or "", "detail": r[5] or "", "created_at": r[6]}
        for r in rows
    ]
    return total, items
```

`update_user` 的 password 分支改为：

```python
    if password:
        sets.append("password_hash = ?")
        params.append(hash_password(password))
        sets.append("token_version = COALESCE(token_version, 0) + 1")
```

- [ ] **Step 5: 运行确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_repo.py -q
```

- [ ] **Step 6: Commit**

```bash
git add cancer_claw/db.py cancer_claw/services/identity/repo.py tests/test_repo.py
git commit -m "feat(auth): token_version/email_verified columns, auth_tokens & auth_events tables"
```

---

## Task 3: 邮件服务

**Files:**
- Create: `cancer_claw/services/identity/mail.py`
- Modify: `cancer_claw/config.py`（`MailConfig`）
- Create: `tests/test_mail.py`

- [ ] **Step 1: 写失败测试** `tests/test_mail.py`

```python
import pytest

from cancer_claw.services.identity import mail


def test_mail_not_configured_by_default(monkeypatch):
    monkeypatch.setattr(mail.settings.mail, "host", "")
    monkeypatch.setattr(mail.settings.mail, "from_addr", "")
    assert not mail.is_mail_configured()


def test_mail_configured_when_host_and_from(monkeypatch):
    monkeypatch.setattr(mail.settings.mail, "host", "smtp.example.com")
    monkeypatch.setattr(mail.settings.mail, "from_addr", "no-reply@example.com")
    assert mail.is_mail_configured()


def test_send_email_requires_config(monkeypatch):
    monkeypatch.setattr(mail.settings.mail, "host", "")
    with pytest.raises(mail.MailError):
        mail._send("a@b.c", "s", "t")
```

- [ ] **Step 2: 运行确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_mail.py -q
```

- [ ] **Step 3: 实现 `mail.py`**

```python
from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from cancer_claw.config import settings


class MailError(Exception):
    pass


def is_mail_configured() -> bool:
    return bool(settings.mail.host and settings.mail.from_addr)


async def send_email_async(to: str, subject: str, text: str) -> None:
    await asyncio.to_thread(_send, to, subject, text)


def _send(to: str, subject: str, text: str) -> None:
    if not is_mail_configured():
        raise MailError("邮件服务未配置")
    msg = EmailMessage()
    msg["From"] = settings.mail.from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    with smtplib.SMTP(settings.mail.host, settings.mail.port, timeout=settings.mail.timeout) as smtp:
        if settings.mail.starttls:
            smtp.starttls()
        if settings.mail.username:
            smtp.login(settings.mail.username, settings.mail.password)
        smtp.send_message(msg)
```

`config.py` 增加：

```python
class MailConfig(BaseModel):
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    from_addr: str = ""
    starttls: bool = True
    timeout: int = 10
    public_base_url: str = ""
```

`Settings` 增加 `mail: MailConfig = MailConfig()`；`_apply_env_overrides` 增加 `CANCER_CLAW_SMTP_HOST/PORT/USERNAME/PASSWORD/FROM/STARTTLS`、`CANCER_CLAW_PUBLIC_BASE_URL` 覆盖。

- [ ] **Step 4: 运行确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_mail.py -q
```

- [ ] **Step 5: Commit**

```bash
git add cancer_claw/services/identity/mail.py cancer_claw/config.py tests/test_mail.py
git commit -m "feat(auth): smtp mail service with config"
```

---

## Task 4: 鉴权依赖 + auth 路由

**Files:**
- Modify: `cancer_claw/services/identity/deps.py`
- Modify: `cancer_claw/interfaces/routes/auth.py`
- Create: `tests/test_auth_api.py`

- [ ] **Step 1: 写失败测试** `tests/test_auth_api.py` + `tests/conftest.py`

`tests/conftest.py`：

```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def app(tmp_path):
    from cancer_claw.config import settings
    from cancer_claw.db import init_db, close_db

    old = {
        "db": settings.database.path,
        "secret": settings.auth.secret,
        "reg": settings.auth.allow_registration,
        "mail_host": settings.mail.host,
        "mail_from": settings.mail.from_addr,
        "projects": settings.paths.projects_dir,
    }
    settings.database.path = str(tmp_path / "test.db")
    settings.auth.secret = "test-secret-abcdef123456"
    settings.auth.allow_registration = True
    settings.mail.host = ""
    settings.mail.from_addr = ""
    settings.paths.projects_dir = str(tmp_path / "workspaces")
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
        settings.paths.projects_dir = old["projects"]


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

`tests/test_auth_api.py`：

```python
import re


async def _register(client, username="alice", password="StrongPass1!", email=""):
    resp = await client.post("/api/auth/register", json={
        "username": username, "password": password, "email": email,
        "display_name": username,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_register_login_me(client):
    data = await _register(client)
    assert data["access_token"]
    assert data["user"]["username"] == "alice"
    assert data["user"]["email_verified"] is False

    resp = await client.post("/api/auth/login", json={
        "username": "alice", "password": "StrongPass1!",
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"


async def test_register_rejects_weak_password(client):
    resp = await client.post("/api/auth/register", json={
        "username": "weak", "password": "12345678",
    })
    assert resp.status_code == 400


async def test_change_password_invalidates_old_token(client):
    data = await _register(client)
    old_token = data["access_token"]
    resp = await client.post("/api/auth/change-password", json={
        "current_password": "StrongPass1!", "new_password": "NewStrong2!",
    }, headers={"Authorization": f"Bearer {old_token}"})
    assert resp.status_code == 204

    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert resp.status_code == 401

    resp = await client.post("/api/auth/login", json={
        "username": "alice", "password": "NewStrong2!",
    })
    assert resp.status_code == 200


async def test_change_password_wrong_current(client):
    data = await _register(client)
    resp = await client.post("/api/auth/change-password", json={
        "current_password": "WrongPass1!", "new_password": "NewStrong2!",
    }, headers={"Authorization": f"Bearer {data['access_token']}"})
    assert resp.status_code == 401


async def test_forgot_password_requires_mail_config(client):
    await _register(client, username="carol", email="carol@example.com")
    resp = await client.post("/api/auth/forgot-password", json={"email": "carol@example.com"})
    assert resp.status_code == 503


async def test_forgot_and_reset_password_flow(client, monkeypatch):
    sent = {}

    async def fake_send(to, subject, text):
        sent["to"] = to
        sent["text"] = text

    from cancer_claw.config import settings
    settings.mail.host = "smtp.example.com"
    settings.mail.from_addr = "no-reply@example.com"
    settings.mail.public_base_url = "https://icore.example.com"
    monkeypatch.setattr("cancer_claw.services.identity.mail.send_email_async", fake_send)

    data = await _register(client, username="dave", email="dave@example.com")
    old_token = data["access_token"]

    resp = await client.post("/api/auth/forgot-password", json={"email": "dave@example.com"})
    assert resp.status_code == 202
    m = re.search(r"reset_token=([A-Za-z0-9_-]+)", sent["text"])
    assert m, sent["text"]

    resp = await client.post("/api/auth/reset-password", json={
        "token": m.group(1), "new_password": "ResetPass1!",
    })
    assert resp.status_code == 200

    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert resp.status_code == 401

    resp = await client.post("/api/auth/reset-password", json={
        "token": m.group(1), "new_password": "ResetPass2!",
    })
    assert resp.status_code == 400  # 一次性


async def test_reset_password_rejects_weak(client, monkeypatch):
    sent = {}

    async def fake_send(to, subject, text):
        sent["text"] = text

    from cancer_claw.config import settings
    settings.mail.host = "smtp.example.com"
    settings.mail.from_addr = "no-reply@example.com"
    settings.mail.public_base_url = "https://icore.example.com"
    monkeypatch.setattr("cancer_claw.services.identity.mail.send_email_async", fake_send)

    await _register(client, username="erin", email="erin@example.com")
    await client.post("/api/auth/forgot-password", json={"email": "erin@example.com"})
    token = re.search(r"reset_token=([A-Za-z0-9_-]+)", sent["text"]).group(1)

    resp = await client.post("/api/auth/reset-password", json={
        "token": token, "new_password": "12345678",
    })
    assert resp.status_code == 400


async def test_verify_email_flow(client, monkeypatch):
    sent = {}

    async def fake_send(to, subject, text):
        sent["text"] = text

    from cancer_claw.config import settings
    settings.mail.host = "smtp.example.com"
    settings.mail.from_addr = "no-reply@example.com"
    settings.mail.public_base_url = "https://icore.example.com"
    monkeypatch.setattr("cancer_claw.services.identity.mail.send_email_async", fake_send)

    data = await _register(client, username="frank", email="frank@example.com")
    token = re.search(r"verify_token=([A-Za-z0-9_-]+)", sent["text"]).group(1)

    resp = await client.get("/api/auth/verify-email", params={"token": token})
    assert resp.status_code == 200

    resp = await client.get("/api/auth/me", headers={
        "Authorization": f"Bearer {data['access_token']}",
    })
    assert resp.json()["email_verified"] is True


async def test_audit_events_recorded_and_admin_listed(client):
    await _register(client, username="grace")
    resp = await client.post("/api/auth/login", json={
        "username": "grace", "password": "StrongPass1!",
    })
    token = resp.json()["access_token"]
    await client.post("/api/auth/login", json={
        "username": "grace", "password": "WrongPass1!",
    })

    resp = await client.get("/api/admin/auth-events", headers={
        "Authorization": f"Bearer {token}",
    })
    assert resp.status_code == 200
    body = resp.json()
    events = {e["event_type"] for e in body["items"]}
    assert {"register", "login_success", "login_failed"} <= events


async def test_disabled_user_gets_403_and_me_rejects(client):
    data = await _register(client, username="hank")
    admin_data = await _register(client, username="root_admin")
    admin = admin_data["access_token"]
    user_id = data["user"]["id"]

    resp = await client.patch(
        f"/api/users/{user_id}",
        json={"status": "disabled"},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert resp.status_code == 200

    resp = await client.get("/api/auth/me", headers={
        "Authorization": f"Bearer {data['access_token']}",
    })
    assert resp.status_code == 403
```

注意：`root_admin` 是第二个注册用户，role 为 user，无法调用 `PATCH /users`。改用首个注册用户做管理员：将 `test_disabled_user_gets_403_and_me_rejects` 改为先注册 `root_admin`（首个=admin），再注册 `hank`。

- [ ] **Step 2: 运行确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_auth_api.py -q
```

- [ ] **Step 3: `deps.py` 增加 token_version 校验**

`get_current_user` 在 `status != "active"` 检查后追加：

```python
    if int(payload.get("ver", 0) or 0) != int(user.get("token_version", 0) or 0):
        raise HTTPException(status_code=401, detail="登录凭证已失效，请重新登录")
```

新增 request 级别的项目访问解析（供签名文件回退使用）：

```python
async def resolve_access_from_request(
    request: Request, project_id: str, *, need: str
) -> ProjectContext:
    user = await get_current_user(
        authorization=request.headers.get("authorization"),
        access_token=request.query_params.get("access_token"),
    )
    return await _resolve_access(project_id, user, need=need)
```

（`deps.py` 需 `from fastapi import Request`。）

- [ ] **Step 4: `auth.py` 新端点**

新增 import：`Response, Query, JSONResponse`、`datetime/timedelta/timezone`、`validate_password_strength/generate_token/hash_token`、`mail`。

`UserPublic` 增加 `email_verified: bool = False`。

`_issue_token` 改为传 `token_version=user.get("token_version", 0)`。

新增辅助：

```python
async def _audit(user_id, username, event_type, ip, detail="") -> None:
    try:
        await repo.record_auth_event(user_id, username, event_type, ip, detail)
    except Exception as e:
        logger.warning("auth_audit_failed", event=event_type, error=str(e))

def _now() -> datetime:
    return datetime.now(timezone.utc)
```

`register`：创建用户前校验密码强度；创建后：

```python
    if user.get("email") and mail.is_mail_configured():
        token = generate_token()
        await repo.create_auth_token(
            user["id"], "email_verify", hash_token(token),
            _now() + timedelta(hours=settings.auth.email_verify_token_ttl_hours),
        )
        link = f"{settings.mail.public_base_url.rstrip('/')}/login?verify_token={token}"
        try:
            await mail.send_email_async(
                user["email"], "iCore 邮箱验证",
                f"请点击链接完成邮箱验证（24 小时内有效）：\n{link}",
            )
        except Exception as e:
            logger.warning("verify_mail_send_failed", user_id=user["id"], error=str(e))
```

`login`：成功/失败/锁定处调用 `_audit`（login_success/login_failed）。

新端点：

```python
@router.post("/auth/change-password", status_code=204)
async def change_password(
    body: ChangePasswordReq, request: Request, user: dict[str, Any] = Depends(get_current_user)
) -> Response:
    full = await repo.get_user_with_hash(user["username"])
    if not full or not verify_password(body.current_password, full.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="当前密码不正确")
    try:
        validate_password_strength(
            body.new_password, username=user["username"],
            min_length=settings.auth.min_password_length,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await repo.update_password(user["id"], body.new_password)
    await _audit(user["id"], user["username"], "password_changed", _client_ip(request))
    return Response(status_code=204)


@router.post("/auth/forgot-password", status_code=202)
async def forgot_password(body: ForgotPasswordReq, request: Request) -> dict[str, bool]:
    if not mail.is_mail_configured():
        raise HTTPException(status_code=503, detail="系统未配置邮件服务，无法发送重置邮件")
    target = await repo.get_user_by_username_or_email(body.username, body.email)
    if target and target.get("email"):
        token = generate_token()
        await repo.create_auth_token(
            target["id"], "password_reset", hash_token(token),
            _now() + timedelta(minutes=settings.auth.reset_token_ttl_minutes),
        )
        link = f"{settings.mail.public_base_url.rstrip('/')}/login?reset_token={token}"
        try:
            await mail.send_email_async(
                target["email"], "iCore 密码重置",
                f"请点击链接重置密码（{settings.auth.reset_token_ttl_minutes} 分钟内有效）：\n{link}",
            )
            await _audit(target["id"], target["username"], "password_reset_requested", _client_ip(request))
        except Exception as e:
            await _audit(target["id"], target["username"], "password_reset_mail_failed", _client_ip(request), str(e))
    else:
        await _audit(None, body.username or body.email, "password_reset_requested_unknown", _client_ip(request))
    return {"ok": True}


@router.post("/auth/reset-password")
async def reset_password(body: ResetPasswordReq, request: Request) -> dict[str, bool]:
    user_id = await repo.consume_auth_token(hash_token(body.token), "password_reset")
    if not user_id:
        raise HTTPException(status_code=400, detail="重置链接无效或已过期")
    user = await repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=400, detail="用户不存在")
    try:
        validate_password_strength(
            body.new_password, username=user["username"],
            min_length=settings.auth.min_password_length,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await repo.update_password(user_id, body.new_password)
    await _audit(user_id, user["username"], "password_reset", _client_ip(request))
    return {"ok": True}


@router.get("/auth/verify-email")
async def verify_email(token: str = Query(..., min_length=8, max_length=256)) -> dict[str, bool]:
    user_id = await repo.consume_auth_token(hash_token(token), "email_verify")
    if not user_id:
        raise HTTPException(status_code=400, detail="验证链接无效或已过期")
    await repo.set_email_verified(user_id)
    return {"ok": True}


@router.post("/auth/send-verification", status_code=202)
async def send_verification(
    request: Request, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, bool]:
    if not mail.is_mail_configured():
        raise HTTPException(status_code=503, detail="系统未配置邮件服务")
    if not user.get("email"):
        raise HTTPException(status_code=400, detail="账号未绑定邮箱")
    if user.get("email_verified"):
        raise HTTPException(status_code=400, detail="邮箱已认证")
    token = generate_token()
    await repo.create_auth_token(
        user["id"], "email_verify", hash_token(token),
        _now() + timedelta(hours=settings.auth.email_verify_token_ttl_hours),
    )
    link = f"{settings.mail.public_base_url.rstrip('/')}/login?verify_token={token}"
    await mail.send_email_async(
        user["email"], "iCore 邮箱验证",
        f"请点击链接完成邮箱验证（24 小时内有效）：\n{link}",
    )
    await _audit(user["id"], user["username"], "verify_email_sent", _client_ip(request))
    return {"ok": True}


@router.get("/admin/auth-events", response_model=AuthEventListResp)
async def list_auth_events(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _admin: dict[str, Any] = Depends(require_admin),
) -> AuthEventListResp:
    total, items = await repo.list_auth_events(limit=limit, offset=offset)
    return AuthEventListResp(total=total, items=items)
```

新模型：

```python
class ChangePasswordReq(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=1, max_length=128)

class ForgotPasswordReq(BaseModel):
    username: str = Field("", max_length=40)
    email: str = Field("", max_length=120)

class ResetPasswordReq(BaseModel):
    token: str = Field(..., min_length=8, max_length=256)
    new_password: str = Field(..., min_length=1, max_length=128)

class AuthEventItem(BaseModel):
    id: int
    user_id: str | None = None
    username: str = ""
    event_type: str
    ip: str = ""
    detail: str = ""
    created_at: str | None = None

class AuthEventListResp(BaseModel):
    total: int
    items: list[AuthEventItem]
```

`register`/`create_user`/`update_user`/`delete_user` 增加 `_audit` 与密码强度校验（admin 创建/更新用户密码也需 `validate_password_strength`，失败返回 400）。

`config.py` `AuthConfig` 增加：

```python
    min_password_length: int = 8
    reset_token_ttl_minutes: int = 30
    email_verify_token_ttl_hours: int = 24
    file_url_ttl_seconds: int = 300
```

并加 env 覆盖 `CANCER_CLAW_AUTH_RESET_TOKEN_TTL_MINUTES`、`CANCER_CLAW_AUTH_EMAIL_VERIFY_TTL_HOURS`、`CANCER_CLAW_AUTH_FILE_URL_TTL_SECONDS`。

- [ ] **Step 5: 修正管理员测试用例并运行通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_auth_api.py -q
```

Expected: 全 PASS。

- [ ] **Step 6: Commit**

```bash
git add cancer_claw/services/identity/deps.py cancer_claw/interfaces/routes/auth.py cancer_claw/config.py tests/test_auth_api.py tests/conftest.py
git commit -m "feat(auth): change-password, forgot/reset, email verify, audit events, token_version"
```

---

## Task 5: 签名文件 URL

**Files:**
- Modify: `cancer_claw/interfaces/routes/files.py`
- Create: `tests/test_files_sign.py`

- [ ] **Step 1: 写失败测试** `tests/test_files_sign.py`

```python
import hmac
import time

from httpx import ASGITransport, AsyncClient


async def _register_and_project(app, client, tmp_path):
    from cancer_claw.services.identity.deps import get_auth_secret

    resp = await client.post("/api/auth/register", json={
        "username": "fileuser", "password": "StrongPass1!",
    })
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post("/api/projects", json={
        "name": "demo", "description": "demo",
    }, headers=headers)
    assert resp.status_code == 200, resp.text
    project = resp.json()
    project_dir = __import__("pathlib").Path(app.state.__dict__.get("_test_projects", ""))
    return token, headers, project["id"], project_dir


async def test_sign_and_fetch_without_bearer(app, client, tmp_path):
    from cancer_claw.config import settings
    from pathlib import Path

    token, headers, project_id, _ = await _register_and_project(app, client, tmp_path)
    project_dir = Path(settings.paths.projects_dir) / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "readme.txt").write_text("hello", encoding="utf-8")

    resp = await client.post(
        f"/api/projects/{project_id}/files/sign",
        json={"path": "readme.txt", "download": False},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    url = resp.json()["url"]
    assert "access_token" not in url

    resp = await client.get(url)
    assert resp.status_code == 200
    assert resp.text == "hello"


async def test_signed_url_rejects_tamper_and_expired(app, client, tmp_path):
    from cancer_claw.config import settings
    from cancer_claw.services.identity.deps import get_auth_secret
    from pathlib import Path

    token, headers, project_id, _ = await _register_and_project(app, client, tmp_path)
    project_dir = Path(settings.paths.projects_dir) / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "a.txt").write_text("aaa", encoding="utf-8")

    exp = int(time.time()) + 300
    payload = f"{project_id}|a.txt|0|{exp}"
    sig = hmac.new(get_auth_secret().encode(), payload.encode(), __import__("hashlib").sha256).hexdigest()
    ok_url = f"/api/projects/{project_id}/files/raw?path=a.txt&download=false&exp={exp}&sig={sig}"
    assert (await client.get(ok_url)).status_code == 200

    bad = f"{project_id}|b.txt|0|{exp}"
    bad_sig = hmac.new(get_auth_secret().encode(), bad.encode(), __import__("hashlib").sha256).hexdigest()
    bad_url = f"/api/projects/{project_id}/files/raw?path=b.txt&download=false&exp={exp}&sig={bad_sig}"
    assert (await client.get(bad_url)).status_code == 401

    exp_past = int(time.time()) - 10
    p2 = f"{project_id}|a.txt|0|{exp_past}"
    s2 = hmac.new(get_auth_secret().encode(), p2.encode(), __import__("hashlib").sha256).hexdigest()
    expired_url = f"/api/projects/{project_id}/files/raw?path=a.txt&download=false&exp={exp_past}&sig={s2}"
    assert (await client.get(expired_url)).status_code == 401
```

注：签名算法统一为 `_sign_url(payload)` = `hmac.new(secret, payload, sha256).hexdigest()`，测试与实现保持一致。

- [ ] **Step 2: 运行确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_files_sign.py -q
```

- [ ] **Step 3: 实现 `files.py`**

新增 import：`hmac, time, urlencode, Request`、`get_auth_secret`、`resolve_access_from_request`。

```python
def _sign_url(payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

def _signed_payload(project_id: str, path: str, download: bool, exp: int) -> str:
    return f"{project_id}|{path}|{int(download)}|{exp}"
```

`get_raw_file` 签名改为：

```python
@router.get("/projects/{project_id}/files/raw", ...)
async def get_raw_file(
    request: Request,
    project_id: str,
    path: str = Query(...),
    download: bool = Query(default=False),
    sig: str | None = Query(default=None),
    exp: int | None = Query(default=None),
):
    if sig is not None or exp is not None:
        if not sig or exp is None:
            raise HTTPException(status_code=400, detail="签名参数不完整")
        expected = _sign_url(_signed_payload(project_id, path, download, exp), get_auth_secret())
        if not hmac.compare_digest(expected, sig):
            raise HTTPException(status_code=401, detail="签名无效")
        if time.time() > exp:
            raise HTTPException(status_code=401, detail="链接已过期")
    else:
        await resolve_access_from_request(request, project_id, need="read")
    await _assert_project_exists(project_id)
    target = _resolve_safe_file(project_id, path)
    ...
```

新端点：

```python
class SignFileReq(BaseModel):
    path: str = Field(..., max_length=1024)
    download: bool = False

@router.post("/projects/{project_id}/files/sign", response_model=dict)
async def sign_file(
    project_id: str,
    body: SignFileReq,
    _ctx: dict = Depends(require_project_read),
) -> dict:
    _resolve_safe_file(project_id, body.path)
    exp = int(time.time()) + settings.auth.file_url_ttl_seconds
    sig = _sign_url(_signed_payload(project_id, body.path, body.download, exp), get_auth_secret())
    qs = urlencode({
        "path": body.path,
        "download": str(body.download).lower(),
        "exp": str(exp),
        "sig": sig,
    })
    return {
        "url": f"/api/projects/{project_id}/files/raw?{qs}",
        "expires_at": exp,
    }
```

（`get_auth_secret` 为空时自动生成仅开发用；签名密钥复用 auth secret。）

- [ ] **Step 4: 运行确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_files_sign.py -q
```

- [ ] **Step 5: Commit**

```bash
git add cancer_claw/interfaces/routes/files.py tests/test_files_sign.py
git commit -m "feat(files): short-lived signed URLs instead of access_token query param"
```

---

## Task 6: 前端 API 客户端与鉴权守卫

**Files:**
- Modify: `web/src/client/services/client.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/ui/widgets/common/PresentedFileCard.tsx`
- Modify: `web/src/application/state/authStore.ts`（`AuthUser` 增加 `email_verified`）

- [ ] **Step 1: `client.ts`**

新增类型与接口：

```ts
export interface AuthEventItem {
  id: number
  user_id?: string | null
  username: string
  event_type: string
  ip: string
  detail: string
  created_at?: string | null
}

export interface SignedFileUrl {
  url: string
  expires_at: number
}
```

`AuthUser` 增加 `email_verified?: boolean`。

新增 API：

```ts
  changePassword: (currentPassword: string, newPassword: string) =>
    http.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    }).then((r) => r.data),
  forgotPassword: (payload: { username?: string; email?: string }) =>
    http.post<{ ok: boolean }>('/auth/forgot-password', payload).then((r) => r.data),
  resetPassword: (token: string, newPassword: string) =>
    http.post<{ ok: boolean }>('/auth/reset-password', {
      token,
      new_password: newPassword,
    }).then((r) => r.data),
  verifyEmail: (token: string) =>
    http.get<{ ok: boolean }>('/auth/verify-email', { params: { token } }).then((r) => r.data),
  sendVerificationEmail: () =>
    http.post<{ ok: boolean }>('/auth/send-verification').then((r) => r.data),
  signFileUrl: (projectId: string, path: string, download = false) =>
    http
      .post<SignedFileUrl>(`/projects/${projectId}/files/sign`, { path, download })
      .then((r) => r.data),
  listAuthEvents: (params?: { limit?: number; offset?: number }) =>
    http
      .get<{ total: number; items: AuthEventItem[] }>('/admin/auth-events', { params })
      .then((r) => r.data),
```

删除 `fileRawUrl`。响应拦截器改为：

```ts
http.interceptors.response.use(
  (resp) => resp,
  (err: AxiosError) => {
    const status = err.response?.status
    const url = err.config?.url || ''
    const isAuthEndpoint = url.includes('/auth/login') || url.includes('/auth/register')
    const detail =
      err.response?.data && typeof err.response.data === 'object'
        ? (err.response.data as { detail?: unknown }).detail
        : undefined
    const accountDisabled =
      status === 403 && typeof detail === 'string' && detail.includes('禁用')
    if ((status === 401 && !isAuthEndpoint) || accountDisabled) {
      forceLogout()
    }
    return Promise.reject(new ApiError(formatApiError(err), status))
  },
)
```

- [ ] **Step 2: `App.tsx` RequireAuth 启动校验**

```tsx
import { useEffect, useState } from 'react'
import { useAuthStore, forceLogout, checkPermission } from './application/state/authStore'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  const setUser = useAuthStore((s) => s.setUser)
  const [validating, setValidating] = useState(!!token)
  const loc = useLocation()

  useEffect(() => {
    if (!token) {
      setValidating(false)
      return
    }
    let cancelled = false
    setValidating(true)
    api.me()
      .then((u) => {
        if (!cancelled) {
          setUser(u as AuthUser)
          setValidating(false)
        }
      })
      .catch(() => {
        if (!cancelled) forceLogout()
      })
    return () => {
      cancelled = true
    }
  }, [token, setUser])

  if (!token) {
    return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />
  }
  if (validating) {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">
        正在验证登录状态…
      </div>
    )
  }
  return <>{children}</>
}
```

（`AuthUser` 从 `@/client/services/client` 导入，`api` 从 `@/client/services/client` 导入。）

- [ ] **Step 3: `PresentedFileCard.tsx` 改用签名 URL**

```tsx
const [signed, setSigned] = useState<{ raw?: string; download?: string }>({})

useEffect(() => {
  let cancelled = false
  setSigned({})
  api.signFileUrl(projectId, file.path).then((u) => {
    if (!cancelled) setSigned((s) => ({ ...s, raw: u.url }))
  }).catch(() => {})
  api.signFileUrl(projectId, file.path, true).then((u) => {
    if (!cancelled) setSigned((s) => ({ ...s, download: u.url }))
  }).catch(() => {})
  return () => { cancelled = true }
}, [projectId, file.path])
```

`rawUrl`/`downloadUrl` 的 `useMemo` 删除，引用处改为 `signed.raw`/`signed.download`；URL 未就绪时按钮 disabled（或渲染占位）。

- [ ] **Step 4: 构建验证**

```bash
cd web; npx tsc -b --pretty false
```

Expected: 无类型错误。

- [ ] **Step 5: Commit**

```bash
git add web/src/client/services/client.ts web/src/App.tsx web/src/ui/widgets/common/PresentedFileCard.tsx web/src/application/state/authStore.ts
git commit -m "feat(web): auth guards, signed file urls, client APIs"
```

---

## Task 7: 前端 UI（账户页 / 登录页 / 审计页）

**Files:**
- Create: `web/src/ui/views/Account.tsx`
- Create: `web/src/ui/views/admin/AuthEvents.tsx`
- Modify: `web/src/ui/views/Login.tsx`
- Modify: `web/src/ui/widgets/Layout/AppLayout.tsx`
- Modify: `web/src/App.tsx`
- Modify: `cancer_claw/services/identity/permissions.py`（`AUDIT_VIEW`）

- [ ] **Step 1: 权限常量**

`permissions.py` 增加 `AUDIT_VIEW = "audit.view"`，加入 `PERMISSION_CATALOG` 的 `action` 组并保持 `ALL_PERMISSIONS` 自动覆盖（admin 全量权限）。

- [ ] **Step 2: `Account.tsx`（改密 + 邮箱状态）**

仿照现有页面结构（Card + Button + Input + toast）：改密表单（当前密码/新密码/确认新密码，新密码 >= 8 位），提交调用 `api.changePassword`，成功后提示并清空；邮箱卡片展示 `user.email`、`email_verified` 状态，未认证且后端支持时提供"发送验证邮件"按钮（`api.sendVerificationEmail`）。

- [ ] **Step 3: `Login.tsx` 扩展**

- `Mode` 增加 `'forgot' | 'reset'`。
- 从 `useLocation` 读取 `reset_token` / `verify_token` 查询参数：`reset_token` 存在时强制 `mode='reset'` 并渲染新密码+确认密码表单；`verify_token` 存在时 `useEffect` 调 `api.verifyEmail` 并 toast 结果。
- 注册表单增加 `email` 输入框（`autoComplete="email"`）。
- 忘记密码入口：登录表单下加"忘记密码？"按钮切换 `mode='forgot'`，提交 `api.forgotPassword({ email 或 username })`，成功提示"如账号存在且已绑定邮箱，重置邮件已发送"。
- 密码长度提示统一改为"至少 8 位"。
- `allowRegistration` 仅控制 login/register 切换。

- [ ] **Step 4: `AppLayout.tsx` 用户菜单增加"账户设置"**

`UserMenu` 的 DropdownMenu 中，退出登录项上方增加：

```tsx
<DropdownMenuItem onClick={() => nav('/account')}>
  <Settings className="h-4 w-4" />
  账户设置
</DropdownMenuItem>
```

（`Settings` 从 lucide-react 导入。）

- [ ] **Step 5: `App.tsx` 路由**

```tsx
<Route path="/account" element={<Account />} />
<Route
  path="/admin/auth-events"
  element={
    <RequirePermission perm="audit.view">
      <AuthEvents />
    </RequirePermission>
  }
/>
```

`ADMIN_NAV_ITEMS` 增加安全日志项（`to: '/admin/auth-events'`，icon 用 `ScrollText`，perm `'menu.evolution'` 或直接 `audit.view`；建议新增 `menu` 权限无需——直接使用 `audit.view`）。

- [ ] **Step 6: `AuthEvents.tsx`**

`useQuery(['admin-auth-events'], () => api.listAuthEvents({ limit: 100 }))` 表格展示时间/用户/事件/来源 IP/详情，刷新按钮。

- [ ] **Step 7: 构建验证**

```bash
cd web; npx tsc -b --pretty false
```

- [ ] **Step 8: Commit**

```bash
git add web/src cancer_claw/services/identity/permissions.py
git commit -m "feat(web): account page, login recovery/verification flows, auth events view"
```

---

## Task 8: 配置与文档

**Files:**
- Modify: `config.yaml`
- Modify: `ops/config/production.yaml`
- Modify: `ops/env.example`

- [ ] **Step 1: 三个配置文件补注释与默认值**

`auth:` 下增加：

```yaml
  min_password_length: 8
  reset_token_ttl_minutes: 30
  email_verify_token_ttl_hours: 24
  file_url_ttl_seconds: 300
```

新增：

```yaml
mail:
  host: ""
  port: 587
  username: ""
  password: ""
  from_addr: ""
  starttls: true
  public_base_url: ""
```

`ops/env.example` 增加：

```bash
CANCER_CLAW_SMTP_HOST=
CANCER_CLAW_SMTP_PORT=587
CANCER_CLAW_SMTP_USERNAME=
CANCER_CLAW_SMTP_PASSWORD=
CANCER_CLAW_SMTP_FROM=
CANCER_CLAW_SMTP_STARTTLS=true
CANCER_CLAW_PUBLIC_BASE_URL=
CANCER_CLAW_AUTH_MIN_PASSWORD_LENGTH=8
```

- [ ] **Step 2: Commit**

```bash
git add config.yaml ops/config/production.yaml ops/env.example
git commit -m "docs(config): mail + password policy + signed url settings"
```

---

## Task 9: 全量验证

- [ ] **Step 1: 后端测试**

```bash
.venv/Scripts/python.exe -m pytest -q
```

Expected: 全 PASS。

- [ ] **Step 2: 前端构建**

```bash
cd web; npm run build
```

Expected: 构建成功（无类型错误）。

- [ ] **Step 3: 冒烟启动**

```bash
.venv/Scripts/python.exe -c "from cancer_claw.app import app; print(app.title)"
```

- [ ] **Step 4: 自查对照**

- 自助改密是否使旧 token 失效？→ `change-password` + `token_version`
- 找回/重置是否可用且一次性？→ `forgot-password` / `reset-password`
- 邮箱是否采集、验证？→ 注册 email + `verify-email`
- 密码策略与 600k 迭代？→ `validate_password_strength` / `_PBKDF2_ITERATIONS`
- JWT 是否用库？→ PyJWT + `jti`/`iss`/`ver`
- 审计是否可查？→ `auth_events` + `/admin/auth-events`
- 文件 URL 是否不再带 token？→ `files/sign` 签名 URL
- 前端启动校验 + 403 禁用登出？→ `RequireAuth` + interceptor

Expected: 全部满足。

- [ ] **Step 5: 汇总提交**

```bash
git log --oneline -10
git status --short
```

确认无遗漏文件后，按 `finishing-a-development-branch` 收尾。
