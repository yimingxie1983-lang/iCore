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


async def test_admin_project_stats_cockpit(client):
    admin = await _register(client, "boss")
    alice = await _register(client, "alice")
    bob = await _register(client, "bob")
    ah = {"Authorization": f"Bearer {admin['access_token']}"}
    h1 = {"Authorization": f"Bearer {alice['access_token']}"}
    h2 = {"Authorization": f"Bearer {bob['access_token']}"}

    pid1 = await _create(client, h1, "肝癌研究")
    pid2 = await _create(client, h2, "肺癌队列")
    await client.post(f"/api/admin/projects/{pid2}/pause", headers=ah)

    from cancer_claw.db import get_db

    db = await get_db()
    await db.execute(
        "INSERT INTO chat_sessions "
        "(session_id, project_id, agent_id, title, preview, "
        " message_count, tool_calls, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("20260826_stats_master", pid1, "claw_master", "会话A", "", 4, 0, "ended"),
    )
    await db.commit()

    resp = await client.get("/api/admin/projects/stats", headers=ah)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    totals = body["totals"]
    assert totals["projects"] == 2
    assert totals["active"] == 1
    assert totals["paused"] == 1
    assert totals["frozen"] == 0
    assert totals["sessions"] == 1
    assert totals["messages"] == 4
    assert totals["owners"] == 2
    assert len(body["created_last_14d"]) == 14
    by_id = {p["id"]: p for p in body["projects"]}
    assert by_id[pid1]["session_count"] == 1
    assert by_id[pid1]["message_count"] == 4
    assert by_id[pid2]["status"] == "paused"

    import json
    import time

    await db.execute(
        "INSERT INTO agent_events "
        "(session_id, project_id, agent_id, seq, type, payload_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "20260826_stats_master",
            pid1,
            "claw_master",
            1,
            "usage",
            json.dumps(
                {
                    "type": "usage",
                    "model": "kimi-k2",
                    "input_tokens": 1000,
                    "cached_input_tokens": 200,
                    "output_tokens": 300,
                    "total_tokens": 1300,
                }
            ),
            time.time(),
        ),
    )
    await db.commit()

    resp = await client.get("/api/admin/projects/stats", headers=ah)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    tok = body["tokens"]
    assert tok["input_tokens"] == 1000
    assert tok["cached_input_tokens"] == 200
    assert tok["output_tokens"] == 300
    assert tok["total_tokens"] == 1300
    assert tok["fresh_input_tokens"] == 800
    assert tok["calls"] == 1
    assert len(tok["last_14d"]) == 14
    assert tok["by_model"][0]["model"] == "kimi-k2"
    from cancer_claw.services.credits.pricing import compute_cost_micro_cny, compute_credits
    from cancer_claw.services.identity import settings_repo

    cfg = await settings_repo.get_billing_config()
    exp_cost = compute_cost_micro_cny(
        "kimi-k2", input_tokens=1000, cached_input_tokens=200, output_tokens=300
    )
    exp_credits = compute_credits(
        "kimi-k2",
        input_tokens=1000,
        cached_input_tokens=200,
        output_tokens=300,
        markup=float(cfg["markup"]),
        mode=str(cfg["mode"]),
        flat_credits_per_1m=float(cfg["flat_credits_per_1m"]),
        flat_output_credits_per_1m=float(cfg["flat_output_credits_per_1m"]),
    )
    assert tok["cost_micro_cny"] == exp_cost
    assert tok["credits"] == exp_credits
    assert tok["by_model"][0]["cost_micro_cny"] == exp_cost
    assert len(tok["last_24h_hourly"]) == 24
    assert sum(h["input_tokens"] for h in tok["last_24h_hourly"]) == 1000
    assert sum(h["cost_micro_cny"] for h in tok["last_24h_hourly"]) == exp_cost
    assert any(d["cost_micro_cny"] == exp_cost for d in tok["last_14d"])
    by_id = {p["id"]: p for p in body["projects"]}
    assert by_id[pid1]["input_tokens"] == 1000
    assert by_id[pid1]["output_tokens"] == 300
    assert by_id[pid1]["cost_micro_cny"] == exp_cost
    assert by_id[pid2]["input_tokens"] == 0

    alice_h = {"Authorization": f"Bearer {alice['access_token']}"}
    resp = await client.get("/api/admin/projects/stats", headers=alice_h)
    assert resp.status_code == 403


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
