import re
import time

from cancer_claw.config import settings
from cancer_claw.services.identity import captcha


def _secret():
    settings.auth.secret = "captcha-test-secret-0123456789abcdef"


def test_challenge_verify_roundtrip():
    _secret()
    ch = captcha.create_challenge(ttl=120)
    m = re.match(r"(\d+)\s*\+\s*(\d+) = \?", ch["question"])
    assert m, ch["question"]
    answer = int(m.group(1)) + int(m.group(2))
    assert captcha.verify_challenge(ch["id"], str(answer))
    assert not captcha.verify_challenge(ch["id"], str(answer + 1))


def test_expired_challenge_rejected():
    _secret()
    ch = captcha.create_challenge(ttl=1)
    time.sleep(1.1)
    assert not captcha.verify_challenge(ch["id"], "1")


def test_tampered_challenge_rejected():
    _secret()
    ch = captcha.create_challenge(ttl=120)
    parts = ch["id"].split(".")
    assert len(parts) == 2
    assert not captcha.verify_challenge(parts[0] + ".deadbeef", "1")
