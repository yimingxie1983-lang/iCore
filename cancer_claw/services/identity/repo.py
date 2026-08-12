

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from cancer_claw.db import get_db, get_read_db
from cancer_claw.services.identity.security import hash_password

ROLE_ADMIN = "admin"
ROLE_USER = "user"
VALID_ROLES = (ROLE_ADMIN, ROLE_USER)

MEMBER_EDITOR = "editor"
MEMBER_VIEWER = "viewer"
VALID_MEMBER_ROLES = (MEMBER_EDITOR, MEMBER_VIEWER)

_USER_PUBLIC_COLS = (
    "id, username, email, display_name, role, status, "
    "COALESCE(credits_balance, 0), created_at, updated_at, "
    "COALESCE(email_verified, 0), COALESCE(token_version, 0)"
)

def _row_to_user(row: Any) -> dict[str, Any]:
    return {
        "id": row[0],
        "username": row[1],
        "email": row[2] or "",
        "display_name": row[3] or "",
        "role": row[4],
        "status": row[5],
        "credits_balance": int(row[6] or 0),
        "created_at": row[7],
        "updated_at": row[8],
        "email_verified": bool(row[9]),
        "token_version": int(row[10] or 0),
    }

async def count_users() -> int:
    db = await get_db()
    cur = await db.execute("SELECT COUNT(*) FROM users")
    row = await cur.fetchone()
    return int(row[0]) if row else 0

async def get_user_by_id(user_id: str) -> dict[str, Any] | None:

    db = await get_read_db()
    cur = await db.execute(
        f"SELECT {_USER_PUBLIC_COLS} FROM users WHERE id = ?", (user_id,)
    )
    row = await cur.fetchone()
    return _row_to_user(row) if row else None

async def get_user_by_username(username: str) -> dict[str, Any] | None:
    db = await get_db()
    cur = await db.execute(
        f"SELECT {_USER_PUBLIC_COLS} FROM users WHERE username = ?", (username,)
    )
    row = await cur.fetchone()
    return _row_to_user(row) if row else None

async def get_user_with_hash(username: str) -> dict[str, Any] | None:

    db = await get_db()
    cur = await db.execute(
        f"SELECT {_USER_PUBLIC_COLS}, password_hash FROM users WHERE username = ?",
        (username,),
    )
    row = await cur.fetchone()
    if not row:
        return None
    user = _row_to_user(row)

    user["password_hash"] = row[11]
    return user

async def list_users() -> list[dict[str, Any]]:
    db = await get_db()
    cur = await db.execute(
        f"SELECT {_USER_PUBLIC_COLS} FROM users ORDER BY created_at ASC"
    )
    rows = await cur.fetchall()
    return [_row_to_user(r) for r in rows]

async def create_user(
    *,
    username: str,
    password: str,
    role: str = ROLE_USER,
    email: str = "",
    display_name: str = "",
) -> dict[str, Any]:

    if role not in VALID_ROLES:
        raise ValueError(f"非法角色: {role}")
    db = await get_db()
    uid = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    pwd_hash = hash_password(password)
    await db.execute(
        """INSERT INTO users
           (id, username, email, display_name, password_hash, role, status,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
        (uid, username, email, display_name or username, pwd_hash, role, now, now),
    )
    await db.commit()
    user = await get_user_by_id(uid)
    assert user is not None
    return user

async def update_user(
    user_id: str,
    *,
    email: str | None = None,
    display_name: str | None = None,
    role: str | None = None,
    status: str | None = None,
    password: str | None = None,
) -> dict[str, Any] | None:

    sets: list[str] = []
    params: list[Any] = []
    if email is not None:
        sets.append("email = ?")
        params.append(email)
    if display_name is not None:
        sets.append("display_name = ?")
        params.append(display_name)
    if role is not None:
        if role not in VALID_ROLES:
            raise ValueError(f"非法角色: {role}")
        sets.append("role = ?")
        params.append(role)
    if status is not None:
        if status not in ("active", "disabled"):
            raise ValueError(f"非法状态: {status}")
        sets.append("status = ?")
        params.append(status)
    if password:
        sets.append("password_hash = ?")
        params.append(hash_password(password))
        sets.append("token_version = COALESCE(token_version, 0) + 1")

    if not sets:
        return await get_user_by_id(user_id)

    sets.append("updated_at = ?")
    params.append(datetime.now(timezone.utc).isoformat())
    params.append(user_id)

    db = await get_db()
    await db.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", params)
    await db.commit()
    return await get_user_by_id(user_id)

async def delete_user(user_id: str) -> None:
    db = await get_db()
    await db.execute("DELETE FROM project_members WHERE user_id = ?", (user_id,))
    await db.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
    await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    await db.commit()

async def get_user_by_email(email: str) -> dict[str, Any] | None:

    if not email or not email.strip():
        return None
    db = await get_read_db()
    cur = await db.execute(
        f"SELECT {_USER_PUBLIC_COLS} FROM users WHERE email = ? COLLATE NOCASE",
        (email.strip(),),
    )
    row = await cur.fetchone()
    return _row_to_user(row) if row else None

async def get_user_by_username_or_email(
    username: str, email: str = ""
) -> dict[str, Any] | None:

    if email and email.strip():
        found = await get_user_by_email(email)
        if found:
            return found
    return await get_user_by_username(username)

async def bump_token_version(user_id: str) -> int:

    db = await get_db()
    await db.execute(
        "UPDATE users SET token_version = COALESCE(token_version, 0) + 1, "
        "updated_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), user_id),
    )
    await db.commit()
    cur = await db.execute(
        "SELECT COALESCE(token_version, 0) FROM users WHERE id = ?", (user_id,)
    )
    row = await cur.fetchone()
    return int(row[0]) if row else 0

async def update_password(user_id: str, password: str) -> dict[str, Any] | None:

    db = await get_db()
    await db.execute(
        "UPDATE users SET password_hash = ?, "
        "token_version = COALESCE(token_version, 0) + 1, updated_at = ? "
        "WHERE id = ?",
        (hash_password(password), datetime.now(timezone.utc).isoformat(), user_id),
    )
    await db.commit()
    return await get_user_by_id(user_id)

async def set_email_verified(user_id: str) -> None:

    db = await get_db()
    await db.execute(
        "UPDATE users SET email_verified = 1, updated_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), user_id),
    )
    await db.commit()

async def create_auth_token(
    user_id: str, kind: str, token_hash: str, expires_at: datetime
) -> None:

    db = await get_db()
    await db.execute(
        """INSERT INTO auth_tokens (user_id, kind, token_hash, expires_at, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            user_id,
            kind,
            token_hash,
            expires_at.isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    await db.commit()

async def consume_auth_token(token_hash: str, kind: str) -> str | None:

    db = await get_db()
    cur = await db.execute(
        """SELECT user_id FROM auth_tokens
           WHERE token_hash = ? AND kind = ? AND used_at IS NULL
             AND expires_at > ?""",
        (token_hash, kind, datetime.now(timezone.utc).isoformat()),
    )
    row = await cur.fetchone()
    if not row:
        return None
    await db.execute(
        "UPDATE auth_tokens SET used_at = ? WHERE token_hash = ?",
        (datetime.now(timezone.utc).isoformat(), token_hash),
    )
    await db.commit()
    return str(row[0])

async def record_auth_event(
    user_id: str | None,
    username: str,
    event_type: str,
    ip: str = "",
    detail: str = "",
) -> None:

    db = await get_db()
    await db.execute(
        """INSERT INTO auth_events (user_id, username, event_type, ip, detail, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            username or "",
            event_type,
            ip or "",
            detail or "",
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    await db.commit()


_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _like_pattern(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _normalize_start(v: str) -> str:
    return f"{v}T00:00:00" if _DATE_ONLY_RE.match(v) else v


def _normalize_end(v: str) -> str:
    return f"{v}T23:59:59.999999" if _DATE_ONLY_RE.match(v) else v


def _auth_events_where(
    username: str = "",
    event_type: str = "",
    ip: str = "",
    detail: str = "",
    start: str = "",
    end: str = "",
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if username:
        clauses.append("username LIKE ? ESCAPE '\\'")
        params.append(_like_pattern(username))
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    if ip:
        clauses.append("ip LIKE ? ESCAPE '\\'")
        params.append(_like_pattern(ip))
    if detail:
        clauses.append("detail LIKE ? ESCAPE '\\'")
        params.append(_like_pattern(detail))
    if start:
        clauses.append("created_at >= ?")
        params.append(_normalize_start(start))
    if end:
        clauses.append("created_at <= ?")
        params.append(_normalize_end(end))
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


async def list_auth_events(
    limit: int | None = 50,
    offset: int = 0,
    username: str = "",
    event_type: str = "",
    ip: str = "",
    detail: str = "",
    start: str = "",
    end: str = "",
) -> tuple[int, list[dict[str, Any]]]:

    db = await get_db()
    where, params = _auth_events_where(
        username=username,
        event_type=event_type,
        ip=ip,
        detail=detail,
        start=start,
        end=end,
    )
    cur = await db.execute(f"SELECT COUNT(*) FROM auth_events{where}", params)
    total = int((await cur.fetchone())[0])
    sql = (
        "SELECT id, user_id, username, event_type, ip, detail, created_at"
        f" FROM auth_events{where} ORDER BY id DESC"
    )
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = [*params, limit, offset]
    cur = await db.execute(sql, params)
    rows = await cur.fetchall()
    items = [
        {
            "id": r[0],
            "user_id": r[1],
            "username": r[2] or "",
            "event_type": r[3],
            "ip": r[4] or "",
            "detail": r[5] or "",
            "created_at": r[6],
        }
        for r in rows
    ]
    return total, items

async def add_or_update_member(
    project_id: str, user_id: str, role: str = MEMBER_EDITOR
) -> None:
    if role not in VALID_MEMBER_ROLES:
        raise ValueError(f"非法成员角色: {role}")
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO project_members (project_id, user_id, role, created_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(project_id, user_id) DO UPDATE SET role = excluded.role""",
        (project_id, user_id, role, now),
    )
    await db.commit()

async def remove_member(project_id: str, user_id: str) -> None:
    db = await get_db()
    await db.execute(
        "DELETE FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    )
    await db.commit()

async def get_member_role(project_id: str, user_id: str) -> str | None:

    db = await get_read_db()
    cur = await db.execute(
        "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    )
    row = await cur.fetchone()
    return row[0] if row else None

async def list_members(project_id: str) -> list[dict[str, Any]]:

    db = await get_db()
    cur = await db.execute(
        """SELECT pm.user_id, pm.role, u.username, u.display_name, pm.created_at
           FROM project_members pm
           JOIN users u ON u.id = pm.user_id
           WHERE pm.project_id = ?
           ORDER BY pm.created_at ASC""",
        (project_id,),
    )
    rows = await cur.fetchall()
    return [
        {
            "user_id": r[0],
            "role": r[1],
            "username": r[2],
            "display_name": r[3] or r[2],
            "created_at": r[4],
        }
        for r in rows
    ]

def _row_to_role(row: Any, perms: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": row[0],
        "name": row[1],
        "description": row[2] or "",
        "is_system": bool(row[3]),
        "created_at": row[4],
        "updated_at": row[5],
        "permissions": perms or [],
    }

async def list_roles() -> list[dict[str, Any]]:

    db = await get_db()
    cur = await db.execute(
        "SELECT id, name, description, is_system, created_at, updated_at "
        "FROM roles ORDER BY is_system DESC, created_at ASC"
    )
    rows = await cur.fetchall()
    cur2 = await db.execute("SELECT role_id, perm_key FROM role_permissions")
    perm_rows = await cur2.fetchall()
    perm_map: dict[str, list[str]] = {}
    for rid, pkey in perm_rows:
        perm_map.setdefault(rid, []).append(pkey)
    return [_row_to_role(r, sorted(perm_map.get(r[0], []))) for r in rows]

async def get_role(role_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cur = await db.execute(
        "SELECT id, name, description, is_system, created_at, updated_at "
        "FROM roles WHERE id = ?",
        (role_id,),
    )
    row = await cur.fetchone()
    if not row:
        return None
    cur2 = await db.execute(
        "SELECT perm_key FROM role_permissions WHERE role_id = ?", (role_id,)
    )
    perms = [r[0] for r in await cur2.fetchall()]
    return _row_to_role(row, sorted(perms))

async def get_role_by_name(name: str) -> dict[str, Any] | None:
    db = await get_db()
    cur = await db.execute(
        "SELECT id, name, description, is_system, created_at, updated_at "
        "FROM roles WHERE name = ?",
        (name,),
    )
    row = await cur.fetchone()
    return _row_to_role(row) if row else None

async def create_role(
    *,
    name: str,
    description: str = "",
    permissions: list[str] | None = None,
    is_system: bool = False,
    role_id: str | None = None,
) -> dict[str, Any]:
    db = await get_db()
    rid = role_id or uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO roles (id, name, description, is_system, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (rid, name, description, 1 if is_system else 0, now, now),
    )
    for pkey in permissions or []:
        await db.execute(
            "INSERT OR IGNORE INTO role_permissions (role_id, perm_key) VALUES (?, ?)",
            (rid, pkey),
        )
    await db.commit()
    role = await get_role(rid)
    assert role is not None
    return role

async def update_role(
    role_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    permissions: list[str] | None = None,
) -> dict[str, Any] | None:
    db = await get_db()
    sets: list[str] = []
    params: list[Any] = []
    if name is not None:
        sets.append("name = ?")
        params.append(name)
    if description is not None:
        sets.append("description = ?")
        params.append(description)
    if sets:
        sets.append("updated_at = ?")
        params.append(datetime.now(timezone.utc).isoformat())
        params.append(role_id)
        await db.execute(f"UPDATE roles SET {', '.join(sets)} WHERE id = ?", params)

    if permissions is not None:
        await db.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
        for pkey in permissions:
            await db.execute(
                "INSERT OR IGNORE INTO role_permissions (role_id, perm_key) VALUES (?, ?)",
                (role_id, pkey),
            )
    await db.commit()
    return await get_role(role_id)

async def delete_role(role_id: str) -> None:
    db = await get_db()
    await db.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
    await db.execute("DELETE FROM user_roles WHERE role_id = ?", (role_id,))
    await db.execute("DELETE FROM roles WHERE id = ?", (role_id,))
    await db.commit()

async def get_user_role_ids(user_id: str) -> list[str]:
    db = await get_read_db()
    cur = await db.execute(
        "SELECT role_id FROM user_roles WHERE user_id = ?", (user_id,)
    )
    return [r[0] for r in await cur.fetchall()]

async def get_user_roles(user_id: str) -> list[dict[str, Any]]:

    db = await get_db()
    cur = await db.execute(
        """SELECT r.id, r.name FROM user_roles ur
           JOIN roles r ON r.id = ur.role_id
           WHERE ur.user_id = ?
           ORDER BY r.name ASC""",
        (user_id,),
    )
    return [{"id": r[0], "name": r[1]} for r in await cur.fetchall()]

async def set_user_roles(user_id: str, role_ids: list[str]) -> None:

    db = await get_db()
    await db.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
    now = datetime.now(timezone.utc).isoformat()
    for rid in role_ids:
        await db.execute(
            "INSERT OR IGNORE INTO user_roles (user_id, role_id, created_at) VALUES (?, ?, ?)",
            (user_id, rid, now),
        )
    await db.commit()

async def get_effective_permissions(user: dict[str, Any]) -> list[str]:

    from cancer_claw.services.identity import permissions as perms

    if user.get("role") == ROLE_ADMIN:
        return sorted(perms.ALL_PERMISSIONS)

    db = await get_read_db()
    cur = await db.execute(
        """SELECT DISTINCT rp.perm_key
           FROM user_roles ur
           JOIN role_permissions rp ON rp.role_id = ur.role_id
           WHERE ur.user_id = ?""",
        (user["id"],),
    )
    rows = await cur.fetchall()
    if not rows:

        cur2 = await db.execute(
            "SELECT COUNT(*) FROM user_roles WHERE user_id = ?", (user["id"],)
        )
        cnt = (await cur2.fetchone())[0]
        if not cnt:
            return sorted(perms.DEFAULT_USER_PERMISSIONS)
        return []
    return sorted({r[0] for r in rows if r[0] in perms.ALL_PERMISSIONS})

async def find_projects_by_name(
    user: dict[str, Any], query: str, *, limit: int = 10
) -> list[dict[str, Any]]:

    q = (query or "").strip()
    if not q:
        return []
    like = f"%{q}%"
    db = await get_read_db()
    if user.get("role") == ROLE_ADMIN:
        cur = await db.execute(
            """SELECT id, name, 'owner' AS role FROM projects
               WHERE name LIKE ? COLLATE NOCASE
               ORDER BY (name = ? COLLATE NOCASE) DESC, updated_at DESC
               LIMIT ?""",
            (like, q, limit),
        )
    else:
        uid = user["id"]
        cur = await db.execute(
            """SELECT p.id, p.name,
                      CASE WHEN p.owner_id = ? THEN 'owner' ELSE pm.role END AS role
               FROM projects p
               LEFT JOIN project_members pm
                      ON pm.project_id = p.id AND pm.user_id = ?
               WHERE (p.owner_id = ? OR pm.user_id = ?)
                 AND p.name LIKE ? COLLATE NOCASE
               ORDER BY (p.name = ? COLLATE NOCASE) DESC, p.updated_at DESC
               LIMIT ?""",
            (uid, uid, uid, uid, like, q, limit),
        )
    rows = await cur.fetchall()
    return [{"id": r[0], "name": r[1], "role": r[2]} for r in rows]
