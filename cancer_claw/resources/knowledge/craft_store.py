

from __future__ import annotations

from pathlib import Path

import structlog

from cancer_claw.config import settings

from cancer_claw.resources.knowledge.md_document import dump_frontmatter_md, parse_frontmatter_md, read_file, write_file

from cancer_claw.resources.knowledge.schemas import CertificationStatus, CraftRecord

logger = structlog.get_logger()

def crafts_dir() -> Path:

    p = Path(settings.paths.library_crafts_dir).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()

def sealed_crafts_dir() -> Path:


    return (Path(__file__).parent.parent / "vault" / "playbooks").resolve()

def _library_craft_file_path(craft_id: str) -> Path:

    return crafts_dir() / f"{craft_id}.md"

def craft_file_path(craft_id: str) -> Path:

    library_path = _library_craft_file_path(craft_id)
    if library_path.is_file():
        return library_path
    sealed_path = sealed_crafts_dir() / f"{craft_id}.md"
    if sealed_path.is_file():
        return sealed_path

    return library_path

def ensure_crafts_dir() -> Path:

    d = crafts_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d

def list_craft_ids() -> list[str]:

    seen: dict[str, Path] = {}

    sealed_d = sealed_crafts_dir()
    if sealed_d.is_dir():
        for p in sealed_d.glob("*.md"):
            if p.is_file():
                seen[p.stem] = p

    library_d = crafts_dir()
    if library_d.is_dir():
        for p in library_d.glob("*.md"):
            if p.is_file():
                seen[p.stem] = p

    return sorted(seen.keys())

def is_sealed_craft(craft_id: str) -> bool:

    if _library_craft_file_path(craft_id).is_file():
        return False
    sealed_path = sealed_crafts_dir() / f"{craft_id}.md"
    return sealed_path.is_file()

def craft_exists(craft_id: str) -> bool:

    return craft_file_path(craft_id).is_file()

def load_craft(craft_id: str) -> CraftRecord:

    path = craft_file_path(craft_id)
    if not path.is_file():
        raise FileNotFoundError(f"Craft 不存在: {craft_id} ({path})")
    fm, body = parse_frontmatter_md(read_file(path))
    return CraftRecord.model_validate({**fm, "full_prompt": body})

def save_craft(record: CraftRecord, *, allow_sealed: bool = False) -> Path:

    if record.sealed and not allow_sealed:


        raise PermissionError(
            f"craft sealed=True 不允许直接写入 library: {record.id}"
        )
    path = _library_craft_file_path(record.id)
    fm = record.model_dump(mode="json", exclude={"full_prompt"})
    text = dump_frontmatter_md(fm, record.full_prompt)
    write_file(path, text)
    logger.info("craft_saved", id=record.id, path=str(path), sealed=record.sealed)
    return path

def create_craft(record: CraftRecord) -> Path:

    if _library_craft_file_path(record.id).is_file():
        raise FileExistsError(f"Craft 已存在: {record.id}")
    return save_craft(record)

def update_craft(record: CraftRecord) -> Path:

    if not _library_craft_file_path(record.id).is_file():
        raise FileNotFoundError(f"Craft 不存在于 library: {record.id}")
    return save_craft(record)

def delete_craft(craft_id: str) -> bool:

    path = _library_craft_file_path(craft_id)
    if not path.is_file():
        return False
    path.unlink()
    logger.info("craft_deleted", id=craft_id, path=str(path))
    return True

def personal_crafts_dir(agent_id: str) -> Path:

    base = Path(settings.paths.agents_dir).expanduser()
    if not base.is_absolute():
        base = Path.cwd() / base
    return (base / agent_id / "crafts").resolve()

def _personal_craft_file_path(craft_id: str, agent_id: str) -> Path:

    return personal_crafts_dir(agent_id) / f"{craft_id}.md"

def _safe_load_path(path: Path) -> CraftRecord | None:

    if not path.is_file():
        return None
    try:
        fm, body = parse_frontmatter_md(read_file(path))
        return CraftRecord.model_validate({**fm, "full_prompt": body})
    except Exception as e:
        logger.warning("craft_load_failed", path=str(path), error=str(e))
        return None

def load_craft_for_agent(craft_id: str, agent_id: str) -> CraftRecord:

    candidates: list[tuple[str, CraftRecord]] = []

    if agent_id:
        rec = _safe_load_path(_personal_craft_file_path(craft_id, agent_id))
        if rec is not None:
            candidates.append(("personal", rec))

    rec = _safe_load_path(_library_craft_file_path(craft_id))
    if rec is not None:
        candidates.append(("shared", rec))

    rec = _safe_load_path(sealed_crafts_dir() / f"{craft_id}.md")
    if rec is not None:
        candidates.append(("sealed", rec))

    if not candidates:
        raise FileNotFoundError(
            f"craft 不存在于任何层（personal/shared/sealed）: {craft_id}"
        )



    certified = [
        r for _, r in candidates
        if r.certification_status == CertificationStatus.CERTIFIED
    ]
    if certified:

        return certified[0]


    sealed_recs = [r for tier, r in candidates if tier == "sealed"]
    if sealed_recs:
        return sealed_recs[0]

    return candidates[0][1]

def list_crafts_for_agent(
    agent_id: str,
    *,
    certified_only: bool = False,
    include_skills: bool = True,
) -> list[CraftRecord]:

    seen_ids: set[str] = set()

    if agent_id:
        pdir = personal_crafts_dir(agent_id)
        if pdir.is_dir():
            for p in pdir.glob("*.md"):
                if p.is_file():
                    seen_ids.add(p.stem)

    sd = sealed_crafts_dir()
    if sd.is_dir():
        for p in sd.glob("*.md"):
            if p.is_file():
                seen_ids.add(p.stem)

    ld = crafts_dir()
    if ld.is_dir():
        for p in ld.glob("*.md"):
            if p.is_file():
                seen_ids.add(p.stem)

    out: list[CraftRecord] = []
    for cid in sorted(seen_ids):
        try:
            rec = load_craft_for_agent(cid, agent_id)
        except FileNotFoundError:
            continue
        if certified_only and rec.certification_status != CertificationStatus.CERTIFIED:
            continue
        out.append(rec)

    if include_skills:

        from cancer_claw.resources.knowledge.skill_loader import load_all_skills

        craft_ids = {r.id for r in out}
        for srec in load_all_skills():
            if srec.id in craft_ids:
                continue
            if certified_only and srec.certification_status != CertificationStatus.CERTIFIED:
                continue
            out.append(srec)


        out.sort(key=lambda r: r.id)

    return out

def load_all_crafts() -> list[CraftRecord]:

    out: list[CraftRecord] = []
    for cid in list_craft_ids():
        try:
            out.append(load_craft(cid))
        except Exception as e:
            logger.warning("craft_load_skipped", id=cid, error=str(e))
    return out

