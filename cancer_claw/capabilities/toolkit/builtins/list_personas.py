

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from cancer_claw.agent.engine.persona import list_personas as _list_personas
from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

if TYPE_CHECKING:
    from cancer_claw.agent.engine.agent import Agent

logger = structlog.get_logger()

class ListPersonasTool(BaseTool):


    @property
    def name(self) -> str:
        return "list_personas"

    @property
    def description(self) -> str:
        return (
            "列出当前内核已注册的所有人格 id / 中文名 / 图标 / 一句话描述。"
            "在调用 switch_persona / as_persona / dispatch_squad / convene_council 前，"
            "如果你不确定有哪些人格可用、或者要为 MDT / 评审 / 多视角议事挑选合适专家，"
            "请先调本工具看全量清单，再按当前场景挑人 —— 不要凭印象瞎填 persona_id。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "list_personas",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }

    async def execute(
        self,
        _agent: "Agent | None" = None,
        **_: Any,
    ) -> ToolResult:



        if _agent is not None and getattr(_agent, "_depth", 0) > 0:
            return ToolResult(
                success=False,
                output=(
                    "list_personas 不能在子任务里调用——子任务是一次性视角，"
                    "不需要也不应该召集其他人格。如果你判断需要更多视角，"
                    "请先 attempt_completion 汇报回主对话，由主智能体决定。"
                ),
                error="nested_call_forbidden",
            )

        personas = _list_personas()


        items: list[dict[str, str]] = [
            {
                "id": p.id,
                "name": p.name,
                "icon": p.icon,
                "description": p.description,
            }
            for p in personas
        ]



        if items:
            lines = [f"已注册 {len(items)} 个人格（按 id 排序）：", ""]
            for it in items:
                icon = (it["icon"] or "•").strip()
                desc = it["description"] or "(无描述)"
                lines.append(f"- {icon} **{it['id']}** ({it['name']}) — {desc}")
            text = "\n".join(lines)
        else:
            text = "当前 personas 目录为空，无可用人格。"

        return ToolResult(
            success=True,
            output=text,
            data={"personas": items, "count": len(items)},
        )
