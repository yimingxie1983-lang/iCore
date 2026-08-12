

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from cancer_claw.services.identity import permissions as perms
from cancer_claw.services.identity import repo as auth_repo
from cancer_claw.services.identity.deps import (
    get_current_user,
    has_permission,
    is_admin,
    require_feature,
    require_permission,
    require_project_manage,
    require_project_read,
)
from cancer_claw.config import settings
from cancer_claw.db import get_db

_require_sharing = require_feature("project_sharing")

logger = structlog.get_logger()
router = APIRouter()

class ProjectCreate(BaseModel):

    name: str = Field(..., min_length=1, max_length=100, description="项目名称")
    description: str = Field("", max_length=500, description="项目描述")

class ProjectUpdate(BaseModel):

    name: str | None = Field(None, min_length=1, max_length=100, description="新的项目名称")
    description: str | None = Field(None, max_length=500, description="新的项目描述")

class ProjectResponse(BaseModel):

    id: str
    name: str
    description: str
    workspace_path: str
    owner_id: str | None = None
    role: str | None = None
    visibility: str = "private"
    created_at: str
    updated_at: str

class ProjectListResponse(BaseModel):

    total: int
    items: list[ProjectResponse]

@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate,
    user: dict = Depends(get_current_user),
):


    if not has_permission(user, perms.PROJECT_CREATE):
        raise HTTPException(status_code=403, detail="没有新建项目的权限")


    project_id = uuid.uuid4().hex[:12]
    projects_dir = Path(settings.paths.projects_dir)
    workspace_path = str(projects_dir / project_id)


    project_dir = projects_dir / project_id
    (project_dir / "workspace").mkdir(parents=True, exist_ok=True)
    (project_dir / "memory").mkdir(parents=True, exist_ok=True)
    (project_dir / "logs").mkdir(parents=True, exist_ok=True)



    memory_file = project_dir / "memory" / "MEMORY.md"
    memory_file.write_text(
        f"# {body.name} — 项目核心记忆\n\n"
        f"> 创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"## 项目概述\n\n{body.description or '（待补充）'}\n\n"
        f"## 关键决策\n\n"
        f"## 约定与规范\n\n",
        encoding="utf-8",
    )


    now = datetime.now(timezone.utc).isoformat()
    owner_id = user["id"]
    db = await get_db()
    await db.execute(
        """INSERT INTO projects
           (id, name, description, workspace_path, owner_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (project_id, body.name, body.description, workspace_path, owner_id, now, now),
    )
    await db.commit()

    logger.info("project_created", id=project_id, name=body.name, owner_id=owner_id)

    return ProjectResponse(
        id=project_id,
        name=body.name,
        description=body.description,
        workspace_path=workspace_path,
        owner_id=owner_id,
        role="owner",
        visibility="private",
        created_at=now,
        updated_at=now,
    )

@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(user: dict = Depends(get_current_user)):

    db = await get_db()

    if is_admin(user):
        cursor = await db.execute(
            "SELECT id, name, description, workspace_path, owner_id, created_at, updated_at, "
            "COALESCE(visibility, 'private') "
            "FROM projects ORDER BY updated_at DESC"
        )
        rows = await cursor.fetchall()
        items = [
            ProjectResponse(
                id=r[0], name=r[1], description=r[2], workspace_path=r[3],
                owner_id=r[4], role="owner", created_at=r[5], updated_at=r[6],
                visibility=r[7],
            )
            for r in rows
        ]
        return ProjectListResponse(total=len(items), items=items)

    uid = user["id"]
    cursor = await db.execute(
        """
        SELECT p.id, p.name, p.description, p.workspace_path, p.owner_id,
               p.created_at, p.updated_at,
               CASE WHEN p.owner_id = ? THEN 'owner' ELSE pm.role END AS eff_role,
               COALESCE(p.visibility, 'private')
        FROM projects p
        LEFT JOIN project_members pm
               ON pm.project_id = p.id AND pm.user_id = ?
        WHERE p.owner_id = ? OR pm.user_id = ?
        ORDER BY p.updated_at DESC
        """,
        (uid, uid, uid, uid),
    )
    rows = await cursor.fetchall()
    items = [
        ProjectResponse(
            id=r[0], name=r[1], description=r[2], workspace_path=r[3],
            owner_id=r[4], role=r[7], created_at=r[5], updated_at=r[6],
            visibility=r[8],
        )
        for r in rows
    ]
    return ProjectListResponse(total=len(items), items=items)

async def _fetch_project_response(
    project_id: str, *, role: str | None = None
) -> ProjectResponse:

    db = await get_db()
    cursor = await db.execute(
        "SELECT id, name, description, workspace_path, owner_id, created_at, updated_at, "
        "COALESCE(visibility, 'private') "
        "FROM projects WHERE id = ?",
        (project_id,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")
    return ProjectResponse(
        id=row[0], name=row[1], description=row[2], workspace_path=row[3],
        owner_id=row[4], role=role, created_at=row[5], updated_at=row[6],
        visibility=row[7],
    )

@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(ctx: dict = Depends(require_project_read)):

    return await _fetch_project_response(ctx["project_id"], role=ctx["role"])

@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    body: ProjectUpdate, ctx: dict = Depends(require_project_manage)
):

    project_id = ctx["project_id"]
    db = await get_db()


    updates = []
    params = []
    if body.name is not None:
        updates.append("name = ?")
        params.append(body.name)
    if body.description is not None:
        updates.append("description = ?")
        params.append(body.description)

    if not updates:
        raise HTTPException(status_code=400, detail="没有提供要更新的字段")


    now = datetime.now(timezone.utc).isoformat()
    updates.append("updated_at = ?")
    params.append(now)
    params.append(project_id)

    await db.execute(
        f"UPDATE projects SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    await db.commit()

    return await _fetch_project_response(project_id, role=ctx["role"])

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

class MemberInfo(BaseModel):

    user_id: str
    username: str
    display_name: str
    role: str
    created_at: str | None = None

class MemberListResp(BaseModel):
    total: int
    items: list[MemberInfo]

class MemberUpsertReq(BaseModel):

    username: str = Field(..., min_length=1, max_length=40)
    role: str = Field("editor", description="editor（读写）/ viewer（只读）")

@router.get("/projects/{project_id}/members", response_model=MemberListResp)
async def list_project_members(ctx: dict = Depends(require_project_read)):

    rows = await auth_repo.list_members(ctx["project_id"])
    return MemberListResp(
        total=len(rows), items=[MemberInfo(**r) for r in rows]
    )

@router.post("/projects/{project_id}/members", response_model=MemberListResp)
async def add_project_member(
    body: MemberUpsertReq, ctx: dict = Depends(require_project_manage)
):

    if body.role not in auth_repo.VALID_MEMBER_ROLES:
        raise HTTPException(status_code=400, detail="role 必须是 editor / viewer")

    target = await auth_repo.get_user_by_username(body.username)
    if not target:
        raise HTTPException(status_code=404, detail=f"用户 {body.username} 不存在")


    project = ctx["project"]
    if project.get("owner_id") == target["id"]:
        raise HTTPException(status_code=400, detail="该用户已是项目所有者")

    await auth_repo.add_or_update_member(ctx["project_id"], target["id"], body.role)
    logger.info(
        "project_member_added",
        project_id=ctx["project_id"],
        user_id=target["id"],
        role=body.role,
    )
    rows = await auth_repo.list_members(ctx["project_id"])
    return MemberListResp(total=len(rows), items=[MemberInfo(**r) for r in rows])

class MemberRolePatchReq(BaseModel):

    role: str = Field(..., description="editor（读写）/ viewer（只读）")

@router.patch(
    "/projects/{project_id}/members/{user_id}", response_model=MemberListResp
)
async def update_project_member(
    user_id: str, body: MemberRolePatchReq, ctx: dict = Depends(require_project_manage)
):

    if body.role not in auth_repo.VALID_MEMBER_ROLES:
        raise HTTPException(status_code=400, detail="role 必须是 editor / viewer")

    current = await auth_repo.get_member_role(ctx["project_id"], user_id)
    if current is None:
        raise HTTPException(status_code=404, detail="该用户不是项目成员")
    await auth_repo.add_or_update_member(ctx["project_id"], user_id, body.role)
    logger.info(
        "project_member_role_updated",
        project_id=ctx["project_id"], user_id=user_id, role=body.role,
    )
    rows = await auth_repo.list_members(ctx["project_id"])
    return MemberListResp(total=len(rows), items=[MemberInfo(**r) for r in rows])

@router.delete(
    "/projects/{project_id}/members/{user_id}", response_model=MemberListResp
)
async def remove_project_member(
    user_id: str, ctx: dict = Depends(require_project_manage)
):

    await auth_repo.remove_member(ctx["project_id"], user_id)
    logger.info(
        "project_member_removed", project_id=ctx["project_id"], user_id=user_id
    )
    rows = await auth_repo.list_members(ctx["project_id"])
    return MemberListResp(total=len(rows), items=[MemberInfo(**r) for r in rows])

class PublishReq(BaseModel):

    default_role: str = Field(
        "viewer", description="批准申请时默认授予的角色：editor / viewer"
    )

class VisibilityResp(BaseModel):
    project_id: str
    visibility: str
    market_default_role: str

@router.post(
    "/projects/{project_id}/publish",
    response_model=VisibilityResp,
    dependencies=[Depends(_require_sharing)],
)
async def publish_project(
    body: PublishReq, ctx: dict = Depends(require_project_manage)
):

    if not has_permission(ctx["user"], perms.PROJECT_PUBLISH):
        raise HTTPException(status_code=403, detail="没有发布项目到市场的权限")
    if body.default_role not in auth_repo.VALID_MEMBER_ROLES:
        raise HTTPException(status_code=400, detail="default_role 必须是 editor / viewer")
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE projects SET visibility = 'market', market_default_role = ?, updated_at = ? WHERE id = ?",
        (body.default_role, now, ctx["project_id"]),
    )
    await db.commit()
    logger.info("project_published", project_id=ctx["project_id"], default_role=body.default_role)
    return VisibilityResp(
        project_id=ctx["project_id"], visibility="market", market_default_role=body.default_role
    )

@router.post(
    "/projects/{project_id}/unpublish",
    response_model=VisibilityResp,
    dependencies=[Depends(_require_sharing)],
)
async def unpublish_project(ctx: dict = Depends(require_project_manage)):

    if not has_permission(ctx["user"], perms.PROJECT_PUBLISH):
        raise HTTPException(status_code=403, detail="没有管理项目发布状态的权限")
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE projects SET visibility = 'private', updated_at = ? WHERE id = ?",
        (now, ctx["project_id"]),
    )
    await db.commit()
    logger.info("project_unpublished", project_id=ctx["project_id"])
    row = await _fetch_project_response(ctx["project_id"], role=ctx["role"])
    return VisibilityResp(
        project_id=ctx["project_id"], visibility="private",
        market_default_role=getattr(row, "market_default_role", "viewer") or "viewer",
    )

class AdminGrantReq(BaseModel):

    username: str = Field(..., min_length=1, max_length=40)
    role: str = Field("viewer", description="editor（读写）/ viewer（只读）")

@router.post("/admin/projects/{project_id}/grant", response_model=MemberListResp)
async def admin_grant_project(
    project_id: str,
    body: AdminGrantReq,
    _user: dict = Depends(require_permission(perms.USER_MANAGE)),
):

    if body.role not in auth_repo.VALID_MEMBER_ROLES:
        raise HTTPException(status_code=400, detail="role 必须是 editor / viewer")
    db = await get_db()
    cur = await db.execute("SELECT owner_id FROM projects WHERE id = ?", (project_id,))
    prow = await cur.fetchone()
    if not prow:
        raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")
    target = await auth_repo.get_user_by_username(body.username)
    if not target:
        raise HTTPException(status_code=404, detail=f"用户 {body.username} 不存在")
    if prow[0] == target["id"]:
        raise HTTPException(status_code=400, detail="该用户已是项目所有者")
    await auth_repo.add_or_update_member(project_id, target["id"], body.role)
    logger.info("admin_granted_project", project_id=project_id,
                user_id=target["id"], role=body.role)
    rows = await auth_repo.list_members(project_id)
    return MemberListResp(total=len(rows), items=[MemberInfo(**r) for r in rows])
