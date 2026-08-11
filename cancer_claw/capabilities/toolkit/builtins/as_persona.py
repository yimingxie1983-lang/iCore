

from __future__ import annotations

import asyncio
import time
import uuid
from typing import TYPE_CHECKING, Any

import structlog

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

if TYPE_CHECKING:
    from cancer_claw.agent.engine.agent import Agent

logger = structlog.get_logger()

class AsPersonaTool(BaseTool):


    @property
    def name(self) -> str:
        return "as_persona"

    @property
    def description(self) -> str:
        return (
            "以另一个 persona（人格/视角）临时启动一个子任务，跑完返回结果，不污染主对话。"
            "可用 persona 通过 list_personas 查看；典型如 clinician/researcher/data_analyst/writer。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "as_persona",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "persona_id": {
                            "type": "string",
                            "description": (
                                "目标人格 id（与 personas/{id}.md 一致），"
                                "如 clinician / researcher / data_analyst / writer"
                            ),
                        },
                        "task": {
                            "type": "string",
                            "description": (
                                "要这个人格完成的具体任务。请写清「输入资料 / 期望产出 / 验收口径」，"
                                "不要简单转发原始用户问题。"
                            ),
                        },
                        "workspace_subdir": {
                            "type": "string",
                            "description": (
                                "可选。让子任务在 workspace/{subdir}/ 下工作，避免和主任务文件冲突。"
                                "默认空（同主工作区根）。"
                            ),
                            "default": "",
                        },
                        "timeout_s": {
                            "type": "integer",
                            "description": "子任务硬超时（秒），默认 600。",
                            "default": 600,
                        },
                        "max_iterations": {
                            "type": "integer",
                            "description": "子任务推理最大轮次，默认 30。",
                            "default": 30,
                        },
                    },
                    "required": ["persona_id", "task"],
                },
            },
        }

    async def execute(
        self,
        persona_id: str,
        task: str,
        workspace_subdir: str = "",
        timeout_s: int = 600,
        max_iterations: int = 30,
        _agent: "Agent | None" = None,
        **_: Any,
    ) -> ToolResult:

        if _agent is None:
            return ToolResult(
                success=False,
                output="as_persona 需要由 Agent 上下文调用，无法独立运行。",
                error="missing agent context",
            )



        if getattr(_agent, "_depth", 0) > 0:
            return ToolResult(
                success=False,
                output=(
                    "as_persona 不能在子任务里嵌套调用。"
                    "如果你正在以非 master 人格执行，请把结论汇报回主对话，"
                    "由主智能体决定下一步是否切换人格。"
                ),
                error="nested_as_persona_forbidden",
            )


        try:
            from cancer_claw.agent.engine.persona import load_persona
            persona = load_persona(persona_id)
        except FileNotFoundError:
            return ToolResult(
                success=False,
                output=(
                    f"未找到 persona '{persona_id}'。"
                    "请先用 list_personas 查询可用 id；"
                    "可用列表通常包含 master / clinician / researcher / data_analyst / writer。"
                ),
                error=f"persona_not_found: {persona_id}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=f"加载 persona 失败：{type(e).__name__}: {e}",
                error=str(e),
            )

        if not persona.soul_text.strip():
            return ToolResult(
                success=False,
                output=f"persona '{persona_id}' 的 soul 文本为空，无法以此人格启动子任务。",
                error="empty_soul_text",
            )





        try:
            from cancer_claw.agent.engine.summon import _compose_prompt, _get_body_soul_text

            transfer_prompt = _compose_prompt(
                body_system=_get_body_soul_text(_agent),
                soul_section=(
                    f"# 本次任务以 **{persona.name}**（{persona.id}）人格执行\n\n"
                    f"{persona.soul_text}"
                ),
                task=task,
                ctx_snapshot="",
            )


            prev_subdir = getattr(_agent, "_workspace_subdir", "")
            if workspace_subdir:
                _agent._workspace_subdir = workspace_subdir

            request_id = uuid.uuid4().hex[:12]
            t0 = time.monotonic()

            logger.info(
                "as_persona_start",
                request_id=request_id,
                from_agent=_agent.id,
                persona=persona.id,
                workspace_subdir=workspace_subdir or "",
            )


            allowed = _agent.default_tool_names()
            if persona.suggested_tools:
                proposed = set(persona.suggested_tools)
                intersect = allowed & proposed
                if intersect:
                    allowed = intersect


            try:
                content, iter_count, usage = await asyncio.wait_for(
                    _agent.spawn_oneshot(
                        transfer_prompt,
                        tools=allowed,
                        max_iterations=max_iterations,
                        sink=getattr(_agent, "_event_sink", None),
                        depth=getattr(_agent, "_depth", 0) + 1,
                    ),
                    timeout=timeout_s,
                )
            finally:
                if workspace_subdir:
                    _agent._workspace_subdir = prev_subdir

            duration_ms = (time.monotonic() - t0) * 1000

            logger.info(
                "as_persona_done",
                request_id=request_id,
                persona=persona.id,
                iterations=iter_count,
                duration_ms=int(duration_ms),
            )

            return ToolResult(
                success=True,
                output=f"[{persona.icon} {persona.name}] {content[:8000]}",
                data={
                    "persona_id": persona.id,
                    "persona_name": persona.name,
                    "request_id": request_id,
                    "iterations": iter_count,
                    "duration_ms": duration_ms,
                    "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                    "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                    "workspace_subdir": workspace_subdir or "",
                },
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output=f"as_persona({persona.id}) 子任务超时（{timeout_s}s）",
                error=f"timeout_after_{timeout_s}s",
            )
        except Exception as e:
            logger.exception("as_persona_failed", persona=persona.id)
            return ToolResult(
                success=False,
                output=f"as_persona({persona.id}) 失败：{type(e).__name__}: {e}",
                error=str(e),
            )
