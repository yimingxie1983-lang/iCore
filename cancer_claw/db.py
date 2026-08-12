

import asyncio
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from cancer_claw.config import settings

import aiosqlite

def _use_postgres() -> bool:
    return settings.database.is_postgres

_PLACEHOLDER_RE = re.compile(r"'(?:[^']|'')*'|\?")

def _convert_sql(sql: str) -> str:

    insert_ignore = False
    m = re.match(r"\s*INSERT\s+OR\s+IGNORE\s+", sql, flags=re.IGNORECASE)
    if m:
        insert_ignore = True
        sql = sql[: m.start()] + "INSERT " + sql[m.end():]


    counter = {"n": 0}

    def _sub(match: "re.Match[str]") -> str:
        tok = match.group(0)
        if tok == "?":
            counter["n"] += 1
            return f"${counter['n']}"
        return tok

    converted = _PLACEHOLDER_RE.sub(_sub, sql)

    if insert_ignore and "on conflict" not in converted.lower():
        low = converted.lower()
        if " returning " in low:
            idx = low.index(" returning ")
            converted = converted[:idx] + " ON CONFLICT DO NOTHING" + converted[idx:]
        else:
            converted = converted.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return converted

def _returns_rows(sql: str) -> bool:
    s = sql.lstrip().lower()
    return s.startswith("select") or s.startswith("with") or " returning " in s

def _status_rowcount(status: str) -> int:

    if not status:
        return 0
    parts = status.split()
    try:
        return int(parts[-1])
    except (ValueError, IndexError):
        return 0

class _PgCursor:


    def __init__(self, rows: list, rowcount: int, lastrowid: Any = None) -> None:
        self._rows = rows
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return list(self._rows)

async def _pg_exec(conn, sql: str, params) -> _PgCursor:
    q = _convert_sql(sql)
    args = list(params) if params else []
    if _returns_rows(sql):
        rows = await conn.fetch(q, *args)
        return _PgCursor(rows, len(rows))
    status = await conn.execute(q, *args)
    return _PgCursor([], _status_rowcount(status))

class _PgConn:


    async def execute(self, sql: str, params=()) -> _PgCursor:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            return await _pg_exec(conn, sql, params)

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None

class _PgTxConn:


    def __init__(self, conn) -> None:
        self._conn = conn

    async def execute(self, sql: str, params=()) -> _PgCursor:
        return await _pg_exec(self._conn, sql, params)

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

_pg_pool = None
_pg_pool_lock: asyncio.Lock | None = None

async def _codec_init(conn) -> None:


    await conn.execute("SET TIME ZONE 'UTC'")

    def _enc(v):
        if v is None:
            return None
        if isinstance(v, str):
            return v
        try:
            return v.isoformat(sep=" ")
        except AttributeError:
            return str(v)

    def _dec(v):
        return v

    for name in ("timestamp", "timestamptz"):
        await conn.set_type_codec(
            name, schema="pg_catalog", encoder=_enc, decoder=_dec, format="text"
        )

def _get_pg_lock() -> asyncio.Lock:
    global _pg_pool_lock
    if _pg_pool_lock is None:
        _pg_pool_lock = asyncio.Lock()
    return _pg_pool_lock

async def _get_pg_pool():
    global _pg_pool
    if _pg_pool is not None:
        return _pg_pool
    async with _get_pg_lock():
        if _pg_pool is not None:
            return _pg_pool
        import asyncpg

        _pg_pool = await asyncpg.create_pool(
            dsn=settings.database.url,
            min_size=max(1, settings.database.pool_min),
            max_size=max(settings.database.pool_min, settings.database.pool_max),
            init=_codec_init,
            command_timeout=60,
        )
        return _pg_pool

_db: "aiosqlite.Connection | None" = None
_read_pool: list = []
_read_pool_idx: int = 0
_read_pool_lock: asyncio.Lock | None = None
_READ_POOL_SIZE = max(1, int(os.environ.get("CANCER_CLAW_DB_READ_POOL", "4") or "4"))

def _get_read_pool_lock() -> asyncio.Lock:
    global _read_pool_lock
    if _read_pool_lock is None:
        _read_pool_lock = asyncio.Lock()
    return _read_pool_lock

async def _init_read_pool() -> None:
    global _read_pool
    async with _get_read_pool_lock():
        if _read_pool:
            return
        db_path = str(Path(settings.database.path))
        pool: list = []
        for _ in range(_READ_POOL_SIZE):
            conn = await aiosqlite.connect(db_path)
            await conn.execute("PRAGMA busy_timeout=5000")
            await conn.execute("PRAGMA query_only=ON")
            await conn.execute("PRAGMA temp_store=MEMORY")
            pool.append(conn)
        _read_pool = pool

async def get_read_db():

    if _use_postgres():
        return _PgConn()
    global _read_pool_idx
    if not _read_pool:
        await _init_read_pool()
    idx = _read_pool_idx % len(_read_pool)
    _read_pool_idx += 1
    return _read_pool[idx]

async def get_db():

    if _use_postgres():

        await _get_pg_pool()
        return _PgConn()
    global _db
    if _db is None:
        await init_db()
    return _db

@asynccontextmanager
async def transaction():

    if _use_postgres():
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            tx = conn.transaction()
            await tx.start()
            try:
                yield _PgTxConn(conn)
            except Exception:
                await tx.rollback()
                raise
            else:
                await tx.commit()
    else:
        db = await get_db()
        try:
            yield db
            await db.commit()
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass
            raise

async def insert_returning_id(conn, sql: str, params=()) -> int:

    if _use_postgres():
        pool = await _get_pg_pool()
        q = _convert_sql(sql)
        if " returning " not in q.lower():
            q = q.rstrip().rstrip(";") + " RETURNING id"
        args = list(params) if params else []
        async with pool.acquire() as c:
            val = await c.fetchval(q, *args)
            return int(val) if val is not None else 0
    cur = await conn.execute(sql, params)
    await conn.commit()
    return int(cur.lastrowid)

async def init_db():

    if _use_postgres():
        pool = await _get_pg_pool()
        await _create_tables_pg(pool)
        return pool


    global _db
    db_path = Path(settings.database.path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(str(db_path))
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")
    await _db.execute("PRAGMA synchronous=NORMAL")
    await _db.execute("PRAGMA busy_timeout=5000")
    await _db.execute("PRAGMA temp_store=MEMORY")
    await _db.execute("PRAGMA wal_autocheckpoint=2000")
    await _create_tables(_db)
    try:
        await _init_read_pool()
    except Exception as e:
        print(f"[db] ⚠ 只读连接池初始化失败（将退化为懒加载）: {e}", flush=True)
    return _db

async def close_db():

    global _db, _read_pool, _pg_pool
    if _pg_pool is not None:
        try:
            await _pg_pool.close()
        except Exception:
            pass
        _pg_pool = None
    if _db:
        await _db.close()
        _db = None
    for conn in _read_pool:
        try:
            await conn.close()
        except Exception:
            pass
    _read_pool = []

def _to_pg_ddl(sql: str) -> str:

    sql = re.sub(
        r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
        "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY",
        sql,
        flags=re.IGNORECASE,
    )
    sql = sql.replace("created_at REAL NOT NULL", "created_at DOUBLE PRECISION NOT NULL")
    sql = re.sub(r"\bTIMESTAMP\b", "TIMESTAMPTZ", sql)
    return sql

_PG_ADD_COLUMNS = [
    ("projects", "owner_id", "TEXT"),
    ("projects", "visibility", "TEXT DEFAULT 'private'"),
    ("projects", "market_default_role", "TEXT DEFAULT 'viewer'"),
    ("projects", "status", "TEXT NOT NULL DEFAULT 'active'"),
    ("projects", "status_changed_at", "TIMESTAMP"),
    ("projects", "status_changed_by", "TEXT"),
    ("users", "credits_balance", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "token_version", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "email_verified", "INTEGER NOT NULL DEFAULT 0"),
    ("conversation_history", "platform_id", "TEXT"),
    ("conversation_history", "session_id", "TEXT"),
    ("conversation_history", "tool_calls_json", "TEXT"),
    ("conversation_history", "tool_call_id", "TEXT"),
    ("conversation_history", "name", "TEXT"),
    ("conversation_history", "seq", "INTEGER"),
]

async def _create_tables_pg(pool) -> None:

    async with pool.acquire() as conn:
        async with conn.transaction():
            for schema in _TABLE_SCHEMAS:
                await conn.execute(_to_pg_ddl(schema))
            for table, column, coltype in _PG_ADD_COLUMNS:
                try:
                    await conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype}"
                    )
                except Exception as e:
                    print(f"[db_migrate_pg] ⚠ skip ALTER {table}.{column}: {e}", flush=True)
            for index in _INDEX_SCHEMAS:
                await conn.execute(index)

_TABLE_SCHEMAS = [








    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        email TEXT DEFAULT '',
        display_name TEXT DEFAULT '',
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        status TEXT NOT NULL DEFAULT 'active',
        credits_balance INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,






    """
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL DEFAULT '',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,




    """
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
    """,






    """
    CREATE TABLE IF NOT EXISTS project_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'editor',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (project_id, user_id),
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )
    """,







    """
    CREATE TABLE IF NOT EXISTS roles (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        description TEXT DEFAULT '',
        is_system INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,




    """
    CREATE TABLE IF NOT EXISTS role_permissions (
        role_id TEXT NOT NULL,
        perm_key TEXT NOT NULL,
        PRIMARY KEY (role_id, perm_key),
        FOREIGN KEY (role_id) REFERENCES roles(id)
    )
    """,



    """
    CREATE TABLE IF NOT EXISTS user_roles (
        user_id TEXT NOT NULL,
        role_id TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, role_id),
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (role_id) REFERENCES roles(id)
    )
    """,







    """
    CREATE TABLE IF NOT EXISTS project_access_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL,
        requester_id TEXT NOT NULL,
        requested_role TEXT NOT NULL DEFAULT 'viewer',
        status TEXT NOT NULL DEFAULT 'pending',
        note TEXT DEFAULT '',
        decided_by TEXT,
        decided_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )
    """,





    """
    CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        soul_path TEXT,
        craft_ids TEXT DEFAULT '[]',
        source TEXT NOT NULL DEFAULT 'user_created',
        status TEXT DEFAULT 'idle',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,






    """
    CREATE TABLE IF NOT EXISTS pipelines (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        version TEXT DEFAULT '1.0.0',
        steps TEXT NOT NULL DEFAULT '[]',
        certification_status TEXT DEFAULT 'uncertified',
        origin_type TEXT DEFAULT 'user_created',
        certified_by TEXT,
        certified_at TIMESTAMP,
        author TEXT DEFAULT 'user',
        enabled INTEGER DEFAULT 1,
        run_count INTEGER DEFAULT 0,
        success_rate REAL DEFAULT 0.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,








    """
    CREATE TABLE IF NOT EXISTS craft_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        craft_id TEXT NOT NULL,
        craft_version INTEGER NOT NULL,
        project_id TEXT,
        task_description TEXT,
        success INTEGER,
        quality_score REAL,
        token_used INTEGER,
        feedback_text TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,








    """
    CREATE TABLE IF NOT EXISTS tools (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        function_schema TEXT NOT NULL,
        implementation TEXT NOT NULL,
        enabled INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,





    """
    CREATE TABLE IF NOT EXISTS plans (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        task_description TEXT NOT NULL,
        analysis TEXT DEFAULT '',
        steps TEXT NOT NULL DEFAULT '[]',
        assigned_agents TEXT DEFAULT '{}',
        assigned_pipelines TEXT DEFAULT '{}',
        status TEXT DEFAULT 'draft',
        created_by TEXT,
        approved_by TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )
    """,




    """
    CREATE TABLE IF NOT EXISTS task_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL,
        agent_id TEXT,
        pipeline_id TEXT,
        task_type TEXT,
        input_summary TEXT,
        output_summary TEXT,
        status TEXT DEFAULT 'running',
        tokens_used INTEGER DEFAULT 0,
        duration_ms INTEGER DEFAULT 0,
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )
    """,




    """
    CREATE TABLE IF NOT EXISTS project_teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        role TEXT DEFAULT '',
        assigned_modules TEXT DEFAULT '[]',
        assigned_pipelines TEXT DEFAULT '[]',
        status TEXT DEFAULT 'assigned',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id),
        FOREIGN KEY (agent_id) REFERENCES agents(id)
    )
    """,




    """
    CREATE TABLE IF NOT EXISTS monitor_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL,
        agent_id TEXT,
        event_type TEXT NOT NULL,
        detail TEXT DEFAULT '{}',
        tokens_delta INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )
    """,























    """
    CREATE TABLE IF NOT EXISTS conversation_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT DEFAULT '',
        tool_calls_json TEXT,
        tool_call_id TEXT,
        name TEXT,
        seq INTEGER,
        platform_id TEXT,
        session_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,







    """
    CREATE TABLE IF NOT EXISTS platforms (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        name TEXT NOT NULL,
        embed_url TEXT DEFAULT '',
        description TEXT DEFAULT '',
        capabilities TEXT DEFAULT '[]',
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )
    """,













    """
    CREATE TABLE IF NOT EXISTS chat_sessions (
        session_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        agent_id TEXT NOT NULL DEFAULT 'claw_master',
        title TEXT DEFAULT '',
        preview TEXT DEFAULT '',
        message_count INTEGER DEFAULT 0,
        tool_calls INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active',
        jsonl_path TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ended_at TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )
    """,













    """
    CREATE TABLE IF NOT EXISTS agent_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        project_id TEXT,
        agent_id TEXT DEFAULT 'claw_master',
        seq INTEGER NOT NULL,
        type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at REAL NOT NULL
    )
    """,












    """
    CREATE TABLE IF NOT EXISTS skill_drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT DEFAULT '',
        content TEXT NOT NULL,
        source_session_id TEXT,
        source_agent_id TEXT,
        project_id TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        reviewed_by TEXT,
        reviewed_at TIMESTAMP,
        skill_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,




















    """
    CREATE TABLE IF NOT EXISTS credit_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        type TEXT NOT NULL,
        amount INTEGER NOT NULL,
        balance_after INTEGER NOT NULL,
        reason TEXT DEFAULT '',
        operator_id TEXT,
        session_id TEXT,
        project_id TEXT,
        model TEXT,
        input_tokens INTEGER DEFAULT 0,
        cached_input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        cost_micro_cny INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """,


    """
    CREATE TABLE IF NOT EXISTS auth_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        expires_at TIMESTAMP NOT NULL,
        used_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """,


    """
    CREATE TABLE IF NOT EXISTS auth_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        username TEXT DEFAULT '',
        event_type TEXT NOT NULL,
        ip TEXT DEFAULT '',
        detail TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,

]

_INDEX_SCHEMAS = [

    "CREATE INDEX IF NOT EXISTS idx_task_logs_project ON task_logs(project_id)",

    "CREATE INDEX IF NOT EXISTS idx_task_logs_agent ON task_logs(agent_id)",

    "CREATE INDEX IF NOT EXISTS idx_craft_feedback_craft ON craft_feedback(craft_id)",

    "CREATE INDEX IF NOT EXISTS idx_plans_project ON plans(project_id)",

    "CREATE INDEX IF NOT EXISTS idx_project_teams_project ON project_teams(project_id)",

    "CREATE INDEX IF NOT EXISTS idx_monitor_events_project ON monitor_events(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_monitor_events_agent ON monitor_events(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_monitor_events_type ON monitor_events(event_type)",

    "CREATE INDEX IF NOT EXISTS idx_conv_history_pa ON conversation_history(project_id, agent_id, created_at DESC)",

    "CREATE INDEX IF NOT EXISTS idx_conv_history_pp ON conversation_history(project_id, platform_id, id DESC)",

    "CREATE INDEX IF NOT EXISTS idx_conv_history_session ON conversation_history(session_id, id ASC)",

    "CREATE INDEX IF NOT EXISTS idx_conv_history_session_seq ON conversation_history(session_id, seq ASC)",

    "CREATE INDEX IF NOT EXISTS idx_platforms_project ON platforms(project_id, status)",

    "CREATE INDEX IF NOT EXISTS idx_chat_sessions_project ON chat_sessions(project_id, updated_at DESC)",

    "CREATE INDEX IF NOT EXISTS idx_chat_sessions_status ON chat_sessions(project_id, status, updated_at DESC)",

    "CREATE INDEX IF NOT EXISTS idx_agent_events_session_seq ON agent_events(session_id, seq ASC)",

    "CREATE INDEX IF NOT EXISTS idx_agent_events_project ON agent_events(project_id, created_at DESC)",

    "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",

    "CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(owner_id, updated_at DESC)",

    "CREATE INDEX IF NOT EXISTS idx_project_members_user ON project_members(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_project_members_project ON project_members(project_id)",

    "CREATE INDEX IF NOT EXISTS idx_role_permissions_role ON role_permissions(role_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role_id)",

    "CREATE INDEX IF NOT EXISTS idx_projects_visibility ON projects(visibility, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)",
    "CREATE INDEX IF NOT EXISTS idx_access_requests_project ON project_access_requests(project_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_access_requests_requester ON project_access_requests(requester_id, status)",

    "CREATE INDEX IF NOT EXISTS idx_skill_drafts_status ON skill_drafts(status, created_at DESC)",

    "CREATE INDEX IF NOT EXISTS idx_credit_tx_user ON credit_transactions(user_id, created_at DESC)",

    "CREATE INDEX IF NOT EXISTS idx_credit_tx_type ON credit_transactions(type, created_at DESC)",

    "CREATE INDEX IF NOT EXISTS idx_auth_tokens_hash ON auth_tokens(token_hash)",
    "CREATE INDEX IF NOT EXISTS idx_auth_tokens_user ON auth_tokens(user_id, kind, created_at DESC)",

    "CREATE INDEX IF NOT EXISTS idx_auth_events_created ON auth_events(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_auth_events_user ON auth_events(user_id, created_at DESC)",
]

async def _create_tables(db: aiosqlite.Connection):

    for schema in _TABLE_SCHEMAS:
        await db.execute(schema)

    await _migrate_add_column_if_missing(
        db, "conversation_history", "platform_id", "TEXT"
    )


    await _migrate_add_column_if_missing(
        db, "conversation_history", "session_id", "TEXT"
    )


    await _migrate_add_column_if_missing(
        db, "conversation_history", "tool_calls_json", "TEXT"
    )
    await _migrate_add_column_if_missing(
        db, "conversation_history", "tool_call_id", "TEXT"
    )
    await _migrate_add_column_if_missing(
        db, "conversation_history", "name", "TEXT"
    )
    await _migrate_add_column_if_missing(
        db, "conversation_history", "seq", "INTEGER"
    )


    await _migrate_add_column_if_missing(
        db, "projects", "owner_id", "TEXT"
    )


    await _migrate_add_column_if_missing(
        db, "users", "credits_balance", "INTEGER DEFAULT 0"
    )

    await _migrate_add_column_if_missing(
        db, "users", "token_version", "INTEGER NOT NULL DEFAULT 0"
    )

    await _migrate_add_column_if_missing(
        db, "users", "email_verified", "INTEGER NOT NULL DEFAULT 0"
    )



    await _migrate_add_column_if_missing(
        db, "projects", "visibility", "TEXT DEFAULT 'private'"
    )
    await _migrate_add_column_if_missing(
        db, "projects", "market_default_role", "TEXT DEFAULT 'viewer'"
    )
    await _migrate_add_column_if_missing(
        db, "projects", "status", "TEXT NOT NULL DEFAULT 'active'"
    )
    await _migrate_add_column_if_missing(
        db, "projects", "status_changed_at", "TIMESTAMP"
    )
    await _migrate_add_column_if_missing(
        db, "projects", "status_changed_by", "TEXT"
    )


    await _migrate_drop_legacy_crafts_table(db)
    for index in _INDEX_SCHEMAS:
        await db.execute(index)
    await db.commit()

async def _migrate_add_column_if_missing(
    db: aiosqlite.Connection,
    table: str,
    column: str,
    column_type: str,
) -> None:

    try:
        cursor = await db.execute(f"PRAGMA table_info({table})")
        rows = await cursor.fetchall()
        existing = {row[1] for row in rows}
        if column not in existing:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
    except Exception as e:
        print(f"[db_migrate] ⚠ skip ALTER {table}.{column}: {e}", flush=True)

async def _migrate_drop_legacy_crafts_table(db: aiosqlite.Connection) -> None:

    try:
        cursor = await db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='craft_feedback'"
        )
        row = await cursor.fetchone()
        needs_rebuild = bool(row and "REFERENCES crafts" in (row[0] or ""))

        if needs_rebuild:

            await db.execute("PRAGMA foreign_keys=OFF")
            try:
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS craft_feedback_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        craft_id TEXT NOT NULL,
                        craft_version INTEGER NOT NULL,
                        project_id TEXT,
                        task_description TEXT,
                        success INTEGER,
                        quality_score REAL,
                        token_used INTEGER,
                        feedback_text TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                await db.execute(
                    """
                    INSERT INTO craft_feedback_new
                        (id, craft_id, craft_version, project_id, task_description,
                         success, quality_score, token_used, feedback_text, created_at)
                    SELECT
                        id, craft_id, craft_version, project_id, task_description,
                        success, quality_score, token_used, feedback_text, created_at
                    FROM craft_feedback
                    """
                )
                await db.execute("DROP TABLE craft_feedback")
                await db.execute("ALTER TABLE craft_feedback_new RENAME TO craft_feedback")
            finally:
                await db.execute("PRAGMA foreign_keys=ON")

        await db.execute("DROP TABLE IF EXISTS crafts")
    except Exception as e:
        print(f"[db_migrate] ⚠ skip drop_legacy_crafts: {e}", flush=True)
