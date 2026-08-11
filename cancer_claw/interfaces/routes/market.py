

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from cancer_claw.services.identity import permissions as perms
from cancer_claw.services.identity import repo as auth_repo
from cancer_claw.services.identity.deps import (
    compute_project_role,
    get_current_user,
    is_admin,
    require_feature,
    require_permission,
)
from cancer_claw.db import get_db

logger = structlog.get_logger()

router = APIRouter(dependencies=[Depends(require_feature("project_sharing"))])

_browse = require_permission(perms.MARKET_BROWSE)

class MarketItem(BaseModel):
    project_id: str
    name: str
    description: str = ""
    owner_name: str = ""
    market_default_role: str = "viewer"

    my_status: str = "none"
    updated_at: str | None = None

class MarketListResp(BaseModel):
    total: int
    items: list[MarketItem]

class ApplyReq(BaseModel):
    note: str = Field("", max_length=200, description="申请留言（可选）")

class AccessRequestItem(BaseModel):
    id: int
    project_id: str
    project_name: str = ""
    requester_id: str
    requester_name: str = ""
    requested_role: str = "viewer"
    status: str = "pending"
    note: str = ""
    created_at: str | None = None
    decided_at: str | None = None

class AccessRequestListResp(BaseModel):
    total: int
    items: list[AccessRequestItem]

@router.get("/market", response_model=MarketListResp)
async def browse_market(user: dict[str, Any] = Depends(_browse)) -> MarketListResp:

    db = await get_db()
    uid = user["id"]
    cur = await db.execute(
        """SELECT p.id, p.name, p.description, p.owner_id,
                  COALESCE(p.market_default_role, 'viewer'), p.updated_at,
                  u.display_name, u.username
           FROM projects p
           LEFT JOIN users u ON u.id = p.owner_id
           WHERE p.visibility = 'market'
           ORDER BY p.updated_at DESC"""
    )
    rows = await cur.fetchall()


    mem_cur = await db.execute(
        "SELECT project_id FROM project_members WHERE user_id = ?", (uid,)
    )
    member_pids = {r[0] for r in await mem_cur.fetchall()}
    pend_cur = await db.execute(
        "SELECT project_id FROM project_access_requests WHERE requester_id = ? AND status = 'pending'",
        (uid,),
    )
    pending_pids = {r[0] for r in await pend_cur.fetchall()}

    items: list[MarketItem] = []
    for r in rows:
        pid, name, desc, owner_id, default_role, updated_at, owner_disp, owner_uname = r
        if owner_id == uid:
            my_status = "owner"
        elif pid in member_pids:
            my_status = "member"
        elif pid in pending_pids:
            my_status = "pending"
        else:
            my_status = "none"
        items.append(
            MarketItem(
                project_id=pid,
                name=name,
                description=desc or "",
                owner_name=(owner_disp or owner_uname or ""),
                market_default_role=default_role,
                my_status=my_status,
                updated_at=updated_at,
            )
        )
    return MarketListResp(total=len(items), items=items)

@router.post("/market/{project_id}/apply", response_model=AccessRequestItem, status_code=201)
async def apply_access(
    project_id: str, body: ApplyReq, user: dict[str, Any] = Depends(_browse)
) -> AccessRequestItem:

    db = await get_db()
    cur = await db.execute(
        "SELECT owner_id, name, COALESCE(visibility,'private'), COALESCE(market_default_role,'viewer') "
        "FROM projects WHERE id = ?",
        (project_id,),
    )
    row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="项目不存在")
    owner_id, pname, visibility, default_role = row
    if visibility != "market":
        raise HTTPException(status_code=400, detail="该项目未发布到市场")
    if owner_id == user["id"]:
        raise HTTPException(status_code=400, detail="这是你自己的项目")
    existing_role = await auth_repo.get_member_role(project_id, user["id"])
    if existing_role is not None:
        raise HTTPException(status_code=400, detail="你已经是该项目成员")

    dup = await db.execute(
        "SELECT id FROM project_access_requests WHERE project_id = ? AND requester_id = ? AND status = 'pending'",
        (project_id, user["id"]),
    )
    if await dup.fetchone():
        raise HTTPException(status_code=409, detail="你已提交过申请，请等待审批")

    now = datetime.now(timezone.utc).isoformat()
    from cancer_claw.db import insert_returning_id

    new_id = await insert_returning_id(
        db,
        """INSERT INTO project_access_requests
           (project_id, requester_id, requested_role, status, note, created_at)
           VALUES (?, ?, ?, 'pending', ?, ?)""",
        (project_id, user["id"], default_role, body.note, now),
    )
    logger.info("market_access_requested", project_id=project_id, requester=user["id"])
    return AccessRequestItem(
        id=new_id,
        project_id=project_id,
        project_name=pname,
        requester_id=user["id"],
        requester_name=user.get("display_name") or user.get("username") or "",
        requested_role=default_role,
        status="pending",
        note=body.note,
        created_at=now,
    )

@router.get("/market/my-requests", response_model=AccessRequestListResp)
async def my_requests(user: dict[str, Any] = Depends(get_current_user)) -> AccessRequestListResp:

    db = await get_db()
    cur = await db.execute(
        """SELECT ar.id, ar.project_id, p.name, ar.requester_id, ar.requested_role,
                  ar.status, ar.note, ar.created_at, ar.decided_at
           FROM project_access_requests ar
           LEFT JOIN projects p ON p.id = ar.project_id
           WHERE ar.requester_id = ?
           ORDER BY ar.created_at DESC""",
        (user["id"],),
    )
    rows = await cur.fetchall()
    items = [
        AccessRequestItem(
            id=r[0], project_id=r[1], project_name=r[2] or "", requester_id=r[3],
            requested_role=r[4], status=r[5], note=r[6] or "",
            created_at=r[7], decided_at=r[8],
        )
        for r in rows
    ]
    return AccessRequestListResp(total=len(items), items=items)

@router.get("/market/requests", response_model=AccessRequestListResp)
async def incoming_requests(
    user: dict[str, Any] = Depends(get_current_user),
) -> AccessRequestListResp:

    db = await get_db()
    if is_admin(user):
        cur = await db.execute(
            """SELECT ar.id, ar.project_id, p.name, ar.requester_id, u.display_name, u.username,
                      ar.requested_role, ar.status, ar.note, ar.created_at, ar.decided_at
               FROM project_access_requests ar
               LEFT JOIN projects p ON p.id = ar.project_id
               LEFT JOIN users u ON u.id = ar.requester_id
               WHERE ar.status = 'pending'
               ORDER BY ar.created_at DESC"""
        )
    else:
        cur = await db.execute(
            """SELECT ar.id, ar.project_id, p.name, ar.requester_id, u.display_name, u.username,
                      ar.requested_role, ar.status, ar.note, ar.created_at, ar.decided_at
               FROM project_access_requests ar
               JOIN projects p ON p.id = ar.project_id
               LEFT JOIN users u ON u.id = ar.requester_id
               WHERE ar.status = 'pending' AND p.owner_id = ?
               ORDER BY ar.created_at DESC""",
            (user["id"],),
        )
    rows = await cur.fetchall()
    items = [
        AccessRequestItem(
            id=r[0], project_id=r[1], project_name=r[2] or "", requester_id=r[3],
            requester_name=(r[4] or r[5] or ""), requested_role=r[6], status=r[7],
            note=r[8] or "", created_at=r[9], decided_at=r[10],
        )
        for r in rows
    ]
    return AccessRequestListResp(total=len(items), items=items)

async def _decide_request(request_id: int, user: dict[str, Any], approve: bool) -> AccessRequestItem:
    db = await get_db()
    cur = await db.execute(
        "SELECT id, project_id, requester_id, requested_role, status FROM project_access_requests WHERE id = ?",
        (request_id,),
    )
    row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="申请不存在")
    _id, project_id, requester_id, requested_role, status = row
    if status != "pending":
        raise HTTPException(status_code=400, detail="该申请已处理")


    project, role = await compute_project_role(user, project_id)
    if project is None or role != "owner":
        raise HTTPException(status_code=403, detail="没有审批该申请的权限")

    now = datetime.now(timezone.utc).isoformat()
    new_status = "approved" if approve else "rejected"
    if approve:
        await auth_repo.add_or_update_member(project_id, requester_id, requested_role)
    await db.execute(
        "UPDATE project_access_requests SET status = ?, decided_by = ?, decided_at = ? WHERE id = ?",
        (new_status, user["id"], now, request_id),
    )
    await db.commit()
    logger.info("market_request_decided", request_id=request_id,
                approve=approve, project_id=project_id, requester=requester_id)
    return AccessRequestItem(
        id=request_id, project_id=project_id, requester_id=requester_id,
        requested_role=requested_role, status=new_status, decided_at=now,
    )

@router.post("/market/requests/{request_id}/approve", response_model=AccessRequestItem)
async def approve_request(
    request_id: int, user: dict[str, Any] = Depends(get_current_user)
) -> AccessRequestItem:
    return await _decide_request(request_id, user, approve=True)

@router.post("/market/requests/{request_id}/reject", response_model=AccessRequestItem)
async def reject_request(
    request_id: int, user: dict[str, Any] = Depends(get_current_user)
) -> AccessRequestItem:
    return await _decide_request(request_id, user, approve=False)
