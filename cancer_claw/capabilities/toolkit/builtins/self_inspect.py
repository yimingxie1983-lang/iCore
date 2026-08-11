

from __future__ import annotations

import time
from typing import Any

import structlog

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

logger = structlog.get_logger(__name__)

def _inspect_identity(parent_agent: Any) -> dict:

    from cancer_claw.config import settings
    from cancer_claw.capabilities.toolkit.workspace import get_tool_workspace

    base = {
        "agent_id": "unknown",
        "agent_name": "unknown",
        "active_channel_role": "owner",
        "project_root": settings.project_root,
        "now_unix": int(time.time()),
    }

    if parent_agent is not None:
        base["agent_id"] = getattr(parent_agent, "id", "unknown")
        base["agent_name"] = getattr(parent_agent, "name", "unknown")
        base["active_channel_role"] = getattr(
            parent_agent, "_active_channel_role", "owner",
        )

    ws = get_tool_workspace()
    if ws and ws.extra_allow_roots:
        base["extra_allow_paths"] = [str(p) for p in ws.extra_allow_roots]

    return base

def _inspect_tools() -> dict:

    from cancer_claw.capabilities.toolkit.registry import CORE_TOOL_NAMES, get_registry

    registry = get_registry()
    core: list[dict] = []
    activatable: list[dict] = []

    for name, tool in registry._tools.items():
        entry = {
            "name": name,
            "description": (tool.description or "")[:160],
        }
        if name in CORE_TOOL_NAMES:
            core.append(entry)
        else:
            activatable.append(entry)

    core.sort(key=lambda x: x["name"])
    activatable.sort(key=lambda x: x["name"])

    return {
        "core": core,
        "activatable": activatable,
        "total": len(core) + len(activatable),
    }

def _inspect_environment() -> dict:

    from cancer_claw.config import settings

    providers_safe: list[dict] = []
    for p in (settings.providers or []):
        providers_safe.append({
            "id": getattr(p, "id", ""),
            "model": getattr(p, "model", "") or getattr(p, "default_model", ""),
            "base_url": getattr(p, "base_url", ""),
        })

    return {
        "app": {
            "name": settings.app.name,
            "version": settings.app.version,
            "debug": settings.app.debug,
        },
        "context_budget": {
            "max_tokens": getattr(settings.context, "max_tokens", None),
            "trim_threshold": getattr(settings.context, "trim_threshold", None),
        },
        "memory": {
            "enabled": getattr(settings.memory, "enabled", True),
        },
        "craft": {
            "enabled": getattr(settings.craft, "enabled", True),
        },
        "evolution": {
            "enabled": getattr(settings.evolution, "enabled", True),
        },
        "providers": providers_safe,
    }

_VALID_SCOPES: set[str] = {"identity", "tools", "environment", "all"}

class SelfInspectTool(BaseTool):


    @property
    def name(self) -> str:
        return "self_inspect"

    @property
    def description(self) -> str:
        return (
            "Agent 自检：查看自己当前的身份、可调用的工具、配置环境。"
            "需要主动判断或确认运行时状态时使用。返回结构稳定。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "self_inspect",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "scope": {
                            "type": "string",
                            "enum": sorted(_VALID_SCOPES),
                            "description": (
                                "查看哪一面：identity 身份 / tools 工具清单 / "
                                "environment 环境配置 / all 全部。不传默认 all。"
                            ),
                        },
                    },
                    "required": [],
                },
            },
        }

    async def execute(self, **kwargs) -> ToolResult:
        scope = (kwargs.get("scope") or "all").strip().lower()
        if scope not in _VALID_SCOPES:
            return ToolResult(
                success=False,
                error=(
                    f"scope={scope!r} 不合法。可选值：{sorted(_VALID_SCOPES)}"
                ),
            )

        parent = kwargs.get("_parent_agent")

        data: dict[str, Any] = {}
        try:
            if scope in ("identity", "all"):
                data["identity"] = _inspect_identity(parent)
            if scope in ("tools", "all"):
                data["tools"] = _inspect_tools()
            if scope in ("environment", "all"):
                data["environment"] = _inspect_environment()
        except Exception as e:
            logger.warning("self_inspect_failed", scope=scope, error=str(e))
            return ToolResult(
                success=False,
                error=f"self_inspect 收集 scope={scope} 时失败：{type(e).__name__}: {e}",
            )

        preview = self._render_preview(data)

        return ToolResult(
            success=True,
            output=preview,
            data=data,
        )

    @staticmethod
    def _render_preview(data: dict) -> str:

        lines: list[str] = []

        if "identity" in data:
            ident = data["identity"]
            lines.append(
                f"[identity] {ident.get('agent_name')}#{ident.get('agent_id')} "
                f"role={ident.get('active_channel_role')} "
                f"project={ident.get('project_root')}"
            )
            extras = ident.get("extra_allow_paths")
            if extras:
                lines.append(
                    f"[extra_paths] 额外可访问路径（绝对路径直接用）: "
                    + ", ".join(extras)
                )

        if "tools" in data:
            t = data["tools"]
            lines.append(
                f"[tools] core={len(t['core'])} "
                f"activatable={len(t['activatable'])} "
                f"(total={t['total']})"
            )

        if "environment" in data:
            env = data["environment"]
            providers = ",".join(
                p["id"] for p in env.get("providers", []) if p.get("id")
            )
            lines.append(
                f"[env] {env['app']['name']} v{env['app']['version']} "
                f"providers=[{providers}]"
            )

        return "\n".join(lines) if lines else "(empty)"
