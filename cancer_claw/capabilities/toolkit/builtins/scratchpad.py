

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult
from cancer_claw.capabilities.toolkit.workspace import get_tool_workspace

logger = structlog.get_logger()

_locks: dict[str, asyncio.Lock] = {}

def _get_lock(project_root: Path) -> asyncio.Lock:
    key = str(project_root)
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock

_SECTIONS = ("CONTRACT", "TODO", "DOING", "DONE", "FINDINGS", "BLOCKERS")

_TEMPLATE = """# 项目共享黑板（SCRATCHPAD）

> 这是多智能体协作的共享工作区。所有 agent 都可读可写。
> 用 `scratchpad` 工具的 `read` / `post` / `update_status` 操作维护本文件，
> 不要直接 file_ops 编辑（避免破坏区段结构）。

## CONTRACT
（架构师在这里写下目录划分 / API / 数据模型 / 运行约定）

## TODO
（待认领的任务清单，格式：`- [ ] <id> | <owner_hint> | <task desc>`）

## DOING
（已认领、正在进行的任务，格式：`- [~] <id> | <owner> | <task desc>`）

## DONE
（已完成的任务，格式：`- [x] <id> | <owner> | <task desc> — <artifacts>`）

## FINDINGS
（共享发现：接口契约、数据格式、关键事实，每条带 `[agent_id @ time]` 前缀）

## BLOCKERS
（阻塞点 / 待澄清问题，每条带 `[agent_id @ time]` 前缀）
"""

def _utc_now_short() -> str:
    return datetime.now(timezone.utc).strftime("%m-%d %H:%M")

def _parse_sections(text: str) -> dict[str, list[str]]:

    sections: dict[str, list[str]] = {"_PREAMBLE": []}
    current = "_PREAMBLE"
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            name = stripped[3:].strip()
            if name in _SECTIONS:
                current = name
                sections.setdefault(current, [])
                continue
        sections.setdefault(current, []).append(line)

    for sec in _SECTIONS:
        sections.setdefault(sec, [])
    return sections

def _render_sections(sections: dict[str, list[str]]) -> str:

    parts: list[str] = []
    preamble = sections.get("_PREAMBLE", [])
    if preamble:
        parts.append("\n".join(preamble).rstrip())
        parts.append("")
    for sec in _SECTIONS:
        parts.append(f"## {sec}")
        body = sections.get(sec, [])

        while body and not body[0].strip():
            body.pop(0)
        while body and not body[-1].strip():
            body.pop()
        if body:
            parts.append("\n".join(body))
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"

def _strip_section_lines(lines: list[str]) -> list[str]:

    return [ln for ln in lines if ln.strip()]

class ScratchpadTool(BaseTool):


    @property
    def name(self) -> str:
        return "scratchpad"

    @property
    def description(self) -> str:
        return (
            "多智能体共享黑板（项目级 SCRATCHPAD.md）。支持："
            "read（读取整块或某区段）、"
            "post（向某区段追加一条记录，自动加 agent_id 和时间戳）、"
            "update_status（把某 task_id 在 TODO/DOING/DONE 之间迁移）。"
            "用于：master 派活看板、sub-agent 共享发现、阻塞回报、契约存档。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "scratchpad",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["read", "post", "update_status"],
                            "description": "read=读取；post=向区段追加；update_status=迁移任务状态",
                        },
                        "section": {
                            "type": "string",
                            "enum": list(_SECTIONS) + ["ALL"],
                            "description": (
                                "read 模式：要读的区段，ALL=整块（默认 ALL）；"
                                "post 模式：要追加的区段，必填"
                            ),
                        },
                        "content": {
                            "type": "string",
                            "description": "post 模式：要追加的内容（一行或多行，会被转成单条记录）",
                        },
                        "task_id": {
                            "type": "string",
                            "description": (
                                "post TODO/DOING/DONE 模式：任务 id（自定义短串，如 T01）；"
                                "update_status 模式：要迁移的任务 id"
                            ),
                        },
                        "owner": {
                            "type": "string",
                            "description": "post TODO/DOING/DONE 模式：负责人 agent_id 或 owner_hint",
                        },
                        "to_status": {
                            "type": "string",
                            "enum": ["TODO", "DOING", "DONE"],
                            "description": "update_status 模式：要迁移到的目标区段",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "read")

        agent_id = kwargs.get("_agent_id") or "unknown"

        ws = get_tool_workspace()
        if ws is None:
            return ToolResult(
                success=False,
                error="未绑定项目工作区。scratchpad 必须通过项目对话接口调用。",
            )
        path = ws.default_relative_root / "SCRATCHPAD.md"
        lock = _get_lock(ws.project_root)

        async with lock:
            if action == "read":
                return await self._read(path, kwargs.get("section") or "ALL")
            if action == "post":
                section = kwargs.get("section", "")
                if section not in _SECTIONS:
                    return ToolResult(
                        success=False,
                        error=f"post 必须指定 section（{', '.join(_SECTIONS)}）",
                    )
                return await self._post(
                    path=path,
                    section=section,
                    content=kwargs.get("content", "").strip(),
                    task_id=(kwargs.get("task_id") or "").strip(),
                    owner=(kwargs.get("owner") or "").strip(),
                    agent_id=agent_id,
                )
            if action == "update_status":
                return await self._update_status(
                    path=path,
                    task_id=(kwargs.get("task_id") or "").strip(),
                    to_status=kwargs.get("to_status", ""),
                    agent_id=agent_id,
                )
            return ToolResult(success=False, error=f"未知 action: {action}")





    def _ensure_file(self, path: Path) -> str:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_TEMPLATE, encoding="utf-8")
            return _TEMPLATE
        return path.read_text(encoding="utf-8")

    async def _read(self, path: Path, section: str) -> ToolResult:
        text = self._ensure_file(path)
        if section == "ALL":
            return ToolResult(success=True, output=text, data={"section": "ALL"})
        sections = _parse_sections(text)
        body = "\n".join(sections.get(section, [])).strip()
        if not body:
            body = f"（{section} 区段为空）"
        return ToolResult(
            success=True,
            output=f"## {section}\n{body}",
            data={"section": section},
        )

    async def _post(
        self,
        *,
        path: Path,
        section: str,
        content: str,
        task_id: str,
        owner: str,
        agent_id: str,
    ) -> ToolResult:
        if not content:
            return ToolResult(success=False, error="content 不能为空")

        text = self._ensure_file(path)
        sections = _parse_sections(text)

        ts = _utc_now_short()
        entry = self._format_entry(section, content, task_id, owner, agent_id, ts)
        sections.setdefault(section, []).append(entry)

        new_text = _render_sections(sections)
        path.write_text(new_text, encoding="utf-8")
        logger.info("scratchpad_posted", section=section, agent=agent_id, task_id=task_id or None)
        return ToolResult(
            success=True,
            output=f"已写入 {section}：\n{entry}",
            data={"section": section, "entry": entry},
        )

    def _format_entry(
        self,
        section: str,
        content: str,
        task_id: str,
        owner: str,
        agent_id: str,
        ts: str,
    ) -> str:

        one_line = " ".join(content.splitlines()).strip()
        if section == "TODO":
            tid = task_id or "T?"
            o = owner or "unassigned"
            return f"- [ ] {tid} | {o} | {one_line}"
        if section == "DOING":
            tid = task_id or "T?"
            o = owner or agent_id
            return f"- [~] {tid} | {o} | {one_line}"
        if section == "DONE":
            tid = task_id or "T?"
            o = owner or agent_id
            return f"- [x] {tid} | {o} | {one_line}"

        return f"- [{agent_id} @ {ts}] {one_line}"

    async def _update_status(
        self,
        *,
        path: Path,
        task_id: str,
        to_status: str,
        agent_id: str,
    ) -> ToolResult:
        if not task_id:
            return ToolResult(success=False, error="task_id 不能为空")
        if to_status not in ("TODO", "DOING", "DONE"):
            return ToolResult(success=False, error="to_status 必须是 TODO/DOING/DONE")

        text = self._ensure_file(path)
        sections = _parse_sections(text)

        moved_line: str | None = None
        moved_from: str | None = None
        for sec in ("TODO", "DOING", "DONE"):
            kept: list[str] = []
            for ln in sections.get(sec, []):
                if moved_line is None and self._line_has_task_id(ln, task_id):
                    moved_line = ln
                    moved_from = sec
                    continue
                kept.append(ln)
            sections[sec] = kept

        if moved_line is None:
            return ToolResult(
                success=False,
                error=f"找不到 task_id={task_id}（在 TODO/DOING/DONE 区段中均不存在）",
            )


        rewritten = self._rewrite_status_mark(moved_line, to_status, agent_id)
        sections.setdefault(to_status, []).append(rewritten)

        new_text = _render_sections(sections)
        path.write_text(new_text, encoding="utf-8")
        logger.info(
            "scratchpad_status_updated",
            task_id=task_id,
            from_=moved_from,
            to=to_status,
            agent=agent_id,
        )
        return ToolResult(
            success=True,
            output=f"task_id={task_id} 已从 {moved_from} 迁移到 {to_status}：\n{rewritten}",
            data={"task_id": task_id, "from": moved_from, "to": to_status},
        )

    @staticmethod
    def _line_has_task_id(line: str, task_id: str) -> bool:


        s = line.lstrip()
        if not s.startswith("- ["):
            return False

        try:
            close_idx = s.index("]")
            rest = s[close_idx + 1 :].strip()
            first_token = rest.split("|", 1)[0].strip()
            return first_token == task_id
        except ValueError:
            return False

    @staticmethod
    def _rewrite_status_mark(line: str, to_status: str, agent_id: str) -> str:
        marker = {"TODO": "[ ]", "DOING": "[~]", "DONE": "[x]"}[to_status]
        s = line.lstrip()
        if s.startswith("- ["):
            try:
                close_idx = s.index("]")
                rest = s[close_idx + 1 :]

                if to_status == "DOING":
                    parts = rest.lstrip().split("|", 2)
                    if len(parts) >= 2 and parts[1].strip() == "unassigned":
                        parts[1] = f" {agent_id} "
                        rest = " " + "|".join(parts)
                return f"- {marker}{rest}"
            except ValueError:
                pass
        return line
