

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any, Iterable

import structlog

from cancer_claw.config import settings
from cancer_claw.resources.knowledge.md_document import parse_frontmatter_md, read_file
from cancer_claw.resources.knowledge.schemas import (
    CertificationStatus,
    CraftKind,
    CraftRecord,
    OriginType,
)

logger = structlog.get_logger()

_SLUG_BAD = re.compile(r"[^a-zA-Z0-9_.\-]+")

def _slugify(text: str) -> str:

    s = _SLUG_BAD.sub("-", text).strip("-")
    if not s:
        s = "anon"

    if not s[0].isalnum():
        s = "x" + s
    return s

_TOOL_HINTS_TO_TOOLS: dict[str, list[str]] = {
    "python": ["code_exec"],
    "py": ["code_exec"],
    "bash": ["shell_exec"],
    "sh": ["shell_exec"],
    "shell": ["shell_exec"],
    "cli": ["shell_exec"],
    "read": ["file_ops"],
    "write": ["file_ops"],
    "edit": ["file_ops"],
    "fs": ["file_ops"],
    "filesystem": ["file_ops"],
    "http": ["http_fetch"],
    "curl": ["http_fetch"],
    "git": ["git_ops"],
    "sql": ["db_ops"],
}

def _infer_tools(fm: dict[str, Any]) -> list[str]:

    out: list[str] = []
    seen: set[str] = set()

    def _add(tool_id: str) -> None:
        if tool_id and tool_id not in seen:
            seen.add(tool_id)
            out.append(tool_id)


    raw_hints: list[str] = []
    for key in ("tool_type", "primary_tool", "tools", "allowed-tools", "allowed_tools"):
        v = fm.get(key)
        if isinstance(v, str):
            raw_hints.append(v)
        elif isinstance(v, list):
            raw_hints.extend(str(x) for x in v)


    for hint in raw_hints:
        tokens = re.split(r"[\s,;|/]+", hint.lower())
        for tok in tokens:
            if tok in _TOOL_HINTS_TO_TOOLS:
                for tid in _TOOL_HINTS_TO_TOOLS[tok]:
                    _add(tid)


    if not out:
        _add("code_exec")
        _add("file_ops")

    return out

def _parse_skill_file(path: Path, scan_root: Path) -> CraftRecord | None:

    try:
        fm, body = parse_frontmatter_md(read_file(path))
    except Exception as e:
        logger.warning("skill_parse_failed", path=str(path), error=str(e))
        return None

    if not isinstance(fm, dict):
        logger.warning("skill_frontmatter_not_dict", path=str(path))
        return None

    name = (fm.get("name") or path.parent.name).strip()
    description = (fm.get("description") or "").strip()


    when_to_use = fm.get("when_to_use") or fm.get("when-to-use")
    if isinstance(when_to_use, str) and when_to_use.strip():
        description = f"{description}\n\n何时使用：{when_to_use.strip()}".strip()

    if not description:

        logger.debug("skill_no_description_skipped", path=str(path), name=name)
        return None


    raw_paths = fm.get("paths") or fm.get("file_patterns") or []
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    file_patterns = [str(p) for p in raw_paths if p]

    try:
        rel = path.parent.relative_to(scan_root).as_posix()
    except ValueError:
        rel = path.parent.as_posix()






    rel_parts = [p for p in rel.split("/") if p]
    if len(rel_parts) >= 2:
        group = rel_parts[-2]
    elif rel_parts:
        group = rel_parts[0]
    else:
        group = "_misc"

    skill_id = f"skill_{_slugify(name)}"

    record = CraftRecord(
        id=skill_id,
        name=name,
        description=description,
        full_prompt=body or "",
        tags=["skill"],
        tools=_infer_tools(fm),
        context_budget=4000,
        version=1,
        enabled=True,
        certification_status=CertificationStatus.CERTIFIED,
        origin_type=OriginType.IMPORTED_SKILL,
        kind=CraftKind.CAPABILITY,
        sealed=False,
        activation={"file_patterns": file_patterns} if file_patterns else {},
        skill_compat={
            "original": fm,
            "relative_path": rel,
            "group": group,
            "source_file": str(path),
        },
    )
    return record

_CACHE_LOCK = threading.RLock()
_CACHED_RECORDS: list[CraftRecord] | None = None
_CACHED_BY_ID: dict[str, CraftRecord] = {}

def _scan_roots() -> list[Path]:

    roots: list[Path] = []
    for raw in settings.skills.scan_paths:
        p = Path(raw)
        if p.is_dir():
            roots.append(p.resolve())
    return roots

def _do_scan() -> tuple[list[CraftRecord], dict[str, CraftRecord]]:

    if not settings.skills.enabled:
        return [], {}

    records: list[CraftRecord] = []
    by_id: dict[str, CraftRecord] = {}
    skipped_dupes = 0

    for root in _scan_roots():

        for skill_md in root.rglob("SKILL.md"):
            if not skill_md.is_file():
                continue
            rec = _parse_skill_file(skill_md, root)
            if rec is None:
                continue
            if rec.id in by_id:

                skipped_dupes += 1
                logger.warning(
                    "skill_id_collision_skipped",
                    id=rec.id,
                    kept=by_id[rec.id].skill_compat.get("source_file"),
                    dropped=str(skill_md),
                )
                continue
            by_id[rec.id] = rec
            records.append(rec)

    logger.info(
        "skills_scanned",
        total=len(records),
        roots=[str(r) for r in _scan_roots()],
        duplicates_skipped=skipped_dupes,
    )
    return records, by_id

def load_all_skills(*, force_refresh: bool = False) -> list[CraftRecord]:

    global _CACHED_RECORDS, _CACHED_BY_ID
    with _CACHE_LOCK:
        if force_refresh or _CACHED_RECORDS is None:
            _CACHED_RECORDS, _CACHED_BY_ID = _do_scan()
        return list(_CACHED_RECORDS)

def get_skill(skill_id: str) -> CraftRecord | None:

    global _CACHED_BY_ID
    with _CACHE_LOCK:
        if _CACHED_RECORDS is None:
            load_all_skills()
        return _CACHED_BY_ID.get(skill_id)

def find_skills_by_file_patterns(file_paths: Iterable[str]) -> list[CraftRecord]:

    import fnmatch

    paths = [str(p) for p in file_paths if p]
    if not paths:
        return []
    out: list[CraftRecord] = []
    for rec in load_all_skills():
        patterns = rec.activation.get("file_patterns") or []
        if not patterns:
            continue
        for pat in patterns:
            if any(fnmatch.fnmatch(fp, pat) for fp in paths):
                out.append(rec)
                break
    return out

def invalidate_cache() -> None:

    global _CACHED_RECORDS, _CACHED_BY_ID
    with _CACHE_LOCK:
        _CACHED_RECORDS = None
        _CACHED_BY_ID = {}

__all__ = [
    "load_all_skills",
    "get_skill",
    "find_skills_by_file_patterns",
    "invalidate_cache",
]
