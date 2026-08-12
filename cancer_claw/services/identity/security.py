from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import uuid
from typing import Any

import jwt as pyjwt

_PBKDF2_ITERATIONS = 600_000
_PBKDF2_ALGO = "pbkdf2_sha256"

COMMON_PASSWORDS: frozenset[str] = frozenset({
    "password", "password1", "password123", "12345678", "123456789",
    "1234567890", "qwertyuiop", "qwerty123", "admin123", "admin888",
    "abc12345", "iloveyou", "11111111", "00000000", "letmein",
    "welcome1", "changeme", "monkey123", "dragon123", "66666666",
})


def hash_password(password: str, *, iterations: int = _PBKDF2_ITERATIONS) -> str:

    if not password:
        raise ValueError("密码不能为空")
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "{}${}${}${}".format(
        _PBKDF2_ALGO,
        iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(dk).decode("ascii"),
    )


def needs_rehash(stored: str) -> bool:

    try:
        algo, iter_s, _salt, _dk = stored.split("$", 3)
        return algo == _PBKDF2_ALGO and int(iter_s) < _PBKDF2_ITERATIONS
    except (ValueError, TypeError):
        return False


def validate_password_strength(
    password: str, *, username: str = "", min_length: int = 8
) -> None:

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


def verify_password(password: str, stored: str) -> bool:

    if not password or not stored:
        return False
    try:
        algo, iter_s, salt_b64, hash_b64 = stored.split("$", 3)
        if algo != _PBKDF2_ALGO:
            return False
        iterations = int(iter_s)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(dk, expected)


def generate_token() -> str:

    return secrets.token_urlsafe(32)


def hash_token(raw: str) -> str:

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TokenError(Exception):
    pass


def create_access_token(
    *,
    user_id: str,
    username: str,
    role: str,
    secret: str,
    ttl_hours: int,
    issued_at: float | None = None,
    token_version: int = 0,
) -> str:

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
            token,
            secret,
            algorithms=["HS256"],
            issuer="icore",
            options={"require": ["exp", "sub"]},
        )
    except pyjwt.ExpiredSignatureError as e:
        raise TokenError("令牌已过期") from e
    except pyjwt.InvalidTokenError as e:
        raise TokenError(f"令牌无效: {e}") from e


def generate_secret() -> str:

    return secrets.token_urlsafe(48)
