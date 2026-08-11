

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import structlog

from cancer_claw.config import settings
from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

logger = structlog.get_logger()

_MAX_CONTENT_LEN = 500
_VALID_SECTIONS = ("决策", "事实", "踩坑", "待办", "概述")

class MemoryWriteTool(BaseTool):


    @property
    def name(self) -> str:
        return "memory_write"

    @property
    def description(self) -> str:
        return (
            "在对话过程中即时向项目核心记忆（MEMORY.md）追加关键信息。"
            "用于记录重要决策、事实发现、踩坑记录或待办事项，"
            "确保跨对话不丢失关键上下文。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "memory_write",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "section": {
                            "type": "string",
                            "enum": list(_VALID_SECTIONS),
                            "description": (
                                "写入的记忆分区：\n"
                                "- 决策：用户拍板的选择（技术选型、方案确认等）\n"
                                "- 事实：项目关键事实（数据路径、环境约束、API 格式等）\n"
                                "- 踩坑：真实遇到的问题 + 根因 + 解法\n"
                                "- 待办：未完成需后续接续的事项\n"
                                "- 概述：项目整体背景（首次使用时写入）"
                            ),
                        },
                        "content": {
                            "type": "string",
                            "description": (
                                "要写入的内容，用精炼的 bullet point 格式（每行以 - 开头）。"
                                "不超过 500 字。只写关键信息，不要写对话流。"
                            ),
                        },
                    },
                    "required": ["section", "content"],
                },
            },
        }

    async def execute(self, **kwargs) -> ToolResult:
        section = kwargs.get("section", "")
        content = kwargs.get("content", "")
        project_id = kwargs.get("project_id", "")

        if not project_id:
            return ToolResult(
                success=False,
                error="缺少 project_id，无法定位项目记忆目录",
            )

        if section not in _VALID_SECTIONS:
            return ToolResult(
                success=False,
                error=f"无效的 section：{section}，需要是 {_VALID_SECTIONS} 之一",
            )

        if not content or not content.strip():
            return ToolResult(
                success=False,
                error="content 不能为空",
            )


        if len(content) > _MAX_CONTENT_LEN:
            content = content[:_MAX_CONTENT_LEN] + "\n- ...（内容过长已截断）"


        projects_dir = Path(settings.paths.projects_dir)
        if not projects_dir.is_absolute():
            projects_dir = (Path.cwd() / projects_dir).resolve()
        memory_path = projects_dir / project_id / "memory" / "MEMORY.md"

        try:
            memory_path.parent.mkdir(parents=True, exist_ok=True)

            ts = datetime.now(timezone.utc).strftime("%m-%d %H:%M")
            section_header = f"## {section}"
            entry = f"\n\n{section_header}（{ts}）\n\n{content.strip()}\n"

            with memory_path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(entry)

            logger.info(
                "memory_write_success",
                project_id=project_id,
                section=section,
                content_len=len(content),
            )
            return ToolResult(
                success=True,
                output=f"已写入项目记忆 [{section}]（{len(content.strip())} 字）",
            )
        except Exception as e:
            logger.warning(
                "memory_write_failed",
                project_id=project_id,
                section=section,
                error=str(e),
            )
            return ToolResult(
                success=False,
                error=f"写入失败：{e}",
            )
