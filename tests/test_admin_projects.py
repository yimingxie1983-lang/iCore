import asyncio
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


async def _create(client, headers: dict, name: str) -> str:
    resp = await client.post("/api/projects", json={"name": name}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_admin_list_projects_filters(client):
    admin = await _register(client, "boss")
    alice = await _register(client, "alice")
    bob = await _register(client, "bob")
    ah = {"Authorization": f"Bearer {admin['access_token']}"}
    h1 = {"Authorization": f"Bearer {alice['access_token']}"}
    h2 = {"Authorization": f"Bearer {bob['access_token']}"}

    pid1 = await _create(client, h1, "肝癌研究")
    pid2 = await _create(client, h2, "肺癌队列")

    resp = await client.get("/api/admin/projects", headers=ah)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[pid1]["owner_username"] == "alice"
    assert by_id[pid1]["status"] == "active"
    assert by_id[pid1]["running"] is False
    assert by_id[pid1]["running_sessions"] == 0

    resp = await client.get(
        "/api/admin/projects", params={"q": "肝癌"}, headers=ah
    )
    assert resp.json()["total"] == 1

    resp = await client.get(
        "/api/admin/projects", params={"owner": "bob"}, headers=ah
    )
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["id"] == pid2

    resp = await client.get(
        "/api/admin/projects", params={"running": "true"}, headers=ah
    )
    assert resp.json()["total"] == 0

    from datetime import date

    today = date.today().isoformat()
    resp = await client.get(
        "/api/admin/projects",
        params={"date_from": today, "date_to": today},
        headers=ah,
    )
    assert resp.json()["total"] == 2

    # 大分页：一次返回全部项目
    resp = await client.get(
        "/api/admin/projects", params={"limit": 500}, headers=ah
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


async def test_non_admin_forbidden(client):
    await _register(client, "boss")  # 第一个注册用户是 admin
    alice = await _register(client, "alice")
    headers = {"Authorization": f"Bearer {alice['access_token']}"}
    resp = await client.get("/api/admin/projects", headers=headers)
    assert resp.status_code == 403
    resp = await client.post("/api/admin/projects/x/pause", headers=headers)
    assert resp.status_code == 403


async def test_pause_cancels_running_and_blocks_chat(client):
    admin = await _register(client, "boss")
    alice = await _register(client, "alice")
    ah = {"Authorization": f"Bearer {admin['access_token']}"}
    h1 = {"Authorization": f"Bearer {alice['access_token']}"}
    pid = await _create(client, h1, "demo")

    from cancer_claw.agent.engine.session_hub import get_session_hub

    hub = get_session_hub()
    started = asyncio.Event()

    async def _runner(_emitter):
        started.set()
        await asyncio.sleep(3600)

    await hub.start("sid-1", project_id=pid, agent_id="a1", runner=_runner)
    assert await hub.is_running("sid-1")

    resp = await client.post(f"/api/admin/projects/{pid}/pause", headers=ah)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "paused"
    assert body["cancelled_runs"] == 1
    assert await hub.running_session_ids(pid) == []

    resp = await client.post(
        f"/api/projects/{pid}/chat", json={"message": "hi"}, headers=h1
    )
    assert resp.status_code == 403

    resp = await client.post(f"/api/admin/projects/{pid}/resume", headers=ah)
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


async def test_freeze_and_unfreeze(client):
    admin = await _register(client, "boss")
    alice = await _register(client, "alice")
    ah = {"Authorization": f"Bearer {admin['access_token']}"}
    h1 = {"Authorization": f"Bearer {alice['access_token']}"}
    pid = await _create(client, h1, "demo")

    resp = await client.post(f"/api/admin/projects/{pid}/freeze", headers=ah)
    assert resp.status_code == 200
    assert resp.json()["status"] == "frozen"

    resp = await client.patch(
        f"/api/projects/{pid}", json={"description": "x"}, headers=h1
    )
    assert resp.status_code == 403

    resp = await client.post(f"/api/admin/projects/{pid}/unfreeze", headers=ah)
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


async def test_admin_delete_frozen_project_blocked(client):
    admin = await _register(client, "boss")
    alice = await _register(client, "alice")
    ah = {"Authorization": f"Bearer {admin['access_token']}"}
    h1 = {"Authorization": f"Bearer {alice['access_token']}"}
    pid = await _create(client, h1, "frozen-delete")

    resp = await client.post(f"/api/admin/projects/{pid}/freeze", headers=ah)
    assert resp.status_code == 200

    resp = await client.delete(f"/api/admin/projects/{pid}", headers=ah)
    assert resp.status_code == 403

    resp = await client.post(f"/api/admin/projects/{pid}/unfreeze", headers=ah)
    assert resp.status_code == 200

    resp = await client.delete(f"/api/admin/projects/{pid}", headers=ah)
    assert resp.status_code == 204


async def test_admin_delete_project(client):
    admin = await _register(client, "boss")
    alice = await _register(client, "alice")
    ah = {"Authorization": f"Bearer {admin['access_token']}"}
    h1 = {"Authorization": f"Bearer {alice['access_token']}"}
    pid = await _create(client, h1, "to-delete")

    resp = await client.delete(f"/api/admin/projects/{pid}", headers=ah)
    assert resp.status_code == 204

    resp = await client.get(f"/api/projects/{pid}", headers=h1)
    assert resp.status_code == 404
