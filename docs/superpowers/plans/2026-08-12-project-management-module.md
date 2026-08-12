# 项目管理模块（管理员）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在“系统管理”中新增仅管理员可访问的“项目管理”模块：全量项目列表，按创建者 / 日期 / 名称 / 运行状态筛选，支持删除、暂停运行、冻结 / 解冻。

**Architecture:** 后端在 `cancer_claw/interfaces/routes/admin_projects.py` 新增 `/api/admin/projects*` 路由（`require_admin` 保护），复用 SessionHub 取消运行、共享 `delete_project_full` 级联删除；`projects` 表新增 `status`（active / paused / frozen）与变更审计列，SQLite 与 PostgreSQL 双迁移。前端新增 `web/src/ui/views/admin/Projects.tsx` 管理页，挂在 `/admin/projects`（`RequireAdmin`），侧边栏“系统管理”组新增入口。聊天 / 同步接口增加运行守卫：paused / frozen 禁止新推理；frozen 额外禁止普通用户的写操作。

**Tech Stack:** FastAPI + Pydantic + aiosqlite / asyncpg（SQLite 与 PostgreSQL 双迁移）、SessionHub（内存 / Redis）、React 18 + Vite + TypeScript + TanStack Query / Table + shadcn 风格 UI。

**状态语义（先对齐再实现）:**

- `active`：正常运行。
- `paused`（暂停运行）：立即取消该项目所有运行中的会话推理，且暂停期间任何用户（含管理员）都不能发起新的推理；项目仍可读写。管理员可 `resume` 恢复。
- `frozen`（冻结）：除暂停的全部效果外，普通用户对该项目的写操作（走 `require_project_write` 的接口，如更新项目、上传、会话修改等）一律 403；管理员仍可解冻 / 管理。只读访问不受影响。
- `running` 不落库，由 SessionHub 实时计算，管理列表在返回前合并。

---

## File Structure

后端：

- `cancer_claw/db.py`（M）— projects 表新增 `status` / `status_changed_at` / `status_changed_by` 三列 + 状态索引；SQLite / PG 双迁移。
- `cancer_claw/services/projects/__init__.py`（C）— 新服务包。
- `cancer_claw/services/projects/service.py`（C）— 状态读写、取消项目运行、级联删除共享逻辑。
- `cancer_claw/services/identity/deps.py`（M）— `_load_project` 带出 status；`require_project_write` 增加冻结守卫；新增 `require_project_runnable`。
- `cancer_claw/interfaces/routes/chat.py`（M）— `chat_stream` / `chat_sync` 使用运行守卫。
- `cancer_claw/interfaces/routes/projects.py`（M）— 删除逻辑改为调用共享服务。
- `cancer_claw/interfaces/routes/admin_projects.py`（C）— 管理员项目管理路由。
- `cancer_claw/app.py`（M）— 挂载 admin_projects_router。
- `cancer_claw/services/identity/permissions.py`（M）— 增加 `menu.project_manage` 权限与目录项。

测试：

- `tests/test_project_status_migration.py`（C）
- `tests/test_project_service.py`（C）
- `tests/test_project_guards.py`（C）
- `tests/test_admin_projects.py`（C）

前端：

- `web/src/client/services/client.ts`（M）— `AdminProject` 类型 + admin API 方法。
- `web/src/ui/views/admin/Projects.tsx`（C）— 管理页。
- `web/src/App.tsx`（M）— `/admin/projects` 路由（RequireAdmin）。
- `web/src/ui/widgets/Layout/AppLayout.tsx`（M）— 系统管理导航项。

---

### Task 1: 数据库迁移 projects.status

**Files:**
- Modify: `cancer_claw/db.py`
- Test: `tests/test_project_status_migration.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_project_status_migration.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_project_status_migration.py -v`

Expected: FAIL — `OperationalError: table projects has no column named status`

- [ ] **Step 3: 实现迁移**

修改 `cancer_claw/db.py`：

1) 在 `_TABLE_SCHEMAS` 的 projects DDL 中，`market_default_role` 一行之后增加三列：

```sql
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        workspace_path TEXT NOT NULL,
        owner_id TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        status_changed_at TIMESTAMP,
        status_changed_by TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
```

2) 在 `_PG_ADD_COLUMNS` 中增加：

```python
    ("projects", "status", "TEXT NOT NULL DEFAULT 'active'"),
    ("projects", "status_changed_at", "TIMESTAMP"),
    ("projects", "status_changed_by", "TEXT"),
```

3) 在 `_create_tables` 中、`market_default_role` 迁移之后增加 SQLite 迁移：

```python
    await _migrate_add_column_if_missing(
        db, "projects", "status", "TEXT NOT NULL DEFAULT 'active'"
    )
    await _migrate_add_column_if_missing(
        db, "projects", "status_changed_at", "TIMESTAMP"
    )
    await _migrate_add_column_if_missing(
        db, "projects", "status_changed_by", "TEXT"
    )
```

4) 在 `_INDEX_SCHEMAS` 末尾增加：

```python
    "CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)",
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_project_status_migration.py -v`

Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add cancer_claw/db.py tests/test_project_status_migration.py
git commit -m "feat(db): add project status columns and migration"
```

---

### Task 2: 共享服务（状态读写 + 取消运行 + 级联删除）

**Files:**
- Create: `cancer_claw/services/projects/__init__.py`
- Create: `cancer_claw/services/projects/service.py`
- Modify: `cancer_claw/interfaces/routes/projects.py`（delete_project 改为调用共享服务）
- Test: `tests/test_project_service.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_project_service.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_project_service.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'cancer_claw.services.projects'`

- [ ] **Step 3: 实现服务包**

创建 `cancer_claw/services/projects/__init__.py`（空文件即可）。

创建 `cancer_claw/services/projects/service.py`：

```python
from __future__ import annotations

import structlog

from cancer_claw.db import get_db, transaction

logger = structlog.get_logger()

PROJECT_STATUS_ACTIVE = "active"
PROJECT_STATUS_PAUSED = "paused"
PROJECT_STATUS_FROZEN = "frozen"
VALID_PROJECT_STATUSES = frozenset(
    {PROJECT_STATUS_ACTIVE, PROJECT_STATUS_PAUSED, PROJECT_STATUS_FROZEN}
)


async def get_project_status(project_id: str) -> str | None:
    """返回项目状态；项目不存在时返回 None。"""

    db = await get_db()
    cur = await db.execute(
        "SELECT COALESCE(status, 'active') FROM projects WHERE id = ?",
        (project_id,),
    )
    row = await cur.fetchone()
    return row[0] if row else None


async def set_project_status(
    project_id: str, status: str, by_user: dict
) -> None:
    """更新项目状态并记录变更人。"""

    if status not in VALID_PROJECT_STATUSES:
        raise ValueError(f"invalid project status: {status}")
    db = await get_db()
    await db.execute(
        "UPDATE projects SET status = ?, status_changed_at = CURRENT_TIMESTAMP, "
        "status_changed_by = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, by_user.get("id"), project_id),
    )
    await db.commit()


async def cancel_project_runs(project_id: str) -> int:
    """取消该项目所有运行中的会话推理，返回成功取消数。"""

    from cancer_claw.agent.engine.session_hub import get_session_hub

    hub = get_session_hub()
    running = await hub.running_session_ids(project_id)
    cancelled = 0
    for sid in running:
        try:
            if await hub.cancel(sid):
                cancelled += 1
        except Exception as e:
            logger.warning(
                "project_cancel_run_failed",
                project_id=project_id,
                session_id=sid,
                error=str(e),
            )
    return cancelled


async def delete_project_full(project_id: str) -> None:
    """级联删除项目相关数据并关闭项目沙箱执行器。"""

    async with transaction() as db:
        await db.execute("DELETE FROM project_members WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM project_access_requests WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM project_teams WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM task_logs WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM plans WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM monitor_events WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM platforms WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM chat_sessions WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM conversation_history WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM agent_events WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    try:
        from cancer_claw.capabilities.toolkit.executor import close_project_executor

        await close_project_executor(project_id)
    except Exception as e:
        logger.warning("project_sandbox_close_error", id=project_id, error=str(e))
```

- [ ] **Step 4: 重构 projects.py 的删除路由**

修改 `cancer_claw/interfaces/routes/projects.py`，将 `delete_project` 函数体整体替换为：

```python
@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(ctx: dict = Depends(require_project_manage)):

    project_id = ctx["project_id"]
    from cancer_claw.services.projects.service import (
        cancel_project_runs,
        delete_project_full,
    )

    await cancel_project_runs(project_id)
    await delete_project_full(project_id)
    logger.info("project_deleted", id=project_id)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_project_service.py -v`

Expected: PASS（3 passed）

- [ ] **Step 6: Commit**

```bash
git add cancer_claw/services/projects cancer_claw/interfaces/routes/projects.py tests/test_project_service.py
git commit -m "feat(projects): extract shared project status and delete service"
```

---

### Task 3: 运行守卫（冻结写保护 + 禁止新推理）

**Files:**
- Modify: `cancer_claw/services/identity/deps.py`
- Modify: `cancer_claw/interfaces/routes/chat.py`
- Test: `tests/test_project_guards.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_project_guards.py`：

```python
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
    ah = {"Authorization": f"Bearer {admin['access_token']}"}
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
```

注意：`test_paused_blocks_chat_but_allows_patch` 中 PATCH 只写 name/description，不会触发 billing。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_project_guards.py -v`

Expected: FAIL — frozen 时 PATCH 返回 200（守卫未实现）

- [ ] **Step 3: 实现 deps.py 守卫**

修改 `cancer_claw/services/identity/deps.py`：

1) `_load_project` 查询增加 status 列：

```python
async def _load_project(project_id: str) -> dict[str, Any] | None:

    db = await get_read_db()
    cur = await db.execute(
        "SELECT id, owner_id, COALESCE(status, 'active') FROM projects WHERE id = ?",
        (project_id,),
    )
    row = await cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "owner_id": row[1], "status": row[2]}
```

2) `_resolve_access` 中、`need == "manage"` 检查之后增加冻结写保护：

```python
    if need == "write" and project.get("status") == "frozen" and not is_admin(user):
        raise HTTPException(status_code=403, detail="项目已冻结，仅管理员可操作")
```

3) 文件末尾新增依赖：

```python
async def require_project_runnable(
    project_id: str, user: dict[str, Any] = Depends(get_current_user)
) -> ProjectContext:

    ctx = await _resolve_access(project_id, user, need="write")
    status = ctx["project"].get("status") or "active"
    if status in ("paused", "frozen"):
        raise HTTPException(status_code=403, detail="项目已暂停或冻结，无法发起新的运行")
    return ctx
```

- [ ] **Step 4: 实现 chat.py 守卫**

修改 `cancer_claw/interfaces/routes/chat.py`：

1) 在 `from cancer_claw.services.identity.deps import (...)` 中增加 `require_project_runnable`：

```python
from cancer_claw.services.identity.deps import (
    compute_project_role,
    get_current_user,
    is_admin,
    require_project_read,
    require_project_runnable,
    require_project_write,
)
```

2) `chat_stream` 的依赖改为运行守卫：

```python
@router.post("/projects/{project_id}/chat")
async def chat_stream(
    project_id: str,
    body: ChatRequest,
    ctx: dict = Depends(require_project_runnable),
):
```

3) `chat_sync` 中、项目角色检查之后增加状态检查：

```python
        if (_project.get("status") or "active") in ("paused", "frozen"):
            raise HTTPException(status_code=403, detail="项目已暂停或冻结，无法发起新的运行")
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_project_guards.py -v`

Expected: PASS（2 passed）

- [ ] **Step 6: 回归运行全部后端测试**

Run: `python -m pytest -v`

Expected: 全部 PASS（新增 + 原有用例）

- [ ] **Step 7: Commit**

```bash
git add cancer_claw/services/identity/deps.py cancer_claw/interfaces/routes/chat.py tests/test_project_guards.py
git commit -m "feat(projects): block new runs when paused/frozen and writes when frozen"
```

---

### Task 4: 管理员项目管理路由

**Files:**
- Create: `cancer_claw/interfaces/routes/admin_projects.py`
- Modify: `cancer_claw/app.py`
- Modify: `cancer_claw/services/identity/permissions.py`
- Test: `tests/test_admin_projects.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_admin_projects.py`：

```python
import asyncio


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


async def test_non_admin_forbidden(client):
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_admin_projects.py -v`

Expected: FAIL — `AssertionError`（/api/admin/projects 返回 404）

- [ ] **Step 3: 实现管理员路由**

创建 `cancer_claw/interfaces/routes/admin_projects.py`：

```python
from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from cancer_claw.db import get_db
from cancer_claw.services.identity.deps import require_admin
from cancer_claw.services.projects.service import (
    PROJECT_STATUS_ACTIVE,
    PROJECT_STATUS_FROZEN,
    PROJECT_STATUS_PAUSED,
    VALID_PROJECT_STATUSES,
    cancel_project_runs,
    delete_project_full,
    get_project_status,
    set_project_status,
)

logger = structlog.get_logger()
router = APIRouter()


class AdminProjectItem(BaseModel):
    id: str
    name: str
    description: str = ""
    workspace_path: str = ""
    owner_id: str | None = None
    owner_username: str = ""
    owner_display_name: str = ""
    status: str = "active"
    running: bool = False
    running_sessions: int = 0
    visibility: str = "private"
    created_at: str | None = None
    updated_at: str | None = None


class AdminProjectListResp(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AdminProjectItem]


class ProjectStatusResp(BaseModel):
    project_id: str
    status: str
    cancelled_runs: int = 0


def _validate_date(value: str, label: str) -> None:
    if not value:
        return
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"{label} 必须是 YYYY-MM-DD") from e


async def _running_by_project() -> dict[str, int]:
    from cancer_claw.agent.engine.session_hub import get_session_hub

    hub = get_session_hub()
    out: dict[str, int] = {}
    for sid in await hub.running_session_ids():
        st = await hub.get_status(sid)
        pid = (st or {}).get("project_id")
        if pid:
            out[pid] = out.get(pid, 0) + 1
    return out


@router.get("/admin/projects", response_model=AdminProjectListResp)
async def admin_list_projects(
    q: str = Query("", max_length=100, description="按项目名称模糊搜索"),
    owner: str = Query("", max_length=40, description="按创建者用户名/显示名模糊搜索"),
    date_from: str = Query("", description="创建日期起，YYYY-MM-DD"),
    date_to: str = Query("", description="创建日期止，YYYY-MM-DD"),
    running: bool | None = Query(None, description="true=运行中 / false=未运行"),
    status: str = Query("", max_length=20, description="active / paused / frozen"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _admin: dict = Depends(require_admin),
) -> AdminProjectListResp:

    _validate_date(date_from, "date_from")
    _validate_date(date_to, "date_to")
    if status and status not in VALID_PROJECT_STATUSES:
        raise HTTPException(status_code=400, detail="status 必须是 active / paused / frozen")

    where = ["1=1"]
    params: list = []
    if q:
        where.append("p.name LIKE ?")
        params.append(f"%{q}%")
    if owner:
        where.append("(u.username LIKE ? OR u.display_name LIKE ?)")
        params.extend([f"%{owner}%", f"%{owner}%"])
    if date_from:
        where.append("date(p.created_at) >= ?")
        params.append(date_from)
    if date_to:
        where.append("date(p.created_at) <= ?")
        params.append(date_to)
    if status:
        where.append("p.status = ?")
        params.append(status)

    db = await get_db()
    cur = await db.execute(
        f"""
        SELECT p.id, p.name, COALESCE(p.description, ''), p.workspace_path,
               p.owner_id, COALESCE(u.username, ''), COALESCE(u.display_name, ''),
               COALESCE(p.status, 'active'), COALESCE(p.visibility, 'private'),
               p.created_at, p.updated_at
        FROM projects p
        LEFT JOIN users u ON u.id = p.owner_id
        WHERE {where}
        ORDER BY p.updated_at DESC
        """,
        params,
    )
    rows = await cur.fetchall()

    running_map = await _running_by_project()
    items: list[AdminProjectItem] = []
    for r in rows:
        run_n = running_map.get(r[0], 0)
        if running is True and run_n == 0:
            continue
        if running is False and run_n > 0:
            continue
        items.append(
            AdminProjectItem(
                id=r[0],
                name=r[1],
                description=r[2],
                workspace_path=r[3],
                owner_id=r[4],
                owner_username=r[5],
                owner_display_name=r[6],
                status=r[7],
                visibility=r[8],
                running=run_n > 0,
                running_sessions=run_n,
                created_at=r[9],
                updated_at=r[10],
            )
        )

    total = len(items)
    return AdminProjectListResp(
        total=total,
        limit=limit,
        offset=offset,
        items=items[offset : offset + limit],
    )


async def _require_project(project_id: str) -> None:
    if await get_project_status(project_id) is None:
        raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")


@router.post(
    "/admin/projects/{project_id}/pause",
    response_model=ProjectStatusResp,
)
async def admin_pause_project(
    project_id: str, admin: dict = Depends(require_admin)
) -> ProjectStatusResp:
    await _require_project(project_id)
    cancelled = await cancel_project_runs(project_id)
    await set_project_status(project_id, PROJECT_STATUS_PAUSED, admin)
    logger.info(
        "admin_project_paused",
        project_id=project_id,
        by=admin.get("username"),
        cancelled_runs=cancelled,
    )
    return ProjectStatusResp(
        project_id=project_id,
        status=PROJECT_STATUS_PAUSED,
        cancelled_runs=cancelled,
    )


@router.post(
    "/admin/projects/{project_id}/resume",
    response_model=ProjectStatusResp,
)
async def admin_resume_project(
    project_id: str, admin: dict = Depends(require_admin)
) -> ProjectStatusResp:
    await _require_project(project_id)
    await set_project_status(project_id, PROJECT_STATUS_ACTIVE, admin)
    logger.info(
        "admin_project_resumed",
        project_id=project_id,
        by=admin.get("username"),
    )
    return ProjectStatusResp(project_id=project_id, status=PROJECT_STATUS_ACTIVE)


@router.post(
    "/admin/projects/{project_id}/freeze",
    response_model=ProjectStatusResp,
)
async def admin_freeze_project(
    project_id: str, admin: dict = Depends(require_admin)
) -> ProjectStatusResp:
    await _require_project(project_id)
    cancelled = await cancel_project_runs(project_id)
    await set_project_status(project_id, PROJECT_STATUS_FROZEN, admin)
    logger.info(
        "admin_project_frozen",
        project_id=project_id,
        by=admin.get("username"),
        cancelled_runs=cancelled,
    )
    return ProjectStatusResp(
        project_id=project_id,
        status=PROJECT_STATUS_FROZEN,
        cancelled_runs=cancelled,
    )


@router.post(
    "/admin/projects/{project_id}/unfreeze",
    response_model=ProjectStatusResp,
)
async def admin_unfreeze_project(
    project_id: str, admin: dict = Depends(require_admin)
) -> ProjectStatusResp:
    await _require_project(project_id)
    await set_project_status(project_id, PROJECT_STATUS_ACTIVE, admin)
    logger.info(
        "admin_project_unfrozen",
        project_id=project_id,
        by=admin.get("username"),
    )
    return ProjectStatusResp(project_id=project_id, status=PROJECT_STATUS_ACTIVE)


@router.delete("/admin/projects/{project_id}", status_code=204)
async def admin_delete_project(
    project_id: str, admin: dict = Depends(require_admin)
) -> None:
    await _require_project(project_id)
    await cancel_project_runs(project_id)
    await delete_project_full(project_id)
    logger.info(
        "admin_project_deleted",
        project_id=project_id,
        by=admin.get("username"),
    )
```

- [ ] **Step 4: 挂载路由 + 权限目录**

修改 `cancer_claw/app.py`：

1) 在现有 router import 附近增加：

```python
from cancer_claw.interfaces.routes.admin_projects import router as admin_projects_router
```

2) 在 `projects_router` include 之后增加：

```python
    app.include_router(admin_projects_router, prefix="/api", tags=["项目管理 / 管理员"])
```

修改 `cancer_claw/services/identity/permissions.py`：

1) 在 `MENU_ROLES` 之后增加常量：

```python
MENU_PROJECT_MANAGE = "menu.project_manage"
```

2) 在 `PERMISSION_CATALOG` 的 menu group items 中、`MENU_ROLES` 项之后增加：

```python
            {"key": MENU_PROJECT_MANAGE, "label": "项目管理（管理员）"},
```

注意：该权限不加入 `DEFAULT_USER_PERMISSIONS`，普通角色默认不可见；管理员通过 `checkPermission` 的 admin 分支放行。

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_admin_projects.py -v`

Expected: PASS（5 passed）

- [ ] **Step 6: 回归全部后端测试 + lint**

Run: `python -m pytest -v`

Run: `python -m ruff check cancer_claw tests`

Expected: 全部 PASS；ruff 无报错

- [ ] **Step 7: Commit**

```bash
git add cancer_claw/interfaces/routes/admin_projects.py cancer_claw/app.py cancer_claw/services/identity/permissions.py tests/test_admin_projects.py
git commit -m "feat(admin): add admin project management API with pause/freeze/delete"
```

---

### Task 5: 前端 API 客户端

**Files:**
- Modify: `web/src/client/services/client.ts`

- [ ] **Step 1: 增加类型与方法**

在 `client.ts` 的 `Project` 接口之后增加：

```ts
export interface AdminProject {
  id: string
  name: string
  description: string
  workspace_path: string
  owner_id?: string | null
  owner_username: string
  owner_display_name: string
  status: 'active' | 'paused' | 'frozen'
  running: boolean
  running_sessions: number
  visibility: string
  created_at?: string | null
  updated_at?: string | null
}

export interface AdminProjectStatusResp {
  project_id: string
  status: 'active' | 'paused' | 'frozen'
  cancelled_runs: number
}
```

在 `api` 对象的 `adminGrantProject` 之后增加：

```ts
  adminListProjects: (params?: {
    q?: string
    owner?: string
    date_from?: string
    date_to?: string
    running?: boolean
    status?: '' | 'active' | 'paused' | 'frozen'
    limit?: number
    offset?: number
  }) =>
    http
      .get<{
        total: number
        limit: number
        offset: number
        items: AdminProject[]
      }>('/admin/projects', {
        params: {
          q: params?.q || undefined,
          owner: params?.owner || undefined,
          date_from: params?.date_from || undefined,
          date_to: params?.date_to || undefined,
          running: params?.running,
          status: params?.status || undefined,
          limit: params?.limit ?? undefined,
          offset: params?.offset ?? undefined,
        },
      })
      .then((r) => r.data),
  adminPauseProject: (id: string) =>
    http
      .post<AdminProjectStatusResp>(`/admin/projects/${id}/pause`)
      .then((r) => r.data),
  adminResumeProject: (id: string) =>
    http
      .post<AdminProjectStatusResp>(`/admin/projects/${id}/resume`)
      .then((r) => r.data),
  adminFreezeProject: (id: string) =>
    http
      .post<AdminProjectStatusResp>(`/admin/projects/${id}/freeze`)
      .then((r) => r.data),
  adminUnfreezeProject: (id: string) =>
    http
      .post<AdminProjectStatusResp>(`/admin/projects/${id}/unfreeze`)
      .then((r) => r.data),
  adminDeleteProject: (id: string) =>
    http.delete<void>(`/admin/projects/${id}`).then((r) => r.data),
```

- [ ] **Step 2: 类型检查**

Run: `cd web; npm run typecheck`

Expected: 无类型错误

- [ ] **Step 3: Commit**

```bash
git add web/src/client/services/client.ts
git commit -m "feat(web): add admin project management API client"
```

---

### Task 6: 前端管理页 + 路由 + 导航

**Files:**
- Create: `web/src/ui/views/admin/Projects.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/ui/widgets/Layout/AppLayout.tsx`

- [ ] **Step 1: 实现管理页**

创建 `web/src/ui/views/admin/Projects.tsx`：

```tsx
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ColumnDef } from '@tanstack/react-table'
import { ChevronLeft, ChevronRight, FolderKanban, Pause, Play, Snowflake, Sun, Trash2 } from 'lucide-react'

import { api, type AdminProject } from '@/client/services/client'
import { Button } from '@/ui/widgets/ui/button'
import { Input } from '@/ui/widgets/ui/input'
import { Badge } from '@/ui/widgets/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/ui/widgets/ui/select'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/ui/widgets/ui/alert-dialog'
import { DataTable } from '@/ui/widgets/ui/data-table'
import { toast } from '@/ui/widgets/ui/sonner'
import PageHeader from '@/ui/widgets/common/PageHeader'
import { parseBackendTime } from '@/shared/foundation/utils'

const PAGE_SIZE = 20

function fmtDate(s?: string | null): string {
  if (!s) return '—'
  const ms = parseBackendTime(s)
  if (ms == null) return s
  return new Date(ms).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function StatusBadge({ status }: { status: AdminProject['status'] }) {
  if (status === 'paused') {
    return (
      <Badge variant="outline" className="border-amber-500/40 bg-amber-500/10 text-amber-700">
        已暂停
      </Badge>
    )
  }
  if (status === 'frozen') {
    return (
      <Badge variant="outline" className="border-slate-500/40 bg-slate-500/10 text-slate-600">
        已冻结
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="border-emerald-500/40 bg-emerald-500/10 text-emerald-700">
      正常
    </Badge>
  )
}

export default function AdminProjects() {
  const qc = useQueryClient()
  const [q, setQ] = useState('')
  const [owner, setOwner] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [running, setRunning] = useState<'all' | 'true' | 'false'>('all')
  const [status, setStatus] = useState<'all' | 'active' | 'paused' | 'frozen'>('all')
  const [offset, setOffset] = useState(0)
  const [deleteTarget, setDeleteTarget] = useState<AdminProject | null>(null)

  useEffect(() => {
    setOffset(0)
  }, [q, owner, dateFrom, dateTo, running, status])

  const params = useMemo(
    () => ({
      q: q.trim() || undefined,
      owner: owner.trim() || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      running: running === 'all' ? undefined : running === 'true',
      status: status === 'all' ? undefined : status,
      limit: PAGE_SIZE,
      offset,
    }),
    [q, owner, dateFrom, dateTo, running, status, offset],
  )

  const { data, isLoading } = useQuery({
    queryKey: ['admin-projects', params],
    queryFn: () => api.adminListProjects(params),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['admin-projects'] })

  const changeStatus = useMutation({
    mutationFn: (input: {
      id: string
      action: 'pause' | 'resume' | 'freeze' | 'unfreeze'
    }) => {
      if (input.action === 'pause') return api.adminPauseProject(input.id)
      if (input.action === 'resume') return api.adminResumeProject(input.id)
      if (input.action === 'freeze') return api.adminFreezeProject(input.id)
      return api.adminUnfreezeProject(input.id)
    },
    onSuccess: () => {
      invalidate()
      toast.success('操作成功')
    },
    onError: (err: Error) => toast.error(err.message || '操作失败'),
  })

  const doDelete = useMutation({
    mutationFn: (id: string) => api.adminDeleteProject(id),
    onSuccess: () => {
      invalidate()
      setDeleteTarget(null)
      toast.success('项目已删除')
    },
    onError: (err: Error) => toast.error(err.message || '删除失败'),
  })

  const columns = useMemo<ColumnDef<AdminProject>[]>(
    () => [
      {
        accessorKey: 'name',
        header: '项目',
        cell: ({ row }) => (
          <div className="min-w-0">
            <div className="font-medium text-foreground">{row.original.name}</div>
            <div className="max-w-[260px] truncate text-xs text-muted-foreground">
              {row.original.description || '—'}
            </div>
          </div>
        ),
      },
      {
        accessorKey: 'owner_username',
        header: '创建者',
        cell: ({ row }) =>
          row.original.owner_display_name || row.original.owner_username || '—',
      },
      {
        accessorKey: 'created_at',
        header: '创建时间',
        cell: ({ row }) => fmtDate(row.original.created_at),
      },
      {
        accessorKey: 'status',
        header: '状态',
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      {
        accessorKey: 'running',
        header: '运行中',
        cell: ({ row }) =>
          row.original.running ? (
            <Badge className="gap-1 border-emerald-500/40 bg-emerald-500/10 text-emerald-700">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
              运行中 · {row.original.running_sessions}
            </Badge>
          ) : (
            <span className="text-xs text-muted-foreground">未运行</span>
          ),
      },
      {
        id: 'actions',
        header: '操作',
        cell: ({ row }) => {
          const p = row.original
          return (
            <div className="flex items-center gap-1">
              {p.status === 'active' && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => changeStatus.mutate({ id: p.id, action: 'pause' })}
                >
                  <Pause className="h-3.5 w-3.5" /> 暂停
                </Button>
              )}
              {p.status === 'paused' && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => changeStatus.mutate({ id: p.id, action: 'resume' })}
                >
                  <Play className="h-3.5 w-3.5" /> 恢复
                </Button>
              )}
              {p.status !== 'frozen' && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => changeStatus.mutate({ id: p.id, action: 'freeze' })}
                >
                  <Snowflake className="h-3.5 w-3.5" /> 冻结
                </Button>
              )}
              {p.status === 'frozen' && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => changeStatus.mutate({ id: p.id, action: 'unfreeze' })}
                >
                  <Sun className="h-3.5 w-3.5" /> 解冻
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive"
                onClick={() => setDeleteTarget(p)}
              >
                <Trash2 className="h-3.5 w-3.5" /> 删除
              </Button>
            </div>
          )
        },
      },
    ],
    [changeStatus],
  )

  const total = data?.total ?? 0
  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + PAGE_SIZE, total)
  const canPrev = offset > 0
  const canNext = offset + PAGE_SIZE < total

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4 lg:p-6">
      <PageHeader
        title="项目管理"
        description="查看系统内全部项目，按创建者、日期、名称与运行状态筛选；可暂停运行、冻结或删除项目。"
        icon={FolderKanban}
      />

      <div className="flex flex-wrap items-end gap-3 rounded-lg border bg-card p-3">
        <div className="flex min-w-[180px] flex-col gap-1">
          <label className="text-xs text-muted-foreground">名称</label>
          <Input placeholder="搜索项目名称" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="flex min-w-[140px] flex-col gap-1">
          <label className="text-xs text-muted-foreground">创建者</label>
          <Input
            placeholder="用户名 / 显示名"
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
          />
        </div>
        <div className="flex min-w-[140px] flex-col gap-1">
          <label className="text-xs text-muted-foreground">创建日期从</label>
          <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </div>
        <div className="flex min-w-[140px] flex-col gap-1">
          <label className="text-xs text-muted-foreground">创建日期至</label>
          <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>
        <div className="flex min-w-[130px] flex-col gap-1">
          <label className="text-xs text-muted-foreground">运行状态</label>
          <Select
            value={running}
            onValueChange={(v) => setRunning(v as 'all' | 'true' | 'false')}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部</SelectItem>
              <SelectItem value="true">运行中</SelectItem>
              <SelectItem value="false">未运行</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex min-w-[130px] flex-col gap-1">
          <label className="text-xs text-muted-foreground">项目状态</label>
          <Select
            value={status}
            onValueChange={(v) =>
              setStatus(v as 'all' | 'active' | 'paused' | 'frozen')
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部</SelectItem>
              <SelectItem value="active">正常</SelectItem>
              <SelectItem value="paused">已暂停</SelectItem>
              <SelectItem value="frozen">已冻结</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        <DataTable
          columns={columns}
          data={data?.items ?? []}
          isLoading={isLoading}
          emptyText="暂无匹配的项目"
          pageSize={Math.max(data?.items.length ?? 0, 1)}
        />
        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 text-xs text-muted-foreground">
          <span>
            共 {total} 条 · 第 {from}-{to} 条
          </span>
          <div className="flex gap-1.5">
            <Button
              variant="outline"
              size="sm"
              disabled={!canPrev}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              <ChevronLeft className="h-3.5 w-3.5" /> 上一页
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!canNext}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              下一页 <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>

      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除项目</AlertDialogTitle>
            <AlertDialogDescription>
              确定删除项目「{deleteTarget?.name}」吗？该操作会级联删除成员、会话、历史与日志，且不可恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground"
              onClick={() => deleteTarget && doDelete.mutate(deleteTarget.id)}
            >
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
```

- [ ] **Step 2: 注册路由**

修改 `web/src/App.tsx`：

1) import 区增加：

```tsx
import AdminProjects from './ui/views/admin/Projects'
```

2) 在 `/admin/monitor` 路由之后增加：

```tsx
        <Route
          path="/admin/projects"
          element={
            <RequireAdmin>
              <AdminProjects />
            </RequireAdmin>
          }
        />
```

- [ ] **Step 3: 增加导航项**

修改 `web/src/ui/widgets/Layout/AppLayout.tsx`：

1) 在 lucide-react import 中增加 `FolderKanban`。

2) 在 `ADMIN_NAV_ITEMS` 数组首位增加：

```tsx
  { to: '/admin/projects', label: '项目管理', icon: FolderKanban, desc: '全量项目 / 暂停 / 冻结', perm: 'menu.project_manage' },
```

- [ ] **Step 4: 前端构建验证**

Run: `cd web; npm run typecheck`

Run: `cd web; npm run build`

Expected: 无类型错误；vite build 成功

- [ ] **Step 5: Commit**

```bash
git add web/src/ui/views/admin/Projects.tsx web/src/App.tsx web/src/ui/widgets/Layout/AppLayout.tsx
git commit -m "feat(web): add admin project management page with filters and actions"
```

---

### Task 7: 端到端验证与手工验收

**Files:** 无代码改动

- [ ] **Step 1: 后端全量测试 + lint**

Run: `python -m pytest -v`

Run: `python -m ruff check cancer_claw tests`

Expected: 全部 PASS，ruff 无报错

- [ ] **Step 2: 前端构建**

Run: `cd web; npm run build`

Expected: 构建成功

- [ ] **Step 3: 手工验收清单**

1. 管理员登录 → 侧边栏“系统管理”出现“项目管理”，可看到全部项目（含非本人创建）。
2. 按名称、创建者、创建日期区间、运行状态、项目状态组合筛选，结果与 `total` 一致。
3. 暂停：先在一个项目发起对话（SSE 推理中），管理员点击“暂停”→ 该会话推理停止，列表“运行中”消失；暂停期间该项目发起对话返回 403；点击“恢复”后恢复正常。
4. 冻结：冻结后普通成员 PATCH 项目 / 上传 / 发起对话均 403，读仍正常；管理员“解冻”后恢复。
5. 删除：点击“删除”弹出确认，确认后项目从列表消失，`/api/projects/{id}` 返回 404。
6. 普通用户直接访问 `/admin/projects` 被重定向到 `/chat`，调用 `/api/admin/projects` 返回 403。

- [ ] **Step 4: Commit（如有收尾改动）**

```bash
git add -A
git commit -m "chore(admin): final verification for project management module"
```

---

## Self-Review

**1. Spec coverage**

- 系统管理内新增项目管理模块：Task 6（导航 + 页面 + 路由）。
- 仅管理员访问：Task 4（`require_admin`）+ Task 6（`RequireAdmin` + `menu.project_manage`）。
- 查阅所有项目：Task 4 `GET /admin/projects`（admin 全量查询）。
- 按创建者 / 日期 / 名称 / 是否运行筛选：Task 4（q / owner / date_from / date_to / running）+ Task 6 UI。
- 删除项目：Task 2 共享 `delete_project_full` + Task 4 admin delete + Task 6 删除确认。
- 暂停项目运行：Task 2 `cancel_project_runs` + Task 3 运行守卫 + Task 4 pause/resume + Task 6 按钮。
- 冻结项目：Task 3 冻结写保护 + Task 4 freeze/unfreeze + Task 6 按钮。

**2. Placeholder scan**

- 无 TBD/TODO；每个代码步骤都给出完整代码；每个测试都给出预期输出与精确命令。

**3. Type consistency**

- 状态常量统一使用 `service.py` 中的 `PROJECT_STATUS_ACTIVE / PAUSED / FROZEN`，前端 `AdminProject['status']` 与后端枚举一致。
- `require_project_runnable` 在 deps.py 定义并在 chat.py 使用，命名前后一致。
- `AdminProjectItem` 字段（owner_username / running / running_sessions / status）与前端 `AdminProject` 类型一一对应。

**已知边界（有意为之，非缺陷）**

- `running` 由 SessionHub 实时计算，管理列表在内存中合并后再分页；项目规模极大时可改为“运行中项目集合 + SQL 分页”优化。
- 删除项目不删除磁盘上的 workspace 目录（与现有 `DELETE /projects/{id}` 行为保持一致）；如需清理磁盘，可在后续单独任务中补充 `shutil.rmtree` 并加确认。
- `chat_sync` 无 project_id 时使用主智能体（系统级），不受项目状态影响，符合“项目级暂停/冻结”的范围。
