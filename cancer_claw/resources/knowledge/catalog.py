

from __future__ import annotations

import re
from typing import Iterable

import structlog

from cancer_claw.config import settings
from cancer_claw.resources.knowledge.craft_store import load_all_crafts
from cancer_claw.resources.knowledge.schemas import (
    CertificationStatus,
    CraftRecord,
    OriginType,
)

logger = structlog.get_logger()

_CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")

def _truncate(text: str | None, limit: int) -> str:

    if not text:
        return ""
    s = text.strip().replace("\n", " ")
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"

def _estimate_tokens(text: str) -> int:

    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    other = len(text) - cjk
    return int(cjk * 1.5 + other * 0.3)

def _render_entry(
    r: CraftRecord,
    *,
    desc_limit: int,
    prefix: str = "",
) -> str:

    desc = _truncate(r.description, desc_limit)
    head = f"{prefix}`{r.id}` **{r.name or r.id}**"
    return f"- {head} — {desc}" if desc else f"- {head}"

def _render_craft_section(
    crafts: list[CraftRecord],
    *,
    include_uncertified: bool,
    desc_limit: int,
) -> tuple[list[str], int]:

    enabled = [r for r in crafts if r.enabled]
    certified = [r for r in enabled if r.certification_status == CertificationStatus.CERTIFIED]
    candidate = (
        [r for r in enabled if r.certification_status == CertificationStatus.UNCERTIFIED]
        if include_uncertified else []
    )

    def _sort_key(r: CraftRecord):
        return (-(r.evolution_score or 0.0), r.id)

    certified.sort(key=_sort_key)
    candidate.sort(key=_sort_key)

    lines: list[str] = []
    if not certified and not candidate:
        return lines, 0

    lines.append("### Crafts（内部方法论）")
    for r in certified:
        lines.append(_render_entry(r, desc_limit=desc_limit))
    if candidate:
        lines.append("")
        lines.append("_未认证候选（默认不应主动采用，仅进化步可引用）：_")
        for r in candidate:
            lines.append(_render_entry(r, desc_limit=desc_limit, prefix="[候选] "))

    text = "\n".join(lines)
    return lines, _estimate_tokens(text)

def _match_skill_by_paths(
    skills: list[CraftRecord], file_paths: list[str]
) -> list[CraftRecord]:

    if not file_paths:
        return []
    import fnmatch

    hit: list[CraftRecord] = []
    for r in skills:
        patterns = r.activation.get("file_patterns") or []
        if not patterns:
            continue
        for pat in patterns:
            if any(fnmatch.fnmatch(fp, pat) for fp in file_paths):
                hit.append(r)
                break
    return hit

def _render_skill_section(
    skills: list[CraftRecord],
    *,
    pinned_ids: set[str],
    file_paths: list[str],
    token_budget: int,
    desc_limit: int,
) -> tuple[list[str], int]:

    if not skills:
        return [], 0

    pinned = [r for r in skills if r.id in pinned_ids]
    rest_after_pinned = [r for r in skills if r.id not in pinned_ids]

    path_hits = _match_skill_by_paths(rest_after_pinned, file_paths)
    hit_ids = {r.id for r in path_hits}
    rest = [r for r in rest_after_pinned if r.id not in hit_ids]
    rest.sort(key=lambda r: r.id)


    grouped: dict[str, list[CraftRecord]] = {}
    for r in rest:
        top = r.skill_compat.get("group") or "_misc"
        grouped.setdefault(top, []).append(r)
    group_order = sorted(grouped.keys())

    lines: list[str] = []
    used = 0

    def _emit(line: str) -> bool:

        nonlocal used
        cost = _estimate_tokens(line) + 1
        if used + cost > token_budget:
            return False
        lines.append(line)
        used += cost
        return True

    header = f"### Skills（外部技能 · 共 {len(skills)} 条；listing 仅摘要，按需 activate_craft 拉正文）"
    if not _emit(header):
        return [], 0


    if pinned:
        _emit("")
        _emit("_📌 已 pin：_")
        for r in pinned:
            if not _emit(_render_entry(r, desc_limit=desc_limit)):
                break


    if path_hits and used < token_budget:
        _emit("")
        _emit(f"_🎯 与当前文件相关（{len(path_hits)}）：_")
        for r in path_hits:
            if not _emit(_render_entry(r, desc_limit=desc_limit)):
                break


    truncated = False
    listed_in_groups = 0
    for top in group_order:
        if used >= token_budget:
            truncated = True
            break
        _emit("")
        if not _emit(f"_📁 {top}（{len(grouped[top])}）：_"):
            truncated = True
            break
        for r in grouped[top]:
            if not _emit(_render_entry(r, desc_limit=desc_limit)):
                truncated = True
                break
            listed_in_groups += 1
        if truncated:
            break

    if truncated:
        lines.append(
            f"_… listing 已到 token 预算上限（{token_budget}），"
            f"剩余 skill 用 ``craft_search(query=...)`` 自行查询_"
        )

    return lines, used

async def build_craft_l1_markdown(
    *,
    include_uncertified: bool = False,
    file_paths: Iterable[str] | None = None,
    extra_pinned: Iterable[str] | None = None,
) -> str:

    cfg = settings.skills
    desc_limit = cfg.l1_max_chars_per_entry
    token_budget = cfg.l1_max_token_budget


    all_crafts_records = load_all_crafts()
    craft_section_lines, craft_tokens = _render_craft_section(
        all_crafts_records,
        include_uncertified=include_uncertified,
        desc_limit=desc_limit,
    )


    skill_lines: list[str] = []
    skill_tokens = 0
    if cfg.enabled:
        try:
            from cancer_claw.resources.knowledge.skill_loader import load_all_skills

            all_skills = [
                r for r in load_all_skills()
                if r.enabled and r.origin_type == OriginType.IMPORTED_SKILL
            ]
        except Exception as e:
            logger.warning("skill_loader_failed_in_catalog", error=str(e))
            all_skills = []


        try:
            from cancer_claw.resources.knowledge.skill_pins import load_pins
            pinned_ids: set[str] = set(load_pins())
        except Exception:
            pinned_ids = set(cfg.pinned)
        if extra_pinned:
            pinned_ids.update(extra_pinned)


        skill_budget = max(token_budget - craft_tokens, 1000)

        skill_lines, skill_tokens = _render_skill_section(
            all_skills,
            pinned_ids=pinned_ids,
            file_paths=list(file_paths or []),
            token_budget=skill_budget,
            desc_limit=desc_limit,
        )


    if not craft_section_lines and not skill_lines:
        return "（暂无可用 Craft / Skill）"

    parts: list[str] = []
    if craft_section_lines:
        parts.append("\n".join(craft_section_lines))
    if skill_lines:
        parts.append("\n".join(skill_lines))

    final = "\n\n".join(parts)
    logger.debug(
        "craft_l1_rendered",
        craft_tokens_est=craft_tokens,
        skill_tokens_est=skill_tokens,
        total_chars=len(final),
    )
    return final
