

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# keep session key stable
import structlog

from cancer_claw.db import get_db, get_read_db
from cancer_claw.capabilities.toolkit.session_history import SESSIONS_DIR_NAME

logger = structlog.get_logger()

def _normalize_content(raw: Any) -> str:

    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts: list[str] = []
        for p in raw:
            if isinstance(p, dict):
                txt = p.get("text") or p.get("content") or ""
                if txt:
                    parts.append(str(txt))
            else:
                parts.append(str(p))
        return " ".join(parts)
    return str(raw)

def _strip_meta_blocks(content: str) -> str:

    while "<env>" in content and "</env>" in content:
        start = content.find("<env>")
        end = content.find("</env>") + len("</env>")
        content = (content[:start] + content[end:]).strip()
    if content.startswith("用户附了以下文件"):
        parts = content.split("\n\n", 1)
        if len(parts) == 2:
            content = parts[1].strip()
    return content

def derive_title_from_messages(messages: list[dict[str, Any]], *, max_len: int = 30) -> str:

    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = _normalize_content(msg.get("content"))
        content = _strip_meta_blocks(content)
        content = content.strip().replace("\n", " ")
        if content:
            return content[:max_len]
    return "新对话"

def derive_preview_from_messages(messages: list[dict[str, Any]], *, max_len: int = 80) -> str:

    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        if msg.get("tool_calls"):
            continue
        content = _normalize_content(msg.get("content"))
        content = content.strip().replace("\n", " ")
        if content:
            return content[:max_len]
    return ""

async def get_session(session_id: str) -> dict[str, Any] | None:

    db = await get_db()
    cursor = await db.execute(
        "SELECT session_id, project_id, agent_id, title, preview, message_count, "
        "tool_calls, status, jsonl_path, created_at, updated_at, ended_at "
        "FROM chat_sessions WHERE session_id = ?",
        (session_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {
        "session_id": row[0],
        "project_id": row[1],
        "agent_id": row[2],
        "title": row[3] or "",
        "preview": row[4] or "",
        "message_count": int(row[5] or 0),
        "tool_calls": int(row[6] or 0),
        "status": row[7] or "active",
        "jsonl_path": row[8] or "",
        "created_at": row[9],
        "updated_at": row[10],
        "ended_at": row[11],
    }

async def list_sessions(
    project_id: str,
    *,
    limit: int = 20,
    offset: int = 0,
    include_archived: bool = False,
) -> list[dict[str, Any]]:


    db = await get_read_db()
    if include_archived:
        sql = (
            "SELECT session_id, project_id, agent_id, title, preview, "
            "message_count, tool_calls, status, jsonl_path, created_at, "
            "updated_at, ended_at "
            "FROM chat_sessions WHERE project_id = ? "
            "ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        )
        params: tuple[Any, ...] = (project_id, limit, offset)
    else:
        sql = (
            "SELECT session_id, project_id, agent_id, title, preview, "
            "message_count, tool_calls, status, jsonl_path, created_at, "
            "updated_at, ended_at "
            "FROM chat_sessions WHERE project_id = ? AND status != 'archived' "
            "ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        )
        params = (project_id, limit, offset)
    cursor = await db.execute(sql, params)
    rows = await cursor.fetchall()
    return [
        {
            "session_id": r[0],
            "project_id": r[1],
            "agent_id": r[2],
            "title": r[3] or "",
            "preview": r[4] or "",
            "message_count": int(r[5] or 0),
            "tool_calls": int(r[6] or 0),
            "status": r[7] or "active",
            "jsonl_path": r[8] or "",
            "created_at": r[9],
            "updated_at": r[10],
            "ended_at": r[11],
        }
        for r in rows
    ]

async def count_sessions(project_id: str, *, include_archived: bool = False) -> int:


    db = await get_read_db()
    if include_archived:
        sql = "SELECT COUNT(*) FROM chat_sessions WHERE project_id = ?"
        params: tuple[Any, ...] = (project_id,)
    else:
        sql = "SELECT COUNT(*) FROM chat_sessions WHERE project_id = ? AND status != 'archived'"
        params = (project_id,)
    cursor = await db.execute(sql, params)
    row = await cursor.fetchone()
    return int(row[0]) if row else 0

async def upsert_session(
    *,
    project_id: str,
    session_id: str,
    agent_id: str = "claw_master",
    title: str | None = None,
    preview: str | None = None,
    message_count: int | None = None,
    tool_calls: int | None = None,
    status: str | None = None,
    jsonl_path: str | None = None,
    ended_at: str | None = None,
) -> dict[str, Any]:

    db = await get_db()
    existing = await get_session(session_id)
    if existing is None:
        await db.execute(
            "INSERT INTO chat_sessions ("
            "session_id, project_id, agent_id, title, preview, "
            "message_count, tool_calls, status, jsonl_path, ended_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                project_id,
                agent_id,
                title or "",
                preview or "",
                message_count or 0,
                tool_calls or 0,
                status or "active",
                jsonl_path or "",
                ended_at,
            ),
        )
        await db.commit()
        logger.info(
            "chat_session_created",
            session_id=session_id,
            project_id=project_id,
            agent_id=agent_id,
        )
        return await get_session(session_id) or {}

    sets: list[str] = []
    params: list[Any] = []
    if title is not None and not (existing.get("title") or "").strip():
        sets.append("title = ?")
        params.append(title)
    if preview is not None:
        sets.append("preview = ?")
        params.append(preview)
    if message_count is not None:
        sets.append("message_count = ?")
        params.append(message_count)
    if tool_calls is not None:
        sets.append("tool_calls = ?")
        params.append(tool_calls)
    if status is not None:
        sets.append("status = ?")
        params.append(status)
    if jsonl_path is not None:
        sets.append("jsonl_path = ?")
        params.append(jsonl_path)
    if ended_at is not None:
        sets.append("ended_at = ?")
        params.append(ended_at)
    sets.append("updated_at = CURRENT_TIMESTAMP")

    if not sets:
        return existing

    sql = f"UPDATE chat_sessions SET {', '.join(sets)} WHERE session_id = ?"
    params.append(session_id)
    await db.execute(sql, params)
    await db.commit()
    return await get_session(session_id) or {}

async def touch_session_on_save(
    *,
    project_id: str,
    session_id: str,
    agent_id: str,
    role: str,
    content: str,
    tool_calls_count: int = 0,
) -> None:

    if not session_id or not project_id:
        return


    derived_title: str | None = None
    derived_preview: str | None = None
    if role == "user":
        stripped = _strip_meta_blocks(content or "").strip().replace("\n", " ")
        if stripped:
            derived_title = stripped[:30]
    elif role == "assistant" and tool_calls_count == 0:

        stripped = (content or "").strip().replace("\n", " ")
        if stripped:
            derived_preview = stripped[:80]

    try:
        db = await get_db()


        await db.execute(
            "INSERT OR IGNORE INTO chat_sessions "
            "(session_id, project_id, agent_id, title, preview, "
            " message_count, tool_calls, status) "
            "VALUES (?, ?, ?, '', '', 0, 0, 'active')",
            (session_id, project_id, agent_id),
        )

        await db.execute(
            """
            UPDATE chat_sessions
            SET message_count = message_count + 1,
                tool_calls = tool_calls + ?,
                updated_at = CURRENT_TIMESTAMP,
                title = CASE
                    WHEN (title IS NULL OR title = '') AND ? IS NOT NULL
                        THEN ?
                    ELSE title
                END,
                preview = CASE
                    WHEN ? IS NOT NULL THEN ?
                    ELSE preview
                END
            WHERE session_id = ?
            """,
            (
                tool_calls_count,
                derived_title, derived_title,
                derived_preview, derived_preview,
                session_id,
            ),
        )
        await db.commit()
    except Exception as e:
        logger.warning(
            "chat_session_index_touch_failed",
            session_id=session_id,
            error=str(e),
        )

async def update_session_title(session_id: str, title: str) -> bool:

    db = await get_db()
    cursor = await db.execute(
        "UPDATE chat_sessions SET title = ?, updated_at = CURRENT_TIMESTAMP "
        "WHERE session_id = ?",
        (title.strip()[:60], session_id),
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0

async def update_session_status(
    session_id: str,
    status: str,
    *,
    ended_at: str | None = None,
) -> bool:

    db = await get_db()
    if ended_at is not None:
        cursor = await db.execute(
            "UPDATE chat_sessions SET status = ?, ended_at = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
            (status, ended_at, session_id),
        )
    else:
        cursor = await db.execute(
            "UPDATE chat_sessions SET status = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE session_id = ?",
            (status, session_id),
        )
    await db.commit()
    return (cursor.rowcount or 0) > 0

async def delete_session_row(session_id: str) -> bool:

    db = await get_db()
    cursor = await db.execute(
        "DELETE FROM chat_sessions WHERE session_id = ?",
        (session_id,),
    )
    await db.commit()
    return (cursor.rowcount or 0) > 0

async def delete_session_full(
    workspace_root: Path | None,
    session_id: str,
) -> dict[str, Any]:

    result: dict[str, Any] = {
        "session_id": session_id,
        "deleted_jsonl": False,
        "deleted_meta": False,
        "deleted_row": False,
        "deleted_history_rows": 0,
    }


    if workspace_root is not None:
        sdir = workspace_root / SESSIONS_DIR_NAME
        jsonl_path = sdir / f"{session_id}.jsonl"
        meta_path = sdir / f"{session_id}.meta.json"
        try:
            if jsonl_path.exists():
                jsonl_path.unlink()
                result["deleted_jsonl"] = True
        except OSError as e:
            logger.warning("session_delete_jsonl_failed", session_id=session_id, error=str(e))
        try:
            if meta_path.exists():
                meta_path.unlink()
                result["deleted_meta"] = True
        except OSError as e:
            logger.warning("session_delete_meta_failed", session_id=session_id, error=str(e))

    try:
        result["deleted_row"] = await delete_session_row(session_id)
    except Exception as e:
        logger.warning("session_delete_row_failed", session_id=session_id, error=str(e))

    try:
        db = await get_db()
        cursor = await db.execute(
            "DELETE FROM conversation_history WHERE session_id = ?",
            (session_id,),
        )


        await db.execute(
            "DELETE FROM agent_events WHERE session_id = ?",
            (session_id,),
        )
        await db.commit()
        result["deleted_history_rows"] = int(cursor.rowcount or 0)
    except Exception as e:
        logger.warning(
            "session_delete_history_failed", session_id=session_id, error=str(e)
        )

    logger.info("session_deleted_full", **result)
    return result

async def _aggregate_session_meta(session_id: str) -> dict[str, Any] | None:

    db = await get_db()
    cursor = await db.execute(
        """
        SELECT id, role, content, tool_calls_json
        FROM conversation_history
        WHERE session_id = ?
        ORDER BY seq IS NULL, seq ASC, created_at ASC, id ASC
        """,
        (session_id,),
    )
    rows = await cursor.fetchall()
    if not rows:
        return None

    title = ""
    preview = ""
    message_count = 0
    tool_calls = 0
    for row in rows:
        role = row[1]
        content = row[2] or ""
        tc_json = row[3]
        if role in ("user", "assistant", "tool", "system"):
            message_count += 1
        if not title and role == "user":
            stripped = _strip_meta_blocks(content).strip().replace("\n", " ")
            if stripped:
                title = stripped[:30]
        if role == "assistant":

            if tc_json:
                try:
                    arr = json.loads(tc_json)
                    if isinstance(arr, list):
                        tool_calls += len(arr)
                except Exception:
                    pass

            if not tc_json and content.strip():
                preview = content.strip().replace("\n", " ")[:80]

    if not title:
        title = "新对话"

    return {
        "title": title,
        "preview": preview,
        "message_count": message_count,
        "tool_calls": tool_calls,
    }

async def sync_from_db(
    *,
    project_id: str,
    session_id: str,
    agent_id: str = "claw_master",
    final_status: str | None = None,
) -> dict[str, Any] | None:

    meta = await _aggregate_session_meta(session_id)
    if meta is None:
        return None

    return await upsert_session(
        project_id=project_id,
        session_id=session_id,
        agent_id=agent_id,
        title=meta["title"] or None,
        preview=meta["preview"],
        message_count=meta["message_count"],
        tool_calls=meta["tool_calls"],
        status=final_status,
    )

async def reconcile_project_sessions(
    workspace_root: Path | None,
    project_id: str,
    *,
    agent_id: str = "claw_master",
) -> int:

    db = await get_db()
    cursor = await db.execute(
        """
        SELECT DISTINCT session_id FROM conversation_history
        WHERE project_id = ? AND session_id IS NOT NULL AND session_id != ''
        """,
        (project_id,),
    )
    rows = await cursor.fetchall()
    sids_in_db = {row[0] for row in rows if row[0]}

    count = 0
    for sid in sids_in_db:
        try:
            result = await sync_from_db(
                project_id=project_id,
                session_id=sid,
                agent_id=agent_id,
            )
            if result is not None:
                count += 1
        except Exception as e:
            logger.warning("session_reconcile_db_failed", session_id=sid, error=str(e))





    if workspace_root is not None:
        sdir = workspace_root / SESSIONS_DIR_NAME
        if sdir.exists():
            for jsonl_path in sdir.glob("*.jsonl"):
                sid = jsonl_path.stem
                if sid in sids_in_db:
                    continue
                try:
                    line_count = 0
                    with jsonl_path.open("r", encoding="utf-8", errors="replace") as fh:
                        for ln in fh:
                            if ln.strip():
                                line_count += 1
                    await upsert_session(
                        project_id=project_id,
                        session_id=sid,
                        agent_id=agent_id,
                        title="（历史会话）",
                        preview="老库 jsonl 残留，消息未迁入 SQLite",
                        message_count=line_count,
                        status="archived",
                        jsonl_path=str(jsonl_path),
                    )
                    count += 1
                except Exception as e:
                    logger.warning(
                        "session_reconcile_jsonl_failed", session_id=sid, error=str(e)
                    )

    logger.info("sessions_reconciled", project_id=project_id, synced=count)
    return count

async def sync_from_jsonl(
    workspace_root: Path,
    project_id: str,
    session_id: str,
    *,
    agent_id: str = "claw_master",
    force_title: bool = False,
) -> dict[str, Any] | None:

    return await sync_from_db(
        project_id=project_id,
        session_id=session_id,
        agent_id=agent_id,
    )
