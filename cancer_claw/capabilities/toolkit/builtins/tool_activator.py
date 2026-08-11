

from __future__ import annotations

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult
from cancer_claw.capabilities.toolkit.registry import get_registry

class ToolActivatorTool(BaseTool):


    @property
    def name(self) -> str:
        return "tool_activator"

    @property
    def description(self) -> str:
        return (
            "动态加载非核心工具的 schema 到本次会话。"
            "当你需要使用 http_fetch / code_exec / json_ops / db_ops / git_ops 等扩展工具时，"
            "先用 action=list 查看可用列表，再用 action=activate 传入 tool_names 加载所需工具。"
            "激活后下一轮推理即可直接调用。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "tool_activator",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["list", "activate"],
                            "description": "list=列出可激活工具；activate=激活指定工具",
                        },
                        "tool_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "要激活的工具名列表（仅 action=activate 时必填）",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "list")

        ctx = kwargs.get("_context")

        registry = get_registry()

        if action == "list":
            catalog = registry.get_extended_tool_catalog()
            if not catalog:
                return ToolResult(success=True, output="（无可激活的扩展工具）")
            lines = ["可激活的扩展工具："]
            for item in catalog:
                lines.append(f"- `{item['name']}`: {item['description']}")
            lines.append("\n使用 action=activate + tool_names=[...] 加载所需工具。")
            return ToolResult(success=True, output="\n".join(lines))

        if action == "activate":
            tool_names = kwargs.get("tool_names") or []
            if not isinstance(tool_names, list) or not tool_names:
                return ToolResult(success=False, error="tool_names 必须是非空字符串数组")

            schemas = registry.get_schemas(tool_names)
            if not schemas:
                return ToolResult(
                    success=False,
                    error=f"未找到任何可激活的工具：{tool_names}",
                )

            if ctx is None:

                return ToolResult(
                    success=False,
                    error="未注入会话上下文，无法完成激活",
                )

            ctx.activate_tools(schemas, craft_id="tool_activator")
            activated = [s["function"]["name"] for s in schemas]
            return ToolResult(
                success=True,
                output=f"已激活工具: {', '.join(activated)}。下一轮推理即可调用。",
                data={"activated": activated},
            )

        return ToolResult(success=False, error=f"未知 action: {action}")
