import base64
import hashlib
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
        hashlib.pbkdf2_hmac("sha256", b"oldpass", b"0123456789abcdef", 10_000)
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
        security.validate_password_strength("Alice123", username="alice123", min_length=8)
    security.validate_password_strength("Kx9#mQ2!z", username="alice", min_length=8)


def test_token_roundtrip_contains_ver_and_jti():
    tok = security.create_access_token(
        user_id="u1",
        username="alice",
        role="user",
        secret="test-secret-0123456789abcdef0123456789abcdef",
        ttl_hours=1,
        token_version=3,
    )
    payload = security.decode_access_token(
        tok, secret="test-secret-0123456789abcdef0123456789abcdef"
    )
    assert payload["sub"] == "u1"
    assert payload["ver"] == 3
    assert payload["iss"] == "icore"
    assert payload["jti"]


def test_token_rejects_tampered_signature():
    tok = security.create_access_token(
        user_id="u1", username="alice", role="user",
        secret="test-secret-0123456789abcdef0123456789abcdef", ttl_hours=1,
    )
    parts = tok.split(".")
    payload = parts[1] + "x" if not parts[1].endswith("=") else parts[1][:-1]
    with pytest.raises(security.TokenError):
        security.decode_access_token(
            f"{parts[0]}.{payload}.{parts[2]}",
            secret="test-secret-0123456789abcdef0123456789abcdef",
        )


def test_expired_token_rejected():
    tok = security.create_access_token(
        user_id="u1", username="alice", role="user",
        secret="test-secret-0123456789abcdef0123456789abcdef", ttl_hours=1,
        issued_at=time.time() - 7200,
    )
    with pytest.raises(security.TokenError, match="过期"):
        security.decode_access_token(
            tok, secret="test-secret-0123456789abcdef0123456789abcdef"
        )


def test_wrong_issuer_rejected():
    import jwt as pyjwt

    bad = pyjwt.encode(
        {
            "iss": "evil",
            "sub": "u1",
            "ver": 0,
            "iat": int(time.time()),
            "nbf": int(time.time()),
            "exp": int(time.time()) + 600,
        },
        "test-secret-0123456789abcdef0123456789abcdef",
        algorithm="HS256",
    )
    with pytest.raises(security.TokenError):
        security.decode_access_token(
            bad, secret="test-secret-0123456789abcdef0123456789abcdef"
        )


def test_verify_token_helpers():
    raw = security.generate_token()
    assert len(raw) >= 32
    h = security.hash_token(raw)
    assert h == security.hash_token(raw)
    assert h != raw
