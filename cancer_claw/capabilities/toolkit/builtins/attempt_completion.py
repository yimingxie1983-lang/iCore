

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

class AttemptCompletionTool(BaseTool):


    @property
    def name(self) -> str:
        return "attempt_completion"

    @property
    def description(self) -> str:
        return (
            "声明任务完成。仅当整个任务真正完成、可交付给用户时调用。"
            "result 参数放给用户看的最终回复（总结 + 产出位置 + 后续建议）。"
            "这是退出 agent loop 的唯一信号；中途阶段性进展不要调用。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "attempt_completion",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "result": {
                            "type": "string",
                            "description": (
                                "要展示给用户的最终回复内容。应包含："
                                "①任务结果摘要；②关键产出/文件位置；③必要的后续建议。"
                                "用自然中文，避免空话。"
                            ),
                        },
                    },
                    "required": ["result"],
                },
            },
        }

    async def execute(self, result: str = "") -> ToolResult:

        result = (result or "").strip()
        if not result:
            return ToolResult(
                success=False,
                output="",
                error=(
                    "attempt_completion 必须提供非空的 result 参数。"
                    "请把要给用户看的最终回复内容放进 result。"
                ),
            )
        return ToolResult(
            success=True,
            output=f"已声明任务完成（{len(result)} 字最终回复）。",
            data={"completion_result": result},
        )
