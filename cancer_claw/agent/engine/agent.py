

from __future__ import annotations

import ast
import asyncio
import contextlib
import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator

import structlog

from cancer_claw.config import settings

from cancer_claw.agent.adaptation import EvolutionFactory, EvolutionRouteContext

from cancer_claw.agent.adaptation.auto_save import save_evolved_memory

from cancer_claw.agent.context_window.manager import ContextManager
from cancer_claw.agent.engine.state_machine import StateMachine, AgentState

from cancer_claw.agent.recall import WorkingMemory, MemoryWriter

from cancer_claw.agent.recall.working import looks_like_ts_only, strip_ts_prefix
from cancer_claw.resources.prompt_templates import load_prompt
from cancer_claw.services.model_router.schema import ChatRequest, ChatResponse
from cancer_claw.services.model_router.strategy import get_router
from cancer_claw.capabilities.toolkit.base import ToolResult
from cancer_claw.capabilities.toolkit.registry import get_registry
from cancer_claw.capabilities.toolkit.workspace import ToolWorkspaceContext, build_workspace_for_project, tool_workspace_scope

logger = structlog.get_logger()

MAX_ITERATIONS = 10000

def build_assistant_pretext_event(
    content: str | None,
    tool_calls: list[dict] | None,
) -> dict | None:

    if not tool_calls:
        return None



    pretext = strip_ts_prefix(content or "").strip()
    if not pretext:
        return None
    return {
        "type": "assistant_pretext",
        "content": pretext,
        "tool_call_ids": [tc["id"] for tc in tool_calls],
    }

def _messages_have_image(messages: list[dict]) -> bool:

    for msg in messages or []:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                return True
    return False

def _safe_parse_python_kwargs(args_str: str) -> dict | None:

    if not args_str.strip():
        return {}
    try:

        tree = ast.parse(f"_d_({args_str})", mode="eval")
    except SyntaxError:
        return None
    if not isinstance(tree.body, ast.Call):
        return None

    def _to_value(node: ast.AST) -> tuple[Any, bool]:
        if isinstance(node, ast.Constant):
            return node.value, True
        if isinstance(node, (ast.List, ast.Tuple)):
            vals: list[Any] = []
            for el in node.elts:
                v, ok = _to_value(el)
                if not ok:
                    return None, False
                vals.append(v)
            return (vals if isinstance(node, ast.List) else tuple(vals)), True
        if isinstance(node, ast.Dict):
            d: dict[Any, Any] = {}
            for k_node, v_node in zip(node.keys, node.values):
                k_val, ok = _to_value(k_node) if k_node is not None else (None, True)
                if not ok:
                    return None, False
                v_val, ok = _to_value(v_node)
                if not ok:
                    return None, False
                d[k_val] = v_val
            return d, True

        return None, False

    out: dict[str, Any] = {}
    for kw in tree.body.keywords:
        if not kw.arg:
            return None
        v, ok = _to_value(kw.value)
        if not ok:
            return None
        out[kw.arg] = v
    return out

def _parse_one_inline_tool_call(raw: str) -> dict | None:

    raw = raw.strip().rstrip(",").strip()
    if not raw:
        return None


    if raw.startswith("{"):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict) and "name" in obj:
            args_val = obj.get("arguments", {})
            args_str = (
                args_val if isinstance(args_val, str)
                else json.dumps(args_val, ensure_ascii=False)
            )
            return {
                "id": f"call_inline_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {"name": str(obj["name"]), "arguments": args_str},
            }


    m = re.match(r"^([\w.]+)\s*\((.*)\)\s*$", raw, re.DOTALL)
    if m:
        tool_name = m.group(1)
        args_part = m.group(2).strip()
        kwargs = _safe_parse_python_kwargs(args_part)
        if kwargs is not None:
            return {
                "id": f"call_inline_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(kwargs, ensure_ascii=False),
                },
            }

    return None

def _parse_inline_tool_calls(content: str) -> list[dict]:

    out: list[dict] = []
    i = 0
    n = len(content)
    while True:
        start = content.find("<tool_call>", i)
        if start < 0:
            break
        body_start = start + len("<tool_call>")

        end_close = content.find("</tool_call>", body_start)
        end_next = content.find("<tool_call>", body_start)
        candidates = [x for x in (end_close, end_next) if x >= 0]
        end = min(candidates) if candidates else n
        block = content[body_start:end].strip()
        tc = _parse_one_inline_tool_call(block) if block else None
        if tc:
            out.append(tc)

        if end_close >= 0 and end == end_close:
            i = end + len("</tool_call>")
        else:
            i = end
    return out

def _reduce_scratchpad_sections_to_plan(
    sections: dict[str, list[str]],
    max_lines_per_section: int = 30,
) -> str:


    def _extract_task_entries(section_lines: list[str]) -> list[str]:
        out: list[str] = []
        for ln in section_lines:
            s = ln.strip()
            if not s.startswith("- ["):
                continue

            content = s[6:].strip() if len(s) > 6 else ""
            if content:
                out.append(content)
        return out

    todos = _extract_task_entries(sections.get("TODO", []))
    doings = _extract_task_entries(sections.get("DOING", []))
    dones = _extract_task_entries(sections.get("DONE", []))

    if not (todos or doings or dones):
        return ""

    chunks: list[str] = []
    if doings:
        chunks.append("### 进行中（DOING）")
        for line in doings[:max_lines_per_section]:
            chunks.append(f"- ▷ {line}")
    if todos:
        if chunks:
            chunks.append("")
        chunks.append("### 待办（TODO）")
        for line in todos[:max_lines_per_section]:
            chunks.append(f"- □ {line}")
    if dones:
        if chunks:
            chunks.append("")
        recent_dones = dones[-max_lines_per_section:]
        chunks.append(f"### 已完成（DONE，最近 {len(recent_dones)} 条）")
        for line in recent_dones:
            chunks.append(f"- ✓ {line}")

    return "\n".join(chunks)

class Agent:


    def __init__(
        self,
        agent_id: str | None = None,
        name: str = "智能体",
        description: str = "",
        soul_path: str | None = None,
        craft_ids: list[str] | None = None,
    ):

        self.id = agent_id or uuid.uuid4().hex[:12]
        self.name = name
        self.description = description
        self.soul_path = soul_path
        self.craft_ids = craft_ids or []


        self._state_machine = StateMachine(AgentState.CREATED)
        self._context = ContextManager()
        self._soul_content: str = ""


        self._total_tokens = 0
        self._model_calls = 0
        self._tool_calls = 0




        self._consecutive_text_only = 0


        self._working_memory: WorkingMemory | None = None


        self._bound_workspace: ToolWorkspaceContext | None = None

        self._bound_project_name: str | None = None

        self._evolution_project_id: str | None = None


        self._current_user: dict | None = None

        self._tool_usage_this_turn: dict[str, int] = {}






        self._charter_stage_just_advanced: bool = False
        self._charter_stage_done_index: int = 0
        self._charter_stage_done_name: str = ""







        self._current_session_id: str | None = None
















        self._chat_lock: "asyncio.Lock" = asyncio.Lock()











        self._delegator: "Agent | None" = None
        self._event_sink: "asyncio.Queue | None" = None
        self._depth: int = 0




        self.lifecycle: str = "active"




        self.personal_crafts_dir: Path = (
            Path(settings.paths.agents_dir) / self.id / "crafts"
        )

        self.personal_crafts_dir.mkdir(parents=True, exist_ok=True)







        self.mode: str = "execute"





        self.active_persona_id: str | None = None





    @property
    def state(self) -> AgentState:

        return self._state_machine.state

    @property
    def context(self) -> ContextManager:

        return self._context

    @property
    def stats(self) -> dict:

        return {
            "agent_id": self.id,
            "name": self.name,
            "state": self.state.value,
            "total_tokens": self._total_tokens,
            "model_calls": self._model_calls,
            "tool_calls": self._tool_calls,
            "context": self._context.get_stats(),
        }

    def default_tool_names(self) -> set[str]:

        registry = get_registry()
        return registry.get_core_tool_names(
            agent_id=self.id,
            persona_id=self.active_persona_id,
            depth=self._depth,
        )





    async def initialize(self):


        if self.soul_path:
            soul_file = Path(self.soul_path)
            if soul_file.exists():
                self._soul_content = soul_file.read_text(encoding="utf-8")
                logger.info("soul_loaded", agent=self.name, path=self.soul_path)
            else:
                logger.warning("soul_file_not_found", agent=self.name, path=self.soul_path)


        self._context.set_system_prompt(
            framework=load_prompt("framework_system"),
            soul=self._soul_content,
        )



        try:
            from cancer_claw.resources.knowledge.catalog import build_craft_l1_markdown
            craft_md = await build_craft_l1_markdown(include_uncertified=False)
            self._context.set_craft_index(craft_md)
            logger.info(
                "library_index_injected",
                agent=self.name,
                agent_id=self.id,
                craft_md_chars=len(craft_md),
                p5_tokens=self._context.budget.get_summary().get("p5", {}).get("used", -1),
            )
        except Exception as e:
            logger.warning("library_catalog_inject_failed", agent=self.name, error=str(e), exc_info=True)




        registry = get_registry()
        core_schemas = registry.get_core_schemas(
            agent_id=self.id, depth=self._depth
        )
        self._context.activate_tools(core_schemas)

        await self._state_machine.transition_to(AgentState.INITIALIZED, "初始化完成")
        logger.info("agent_initialized", agent=self.name, agent_id=self.id)





    async def swap_persona(self, persona_id: str) -> dict:

        from cancer_claw.agent.engine.persona import load_persona

        persona = load_persona(persona_id)
        registry = get_registry()





        old_core = registry.get_core_tool_names(
            agent_id=self.id,
            persona_id=self.active_persona_id,
            depth=self._depth,
        )
        new_core = registry.get_core_tool_names(
            agent_id=self.id,
            persona_id=persona.id,
            depth=self._depth,
        )
        tools_to_remove = sorted(old_core - new_core)
        tools_to_add = sorted(new_core - old_core)

        old_id = self.active_persona_id
        self._soul_content = persona.soul_text

        if persona.source_path is not None:
            self.soul_path = str(persona.source_path)
        self.active_persona_id = persona.id


        self._context.set_system_prompt(soul=persona.soul_text)





        if tools_to_remove:
            self._context.deactivate_tools(tools_to_remove)
        if tools_to_add:
            add_schemas = registry.get_schemas(tools_to_add)
            if add_schemas:
                self._context.activate_tools(add_schemas)

        logger.info(
            "persona_swapped",
            agent=self.name,
            agent_id=self.id,
            from_persona=old_id,
            to_persona=persona.id,
            soul_chars=len(persona.soul_text),
            tools_added=tools_to_add,
            tools_removed=tools_to_remove,
        )


        if self._event_sink is not None:
            try:
                self._event_sink.put_nowait(
                    {
                        "type": "persona_switched",
                        "agent_id": self.id,
                        "from_persona": old_id,
                        "to_persona": persona.id,
                        "name": persona.name,
                        "icon": persona.icon,
                        "depth": self._depth,
                        "tools_added": tools_to_add,
                        "tools_removed": tools_to_remove,
                    }
                )
            except Exception:
                pass

        return {
            "id": persona.id,
            "name": persona.name,
            "description": persona.description,
            "icon": persona.icon,
            "soul_chars": len(persona.soul_text),
            "tools_added": tools_to_add,
            "tools_removed": tools_to_remove,
        }

    @property
    def active_persona(self) -> dict | None:

        if not self.active_persona_id:
            return None
        try:
            from cancer_claw.agent.engine.persona import load_persona
            p = load_persona(self.active_persona_id)
            return {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "icon": p.icon,
                "suggested_tools": list(p.suggested_tools),
            }
        except Exception:
            return {"id": self.active_persona_id}

    async def bind_tool_workspace(self, project_id: str) -> None:

        from cancer_claw.db import get_db
        from cancer_claw.capabilities.toolkit.executor import (
            get_project_executor,
            is_sandbox_enabled,
            SandboxUnavailable,
        )

        db = await get_db()
        cursor = await db.execute("SELECT id, name FROM projects WHERE id = ?", (project_id,))
        row = await cursor.fetchone()
        if not row:
            self._bound_workspace = None
            self._bound_project_name = None
            self._evolution_project_id = None
            self._working_memory = None
            return

        self._bound_project_name = (row[1] if len(row) > 1 else None) or None


        executor = None
        if is_sandbox_enabled():
            try:
                executor = await get_project_executor(project_id)
            except SandboxUnavailable as e:

                logger.error("agent_bind_sandbox_unavailable",
                             agent_id=self.id, project_id=project_id, error=str(e))
                raise

        self._bound_workspace = build_workspace_for_project(project_id, executor=executor)
        self._evolution_project_id = project_id
        self._working_memory = WorkingMemory(project_id, self.id)



        self._refresh_project_instructions()




        self._refresh_charter()

    def _maybe_reinject_master_plan(self) -> None:

        from cancer_claw.agent.engine.system_agents import MASTER_AGENT_ID

        if self.id != MASTER_AGENT_ID:
            return
        if self._bound_workspace is None:
            return
        workspace_root = self._bound_workspace.default_relative_root
        sp_path = workspace_root / "SCRATCHPAD.md"
        if not sp_path.exists() or not sp_path.is_file():
            return
        try:
            text = sp_path.read_text(encoding="utf-8")
            from cancer_claw.capabilities.toolkit.builtins.scratchpad import _parse_sections

            sections = _parse_sections(text)
            plan_lines = _reduce_scratchpad_sections_to_plan(sections)
            if not plan_lines:
                return
            wrapped = (
                "## 当前任务进度（由黑板 SCRATCHPAD 自动归并）\n\n"
                f"{plan_lines}\n\n"
                "继续推进未完成项；完成后及时把 task_id 迁到 DONE。"
            )
            self._context.set_plan(wrapped)
            logger.info(
                "master_plan_reinjected",
                agent=self.name,
                lines_chars=len(plan_lines),
            )
        except Exception as e:
            logger.warning("master_plan_reinject_failed", error=str(e))

    def _maybe_reinject_master_environment(self) -> None:

        from cancer_claw.agent.engine.system_agents import MASTER_AGENT_ID
        if self.id != MASTER_AGENT_ID:
            return

        try:
            snapshot = self._render_master_environment_snapshot()
            self._context.set_environment_snapshot(snapshot)
            logger.debug(
                "master_environment_reinjected",
                agent=self.name,
                snapshot_chars=len(snapshot),
            )
        except Exception as e:

            logger.warning("master_environment_reinject_failed", error=str(e))

    def _render_master_environment_snapshot(self) -> str:


        role = getattr(self, "_active_channel_role", "owner")


        tool_line = ""
        try:
            from cancer_claw.capabilities.toolkit.registry import CORE_TOOL_NAMES, get_registry

            reg = get_registry()
            core_n = activatable_n = 0
            for name in reg._tools.keys():
                if name in CORE_TOOL_NAMES:
                    core_n += 1
                else:
                    activatable_n += 1

            tool_line = (
                f"- 工具：{core_n} 核心 + {activatable_n} 按需"
                "（用 self_inspect 看详情）"
            )
        except Exception:
            pass


        ws = self._bound_workspace
        if ws and getattr(ws, "project_id", None):
            pname = (self._bound_project_name or "").strip()
            if pname:
                project_line = f"- 当前项目：{pname}（{ws.project_id}）"
            else:
                project_line = f"- 当前项目：{ws.project_id}"
        else:
            project_line = "- 当前项目：（未绑定，纯对话模式）"


        extra_paths_line = ""
        if ws and getattr(ws, "extra_allow_roots", None):
            extras = [str(p) for p in ws.extra_allow_roots]
            if extras:
                extra_paths_line = (
                    "- **额外可访问路径**（文件工具可直接读写这些目录下的文件，"
                    "使用绝对路径即可）：\n"
                    + "\n".join(f"  - `{p}`" for p in extras)
                )


        lines = [
            f"- 当前对话方角色：**{role}**",
            project_line,
        ]
        if tool_line:
            lines.append(tool_line)
        if extra_paths_line:
            lines.append(extra_paths_line)
        lines.append(
            "- 需要更详细信息时调 `self_inspect`（先 tool_activator activate 再用）"
        )
        return "\n".join(lines)

    async def _build_bg_startup_summary(
        self, *, pid: int, log_path: str
    ) -> tuple[str, bool]:

        from cancer_claw.capabilities.toolkit.builtins.shell_exec import _bg_procs, ShellExecTool

        TAIL_BYTES = 8192
        entry = _bg_procs.get(pid)
        if entry is None:
            return (
                f"[框架·启动摘要] PID={pid} 已不在监控列表（可能已立刻崩掉，或非本 session 启动）",
                False,
            )





        executor = (
            self._bound_workspace.executor if self._bound_workspace else None
        )


        still_running = True
        exit_code: int | None = None
        if entry.sandboxed:
            if executor is None:
                return (
                    f"[框架·启动摘要] PID={pid} 沙箱 executor 不可用（agent 未绑定 workspace？）",
                    False,
                )
            try:
                infos = await executor.list_background()
                cur = next((i for i in infos if i.pid == pid), None)
                still_running = cur is not None and cur.status == "running"
                exit_code = (
                    cur.returncode if (cur and not still_running) else None
                )
            except Exception as _qerr:
                return (
                    f"[框架·启动摘要] PID={pid} 沙箱查询失败: {_qerr!r}",
                    False,
                )
        else:
            ec = entry.proc.poll() if entry.proc else None
            still_running = ec is None
            exit_code = ec if not still_running else None




        tail_text = ""
        log_size = 0
        log_total_lines = 0
        if log_path:
            try:
                lp = Path(log_path)
                if lp.exists():
                    log_size = lp.stat().st_size
                    with lp.open("rb") as fh:
                        if log_size > TAIL_BYTES:
                            fh.seek(-TAIL_BYTES, 2)
                            raw = fh.read()
                            tail_text = "...[尾部]\n" + raw.decode(
                                "utf-8", errors="replace"
                            )
                        else:
                            tail_text = fh.read().decode(
                                "utf-8", errors="replace"
                            )

                    try:
                        with lp.open("rb") as fh2:
                            log_total_lines = sum(1 for _ in fh2)
                    except Exception:
                        log_total_lines = 0
            except Exception as _ferr:
                tail_text = f"[读日志失败] {_ferr!r}"
        else:

            if entry.sandboxed and executor is not None:
                try:
                    out, err = await executor.read_background_output(
                        pid, max_bytes=TAIL_BYTES
                    )
                    tail_text = (out + ("\n[stderr]\n" + err if err else ""))
                except Exception as _qerr:
                    tail_text = f"[读沙箱缓冲失败] {_qerr!r}"
            elif not entry.sandboxed:
                tail_text = ShellExecTool._decode(b"".join(entry.buf))




        if still_running:
            status_line = "运行中"
            head_banner = ""
            if log_path:
                next_hint = (
                    f"服务已起来。后续按需用 "
                    f"file_ops.read_file(path=\"{log_path}\", offset={log_total_lines + 1}) "
                    f"增量读新日志（行级 offset，从下一行开始读，不要每轮都查）；"
                    f"或读尾部用 offset=-100。做健康检查/接口验证后再决定下一步。"
                )
            else:
                next_hint = (
                    "💡 服务已起来。日志文件不可用，可用 shell_exec.read_process_output "
                    f"(pid={pid}) 拉内存缓冲。"
                )
        elif exit_code == 0:
            status_line = "已退出(exit_code=0)"
            head_banner = "ℹ️ 进程正常退出（exit_code=0）。如这是预期外行为，请检查命令是否本就是短命令。\n"
            next_hint = "💡 短命令本不该用 run_background，下次用 run_command 即可。"
        else:

            status_line = f"已退出(exit_code={exit_code})"
            head_banner = (
                f"⚠️⚠️⚠️ 进程已**异常退出**（exit_code={exit_code}）。\n"
                f"必须先读完整日志找根因，禁止直接换端口/重试 —— 端口冲突只是症状，"
                f"真正的失败原因（缺依赖 / import 失败 / 配置错 / 端口被占）在日志里。\n"
            )
            if log_path:
                next_hint = (
                    f"📌 必读日志：file_ops.read_file(path=\"{log_path}\")"
                    f"（共 {log_size} 字节，全文不大可一次读完）。\n"
                    f"读完日志后：(1) 找出根因 → (2) 修代码或环境 → (3) 再起服务。\n"
                    f"⛔ 禁止：在没读完整日志、没定位根因前，就换端口/重试或写新启动脚本。"
                )
            else:
                next_hint = (
                    f"📌 必读输出：shell_exec.read_process_output(pid={pid}) 看完整错误。\n"
                    f"⛔ 禁止：没看完整错误就盲目换端口/重试。"
                )

        proc_output = (
            f"[框架·启动摘要] PID={pid} 状态: {status_line}\n"
            f"命令: {entry.command}\n"
            + (f"日志: {log_path} (size={log_size} bytes)\n" if log_path else "")
            + (head_banner if head_banner else "")
            + f"{'─'*40}\n"
            + (tail_text or "（暂无输出）")
            + f"\n{'─'*40}\n{next_hint}"
        )
        return proc_output, still_running

    def _filter_tools_for_mode(self, tools: list[dict] | None) -> list[dict] | None:

        if not tools:
            return tools
        if self.mode != "plan":
            return tools
        from cancer_claw.capabilities.toolkit.registry import PLAN_MODE_VISIBLE_TOOLS

        filtered = [
            t for t in tools
            if t.get("function", {}).get("name", "") in PLAN_MODE_VISIBLE_TOOLS
        ]
        return filtered or None

    def _refresh_charter(self) -> None:

        if self._bound_workspace is None:
            self._context.set_charter("")
            return
        workspace_root = self._bound_workspace.default_relative_root
        charter_path = workspace_root / "CHARTER.md"
        try:
            if not charter_path.exists() or not charter_path.is_file():
                self._context.set_charter("")
                return
            content = charter_path.read_text(encoding="utf-8").strip()
            if not content:
                self._context.set_charter("")
                return

            try:
                intro = load_prompt("charter_intro").strip()
                payload = f"{intro}\n\n{content}"
            except FileNotFoundError:
                payload = content
            self._context.set_charter(payload)
            logger.debug(
                "charter_injected",
                agent=self.name,
                path=str(charter_path),
                chars=len(content),
            )
        except Exception as e:
            logger.warning(
                "charter_inject_failed",
                agent=self.name,
                path=str(charter_path),
                error=str(e),
            )
            self._context.set_charter("")

    def _track_charter_advance_from_tool_result(self, func_name: str, result) -> None:

        if func_name != "task_charter":
            return
        if not getattr(result, "success", False):
            return
        data = getattr(result, "data", None) or {}
        if not isinstance(data, dict):
            return
        if "stage_done_index" not in data:
            return
        try:
            idx = int(data.get("stage_done_index") or 0)
        except (TypeError, ValueError):
            idx = 0
        name = str(data.get("stage_done") or "")
        if idx <= 0 or not name:
            return
        self._charter_stage_just_advanced = True
        self._charter_stage_done_index = idx
        self._charter_stage_done_name = name
        logger.debug(
            "charter_stage_tracked",
            agent_id=self.id,
            stage_index=idx,
            stage_name=name,
        )

    def _maybe_inject_charter_init_hint(self, user_message: str | list[dict]) -> None:

        from cancer_claw.agent.engine.system_agents import MASTER_AGENT_ID

        if self.id != MASTER_AGENT_ID:
            return
        if self._bound_workspace is None:
            return
        workspace_root = self._bound_workspace.default_relative_root
        charter_path = workspace_root / "CHARTER.md"
        if charter_path.exists():
            return

        cfg = settings.charter

        user_chars = len(self._user_message_to_text(user_message))




        predicted_stages = 0
        plan_path = workspace_root / "PLAN.md"
        if plan_path.exists() and plan_path.is_file():
            try:
                plan_text = plan_path.read_text(encoding="utf-8")
                predicted_stages = len(
                    re.findall(
                        r"^\s*(?:#{2,4}\s*|[-*]\s*|\d+\.\s*)阶段\s*[\d一二三四五六七八九十百零A-Z]",
                        plan_text,
                        re.MULTILINE,
                    )
                )
            except Exception:
                predicted_stages = 0


        predicted_iterations = max(1, user_chars // 200) if user_chars else 0

        triggered: list[str] = []
        if user_chars >= cfg.auto_init_user_chars:
            triggered.append(f"user 消息 {user_chars} 字 ≥ {cfg.auto_init_user_chars}")
        if predicted_stages >= cfg.auto_init_min_stages:
            triggered.append(f"PLAN 阶段数 {predicted_stages} ≥ {cfg.auto_init_min_stages}")
        if predicted_iterations >= cfg.auto_init_min_iterations:
            triggered.append(
                f"预估工具回合 {predicted_iterations} ≥ {cfg.auto_init_min_iterations}"
            )

        if not triggered:
            return

        hint = (
            "[框架·长任务提示] 本任务体量较大（"
            + " / ".join(triggered)
            + "），且工作区还没有 CHARTER.md。"
            "强烈建议先调 task_charter(action=\"init\", title=..., stages=[...]) "
            "写一份任务契约，让阶段切换 + 进化链生效。短任务可忽略本提示。"
        )
        self._context.append_to_pending_user_prefix(hint)
        logger.info(
            "charter_init_hint_injected",
            agent=self.name,
            user_chars=user_chars,
            predicted_stages=predicted_stages,
            predicted_iterations=predicted_iterations,
            reasons=triggered,
        )

    def _refresh_project_instructions(self) -> None:

        if self._bound_workspace is None:
            self._context.set_project_instructions("")
            return
        workspace_root = self._bound_workspace.default_relative_root
        agents_md_path = workspace_root / "AGENTS.md"
        try:
            if not agents_md_path.exists() or not agents_md_path.is_file():
                self._context.set_project_instructions("")
                return
            content = agents_md_path.read_text(encoding="utf-8").strip()
            if not content:
                self._context.set_project_instructions("")
                return
            wrapped = load_prompt("agents_md_inject", agents_md_content=content)
            self._context.set_project_instructions(wrapped)
            logger.info(
                "agents_md_injected",
                agent=self.name,
                path=str(agents_md_path),
                chars=len(content),
            )
        except Exception as e:
            logger.warning(
                "agents_md_inject_failed",
                agent=self.name,
                path=str(agents_md_path),
                error=str(e),
            )
            self._context.set_project_instructions("")

    async def prepare(self, task: str = ""):

        if task:
            self._context.set_system_prompt(task=task)

        await self._state_machine.transition_to(AgentState.READY, "准备就绪")





    async def _inject_working_memory(self):

        if not self._working_memory:
            return
        try:

            history_max = settings.memory.history_inject_max_tokens
            history_msgs = await self._working_memory.load_as_messages(max_tokens=history_max)
            if history_msgs:
                self._context.inject_history_messages(history_msgs)
                print(
                    f"[{self.name}] 📜 历史消息注入 {len(history_msgs)} 条（预算 {history_max} tokens）",
                    flush=True,
                )


            onelines = self._working_memory.load_recent_onelines_only()
            p2_parts: list[str] = []
            if onelines:
                lines = ["## 近期任务摘要\n"]
                lines.extend(f"- {entry}" for entry in onelines)
                p2_parts.append("\n".join(lines))


            try:
                recall_guide = load_prompt("memory_recall_guide")
                p2_parts.append(recall_guide)
            except FileNotFoundError:
                pass

            if p2_parts:
                self._context.set_memory("\n\n".join(p2_parts))

        except Exception as e:
            print(f"[{self.name}] ⚠️ 工作记忆注入失败: {e!r}", flush=True)
            logger.warning("working_memory_inject_failed", agent_id=self.id, error=str(e))

    @staticmethod
    def _user_message_to_text(user_message: str | list[dict] | None) -> str:

        if not user_message:
            return ""
        if isinstance(user_message, str):
            return user_message
        if not isinstance(user_message, list):
            return str(user_message)
        parts: list[str] = []
        for p in user_message:
            if not isinstance(p, dict):
                continue
            t = p.get("type")
            if t == "text":
                txt = p.get("text") or ""
                if isinstance(txt, str) and txt:
                    parts.append(txt)
            elif t == "image_url":

                alt = p.get("image_url", {}).get("alt") if isinstance(p.get("image_url"), dict) else None
                parts.append(f"[image{f':{alt}' if alt else ''}]")
        return "\n".join(parts)

    async def _save_user_message_immediately(
        self,
        user_message: str | list[dict],
        *,
        attachment_metas: list[dict] | None = None,
    ):

        if not self._working_memory:
            return
        try:
            text = self._user_message_to_text(user_message)
            if attachment_metas:
                import json as _json
                sentinel = (
                    "\n<!--CC:ATTACHMENTS:v1-->"
                    + _json.dumps(attachment_metas, ensure_ascii=False)
                    + "<!--/CC:ATTACHMENTS-->"
                )
                text += sentinel
            await self._working_memory.save_turn("user", text)
        except Exception as e:
            logger.warning("user_message_presave_failed", agent_id=self.id, error=str(e))

    async def _save_conversation_turns(self, user_message: str, assistant_message: str):

        if not self._working_memory:
            return
        try:
            await self._working_memory.save_turn("assistant", assistant_message)
        except Exception as e:
            logger.warning("conversation_save_failed", agent_id=self.id, error=str(e))





    async def start_or_resume_session(
        self, session_id: str | None, *, force_new: bool = False,
    ) -> str:

        from cancer_claw.capabilities.toolkit.session_history import _make_session_id


        if force_new:
            new_sid = _make_session_id(self.id)
            self._current_session_id = new_sid
            self._sync_session_hint_to_memory()
            await self._upsert_current_session_index(status="active")
            logger.info(
                "session_started_new",
                agent_id=self.id,
                session_id=new_sid,
                trigger="force_new",
            )
            return new_sid


        if not session_id and self._current_session_id:
            self._sync_session_hint_to_memory()
            return self._current_session_id


        if not session_id:
            new_sid = _make_session_id(self.id)
            self._current_session_id = new_sid
            self._sync_session_hint_to_memory()
            await self._upsert_current_session_index(status="active")
            logger.info(
                "session_started_new",
                agent_id=self.id,
                session_id=new_sid,
            )
            return new_sid


        if session_id == self._current_session_id:
            self._sync_session_hint_to_memory()
            return session_id


        self._current_session_id = session_id
        self._sync_session_hint_to_memory()
        loaded = await self._restore_messages_from_db(session_id)
        await self._upsert_current_session_index(
            status="active" if not loaded else "ended",
        )
        logger.info(
            "session_resumed",
            agent_id=self.id,
            session_id=session_id,
            restored_messages=loaded,
        )
        return session_id

    def _sync_session_hint_to_memory(self) -> None:

        if self._working_memory is None:
            return
        try:
            self._working_memory.set_session_hint(self._current_session_id)
        except Exception as e:
            logger.warning(
                "session_hint_sync_failed",
                agent_id=self.id,
                error=str(e),
            )

    async def _restore_messages_from_db(self, session_id: str) -> int:

        try:
            self._context.clear_messages()
        except Exception:
            logger.warning("clear_messages_failed_before_restore", session_id=session_id)

        try:
            from cancer_claw.db import get_db
            from cancer_claw.agent.recall.working import (
                _attach_ts_prefix,
                _format_sqlite_ts,
                _parse_stored_content,
                _repair_tool_pairs,
            )

            db = await get_db()
            cursor = await db.execute(
                """
                SELECT id, role, content, tool_calls_json, tool_call_id, name,
                       created_at, seq
                FROM conversation_history
                WHERE session_id = ?
                ORDER BY seq IS NULL, seq ASC, created_at ASC, id ASC
                """,
                (session_id,),
            )
            rows = await cursor.fetchall()
        except Exception as e:
            logger.warning(
                "session_restore_db_read_failed",
                session_id=session_id,
                error=str(e),
            )
            return 0

        if not rows:
            return 0

        msgs: list[dict] = []
        for row in rows:
            role = row[1]
            content = row[2] or ""
            tc_json = row[3]
            tc_id = row[4]
            name = row[5]
            ts_str = _format_sqlite_ts(row[6])
            m = _parse_stored_content(
                role,
                content,
                tool_calls_json=tc_json,
                tool_call_id=tc_id,
                name=name,
            )
            m = _attach_ts_prefix(m, ts_str)
            msgs.append(m)


        msgs = _repair_tool_pairs(msgs)

        try:

            self._context._messages.clear()

            self._context._messages.extend(msgs)
        except Exception as e:
            logger.warning(
                "session_restore_inject_failed",
                session_id=session_id,
                error=str(e),
            )
            return 0
        return len(msgs)

    async def _upsert_current_session_index(self, *, status: str = "active") -> None:

        if not self._current_session_id:
            return
        if self._bound_workspace is None:
            return


        try:
            project_root = self._bound_workspace.project_root
            project_id = project_root.name
        except Exception:
            return

        try:
            from cancer_claw.agent.recall.session_repo import upsert_session

            await upsert_session(
                project_id=project_id,
                session_id=self._current_session_id,
                agent_id=self.id,
                status=status,
            )
        except Exception as e:
            logger.warning(
                "session_index_upsert_failed",
                agent_id=self.id,
                session_id=self._current_session_id,
                error=str(e),
            )

    async def _finalize_session_status_ended(self) -> None:

        if not self._current_session_id:
            return
        try:
            from datetime import datetime, timezone

            from cancer_claw.agent.recall.session_repo import update_session_status

            await update_session_status(
                self._current_session_id,
                "ended",
                ended_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as e:
            logger.warning(
                "session_status_finalize_failed",
                agent_id=self.id,
                session_id=self._current_session_id,
                error=str(e),
            )





    async def chat(self, user_message: str | list[dict]) -> str:

        final_content = ""
        async for ev in self._iter_reasoning_events(user_message):
            if ev.get("type") == "_final":
                final_content = ev.get("content", "")
        return final_content

    async def chat_stream(self, user_message: str | list[dict]) -> AsyncGenerator[dict, None]:

        _ag = f"{self.name}({self.id})"

        _msg_preview = self._user_message_to_text(user_message)[:80]
        print(f"\n[{_ag}] ▶ chat_stream | 消息={_msg_preview!r}", flush=True)


        if self.state == AgentState.CREATED:
            await self.initialize()
        if self.state == AgentState.INITIALIZED:
            await self.prepare()
        if self.state in (AgentState.COMPLETED, AgentState.FAILED, AgentState.RUNNING):
            await self._state_machine.reset("接收新对话（上轮可能异常中断）")
            await self.initialize()
            await self.prepare()




        if not self._current_session_id:
            try:
                await self.start_or_resume_session(None)
            except Exception as e:
                logger.warning("session_auto_start_failed", agent_id=self.id, error=str(e))

        queue: asyncio.Queue = asyncio.Queue()

        self._event_sink = queue
        self._depth = 0

        async def _runner():
            try:
                await self._run_into_sink(user_message, queue, depth=0)
            except asyncio.CancelledError:

                print(f"[{_ag}] ⚠️ Runner 被取消（SSE 断开）", flush=True)
            except Exception as e:
                print(f"[{_ag}] ❌ Runner 异常: {e!r}", flush=True)
                logger.exception("chat_stream_runner_failed", agent_id=self.id)
                await queue.put({
                    "type": "error",
                    "error": str(e) or repr(e),
                    "agent_id": self.id,
                    "agent_name": self.name,
                    "depth": 0,
                })
            finally:
                await queue.put(None)

        runner_task = asyncio.create_task(_runner())
        event_count = 0
        try:
            while True:
                ev = await queue.get()
                if ev is None:
                    print(f"[{_ag}] ◀ SSE 流结束，共 {event_count} 个事件", flush=True)
                    break
                event_count += 1
                yield ev
        finally:
            if not runner_task.done():
                print(f"[{_ag}] ⚠️ 取消未完成的 Runner（客户端断开）", flush=True)
                runner_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await runner_task

    async def _run_into_sink(
        self,
        user_message: str | list[dict],
        sink: asyncio.Queue | None,
        depth: int,
    ) -> str:

        _ag = f"{self.name}({self.id})"

        self._event_sink = sink
        self._depth = depth

        final_content = ""
        async for ev in self._iter_reasoning_events(user_message):
            ev_type = ev.get("type")
            if ev_type == "_final":
                final_content = ev.get("content", "")
                continue
            if sink is not None:
                stamped = {
                    **ev,
                    "agent_id": self.id,
                    "agent_name": self.name,
                    "depth": depth,
                }
                await sink.put(stamped)

        return final_content

    def clone_for_subtask(self) -> "Agent":



        carrier = Agent.__new__(Agent)


        carrier.id = f"{self.id}#sub"
        carrier.name = self.name
        carrier.description = self.description
        carrier.soul_path = self.soul_path
        carrier.craft_ids = list(self.craft_ids)
        carrier._soul_content = self._soul_content
        carrier.active_persona_id = self.active_persona_id
        carrier._bound_workspace = self._bound_workspace
        carrier._bound_project_name = self._bound_project_name
        carrier._evolution_project_id = self._evolution_project_id
        carrier._current_user = self._current_user
        carrier.personal_crafts_dir = self.personal_crafts_dir
        carrier.lifecycle = self.lifecycle
        carrier.mode = self.mode


        carrier._state_machine = StateMachine(AgentState.CREATED)
        carrier._context = ContextManager()
        carrier._working_memory = None
        carrier._total_tokens = 0
        carrier._model_calls = 0
        carrier._tool_calls = 0
        carrier._consecutive_text_only = 0
        carrier._tool_usage_this_turn = {}
        carrier._charter_stage_just_advanced = False
        carrier._charter_stage_done_index = 0
        carrier._charter_stage_done_name = ""
        carrier._current_session_id = None
        carrier._delegator = self
        carrier._event_sink = None
        carrier._depth = 0

        return carrier

    def clone_for_session(self) -> "Agent":

        carrier = self.clone_for_subtask()
        carrier.id = self.id
        carrier._delegator = None


        carrier._chat_lock = asyncio.Lock()
        if self._working_memory is not None:
            carrier._working_memory = WorkingMemory(
                self._working_memory.project_id,
                self.id,
                cross_agent_ids=list(self._working_memory.cross_agent_ids),
            )
        return carrier

    async def spawn_oneshot(
        self,
        prompt: str,
        *,
        tools: set[str] | None = None,
        max_iterations: int = 50,
        sink: asyncio.Queue | None = None,
        depth: int = 0,
    ) -> tuple[str, int, dict[str, int]]:

        _ag = f"{self.name}({self.id})"

        print(
            f"[{_ag}][oneshot] ▶ depth={depth} | "
            f"tools={'默认核心' if tools is None else len(tools)} | "
            f"prompt={len(prompt)}字",
            flush=True,
        )




        if self.state == AgentState.CREATED:
            await self.initialize()
        if self.state == AgentState.INITIALIZED:
            await self.prepare()
        if self.state in (AgentState.COMPLETED, AgentState.FAILED, AgentState.RUNNING):
            await self._state_machine.reset("spawn_oneshot 重置")
            await self.initialize()
            await self.prepare()


        prev_context = self._context
        prev_wm = self._working_memory
        prev_allowlist = getattr(self, "_tool_allowlist", None)
        prev_tool_calls = self._tool_calls
        prev_total_tokens = self._total_tokens
        had_allowlist_attr = hasattr(self, "_tool_allowlist")


        tmp_context = ContextManager()

        tmp_context._system_parts = dict(prev_context._system_parts)

        registry = get_registry()
        if tools is not None:

            schemas: list[dict] = []
            missing: list[str] = []
            for nm in tools:
                s = registry.get_schema(nm)
                if s:
                    schemas.append(s)
                else:
                    missing.append(nm)
            if missing:
                logger.warning(
                    "spawn_oneshot_unknown_tools",
                    agent=self.id,
                    missing=missing,
                )
            if schemas:
                tmp_context.activate_tools(schemas)
            self._tool_allowlist = set(tools)
            _activated = [s.get("function", {}).get("name") for s in schemas]

            tmp_context.set_protected_tool_names(set(_activated))
            if missing:
                print(f"[{_ag}][oneshot] ⚠️  registry 缺失工具：{sorted(missing)}", flush=True)
            print(
                f"[{_ag}][oneshot] 工具装载 {len(_activated)} 个（受保护）：{sorted(_activated)}",
                flush=True,
            )
        else:



            _core_schemas = registry.get_core_schemas(
                agent_id=self.id,
                persona_id=self.active_persona_id,
                depth=depth,
            )
            tmp_context.activate_tools(_core_schemas)
            self._tool_allowlist = None
            _activated = [s.get("function", {}).get("name") for s in _core_schemas]
            tmp_context.set_protected_tool_names(set(_activated))
            print(
                f"[{_ag}][oneshot] 工具装载 {len(_activated)} 个默认核心（受保护）：{sorted(_activated)}",
                flush=True,
            )

        self._context = tmp_context
        self._working_memory = None



        final_content = ""
        try:
            async for ev in self._iter_reasoning_events(prompt):
                ev_type = ev.get("type")
                if ev_type == "_final":
                    final_content = ev.get("content", "")
                    continue
                if sink is not None:
                    stamped = {
                        **ev,
                        "agent_id": self.id,
                        "agent_name": self.name,
                        "depth": depth,
                    }
                    try:
                        await sink.put(stamped)
                    except Exception:
                        logger.warning("spawn_oneshot_sink_put_failed", exc_info=True)
        finally:

            self._context = prev_context
            self._working_memory = prev_wm
            if had_allowlist_attr:
                self._tool_allowlist = prev_allowlist
            else:

                try:
                    del self._tool_allowlist
                except AttributeError:
                    pass

        iter_count = max(0, self._tool_calls - prev_tool_calls)


        usage: dict[str, int] = {
            "prompt_tokens": max(0, self._total_tokens - prev_total_tokens),
            "completion_tokens": 0,
        }
        print(
            f"[{_ag}][oneshot] ◀ done | iter≈{iter_count} | tokens≈{usage['prompt_tokens']} | "
            f"回复={len(final_content)}字",
            flush=True,
        )
        return final_content, iter_count, usage

    async def consult(
        self,
        question: str,
        *,
        from_agent_id: str,
        from_agent_name: str,
        context_hint: str = "",
    ) -> str:


        if not self._soul_content and self.soul_path:
            soul_file = Path(self.soul_path)
            if soul_file.exists():
                self._soul_content = soul_file.read_text(encoding="utf-8")


        consult_system = (
            f"# 角色\n你是 {self.name}（{self.id}）。\n\n"
            f"# 你的人格\n{self._soul_content}\n\n"
            "# 当前情境\n"
            "你的下属 sub-agent 在执行任务过程中遇到了无法独立判断的问题，"
            "通过旁路咨询通道向你请教。请基于你的经验和职责给出一个**简短明确**的答复，"
            "帮助下属继续推进。\n\n"
            "## 要求\n"
            "- 答案要直接、可执行，不要展开冗长解释\n"
            "- 如果问题超出你的判断范围，明确告知\"无法判断，建议向用户确认\"\n"
            "- 不要调用任何工具，只用自然语言回答\n"
            "- 控制在 5 句话以内"
        )
        consult_user = (
            f"## 提问者\n{from_agent_name} ({from_agent_id})\n\n"
            f"## 问题\n{question.strip()}\n\n"
            f"## 上下文\n{(context_hint or '（无）').strip()}"
        )

        request = ChatRequest(
            messages=[
                {"role": "system", "content": consult_system},
                {"role": "user", "content": consult_user},
            ],
            tools=None,
            task_type="fast",
        )

        logger.info(
            "consult_invoked",
            consultant=self.id,
            from_agent=from_agent_id,
            question_preview=question[:120],
        )
        try:
            response = await get_router().chat(request)
        except Exception as e:
            logger.exception("consult_failed", consultant=self.id)
            return f"[旁路咨询失败: {e}]"


        self._model_calls += 1
        self._total_tokens += response.usage.get("total_tokens", 0)
        return (response.content or "").strip()

    async def _iter_reasoning_events(self, user_message: str | list[dict]) -> AsyncGenerator[dict, None]:

        _ag = f"{self.name}({self.id})"


        if self.state == AgentState.CREATED:
            await self.initialize()
        if self.state == AgentState.INITIALIZED:
            await self.prepare()
        if self.state in (AgentState.COMPLETED, AgentState.FAILED, AgentState.RUNNING):
            print(f"[{_ag}] ⚠️ 非预期状态={self.state.value}，强制重置", flush=True)
            await self._state_machine.reset("接收新对话（上轮可能异常中断）")
            await self.initialize()
            await self.prepare()


        if not self._current_session_id:
            try:
                await self.start_or_resume_session(None)
            except Exception as e:
                logger.warning("session_auto_start_failed", agent_id=self.id, error=str(e))




        att_metas = getattr(self, "_pending_attachment_metas", None)
        self._pending_attachment_metas = None
        await self._save_user_message_immediately(user_message, attachment_metas=att_metas)



        self._context.clear_messages()
        await self._inject_working_memory()



        self.mode = "execute"











        self._refresh_charter()



        self._maybe_reinject_master_environment()





        self._maybe_inject_charter_init_hint(user_message)





        try:
            now_local = datetime.now().astimezone()
            self._context.set_clock(
                f"当前时间: {now_local.strftime('%Y-%m-%d %H:%M:%S %z')}"
            )
        except Exception:
            pass

        self._context.add_message("user", user_message)
        self._tool_usage_this_turn = {}

        self._charter_stage_just_advanced = False
        self._charter_stage_done_index = 0
        self._charter_stage_done_name = ""

        self._consecutive_text_only = 0
        await self._state_machine.transition_to(AgentState.RUNNING, "开始推理")

        final_content = ""
        completed_normally = False
        iteration = 0

        _total_input_tokens = 0
        _total_output_tokens = 0


        _task_model_calls = 0
        _task_tool_calls = 0
        _reasoning_start = time.monotonic()





        _bg_monitor_queue: list[dict] = []

        try:
            for iteration in range(MAX_ITERATIONS):
                _elapsed = round(time.monotonic() - _reasoning_start, 1)



                print(
                    f"\n[{_ag}] {'='*60}\n"
                    f"[{_ag}] 第 {iteration + 1} 轮（本次任务）| "
                    f"模型调用={_task_model_calls} | 工具调用={_task_tool_calls} | "
                    f"tokens in={_total_input_tokens}/out={_total_output_tokens} | "
                    f"已用时={_elapsed}s | 后台进程={len(_bg_monitor_queue)}\n"
                    f"[{_ag}]   生命周期累计：模型={self._model_calls} 工具={self._tool_calls} tokens={self._total_tokens}\n"
                    f"[{_ag}] {'='*60}",
                    flush=True,
                )




                if _bg_monitor_queue:
                    pending = _bg_monitor_queue.pop(0)
                    pid       = pending["pid"]
                    interval  = pending["check_interval"]
                    log_path  = pending.get("log_path", "") or ""

                    yield {
                        "type": "thinking",
                        "content": f"等待 {interval}s 收集后台进程 PID={pid} 启动摘要...",
                    }
                    await asyncio.sleep(interval)

                    proc_output, still_running = await self._build_bg_startup_summary(
                        pid=pid, log_path=log_path
                    )

                    yield {"type": "process_output", "pid": pid, "output": proc_output[:500]}
                    self._context.add_message("user", proc_output)



                messages, tools = self._context.build_request()

                tools = self._filter_tools_for_mode(tools)
                tool_names = [t.get("function", {}).get("name") for t in (tools or [])]

                if not tools and self._context.active_tools:
                    print(
                        f"[{_ag}] ⚠️  ctx 有 {len(self._context.active_tools)} 个工具但 mode={self.mode} 过滤后变空",
                        flush=True,
                    )
                elif not tools:
                    print(f"[{_ag}] ⚠️  ctx.active_tools=0（sub-agent 启动时未装工具）", flush=True)

                _has_vision = _messages_have_image(messages)
                request = ChatRequest(
                    messages=messages,
                    tools=tools,
                    requires_vision=_has_vision,
                )
                if _has_vision:
                    print(f"[{_ag}] 🖼️  检测到图片输入 → 路由到 vision 模型", flush=True)

                yield {"type": "thinking", "content": f"第 {iteration + 1} 轮推理..."}
                _call_t0 = time.monotonic()
                response = await get_router().chat(request)
                _call_ms = round((time.monotonic() - _call_t0) * 1000)
                self._model_calls += 1
                _task_model_calls += 1


                _u = response.usage
                _round_in  = _u.get("prompt_tokens", 0) or _u.get("input_tokens", 0) or 0
                _round_out = _u.get("completion_tokens", 0) or _u.get("output_tokens", 0) or 0
                _round_total = _u.get("total_tokens", 0) or (_round_in + _round_out)

                _round_cached = 0
                _ptd = _u.get("prompt_tokens_details") or {}
                if isinstance(_ptd, dict):
                    _round_cached = int(
                        _ptd.get("cached_tokens", 0)
                        or _u.get("cached_tokens", 0)
                        or _u.get("cached_input_tokens", 0)
                        or 0
                    )
                else:
                    _round_cached = int(
                        _u.get("cached_tokens", 0)
                        or _u.get("cached_input_tokens", 0)
                        or 0
                    )
                self._total_tokens += _round_total
                _total_input_tokens += _round_in
                _total_output_tokens += _round_out



                yield {
                    "type": "usage",
                    "model": getattr(response, "model", None),
                    "input_tokens": _round_in,
                    "output_tokens": _round_out,
                    "cached_input_tokens": _round_cached,
                    "total_tokens": _round_total,
                    "elapsed_ms": _call_ms,

                    "task_input_tokens": _total_input_tokens,
                    "task_output_tokens": _total_output_tokens,
                    "task_total_tokens": _total_input_tokens + _total_output_tokens,
                }


                has_tool_calls = bool(response.tool_calls)
                tool_call_names = (
                    [tc["function"]["name"] for tc in response.tool_calls]
                    if has_tool_calls else []
                )
                content_preview = (response.content or "")[:200]
                print(
                    f"[{_ag}] ◀ 模型返回 {_call_ms/1000:.1f}s | "
                    f"本轮 in={_round_in} out={_round_out} (total={_round_total}) | "
                    f"本次任务 in={_total_input_tokens} out={_total_output_tokens} | "
                    f"{response.model}",
                    flush=True,
                )
                if has_tool_calls:
                    print(f"[{_ag}]   → 工具: {tool_call_names}", flush=True)
                if content_preview:
                    print(f"[{_ag}]   → 内容: {content_preview!r}", flush=True)
                elif not has_tool_calls:
                    print(f"[{_ag}]   → ⚠️  无工具调用也无文本！finish_reason={response.finish_reason!r}", flush=True)



                if response.reasoning_content:
                    yield {"type": "thinking", "content": response.reasoning_content}

                if response.tool_calls:

                    self._consecutive_text_only = 0

                    _completion_requested = False
                    self._context.add_assistant_tool_calls(
                        response.content, response.tool_calls,
                        reasoning_content=response.reasoning_content,
                    )




                    if self._working_memory:
                        try:
                            await self._working_memory.save_turn(
                                "assistant",
                                response.content or "",
                                tool_calls=response.tool_calls,
                            )
                        except Exception as _snap_err:
                            logger.warning("tool_turn_snapshot_failed", agent_id=self.id, error=str(_snap_err))





                    _pretext_event = build_assistant_pretext_event(
                        response.content, response.tool_calls
                    )
                    if _pretext_event is not None:
                        yield _pretext_event

                    _pending_tool_images: list[dict] = []

                    for tc_idx, tc in enumerate(response.tool_calls):
                        func_name = tc["function"]["name"]
                        func_args_str = tc["function"]["arguments"]
                        tc_id = tc["id"]

                        print(f"[{_ag}]   🔧 [{tc_idx+1}/{len(response.tool_calls)}] {func_name} | 参数={func_args_str[:200]!r}", flush=True)

                        yield {
                            "type": "tool_call",
                            "tool": func_name,
                            "arguments": func_args_str,
                            "tool_call_id": tc_id,
                        }

                        _tool_t0 = time.monotonic()
                        result = await self._execute_tool(func_name, func_args_str)
                        _tool_ms = round((time.monotonic() - _tool_t0) * 1000)
                        self._tool_calls += 1
                        _task_tool_calls += 1
                        self._tool_usage_this_turn[func_name] = (
                            self._tool_usage_this_turn.get(func_name, 0) + 1
                        )
                        self._track_charter_advance_from_tool_result(func_name, result)

                        output_preview = (result.output or "")[:400]
                        _err = repr(result.error) if not result.success else None
                        _mark = "✅" if result.success else "❌"
                        print(
                            f"[{_ag}]   {_mark} {func_name}（{_tool_ms}ms）| "
                            f"输出={output_preview!r}"
                            + (f" | 错误={_err}" if _err else ""),
                            flush=True,
                        )





                        _SSE_OUTPUT_LIMIT = 32768
                        _full_output = result.output or ""
                        _truncated = len(_full_output) > _SSE_OUTPUT_LIMIT
                        _result_event = {
                            "type": "tool_result",
                            "tool": func_name,
                            "tool_call_id": tc_id,
                            "success": result.success,
                            "output": _full_output[:_SSE_OUTPUT_LIMIT],
                            "error": result.error,
                            "duration_ms": _tool_ms,
                            "arguments": func_args_str,
                            "truncated": _truncated,
                        }
                        if _truncated:
                            _result_event["full_length"] = len(_full_output)
                        if result.data:
                            _result_event["data"] = result.data
                        yield _result_event


                        if result.success:
                            tool_feedback = result.output or "（工具执行成功，无输出）"
                        else:
                            parts = []
                            if result.error:
                                parts.append(f"错误: {result.error}")
                            if result.output:
                                parts.append(f"执行输出:\n{result.output}")
                            tool_feedback = "\n\n".join(parts) or "（工具执行失败，无详细信息）"


                        _tool_persist_content = self._compact_tool_feedback_for_context(
                            tool_feedback, func_name, tc_id
                        )
                        self._context.add_tool_result(tc_id, _tool_persist_content)
                        if self._working_memory:
                            try:
                                await self._working_memory.save_turn(
                                    "tool",
                                    _tool_persist_content,
                                    tool_call_id=tc_id,
                                )
                            except Exception as _save_err:
                                logger.warning(
                                    "tool_result_persist_failed",
                                    agent_id=self.id,
                                    tool=func_name,
                                    error=str(_save_err),
                                )


                        if result.success and result.data and result.data.get("images"):
                            _pending_tool_images.extend(result.data["images"])





                        if (func_name == "shell_exec"
                                and result.success
                                and result.data.get("pid")):
                            pid = result.data["pid"]
                            log_path = result.data.get("log_path", "") or ""
                            _bg_monitor_queue.append({
                                "pid": pid,
                                "check_interval": 10,
                                "max_checks": 1,
                                "checked": 0,
                                "log_path": log_path,
                            })

                            _stop_schema = get_registry().get_schema("stop_background_monitor")
                            if _stop_schema:
                                self._context.activate_tools([_stop_schema])
                            logger.info("background_process_registered", agent_id=self.id, pid=pid, log_path=log_path)
                            yield {
                                "type": "thinking",
                                "content": f"已注册后台进程 PID={pid}，10s 后将注入启动摘要；之后请用 file_ops.read_file 读日志",
                            }



                        if func_name == "stop_background_monitor" and result.success:
                            stop_pid = result.data.get("stop_pid")
                            before_len = len(_bg_monitor_queue)
                            _bg_monitor_queue[:] = [
                                m for m in _bg_monitor_queue if m["pid"] != stop_pid
                            ]
                            removed = before_len - len(_bg_monitor_queue)
                            print(
                                f"[{_ag}]   stop_background_monitor: PID={stop_pid} "
                                f"已从监控队列移除（移除={removed}条，剩余={len(_bg_monitor_queue)}条）",
                                flush=True,
                            )

                            if not _bg_monitor_queue:
                                self._context.deactivate_tools(["stop_background_monitor"])


















                        if func_name == "attempt_completion" and result.success:
                            completion_result = (
                                result.data.get("completion_result", "") or ""
                            ).strip()
                            raw_response_content = response.content or ""
                            response_content = strip_ts_prefix(raw_response_content).strip()
                            if looks_like_ts_only(raw_response_content):
                                response_content = ""
                            final_content = (
                                response_content or completion_result or final_content
                            )
                            _completion_requested = True


                            try:
                                from cancer_claw.capabilities.toolkit.builtins.plan_mode import (
                                    archive_current_plan_on_completion,
                                )
                                archive_info = archive_current_plan_on_completion(
                                    self, completion_result or final_content
                                )
                                if archive_info.get("archived_to"):
                                    print(
                                        f"[{_ag}]   PLAN.md 已归档到 "
                                        f"{archive_info['archived_to']}（含完成报告）",
                                        flush=True,
                                    )
                                elif archive_info.get("warning"):
                                    print(
                                        f"[{_ag}]   PLAN.md 归档跳过：{archive_info['warning']}",
                                        flush=True,
                                    )
                            except Exception as _arch_err:
                                logger.warning(
                                    "plan_archive_dispatch_failed",
                                    agent_id=self.id,
                                    error=str(_arch_err),
                                )
                            print(
                                f"[{_ag}]   attempt_completion 收到完成声明（{len(final_content)}字），"
                                f"准备退出推理循环",
                                flush=True,
                            )
                            break


                    if _completion_requested:
                        print(f"[{_ag}] → attempt_completion 触发退出", flush=True)




                        clean_final = strip_ts_prefix(final_content)
                        yield {"type": "message", "content": clean_final}
                        if self._working_memory:
                            try:
                                await self._working_memory.save_turn("assistant", clean_final)
                            except Exception as _save_err:
                                logger.warning("real_time_persist_failed", agent_id=self.id, error=str(_save_err))
                        completed_normally = True
                        break

                    print(f"[{_ag}]   本轮工具执行完毕 | 累计={dict(self._tool_usage_this_turn)}", flush=True)


                    if _pending_tool_images:
                        self._inject_tool_images_as_user_message(_pending_tool_images)
                        print(
                            f"[{_ag}]   🖼️  注入 {len(_pending_tool_images)} 张工具图片到上下文",
                            flush=True,
                        )

                    continue
                else:
                    final_content = response.content or ""
                    print(
                        f"[{_ag}] → 无工具调用 | content长度={len(final_content)} | 状态={self.state.value} | 后台进程待监控={len(_bg_monitor_queue)}",
                        flush=True,
                    )





                    if not final_content:
                        if getattr(response, "reasoning_has_tool_call", False):


                            print(
                                f"[{_ag}] ⚠️  Qwen3 bug: reasoning 含 <tool_call> 但未实际调用"
                                f"（finish_reason={response.finish_reason!r}）→ 发送纠偏指令",
                                flush=True,
                            )
                            self._context.add_message(
                                "user",
                                "你已经在思考中规划了工具调用，但没有实际执行。"
                                "请现在立即直接调用相应工具，不要再描述，直接行动。",
                            )
                        else:
                            print(f"[{_ag}] ⚠️  content 为空（finish_reason={response.finish_reason!r}），不可信的结束信号，继续推理", flush=True)
                            self._context.add_message("user", "请继续完成任务，给出你的下一步行动或最终回复。")
                        continue













                    if ("<tool_call>" in final_content
                            or "</tool_call>" in final_content):
                        inline_tcs = _parse_inline_tool_calls(final_content)
                        if inline_tcs:
                            print(
                                f"[{_ag}] ⚠️  fail mode: content 含 {len(inline_tcs)} 个 "
                                f"<tool_call> 文本块 → 框架代为执行（不浪费纠偏轮）",
                                flush=True,
                            )



                            self._context.add_assistant_tool_calls(
                                final_content, inline_tcs
                            )


                            if self._working_memory:
                                try:
                                    await self._working_memory.save_turn(
                                        "assistant",
                                        final_content or "",
                                        tool_calls=inline_tcs,
                                    )
                                except Exception as _snap_err:
                                    logger.warning(
                                        "tool_turn_snapshot_failed",
                                        agent_id=self.id,
                                        path="inline",
                                        error=str(_snap_err),
                                    )

                            _pending_inline_images: list[dict] = []

                            for tc in inline_tcs:
                                func_name = tc["function"]["name"]
                                func_args_str = tc["function"]["arguments"]
                                tc_id = tc["id"]

                                yield {
                                    "type": "tool_call",
                                    "tool": func_name,
                                    "arguments": func_args_str,
                                    "tool_call_id": tc_id,
                                    "from_inline_parse": True,
                                }

                                _tool_t0 = time.monotonic()
                                result = await self._execute_tool(func_name, func_args_str)
                                _tool_ms = round((time.monotonic() - _tool_t0) * 1000)
                                self._tool_calls += 1
                                _task_tool_calls += 1
                                self._tool_usage_this_turn[func_name] = (
                                    self._tool_usage_this_turn.get(func_name, 0) + 1
                                )
                                self._track_charter_advance_from_tool_result(func_name, result)

                                _mark = "✓" if result.success else "✗"
                                print(
                                    f"[{_ag}]   {_mark} inline {func_name} ({_tool_ms}ms)",
                                    flush=True,
                                )

                                _SSE_OUTPUT_LIMIT = 32768
                                _full_output = result.output or ""
                                _truncated = len(_full_output) > _SSE_OUTPUT_LIMIT
                                _ev = {
                                    "type": "tool_result",
                                    "tool": func_name,
                                    "tool_call_id": tc_id,
                                    "success": result.success,
                                    "output": _full_output[:_SSE_OUTPUT_LIMIT],
                                    "error": result.error,
                                    "duration_ms": _tool_ms,
                                    "arguments": func_args_str,
                                    "truncated": _truncated,
                                    "from_inline_parse": True,
                                }
                                if _truncated:
                                    _ev["full_length"] = len(_full_output)
                                if result.data:
                                    _ev["data"] = result.data
                                yield _ev

                                if result.success:
                                    tool_feedback = (
                                        result.output or "（工具执行成功，无输出）"
                                    )
                                else:
                                    parts = []
                                    if result.error:
                                        parts.append(f"错误: {result.error}")
                                    if result.output:
                                        parts.append(f"执行输出:\n{result.output}")
                                    tool_feedback = (
                                        "\n\n".join(parts)
                                        or "（工具执行失败，无详细信息）"
                                    )
                                _tool_persist_content = self._compact_tool_feedback_for_context(
                                    tool_feedback, func_name, tc_id
                                )
                                self._context.add_tool_result(tc_id, _tool_persist_content)
                                if self._working_memory:
                                    try:
                                        await self._working_memory.save_turn(
                                            "tool",
                                            _tool_persist_content,
                                            tool_call_id=tc_id,
                                        )
                                    except Exception as _save_err:
                                        logger.warning(
                                            "tool_result_persist_failed",
                                            agent_id=self.id,
                                            tool=func_name,
                                            error=str(_save_err),
                                        )


                                if result.success and result.data and result.data.get("images"):
                                    _pending_inline_images.extend(result.data["images"])


                            if _pending_inline_images:
                                self._inject_tool_images_as_user_message(_pending_inline_images)
                                print(
                                    f"[{_ag}]   🖼️  注入 {len(_pending_inline_images)} 张工具图片到上下文（inline路径）",
                                    flush=True,
                                )

                            continue
                        else:

                            print(
                                f"[{_ag}] ⚠️ inline 解析失败 → 发纠偏指令重试",
                                flush=True,
                            )
                            self._context.add_message("assistant", final_content)
                            self._context.add_message(
                                "user",
                                "你上一轮把工具调用写成了 `<tool_call>...</tool_call>` 纯文本，"
                                "**没有真正调用工具**——框架已尝试解析这些文本块但格式不规范，"
                                "无法代为执行。\n\n"
                                "请现在通过标准 function calling 接口直接调用相应工具，"
                                "**不要**再用 `<tool_call>` 文本格式描述工具调用。"
                                "如果你要读 scratchpad，直接调用 scratchpad 工具；"
                                "如果你要写文件，直接调用 file_ops 工具。",
                            )
                            final_content = ""
                            continue












                    if _bg_monitor_queue:


                        clean_snapshot = strip_ts_prefix(final_content)
                        self._context.add_message("assistant", clean_snapshot)
                        if self._working_memory:
                            try:
                                await self._working_memory.save_turn("assistant", clean_snapshot)
                            except Exception as _save_err:
                                logger.warning("real_time_persist_failed", agent_id=self.id, error=str(_save_err))
                        print(
                            f"[{_ag}] 后台进程未结束 pids={[m['pid'] for m in _bg_monitor_queue]}，继续监控",
                            flush=True,
                        )
                        continue

                    self._consecutive_text_only += 1



                    final_content = strip_ts_prefix(final_content)
                    _extra_msg_kw: dict = {}
                    if response.reasoning_content:
                        _extra_msg_kw["reasoning_content"] = response.reasoning_content
                    self._context.add_message("assistant", final_content, **_extra_msg_kw)














                    if self._consecutive_text_only >= 3:
                        print(
                            f"[{_ag}] 连续 {self._consecutive_text_only} 次纯文本 -> 强制软退出",
                            flush=True,
                        )

                    print(
                        f"[{_ag}] 模型纯文本无工具调用 → 自动作为 attempt_completion 收尾"
                        f"（省一轮重做；不归档 PLAN）",
                        flush=True,
                    )

                    clean_final = strip_ts_prefix(final_content)
                    yield {"type": "message", "content": clean_final}
                    if self._working_memory:
                        try:
                            await self._working_memory.save_turn("assistant", clean_final)
                        except Exception as _save_err:
                            logger.warning(
                                "real_time_persist_failed",
                                agent_id=self.id, error=str(_save_err),
                            )

                    _total_elapsed = round(time.monotonic() - _reasoning_start, 1)
                    print(
                        f"[{_ag}] ✅ 文本收尾 | 轮次={iteration + 1} | "
                        f"模型调用(任务)={_task_model_calls} 工具调用(任务)={_task_tool_calls} | "
                        f"tokens in={_total_input_tokens}/out={_total_output_tokens}（本次任务）| "
                        f"生命周期累计 模型={self._model_calls} 工具={self._tool_calls} tokens={self._total_tokens} | "
                        f"耗时={_total_elapsed}s",
                        flush=True,
                    )
                    completed_normally = True
                    break
            else:
                _bg_pids = [m['pid'] for m in _bg_monitor_queue] if _bg_monitor_queue else []
                print(
                    f"[{_ag}] ❌ 达到最大迭代次数 {MAX_ITERATIONS} | "
                    f"模型调用(任务)={_task_model_calls} 工具调用(任务)={_task_tool_calls} | "
                    f"tokens in={_total_input_tokens}/out={_total_output_tokens}（本次任务）| "
                    f"生命周期累计 模型={self._model_calls} 工具={self._tool_calls} tokens={self._total_tokens} | "
                    f"工具={dict(self._tool_usage_this_turn)}"
                    + (f" | 后台进程={_bg_pids}" if _bg_pids else ""),
                    flush=True,
                )
                yield {
                    "type": "error",
                    "error": f"推理循环达到最大次数（{MAX_ITERATIONS}）",
                }

            await self._state_machine.transition_to(AgentState.COMPLETED, "推理完成")


            self._schedule_evolution_after_task(
                completed_normally=completed_normally,
                user_message=user_message,
                final_response=final_content,
                iterations=iteration + 1,
            )

            await self._finalize_session_status_ended()
            _done_elapsed = round(time.monotonic() - _reasoning_start, 1)
            _done_stats = {
                **self.stats,
                "input_tokens": _total_input_tokens,
                "output_tokens": _total_output_tokens,
                "elapsed_seconds": _done_elapsed,
                "iterations": iteration + 1,
                "tool_usage": dict(self._tool_usage_this_turn),
            }
            print(
                f"[{_ag}] ✅ 完成 | 轮次={iteration + 1} | "
                f"模型调用(任务)={_task_model_calls} 工具调用(任务)={_task_tool_calls} | "
                f"tokens in={_total_input_tokens}/out={_total_output_tokens}（本次任务）| "
                f"生命周期累计 模型={self._model_calls} 工具={self._tool_calls} tokens={self._total_tokens} | "
                f"耗时={_done_elapsed}s",
                flush=True,
            )
            try:
                from cancer_claw.services.tracing import dump_turn_diagnostic
                dump_turn_diagnostic(
                    self,
                    user_message=user_message,
                    final_content=final_content,
                    iterations=iteration + 1,
                    elapsed_seconds=_done_elapsed,
                    input_tokens=_total_input_tokens,
                    output_tokens=_total_output_tokens,
                )
            except Exception:
                pass
            yield {"type": "done", "stats": _done_stats}
        except asyncio.CancelledError:


            _cancel_elapsed = round(time.monotonic() - _reasoning_start, 1)
            print(
                f"[{_ag}] ⚠️ 推理被取消（SSE 断开）| 轮次={iteration} | "
                f"模型调用(任务)={_task_model_calls} 工具调用(任务)={_task_tool_calls} | "
                f"tokens in={_total_input_tokens}/out={_total_output_tokens}（本次任务）| "
                f"生命周期累计 tokens={self._total_tokens} | "
                f"耗时={_cancel_elapsed}s",
                flush=True,
            )
            logger.warning("reasoning_cancelled", agent_id=self.id)
            await self._state_machine.transition_to(AgentState.FAILED, "推理被取消（连接断开）")

            if final_content and self._working_memory:
                try:
                    truncated = final_content + "\n\n[⚠️ 推理被中断，以上为截断内容]"
                    await self._working_memory.save_turn("assistant", truncated)
                except Exception as _save_err:
                    logger.warning("cancelled_save_failed", agent_id=self.id, error=str(_save_err))

            await self._finalize_session_status_ended()
            yield {"type": "error", "error": "推理被取消（连接断开）"}

        except Exception as e:
            _err_elapsed = round(time.monotonic() - _reasoning_start, 1)
            print(
                f"[{_ag}] ❌ 推理异常 | 轮次={iteration} | "
                f"模型调用(任务)={_task_model_calls} 工具调用(任务)={_task_tool_calls} | "
                f"tokens in={_total_input_tokens}/out={_total_output_tokens}（本次任务）| "
                f"生命周期累计 tokens={self._total_tokens} | "
                f"耗时={_err_elapsed}s | 错误={e!r}",
                flush=True,
            )
            logger.exception("reasoning_events_failed", agent_id=self.id)
            await self._state_machine.transition_to(AgentState.FAILED, str(e) or repr(e))

            if final_content and self._working_memory:
                try:
                    truncated = final_content + "\n\n[⚠️ 推理异常中断]"
                    await self._working_memory.save_turn("assistant", truncated)
                except Exception as _save_err:
                    logger.warning("error_save_failed", agent_id=self.id, error=str(_save_err))

            self._schedule_evolution_after_task(
                completed_normally=completed_normally,
                user_message=user_message,
                final_response=final_content,
                iterations=iteration + 1,
            )

            await self._finalize_session_status_ended()
            yield {"type": "error", "error": str(e) or repr(e)}
        finally:


            yield {"type": "_final", "content": final_content}





    async def _reasoning_loop(self) -> tuple[str, int]:

        iteration = 0
        _sync_pending_images: list[dict] = []
        for iteration in range(MAX_ITERATIONS):



            messages, tools = self._context.build_request()

            tools = self._filter_tools_for_mode(tools)
            request = ChatRequest(
                messages=messages,
                tools=tools,
                requires_vision=_messages_have_image(messages),
            )
            response = await get_router().chat(request)


            self._model_calls += 1
            self._total_tokens += response.usage.get("total_tokens", 0)

            logger.info("model_response",
                       agent=self.name,
                       iteration=iteration + 1,
                       has_tool_calls=bool(response.tool_calls),
                       tokens=response.usage.get("total_tokens", 0))

            if response.tool_calls:

                self._context.add_assistant_tool_calls(
                    response.content, response.tool_calls,
                    reasoning_content=response.reasoning_content,
                )

                if self._working_memory:
                    try:
                        await self._working_memory.save_turn(
                            "assistant",
                            response.content or "",
                            tool_calls=response.tool_calls,
                        )
                    except Exception as _snap_err:
                        logger.warning(
                            "tool_turn_snapshot_failed",
                            agent_id=self.id,
                            path="nonstream",
                            error=str(_snap_err),
                        )

                for tc in response.tool_calls:
                    func_name = tc["function"]["name"]
                    func_args_str = tc["function"]["arguments"]
                    tc_id = tc["id"]


                    result = await self._execute_tool(func_name, func_args_str)
                    self._tool_calls += 1
                    self._tool_usage_this_turn[func_name] = self._tool_usage_this_turn.get(func_name, 0) + 1
                    self._track_charter_advance_from_tool_result(func_name, result)


                    result_content = result.output if result.success else f"工具执行失败: {result.error}"
                    _tool_persist_content = self._compact_tool_feedback_for_context(
                        result_content, func_name, tc_id
                    )
                    self._context.add_tool_result(tc_id, _tool_persist_content)
                    if self._working_memory:
                        try:
                            await self._working_memory.save_turn(
                                "tool",
                                _tool_persist_content,
                                tool_call_id=tc_id,
                            )
                        except Exception as _save_err:
                            logger.warning(
                                "tool_result_persist_failed",
                                agent_id=self.id,
                                tool=func_name,
                                error=str(_save_err),
                            )


                    if result.success and result.data and result.data.get("images"):
                        _sync_pending_images.extend(result.data["images"])


                if _sync_pending_images:
                    self._inject_tool_images_as_user_message(_sync_pending_images)
                    _sync_pending_images = []


                continue

            else:


                final_content = strip_ts_prefix(response.content or "")
                _extra_kw: dict = {}
                if response.reasoning_content:
                    _extra_kw["reasoning_content"] = response.reasoning_content
                self._context.add_message("assistant", final_content, **_extra_kw)
                return final_content, iteration + 1


        return f"[系统提示: 推理循环达到最大次数 {MAX_ITERATIONS}，自动停止]", iteration + 1

    async def _execute_tool(self, tool_name: str, arguments_json: str) -> ToolResult:

        registry = get_registry()
        tool = registry.get_tool(tool_name)

        if not tool:
            return ToolResult(
                success=False,
                error=f"工具 '{tool_name}' 未注册，可用工具: {registry.tool_names}",
            )




        allowlist = getattr(self, "_tool_allowlist", None)
        if allowlist:


            if tool_name not in allowlist and tool_name != "tool_activator":
                return ToolResult(
                    success=False,
                    error=(
                        f"本步（管道 step）未授权工具 '{tool_name}'；"
                        f"白名单: {sorted(allowlist)}；请只用被允许的工具。"
                    ),
                )


        try:
            kwargs = json.loads(arguments_json) if arguments_json else {}
        except json.JSONDecodeError as e:
            return ToolResult(
                success=False,
                error=f"工具参数 JSON 解析失败: {str(e)}\n原始参数: {arguments_json}",
            )



        if self.mode == "plan":
            from cancer_claw.capabilities.toolkit.registry import (
                PLAN_MODE_ALLOWED_ACTIONS,
                PLAN_MODE_VISIBLE_TOOLS,
            )

            if tool_name not in PLAN_MODE_VISIBLE_TOOLS:
                return ToolResult(
                    success=False,
                    error=(
                        f"⚠️ 当前处于 Plan Mode（只读模式），工具 '{tool_name}' 不可用。"
                        f"完成调研 + 输出实施计划 + 用户审批后，调 `exit_plan_mode` 切换到 execute 模式再继续。"
                    ),
                )

            allowed_actions = PLAN_MODE_ALLOWED_ACTIONS.get(tool_name)
            if allowed_actions is not None:
                action = (kwargs.get("action") or "").strip()
                if action and action not in allowed_actions:
                    return ToolResult(
                        success=False,
                        error=(
                            f"⚠️ Plan Mode 下工具 '{tool_name}' 仅允许 action ∈ {sorted(allowed_actions)}，"
                            f"当前 action='{action}' 是写操作，已拒绝。"
                            f"如需写操作，先调 `exit_plan_mode`。"
                        ),
                    )


        if tool_name == "memory_recall":
            kwargs.setdefault("project_id", self._evolution_project_id or "")
            kwargs.setdefault("agent_id", self.id)


        if tool_name == "memory_write":
            kwargs.setdefault("project_id", self._evolution_project_id or "")


        if tool_name == "tool_activator":
            kwargs["_context"] = self._context


        if tool_name == "scratchpad":
            kwargs["_agent_id"] = self.id


        if tool_name == "ask_user":
            kwargs["_event_sink"] = self._event_sink
            kwargs["_agent_id"] = self.id
            kwargs["_agent_name"] = self.name
            kwargs["_depth"] = self._depth
            kwargs["_parent_agent"] = self

            kwargs["_session_id"] = getattr(self, "_current_session_id", "") or ""


        if tool_name in ("enter_plan_mode", "exit_plan_mode"):
            kwargs["_parent_agent"] = self


        if tool_name == "as_persona":
            kwargs["_agent"] = self






        if tool_name in ("dispatch_squad", "convene_council"):
            kwargs["_agent"] = self



        if tool_name in ("project_lookup", "project_open"):
            kwargs["_current_user"] = self._current_user
        if tool_name == "project_open":
            kwargs["_agent"] = self


        logger.info("tool_executing", agent=self.name, tool=tool_name, args_preview=arguments_json[:200])
        with tool_workspace_scope(self._bound_workspace):
            result = await tool.run(**kwargs)
        logger.info("tool_executed", agent=self.name, tool=tool_name,
                    success=result.success, duration_ms=round(result.duration_ms, 1))

        return result










    def _should_skip_evolution(
        self,
        *,
        user_message: str | list[dict],
        final_response: str,
        iterations: int,
    ) -> tuple[bool, str]:

        had_tools = bool(self._tool_usage_this_turn)
        u_text = self._user_message_to_text(user_message)
        u_len = len(u_text.strip())
        a_len = len((final_response or "").strip())

        if not had_tools and u_len < 20:
            return True, f"trivial_user_input(u_len={u_len})"
        if not had_tools and iterations < 2:
            return True, f"few_iterations({iterations})"
        if not had_tools and a_len < 100:
            return True, f"short_reply(a_len={a_len})"
        return False, ""

    def _schedule_evolution_after_task(
        self,
        *,
        completed_normally: bool,
        user_message: str | list[dict] = "",
        final_response: str = "",
        iterations: int = 0,
    ) -> None:

        if not settings.evolution.enabled or not settings.evolution.auto_after_task:
            return

        if not completed_normally and not final_response:
            return
        if not self._evolution_project_id:
            return

        skip, reason = self._should_skip_evolution(
            user_message=user_message,
            final_response=final_response,
            iterations=iterations,
        )
        if skip:
            logger.info("evolution_skipped", agent_id=self.id, reason=reason)
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("evolution_skip_no_event_loop", agent_id=self.id)
            return


        excerpt_snapshot = self._format_conversation_excerpt()
        tools_snapshot = self._tools_invoked_summary_block()

        loop.create_task(self._evolution_background_job(
            conversation_excerpt=excerpt_snapshot,
            tools_invoked_summary=tools_snapshot,
        ))
        logger.info(
            "evolution_route_scheduled",
            agent_id=self.id,
            project_id=self._evolution_project_id,
        )










        self._context.clear_messages()

    async def _evolution_background_job(
        self,
        *,
        conversation_excerpt: str | None = None,
        tools_invoked_summary: str | None = None,
    ) -> None:

        try:
            ctx = await self._build_evolution_route_context(
                conversation_excerpt=conversation_excerpt,
                tools_invoked_summary=tools_invoked_summary,
            )

            result = await EvolutionFactory().run_route(ctx)
            logger.info(
                "evolution_route_finished",
                agent_id=self.id,
                project_id=self._evolution_project_id,
                steps=result.completed_steps,
                error_steps=list(result.errors.keys()),
                stage_advanced=ctx.stage_just_advanced,
                stage_index=ctx.stage_index,
            )



            stage_suffix = ""
            if ctx.stage_just_advanced and ctx.stage_index > 0:
                raw_name = ctx.stage_name or "stage"

                slug = re.sub(r"[\s\\/:*?\"<>|]+", "-", raw_name).strip("-")[:30] or "stage"
                stage_suffix = f"stage{ctx.stage_index}_{slug}"


            if settings.memory.auto_extract_enabled:

                if result.memory_digest_raw and self._evolution_project_id:
                    await self._persist_project_memory(
                        result.memory_digest_raw,
                        stage_suffix=stage_suffix,
                    )

                if result.agent_memory_digest_raw:
                    await self._persist_agent_memory(
                        result.agent_memory_digest_raw,
                        stage_suffix=stage_suffix,
                    )




            if getattr(settings.evolution, "skill_draft_enabled", False):
                await self._maybe_persist_skill_draft(ctx)
        except Exception:
            logger.exception("evolution_route_job_failed", agent_id=self.id)

    async def _maybe_persist_skill_draft(self, ctx) -> None:

        try:
            draft = await EvolutionFactory().run_skill_draft(ctx)
        except Exception:
            logger.warning("evolution_skill_draft_failed", agent_id=self.id)
            return
        if not draft:


            logger.info(
                "evolution_skill_draft_skipped",
                agent_id=self.id,
                project_id=self._evolution_project_id,
                reason="model_skip_or_invalid_format",
            )
            return
        try:
            from cancer_claw.agent.adaptation import skill_draft_repo


            draft_name = ""
            for line in draft.splitlines():
                s = line.strip()
                if s.startswith("name:"):
                    draft_name = s.split(":", 1)[1].strip()
                    break

            draft_id = await skill_draft_repo.create_draft(
                name=draft_name,
                content=draft,
                source_session_id=getattr(self, "_current_session_id", None),
                source_agent_id=self.id,
                project_id=self._evolution_project_id,
            )
            logger.info(
                "evolution_skill_draft_persisted",
                agent_id=self.id,
                draft_id=draft_id,
                name=draft_name,
            )
        except Exception:
            logger.warning("evolution_skill_draft_persist_failed", agent_id=self.id)

    async def _persist_project_memory(self, raw: str, *, stage_suffix: str = "") -> None:

        snippet = MemoryWriter.parse_snippet(raw)
        if not snippet:
            return
        pid = self._evolution_project_id
        digest_dir = Path(settings.paths.projects_dir) / pid / "memory" / "digests"
        try:
            await MemoryWriter.append_to_daily(
                digest_dir, snippet, filename_suffix=stage_suffix
            )
            logger.info("memory_digest_persisted", scope="project", project_id=pid,
                        oneline=snippet.get("oneline", ""),
                        stage_suffix=stage_suffix or "(none)")
        except Exception:
            logger.warning("memory_digest_persist_failed", scope="project", project_id=pid)

    async def _persist_agent_memory(self, raw: str, *, stage_suffix: str = "") -> None:

        snippet = MemoryWriter.parse_snippet(raw)
        if not snippet:
            return
        digest_dir = Path(settings.paths.agents_dir) / self.id / "memory" / "digests"
        try:
            await MemoryWriter.append_to_daily(
                digest_dir, snippet, filename_suffix=stage_suffix
            )
            logger.info("memory_digest_persisted", scope="agent", agent_id=self.id,
                        oneline=snippet.get("oneline", ""),
                        stage_suffix=stage_suffix or "(none)")
        except Exception:
            logger.warning("memory_digest_persist_failed", scope="agent", agent_id=self.id)

    def _tools_invoked_summary_block(self) -> str:

        had = getattr(self, "_tool_usage_this_turn", None) or {}
        if had:
            tool_lines = [f"- `{n}`: {c} 次" for n, c in sorted(had.items())]
            return "\n".join(tool_lines)
        return "（本轮未记录工具调用）"

    def _inject_tool_images_as_user_message(self, images: list[dict]) -> None:

        import base64 as _b64

        content_parts: list[dict] = [
            {
                "type": "text",
                "text": (
                    f"[系统注入] 以下是工具提取的 {len(images)} 张图片，"
                    "请结合上面的工具文本输出一起分析："
                ),
            }
        ]

        for img in images:
            img_bytes = img.get("bytes") or b""
            mime = img.get("mime", "image/png")
            label = img.get("label", "图片")

            if not img_bytes:
                continue

            b64_str = _b64.b64encode(img_bytes).decode("ascii")
            data_url = f"data:{mime};base64,{b64_str}"

            content_parts.append({
                "type": "text",
                "text": f"[{label}]",
            })
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": data_url},
            })

        if len(content_parts) <= 1:
            return

        self._context.add_message("user", content_parts)

    def _compact_tool_feedback_for_context(self, raw: str, tool_name: str, tc_id: str) -> str:

        from cancer_claw.capabilities.toolkit.result_compact import compact_for_chat_context

        text = raw or ""
        compacted, meta = compact_for_chat_context(
            text,
            tool_name=tool_name,
            tag_suffix=tc_id or tool_name,
            parent_agent=self,
        )
        if meta.get("overflow"):
            logger.info(
                "tool_output_overflow_compact",
                agent_id=self.id,
                tool=tool_name,
                original_chars=meta.get("original_chars"),
                cache_path=meta.get("overflow_cache_path"),
            )
        return compacted

    def _format_conversation_excerpt(self, max_total: int = 14000) -> str:

        parts: list[str] = []
        used = 0
        for m in self._context.messages:
            role = m.get("role", "")
            if role == "assistant" and m.get("tool_calls"):
                chunk = f"[{role}]\n(tool_calls 已省略元数据长度)\n"
            else:
                content = m.get("content")
                if not isinstance(content, str):
                    content = str(content) if content is not None else ""
                cap = 4500 if role == "user" else 3500
                body = content[:cap] + ("…" if len(content) > cap else "")
                chunk = f"[{role}]\n{body}\n"
            if used + len(chunk) > max_total:
                parts.append("…\n[摘录因长度截断]")
                break
            parts.append(chunk)
            used += len(chunk)
        return "\n---\n".join(parts) if parts else "（无消息）"

    async def _load_evolution_catalog(self) -> tuple[str, str]:

        prior = ""
        crafts_lines: list[str] = []

        pid = self._evolution_project_id
        if pid:
            projects_dir = Path(settings.paths.projects_dir).expanduser()
            if not projects_dir.is_absolute():
                projects_dir = (Path.cwd() / projects_dir).resolve()
            mem_path = projects_dir / pid / "memory" / "MEMORY.md"

            def _read_mem() -> str:
                if not mem_path.is_file():
                    return ""
                return mem_path.read_text(encoding="utf-8")[:8000]

            try:
                prior = await asyncio.to_thread(_read_mem)
            except Exception:
                prior = ""

        try:
            from cancer_claw.resources.knowledge.craft_store import load_all_crafts

            enabled_recs = [r for r in load_all_crafts() if r.enabled]
            enabled_recs.sort(key=lambda r: (-(r.evolution_score or 0.0), r.id))
            for r in enabled_recs[:40]:
                desc = (r.description or "")[:200]
                crafts_lines.append(f"- `{r.id}` **{r.name or r.id}** — {desc}")
        except Exception as e:
            logger.warning("evolution_catalog_load_failed", error=str(e))

        crafts_block = "\n".join(crafts_lines) if crafts_lines else "（无或未加载）"
        return prior, crafts_block

    async def _build_evolution_route_context(
        self,
        *,
        conversation_excerpt: str | None = None,
        tools_invoked_summary: str | None = None,
    ) -> EvolutionRouteContext:

        prior, crafts_l1 = await self._load_evolution_catalog()
        if tools_invoked_summary is not None:
            tools_summary = tools_invoked_summary
        else:
            tools_summary = self._tools_invoked_summary_block()
        excerpt = (
            conversation_excerpt
            if conversation_excerpt is not None
            else self._format_conversation_excerpt()
        )
        return EvolutionRouteContext(
            agent_id=self.id,
            agent_name=self.name,
            conversation_excerpt=excerpt,
            tools_invoked_summary=tools_summary,
            project_id=self._evolution_project_id,
            project_hint=(self.description or "")[:800],
            existing_crafts_l1=crafts_l1,
            prior_memory_excerpt=prior,

            stage_just_advanced=self._charter_stage_just_advanced,
            stage_index=self._charter_stage_done_index,
            stage_name=self._charter_stage_done_name,
        )
