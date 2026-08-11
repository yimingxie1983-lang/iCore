

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog

from cancer_claw.agent.engine.evidence import EvidenceSnapshot

logger = structlog.get_logger()

@dataclass(frozen=True)
class SquadTaskRequest:


    id: str
    title: str
    prompt: str
    persona_id: str | None = None
    evidence_refs: tuple[str, ...] = ()

@dataclass(frozen=True)
class SquadRequest:


    title: str
    tasks: tuple[SquadTaskRequest, ...]
    snapshot: EvidenceSnapshot
    max_parallelism: int = 4


    timeout_s: int = 300

@dataclass
class SquadTaskResult:


    id: str
    title: str
    persona_id: str | None
    success: bool
    summary: str = ""
    artifacts: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    duration_ms: float = 0.0
    error: str | None = None

@dataclass
class SquadReport:


    squad_id: str
    title: str
    snapshot_id: str
    tasks: tuple[SquadTaskResult, ...]
    duration_ms: float
    warnings_emitted: int = 0

_EVENT_TYPE_REWRITE: dict[str, str] = {
    "thinking": "squad_task_thinking",
    "tool_call": "squad_task_tool_call",
    "tool_result": "squad_task_tool_result",
}

def _rewrite_event(ev: dict, squad_id: str, task_id: str) -> dict | None:

    if not isinstance(ev, dict):
        return None
    orig_type = ev.get("type")
    new_type = _EVENT_TYPE_REWRITE.get(orig_type)
    if new_type is None:
        return None
    payload = {k: v for k, v in ev.items() if k not in ("type", "squad_id", "task_id")}
    return {
        "type": new_type,
        "squad_id": squad_id,
        "task_id": task_id,
        **payload,
    }

async def _bridge_sub_events(
    inner_sink: asyncio.Queue,
    parent_sink: asyncio.Queue | None,
    squad_id: str,
    task_id: str,
) -> None:

    while True:
        ev = await inner_sink.get()
        if ev is None:
            break
        rewritten = _rewrite_event(ev, squad_id, task_id)
        if rewritten is None:
            continue
        if parent_sink is None:
            continue
        try:
            await parent_sink.put(rewritten)
        except Exception:
            logger.warning("squad_bridge_put_failed", exc_info=True)

async def _push(sink: asyncio.Queue | None, event: dict) -> None:

    if sink is None:
        return
    try:
        await sink.put(event)
    except Exception:
        logger.warning("squad_push_failed", exc_info=True)

def _filtered_snapshot_section(
    snapshot: EvidenceSnapshot,
    refs: tuple[str, ...],
) -> str:

    if not refs:
        return snapshot.as_prompt_section()
    wanted = set(refs)
    keep = [f for f in snapshot.facts if f.ref in wanted]
    if not keep:
        return snapshot.as_prompt_section()
    return EvidenceSnapshot.from_facts(keep).as_prompt_section()

def _build_task_prompt(task: SquadTaskRequest, snapshot: EvidenceSnapshot) -> str:

    sections = [
        _filtered_snapshot_section(snapshot, task.evidence_refs),
        "",
        f"# 你的子任务：{task.title}",
        "",
        task.prompt.strip(),
        "",
        "# 输出契约（务必遵守）",
        "",
        "在你最终回复的结尾，用 ```json``` 代码块输出符合以下 schema 的 JSON：",
        "",
        "```json",
        "{",
        '  "success": true,',
        '  "summary": "<回报给主智能体的完整产出，markdown，建议 ≤ 4000 字>",',
        '  "artifacts": ["可选：磁盘产出文件相对路径"],',
        '  "open_questions": ["可选：仍未澄清的关键问题"]',
        "}",
        "```",
        "",
        "**关于 summary 字段（重要，决定 squad 是否白派）**：",
        "- 这是主智能体看到你工作的**唯一渠道**——你 tool_call/tool_result 的原文",
        "  （citation_resolve / pubmed_search / file_ops 等）主智能体一概看不到。",
        "- 因此 summary 必须把用户原始任务要求的**所有字段/数据完整列出**，",
        "  不要替主智能体做'结论压缩'：",
        "    * 要求返回元数据 → 列完整 markdown 表格（标题/作者/期刊/年份/DOI/...）",
        "    * 要求评估 → 给完整评估文",
        "    * 要求对比 → 给对比表",
        "    * 要求一句话结论 → 才写一句话",
        "- 用户原始任务问你要 7 个字段，你就完整列 7 个字段；",
        "  写'PMID:xxx 与主题不相关'然后丢掉作者/年份/DOI 是 squad 白派典型反模式。",
        "",
        "约束：",
        "- 你看到的事实卷宗是冻结的；卷宗外信息不得作为论据，需要补证据请在",
        "  open_questions 里列出（主 agent 会决定是否重开议程）",
        "- 你不能调用 dispatch_squad / convene_council / as_persona / switch_persona",
        "- 完成本子任务即可，不要管其他兄弟子任务在做什么（互不可见）",
    ]
    return "\n".join(sections)

def _extract_json(content: str) -> dict[str, Any]:

    from cancer_claw.agent.engine.summon import _extract_json_object

    obj = _extract_json_object(content) or {}
    return obj if isinstance(obj, dict) else {}

async def _run_one_task(
    task: SquadTaskRequest,
    *,
    snapshot: EvidenceSnapshot,
    master_agent: Any,
    squad_id: str,
    timeout_s: int,
    parent_sink: asyncio.Queue | None,
) -> SquadTaskResult:

    t0 = time.monotonic()
    inner_sink: asyncio.Queue = asyncio.Queue()
    bridge: asyncio.Task | None = None

    persona = None
    persona_block = ""
    if task.persona_id:
        try:
            from cancer_claw.agent.engine.persona import load_persona

            persona = load_persona(task.persona_id)
            persona_block = (
                f"# 本子任务以 **{persona.name}**（{persona.id}）人格执行\n\n"
                f"{persona.soul_text}\n\n"
            )
        except FileNotFoundError:
            return await _task_error_result(
                task,
                squad_id,
                parent_sink,
                t0,
                error=f"persona_not_found: {task.persona_id}",
            )
        except Exception as exc:
            logger.warning(
                "squad_task_persona_load_failed",
                squad_id=squad_id,
                task_id=task.id,
                error=str(exc),
            )
            return await _task_error_result(
                task,
                squad_id,
                parent_sink,
                t0,
                error=f"persona_load_failed: {type(exc).__name__}: {exc}",
            )

    full_prompt = persona_block + _build_task_prompt(task, snapshot)




    from cancer_claw.capabilities.toolkit.registry import CORE_TOOL_NAMES

    allowed: set[str] = set(master_agent.default_tool_names())
    if persona is not None and persona.suggested_tools:
        proposed = set(persona.suggested_tools)
        intersect = allowed & proposed
        if intersect:
            allowed = intersect | CORE_TOOL_NAMES
        else:
            allowed = set(CORE_TOOL_NAMES)

    bridge = asyncio.create_task(
        _bridge_sub_events(inner_sink, parent_sink, squad_id, task.id)
    )

    await _push(
        parent_sink,
        {
            "type": "squad_task_started",
            "squad_id": squad_id,
            "task_id": task.id,
            "task_title": task.title,
            "persona_id": task.persona_id,
            "depth": getattr(master_agent, "_depth", 0) + 1,
        },
    )

    spawn_depth = getattr(master_agent, "_depth", 0) + 1
    try:
        content, _iter_count, _usage = await asyncio.wait_for(
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
        result = SquadTaskResult(
            id=task.id,
            title=task.title,
            persona_id=task.persona_id,
            success=False,
            error=f"timeout after {timeout_s}s",
            duration_ms=(time.monotonic() - t0) * 1000,
        )
    except Exception as exc:
        logger.exception(
            "squad_task_spawn_failed",
            squad_id=squad_id,
            task_id=task.id,
        )
        result = SquadTaskResult(
            id=task.id,
            title=task.title,
            persona_id=task.persona_id,
            success=False,
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=(time.monotonic() - t0) * 1000,
        )
    else:
        json_obj = _extract_json(content)
        result = SquadTaskResult(
            id=task.id,
            title=task.title,
            persona_id=task.persona_id,
            success=bool(json_obj.get("success", True)),
            summary=str(json_obj.get("summary", "")).strip()[:500],
            artifacts=tuple(
                str(a) for a in (json_obj.get("artifacts") or []) if a
            ),
            open_questions=tuple(
                str(q) for q in (json_obj.get("open_questions") or []) if q
            ),
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

    done_event = {
        "type": "squad_task_done",
        "squad_id": squad_id,
        "task_id": task.id,
        "success": result.success,
        "summary": result.summary,
        "artifacts": list(result.artifacts),
        "duration_ms": result.duration_ms,
    }
    if result.error:
        done_event["error"] = result.error
    await _push(parent_sink, done_event)

    return result

async def _task_error_result(
    task: SquadTaskRequest,
    squad_id: str,
    parent_sink: asyncio.Queue | None,
    t0: float,
    *,
    error: str,
) -> SquadTaskResult:

    await _push(
        parent_sink,
        {
            "type": "squad_task_started",
            "squad_id": squad_id,
            "task_id": task.id,
            "task_title": task.title,
            "persona_id": task.persona_id,
            "depth": 1,
        },
    )
    duration_ms = (time.monotonic() - t0) * 1000
    await _push(
        parent_sink,
        {
            "type": "squad_task_done",
            "squad_id": squad_id,
            "task_id": task.id,
            "success": False,
            "summary": "",
            "artifacts": [],
            "duration_ms": duration_ms,
            "error": error,
        },
    )
    return SquadTaskResult(
        id=task.id,
        title=task.title,
        persona_id=task.persona_id,
        success=False,
        error=error,
        duration_ms=duration_ms,
    )

class _suppress:


    def __init__(self, *exc_types: type[BaseException]) -> None:
        self._exc = exc_types or (Exception,)

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        return exc_type is not None and issubclass(exc_type, self._exc)

async def _try_clone_carrier(
    master_agent: Any,
    *,
    squad_id: str,
    task_id: str,
    parent_sink: asyncio.Queue | None,
) -> Any:

    clone_fn = getattr(master_agent, "clone_for_subtask", None)
    if clone_fn is None:
        return master_agent
    try:
        return clone_fn()
    except Exception as exc:
        logger.warning(
            "squad_carrier_clone_failed",
            squad_id=squad_id,
            task_id=task_id,
            error=f"{type(exc).__name__}: {exc}",
        )
        await _push(
            parent_sink,
            {
                "type": "evidence_warning",
                "squad_id": squad_id,
                "task_id": task_id,
                "ref": "carrier_clone",
                "hit": (
                    f"clone_for_subtask 抛 {type(exc).__name__}: {exc}；"
                    f"本子任务已降级串行执行，前端可能看到该任务与其他任务互相覆盖事件流"
                ),
            },
        )
        return master_agent

async def _run_one_task_with_carrier(
    task: SquadTaskRequest,
    *,
    snapshot: EvidenceSnapshot,
    master_agent: Any,
    squad_id: str,
    timeout_s: int,
    parent_sink: asyncio.Queue | None,
    semaphore: asyncio.Semaphore,
) -> SquadTaskResult:

    carrier = await _try_clone_carrier(
        master_agent,
        squad_id=squad_id,
        task_id=task.id,
        parent_sink=parent_sink,
    )
    async with semaphore:
        return await _run_one_task(
            task,
            snapshot=snapshot,
            master_agent=carrier,
            squad_id=squad_id,
            timeout_s=timeout_s,
            parent_sink=parent_sink,
        )

async def _run_tasks_parallel(
    tasks: tuple[SquadTaskRequest, ...],
    *,
    snapshot: EvidenceSnapshot,
    master_agent: Any,
    squad_id: str,
    timeout_s: int,
    parent_sink: asyncio.Queue | None,
    max_parallelism: int,
) -> list[SquadTaskResult]:

    if max_parallelism < 1:
        max_parallelism = 1
    sem = asyncio.Semaphore(max_parallelism)

    pending = [
        asyncio.create_task(
            _run_one_task_with_carrier(
                task,
                snapshot=snapshot,
                master_agent=master_agent,
                squad_id=squad_id,
                timeout_s=timeout_s,
                parent_sink=parent_sink,
                semaphore=sem,
            ),
            name=f"squad[{squad_id}].{task.id}",
        )
        for task in tasks
    ]

    raw_results = await asyncio.gather(*pending, return_exceptions=True)
    out: list[SquadTaskResult] = []
    for task, r in zip(tasks, raw_results, strict=True):
        if isinstance(r, BaseException):
            logger.exception(
                "squad_task_unexpected_exception",
                squad_id=squad_id,
                task_id=task.id,
                error=f"{type(r).__name__}: {r}",
            )
            out.append(
                SquadTaskResult(
                    id=task.id,
                    title=task.title,
                    persona_id=task.persona_id,
                    success=False,
                    error=f"unexpected: {type(r).__name__}: {r}",
                )
            )
        else:
            out.append(r)
    return out

async def run_squad(req: SquadRequest, master_agent: Any) -> SquadReport:

    if getattr(master_agent, "_depth", 0) > 0:
        raise RuntimeError(
            "dispatch_squad 不能在 sub-agent 上下文里调用（账本 §16 关键不变量）"
        )
    if not req.tasks:
        raise ValueError("SquadRequest.tasks 不能为空")

    squad_id = uuid.uuid4().hex[:12]
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

    await _push(
        parent_sink,
        {
            "type": "squad_started",
            "squad_id": squad_id,
            "title": req.title,
            "snapshot_id": req.snapshot.id,
            "tasks_total": len(req.tasks),
        },
    )
    logger.info(
        "squad_started",
        squad_id=squad_id,
        title=req.title,
        tasks_total=len(req.tasks),
        snapshot_id=req.snapshot.id,
        max_parallelism_requested=req.max_parallelism,
        warnings_emitted=len(warnings),
    )




    results = await _run_tasks_parallel(
        req.tasks,
        snapshot=req.snapshot,
        master_agent=master_agent,
        squad_id=squad_id,
        timeout_s=req.timeout_s,
        parent_sink=parent_sink,
        max_parallelism=req.max_parallelism,
    )

    duration_ms = (time.monotonic() - t0) * 1000

    await _push(
        parent_sink,
        {
            "type": "squad_concluded",
            "squad_id": squad_id,
            "duration_ms": duration_ms,
        },
    )
    logger.info(
        "squad_concluded",
        squad_id=squad_id,
        success_count=sum(1 for r in results if r.success),
        total=len(results),
        duration_ms=int(duration_ms),
    )

    return SquadReport(
        squad_id=squad_id,
        title=req.title,
        snapshot_id=req.snapshot.id,
        tasks=tuple(results),
        duration_ms=duration_ms,
        warnings_emitted=len(warnings),
    )

__all__ = [
    "SquadTaskRequest",
    "SquadRequest",
    "SquadTaskResult",
    "SquadReport",
    "run_squad",
]
