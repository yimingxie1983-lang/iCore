import re
from urllib.parse import quote

from cancer_claw.capabilities.toolkit.session_history import _make_session_id


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


def test_make_session_id_strips_hash():
    sid = _make_session_id("claw_master#sub")
    assert "#" not in sid
    assert sid.endswith("_master-sub")


async def test_empty_subtask_sessions_pruned_from_list(client):
    user = await _register(client)
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    pid = await _make_project(client, headers, "测试")

    from cancer_claw.db import get_db

    db = await get_db()
    await db.execute(
        "INSERT INTO chat_sessions "
        "(session_id, project_id, agent_id, title, preview, "
        " message_count, tool_calls, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("20260821_095335_master", pid, "claw_master", "识别影像", "", 2, 0, "active"),
    )
    await db.execute(
        "INSERT INTO chat_sessions "
        "(session_id, project_id, agent_id, title, preview, "
        " message_count, tool_calls, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("20260821_101007_master#sub", pid, "claw_master#sub", "", "", 0, 0, "ended"),
    )
    await db.execute(
        "INSERT INTO chat_sessions "
        "(session_id, project_id, agent_id, title, preview, "
        " message_count, tool_calls, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("20260821_101141_master#sub", pid, "claw_master#sub", "", "", 0, 0, "ended"),
    )
    await db.commit()

    resp = await client.get(f"/api/projects/{pid}/sessions", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert [it["session_id"] for it in body["items"]] == ["20260821_095335_master"]

    cur = await db.execute(
        "SELECT session_id FROM chat_sessions WHERE project_id = ? ORDER BY session_id",
        (pid,),
    )
    leftover = [r[0] for r in await cur.fetchall()]
    assert leftover == ["20260821_095335_master"]


async def test_encoded_hash_session_id_can_be_deleted(client):
    user = await _register(client, "bob")
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    pid = await _make_project(client, headers)

    from cancer_claw.db import get_db

    sid = "20260821_101200_master#sub"
    db = await get_db()
    await db.execute(
        "INSERT INTO chat_sessions "
        "(session_id, project_id, agent_id, title, preview, "
        " message_count, tool_calls, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (sid, pid, "claw_master#sub", "", "", 1, 0, "ended"),
    )
    await db.commit()

    resp = await client.delete(
        f"/api/projects/{pid}/sessions/{quote(sid, safe='')}",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted_row"] is True

    cur = await db.execute(
        "SELECT COUNT(*) FROM chat_sessions WHERE session_id = ?",
        (sid,),
    )
    row = await cur.fetchone()
    assert int(row[0]) == 0
