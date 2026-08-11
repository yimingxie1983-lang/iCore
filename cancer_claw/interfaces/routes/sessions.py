

from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from cancer_claw.services.identity.deps import require_project_read, require_project_write
from cancer_claw.db import get_db
from cancer_claw.agent.recall.session_repo import (
    count_sessions,
    delete_session_full,
    get_session,
    list_sessions,
    reconcile_project_sessions,
    update_session_status,
    update_session_title,
)
from cancer_claw.agent.recall.working import _parse_stored_content
from cancer_claw.capabilities.toolkit.workspace import get_project_workspace_root

logger = structlog.get_logger()
router = APIRouter()

_RECONCILE_MIN_INTERVAL_S = 30.0
_last_reconcile_at: dict[str, float] = {}
_reconcile_inflight: set[str] = set()

class SessionMeta(BaseModel):


    session_id: str
    project_id: str
    agent_id: str
    title: str = ""
    preview: str = ""
    message_count: int = 0
    tool_calls: int = 0
    status: str = "active"
    jsonl_path: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    ended_at: str | None = None

class SessionListResp(BaseModel):


    items: list[SessionMeta] = Field(default_factory=list)
    total: int = Field(0, description="符合过滤条件的总数（不分页）")
    limit: int = 20
    offset: int = 0

class SessionMessage(BaseModel):


    role: str
    content: Any = None
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None

class SessionMessagesResp(BaseModel):


    session_id: str
    total: int = Field(0, description="jsonl 文件总行数（= 消息总数）")
    offset: int = 0
    limit: int = 50
    messages: list[dict] = Field(default_factory=list)

class SessionPatchReq(BaseModel):


    title: str | None = Field(None, description="新标题，1-60 字；为空字符串表示清空")
    status: str | None = Field(
        None,
        description="新状态：active / ended / archived",
    )

class SessionDeleteResp(BaseModel):


    session_id: str
    deleted_jsonl: bool = False
    deleted_meta: bool = False
    deleted_row: bool = False
    deleted_history_rows: int = 0

class ReconcileResp(BaseModel):


    synced: int = Field(0, description="本次扫到并同步的会话数")

async def _assert_project_exists(project_id: str) -> None:

    db = await get_db()
    cur = await db.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
    if not await cur.fetchone():
        raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")

async def _get_session_or_404(project_id: str, session_id: str) -> dict[str, Any]:

    row = await get_session(session_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")
    if row.get("project_id") != project_id:
        raise HTTPException(
            status_code=404,
            detail=f"会话 {session_id} 不属于项目 {project_id}",
        )
    return row

async def _read_messages_from_db(
    session_id: str,
    *,
    offset: int,
    limit: int,
) -> tuple[int, list[dict]]:

    db = await get_db()

    cursor = await db.execute(
        "SELECT COUNT(*) FROM conversation_history WHERE session_id = ?",
        (session_id,),
    )
    row = await cursor.fetchone()
    total = int(row[0]) if row else 0
    if total == 0:
        return 0, []

    cursor = await db.execute(
        """
        SELECT id, role, content, tool_calls_json, tool_call_id, name,
               created_at, seq
        FROM conversation_history
        WHERE session_id = ?
        ORDER BY seq IS NULL, seq ASC, created_at ASC, id ASC
        LIMIT ? OFFSET ?
        """,
        (session_id, limit, offset),
    )
    rows = await cursor.fetchall()

    msgs: list[dict] = []
    for r in rows:
        m = _parse_stored_content(
            r[1],
            r[2] or "",
            tool_calls_json=r[3],
            tool_call_id=r[4],
            name=r[5],
        )

        m["created_at"] = r[6]
        msgs.append(m)
    return total, msgs

@router.get(
    "/projects/{project_id}/sessions",
    response_model=SessionListResp,
    summary="列项目下的会话（按 updated_at 倒序）",
)
async def list_project_sessions(
    project_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_archived: bool = Query(False),
    _ctx: dict = Depends(require_project_read),
) -> SessionListResp:




    try:
        db = await get_db()
        cur = await db.execute(
            """
            SELECT COUNT(DISTINCT session_id) FROM conversation_history
            WHERE project_id = ? AND session_id IS NOT NULL AND session_id != ''
            """,
            (project_id,),
        )
        row1 = await cur.fetchone()
        distinct_in_history = int(row1[0]) if row1 else 0

        cur = await db.execute(
            "SELECT COUNT(*) FROM chat_sessions WHERE project_id = ?",
            (project_id,),
        )
        row2 = await cur.fetchone()
        in_index = int(row2[0]) if row2 else 0

        if distinct_in_history > in_index:
            now = time.monotonic()
            throttled = (now - _last_reconcile_at.get(project_id, 0.0)) < _RECONCILE_MIN_INTERVAL_S
            if project_id in _reconcile_inflight or throttled:


                logger.info(
                    "sessions_auto_reconcile_skipped",
                    project_id=project_id,
                    in_history=distinct_in_history,
                    in_index=in_index,
                    reason="inflight" if project_id in _reconcile_inflight else "throttled",
                )
            else:
                logger.info(
                    "sessions_auto_reconcile",
                    project_id=project_id,
                    in_history=distinct_in_history,
                    in_index=in_index,
                )
                _reconcile_inflight.add(project_id)
                try:
                    ws_root = get_project_workspace_root(project_id)
                except Exception:
                    ws_root = None
                try:
                    await reconcile_project_sessions(ws_root, project_id)
                finally:

                    _last_reconcile_at[project_id] = time.monotonic()
                    _reconcile_inflight.discard(project_id)
    except Exception as e:
        logger.warning("sessions_auto_reconcile_failed", project_id=project_id, error=str(e))

    total = await count_sessions(project_id, include_archived=include_archived)
    rows = await list_sessions(
        project_id,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
    )
    return SessionListResp(
        items=[SessionMeta(**r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )

@router.get(
    "/projects/{project_id}/sessions/{session_id}",
    response_model=SessionMeta,
    summary="取单个会话详情",
)
async def get_session_detail(
    project_id: str,
    session_id: str,
    _ctx: dict = Depends(require_project_read),
) -> SessionMeta:
    row = await _get_session_or_404(project_id, session_id)
    return SessionMeta(**row)

@router.get(
    "/projects/{project_id}/sessions/{session_id}/messages",
    response_model=SessionMessagesResp,
    summary="分页读取会话消息（conversation_history 事实源）",
)
async def get_session_messages(
    project_id: str,
    session_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    _ctx: dict = Depends(require_project_read),
) -> SessionMessagesResp:
    await _get_session_or_404(project_id, session_id)

    total, msgs = await _read_messages_from_db(
        session_id, offset=offset, limit=limit,
    )
    return SessionMessagesResp(
        session_id=session_id,
        total=total,
        offset=offset,
        limit=limit,
        messages=msgs,
    )

@router.get(
    "/projects/{project_id}/sessions/{session_id}/events",
    summary="读取会话的完整事件流（用于刷新后历史回放）",
)
async def get_session_events(
    project_id: str,
    session_id: str,
    after_seq: int = Query(0, ge=0, description="只返回 seq > after_seq 的事件"),
    limit: int = Query(2000, ge=1, le=10000, description="单次返回上限"),
    _ctx: dict = Depends(require_project_read),
) -> dict:

    await _get_session_or_404(project_id, session_id)

    db = await get_db()

    cur = await db.execute(
        "SELECT COUNT(*) FROM agent_events WHERE session_id = ?",
        (session_id,),
    )
    row = await cur.fetchone()
    total = int(row[0]) if row else 0

    cur = await db.execute(
        """
        SELECT seq, type, payload_json, created_at
        FROM agent_events
        WHERE session_id = ? AND seq > ?
        ORDER BY seq ASC
        LIMIT ?
        """,
        (session_id, after_seq, limit),
    )
    rows = await cur.fetchall()

    events: list[dict] = []
    for r in rows:
        try:
            import json as _json
            payload = _json.loads(r[2] or "{}")
        except Exception:
            payload = {}
        events.append({
            "seq": int(r[0]),
            "type": str(r[1] or ""),
            "payload": payload,
            "created_at": float(r[3] or 0.0),
        })

    return {
        "session_id": session_id,
        "total": total,
        "after_seq": after_seq,
        "events": events,
    }

@router.patch(
    "/projects/{project_id}/sessions/{session_id}",
    response_model=SessionMeta,
    summary="改 title 或 status",
)
async def patch_session(
    project_id: str,
    session_id: str,
    req: SessionPatchReq,
    _ctx: dict = Depends(require_project_write),
) -> SessionMeta:
    await _get_session_or_404(project_id, session_id)

    if req.title is None and req.status is None:
        raise HTTPException(status_code=400, detail="至少要传 title 或 status")

    if req.title is not None:
        await update_session_title(session_id, req.title)
    if req.status is not None:
        if req.status not in ("active", "ended", "archived"):
            raise HTTPException(
                status_code=400,
                detail="status 必须是 active / ended / archived 之一",
            )
        await update_session_status(session_id, req.status)

    row = await get_session(session_id)
    if not row:

        raise HTTPException(status_code=500, detail="更新后无法重新读取会话")
    return SessionMeta(**row)

@router.delete(
    "/projects/{project_id}/sessions/{session_id}",
    response_model=SessionDeleteResp,
    summary="物理删除会话（chat_sessions + conversation_history + 残留 jsonl）",
)
async def delete_session(
    project_id: str,
    session_id: str,
    _ctx: dict = Depends(require_project_write),
) -> SessionDeleteResp:








    row = await get_session(session_id)
    if row is None:
        return SessionDeleteResp(session_id=session_id)
    if row.get("project_id") != project_id:
        raise HTTPException(
            status_code=404,
            detail=f"会话 {session_id} 不属于项目 {project_id}",
        )

    try:
        ws_root = get_project_workspace_root(project_id)
    except Exception:
        ws_root = None
    result = await delete_session_full(ws_root, session_id)
    return SessionDeleteResp(**result)

@router.post(
    "/projects/{project_id}/sessions/reconcile",
    response_model=ReconcileResp,
    summary="重建索引：从 conversation_history 聚合元信息到 chat_sessions 表",
)
async def reconcile_sessions(
    project_id: str,
    _ctx: dict = Depends(require_project_write),
) -> ReconcileResp:
    try:
        ws_root = get_project_workspace_root(project_id)
    except Exception:
        ws_root = None
    synced = await reconcile_project_sessions(ws_root, project_id)
    return ReconcileResp(synced=synced)
