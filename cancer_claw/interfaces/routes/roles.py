

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from cancer_claw.services.identity import permissions as perms
from cancer_claw.services.identity import repo
from cancer_claw.services.identity.deps import require_permission

logger = structlog.get_logger()
router = APIRouter()

_role_manage = require_permission(perms.ROLE_MANAGE)

class RoleInfo(BaseModel):
    id: str
    name: str
    description: str = ""
    is_system: bool = False
    permissions: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None

class RoleListResp(BaseModel):
    total: int
    items: list[RoleInfo]

class RoleCreateReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    description: str = Field("", max_length=200)
    permissions: list[str] = Field(default_factory=list)

class RoleUpdateReq(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=40)
    description: str | None = Field(None, max_length=200)
    permissions: list[str] | None = None

class UserRolesReq(BaseModel):
    role_ids: list[str] = Field(default_factory=list)

@router.get("/permissions/catalog")
async def permission_catalog(_user: dict[str, Any] = Depends(_role_manage)):

    return {"groups": perms.PERMISSION_CATALOG}

@router.get("/roles", response_model=RoleListResp)
async def list_roles(_user: dict[str, Any] = Depends(_role_manage)) -> RoleListResp:
    items = await repo.list_roles()
    return RoleListResp(total=len(items), items=[RoleInfo(**r) for r in items])

@router.post("/roles", response_model=RoleInfo, status_code=201)
async def create_role(
    body: RoleCreateReq, _user: dict[str, Any] = Depends(_role_manage)
) -> RoleInfo:
    if await repo.get_role_by_name(body.name):
        raise HTTPException(status_code=409, detail="角色名已存在")
    role = await repo.create_role(
        name=body.name,
        description=body.description,
        permissions=perms.sanitize_permissions(body.permissions),
    )
    logger.info("role_created", name=body.name)
    return RoleInfo(**role)

@router.get("/roles/{role_id}", response_model=RoleInfo)
async def get_role(role_id: str, _user: dict[str, Any] = Depends(_role_manage)) -> RoleInfo:
    role = await repo.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    return RoleInfo(**role)

@router.patch("/roles/{role_id}", response_model=RoleInfo)
async def update_role(
    role_id: str, body: RoleUpdateReq, _user: dict[str, Any] = Depends(_role_manage)
) -> RoleInfo:
    role = await repo.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    if body.name is not None and body.name != role["name"]:
        clash = await repo.get_role_by_name(body.name)
        if clash and clash["id"] != role_id:
            raise HTTPException(status_code=409, detail="角色名已存在")
    updated = await repo.update_role(
        role_id,
        name=body.name,
        description=body.description,
        permissions=(
            perms.sanitize_permissions(body.permissions)
            if body.permissions is not None
            else None
        ),
    )
    assert updated is not None
    logger.info("role_updated", role_id=role_id)
    return RoleInfo(**updated)

@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(role_id: str, _user: dict[str, Any] = Depends(_role_manage)):
    role = await repo.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    if role["is_system"]:
        raise HTTPException(status_code=400, detail="系统内置角色不可删除")
    await repo.delete_role(role_id)
    logger.info("role_deleted", role_id=role_id)

@router.get("/users/{user_id}/roles")
async def get_user_roles(user_id: str, _user: dict[str, Any] = Depends(_role_manage)):
    target = await repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"items": await repo.get_user_roles(user_id)}

@router.put("/users/{user_id}/roles")
async def set_user_roles(
    user_id: str, body: UserRolesReq, _user: dict[str, Any] = Depends(_role_manage)
):
    target = await repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    valid_ids: list[str] = []
    for rid in body.role_ids:
        if await repo.get_role(rid):
            valid_ids.append(rid)
    await repo.set_user_roles(user_id, valid_ids)
    logger.info("user_roles_set", user_id=user_id, roles=valid_ids)
    return {"items": await repo.get_user_roles(user_id)}
