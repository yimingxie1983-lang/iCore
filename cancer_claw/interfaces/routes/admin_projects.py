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
        WHERE {" AND ".join(where)}
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
