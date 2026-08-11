

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import structlog

from cancer_claw.config import settings
from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult
from cancer_claw.capabilities.toolkit.workspace import get_tool_workspace

logger = structlog.get_logger()

_STATUS_DISPLAY = {
    "todo": "⏳ todo",
    "doing": "▶ doing",
    "done": "✓ done",
}

_STATUS_PARSE = {
    "todo": "todo",
    "doing": "doing",
    "done": "done",
    "⏳ todo": "todo",
    "▶ doing": "doing",
    "✓ done": "done",
    "⏳": "todo",
    "▶": "doing",
    "✓": "done",
    "x": "done",
    "[x]": "done",
    "[ ]": "todo",
    "[~]": "doing",
}

_SECTION_CONTRACT = "任务契约"
_SECTION_STAGES = "阶段进度"
_SECTION_CONSTRAINTS = "跨阶段约束"
_SECTION_DECISIONS = "关键决策记录"
_SECTION_EVENTS = "最近事件"
_SECTION_BLOCKERS = "当前阻塞"
_KNOWN_SECTIONS = (
    _SECTION_CONTRACT,
    _SECTION_STAGES,
    _SECTION_CONSTRAINTS,
    _SECTION_DECISIONS,
    _SECTION_EVENTS,
    _SECTION_BLOCKERS,
)

_HEADER_RE = re.compile(
    r"^>\s*创建于\s*(\d{4}-\d{2}-\d{2})\s*·\s*总阶段数\s*(\d+)"
    r"(?:\s*·\s*当前阶段\s*(\d+)/(\d+))?"
    r"(?:\s*·\s*状态[:：]\s*(\w+))?",
)

@dataclass
class StageRow:


    name: str
    status: str = "todo"
    finished_at: str = ""
    plan_archive: str = ""
    artifacts: str = ""

@dataclass
class CharterDoc:


    title: str = ""
    created_at: str = ""
    state: str = "in_progress"


    objective: str = ""
    scope: str = ""
    out_of_scope: str = ""
    acceptance: list[str] = field(default_factory=list)


    stages: list[StageRow] = field(default_factory=list)


    constraints: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


    unknown_sections: dict[str, list[str]] = field(default_factory=dict)



    @property
    def current_stage_index(self) -> int:

        for i, s in enumerate(self.stages):
            if s.status == "doing":
                return i + 1
        return 0

    @property
    def stage_total(self) -> int:
        return len(self.stages)

    @property
    def all_done(self) -> bool:
        return bool(self.stages) and all(s.status == "done" for s in self.stages)

def _normalize_status(text: str) -> str:

    t = text.strip().lower()
    if t in _STATUS_PARSE:
        return _STATUS_PARSE[t]

    if "done" in t or "完成" in t or "✓" in t:
        return "done"
    if "doing" in t or "进行" in t or "▶" in t:
        return "doing"
    if "todo" in t or "待办" in t or "⏳" in t:
        return "todo"
    return "todo"

def _parse_stages_table(lines: list[str]) -> list[StageRow]:

    stages: list[StageRow] = []
    for raw in lines:
        line = raw.strip()
        if not line.startswith("|"):
            continue

        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(set(c) <= {"-", " ", ":"} for c in cells):
            continue
        if len(cells) < 3:
            continue

        first = cells[0].lower()
        if first in {"#", "序号", "id"} and ("阶段" in cells[1] or "name" in cells[1].lower()):
            continue
        if first.isdigit() or first.startswith("阶段"):

            name = cells[1] if len(cells) > 1 else ""
            status = _normalize_status(cells[2]) if len(cells) > 2 else "todo"
            finished_at = cells[3] if len(cells) > 3 else ""
            plan_archive = cells[4] if len(cells) > 4 else ""
            artifacts = cells[5] if len(cells) > 5 else ""
            if name:
                stages.append(
                    StageRow(
                        name=name,
                        status=status,
                        finished_at=finished_at,
                        plan_archive=plan_archive,
                        artifacts=artifacts,
                    )
                )
    return stages

def _parse_bullets(lines: list[str]) -> list[str]:

    out: list[str] = []
    for raw in lines:
        s = raw.strip()
        if s.startswith("- ") or s.startswith("* "):
            out.append(s[2:].strip())
    return out

def _parse_contract_kv(lines: list[str]) -> tuple[str, str, str, list[str]]:

    objective = ""
    scope = ""
    out_of_scope = ""
    acceptance: list[str] = []
    in_acceptance = False
    kv_re = re.compile(r"^-\s*\*\*([^*]+)\*\*[:：]\s*(.*)$")
    for raw in lines:
        line = raw.rstrip()
        m = kv_re.match(line.strip())
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            in_acceptance = False
            if key in ("目标", "objective", "Objective"):
                objective = val
            elif key in ("范围", "scope", "Scope"):
                scope = val
            elif key in ("不做什么", "out_of_scope", "Out of scope"):
                out_of_scope = val
            elif key in ("验收", "acceptance", "Acceptance"):
                if val:
                    acceptance.append(val)
                else:
                    in_acceptance = True
            continue
        if in_acceptance:
            s = line.strip()
            if s.startswith("- ") or s.startswith("* "):
                acceptance.append(s[2:].strip())
            elif not s:
                continue
            else:
                in_acceptance = False
    return objective, scope, out_of_scope, acceptance

def parse_charter(text: str) -> CharterDoc:

    doc = CharterDoc()
    if not text or not text.strip():
        return doc

    lines = text.splitlines()
    i = 0
    n = len(lines)


    while i < n and not lines[i].strip():
        i += 1
    if i < n and lines[i].strip().startswith("# "):
        doc.title = lines[i].strip()[2:].strip()
        i += 1


    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        m = _HEADER_RE.match(s)
        if m:
            doc.created_at = m.group(1) or ""
            doc.state = m.group(5) or "in_progress"
            i += 1
            continue
        if s.startswith("> "):

            i += 1
            continue
        break


    current_section: str | None = None
    section_lines: list[str] = []

    def flush():

        nonlocal section_lines
        if current_section is None:
            section_lines = []
            return
        if current_section == _SECTION_CONTRACT:
            o, s, oos, acc = _parse_contract_kv(section_lines)
            doc.objective = o or doc.objective
            doc.scope = s or doc.scope
            doc.out_of_scope = oos or doc.out_of_scope
            if acc:
                doc.acceptance = acc
        elif current_section == _SECTION_STAGES:
            stages = _parse_stages_table(section_lines)
            if stages:
                doc.stages = stages
        elif current_section == _SECTION_CONSTRAINTS:
            bullets = _parse_bullets(section_lines)
            if bullets:
                doc.constraints = bullets
        elif current_section == _SECTION_DECISIONS:
            bullets = _parse_bullets(section_lines)
            if bullets:
                doc.decisions = bullets
        elif current_section == _SECTION_EVENTS:
            bullets = _parse_bullets(section_lines)
            if bullets:
                doc.events = bullets
        elif current_section == _SECTION_BLOCKERS:
            bullets = _parse_bullets(section_lines)
            if bullets:
                doc.blockers = bullets
        else:

            doc.unknown_sections[current_section] = list(section_lines)
        section_lines = []

    while i < n:
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("## "):
            flush()
            title = stripped[3:].strip()

            matched = None
            for known in _KNOWN_SECTIONS:
                if title.startswith(known):
                    matched = known
                    break
            current_section = matched if matched else title
        else:
            section_lines.append(line)
        i += 1
    flush()

    return doc

def serialize_charter(doc: CharterDoc) -> str:

    parts: list[str] = []
    parts.append(f"# {doc.title}" if doc.title else "# 任务契约")
    parts.append("")
    header_bits: list[str] = []
    if doc.created_at:
        header_bits.append(f"创建于 {doc.created_at}")
    if doc.stages:
        header_bits.append(f"总阶段数 {doc.stage_total}")
        cur = doc.current_stage_index
        if cur > 0:
            header_bits.append(f"当前阶段 {cur}/{doc.stage_total}")
    header_bits.append(f"状态: {doc.state}")
    parts.append("> " + " · ".join(header_bits))
    parts.append("")


    parts.append(f"## {_SECTION_CONTRACT}")
    if doc.objective:
        parts.append(f"- **目标**：{doc.objective}")
    if doc.scope:
        parts.append(f"- **范围**：{doc.scope}")
    if doc.out_of_scope:
        parts.append(f"- **不做什么**：{doc.out_of_scope}")
    if doc.acceptance:
        parts.append("- **验收**：")
        for a in doc.acceptance:
            parts.append(f"  - {a}")
    if not (doc.objective or doc.scope or doc.out_of_scope or doc.acceptance):
        parts.append("- （待补充）")
    parts.append("")


    parts.append(f"## {_SECTION_STAGES}")
    parts.append("| # | 阶段名 | 状态 | 完成时间 | PLAN 归档 | 关键产出 |")
    parts.append("|---|---|---|---|---|---|")
    for idx, s in enumerate(doc.stages, start=1):
        status_disp = _STATUS_DISPLAY.get(s.status, s.status)

        artifacts_safe = (s.artifacts or "").replace("|", "\\|")
        parts.append(
            f"| {idx} | {s.name} | {status_disp} | {s.finished_at} | {s.plan_archive} | {artifacts_safe} |"
        )
    if not doc.stages:
        parts.append("| 1 | （未定义） | ⏳ todo |  |  |  |")
    parts.append("")


    parts.append(f"## {_SECTION_CONSTRAINTS}")
    if doc.constraints:
        for c in doc.constraints:
            parts.append(f"- {c}")
    else:
        parts.append("- （无）")
    parts.append("")


    parts.append(f"## {_SECTION_DECISIONS}")
    if doc.decisions:
        for d in doc.decisions:
            parts.append(f"- {d}")
    else:
        parts.append("- （暂无记录）")
    parts.append("")


    parts.append(f"## {_SECTION_EVENTS}")
    if doc.events:
        for e in doc.events:
            parts.append(f"- {e}")
    else:
        parts.append("- （暂无事件）")
    parts.append("")


    parts.append(f"## {_SECTION_BLOCKERS}")
    if doc.blockers:
        for b in doc.blockers:
            parts.append(f"- {b}")
    else:
        parts.append("- （空表示无阻塞）")
    parts.append("")


    for name, body in doc.unknown_sections.items():
        parts.append(f"## {name}")
        parts.extend(body)
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"

_locks: dict[str, asyncio.Lock] = {}

_last_write_times: dict[tuple[str, str], float] = {}

def _get_lock(project_root: Path) -> asyncio.Lock:
    key = str(project_root)
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock

def _should_debounce(project_root: Path, field_name: str, interval_seconds: int) -> bool:

    if interval_seconds <= 0:
        return False
    key = (str(project_root), field_name)
    now = time.monotonic()
    last = _last_write_times.get(key, 0.0)
    if now - last < interval_seconds:
        return True
    _last_write_times[key] = now
    return False

def _slugify(text: str, max_len: int = 40) -> str:

    if not text:
        return "untitled"
    s = text.strip()
    s = re.sub(r"[\s\\/:*?\"<>|]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-")
    return s[:max_len] or "untitled"

def _now_ymdhm() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")

def _now_ymd() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")

class TaskCharterTool(BaseTool):


    @property
    def name(self) -> str:
        return "task_charter"

    @property
    def description(self) -> str:
        return (
            "长任务（≥3 阶段）的任务契约 + 阶段进度账本 + 事件滑动窗口。"
            "init 写入新契约；read 读全文；log_event 记事件（60s 防抖）；"
            "advance_stage 必须与 attempt_completion 配对使用以让一次流自然结束触发进化链；"
            "update_decision / update_blocker 维护决策与阻塞；finalize 归档全任务结束。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "task_charter",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "init",
                                "read",
                                "log_event",
                                "advance_stage",
                                "update_decision",
                                "update_blocker",
                                "finalize",
                            ],
                            "description": "操作类型",
                        },
                        "title": {
                            "type": "string",
                            "description": "init: 长任务标题（用于归档文件名 slug）",
                        },
                        "stages": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "init: 阶段名列表（顺序即阶段顺序，第一个自动 doing）",
                        },
                        "objective": {
                            "type": "string",
                            "description": "init: 业务级 1 句话目标",
                        },
                        "scope": {
                            "type": "string",
                            "description": "init: 包含什么",
                        },
                        "out_of_scope": {
                            "type": "string",
                            "description": "init: 不做什么",
                        },
                        "acceptance": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "init: 用户视角的验收条件列表",
                        },
                        "constraints": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "init: 跨阶段约束列表（可选）",
                        },
                        "text": {
                            "type": "string",
                            "description": (
                                "log_event: 一行事件描述；"
                                "update_blocker: 阻塞描述（空字符串=清空）"
                            ),
                        },
                        "result_summary": {
                            "type": "string",
                            "description": "advance_stage: 当前阶段的成果摘要",
                        },
                        "artifacts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "advance_stage: 关键产出（文件路径或 API 列表）",
                        },
                        "plan_archive": {
                            "type": "string",
                            "description": "advance_stage: 当前阶段 PLAN.md 归档后的路径（可选）",
                        },
                        "decision": {
                            "type": "string",
                            "description": "update_decision: 决策内容",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "update_decision: 决策理由（可选）",
                        },
                        "final_summary": {
                            "type": "string",
                            "description": "finalize: 全任务总结，写入归档头部",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    async def execute(self, action: str = "", **kwargs) -> ToolResult:
        ws = get_tool_workspace()
        if ws is None:
            return ToolResult(
                success=False,
                error=(
                    "task_charter 需要先绑定项目工作区（bind_tool_workspace）。"
                    "如果你在 sub-agent 内调用，请检查 spawn_oneshot 是否传入了 workspace。"
                ),
            )
        action = (action or "").strip().lower()
        if not action:
            return ToolResult(success=False, error="缺少 action 参数")

        charter_path: Path = ws.default_relative_root / "CHARTER.md"
        lock = _get_lock(ws.project_root)

        async with lock:
            if action == "init":
                return await self._action_init(charter_path, kwargs)
            if action == "read":
                return await self._action_read(charter_path)
            if action == "log_event":
                return await self._action_log_event(ws.project_root, charter_path, kwargs)
            if action == "advance_stage":
                return await self._action_advance_stage(charter_path, kwargs)
            if action == "update_decision":
                return await self._action_update_decision(charter_path, kwargs)
            if action == "update_blocker":
                return await self._action_update_blocker(charter_path, kwargs)
            if action == "finalize":
                return await self._action_finalize(ws, charter_path, kwargs)
            return ToolResult(success=False, error=f"未知 action: {action}")



    async def _action_init(self, charter_path: Path, kw: dict) -> ToolResult:
        if charter_path.exists():
            return ToolResult(
                success=False,
                error=(
                    f"CHARTER.md 已存在于 {charter_path}。"
                    "如要重建请先 finalize（归档旧 charter），或用 file_ops 手动备份后删除。"
                ),
            )
        title = (kw.get("title") or "").strip()
        if not title:
            return ToolResult(success=False, error="init 需要非空的 title 参数")
        stages_raw = kw.get("stages") or []
        if not isinstance(stages_raw, list) or len(stages_raw) < 1:
            return ToolResult(
                success=False,
                error="init 需要 stages 参数为非空字符串列表（长任务至少 1 个阶段）",
            )
        stages: list[StageRow] = []
        for idx, name in enumerate(stages_raw):
            s = str(name).strip()
            if not s:
                continue
            stages.append(StageRow(name=s, status=("doing" if idx == 0 else "todo")))
        if not stages:
            return ToolResult(success=False, error="stages 内所有项都是空字符串")

        doc = CharterDoc(
            title=title,
            created_at=_now_ymd(),
            state="in_progress",
            objective=(kw.get("objective") or "").strip(),
            scope=(kw.get("scope") or "").strip(),
            out_of_scope=(kw.get("out_of_scope") or "").strip(),
            acceptance=[a.strip() for a in (kw.get("acceptance") or []) if str(a).strip()],
            stages=stages,
            constraints=[c.strip() for c in (kw.get("constraints") or []) if str(c).strip()],
        )
        text = serialize_charter(doc)
        charter_path.parent.mkdir(parents=True, exist_ok=True)
        charter_path.write_text(text, encoding="utf-8", newline="\n")
        logger.info(
            "charter_init",
            path=str(charter_path),
            title=title,
            stages=len(stages),
        )
        return ToolResult(
            success=True,
            output=(
                f"CHARTER.md 已创建（{len(stages)} 阶段，当前阶段 1/{len(stages)}: "
                f"{stages[0].name}）。后续每阶段完成请调 advance_stage + attempt_completion。"
            ),
            data={"path": str(charter_path), "stage_total": len(stages)},
        )

    async def _action_read(self, charter_path: Path) -> ToolResult:
        if not charter_path.exists():
            return ToolResult(
                success=True,
                output="（无 CHARTER.md，未初始化长任务契约。如本任务体量较大可调 task_charter.init）",
                data={"exists": False},
            )
        text = charter_path.read_text(encoding="utf-8")
        doc = parse_charter(text)
        return ToolResult(
            success=True,
            output=text,
            data={
                "exists": True,
                "path": str(charter_path),
                "title": doc.title,
                "current_stage_index": doc.current_stage_index,
                "stage_total": doc.stage_total,
                "state": doc.state,
                "all_done": doc.all_done,
            },
        )

    async def _action_log_event(
        self, project_root: Path, charter_path: Path, kw: dict
    ) -> ToolResult:
        text = (kw.get("text") or "").strip()
        if not text:
            return ToolResult(success=False, error="log_event 需要非空的 text")
        if not charter_path.exists():
            return ToolResult(
                success=False,
                error="CHARTER.md 不存在，请先 init",
            )
        debounce = settings.charter.log_event_debounce_seconds
        if _should_debounce(project_root, "log_event", debounce):
            return ToolResult(
                success=True,
                output=f"log_event 在 {debounce}s 防抖期内被静默跳过（避免击穿 prefix cache）。",
                data={"debounced": True},
            )
        doc = parse_charter(charter_path.read_text(encoding="utf-8"))
        window = settings.charter.event_window_size
        entry = f"{_now_ymdhm()} | {text}"
        doc.events.append(entry)

        if window > 0 and len(doc.events) > window:
            doc.events = doc.events[-window:]
        charter_path.write_text(serialize_charter(doc), encoding="utf-8", newline="\n")
        return ToolResult(
            success=True,
            output=f"已追加事件（窗口 {len(doc.events)}/{window}）：{entry}",
            data={"event": entry, "window_used": len(doc.events)},
        )

    async def _action_advance_stage(self, charter_path: Path, kw: dict) -> ToolResult:
        if not charter_path.exists():
            return ToolResult(success=False, error="CHARTER.md 不存在，请先 init")
        summary = (kw.get("result_summary") or "").strip()
        if not summary:
            return ToolResult(
                success=False,
                error="advance_stage 必须提供 result_summary（当前阶段做完了什么）",
            )
        artifacts = kw.get("artifacts") or []
        if not isinstance(artifacts, list):
            artifacts = [str(artifacts)]
        artifacts_str = ", ".join(str(a).strip() for a in artifacts if str(a).strip())
        plan_archive = (kw.get("plan_archive") or "").strip()

        doc = parse_charter(charter_path.read_text(encoding="utf-8"))
        if not doc.stages:
            return ToolResult(success=False, error="charter 内没有阶段表，无法 advance")


        cur_idx = -1
        for i, s in enumerate(doc.stages):
            if s.status == "doing":
                cur_idx = i
                break
        if cur_idx < 0:
            for i, s in enumerate(doc.stages):
                if s.status == "todo":
                    cur_idx = i
                    break
        if cur_idx < 0:
            return ToolResult(
                success=False,
                error="所有阶段都已 done。建议直接 finalize 归档整个 charter。",
            )


        cur = doc.stages[cur_idx]
        cur.status = "done"
        cur.finished_at = _now_ymdhm()
        if plan_archive:
            cur.plan_archive = plan_archive
        if artifacts_str:

            cur.artifacts = (cur.artifacts + "; " + artifacts_str) if cur.artifacts else artifacts_str


        event_text = f"阶段 {cur_idx + 1} 「{cur.name}」完成 — {summary}"
        doc.events.append(f"{_now_ymdhm()} | {event_text}")
        window = settings.charter.event_window_size
        if window > 0 and len(doc.events) > window:
            doc.events = doc.events[-window:]


        next_idx = -1
        for i in range(cur_idx + 1, len(doc.stages)):
            if doc.stages[i].status == "todo":
                doc.stages[i].status = "doing"
                next_idx = i
                break


        if next_idx < 0 and doc.all_done:
            output = (
                f"阶段 {cur_idx + 1} 「{cur.name}」已标记完成。"
                f"所有 {doc.stage_total} 阶段均已 done，建议下一步调 finalize 归档 charter。"
            )
        elif next_idx < 0:
            output = (
                f"阶段 {cur_idx + 1} 「{cur.name}」已标记完成。"
                f"后续没有 todo 阶段。可调 finalize 或手动 update charter 添加新阶段。"
            )
        else:
            nxt = doc.stages[next_idx]
            output = (
                f"阶段 {cur_idx + 1} 「{cur.name}」完成 ✓；"
                f"阶段 {next_idx + 1} 「{nxt.name}」已切换为 ▶ doing。"
                f"接下来请调用 attempt_completion 让本轮流自然结束，"
                f"框架会触发进化链把本阶段沉淀到 memory/digests/。"
            )

        charter_path.write_text(serialize_charter(doc), encoding="utf-8", newline="\n")
        logger.info(
            "charter_advance_stage",
            stage_done=cur.name,
            stage_done_idx=cur_idx + 1,
            stage_next_idx=next_idx + 1 if next_idx >= 0 else 0,
            all_done=doc.all_done,
        )
        return ToolResult(
            success=True,
            output=output,
            data={
                "stage_done": cur.name,
                "stage_done_index": cur_idx + 1,
                "stage_next_index": next_idx + 1 if next_idx >= 0 else 0,
                "stage_next_name": doc.stages[next_idx].name if next_idx >= 0 else "",
                "all_done": doc.all_done,
            },
        )

    async def _action_update_decision(self, charter_path: Path, kw: dict) -> ToolResult:
        if not charter_path.exists():
            return ToolResult(success=False, error="CHARTER.md 不存在，请先 init")
        decision = (kw.get("decision") or "").strip()
        if not decision:
            return ToolResult(success=False, error="update_decision 需要非空的 decision")
        rationale = (kw.get("rationale") or "").strip()
        doc = parse_charter(charter_path.read_text(encoding="utf-8"))
        entry = f"{_now_ymdhm()} | {decision}" + (f"（理由：{rationale}）" if rationale else "")
        doc.decisions.append(entry)
        charter_path.write_text(serialize_charter(doc), encoding="utf-8", newline="\n")
        return ToolResult(
            success=True,
            output=f"已记录决策：{entry}",
            data={"decision": entry, "decisions_total": len(doc.decisions)},
        )

    async def _action_update_blocker(self, charter_path: Path, kw: dict) -> ToolResult:
        if not charter_path.exists():
            return ToolResult(success=False, error="CHARTER.md 不存在，请先 init")
        text = kw.get("text", "")
        text_stripped = (text or "").strip()
        doc = parse_charter(charter_path.read_text(encoding="utf-8"))
        if not text_stripped:
            doc.blockers = []
            output = "已清空阻塞段。"
        else:

            doc.blockers = [
                line.strip().lstrip("- ").strip()
                for line in text_stripped.splitlines()
                if line.strip()
            ]
            output = f"已重写阻塞段（{len(doc.blockers)} 条）。"
        charter_path.write_text(serialize_charter(doc), encoding="utf-8", newline="\n")
        return ToolResult(
            success=True,
            output=output,
            data={"blockers_total": len(doc.blockers)},
        )

    async def _action_finalize(self, ws, charter_path: Path, kw: dict) -> ToolResult:
        if not charter_path.exists():
            return ToolResult(
                success=False,
                error="CHARTER.md 不存在；任务尚未 init 不需要 finalize。",
            )
        final_summary = (kw.get("final_summary") or "").strip()
        doc = parse_charter(charter_path.read_text(encoding="utf-8"))


        doc.state = "finalized"
        if final_summary:
            doc.events.append(f"{_now_ymdhm()} | [FINALIZE] {final_summary}")
            window = settings.charter.event_window_size
            if window > 0 and len(doc.events) > window:
                doc.events = doc.events[-window:]

        archive_dir: Path = ws.default_relative_root / "docs" / "charters"
        archive_dir.mkdir(parents=True, exist_ok=True)
        ymd = _now_ymd().replace("-", "")
        slug = _slugify(doc.title)
        archive_path = archive_dir / f"{ymd}_{slug}.md"


        archive_text = serialize_charter(doc)
        if final_summary:

            archive_text = archive_text.replace(
                f"## {_SECTION_CONTRACT}",
                f"## 最终总结\n\n{final_summary}\n\n## {_SECTION_CONTRACT}",
                1,
            )
        archive_path.write_text(archive_text, encoding="utf-8", newline="\n")


        unfinished = [s.name for s in doc.stages if s.status != "done"]


        try:
            charter_path.unlink()
        except FileNotFoundError:
            pass

        logger.info(
            "charter_finalized",
            archive_path=str(archive_path),
            title=doc.title,
            unfinished_stages=unfinished,
        )
        output = (
            f"CHARTER.md 已归档到 {archive_path.relative_to(ws.project_root)}，"
            f"workspace/CHARTER.md 已删除。"
        )
        if unfinished:
            output += f"\n⚠ 注意：以下阶段未标记 done 即被 finalize：{', '.join(unfinished)}"
        return ToolResult(
            success=True,
            output=output,
            data={
                "archive_path": str(archive_path),
                "unfinished_stages": unfinished,
            },
        )
