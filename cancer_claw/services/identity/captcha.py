from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from cancer_claw.services.identity.deps import get_auth_secret


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _sign(payload: str, secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def create_challenge(*, ttl: int = 120) -> dict[str, Any]:

    a = secrets.randbelow(90) + 10
    b = secrets.randbelow(90) + 10
    exp = int(time.time()) + ttl
    payload = json.dumps(
        {"ans": a + b, "exp": exp, "nonce": secrets.token_urlsafe(8)},
        separators=(",", ":"),
    )
    token = _b64url(payload.encode("utf-8"))
    sig = _sign(token, get_auth_secret())
    return {
        "id": f"{token}.{sig}",
        "question": f"{a} + {b} = ?",
        "expires_in": ttl,
    }


def verify_challenge(token: str, answer: str) -> bool:

    if not token or not answer:
        return False
    parts = token.split(".")
    if len(parts) != 2:
        return False
    payload_b64, sig = parts
    expected = _sign(payload_b64, get_auth_secret())
    if not hmac.compare_digest(expected, sig):
        return False
    try:
        raw = base64.urlsafe_b64decode(
            payload_b64 + "=" * (-len(payload_b64) % 4)
        ).decode("utf-8")
        payload = json.loads(raw)
    except (ValueError, TypeError, json.JSONDecodeError):
        return False
    if time.time() > int(payload.get("exp", 0) or 0):
        return False
    try:
        return int(answer) == int(payload.get("ans"))
    except (TypeError, ValueError):
        return False
