

from __future__ import annotations

import re
from pathlib import Path

from cancer_claw.config import settings
from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

_RE_INDEX_LINE = re.compile(r"^-\s*(\d{2}:\d{2})\s*\|\s*(.+)$", re.MULTILINE)

_RE_EVENT_HEADER = re.compile(r"^##\s*(\d{2}:\d{2})\s*-\s*(.+)$", re.MULTILINE)

def _resolve_digest_dir(scope: str, project_id: str, agent_id: str) -> Path:

    if scope == "agent":
        return Path(settings.paths.agents_dir) / agent_id / "memory" / "digests"
    else:
        return Path(settings.paths.projects_dir) / project_id / "memory" / "digests"

class MemoryRecallTool(BaseTool):


    @property
    def name(self) -> str:
        return "memory_recall"

    @property
    def description(self) -> str:
        return (
            "查阅历史事件记忆。支持列出记忆文件、扫描日期范围索引、"
            "读取某天某时间点的事件详情、读取某天完整记忆。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "memory_recall",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["list_files", "scan_index", "read_event", "read_full"],
                            "description": (
                                "操作类型：\n"
                                "- list_files: 列出所有 digest 文件名\n"
                                "- scan_index: 扫描日期范围内的摘要索引\n"
                                "- read_event: 读取某天某时间点的事件详情\n"
                                "- read_full: 读取某天完整 digest 文件"
                            ),
                        },
                        "scope": {
                            "type": "string",
                            "enum": ["project", "agent"],
                            "description": "记忆范围：project=项目记忆，agent=智能体私有记忆",
                            "default": "project",
                        },
                        "start_date": {
                            "type": "string",
                            "description": "起始日期（YYYY-MM-DD），scan_index 时使用",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "结束日期（YYYY-MM-DD），scan_index 时使用",
                        },
                        "date": {
                            "type": "string",
                            "description": "目标日期（YYYY-MM-DD），read_event / read_full 时使用",
                        },
                        "time": {
                            "type": "string",
                            "description": "目标时间（HH:MM），read_event 时使用",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "")
        scope = kwargs.get("scope", "project")
        project_id = kwargs.get("project_id", "")
        agent_id = kwargs.get("agent_id", "")

        if not project_id and not agent_id:
            return ToolResult(
                success=False,
                error="缺少 project_id 或 agent_id，无法定位记忆目录",
            )

        digest_dir = _resolve_digest_dir(scope, project_id, agent_id)

        if action == "list_files":
            return self._list_files(digest_dir)
        elif action == "scan_index":
            return self._scan_index(
                digest_dir,
                kwargs.get("start_date", ""),
                kwargs.get("end_date", ""),
            )
        elif action == "read_event":
            return self._read_event(
                digest_dir,
                kwargs.get("date", ""),
                kwargs.get("time", ""),
            )
        elif action == "read_full":
            return self._read_full(digest_dir, kwargs.get("date", ""))
        else:
            return ToolResult(success=False, error=f"不支持的操作: {action}")

    def _list_files(self, digest_dir: Path) -> ToolResult:

        if not digest_dir.exists():
            return ToolResult(success=True, output="（无记忆文件）")

        files = sorted(digest_dir.glob("????-??-??.md"), reverse=True)
        if not files:
            return ToolResult(success=True, output="（无记忆文件）")

        lines = [f.stem for f in files]
        return ToolResult(
            success=True,
            output=f"共 {len(lines)} 个记忆文件：\n" + "\n".join(lines),
            data={"files": lines},
        )

    def _scan_index(
        self, digest_dir: Path, start_date: str, end_date: str
    ) -> ToolResult:

        if not digest_dir.exists():
            return ToolResult(success=True, output="（无记忆文件）")

        files = sorted(digest_dir.glob("????-??-??.md"), reverse=True)
        results: list[str] = []

        for md_file in files:
            date_str = md_file.stem

            if start_date and date_str < start_date:
                continue
            if end_date and date_str > end_date:
                continue

            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            for m in _RE_INDEX_LINE.finditer(content):
                time_str = m.group(1)
                oneline = m.group(2).strip()
                results.append(f"{date_str} {time_str} | {oneline}")

        if not results:
            date_range = ""
            if start_date or end_date:
                date_range = f"（{start_date or '...'} ~ {end_date or '...'}）"
            return ToolResult(
                success=True,
                output=f"该日期范围{date_range}内无记忆摘要",
            )

        return ToolResult(
            success=True,
            output=f"找到 {len(results)} 条摘要：\n" + "\n".join(results),
            data={"entries": results},
        )

    def _read_event(
        self, digest_dir: Path, date: str, time: str
    ) -> ToolResult:

        if not date:
            return ToolResult(success=False, error="缺少 date 参数")
        if not time:
            return ToolResult(success=False, error="缺少 time 参数")

        filepath = digest_dir / f"{date}.md"
        if not filepath.exists():
            return ToolResult(
                success=True,
                output=f"{date} 无记忆文件",
            )

        content = filepath.read_text(encoding="utf-8")


        matches = list(_RE_EVENT_HEADER.finditer(content))
        target_start = None
        target_end = None

        for i, m in enumerate(matches):
            if m.group(1) == time:
                target_start = m.start()

                if i + 1 < len(matches):
                    target_end = matches[i + 1].start()
                else:
                    target_end = len(content)
                break

        if target_start is None:
            return ToolResult(
                success=True,
                output=f"{date} {time} 无匹配事件",
            )

        event_text = content[target_start:target_end].strip()
        return ToolResult(
            success=True,
            output=event_text,
            data={"date": date, "time": time},
        )

    def _read_full(self, digest_dir: Path, date: str) -> ToolResult:

        if not date:
            return ToolResult(success=False, error="缺少 date 参数")

        filepath = digest_dir / f"{date}.md"
        if not filepath.exists():
            return ToolResult(
                success=True,
                output=f"{date} 无记忆文件",
            )

        content = filepath.read_text(encoding="utf-8")

        if len(content) > 8000:
            content = content[:8000] + "\n\n...（内容过长，已截断。请用 read_event 查看特定事件）"

        return ToolResult(
            success=True,
            output=content,
            data={"date": date},
        )
