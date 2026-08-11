

from __future__ import annotations

import structlog
from cancer_claw.capabilities.toolkit.base import BaseTool

logger = structlog.get_logger()

CORE_TOOL_NAMES: set[str] = {
    "file_ops",
    "shell_exec",
    "ask_user",
    "memory_recall",
    "memory_write",
    "tool_activator",







    "attempt_completion",


    "task_charter",





    "craft_search",
    "activate_craft",
    "http_fetch",


    "self_inspect",






    "present_file",




    "pubmed_search",
    "citation_resolve",


    "skill_resource",


    "pptx_read",


    "project_lookup",
    "project_open",
}

MAIN_LOOP_SYSTEM_TOOLS: set[str] = {
    "enter_plan_mode",
    "exit_plan_mode",
    "as_persona",
    "switch_persona",
    "dispatch_squad",
    "convene_council",



    "list_personas",
}

CODER_PERSONA_TOOLS: set[str] = {

    "file_ops",
    "shell_exec",
    "ask_user",
    "memory_recall",
    "memory_write",
    "tool_activator",
    "attempt_completion",
    "task_charter",

    "craft_search",
    "activate_craft",
    "http_fetch",
    "self_inspect",

    "code_exec",
    "git_ops",
    "text_ops",
    "json_ops",



    "present_file",

    "pubmed_search",
    "citation_resolve",
    "skill_resource",
    "pptx_read",
}

ML_ENGINEER_PERSONA_TOOLS: set[str] = {
    "file_ops",
    "shell_exec",
    "code_exec",
    "ask_user",
    "memory_recall",
    "memory_write",
    "tool_activator",
    "attempt_completion",
    "task_charter",
    "craft_search",
    "activate_craft",
    "http_fetch",
    "self_inspect",
    "present_file",
    "pubmed_search",
    "citation_resolve",
    "skill_resource",
    "pptx_read",


}

_PERSONA_TOOL_SETS: dict[str, set[str]] = {
    "coder": CODER_PERSONA_TOOLS,
    "ml_engineer": ML_ENGINEER_PERSONA_TOOLS,
}

PLAN_MODE_VISIBLE_TOOLS: set[str] = {
    "file_ops",

    "task_charter",
    "ask_user",
    "memory_recall",
    "memory_write",
    "craft_search",
    "tool_activator",
    "self_inspect",
    "http_fetch",
    "text_ops",
    "json_ops",
    "exit_plan_mode",
    "attempt_completion",
}

PLAN_MODE_ALLOWED_ACTIONS: dict[str, set[str]] = {
    "file_ops": {"read_file", "list_dir", "exists", "glob"},

    "task_charter": {"read"},
}

SUBAGENT_ONLY_TOOLS: set[str] = set()

class ToolRegistry:


    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):

        self._tools[tool.name] = tool
        logger.debug("tool_registered", name=tool.name)

    def unregister(self, tool_name: str):
        if tool_name in self._tools:
            del self._tools[tool_name]

    def get_tool(self, tool_name: str) -> BaseTool | None:
        return self._tools.get(tool_name)

    def get_schema(self, tool_name: str) -> dict | None:
        tool = self._tools.get(tool_name)
        if tool:
            return tool.get_schema()
        return None

    def get_schemas(self, tool_names: list[str]) -> list[dict]:

        schemas = []
        for name in tool_names:
            schema = self.get_schema(name)
            if schema:
                schemas.append(schema)
        return schemas

    def get_all_schemas(self) -> list[dict]:

        return [tool.get_schema() for tool in self._tools.values()]

    def get_core_schemas(
        self,
        agent_id: str | None = None,
        persona_id: str | None = None,
        depth: int = 0,
    ) -> list[dict]:

        names = self._compute_core_names(agent_id, persona_id, depth)
        return [
            tool.get_schema()
            for name, tool in self._tools.items()
            if name in names
        ]

    def get_core_tool_names(
        self,
        agent_id: str | None = None,
        persona_id: str | None = None,
        depth: int = 0,
    ) -> set[str]:

        names = self._compute_core_names(agent_id, persona_id, depth)

        return {n for n in names if n in self._tools}

    def _compute_core_names(
        self,
        agent_id: str | None,
        persona_id: str | None,
        depth: int,
    ) -> set[str]:


        if persona_id and persona_id in _PERSONA_TOOL_SETS:
            names = set(_PERSONA_TOOL_SETS[persona_id])
        else:
            names = set(CORE_TOOL_NAMES)



        if depth == 0:
            names |= MAIN_LOOP_SYSTEM_TOOLS
        else:
            names |= SUBAGENT_ONLY_TOOLS



        _ = agent_id
        return names

    def get_extended_tool_catalog(self) -> list[dict]:

        excluded = CORE_TOOL_NAMES | MAIN_LOOP_SYSTEM_TOOLS | SUBAGENT_ONLY_TOOLS
        return [
            {"name": name, "description": tool.description}
            for name, tool in sorted(self._tools.items())
            if name not in excluded
        ]

    def list_tools(self) -> list[dict]:

        return [
            {"name": tool.name, "description": tool.description}
            for tool in self._tools.values()
        ]

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    @property
    def count(self) -> int:
        return len(self._tools)

def _register_builtins(registry: ToolRegistry):

    from cancer_claw.capabilities.toolkit.builtins.file_ops import FileOpsTool
    from cancer_claw.capabilities.toolkit.builtins.shell_exec import ShellExecTool
    from cancer_claw.capabilities.toolkit.builtins.http_fetch import HttpFetchTool
    from cancer_claw.capabilities.toolkit.builtins.code_exec import CodeExecTool
    from cancer_claw.capabilities.toolkit.builtins.text_ops import TextOpsTool
    from cancer_claw.capabilities.toolkit.builtins.json_ops import JsonOpsTool
    from cancer_claw.capabilities.toolkit.builtins.db_ops import DbOpsTool
    from cancer_claw.capabilities.toolkit.builtins.git_ops import GitOpsTool
    from cancer_claw.capabilities.toolkit.builtins.archive_ops import ArchiveOpsTool
    from cancer_claw.capabilities.toolkit.builtins.env_ops import EnvOpsTool
    from cancer_claw.capabilities.toolkit.builtins.process_ops import ProcessOpsTool
    from cancer_claw.capabilities.toolkit.builtins.ask_user import AskUserTool
    from cancer_claw.capabilities.toolkit.builtins.memory_recall import MemoryRecallTool
    from cancer_claw.capabilities.toolkit.builtins.memory_write import MemoryWriteTool
    from cancer_claw.capabilities.toolkit.builtins.tool_activator import ToolActivatorTool
    from cancer_claw.capabilities.toolkit.builtins.scratchpad import ScratchpadTool
    from cancer_claw.capabilities.toolkit.builtins.stop_background_monitor import StopBackgroundMonitorTool
    from cancer_claw.capabilities.toolkit.builtins.browser_verify import BrowserVerifyTool
    from cancer_claw.capabilities.toolkit.builtins.contract_codegen import ContractCodegenTool
    from cancer_claw.capabilities.toolkit.builtins.craft_search import CraftSearchTool
    from cancer_claw.capabilities.toolkit.builtins.activate_craft import ActivateCraftTool
    from cancer_claw.capabilities.toolkit.builtins.plan_mode import EnterPlanModeTool, ExitPlanModeTool
    from cancer_claw.capabilities.toolkit.builtins.attempt_completion import AttemptCompletionTool
    from cancer_claw.capabilities.toolkit.builtins.self_inspect import SelfInspectTool
    from cancer_claw.capabilities.toolkit.builtins.session_history import SessionHistoryTool
    from cancer_claw.capabilities.toolkit.builtins.as_persona import AsPersonaTool
    from cancer_claw.capabilities.toolkit.builtins.switch_persona import SwitchPersonaTool
    from cancer_claw.capabilities.toolkit.builtins.list_personas import ListPersonasTool
    from cancer_claw.capabilities.toolkit.builtins.task_charter import TaskCharterTool
    from cancer_claw.capabilities.toolkit.builtins.citation_resolve import CitationResolveTool
    from cancer_claw.capabilities.toolkit.builtins.present_file import PresentFileTool
    from cancer_claw.capabilities.toolkit.builtins.pubmed_search import PubMedSearchTool
    from cancer_claw.capabilities.toolkit.builtins.dispatch_squad import DispatchSquadTool
    from cancer_claw.capabilities.toolkit.builtins.convene_council import ConveneCouncilTool
    from cancer_claw.capabilities.toolkit.builtins.skill_resource import SkillResourceTool
    from cancer_claw.capabilities.toolkit.builtins.pptx_read import PptxReadTool
    from cancer_claw.capabilities.toolkit.builtins.project_access import (
        ProjectLookupTool,
        ProjectOpenTool,
    )

    builtins = [
        FileOpsTool(),
        ShellExecTool(),
        HttpFetchTool(),
        CodeExecTool(),
        TextOpsTool(),
        JsonOpsTool(),
        DbOpsTool(),
        GitOpsTool(),
        ArchiveOpsTool(),
        EnvOpsTool(),
        ProcessOpsTool(),
        AskUserTool(),
        MemoryRecallTool(),
        MemoryWriteTool(),
        ToolActivatorTool(),
        ScratchpadTool(),
        StopBackgroundMonitorTool(),
        BrowserVerifyTool(),
        ContractCodegenTool(),
        CraftSearchTool(),
        ActivateCraftTool(),
        EnterPlanModeTool(),
        ExitPlanModeTool(),
        AttemptCompletionTool(),
        SelfInspectTool(),
        SessionHistoryTool(),
        AsPersonaTool(),
        SwitchPersonaTool(),
        ListPersonasTool(),
        TaskCharterTool(),
        CitationResolveTool(),
        PresentFileTool(),
        PubMedSearchTool(),
        DispatchSquadTool(),
        ConveneCouncilTool(),
        SkillResourceTool(),
        PptxReadTool(),
        ProjectLookupTool(),
        ProjectOpenTool(),
    ]

    for tool in builtins:
        registry.register(tool)

    logger.info("builtin_tools_registered", count=len(builtins),
                tools=[t.name for t in builtins])

_registry: ToolRegistry | None = None

def get_registry() -> ToolRegistry:

    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_builtins(_registry)
    return _registry

def reset_registry():

    global _registry
    _registry = None
