

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from cancer_claw.services.identity.deps import require_admin
from cancer_claw.config import settings
from cancer_claw.agent.adaptation import skill_draft_repo
from cancer_claw.resources.knowledge.skill_loader import invalidate_cache, load_all_skills

logger = structlog.get_logger()
router = APIRouter()

_SLUG_BAD = re.compile(r"[^a-z0-9\-]+")

def _slug(text: str) -> str:

    s = _SLUG_BAD.sub("-", (text or "").strip().lower()).strip("-")
    return s or "evolved-skill"

def _skill_dir_for(draft_id: int, name: str) -> Path:

    return Path(settings.skills.uploads_dir) / f"evolved-{draft_id}-{_slug(name)}"

def _write_skill_file(draft_id: int, name: str, content: str) -> Path:

    target_dir = _skill_dir_for(draft_id, name)
    target_dir.mkdir(parents=True, exist_ok=True)
    skill_file = target_dir / "SKILL.md"
    tmp = target_dir / ".SKILL.md.tmp"
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(skill_file)
    return skill_file

async def rehydrate_approved_skills() -> int:

    if not settings.skills.enabled:
        return 0
    written = 0
    offset = 0
    page = 200
    try:
        while True:
            rows = await skill_draft_repo.list_drafts(
                status=skill_draft_repo.STATUS_APPROVED, limit=page, offset=offset
            )
            if not rows:
                break
            for d in rows:
                content = (d.get("content") or "").strip()
                if not content:
                    continue
                skill_file = _skill_dir_for(d["id"], d.get("name") or "") / "SKILL.md"
                if skill_file.exists():
                    continue
                try:
                    _write_skill_file(d["id"], d.get("name") or "", content)
                    written += 1
                except Exception as e:
                    logger.warning(
                        "skill_rehydrate_write_failed", draft_id=d.get("id"), error=str(e)
                    )
            if len(rows) < page:
                break
            offset += page
    except Exception as e:
        logger.warning("skill_rehydrate_failed", error=str(e))
    if written:
        invalidate_cache()
    return written

class DraftBrief(BaseModel):
    id: int
    name: str
    status: str
    source_session_id: str | None = None
    source_agent_id: str | None = None
    project_id: str | None = None
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    skill_path: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    preview: str = ""

class DraftDetail(DraftBrief):
    content: str = ""

class DraftListResp(BaseModel):
    items: list[DraftBrief]
    total: int
    counts: dict[str, int] = Field(default_factory=dict)

class DraftUpdate(BaseModel):
    name: str | None = None
    content: str | None = None

class ApproveResp(BaseModel):
    ok: bool
    skill_path: str
    total_after: int
    message: str = ""

def _to_brief(d: dict[str, Any]) -> DraftBrief:
    content = d.get("content") or ""
    return DraftBrief(
        id=d["id"],
        name=d.get("name") or "",
        status=d.get("status") or "pending",
        source_session_id=d.get("source_session_id"),
        source_agent_id=d.get("source_agent_id"),
        project_id=d.get("project_id"),
        reviewed_by=d.get("reviewed_by"),
        reviewed_at=str(d.get("reviewed_at")) if d.get("reviewed_at") else None,
        skill_path=d.get("skill_path"),
        created_at=str(d.get("created_at")) if d.get("created_at") else None,
        updated_at=str(d.get("updated_at")) if d.get("updated_at") else None,
        preview=content[:200],
    )

@router.get("/skill-drafts", response_model=DraftListResp, tags=["进化审批"])
async def list_skill_drafts(
    status: str = "",
    search: str = "",
    limit: int = 100,
    offset: int = 0,
    _admin: dict[str, Any] = Depends(require_admin),
) -> DraftListResp:

    status_filter = status.strip() or None
    search_term = search.strip() or None
    rows = await skill_draft_repo.list_drafts(
        status=status_filter, search=search_term,
        limit=max(1, min(limit, 500)), offset=max(0, offset),
    )
    counts = {
        "pending": await skill_draft_repo.count_drafts(status="pending", search=search_term),
        "approved": await skill_draft_repo.count_drafts(status="approved", search=search_term),
        "rejected": await skill_draft_repo.count_drafts(status="rejected", search=search_term),
    }
    return DraftListResp(
        items=[_to_brief(r) for r in rows],
        total=await skill_draft_repo.count_drafts(status=status_filter, search=search_term),
        counts=counts,
    )

@router.get("/skill-drafts/{draft_id}", response_model=DraftDetail, tags=["进化审批"])
async def get_skill_draft(
    draft_id: int, _admin: dict[str, Any] = Depends(require_admin)
) -> DraftDetail:
    d = await skill_draft_repo.get_draft(draft_id)
    if not d:
        raise HTTPException(status_code=404, detail=f"草稿 {draft_id} 不存在")
    brief = _to_brief(d)
    return DraftDetail(**brief.model_dump(), content=d.get("content") or "")

@router.patch("/skill-drafts/{draft_id}", response_model=DraftDetail, tags=["进化审批"])
async def update_skill_draft(
    draft_id: int,
    body: DraftUpdate,
    _admin: dict[str, Any] = Depends(require_admin),
) -> DraftDetail:

    d = await skill_draft_repo.get_draft(draft_id)
    if not d:
        raise HTTPException(status_code=404, detail=f"草稿 {draft_id} 不存在")
    if d.get("status") != "pending":
        raise HTTPException(status_code=409, detail="仅待审批草稿可编辑")
    if body.name is None and body.content is None:
        raise HTTPException(status_code=400, detail="没有提供要更新的字段")

    await skill_draft_repo.update_draft_content(
        draft_id, name=body.name, content=body.content
    )
    updated = await skill_draft_repo.get_draft(draft_id)
    assert updated is not None
    brief = _to_brief(updated)
    return DraftDetail(**brief.model_dump(), content=updated.get("content") or "")

@router.post(
    "/skill-drafts/{draft_id}/approve", response_model=ApproveResp, tags=["进化审批"]
)
async def approve_skill_draft(
    draft_id: int, admin: dict[str, Any] = Depends(require_admin)
) -> ApproveResp:

    d = await skill_draft_repo.get_draft(draft_id)
    if not d:
        raise HTTPException(status_code=404, detail=f"草稿 {draft_id} 不存在")
    if d.get("status") != "pending":
        raise HTTPException(status_code=409, detail="该草稿已处理，不能重复通过")

    content = (d.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="草稿内容为空，无法固化")



    try:
        skill_file = _write_skill_file(draft_id, d.get("name") or "", content)
    except Exception as e:
        logger.warning("skill_draft_write_failed", draft_id=draft_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"写入技能库失败: {e}") from e

    invalidate_cache()
    total_after = len(load_all_skills(force_refresh=True))

    rel_path = str(skill_file)
    await skill_draft_repo.mark_reviewed(
        draft_id,
        status=skill_draft_repo.STATUS_APPROVED,
        reviewed_by=str(admin.get("id") or admin.get("username") or "admin"),
        skill_path=rel_path,
    )
    logger.info("skill_draft_approved", draft_id=draft_id, skill_path=rel_path)
    return ApproveResp(
        ok=True,
        skill_path=rel_path,
        total_after=total_after,
        message=f"已固化为 Skill（技能库现共 {total_after} 条）",
    )

@router.post(
    "/skill-drafts/{draft_id}/reject", response_model=DraftDetail, tags=["进化审批"]
)
async def reject_skill_draft(
    draft_id: int, admin: dict[str, Any] = Depends(require_admin)
) -> DraftDetail:

    d = await skill_draft_repo.get_draft(draft_id)
    if not d:
        raise HTTPException(status_code=404, detail=f"草稿 {draft_id} 不存在")
    if d.get("status") != "pending":
        raise HTTPException(status_code=409, detail="该草稿已处理，不能重复拒绝")

    await skill_draft_repo.mark_reviewed(
        draft_id,
        status=skill_draft_repo.STATUS_REJECTED,
        reviewed_by=str(admin.get("id") or admin.get("username") or "admin"),
    )
    updated = await skill_draft_repo.get_draft(draft_id)
    assert updated is not None
    brief = _to_brief(updated)
    return DraftDetail(**brief.model_dump(), content=updated.get("content") or "")
