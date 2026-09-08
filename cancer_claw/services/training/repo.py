from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from cancer_claw.db import get_db

_COLS = (
    "id, project_id, user_id, brief, status, design_json, python_exe, script_path, "
    "log_path, pid, metrics_json, error, created_at, updated_at, finished_at"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(cur, row) -> dict[str, Any] | None:
    if row is None:
        return None
    if hasattr(row, "keys"):
        data = {k: row[k] for k in row.keys()}
    else:
        cols = [d[0] for d in cur.description]
        data = dict(zip(cols, row))
    if data.get("design_json") and isinstance(data["design_json"], str):
        try:
            data["design"] = json.loads(data["design_json"])
        except json.JSONDecodeError:
            data["design"] = None
    else:
        data["design"] = data.get("design_json") if isinstance(data.get("design_json"), dict) else None
    if data.get("metrics_json") and isinstance(data["metrics_json"], str):
        try:
            data["metrics"] = json.loads(data["metrics_json"])
        except json.JSONDecodeError:
            data["metrics"] = None
    else:
        data["metrics"] = None
    return data


async def insert_run(
    *,
    run_id: str,
    project_id: str,
    user_id: str,
    brief: str,
    status: str,
    design: dict[str, Any] | None = None,
    python_exe: str = "",
    script_path: str = "",
    log_path: str = "",
    error: str = "",
) -> dict[str, Any]:
    db = await get_db()
    now = _now()
    await db.execute(
        "INSERT INTO train_runs (id, project_id, user_id, brief, status, design_json, "
        "python_exe, script_path, log_path, pid, metrics_json, error, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            project_id,
            user_id,
            brief,
            status,
            json.dumps(design, ensure_ascii=False) if design else "",
            python_exe,
            script_path,
            log_path,
            None,
            "",
            error,
            now,
            now,
        ),
    )
    await db.commit()
    got = await get_run(project_id, run_id)
    assert got is not None
    return got


async def get_run(project_id: str, run_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cur = await db.execute(
        f"SELECT {_COLS} FROM train_runs WHERE project_id = ? AND id = ?",
        (project_id, run_id),
    )
    return _as_dict(cur, await cur.fetchone())


async def list_runs(project_id: str, *, limit: int = 30) -> list[dict[str, Any]]:
    db = await get_db()
    cur = await db.execute(
        f"SELECT {_COLS} FROM train_runs WHERE project_id = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (project_id, int(limit)),
    )
    rows = await cur.fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _as_dict(cur, row)
        if item:
            out.append(item)
    return out


async def update_run(project_id: str, run_id: str, **fields: Any) -> dict[str, Any] | None:
    if not fields:
        return await get_run(project_id, run_id)
    allowed = {
        "status",
        "design_json",
        "python_exe",
        "script_path",
        "log_path",
        "pid",
        "metrics_json",
        "error",
        "finished_at",
    }
    sets: list[str] = []
    params: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "design_json" and not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False) if value is not None else ""
        if key == "metrics_json" and not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False) if value is not None else ""
        sets.append(f"{key} = ?")
        params.append(value)
    if not sets:
        return await get_run(project_id, run_id)
    sets.append("updated_at = ?")
    params.append(_now())
    params.extend([project_id, run_id])
    db = await get_db()
    await db.execute(
        f"UPDATE train_runs SET {', '.join(sets)} WHERE project_id = ? AND id = ?",
        tuple(params),
    )
    await db.commit()
    return await get_run(project_id, run_id)
