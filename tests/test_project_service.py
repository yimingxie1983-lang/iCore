async def _register(client, username="alice", password="StrongPass1!"):
    resp = await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": password,
            "email": "",
            "display_name": username,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_set_and_get_project_status(client):
    data = await _register(client)
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    created = await client.post("/api/projects", json={"name": "demo"}, headers=headers)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]

    from cancer_claw.services.projects.service import (
        PROJECT_STATUS_PAUSED,
        get_project_status,
        set_project_status,
    )

    assert await get_project_status(pid) == "active"
    await set_project_status(pid, PROJECT_STATUS_PAUSED, {"id": "u1", "username": "u1"})
    assert await get_project_status(pid) == PROJECT_STATUS_PAUSED


async def test_set_project_status_rejects_invalid(client):
    from cancer_claw.services.projects.service import set_project_status

    try:
        await set_project_status("p1", "weird", {"id": "u1"})
    except ValueError:
        return
    raise AssertionError("invalid status should raise ValueError")


async def test_delete_project_full_removes_related_rows(client):
    data = await _register(client)
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    created = await client.post("/api/projects", json={"name": "to-delete"}, headers=headers)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]

    from cancer_claw.db import get_db

    db = await get_db()
    await db.execute(
        "INSERT INTO chat_sessions (session_id, project_id, agent_id, title, status) "
        "VALUES ('s1', ?, 'claw_master', 't', 'active')",
        (pid,),
    )
    await db.execute(
        "INSERT INTO agent_events (session_id, project_id, agent_id, seq, type, payload_json, created_at) "
        "VALUES ('s1', ?, 'claw_master', 1, 'message', '{}', 1.0)",
        (pid,),
    )
    await db.commit()

    from cancer_claw.services.projects.service import delete_project_full

    await delete_project_full(pid)

    cur = await db.execute("SELECT COUNT(*) FROM projects WHERE id = ?", (pid,))
    assert (await cur.fetchone())[0] == 0
    cur = await db.execute("SELECT COUNT(*) FROM chat_sessions WHERE project_id = ?", (pid,))
    assert (await cur.fetchone())[0] == 0
    cur = await db.execute("SELECT COUNT(*) FROM agent_events WHERE project_id = ?", (pid,))
    assert (await cur.fetchone())[0] == 0
