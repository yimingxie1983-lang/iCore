

from __future__ import annotations

import asyncio
import time
import re
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from string import Template
from typing import Any, Iterable, Literal

import structlog

from cancer_claw.agent.engine.evidence import EvidenceSnapshot

logger = structlog.get_logger()

DEFAULT_ARBITER_PERSONA: str = "critical_reviewer"

_PROMPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "resources"
    / "prompt_templates"
    / "deliberation"
)

@lru_cache(maxsize=8)
def _load_prompt(name: str) -> Template:

    text = (_PROMPTS_DIR / name).read_text(encoding="utf-8")
    return Template(text)

_STANCE_TEXT_MAX_CHARS = 16384

@dataclass(frozen=True)
class CouncilRole:


    persona_id: str
    stance_hint: str | None = None

@dataclass(frozen=True)
class CouncilRequest:


    question: str
    roles: tuple[CouncilRole, ...]
    snapshot: EvidenceSnapshot
    arbiter_persona: str = DEFAULT_ARBITER_PERSONA
    rebut: bool = False





    timeout_s: int = 300




    max_parallelism: int = 4

@dataclass
class Stance:


    role_id: str
    persona_id: str
    success: bool
    text: str = ""
    evidence_refs: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    duration_ms: float = 0.0
    error: str | None = None

@dataclass
class Rebuttal:


    role_id: str
    persona_id: str
    success: bool
    text: str = ""
    evidence_refs: tuple[str, ...] = ()
    duration_ms: float = 0.0
    error: str | None = None

VerdictType = Literal["consensus", "arbitrated", "escalate"]

@dataclass
class Verdict:


    type: VerdictType
    text: str
    conflict_matrix: tuple[dict, ...] = ()
    minority_notes: str = ""
    duration_ms: float = 0.0
    error: str | None = None

@dataclass
class CouncilReport:


    council_id: str
    question: str
    snapshot_id: str
    arbiter_persona: str
    stances: tuple[Stance, ...]
    verdict: Verdict
    duration_ms: float
    warnings_emitted: int = 0
    rebuttals: tuple[Rebuttal, ...] = ()

_EVENT_TYPE_REWRITE_ROLE: dict[str, str] = {
    "thinking": "council_role_thinking",
    "tool_call": "council_role_tool_call",
    "tool_result": "council_role_tool_result",
}

_EVENT_TYPE_REWRITE_REBUT: dict[str, str] = {
    "thinking": "council_role_rebut_thinking",
    "tool_call": "council_role_rebut_tool_call",
    "tool_result": "council_role_rebut_tool_result",
}

_EVENT_TYPE_REWRITE_ARBITER: dict[str, str] = {
    "thinking": "council_arbiter_thinking",
    "tool_call": "council_arbiter_tool_call",
    "tool_result": "council_arbiter_tool_result",
}

def _rewrite_event_role(ev: dict, council_id: str, role_id: str) -> dict | None:

    if not isinstance(ev, dict):
        return None
    new_type = _EVENT_TYPE_REWRITE_ROLE.get(ev.get("type"))
    if new_type is None:
        return None
    payload = {
        k: v for k, v in ev.items() if k not in ("type", "council_id", "role_id")
    }
    return {
        "type": new_type,
        "council_id": council_id,
        "role_id": role_id,
        **payload,
    }

def _rewrite_event_arbiter(ev: dict, council_id: str) -> dict | None:

    if not isinstance(ev, dict):
        return None
    new_type = _EVENT_TYPE_REWRITE_ARBITER.get(ev.get("type"))
    if new_type is None:
        return None
    payload = {k: v for k, v in ev.items() if k not in ("type", "council_id")}
    return {
        "type": new_type,
        "council_id": council_id,
        **payload,
    }

async def _bridge_role_events(
    inner_sink: asyncio.Queue,
    parent_sink: asyncio.Queue | None,
    council_id: str,
    role_id: str,
) -> None:

    while True:
        ev = await inner_sink.get()
        if ev is None:
            break
        rewritten = _rewrite_event_role(ev, council_id, role_id)
        if rewritten is None:
            continue
        if parent_sink is None:
            continue
        try:
            await parent_sink.put(rewritten)
        except Exception:
            logger.warning("council_bridge_put_failed", exc_info=True)

def _rewrite_event_rebut(ev: dict, council_id: str, role_id: str) -> dict | None:

    if not isinstance(ev, dict):
        return None
    new_type = _EVENT_TYPE_REWRITE_REBUT.get(ev.get("type"))
    if new_type is None:
        return None
    payload = {
        k: v for k, v in ev.items() if k not in ("type", "council_id", "role_id")
    }
    return {
        "type": new_type,
        "council_id": council_id,
        "role_id": role_id,
        **payload,
    }

async def _bridge_rebut_events(
    inner_sink: asyncio.Queue,
    parent_sink: asyncio.Queue | None,
    council_id: str,
    role_id: str,
) -> None:

    while True:
        ev = await inner_sink.get()
        if ev is None:
            break
        rewritten = _rewrite_event_rebut(ev, council_id, role_id)
        if rewritten is None:
            continue
        if parent_sink is None:
            continue
        try:
            await parent_sink.put(rewritten)
        except Exception:
            logger.warning("council_bridge_put_failed", exc_info=True)

async def _bridge_arbiter_events(
    inner_sink: asyncio.Queue,
    parent_sink: asyncio.Queue | None,
    council_id: str,
) -> None:

    while True:
        ev = await inner_sink.get()
        if ev is None:
            break
        rewritten = _rewrite_event_arbiter(ev, council_id)
        if rewritten is None:
            continue
        if parent_sink is None:
            continue
        try:
            await parent_sink.put(rewritten)
        except Exception:
            logger.warning("council_bridge_put_failed", exc_info=True)

async def _push(sink: asyncio.Queue | None, event: dict) -> None:

    if sink is None:
        return
    try:
        await sink.put(event)
    except Exception:
        logger.warning("council_push_failed", exc_info=True)

class _suppress:


    def __init__(self, *exc_types: type[BaseException]) -> None:
        self._types = exc_types or (Exception,)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return exc_type is not None and issubclass(exc_type, self._types)

def _extract_json(content: str) -> dict[str, Any]:

    from cancer_claw.agent.engine.summon import _extract_json_object

    obj = _extract_json_object(content) or {}
    return obj if isinstance(obj, dict) else {}

_REF_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"PMID\s*[:：]\s*(\d{4,9})", re.IGNORECASE), "PMID"),
    (re.compile(r"DOI\s*[:：]\s*(10\.\d{3,9}/[\-._;()/:A-Za-z0-9]+)", re.IGNORECASE), "DOI"),
    (re.compile(r"NCT\s*[:：]?\s*(\d{8})", re.IGNORECASE), "NCT"),
    (re.compile(r"case\s*[:：]\s*([A-Za-z0-9_\-]+)", re.IGNORECASE), "case"),
)

def _infer_refs_from_text(text: str, snapshot_refs: set[str]) -> tuple[str, ...]:

    if not text or not snapshot_refs:
        return ()
    found: set[str] = set()
    for pat, prefix in _REF_PATTERNS:
        for m in pat.finditer(text):
            ref = f"{prefix}:{m.group(1)}"
            if ref in snapshot_refs:
                found.add(ref)
    return tuple(sorted(found))

def _build_role_prompt(
    role: CouncilRole,
    question: str,
    snapshot: EvidenceSnapshot,
) -> str:

    if role.stance_hint:

        stance_hint_block = (
            f"# 视角侧重\n\n{role.stance_hint.strip()}\n\n"
        )
    else:
        stance_hint_block = ""

    template = _load_prompt("role_prompt.md")
    return template.safe_substitute(
        question=question.strip(),
        snapshot_section=snapshot.as_prompt_section(),
        stance_hint_block=stance_hint_block,
    )

def _anonymize_stances(stances: Iterable[Stance]) -> list[dict]:

    out: list[dict] = []
    for i, s in enumerate(stances):
        if not s.success:
            continue
        out.append(
            {
                "role_id": f"role_anon_{i}",
                "text": s.text,
                "evidence_refs": list(s.evidence_refs),
                "open_questions": list(s.open_questions),
            }
        )
    return out

def _build_arbiter_prompt(
    question: str,
    snapshot: EvidenceSnapshot,
    stances: Iterable[Stance],
) -> str:

    import json as _json

    anon = _anonymize_stances(stances)
    template = _load_prompt("arbiter_prompt.md")
    return template.safe_substitute(
        question=question.strip(),
        snapshot_section=snapshot.as_prompt_section(),
        stances_json=_json.dumps(anon, ensure_ascii=False, indent=2),
    )

def _build_rebuttal_prompt(
    role: CouncilRole,
    question: str,
    snapshot: EvidenceSnapshot,
    my_stance: Stance,
    all_stances: tuple[Stance, ...],
) -> str:

    import json as _json

    other_anon: list[dict] = []
    for i, s in enumerate(all_stances):
        if s.role_id == my_stance.role_id:
            continue
        if not s.success:
            continue
        other_anon.append(
            {
                "role_id": f"role_anon_{i}",
                "text": s.text,
                "evidence_refs": list(s.evidence_refs),
                "open_questions": list(s.open_questions),
            }
        )

    template = _load_prompt("rebuttal_prompt.md")
    return template.safe_substitute(
        question=question.strip(),
        snapshot_section=snapshot.as_prompt_section(),
        my_stance_text=my_stance.text or "(无文本)",
        other_stances_json=_json.dumps(other_anon, ensure_ascii=False, indent=2),
    )

def _build_arbiter_prompt_with_rebuttals(
    question: str,
    snapshot: EvidenceSnapshot,
    stances: Iterable[Stance],
    rebuttals: Iterable[Rebuttal],
) -> str:

    import json as _json

    anon = _anonymize_stances(stances)
    rebut_map = {r.role_id: r for r in rebuttals if r.success}
    for entry in anon:
        idx = int(entry["role_id"].split("_")[-1])
        role_id = f"role_{idx}"
        reb = rebut_map.get(role_id)
        if reb:
            entry["rebuttal_text"] = reb.text
            entry["rebuttal_evidence_refs"] = list(reb.evidence_refs)

    template = _load_prompt("arbiter_prompt.md")
    return template.safe_substitute(
        question=question.strip(),
        snapshot_section=snapshot.as_prompt_section(),
        stances_json=_json.dumps(anon, ensure_ascii=False, indent=2),
    )

async def _run_one_rebuttal(
    role: CouncilRole,
    role_id: str,
    *,
    question: str,
    snapshot: EvidenceSnapshot,
    my_stance: Stance,
    all_stances: tuple[Stance, ...],
    master_agent: Any,
    council_id: str,
    timeout_s: int,
    parent_sink: asyncio.Queue | None,
) -> Rebuttal:

    t0 = time.monotonic()
    inner_sink: asyncio.Queue = asyncio.Queue()
    bridge: asyncio.Task | None = None

    try:
        from cancer_claw.agent.engine.persona import load_persona

        persona = load_persona(role.persona_id)
    except Exception as exc:
        logger.warning(
            "council_rebuttal_persona_load_failed",
            council_id=council_id,
            role_id=role_id,
            persona_id=role.persona_id,
            error=str(exc),
        )
        await _push(
            parent_sink,
            {
                "type": "council_role_rebut_started",
                "council_id": council_id,
                "role_id": role_id,
                "persona_id": role.persona_id,
            },
        )
        return Rebuttal(
            role_id=role_id,
            persona_id=role.persona_id,
            success=False,
            error=f"persona_load_failed: {type(exc).__name__}: {exc}",
            duration_ms=(time.monotonic() - t0) * 1000,
        )

    persona_block = (
        f"# 你的人格：**{persona.name}**（{persona.id}）\n\n"
        f"{persona.soul_text}\n\n"
    )
    full_prompt = persona_block + _build_rebuttal_prompt(
        role, question, snapshot, my_stance, all_stances
    )

    allowed: set[str] = set(master_agent.default_tool_names())
    if persona.suggested_tools:
        proposed = set(persona.suggested_tools)
        intersect = allowed & proposed
        if intersect:
            allowed = intersect

    bridge = asyncio.create_task(
        _bridge_rebut_events(inner_sink, parent_sink, council_id, role_id)
    )

    await _push(
        parent_sink,
        {
            "type": "council_role_rebut_started",
            "council_id": council_id,
            "role_id": role_id,
            "persona_id": role.persona_id,
            "persona_name": persona.name,
            "depth": getattr(master_agent, "_depth", 0) + 1,
        },
    )

    spawn_depth = getattr(master_agent, "_depth", 0) + 1
    rebuttal: Rebuttal
    try:
        content, _iter, _usage = await asyncio.wait_for(
            master_agent.spawn_oneshot(
                full_prompt,
                tools=allowed,
                max_iterations=30,
                sink=inner_sink,
                depth=spawn_depth,
            ),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        rebuttal = Rebuttal(
            role_id=role_id,
            persona_id=role.persona_id,
            success=False,
            error=f"timeout after {timeout_s}s",
            duration_ms=(time.monotonic() - t0) * 1000,
        )
    except Exception as exc:
        logger.exception(
            "council_rebuttal_spawn_failed",
            council_id=council_id,
            role_id=role_id,
        )
        rebuttal = Rebuttal(
            role_id=role_id,
            persona_id=role.persona_id,
            success=False,
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=(time.monotonic() - t0) * 1000,
        )
    else:


        json_obj = _extract_json(content)
        snapshot_refs = {f.ref for f in snapshot.facts}

        if not json_obj:
            text_raw = content.strip()
            evidence_refs_tuple = _infer_refs_from_text(text_raw, snapshot_refs)
            schema_warning = "json_block_missing"
        else:
            text_raw = str(json_obj.get("text", "")).strip()
            if not text_raw:
                text_raw = content.strip()
                schema_warning = "json_text_field_empty"
            else:
                schema_warning = None
            raw_refs = [
                str(r) for r in (json_obj.get("evidence_refs") or []) if r
            ]
            evidence_refs_tuple = tuple(raw_refs)

        if len(text_raw) > _STANCE_TEXT_MAX_CHARS:
            logger.warning(
                "council_rebuttal_text_truncated",
                council_id=council_id,
                role_id=role_id,
                raw_chars=len(text_raw),
                truncated_to=_STANCE_TEXT_MAX_CHARS,
            )
        text_clipped = text_raw[:_STANCE_TEXT_MAX_CHARS]

        bad_refs = [r for r in evidence_refs_tuple if r not in snapshot_refs]
        for bad in bad_refs:
            await _push(
                parent_sink,
                {
                    "type": "evidence_warning",
                    "council_id": council_id,
                    "role_id": role_id,
                    "ref": bad,
                    "hit": "反驳轮引用了未在事实卷宗声明的事实（软警告）",
                },
            )
        if schema_warning is not None:
            await _push(
                parent_sink,
                {
                    "type": "evidence_warning",
                    "council_id": council_id,
                    "role_id": role_id,
                    "ref": f"schema:{schema_warning}",
                    "hit": (
                        "反驳轮 sub 输出未严格遵守 JSON 契约，已退化为纯 markdown"
                        if schema_warning == "json_block_missing"
                        else "反驳轮 JSON 的 text 字段为空，已用 raw content 兜底"
                    ),
                },
            )

        rebuttal = Rebuttal(
            role_id=role_id,
            persona_id=role.persona_id,
            success=True,
            text=text_clipped,
            evidence_refs=evidence_refs_tuple,
            duration_ms=(time.monotonic() - t0) * 1000,
        )
    finally:
        try:
            await inner_sink.put(None)
        except Exception:
            pass
        if bridge is not None:
            try:
                await asyncio.wait_for(bridge, timeout=2.0)
            except asyncio.TimeoutError:
                bridge.cancel()
                with _suppress(BaseException):
                    await bridge

    await _push(
        parent_sink,
        {
            "type": "council_role_rebuttal",
            "council_id": council_id,
            "role_id": role_id,
            "success": rebuttal.success,
            "text": rebuttal.text,
            "evidence_refs": list(rebuttal.evidence_refs),
            "duration_ms": rebuttal.duration_ms,
            "error": rebuttal.error,
        },
    )
    return rebuttal

async def _run_one_role(
    role: CouncilRole,
    role_id: str,
    *,
    question: str,
    snapshot: EvidenceSnapshot,
    master_agent: Any,
    council_id: str,
    timeout_s: int,
    parent_sink: asyncio.Queue | None,
) -> Stance:

    t0 = time.monotonic()
    inner_sink: asyncio.Queue = asyncio.Queue()
    bridge: asyncio.Task | None = None


    try:
        from cancer_claw.agent.engine.persona import load_persona

        persona = load_persona(role.persona_id)
    except FileNotFoundError:
        return await _role_error_result(
            role,
            role_id,
            council_id,
            parent_sink,
            t0,
            error=f"persona_not_found: {role.persona_id}",
        )
    except Exception as exc:
        logger.warning(
            "council_role_persona_load_failed",
            council_id=council_id,
            role_id=role_id,
            error=str(exc),
        )
        return await _role_error_result(
            role,
            role_id,
            council_id,
            parent_sink,
            t0,
            error=f"persona_load_failed: {type(exc).__name__}: {exc}",
        )

    persona_block = (
        f"# 你的人格：**{persona.name}**（{persona.id}）\n\n"
        f"{persona.soul_text}\n\n"
    )
    full_prompt = persona_block + _build_role_prompt(role, question, snapshot)






    from cancer_claw.capabilities.toolkit.registry import CORE_TOOL_NAMES

    allowed: set[str] = set(master_agent.default_tool_names())
    if persona.suggested_tools:
        proposed = set(persona.suggested_tools)
        intersect = allowed & proposed
        if intersect:
            allowed = intersect | CORE_TOOL_NAMES
        else:
            allowed = set(CORE_TOOL_NAMES)

    bridge = asyncio.create_task(
        _bridge_role_events(inner_sink, parent_sink, council_id, role_id)
    )

    await _push(
        parent_sink,
        {
            "type": "council_role_started",
            "council_id": council_id,
            "role_id": role_id,
            "persona_id": role.persona_id,
            "persona_name": persona.name,
            "icon": persona.icon or "",
            "depth": getattr(master_agent, "_depth", 0) + 1,
        },
    )

    spawn_depth = getattr(master_agent, "_depth", 0) + 1
    stance: Stance
    try:
        content, _iter, _usage = await asyncio.wait_for(
            master_agent.spawn_oneshot(
                full_prompt,
                tools=allowed,
                max_iterations=50,
                sink=inner_sink,
                depth=spawn_depth,
            ),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        stance = Stance(
            role_id=role_id,
            persona_id=role.persona_id,
            success=False,
            error=f"timeout after {timeout_s}s",
            duration_ms=(time.monotonic() - t0) * 1000,
        )
    except Exception as exc:
        logger.exception(
            "council_role_spawn_failed",
            council_id=council_id,
            role_id=role_id,
        )
        stance = Stance(
            role_id=role_id,
            persona_id=role.persona_id,
            success=False,
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=(time.monotonic() - t0) * 1000,
        )
    else:












        json_obj = _extract_json(content)
        snapshot_refs = {f.ref for f in snapshot.facts}

        if not json_obj:

            text_raw = content.strip()

            inferred_refs = _infer_refs_from_text(text_raw, snapshot_refs)
            open_qs_tuple: tuple[str, ...] = ()
            evidence_refs_tuple = inferred_refs
            schema_warning = "json_block_missing"
        else:
            text_raw = str(json_obj.get("text", "")).strip()

            if not text_raw:
                text_raw = content.strip()
                schema_warning = "json_text_field_empty"
            else:
                schema_warning = None
            raw_refs = [
                str(r) for r in (json_obj.get("evidence_refs") or []) if r
            ]
            evidence_refs_tuple = tuple(raw_refs)
            open_qs_tuple = tuple(
                str(q) for q in (json_obj.get("open_questions") or []) if q
            )



        if len(text_raw) > _STANCE_TEXT_MAX_CHARS:
            logger.warning(
                "council_stance_text_truncated",
                council_id=council_id,
                role_id=role_id,
                raw_chars=len(text_raw),
                truncated_to=_STANCE_TEXT_MAX_CHARS,
            )
        text_clipped = text_raw[:_STANCE_TEXT_MAX_CHARS]


        bad_refs = [r for r in evidence_refs_tuple if r not in snapshot_refs]
        for bad in bad_refs:


            await _push(
                parent_sink,
                {
                    "type": "evidence_warning",
                    "council_id": council_id,
                    "role_id": role_id,
                    "ref": bad,
                    "hit": "引用了未在事实卷宗声明的事实（已降级为软警告）",
                },
            )


        if schema_warning is not None:
            await _push(
                parent_sink,
                {
                    "type": "evidence_warning",
                    "council_id": council_id,
                    "role_id": role_id,
                    "ref": f"schema:{schema_warning}",
                    "hit": (
                        "sub-agent 输出未严格遵守 JSON 契约，已退化为纯 markdown 表态"
                        if schema_warning == "json_block_missing"
                        else "sub-agent JSON 的 text 字段为空，已用 raw content 兜底"
                    ),
                },
            )

        stance = Stance(
            role_id=role_id,
            persona_id=role.persona_id,

            success=bool(json_obj.get("success", True)) if json_obj else True,
            text=text_clipped,
            evidence_refs=evidence_refs_tuple,
            open_questions=open_qs_tuple,
            duration_ms=(time.monotonic() - t0) * 1000,
        )
    finally:
        try:
            await inner_sink.put(None)
        except Exception:
            pass
        if bridge is not None:
            try:
                await asyncio.wait_for(bridge, timeout=2.0)
            except asyncio.TimeoutError:
                bridge.cancel()
                with _suppress(BaseException):
                    await bridge

    await _push(
        parent_sink,
        {
            "type": "council_role_stance",
            "council_id": council_id,
            "role_id": role_id,
            "success": stance.success,
            "text": stance.text,
            "evidence_refs": list(stance.evidence_refs),
            "open_questions": list(stance.open_questions),
            "duration_ms": stance.duration_ms,
            **({"error": stance.error} if stance.error else {}),
        },
    )
    return stance

async def _role_error_result(
    role: CouncilRole,
    role_id: str,
    council_id: str,
    parent_sink: asyncio.Queue | None,
    t0: float,
    *,
    error: str,
) -> Stance:

    await _push(
        parent_sink,
        {
            "type": "council_role_started",
            "council_id": council_id,
            "role_id": role_id,
            "persona_id": role.persona_id,
            "persona_name": role.persona_id,
            "icon": "",
            "depth": 1,
        },
    )
    duration_ms = (time.monotonic() - t0) * 1000
    stance = Stance(
        role_id=role_id,
        persona_id=role.persona_id,
        success=False,
        duration_ms=duration_ms,
        error=error,
    )
    await _push(
        parent_sink,
        {
            "type": "council_role_stance",
            "council_id": council_id,
            "role_id": role_id,
            "success": False,
            "text": "",
            "evidence_refs": [],
            "open_questions": [],
            "duration_ms": duration_ms,
            "error": error,
        },
    )
    return stance

async def _run_arbiter(
    *,
    question: str,
    snapshot: EvidenceSnapshot,
    stances: tuple[Stance, ...],
    arbiter_persona: str,
    master_agent: Any,
    council_id: str,
    timeout_s: int,
    parent_sink: asyncio.Queue | None,
    rebuttals: tuple[Rebuttal, ...] | None = None,
) -> Verdict:

    t0 = time.monotonic()
    inner_sink: asyncio.Queue = asyncio.Queue()
    bridge: asyncio.Task | None = None

    try:
        from cancer_claw.agent.engine.persona import load_persona

        persona = load_persona(arbiter_persona)
    except Exception as exc:
        await _push(
            parent_sink,
            {
                "type": "council_arbiter_started",
                "council_id": council_id,
                "persona_id": arbiter_persona,
                "depth": getattr(master_agent, "_depth", 0) + 1,
            },
        )
        return Verdict(
            type="escalate",
            text=f"arbiter persona 加载失败：{arbiter_persona}。议程移交主智能体 ask_user 决断。",
            duration_ms=(time.monotonic() - t0) * 1000,
            error=f"arbiter_persona_load_failed: {type(exc).__name__}: {exc}",
        )

    persona_block = (
        f"# 你的人格：**{persona.name}**（{persona.id}）\n\n"
        f"{persona.soul_text}\n\n"
    )
    if rebuttals:
        full_prompt = persona_block + _build_arbiter_prompt_with_rebuttals(
            question, snapshot, stances, rebuttals
        )
    else:
        full_prompt = persona_block + _build_arbiter_prompt(question, snapshot, stances)





    allowed: set[str] = set(master_agent.default_tool_names())
    if persona.suggested_tools:
        proposed = set(persona.suggested_tools)
        intersect = allowed & proposed
        if intersect:
            allowed = intersect

    bridge = asyncio.create_task(
        _bridge_arbiter_events(inner_sink, parent_sink, council_id)
    )

    await _push(
        parent_sink,
        {
            "type": "council_arbiter_started",
            "council_id": council_id,
            "persona_id": arbiter_persona,
            "persona_name": persona.name,
            "icon": persona.icon or "⚖️",
            "depth": getattr(master_agent, "_depth", 0) + 1,
        },
    )

    spawn_depth = getattr(master_agent, "_depth", 0) + 1
    verdict: Verdict
    try:
        content, _iter, _usage = await asyncio.wait_for(
            master_agent.spawn_oneshot(
                full_prompt,
                tools=allowed,
                max_iterations=30,
                sink=inner_sink,
                depth=spawn_depth,
            ),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        verdict = Verdict(
            type="escalate",
            text="arbiter 仲裁超时。议程移交主智能体 ask_user 决断。",
            duration_ms=(time.monotonic() - t0) * 1000,
            error=f"timeout after {timeout_s}s",
        )
    except Exception as exc:
        logger.exception("council_arbiter_spawn_failed", council_id=council_id)
        verdict = Verdict(
            type="escalate",
            text="arbiter 仲裁异常。议程移交主智能体 ask_user 决断。",
            duration_ms=(time.monotonic() - t0) * 1000,
            error=f"{type(exc).__name__}: {exc}",
        )
    else:
        json_obj = _extract_json(content)
        raw_type = str(json_obj.get("type", "")).strip().lower()
        if raw_type not in {"consensus", "arbitrated", "escalate"}:

            verdict = Verdict(
                type="escalate",
                text="arbiter 输出格式损坏（schema 校验失败）。议程移交主智能体 ask_user 决断。",
                duration_ms=(time.monotonic() - t0) * 1000,
                error=f"bad_verdict_type: {raw_type!r}",
            )
        else:
            cm_raw = json_obj.get("conflict_matrix") or []












            anon_to_role: dict[str, str] = {
                f"role_anon_{i}": s.role_id
                for i, s in enumerate(stances)
                if s.success
            }
            conflict_matrix_raw: list[dict] = [
                cm for cm in cm_raw if isinstance(cm, dict)
            ]
            conflict_matrix_mapped: list[dict] = []
            for cm in conflict_matrix_raw:
                positions = cm.get("positions") or {}
                if isinstance(positions, dict):
                    mapped_positions = {
                        anon_to_role.get(k, k): v for k, v in positions.items()
                    }
                else:
                    mapped_positions = positions
                conflict_matrix_mapped.append(
                    {**cm, "positions": mapped_positions}
                )
            conflict_matrix: tuple[dict, ...] = tuple(conflict_matrix_mapped)
            verdict = Verdict(
                type=raw_type,
                text=str(json_obj.get("text", "")).strip()[:4000],
                conflict_matrix=conflict_matrix,
                minority_notes=str(json_obj.get("minority_notes", "")).strip()[
                    :1000
                ],
                duration_ms=(time.monotonic() - t0) * 1000,
            )
    finally:
        try:
            await inner_sink.put(None)
        except Exception:
            pass
        if bridge is not None:
            try:
                await asyncio.wait_for(bridge, timeout=2.0)
            except asyncio.TimeoutError:
                bridge.cancel()
                with _suppress(BaseException):
                    await bridge

    await _push(
        parent_sink,
        {
            "type": "council_verdict",
            "council_id": council_id,
            "verdict_type": verdict.type,
            "text": verdict.text,
            "conflict_matrix": list(verdict.conflict_matrix),
            "minority_notes": verdict.minority_notes,
            "duration_ms": verdict.duration_ms,
            **({"error": verdict.error} if verdict.error else {}),
        },
    )
    return verdict

async def _persist_council_audit(
    report: CouncilReport,
    snapshot: EvidenceSnapshot,
    master_agent: Any,
) -> None:

    import json as _json
    from pathlib import Path

    workspace = getattr(master_agent, "_bound_workspace", None)
    if workspace is None:
        return
    root = getattr(workspace, "default_relative_root", None)
    if root is None:
        return

    try:
        council_dir = Path(root) / "councils" / report.council_id
        council_dir.mkdir(parents=True, exist_ok=True)


        snap_data = {
            "id": snapshot.id,
            "facts": [
                {
                    "kind": f.kind.value,
                    "ref": f.ref,
                    "content": f.content,
                    "source": f.source,
                }
                for f in snapshot.facts
            ],
        }
        (council_dir / "snapshot.json").write_text(
            _json.dumps(snap_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


        stances_data = [
            {
                "role_id": s.role_id,
                "persona_id": s.persona_id,
                "success": s.success,
                "text": s.text,
                "evidence_refs": list(s.evidence_refs),
                "open_questions": list(s.open_questions),
                "duration_ms": s.duration_ms,
                "error": s.error,
            }
            for s in report.stances
        ]
        (council_dir / "stances.json").write_text(
            _json.dumps(stances_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


        rebuttals_data = [
            {
                "role_id": r.role_id,
                "persona_id": r.persona_id,
                "success": r.success,
                "text": r.text,
                "evidence_refs": list(r.evidence_refs),
                "duration_ms": r.duration_ms,
                "error": r.error,
            }
            for r in report.rebuttals
        ]
        (council_dir / "rebuttals.json").write_text(
            _json.dumps(rebuttals_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


        verdict_data = {
            "type": report.verdict.type,
            "text": report.verdict.text,
            "conflict_matrix": list(report.verdict.conflict_matrix),
            "minority_notes": report.verdict.minority_notes,
            "duration_ms": report.verdict.duration_ms,
            "error": report.verdict.error,
        }
        (council_dir / "verdict.json").write_text(
            _json.dumps(verdict_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        logger.info(
            "council_audit_persisted",
            council_id=report.council_id,
            path=str(council_dir),
        )
    except Exception:
        logger.warning(
            "council_audit_persist_failed",
            council_id=report.council_id,
            exc_info=True,
        )

async def _try_clone_carrier(
    master_agent: Any,
    *,
    council_id: str,
    role_id: str,
    parent_sink: asyncio.Queue | None,
) -> Any:

    clone_fn = getattr(master_agent, "clone_for_subtask", None)
    if clone_fn is None:
        return master_agent
    try:
        return clone_fn()
    except Exception as exc:
        logger.warning(
            "council_carrier_clone_failed",
            council_id=council_id,
            role_id=role_id,
            error=f"{type(exc).__name__}: {exc}",
        )

        await _push(
            parent_sink,
            {
                "type": "evidence_warning",
                "council_id": council_id,
                "role_id": role_id,
                "ref": "carrier_clone",
                "hit": (
                    f"clone_for_subtask 抛 {type(exc).__name__}: {exc}；"
                    f"本 role 已降级串行执行，前端可能看到该 role 与其他 role 互相覆盖事件流"
                ),
            },
        )
        return master_agent

async def _run_one_role_with_carrier(
    role: CouncilRole,
    role_id: str,
    *,
    question: str,
    snapshot: EvidenceSnapshot,
    master_agent: Any,
    council_id: str,
    timeout_s: int,
    parent_sink: asyncio.Queue | None,
    semaphore: asyncio.Semaphore,
) -> Stance:

    carrier = await _try_clone_carrier(
        master_agent,
        council_id=council_id,
        role_id=role_id,
        parent_sink=parent_sink,
    )
    async with semaphore:
        return await _run_one_role(
            role,
            role_id,
            question=question,
            snapshot=snapshot,
            master_agent=carrier,
            council_id=council_id,
            timeout_s=timeout_s,
            parent_sink=parent_sink,
        )

async def _run_roles_parallel(
    roles: tuple[CouncilRole, ...],
    *,
    question: str,
    snapshot: EvidenceSnapshot,
    master_agent: Any,
    council_id: str,
    timeout_s: int,
    parent_sink: asyncio.Queue | None,
    max_parallelism: int,
) -> list[Stance]:

    if max_parallelism < 1:
        max_parallelism = 1
    sem = asyncio.Semaphore(max_parallelism)

    tasks = [
        asyncio.create_task(
            _run_one_role_with_carrier(
                role,
                f"role_{i}",
                question=question,
                snapshot=snapshot,
                master_agent=master_agent,
                council_id=council_id,
                timeout_s=timeout_s,
                parent_sink=parent_sink,
                semaphore=sem,
            ),
            name=f"council[{council_id}].role_{i}",
        )
        for i, role in enumerate(roles)
    ]

    raw_results = await asyncio.gather(*tasks, return_exceptions=True)
    out: list[Stance] = []
    for i, (role, r) in enumerate(zip(roles, raw_results, strict=True)):
        if isinstance(r, BaseException):
            logger.exception(
                "council_role_unexpected_exception",
                council_id=council_id,
                role_id=f"role_{i}",
                error=f"{type(r).__name__}: {r}",
            )
            out.append(
                Stance(
                    role_id=f"role_{i}",
                    persona_id=role.persona_id,
                    success=False,
                    error=f"unexpected: {type(r).__name__}: {r}",
                )
            )
        else:
            out.append(r)
    return out

async def _run_one_rebuttal_with_carrier(
    role: CouncilRole,
    role_id: str,
    *,
    question: str,
    snapshot: EvidenceSnapshot,
    my_stance: Stance,
    all_stances: tuple[Stance, ...],
    master_agent: Any,
    council_id: str,
    timeout_s: int,
    parent_sink: asyncio.Queue | None,
    semaphore: asyncio.Semaphore,
) -> Rebuttal:

    carrier = await _try_clone_carrier(
        master_agent,
        council_id=council_id,
        role_id=role_id,
        parent_sink=parent_sink,
    )
    async with semaphore:
        return await _run_one_rebuttal(
            role,
            role_id,
            question=question,
            snapshot=snapshot,
            my_stance=my_stance,
            all_stances=all_stances,
            master_agent=carrier,
            council_id=council_id,
            timeout_s=timeout_s,
            parent_sink=parent_sink,
        )

async def _run_rebuttals_parallel(
    roles: tuple[CouncilRole, ...],
    *,
    stances: list[Stance],
    question: str,
    snapshot: EvidenceSnapshot,
    master_agent: Any,
    council_id: str,
    timeout_s: int,
    parent_sink: asyncio.Queue | None,
    max_parallelism: int,
) -> list[Rebuttal]:

    if max_parallelism < 1:
        max_parallelism = 1
    sem = asyncio.Semaphore(max_parallelism)
    stances_tuple = tuple(stances)


    tasks: list[tuple[int, asyncio.Task | Rebuttal]] = []
    for i, role in enumerate(roles):
        role_id = f"role_{i}"
        my_stance = stances[i]
        if not my_stance.success:
            tasks.append(
                (
                    i,
                    Rebuttal(
                        role_id=role_id,
                        persona_id=role.persona_id,
                        success=False,
                        error="skipped: first round stance failed",
                        duration_ms=0.0,
                    ),
                )
            )
            continue
        tasks.append(
            (
                i,
                asyncio.create_task(
                    _run_one_rebuttal_with_carrier(
                        role,
                        role_id,
                        question=question,
                        snapshot=snapshot,
                        my_stance=my_stance,
                        all_stances=stances_tuple,
                        master_agent=master_agent,
                        council_id=council_id,
                        timeout_s=timeout_s,
                        parent_sink=parent_sink,
                        semaphore=sem,
                    ),
                    name=f"council[{council_id}].rebut_{i}",
                ),
            )
        )

    out: list[Rebuttal] = []
    for i, item in tasks:
        if isinstance(item, Rebuttal):
            out.append(item)
            continue
        try:
            out.append(await item)
        except BaseException as exc:
            logger.exception(
                "council_rebuttal_unexpected_exception",
                council_id=council_id,
                role_id=f"role_{i}",
                error=f"{type(exc).__name__}: {exc}",
            )
            out.append(
                Rebuttal(
                    role_id=f"role_{i}",
                    persona_id=roles[i].persona_id,
                    success=False,
                    error=f"unexpected: {type(exc).__name__}: {exc}",
                )
            )
    return out

async def run_council(
    req: CouncilRequest, master_agent: Any
) -> CouncilReport:

    if getattr(master_agent, "_depth", 0) > 0:
        raise ValueError(
            "run_council 拒绝在 sub-agent 上下文里调用（账本 §16 关键不变量）"
        )
    if not req.roles or len(req.roles) < 2:
        raise ValueError("convene_council 至少需要 2 个 role（议会需要差异性）")
    persona_ids = [r.persona_id for r in req.roles]
    if len(set(persona_ids)) != len(persona_ids):
        raise ValueError(f"convene_council roles 中 persona_id 重复：{persona_ids}")
    if req.arbiter_persona in persona_ids:
        raise ValueError(
            f"arbiter_persona ({req.arbiter_persona}) 不能同时出现在 roles 里——"
            "仲裁人和议事人格必须互斥"
        )

    council_id = f"council_{uuid.uuid4().hex[:12]}"
    parent_sink: asyncio.Queue | None = getattr(master_agent, "_event_sink", None)
    t0 = time.monotonic()


    warnings = req.snapshot.subjective_warnings()
    for fact, hit in warnings:
        await _push(
            parent_sink,
            {
                "type": "evidence_warning",
                "snapshot_id": req.snapshot.id,
                "ref": fact.ref,
                "hit": hit,
            },
        )

    if req.rebut:
        logger.info(
            "council_rebut_enabled",
            council_id=council_id,
            note="Phase 3: second round rebuttal will run after first round stances",
        )

    await _push(
        parent_sink,
        {
            "type": "council_convened",
            "council_id": council_id,
            "question": req.question,
            "snapshot_id": req.snapshot.id,
            "roles": [
                {"role_id": f"role_{i}", "persona_id": r.persona_id}
                for i, r in enumerate(req.roles)
            ],
            "arbiter_persona": req.arbiter_persona,
        },
    )
    logger.info(
        "council_convened",
        council_id=council_id,
        roles_total=len(req.roles),
        snapshot_id=req.snapshot.id,
        warnings_emitted=len(warnings),
    )





    stances = await _run_roles_parallel(
        req.roles,
        question=req.question,
        snapshot=req.snapshot,
        master_agent=master_agent,
        council_id=council_id,
        timeout_s=req.timeout_s,
        parent_sink=parent_sink,
        max_parallelism=req.max_parallelism,
    )


    rebuttals: list[Rebuttal] = []
    if req.rebut:
        rebuttals = await _run_rebuttals_parallel(
            req.roles,
            stances=stances,
            question=req.question,
            snapshot=req.snapshot,
            master_agent=master_agent,
            council_id=council_id,
            timeout_s=req.timeout_s,
            parent_sink=parent_sink,
            max_parallelism=req.max_parallelism,
        )


    if req.rebut and rebuttals:
        verdict = await _run_arbiter(
            question=req.question,
            snapshot=req.snapshot,
            stances=tuple(stances),
            arbiter_persona=req.arbiter_persona,
            master_agent=master_agent,
            council_id=council_id,
            timeout_s=req.timeout_s,
            parent_sink=parent_sink,
            rebuttals=tuple(rebuttals),
        )
    else:
        verdict = await _run_arbiter(
            question=req.question,
            snapshot=req.snapshot,
            stances=tuple(stances),
            arbiter_persona=req.arbiter_persona,
            master_agent=master_agent,
            council_id=council_id,
            timeout_s=req.timeout_s,
            parent_sink=parent_sink,
        )

    duration_ms = (time.monotonic() - t0) * 1000

    await _push(
        parent_sink,
        {
            "type": "council_concluded",
            "council_id": council_id,
            "duration_ms": duration_ms,
            "verdict_type": verdict.type,
        },
    )













    if verdict.type == "escalate":
        logger.info(
            "council_escalate_verdict",
            council_id=council_id,
            note="交由主 agent 亲自 ask_user 决断（不再在编排器伪造 ask_user_pending）",
        )

    logger.info(
        "council_concluded",
        council_id=council_id,
        verdict_type=verdict.type,
        roles=len(stances),
        successful_stances=sum(1 for s in stances if s.success),
        duration_ms=int(duration_ms),
    )

    report = CouncilReport(
        council_id=council_id,
        question=req.question,
        snapshot_id=req.snapshot.id,
        arbiter_persona=req.arbiter_persona,
        stances=tuple(stances),
        verdict=verdict,
        duration_ms=duration_ms,
        warnings_emitted=len(warnings),
        rebuttals=tuple(rebuttals) if rebuttals else (),
    )


    await _persist_council_audit(report, req.snapshot, master_agent)

    return report

__all__ = [
    "DEFAULT_ARBITER_PERSONA",
    "CouncilRole",
    "CouncilRequest",
    "Stance",
    "Rebuttal",
    "Verdict",
    "VerdictType",
    "CouncilReport",
    "run_council",
]
