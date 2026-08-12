import re


def _solve_challenge(challenge):
    m = re.match(r"(\d+)\s*\+\s*(\d+) = \?", challenge["question"])
    assert m, challenge["question"]
    return str(int(m.group(1)) + int(m.group(2)))


async def _register(client, username="alice", password="StrongPass1!"):
    resp = await client.get("/api/auth/captcha")
    assert resp.status_code == 200, resp.text
    challenge = resp.json()
    resp = await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": password,
            "email": f"{username}@example.com",
            "display_name": username,
            "captcha": {"id": challenge["id"], "answer": _solve_challenge(challenge)},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _make_project(client, headers: dict, name="demo") -> str:
    resp = await client.post("/api/projects", json={"name": name}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_frozen_blocks_write_and_chat_but_allows_read(client):
    admin = await _register(client, "boss")
    alice = await _register(client, "alice")
    ah = {"Authorization": f"Bearer {admin['access_token']}"}
    h1 = {"Authorization": f"Bearer {alice['access_token']}"}
    pid = await _make_project(client, h1)

    from cancer_claw.services.projects.service import (
        PROJECT_STATUS_FROZEN,
        set_project_status,
    )

    await set_project_status(pid, PROJECT_STATUS_FROZEN, admin)

    resp = await client.patch(
        f"/api/projects/{pid}", json={"description": "x"}, headers=h1
    )
    assert resp.status_code == 403

    resp = await client.post(
        f"/api/projects/{pid}/chat", json={"message": "hi"}, headers=h1
    )
    assert resp.status_code == 403

    resp = await client.post(
        "/api/chat/sync", json={"message": "hi"}, params={"project_id": pid}, headers=h1
    )
    assert resp.status_code == 403

    # 冻结后管理员同样不能写操作 / 发起运行，但可以查看
    resp = await client.patch(
        f"/api/projects/{pid}", json={"description": "z"}, headers=ah
    )
    assert resp.status_code == 403

    resp = await client.post(
        f"/api/projects/{pid}/chat", json={"message": "hi"}, headers=ah
    )
    assert resp.status_code == 403

    resp = await client.get(f"/api/projects/{pid}", headers=ah)
    assert resp.status_code == 200

    resp = await client.get(f"/api/projects/{pid}", headers=h1)
    assert resp.status_code == 200

    from cancer_claw.services.projects.service import PROJECT_STATUS_ACTIVE

    await set_project_status(pid, PROJECT_STATUS_ACTIVE, admin)
    resp = await client.patch(
        f"/api/projects/{pid}", json={"description": "y"}, headers=h1
    )
    assert resp.status_code == 200


async def test_paused_blocks_chat_but_allows_patch(client):
    admin = await _register(client, "boss")
    alice = await _register(client, "alice")
    h1 = {"Authorization": f"Bearer {alice['access_token']}"}
    pid = await _make_project(client, h1)

    from cancer_claw.services.projects.service import (
        PROJECT_STATUS_PAUSED,
        set_project_status,
    )

    await set_project_status(pid, PROJECT_STATUS_PAUSED, admin)

    resp = await client.post(
        f"/api/projects/{pid}/chat", json={"message": "hi"}, headers=h1
    )
    assert resp.status_code == 403

    resp = await client.patch(
        f"/api/projects/{pid}", json={"description": "ok"}, headers=h1
    )
    assert resp.status_code == 200
