import re


async def _register(client, username="alice", password="StrongPass1!", email=""):
    resp = await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": password,
            "email": email,
            "display_name": username,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_register_login_me(client):
    data = await _register(client)
    assert data["access_token"]
    assert data["user"]["username"] == "alice"
    assert data["user"]["email_verified"] is False

    resp = await client.post(
        "/api/auth/login", json={"username": "alice", "password": "StrongPass1!"}
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    resp = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"


async def test_register_rejects_weak_password(client):
    resp = await client.post(
        "/api/auth/register", json={"username": "weak", "password": "12345678"}
    )
    assert resp.status_code == 400


async def test_change_password_invalidates_old_token(client):
    data = await _register(client)
    old_token = data["access_token"]
    resp = await client.post(
        "/api/auth/change-password",
        json={"current_password": "StrongPass1!", "new_password": "NewStrong2!"},
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert resp.status_code == 204

    resp = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}
    )
    assert resp.status_code == 401

    resp = await client.post(
        "/api/auth/login", json={"username": "alice", "password": "NewStrong2!"}
    )
    assert resp.status_code == 200


async def test_change_password_wrong_current(client):
    data = await _register(client)
    resp = await client.post(
        "/api/auth/change-password",
        json={"current_password": "WrongPass1!", "new_password": "NewStrong2!"},
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert resp.status_code == 401


async def test_forgot_password_requires_mail_config(client):
    await _register(client, username="carol", email="carol@example.com")
    resp = await client.post(
        "/api/auth/forgot-password", json={"email": "carol@example.com"}
    )
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

    resp = await client.post(
        "/api/auth/forgot-password", json={"email": "dave@example.com"}
    )
    assert resp.status_code == 202
    m = re.search(r"reset_token=([A-Za-z0-9_-]+)", sent["text"])
    assert m, sent["text"]

    resp = await client.post(
        "/api/auth/reset-password", json={"token": m.group(1), "new_password": "ResetPass1!"}
    )
    assert resp.status_code == 200

    resp = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}
    )
    assert resp.status_code == 401

    resp = await client.post(
        "/api/auth/reset-password", json={"token": m.group(1), "new_password": "ResetPass2!"}
    )
    assert resp.status_code == 400


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

    resp = await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "12345678"}
    )
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

    resp = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"}
    )
    assert resp.json()["email_verified"] is True


async def test_audit_events_recorded_and_admin_listed(client):
    await _register(client, username="grace")
    resp = await client.post(
        "/api/auth/login", json={"username": "grace", "password": "StrongPass1!"}
    )
    token = resp.json()["access_token"]
    await client.post(
        "/api/auth/login", json={"username": "grace", "password": "WrongPass1!"}
    )

    resp = await client.get(
        "/api/admin/auth-events", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    events = {e["event_type"] for e in body["items"]}
    assert {"register", "login_success", "login_failed"} <= events


async def test_disabled_user_gets_403_and_me_rejects(client):
    admin_data = await _register(client, username="root_admin")
    admin = admin_data["access_token"]
    data = await _register(client, username="hank")
    user_id = data["user"]["id"]

    resp = await client.patch(
        f"/api/users/{user_id}",
        json={"status": "disabled"},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert resp.status_code == 200

    resp = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"}
    )
    assert resp.status_code == 403
