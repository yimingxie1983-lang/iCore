

from __future__ import annotations

from typing import Any

import structlog

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

logger = structlog.get_logger()

class ActivateCraftTool(BaseTool):


    @property
    def name(self) -> str:
        return "activate_craft"

    @property
    def description(self) -> str:
        return (
            "临时激活一个 craft 在自己（或指定 agent）身上跑一次性任务（Mode B）。"
            "等价于 summon(body=self, soul=craft_id, isolation=True)，"
            "不污染调用方主对话历史，工具白名单自动按 body∩craft 收窄。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "activate_craft",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "craft_id": {
                            "type": "string",
                            "description": "要激活的 craft id（必须存在于三层库任一层）",
                        },
                        "task": {
                            "type": "string",
                            "description": "本次激活要完成的具体任务（自然语言）",
                        },
                        "agent_id": {
                            "type": "string",
                            "description": (
                                "可选：要给哪个 agent 临时戴上 craft 的帽子。"
                                "默认空串=用调用方自己（master 使用即 claw_master）。"
                            ),
                            "default": "",
                        },
                        "task_kind": {
                            "type": "string",
                            "description": "可选任务种类，用于日志关联，不影响执行",
                            "default": "",
                        },
                    },
                    "required": ["craft_id", "task"],
                },
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        craft_id = (kwargs.get("craft_id") or "").strip()
        task = (kwargs.get("task") or "").strip()
        agent_id_arg = (kwargs.get("agent_id") or "").strip()

        if not craft_id:
            return ToolResult(success=False, error="craft_id 不能为空")
        if not task:
            return ToolResult(success=False, error="task 不能为空")


        caller_id = (kwargs.get("agent_id_caller") or kwargs.get("agent_id") or "").strip()
        body = agent_id_arg or caller_id or "claw_master"


        from cancer_claw.agent.engine.summon import summon, SummonRequest

        req = SummonRequest(
            body=body,
            soul=craft_id,
            task=task,
            isolation=True,
        )

        logger.info(
            "activate_craft_invoked",
            body=body,
            soul=craft_id,
            task_preview=task[:80],
        )

        result = await summon(req)


        if result.success:
            output = (
                f"[activate_craft] body={body} soul={craft_id} 完成。\n"
                f"耗时={int(result.duration_ms)}ms iter={result.iterations} "
                f"tokens={result.prompt_tokens + result.completion_tokens}\n"
                f"摘要：{result.summary or '(无)'}\n"
                f"内容（前 1KB）：{(result.content or '')[:1000]}"
            )
        else:
            output = (
                f"[activate_craft] 失败：{result.error}\n"
                f"body={body} soul={craft_id} duration={int(result.duration_ms)}ms"
            )

        return ToolResult(
            success=result.success,
            output=output,
            data={
                "request_id": result.request_id,
                "body": body,
                "soul": craft_id,
                "success": result.success,
                "content": (result.content or "")[:4000],
                "json_output": result.json_output,
                "artifacts": result.artifacts,
                "summary": result.summary,
                "iterations": result.iterations,
                "duration_ms": result.duration_ms,
                "schema_valid": result.schema_valid,
                "error": result.error,
            },
            error=result.error or "",
        )
