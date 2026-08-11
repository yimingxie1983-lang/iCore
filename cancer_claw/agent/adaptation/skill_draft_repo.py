

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from cancer_claw.db import get_db, get_read_db

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

def _row_to_dict(row: Any) -> dict[str, Any]:

    return {
        "id": row[0],
        "name": row[1] or "",
        "content": row[2] or "",
        "source_session_id": row[3],
        "source_agent_id": row[4],
        "project_id": row[5],
        "status": row[6],
        "reviewed_by": row[7],
        "reviewed_at": row[8],
        "skill_path": row[9],
        "created_at": row[10],
        "updated_at": row[11],
    }

_SELECT_COLS = (
    "id, name, content, source_session_id, source_agent_id, project_id, "
    "status, reviewed_by, reviewed_at, skill_path, created_at, updated_at"
)

async def create_draft(
    *,
    name: str,
    content: str,
    source_session_id: str | None = None,
    source_agent_id: str | None = None,
    project_id: str | None = None,
) -> int:

    from cancer_claw.db import insert_returning_id

    db = await get_db()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    return await insert_returning_id(
        db,
        """INSERT INTO skill_drafts
           (name, content, source_session_id, source_agent_id, project_id,
            status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            name,
            content,
            source_session_id,
            source_agent_id,
            project_id,
            STATUS_PENDING,
            now,
            now,
        ),
    )

def _where_and_params(
    status: str | None, search: str | None
) -> tuple[str, list[Any]]:

    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    term = (search or "").strip()
    if term:
        like = f"%{term}%"
        clauses.append("(name LIKE ? OR content LIKE ?)")
        params.extend([like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params

async def list_drafts(
    *,
    status: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:

    db = await get_read_db()
    where, params = _where_and_params(status, search)
    sql = (
        f"SELECT {_SELECT_COLS} FROM skill_drafts {where} "
        "ORDER BY created_at DESC LIMIT ? OFFSET ?"
    )
    cur = await db.execute(sql, tuple(params) + (limit, offset))
    rows = await cur.fetchall()
    return [_row_to_dict(r) for r in rows]

async def count_drafts(
    *, status: str | None = None, search: str | None = None
) -> int:

    db = await get_read_db()
    where, params = _where_and_params(status, search)
    cur = await db.execute(
        f"SELECT COUNT(*) FROM skill_drafts {where}", tuple(params)
    )
    row = await cur.fetchone()
    return int(row[0]) if row else 0

async def get_draft(draft_id: int) -> dict[str, Any] | None:

    db = await get_read_db()
    cur = await db.execute(
        f"SELECT {_SELECT_COLS} FROM skill_drafts WHERE id = ?", (draft_id,)
    )
    row = await cur.fetchone()
    return _row_to_dict(row) if row else None

async def update_draft_content(
    draft_id: int, *, name: str | None = None, content: str | None = None
) -> bool:

    sets: list[str] = []
    params: list[Any] = []
    if name is not None:
        sets.append("name = ?")
        params.append(name)
    if content is not None:
        sets.append("content = ?")
        params.append(content)
    if not sets:
        return False
    sets.append("updated_at = ?")
    params.append(datetime.now(timezone.utc).isoformat(timespec="seconds"))
    params.append(draft_id)

    db = await get_db()
    cur = await db.execute(
        f"UPDATE skill_drafts SET {', '.join(sets)} "
        "WHERE id = ? AND status = 'pending'",
        tuple(params),
    )
    await db.commit()
    return cur.rowcount > 0

async def mark_reviewed(
    draft_id: int,
    *,
    status: str,
    reviewed_by: str,
    skill_path: str | None = None,
) -> bool:

    db = await get_db()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = await db.execute(
        """UPDATE skill_drafts
           SET status = ?, reviewed_by = ?, reviewed_at = ?, skill_path = ?, updated_at = ?
           WHERE id = ?""",
        (status, reviewed_by, now, skill_path, now, draft_id),
    )
    await db.commit()
    return cur.rowcount > 0
