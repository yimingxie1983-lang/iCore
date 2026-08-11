

from __future__ import annotations

import io
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

from cancer_claw.config import settings
from cancer_claw.resources.knowledge.skill_loader import (
    get_skill,
    invalidate_cache,
    load_all_skills,
)
from cancer_claw.resources.knowledge.skill_pins import add_pin, load_pins, remove_pin

logger = structlog.get_logger()
router = APIRouter()

class SkillBrief(BaseModel):

    id: str
    name: str
    description: str
    tools: list[str] = Field(default_factory=list)
    relative_path: str = ""
    group: str = ""
    pinned: bool = False
    source_file: str = ""

class SkillDetail(SkillBrief):

    full_prompt: str = ""
    original_frontmatter: dict[str, Any] = Field(default_factory=dict)

class UploadResp(BaseModel):
    ok: bool
    accepted_files: int
    new_skills: int
    total_after: int
    target_dir: str
    message: str = ""

class RefreshResp(BaseModel):
    total: int
    duration_ms: int

class PinsResp(BaseModel):
    ids: list[str]
    total: int

def _record_to_brief(rec, *, pinned_set: set[str]) -> SkillBrief:
    rel = rec.skill_compat.get("relative_path") or ""
    group = rec.skill_compat.get("group") or "_misc"
    return SkillBrief(
        id=rec.id,
        name=rec.name or rec.id,
        description=rec.description or "",
        tools=list(rec.tools or []),
        relative_path=rel,
        group=group,
        pinned=rec.id in pinned_set,
        source_file=str(rec.skill_compat.get("source_file") or ""),
    )

@router.get("/skills", tags=["技能库"])
async def api_list_skills(
    query: str = "",
    group: str = "",
    pinned_only: bool = False,
    limit: int = 60,
    offset: int = 0,
) -> dict:

    pinned_set = set(load_pins())
    all_skills = load_all_skills()

    q = (query or "").strip().lower()
    g = (group or "").strip()


    all_briefs: list[SkillBrief] = []
    groups: dict[str, int] = {}
    for rec in all_skills:
        b = _record_to_brief(rec, pinned_set=pinned_set)
        all_briefs.append(b)
        groups[b.group] = groups.get(b.group, 0) + 1


    def _match(b: SkillBrief) -> bool:
        if q and q not in b.id.lower() and q not in b.name.lower() and q not in b.description.lower():
            return False
        if g and b.group != g:
            return False
        if pinned_only and not b.pinned:
            return False
        return True

    filtered = [b for b in all_briefs if _match(b)]
    filtered.sort(key=lambda x: (x.group, x.id))


    safe_limit = max(1, min(int(limit or 60), 500))
    safe_offset = max(0, int(offset or 0))
    page = filtered[safe_offset : safe_offset + safe_limit]

    return {
        "total": len(page),
        "total_all": len(all_skills),
        "total_filtered": len(filtered),
        "offset": safe_offset,
        "limit": safe_limit,
        "has_more": safe_offset + len(page) < len(filtered),
        "items": [b.model_dump() for b in page],
        "groups": [
            {"name": k, "count": v} for k, v in sorted(groups.items(), key=lambda x: x[0])
        ],
        "pinned_ids": sorted(pinned_set),
    }

_SLUG_BAD = re.compile(r"[^a-zA-Z0-9_.\-]+")

def _slug(text: str) -> str:
    s = _SLUG_BAD.sub("-", text or "").strip("-")
    return s or "anon"

def _ensure_uploads_dir() -> Path:
    p = Path(settings.skills.uploads_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p

def _safe_extract_zip(zf: zipfile.ZipFile, target_dir: Path) -> int:

    target_dir = target_dir.resolve()
    count = 0
    for member in zf.infolist():

        member_path = Path(member.filename)
        if member_path.is_absolute() or any(part == ".." for part in member_path.parts):
            logger.warning("skill_zip_unsafe_member_skipped", member=member.filename)
            continue
        dest = (target_dir / member_path).resolve()

        try:
            dest.relative_to(target_dir)
        except ValueError:
            logger.warning("skill_zip_path_escape_skipped", member=member.filename)
            continue

        if member.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            count += 1
    return count

@router.post("/skills/upload", response_model=UploadResp, tags=["技能库"])
async def api_upload_skill(file: UploadFile = File(...)) -> UploadResp:

    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="未收到文件")

    before = len(load_all_skills())
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    name_stem = Path(file.filename).stem
    subdir = _ensure_uploads_dir() / f"{ts}-{_slug(name_stem)}"
    subdir.mkdir(parents=True, exist_ok=True)

    raw = await file.read()
    accepted = 0
    msg = ""

    fn_lower = file.filename.lower()
    try:
        if fn_lower.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
                accepted = _safe_extract_zip(zf, subdir)
            msg = f"zip 解压完成（{accepted} 文件）"
        elif fn_lower.endswith(".md"):

            target_name = "SKILL.md" if Path(file.filename).name != "SKILL.md" else file.filename
            (subdir / target_name).write_bytes(raw)
            accepted = 1
            msg = "单文件保存为 SKILL.md"
        else:

            shutil.rmtree(subdir, ignore_errors=True)
            raise HTTPException(
                status_code=415,
                detail=f"暂仅支持 .zip 或 .md，收到 {file.filename}",
            )
    except HTTPException:
        raise
    except Exception as e:

        shutil.rmtree(subdir, ignore_errors=True)
        logger.warning("skill_upload_failed", error=str(e), filename=file.filename)
        raise HTTPException(status_code=500, detail=f"上传失败: {e}") from e

    invalidate_cache()
    after = len(load_all_skills())
    delta = after - before

    logger.info(
        "skill_uploaded",
        filename=file.filename,
        accepted_files=accepted,
        new_skills=delta,
        target=str(subdir),
    )

    return UploadResp(
        ok=True,
        accepted_files=accepted,
        new_skills=delta,
        total_after=after,
        target_dir=str(subdir),
        message=msg + f"（共 +{delta} 条 skill）",
    )

@router.post("/skills/refresh", response_model=RefreshResp, tags=["技能库"])
async def api_refresh_skills() -> RefreshResp:

    t0 = datetime.now(timezone.utc)
    invalidate_cache()
    skills = load_all_skills(force_refresh=True)
    dt_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
    return RefreshResp(total=len(skills), duration_ms=dt_ms)

@router.get("/skills/pins", response_model=PinsResp, tags=["技能库"])
async def api_list_pins() -> PinsResp:
    ids = load_pins()
    return PinsResp(ids=ids, total=len(ids))

@router.post("/skills/pins/{skill_id}", response_model=PinsResp, tags=["技能库"])
async def api_add_pin(skill_id: str) -> PinsResp:
    if get_skill(skill_id) is None:
        raise HTTPException(status_code=404, detail=f"skill 不存在: {skill_id}")
    ids = add_pin(skill_id)
    return PinsResp(ids=ids, total=len(ids))

@router.delete("/skills/pins/{skill_id}", response_model=PinsResp, tags=["技能库"])
async def api_remove_pin(skill_id: str) -> PinsResp:
    ids = remove_pin(skill_id)
    return PinsResp(ids=ids, total=len(ids))

@router.get("/skills/{skill_id}", response_model=SkillDetail, tags=["技能库"])
async def api_get_skill_detail(skill_id: str) -> SkillDetail:

    rec = get_skill(skill_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"skill 不存在: {skill_id}")

    pinned_set = set(load_pins())
    brief = _record_to_brief(rec, pinned_set=pinned_set)
    return SkillDetail(
        **brief.model_dump(),
        full_prompt=rec.full_prompt or "",
        original_frontmatter=dict(rec.skill_compat.get("original") or {}),
    )
