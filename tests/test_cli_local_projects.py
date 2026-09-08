import re
from pathlib import Path


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


async def test_cli_local_project_hidden_from_web_lists(client, tmp_path):
    admin = await _register(client, "boss")
    alice = await _register(client, "alice")
    ah = {"Authorization": f"Bearer {admin['access_token']}"}
    h1 = {"Authorization": f"Bearer {alice['access_token']}"}

    resp = await client.post("/api/projects", json={"name": "正常项目"}, headers=h1)
    assert resp.status_code == 201, resp.text
    web_pid = resp.json()["id"]

    from cancer_claw.client.project import ensure_local_project

    work = tmp_path / "cancer_claw_share_fake"
    work.mkdir()
    cli_pid, _ = await ensure_local_project(work)

    resp = await client.get("/api/projects", headers=ah)
    assert resp.status_code == 200, resp.text
    ids = {p["id"] for p in resp.json()["items"]}
    assert web_pid in ids
    assert cli_pid not in ids

    resp = await client.get("/api/projects", headers=h1)
    assert resp.status_code == 200, resp.text
    ids = {p["id"] for p in resp.json()["items"]}
    assert web_pid in ids
    assert cli_pid not in ids

    resp = await client.get("/api/admin/projects", headers=ah)
    assert resp.status_code == 200, resp.text
    ids = {p["id"] for p in resp.json()["items"]}
    assert web_pid in ids
    assert cli_pid not in ids

    resp = await client.get("/api/admin/projects/stats", headers=ah)
    assert resp.status_code == 200, resp.text
    stats_ids = {p["id"] for p in resp.json()["projects"]}
    assert web_pid in stats_ids
    assert cli_pid not in stats_ids
    assert resp.json()["totals"]["projects"] == 1


async def test_migrate_marks_existing_outside_workspace_as_cli_local(app):
    from cancer_claw.config import settings
    from cancer_claw.db import _migrate_mark_cli_local_projects, get_db

    db = await get_db()
    outside = str(Path(settings.paths.projects_dir).resolve().parent / "cli-outside")
    await db.execute(
        "INSERT INTO projects (id, name, description, workspace_path, owner_id, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "abcdef123456",
            "cancer_claw_share_20260722_1757",
            "本地工作区",
            outside,
            "local",
            "web",
        ),
    )
    await db.commit()
    await _migrate_mark_cli_local_projects(db)
    await db.commit()
    cur = await db.execute("SELECT source FROM projects WHERE id = ?", ("abcdef123456",))
    row = await cur.fetchone()
    assert row is not None
    assert row[0] == "cli_local"
