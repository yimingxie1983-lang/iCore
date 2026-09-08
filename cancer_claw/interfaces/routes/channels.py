"""微信渠道 API：个人扫码绑定。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from cancer_claw.channels import binding as binding_svc
from cancer_claw.config import settings
from cancer_claw.db import get_db
from cancer_claw.services.identity.deps import get_current_user

router = APIRouter(prefix="/channels/wechat", tags=["微信渠道"])


class CreateBindCodeBody(BaseModel):
    project_id: str = Field(..., min_length=1)
    permissions_mode: str = "ask"


@router.get("/status")
async def wechat_channel_status(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    cfg = settings.channels.wechat
    return {
        "enabled": bool(cfg.enabled),
        "mode": cfg.mode,
        "progress_to_chat": bool(cfg.progress_to_chat),
        "default_permissions": cfg.default_permissions,
        "bind_code_ttl_seconds": int(cfg.bind_code_ttl_seconds),
        "hint": "本机运行: icore wechat login && icore wechat serve",
    }


@router.post("/bind-codes")
async def create_bind_code(
    body: CreateBindCodeBody,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    if not settings.channels.wechat.enabled:
        raise HTTPException(status_code=400, detail="微信渠道未启用")
    project_id = body.project_id.strip()
    db = await get_db()
    cur = await db.execute("SELECT id, name, owner_id FROM projects WHERE id = ?", (project_id,))
    project_row = await cur.fetchone()
    if not project_row:
        raise HTTPException(status_code=404, detail="项目不存在")
    if hasattr(project_row, "keys"):
        project = {k: project_row[k] for k in project_row.keys()}
    else:
        cols = [d[0] for d in cur.description]
        project = {cols[i]: project_row[i] for i in range(len(cols))}

    # 简单鉴权：管理员或 owner / 成员
    user_id = str(user.get("id") or "")
    is_admin = bool(user.get("is_admin") or user.get("role") == "admin")
    if not is_admin and str(project["owner_id"]) != user_id:
        cur = await db.execute(
            "SELECT 1 FROM project_members WHERE project_id = ? AND user_id = ?",
            (project_id, user_id),
        )
        if not await cur.fetchone():
            raise HTTPException(status_code=403, detail="无权绑定该项目")

    mode = (body.permissions_mode or settings.channels.wechat.default_permissions or "ask").strip()
    result = await binding_svc.create_bind_code(
        user_id=user_id,
        project_id=project_id,
        permissions_mode=mode,
        ttl_seconds=int(settings.channels.wechat.bind_code_ttl_seconds or 600),
    )
    result["project_name"] = project["name"]
    result["instruction"] = f"在微信中向 iCore 助手发送：/bind {result['code']}"
    return result


@router.get("/bind-codes")
async def list_bind_codes(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    rows = await binding_svc.list_bind_codes_for_user(str(user.get("id") or ""))
    return {"items": rows}


@router.get("/bindings")
async def list_bindings(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    rows = await binding_svc.list_bindings_for_user(str(user.get("id") or ""))
    return {"items": rows}


@router.delete("/bindings/{external_scope_id}")
async def unbind(
    external_scope_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    binding = await binding_svc.get_binding(binding_svc.CHANNEL_WECHAT, external_scope_id)
    if not binding:
        raise HTTPException(status_code=404, detail="绑定不存在")
    if str(binding.get("user_id")) != str(user.get("id") or "") and not (
        user.get("is_admin") or user.get("role") == "admin"
    ):
        raise HTTPException(status_code=403, detail="无权解绑")
    ok = await binding_svc.delete_binding(binding_svc.CHANNEL_WECHAT, external_scope_id)
    return {"ok": ok}
