async def test_projects_table_has_status_columns(app):
    from cancer_claw.db import get_db

    db = await get_db()
    cur = await db.execute("PRAGMA table_info(projects)")
    cols = {row[1] for row in await cur.fetchall()}
    assert {"status", "status_changed_at", "status_changed_by"} <= cols


async def test_new_project_defaults_to_active(app):
    from cancer_claw.db import get_db

    db = await get_db()
    await db.execute(
        "INSERT INTO projects (id, name, description, workspace_path) "
        "VALUES ('p1', 'demo', '', '/tmp/p1')"
    )
    await db.commit()
    cur = await db.execute("SELECT status FROM projects WHERE id = 'p1'")
    row = await cur.fetchone()
    assert row is not None
    assert row[0] == "active"
