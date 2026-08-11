

from __future__ import annotations

from cancer_claw.agent.context_window.budget import ContextBudget, estimate_tokens
from cancer_claw.agent.context_window.history_dedup import compact_duplicate_tool_results

class ContextManager:


    def __init__(self, max_tokens: int | None = None):

        self._budget = ContextBudget(max_tokens)


        self._system_parts: dict[str, str] = {
            "framework": "",
            "project_instructions": "",
            "soul": "",



            "environment_snapshot": "",
            "task": "",



            "charter": "",
            "craft_index": "",
            "memory": "",
            "plan": "",
            "team_info": "",
        }


        self._messages: list[dict] = []



        self._active_tools: list[dict] = []


        self._active_craft_ids: set[str] = set()






        self._protected_tool_names: set[str] = set()










        self._pending_user_prefix: str = ""








        self._pending_clock: str = ""





    def set_system_prompt(self, soul: str = "", task: str = "",
                          framework: str = "", team_info: str = ""):

        if framework:
            self._system_parts["framework"] = framework
        if soul:
            self._system_parts["soul"] = soul
        if task:
            self._system_parts["task"] = task
        if team_info:
            self._system_parts["team_info"] = team_info
        self._update_budget()

    def set_craft_index(self, index_text: str):

        self._system_parts["craft_index"] = index_text
        self._update_budget()

    def set_memory(self, memory_text: str):

        self._system_parts["memory"] = memory_text
        self._update_budget()

    def set_project_instructions(self, text: str):

        self._system_parts["project_instructions"] = text or ""
        self._update_budget()

    def set_environment_snapshot(self, snapshot_text: str):



        self._system_parts["environment_snapshot"] = ""
        self._pending_user_prefix = (snapshot_text or "").strip()
        self._update_budget()

    def set_pending_user_prefix(self, text: str) -> None:

        self._pending_user_prefix = (text or "").strip()

    def append_to_pending_user_prefix(self, text: str) -> None:

        new_text = (text or "").strip()
        if not new_text:
            return
        if self._pending_user_prefix:
            self._pending_user_prefix = self._pending_user_prefix + "\n" + new_text
        else:
            self._pending_user_prefix = new_text

    def set_clock(self, clock_text: str) -> None:

        self._pending_clock = (clock_text or "").strip()

    def set_plan(self, plan_text: str):

        self._system_parts["plan"] = plan_text
        self._update_budget()

    def set_charter(self, charter_text: str) -> None:

        self._system_parts["charter"] = charter_text or ""
        self._update_budget()





    def add_message(self, role: str, content: str | list[dict], **extra):

        env_block: str = ""
        if role == "user" and (self._pending_user_prefix or self._pending_clock):
            env_lines: list[str] = []
            if self._pending_clock:
                env_lines.append(self._pending_clock)
            if self._pending_user_prefix:
                env_lines.append(self._pending_user_prefix)
            env_block = "<env>\n" + "\n".join(env_lines) + "\n</env>\n\n"
            self._pending_user_prefix = ""
            self._pending_clock = ""


        if env_block:
            if isinstance(content, list):
                new_content: list[dict] = list(content)
                if new_content and isinstance(new_content[0], dict) and new_content[0].get("type") == "text":

                    first = dict(new_content[0])
                    first["text"] = env_block + (first.get("text") or "")
                    new_content[0] = first
                else:
                    new_content.insert(0, {"type": "text", "text": env_block})
                content = new_content
            else:
                content = env_block + (content or "")

        msg = {"role": role, "content": content}
        msg.update(extra)
        self._messages.append(msg)
        self._update_budget()

    def add_tool_result(self, tool_call_id: str, content: str):

        self._messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        })
        self._update_budget()

    def add_assistant_tool_calls(self, content: str | None, tool_calls: list[dict],
                                   reasoning_content: str | None = None):

        msg = {"role": "assistant", "content": content or ""}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content
        self._messages.append(msg)
        self._update_budget()

    def inject_history_messages(self, history: list[dict]):

        for msg in history:
            new_msg: dict = {"role": msg["role"], "content": msg.get("content", "") or ""}

            if msg.get("tool_calls"):
                new_msg["tool_calls"] = msg["tool_calls"]
            if msg.get("tool_call_id"):
                new_msg["tool_call_id"] = msg["tool_call_id"]
            if msg.get("reasoning_content"):
                new_msg["reasoning_content"] = msg["reasoning_content"]
            self._messages.append(new_msg)
        if history:
            self._update_budget()

    def clear_messages(self):

        self._messages.clear()
        self._update_budget()

    def replace_messages(self, new_messages: list[dict]) -> None:

        self._messages = list(new_messages)
        self._update_budget()

    @property
    def messages(self) -> list[dict]:

        return list(self._messages)

    @property
    def message_count(self) -> int:

        return len(self._messages)





    def activate_tools(self, tool_schemas: list[dict], craft_id: str = ""):

        for schema in tool_schemas:

            func_name = schema.get("function", {}).get("name", "")
            if not any(t.get("function", {}).get("name") == func_name for t in self._active_tools):
                self._active_tools.append(schema)
        if craft_id:
            self._active_craft_ids.add(craft_id)
        self._update_budget()

    def deactivate_tools(self, tool_names: list[str], craft_id: str = ""):

        self._active_tools = [
            t for t in self._active_tools
            if t.get("function", {}).get("name", "") not in tool_names
        ]
        if craft_id:
            self._active_craft_ids.discard(craft_id)
        self._update_budget()

    def deactivate_all_tools(self):

        if not self._protected_tool_names:

            self._active_tools.clear()
            self._active_craft_ids.clear()
        else:

            self._active_tools = [
                t for t in self._active_tools
                if t.get("function", {}).get("name", "") in self._protected_tool_names
            ]

            self._active_craft_ids.clear()
        self._update_budget()

    def set_protected_tool_names(self, names: set[str]) -> None:

        self._protected_tool_names = set(names)

    @property
    def protected_tool_names(self) -> set[str]:

        return set(self._protected_tool_names)

    @property
    def active_tools(self) -> list[dict]:

        return list(self._active_tools)

    @property
    def active_craft_ids(self) -> set[str]:

        return set(self._active_craft_ids)





    def build_request(self) -> tuple[list[dict], list[dict] | None]:





        compact_duplicate_tool_results(self._messages)


        system_content = self._build_system_content()
        system_msg = {"role": "system", "content": system_content}


        messages = [system_msg] + self._messages


        tools = self._active_tools if self._active_tools else None

        return messages, tools

    def _build_system_content(self) -> str:

        parts = []

        if self._system_parts["framework"]:
            parts.append(self._system_parts["framework"])

        if self._system_parts["project_instructions"]:
            parts.append(self._system_parts["project_instructions"])

        if self._system_parts["soul"]:
            parts.append(f"# 你的身份与人格\n\n{self._system_parts['soul']}")






        if self._system_parts["task"]:
            parts.append(f"# 当前任务\n\n{self._system_parts['task']}")

        if self._system_parts["team_info"]:
            parts.append(f"# 团队信息\n\n{self._system_parts['team_info']}")




        if self._system_parts["charter"]:
            parts.append(f"# 任务契约（CHARTER）\n\n{self._system_parts['charter']}")

        if self._system_parts["plan"]:
            parts.append(f"# 执行计划\n\n{self._system_parts['plan']}")

        if self._system_parts["memory"]:
            parts.append(f"# 项目记忆\n\n{self._system_parts['memory']}")

        if self._system_parts["craft_index"]:
            parts.append(f"# 可用技能（Craft）\n\n{self._system_parts['craft_index']}")

        return "\n\n---\n\n".join(parts)





    def _update_budget(self):


        p0_text = (
            self._system_parts["framework"]
            + self._system_parts["project_instructions"]
            + self._system_parts["soul"]
            + self._system_parts["environment_snapshot"]
            + self._system_parts["task"]
        )
        p0_used = estimate_tokens(p0_text)


        tools_text = str(self._active_tools)
        p1_used = estimate_tokens(tools_text)


        p2_used = estimate_tokens(self._system_parts["memory"])



        p3_used = estimate_tokens(
            self._system_parts["plan"] + self._system_parts["charter"]
        )


        def _content_to_text(c) -> str:
            if not c:
                return ""
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                parts: list[str] = []
                for p in c:
                    if isinstance(p, dict) and p.get("type") == "text":
                        t = p.get("text") or ""
                        if isinstance(t, str):
                            parts.append(t)
                return "".join(parts)
            return str(c)

        conv_text = "".join(_content_to_text(m.get("content")) for m in self._messages)
        p4_used = estimate_tokens(conv_text)


        p5_used = estimate_tokens(self._system_parts["craft_index"])

        self._budget.update_usage(
            p0_used=p0_used, p1_used=p1_used, p2_used=p2_used,
            p3_used=p3_used, p4_used=p4_used, p5_used=p5_used,
        )

    @property
    def budget(self) -> ContextBudget:

        return self._budget

    def get_stats(self) -> dict:

        return {
            "message_count": len(self._messages),
            "active_tools": len(self._active_tools),
            "active_crafts": len(self._active_craft_ids),
            "budget": self._budget.get_summary(),
        }
