import hashlib
import hmac
import re
import time


def _solve_challenge(challenge):
    m = re.match(r"(\d+)\s*\+\s*(\d+) = \?", challenge["question"])
    assert m, challenge["question"]
    return str(int(m.group(1)) + int(m.group(2)))


async def _register_and_project(client):
    resp = await client.get("/api/auth/captcha")
    assert resp.status_code == 200
    challenge = resp.json()
    resp = await client.post(
        "/api/auth/register",
        json={
            "username": "fileuser",
            "password": "StrongPass1!",
            "captcha": {
                "id": challenge["id"],
                "answer": _solve_challenge(challenge),
            },
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        "/api/projects", json={"name": "demo", "description": "demo"}, headers=headers
    )
    assert resp.status_code in (200, 201), resp.text
    return token, headers, resp.json()["id"]


def _sig(secret: str, project_id: str, path: str, download: bool, exp: int) -> str:
    payload = f"{project_id}|{path}|{int(download)}|{exp}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


async def test_sign_and_fetch_without_bearer(app, client, tmp_path):
    from pathlib import Path

    from cancer_claw.config import settings

    _, headers, project_id = await _register_and_project(client)
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
    from pathlib import Path

    from cancer_claw.config import settings
    from cancer_claw.services.identity.deps import get_auth_secret

    _, _, project_id = await _register_and_project(client)
    project_dir = Path(settings.paths.projects_dir) / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "a.txt").write_text("aaa", encoding="utf-8")
    secret = get_auth_secret()

    exp = int(time.time()) + 300
    ok_sig = _sig(secret, project_id, "a.txt", False, exp)
    ok_url = f"/api/projects/{project_id}/files/raw?path=a.txt&download=false&exp={exp}&sig={ok_sig}"
    assert (await client.get(ok_url)).status_code == 200

    bad_sig = _sig(secret, project_id, "b.txt", False, exp)
    bad_url = f"/api/projects/{project_id}/files/raw?path=a.txt&download=false&exp={exp}&sig={bad_sig}"
    assert (await client.get(bad_url)).status_code == 401

    exp_past = int(time.time()) - 10
    s2 = _sig(secret, project_id, "a.txt", False, exp_past)
    expired_url = (
        f"/api/projects/{project_id}/files/raw?path=a.txt"
        f"&download=false&exp={exp_past}&sig={s2}"
    )
    assert (await client.get(expired_url)).status_code == 401
