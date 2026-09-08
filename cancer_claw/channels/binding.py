"""渠道绑定：微信 peer ↔ iCore 用户 / 项目 / 会话。"""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone
from typing import Any

from cancer_claw.db import get_db

CHANNEL_WECHAT = "wechat"
BIND_CODE_TTL_S = 600


def _as_dict(row: Any, cursor: Any = None) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    keys = getattr(row, "keys", None)
    if callable(keys):
        return {k: row[k] for k in keys()}
    if cursor is not None and getattr(cursor, "description", None):
        cols = [d[0] for d in cursor.description]
        return {cols[i]: row[i] for i in range(min(len(cols), len(row)))}
    return None


async def _fetchone_dict(cur: Any) -> dict[str, Any] | None:
    row = await cur.fetchone()
    return _as_dict(row, cur)


async def _fetchall_dicts(cur: Any) -> list[dict[str, Any]]:
    rows = await cur.fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        d = _as_dict(row, cur)
        if d:
            out.append(d)
    return out


async def create_bind_code(
    *,
    user_id: str,
    project_id: str,
    permissions_mode: str = "ask",
    ttl_seconds: int = BIND_CODE_TTL_S,
) -> dict[str, Any]:
    code = secrets.token_hex(3).upper()  # 6 hex chars
    now = time.time()
    expires_at = now + max(60, int(ttl_seconds))
    db = await get_db()
    await db.execute(
        """INSERT INTO channel_bind_codes
           (code, channel, user_id, project_id, permissions_mode, expires_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            code,
            CHANNEL_WECHAT,
            user_id,
            project_id,
            permissions_mode or "ask",
            expires_at,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    await db.commit()
    return {
        "code": code,
        "channel": CHANNEL_WECHAT,
        "user_id": user_id,
        "project_id": project_id,
        "permissions_mode": permissions_mode or "ask",
        "expires_at": expires_at,
        "expires_in": int(expires_at - now),
    }


async def consume_bind_code(code: str, *, external_scope_id: str) -> dict[str, Any] | None:
    normalized = str(code or "").strip().upper()
    if not normalized:
        return None
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM channel_bind_codes WHERE code = ? AND channel = ?",
        (normalized, CHANNEL_WECHAT),
    )
    row = await cur.fetchone()
    if not row:
        return None
    data = _as_dict(row, cur) or {}
    if float(data.get("expires_at") or 0) < time.time():
        await db.execute("DELETE FROM channel_bind_codes WHERE code = ?", (normalized,))
        await db.commit()
        return None
    if data.get("consumed_at"):
        return None

    now_iso = datetime.now(timezone.utc).isoformat()
    binding = await upsert_binding(
        channel=CHANNEL_WECHAT,
        external_scope_id=external_scope_id,
        user_id=str(data["user_id"]),
        project_id=str(data["project_id"]),
        permissions_mode=str(data.get("permissions_mode") or "ask"),
        session_id=None,
    )
    await db.execute(
        "UPDATE channel_bind_codes SET consumed_at = ?, consumed_by = ? WHERE code = ?",
        (now_iso, external_scope_id, normalized),
    )
    await db.commit()
    return binding


async def upsert_binding(
    *,
    channel: str,
    external_scope_id: str,
    user_id: str,
    project_id: str,
    permissions_mode: str = "ask",
    session_id: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    cur = await db.execute(
        "SELECT id FROM channel_bindings WHERE channel = ? AND external_scope_id = ?",
        (channel, external_scope_id),
    )
    existing = await cur.fetchone()
    if existing:
        existing_d = _as_dict(existing, cur) or {}
        await db.execute(
            """UPDATE channel_bindings
               SET user_id = ?, project_id = ?, permissions_mode = ?,
                   session_id = COALESCE(?, session_id), updated_at = ?
               WHERE channel = ? AND external_scope_id = ?""",
            (
                user_id,
                project_id,
                permissions_mode,
                session_id,
                now,
                channel,
                external_scope_id,
            ),
        )
        binding_id = str(existing_d.get("id") or "")
    else:
        binding_id = secrets.token_hex(8)
        await db.execute(
            """INSERT INTO channel_bindings
               (id, channel, external_scope_id, user_id, project_id, session_id,
                permissions_mode, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                binding_id,
                channel,
                external_scope_id,
                user_id,
                project_id,
                session_id,
                permissions_mode,
                now,
                now,
            ),
        )
    await db.commit()
    return await get_binding(channel, external_scope_id) or {
        "id": binding_id,
        "channel": channel,
        "external_scope_id": external_scope_id,
        "user_id": user_id,
        "project_id": project_id,
        "session_id": session_id,
        "permissions_mode": permissions_mode,
    }


async def get_binding(channel: str, external_scope_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM channel_bindings WHERE channel = ? AND external_scope_id = ?",
        (channel, external_scope_id),
    )
    return await _fetchone_dict(cur)


async def update_binding_session(
    channel: str,
    external_scope_id: str,
    *,
    session_id: str | None = None,
    project_id: str | None = None,
    clear_session: bool = False,
) -> dict[str, Any] | None:
    binding = await get_binding(channel, external_scope_id)
    if not binding:
        return None
    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    new_session = None if clear_session else (session_id if session_id is not None else binding.get("session_id"))
    new_project = project_id or binding.get("project_id")
    await db.execute(
        """UPDATE channel_bindings
           SET session_id = ?, project_id = ?, updated_at = ?
           WHERE channel = ? AND external_scope_id = ?""",
        (new_session, new_project, now, channel, external_scope_id),
    )
    await db.commit()
    return await get_binding(channel, external_scope_id)


async def delete_binding(channel: str, external_scope_id: str) -> bool:
    db = await get_db()
    cur = await db.execute(
        "DELETE FROM channel_bindings WHERE channel = ? AND external_scope_id = ?",
        (channel, external_scope_id),
    )
    await db.commit()
    return (cur.rowcount or 0) > 0


async def list_bindings_for_user(user_id: str, channel: str = CHANNEL_WECHAT) -> list[dict[str, Any]]:
    db = await get_db()
    cur = await db.execute(
        """SELECT * FROM channel_bindings
           WHERE user_id = ? AND channel = ?
           ORDER BY updated_at DESC""",
        (user_id, channel),
    )
    return await _fetchall_dicts(cur)


async def list_bind_codes_for_user(user_id: str, channel: str = CHANNEL_WECHAT) -> list[dict[str, Any]]:
    db = await get_db()
    now = time.time()
    cur = await db.execute(
        """SELECT * FROM channel_bind_codes
           WHERE user_id = ? AND channel = ? AND consumed_at IS NULL AND expires_at > ?
           ORDER BY created_at DESC""",
        (user_id, channel, now),
    )
    return await _fetchall_dicts(cur)
