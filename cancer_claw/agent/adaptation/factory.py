

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

import structlog

from cancer_claw.resources.prompt_templates import load_prompt
from cancer_claw.services.model_router.schema import ChatRequest
from cancer_claw.services.model_router.strategy import get_router

logger = structlog.get_logger()

MARKER_SUMMARY = "---SUMMARY---"
MARKER_MEMORY = "---MEMORY_SNIPPET---"
MARKER_AGENT_MEMORY = "---AGENT_MEMORY---"
MARKER_SKILL_DRAFT = "---SKILL_DRAFT---"

@dataclass
class EvolutionRouteContext:


    agent_id: str
    agent_name: str
    conversation_excerpt: str
    tools_invoked_summary: str
    project_id: str | None = None
    project_hint: str = ""
    prior_memory_excerpt: str = ""
    existing_crafts_l1: str = ""
    task_type: str = "fast"
    temperature: float = 0.2









    stage_just_advanced: bool = False
    stage_index: int = 0
    stage_name: str = ""

@dataclass
class EvolutionRouteResult:


    task_digest_raw: str = ""
    memory_digest_raw: str = ""
    agent_memory_digest_raw: str = ""
    errors: dict[str, str] = field(default_factory=dict)
    completed_steps: list[str] = field(default_factory=list)

def _extract_after_marker(text: str, marker: str) -> str:

    if not text:
        return ""
    idx = text.find(marker)
    if idx < 0:
        return text.strip()
    return text[idx + len(marker):].strip()

def _split_all_three(text: str) -> tuple[str, str, str]:

    if not text:
        return "", "", ""

    s_idx = text.find(MARKER_SUMMARY)
    m_idx = text.find(MARKER_MEMORY)
    a_idx = text.find(MARKER_AGENT_MEMORY)


    if s_idx < 0:
        digest = ""
    elif m_idx > s_idx:
        digest = text[s_idx + len(MARKER_SUMMARY):m_idx].strip()
    else:
        digest = text[s_idx + len(MARKER_SUMMARY):].strip()


    if m_idx < 0:
        project_memory = ""
    elif a_idx > m_idx:
        project_memory = text[m_idx + len(MARKER_MEMORY):a_idx].strip()
    else:
        project_memory = text[m_idx + len(MARKER_MEMORY):].strip()


    if a_idx < 0:
        agent_memory = ""
    else:
        agent_memory = text[a_idx + len(MARKER_AGENT_MEMORY):].strip()

    return digest, project_memory, agent_memory

async def _chat(system: str, user: str, *, task_type: str, temperature: float) -> str:

    router = get_router()
    req = ChatRequest(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        tools=None,
        task_type=task_type,
        temperature=temperature,
    )
    resp = await router.chat(req)
    return (resp.content or "").strip()

class EvolutionFactory:


    def __init__(self, load_prompt_fn: Callable[..., str] | None = None):
        self._load = load_prompt_fn or load_prompt

    def build_task_digest_user_message(self, ctx: EvolutionRouteContext) -> str:

        lines = [f"## 智能体\n- id: `{ctx.agent_id}`\n- 名称: {ctx.agent_name}"]
        if ctx.project_id:
            lines.append(f"- 项目 id: `{ctx.project_id}`")
        if ctx.project_hint.strip():
            lines.append(f"- 项目背景: {ctx.project_hint.strip()}")
        lines.append("\n## 对话摘录\n" + ctx.conversation_excerpt.strip())
        lines.append("\n## 工具调用概况\n" + (ctx.tools_invoked_summary.strip() or "（未提供）"))
        return "\n".join(lines)

    def build_memory_user_message(self, ctx: EvolutionRouteContext, task_digest: str) -> str:

        iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        prior = ctx.prior_memory_excerpt.strip() or "（无）"
        return (
            f"- **日期/上下文**: {iso} UTC, agent={ctx.agent_name}\n\n"
            f"## task_digest\n{task_digest}\n\n"
            f"## prior_memory_excerpt\n{prior}"
        )

    def build_digest_and_memory_user_message(self, ctx: EvolutionRouteContext) -> str:

        iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        lines = [
            f"## 智能体\n- id: `{ctx.agent_id}`\n- 名称: {ctx.agent_name}",
        ]
        if ctx.project_id:
            lines.append(f"- 项目 id: `{ctx.project_id}`")
        if ctx.project_hint.strip():
            lines.append(f"- 项目背景: {ctx.project_hint.strip()}")
        lines.append(f"- UTC 时间: {iso}")


        if ctx.stage_just_advanced and ctx.stage_index > 0:
            stage_label = ctx.stage_name or f"阶段{ctx.stage_index}"
            lines.append(
                f"\n## 阶段切换上下文（来自 task_charter.advance_stage）\n"
                f"本次总结由长任务阶段切换触发：**阶段 {ctx.stage_index} 「{stage_label}」"
                f"刚刚完成**。请聚焦本阶段的成果（具体产出、关键决策、踩坑），"
                "避免回到全任务层面的虚高摘要；后续阶段也会有各自的 digest 文件，不要重复。"
            )

        lines.append("\n## 对话摘录\n" + ctx.conversation_excerpt.strip())
        lines.append("\n## 工具调用概况\n" + (ctx.tools_invoked_summary.strip() or "（未提供）"))
        lines.append("\n## prior_memory_excerpt\n" + (ctx.prior_memory_excerpt.strip() or "（无）"))
        if ctx.existing_crafts_l1.strip():
            lines.append("\n## existing_crafts_l1\n" + ctx.existing_crafts_l1.strip())
        return "\n".join(lines)

    async def run_task_digest(self, ctx: EvolutionRouteContext) -> str:
        system = self._load("evolution_route_task_digest")
        user = self.build_task_digest_user_message(ctx)
        raw = await _chat(system, user, task_type=ctx.task_type, temperature=ctx.temperature)
        return _extract_after_marker(raw, MARKER_SUMMARY)

    async def run_memory_digest(self, ctx: EvolutionRouteContext, task_digest: str) -> str:
        system = self._load("evolution_route_memory_digest")
        user = self.build_memory_user_message(ctx, task_digest)
        raw = await _chat(system, user, task_type=ctx.task_type, temperature=ctx.temperature)
        return _extract_after_marker(raw, MARKER_MEMORY)

    async def run_digest_and_memory(self, ctx: EvolutionRouteContext) -> tuple[str, str, str]:

        system = self._load("evolution_route_digest_and_memory")
        user = self.build_digest_and_memory_user_message(ctx)
        raw = await _chat(system, user, task_type=ctx.task_type, temperature=ctx.temperature)
        return _split_all_three(raw)

    def build_skill_draft_user_message(self, ctx: EvolutionRouteContext) -> str:

        iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        lines = [f"## 智能体\n- id: `{ctx.agent_id}`\n- 名称: {ctx.agent_name}"]
        if ctx.project_id:
            lines.append(f"- 项目 id: `{ctx.project_id}`")
        if ctx.project_hint.strip():
            lines.append(f"- 项目背景: {ctx.project_hint.strip()}")
        lines.append(f"- UTC 时间: {iso}")
        lines.append("\n## 对话摘录\n" + ctx.conversation_excerpt.strip())
        lines.append("\n## 工具调用概况\n" + (ctx.tools_invoked_summary.strip() or "（未提供）"))
        if ctx.existing_crafts_l1.strip():
            lines.append("\n## existing_crafts_l1\n" + ctx.existing_crafts_l1.strip())
        return "\n".join(lines)

    async def run_skill_draft(self, ctx: EvolutionRouteContext) -> str:

        system = self._load("evolution_skill_draft")
        user = self.build_skill_draft_user_message(ctx)
        raw = await _chat(system, user, task_type=ctx.task_type, temperature=ctx.temperature)
        body = _extract_after_marker(raw, MARKER_SKILL_DRAFT)





        if not body:
            logger.debug("skill_draft_decision", decision="empty", raw_head=raw[:120])
            return ""
        if body.lstrip().upper().startswith("SKIP"):
            logger.debug("skill_draft_decision", decision="skip", reason=body[:160])
            return ""
        if "name:" not in body or "description:" not in body:
            logger.debug("skill_draft_decision", decision="invalid", body_head=body[:160])
            return ""
        logger.debug("skill_draft_decision", decision="draft")
        return body

    async def run_route(self, ctx: EvolutionRouteContext) -> EvolutionRouteResult:

        out = EvolutionRouteResult()

        try:
            digest, project_mem_raw, agent_mem_raw = await self.run_digest_and_memory(ctx)
            out.task_digest_raw = digest
            out.memory_digest_raw = project_mem_raw
            out.agent_memory_digest_raw = agent_mem_raw
            if digest:
                out.completed_steps.append("task_digest")
            if project_mem_raw:
                out.completed_steps.append("memory_digest")
            if agent_mem_raw:
                out.completed_steps.append("agent_memory_digest")
        except Exception as e:
            logger.warning("evolution_digest_and_memory_failed", error=str(e))
            out.errors["digest_and_memory"] = str(e)

        return out

    def schedule_route(
        self, ctx: EvolutionRouteContext, *, loop: asyncio.AbstractEventLoop | None = None
    ) -> asyncio.Task[EvolutionRouteResult]:

        lp = loop or asyncio.get_running_loop()
        return lp.create_task(self.run_route(ctx))

def schedule_evolution_route(
    ctx: EvolutionRouteContext,
    *,
    loop: asyncio.AbstractEventLoop | None = None,
) -> asyncio.Task[EvolutionRouteResult]:

    return EvolutionFactory().schedule_route(ctx, loop=loop)
