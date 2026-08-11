

from __future__ import annotations

from typing import Any

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

class ProjectLookupTool(BaseTool):
    name = "project_lookup"
    description = (
        "按项目名称解析项目 id（仅在你有权限访问的项目内查找）。"
        "当用户用项目名（而不是 id）指代某个项目时先用它拿到 id；"
        "若返回多个候选，请向用户澄清具体是哪一个，不要臆断。"
    )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "项目名称或其中的关键词（模糊匹配，不区分大小写）",
                        }
                    },
                    "required": ["name"],
                },
            },
        }

    async def execute(self, **kwargs) -> ToolResult:
        name = (kwargs.get("name") or "").strip()
        current_user: dict[str, Any] | None = kwargs.get("_current_user")
        if not name:
            return ToolResult(success=False, error="请提供要查找的项目名称。")
        if not current_user:
            return ToolResult(
                success=False,
                error="无登录用户上下文，无法按名称解析项目（请通过项目对话接口调用）。",
            )

        from cancer_claw.services.identity import repo as auth_repo

        candidates = await auth_repo.find_projects_by_name(current_user, name)
        if not candidates:
            return ToolResult(
                success=True,
                output=f"没有找到名称匹配「{name}」且你有权限访问的项目。",
                data={"candidates": []},
            )
        lines = [
            f"{i+1}. {c['name']}（id={c['id']}，你的角色={c['role']}）"
            for i, c in enumerate(candidates)
        ]
        note = "" if len(candidates) == 1 else "\n存在多个候选，请与用户确认具体是哪一个后再用 project_open 打开。"
        return ToolResult(
            success=True,
            output="匹配到以下项目：\n" + "\n".join(lines) + note,
            data={"candidates": candidates},
        )

class ProjectOpenTool(BaseTool):
    name = "project_open"
    description = (
        "把当前对话的工作区切换到指定项目（按项目 id，或唯一匹配的项目名称）。"
        "切换后 file_ops / shell_exec / 记忆等工具将作用于该项目。"
        "仅能打开你有权限访问的项目；若按名称匹配到多个项目会拒绝，请先用 project_lookup 澄清。"
    )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "project_id": {
                            "type": "string",
                            "description": "目标项目 id（优先；若已知 id 直接传）",
                        },
                        "name": {
                            "type": "string",
                            "description": "目标项目名称（当未提供 id 时按名称唯一匹配）",
                        },
                    },
                },
            },
        }

    async def execute(self, **kwargs) -> ToolResult:
        project_id = (kwargs.get("project_id") or "").strip()
        name = (kwargs.get("name") or "").strip()
        current_user: dict[str, Any] | None = kwargs.get("_current_user")
        agent = kwargs.get("_agent")

        if not current_user:
            return ToolResult(
                success=False,
                error="无登录用户上下文，无法切换项目（请通过项目对话接口调用）。",
            )
        if agent is None:
            return ToolResult(success=False, error="内部错误：缺少 agent 引用，无法切换工作区。")
        if not project_id and not name:
            return ToolResult(success=False, error="请提供 project_id 或项目 name。")

        from cancer_claw.services.identity import repo as auth_repo
        from cancer_claw.services.identity.deps import compute_project_role


        target_name = name
        if not project_id:
            candidates = await auth_repo.find_projects_by_name(current_user, name)
            if not candidates:
                return ToolResult(
                    success=False,
                    error=f"没有找到名称匹配「{name}」且你有权限访问的项目。",
                )
            if len(candidates) > 1:
                lines = [f"- {c['name']}（id={c['id']}）" for c in candidates]
                return ToolResult(
                    success=False,
                    error="名称匹配到多个项目，请用 project_lookup 与用户确认后再传具体 id：\n"
                    + "\n".join(lines),
                )
            project_id = candidates[0]["id"]
            target_name = candidates[0]["name"]


        project, role = await compute_project_role(current_user, project_id)
        if project is None or role is None:
            return ToolResult(
                success=False,
                error=f"项目 {project_id} 不存在，或你没有访问权限。",
            )

        await agent.bind_tool_workspace(project_id)

        bound = getattr(agent, "_bound_workspace", None)
        if bound is None or getattr(bound, "project_id", None) != project_id:
            return ToolResult(success=False, error=f"切换到项目 {project_id} 失败。")

        return ToolResult(
            success=True,
            output=(
                f"已切换到项目「{target_name or project_id}」（id={project_id}，你的角色={role}）。"
                f"后续文件 / 命令 / 记忆操作都作用于该项目。"
            ),
            data={"project_id": project_id, "name": target_name, "role": role},
        )
