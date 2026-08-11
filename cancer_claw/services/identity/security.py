

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

_PBKDF2_ITERATIONS = 240_000
_PBKDF2_ALGO = "pbkdf2_sha256"

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

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

def _sign(message: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest()
    return _b64url_encode(sig)

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
) -> str:

    if not secret:
        raise TokenError("缺少签名密钥（settings.auth.secret）")
    now = int(issued_at if issued_at is not None else time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + int(ttl_hours) * 3600,
    }
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h}.{p}".encode("ascii")
    s = _sign(signing_input, secret)
    return f"{h}.{p}.{s}"

def decode_access_token(token: str, *, secret: str) -> dict[str, Any]:

    if not token:
        raise TokenError("空令牌")
    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError("令牌结构损坏")
    h, p, s = parts
    signing_input = f"{h}.{p}".encode("ascii")
    expected_sig = _sign(signing_input, secret)
    if not hmac.compare_digest(expected_sig, s):
        raise TokenError("签名校验失败")
    try:
        payload = json.loads(_b64url_decode(p))
    except (ValueError, TypeError) as e:
        raise TokenError(f"载荷解析失败: {e}") from e
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or time.time() > exp:
        raise TokenError("令牌已过期")
    return payload

def generate_secret() -> str:

    return secrets.token_urlsafe(48)
