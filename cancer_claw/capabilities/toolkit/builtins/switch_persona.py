

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

if TYPE_CHECKING:
    from cancer_claw.agent.engine.agent import Agent

logger = structlog.get_logger()

class SwitchPersonaTool(BaseTool):


    @property
    def name(self) -> str:
        return "switch_persona"

    @property
    def description(self) -> str:
        return (
            "把主对话切换到另一个 persona 长期接管（主对话延续，messages/memory/charter 全部保留），"
            "适用于'接下来这段对话用专家视角持续推进'的场景。"
            "如果只是想用别的视角跑一次性子任务后回到当前人格，请用 as_persona 而非本工具。"
            "可用 persona 通过 list_personas 查看；典型如 master / clinician / researcher / "
            "data_analyst / writer / coder。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "switch_persona",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "persona_id": {
                            "type": "string",
                            "description": (
                                "目标人格 id（与 personas/{id}.md 一致），"
                                "如 clinician / researcher / data_analyst / writer / coder / master。"
                                "切回主调度视角传 'master'。"
                            ),
                        },
                        "reason": {
                            "type": "string",
                            "description": (
                                "为什么要切到这个人格——用一两句话说清。这会被记录到日志/SSE 事件里，"
                                "让用户在前端看到'AI 主动切到 data_analyst 是因为...'，避免无声切换让人困惑。"
                            ),
                        },
                    },
                    "required": ["persona_id", "reason"],
                },
            },
        }

    async def execute(
        self,
        persona_id: str,
        reason: str = "",
        _agent: "Agent | None" = None,
        **_: Any,
    ) -> ToolResult:

        if _agent is None:
            return ToolResult(
                success=False,
                output="switch_persona 需要由 Agent 上下文调用，无法独立运行。",
                error="missing agent context",
            )

        persona_id = (persona_id or "").strip()
        if not persona_id:
            return ToolResult(
                success=False,
                output="persona_id 不能为空。可用列表请调 list_personas 查询。",
                error="empty_persona_id",
            )



        if getattr(_agent, "_depth", 0) > 0:
            return ToolResult(
                success=False,
                output=(
                    "switch_persona 不能在子任务里调用——子任务本身就是临时人格上下文，"
                    "跑完即销毁。如果你想在子任务里换视角，请汇报回主对话由主智能体决定。"
                ),
                error="nested_switch_forbidden",
            )


        if persona_id == (_agent.active_persona_id or "master"):
            return ToolResult(
                success=True,
                output=f"当前已经是 '{persona_id}' 人格，无需切换。",
                data={
                    "persona_id": persona_id,
                    "no_op": True,
                    "reason": reason or "",
                },
            )


        try:
            result = await _agent.swap_persona(persona_id)
        except FileNotFoundError:
            return ToolResult(
                success=False,
                output=(
                    f"未找到 persona '{persona_id}'。"
                    "请先用 list_personas 查询可用 id；"
                    "常见 id：master / clinician / researcher / data_analyst / writer / coder。"
                ),
                error=f"persona_not_found: {persona_id}",
            )
        except ValueError as e:
            return ToolResult(
                success=False,
                output=f"persona '{persona_id}' 文件解析失败：{e}",
                error=str(e),
            )
        except Exception as e:
            logger.warning(
                "switch_persona_failed",
                agent_id=_agent.id,
                persona_id=persona_id,
                error=str(e),
            )
            return ToolResult(
                success=False,
                output=f"切换人格失败：{type(e).__name__}: {e}",
                error=str(e),
            )

        logger.info(
            "persona_switch_via_tool",
            agent_id=_agent.id,
            to_persona=persona_id,
            reason=(reason or "")[:120],
            tools_added=result.get("tools_added", []),
            tools_removed=result.get("tools_removed", []),
        )

        added = result.get("tools_added") or []
        removed = result.get("tools_removed") or []
        diff_parts: list[str] = []
        if added:
            diff_parts.append(f"新增工具: {', '.join(added)}")
        if removed:
            diff_parts.append(f"移除工具: {', '.join(removed)}")
        diff_line = "；".join(diff_parts) if diff_parts else "工具集无变化"

        output = (
            f"✅ 已切换到 **{result.get('name') or persona_id}** ({persona_id}) 人格。\n"
            f"原因: {reason or '（未说明）'}\n"
            f"{diff_line}\n"
            f"下一轮起将以新视角继续主对话；如需切回，调用 switch_persona(persona_id='master')。"
        )

        return ToolResult(
            success=True,
            output=output,
            data={
                "persona_id": result.get("id") or persona_id,
                "name": result.get("name"),
                "icon": result.get("icon"),
                "description": result.get("description"),
                "tools_added": added,
                "tools_removed": removed,
                "reason": reason or "",
            },
        )
