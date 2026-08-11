

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import structlog

from cancer_claw.config import settings
from cancer_claw.agent.context_window.budget import estimate_tokens
from cancer_claw.db import get_db

logger = structlog.get_logger()

_RE_INDEX_LINE = re.compile(r"^-\s*(\d{2}:\d{2})\s*\|\s*(.+)$", re.MULTILINE)

_TOOL_RESULT_MARK = "__OK_TOOLRESULT_v1__"
_TOOL_CALLS_MARK = "__OK_TOOLCALLS_v1__"

def _format_sqlite_ts(ts_raw) -> str:

    if not ts_raw:
        return ""
    if isinstance(ts_raw, datetime):
        dt = ts_raw
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    else:
        s = str(ts_raw).strip()
        if not s:
            return ""

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
        else:

            try:
                dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except ValueError:
                return ""

    return dt.astimezone().strftime("%Y-%m-%d %H:%M")

_TS_PREFIX_RE = re.compile(
    r"^\s*\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\]\s*\n?",
)

_TS_ONLY_RE = re.compile(
    r"^\s*\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\]\s*$",
)

def strip_ts_prefix(text: str) -> str:

    if not text:
        return text
    return _TS_PREFIX_RE.sub("", text, count=1)

def looks_like_ts_only(text: str | None) -> bool:

    if not text:
        return True
    return bool(_TS_ONLY_RE.match(text.strip()))

def _attach_ts_prefix(msg: dict, ts_str: str) -> dict:

    if not ts_str:
        return msg
    if msg.get("role") not in ("user", "tool"):
        return msg
    new_msg = dict(msg)
    base = new_msg.get("content") or ""
    new_msg["content"] = f"[{ts_str}]\n{base}"
    return new_msg

def _parse_stored_content(
    role: str,
    content: str,
    *,
    tool_calls_json: str | None = None,
    tool_call_id: str | None = None,
    name: str | None = None,
) -> dict:


    if role == "tool" and tool_call_id:
        msg: dict = {
            "role": "tool",
            "tool_call_id": str(tool_call_id),
            "content": content or "",
        }
        if name:
            msg["name"] = str(name)
        return msg
    if role == "assistant" and tool_calls_json:
        try:
            tcs = json.loads(tool_calls_json)
            if isinstance(tcs, list) and tcs:
                m: dict = {"role": "assistant", "content": content or ""}
                m["tool_calls"] = tcs
                return m
        except Exception:
            pass


    if role == "tool" and content.startswith(_TOOL_RESULT_MARK):
        try:
            head, rest = content.split("\n", 1) if "\n" in content else (content, "")
            meta = json.loads(head[len(_TOOL_RESULT_MARK):])
            return {
                "role": "tool",
                "tool_call_id": str(meta.get("tool_call_id") or ""),
                "content": rest,
            }
        except Exception:
            pass
    elif role == "assistant" and content.startswith(_TOOL_CALLS_MARK):
        try:
            head, rest = content.split("\n", 1) if "\n" in content else (content, "")
            meta = json.loads(head[len(_TOOL_CALLS_MARK):])
            tool_calls = meta.get("tool_calls") or []
            msg2: dict = {"role": "assistant", "content": rest}
            if tool_calls:
                msg2["tool_calls"] = tool_calls
            return msg2
        except Exception:
            pass
    return {"role": role, "content": content}

def _budget_and_repair(msgs: list[dict], max_tokens: int) -> list[dict]:

    used = 0
    cut_idx = 0
    for i in range(len(msgs) - 1, -1, -1):
        t = estimate_tokens(msgs[i].get("content", "") or "")
        if used + t > max_tokens:
            cut_idx = i + 1
            break
        used += t
    msgs = msgs[cut_idx:]

    return _repair_tool_pairs(msgs)

def _repair_tool_pairs(msgs: list[dict]) -> list[dict]:

    if not msgs:
        return msgs


    out = list(msgs)
    while out and out[0].get("role") == "tool":
        out.pop(0)


    expected_ids: set[str] = set()
    fulfilled_ids: set[str] = set()
    for m in out:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                tc_id = tc.get("id") or ""
                if tc_id:
                    expected_ids.add(tc_id)
        elif m.get("role") == "tool":
            tc_id = m.get("tool_call_id", "")
            if tc_id:
                fulfilled_ids.add(tc_id)

    missing_ids = expected_ids - fulfilled_ids
    if not missing_ids:
        return out


    repaired: list[dict] = []
    for m in out:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            kept = [tc for tc in m["tool_calls"] if tc.get("id") not in missing_ids]
            new_m = dict(m)
            if kept:
                new_m["tool_calls"] = kept
            else:
                new_m.pop("tool_calls", None)
                if not (new_m.get("content") or "").strip():
                    new_m["content"] = "[历史中断：上一轮工具调用记录在加载时被截断]"
            repaired.append(new_m)
        elif m.get("role") == "tool" and m.get("tool_call_id") in missing_ids:
            continue
        else:
            repaired.append(m)
    return repaired

class WorkingMemory:


    def __init__(self, project_id: str, agent_id: str,
                 cross_agent_ids: list[str] | None = None):
        self.project_id = project_id
        self.agent_id = agent_id

        self.cross_agent_ids: list[str] = cross_agent_ids or []


        self._project_digest_dir = (
            Path(settings.paths.projects_dir) / project_id / "memory" / "digests"
        )
        self._agent_digest_dir = (
            Path(settings.paths.agents_dir) / agent_id / "memory" / "digests"
        )





        self._runtime_platform_id: str | None = None
        self._runtime_page_context: dict | None = None






        self._runtime_session_id: str | None = None

    def set_runtime_hint(
        self,
        platform_id: str | None,
        page_context: dict | None = None,
    ) -> None:

        self._runtime_platform_id = (platform_id or "").strip() or None
        self._runtime_page_context = page_context if page_context else None

    def set_session_hint(self, session_id: str | None) -> None:

        self._runtime_session_id = (session_id or "").strip() or None

    def build_runtime_hint_text(self) -> str:

        if not self._runtime_platform_id:
            return ""
        lines = ["[当下情境]", f"- 来源平台：{self._runtime_platform_id}"]
        ctx = self._runtime_page_context or {}
        url = (ctx.get("url") or "").strip()
        title = (ctx.get("title") or "").strip()
        if url or title:
            seg = url
            if title:
                seg = f"{seg} — {title}" if seg else title
            lines.append(f"- 当前页面：{seg}")
        sel = (ctx.get("selection") or "").strip()
        if sel:
            if len(sel) > 200:
                sel = sel[:200] + "..."
            lines.append(f"- 用户选中文本：{sel}")
        return "\n".join(lines)

    async def build(self) -> str:

        parts: list[str] = []


        turns = await self._load_recent_turns()
        if turns:
            cross_note = (
                f"（含主智能体对话，来源：{', '.join(self.cross_agent_ids)}）"
                if self.cross_agent_ids else ""
            )
            lines = [f"## 近期对话回顾 {cross_note}\n"]
            for turn in turns:
                role = turn["role"]
                content = turn["content"]
                source = turn.get("source_agent", "")
                ts = turn.get("ts", "")

                if len(content) > 300:
                    content = content[:300] + "..."
                source_tag = f"[{source}]" if source and source != self.agent_id else ""
                ts_tag = f"[{ts}]" if ts else ""
                lines.append(f"{ts_tag}[{role}]{source_tag}: {content}")
            parts.append("\n".join(lines))


        onelines = self._load_recent_onelines()
        if onelines:
            lines = ["## 近期记忆摘要\n"]
            for entry in onelines:
                lines.append(f"- {entry}")
            parts.append("\n".join(lines))

        return "\n\n".join(parts)

    async def load_as_messages(
        self,
        max_tokens: int = 8000,
        *,
        platform_id: str | None = None,
    ) -> list[dict]:


        effective_platform = platform_id or self._runtime_platform_id
        if effective_platform:
            return await self._load_layered_messages(
                max_tokens=max_tokens,
                platform_id=effective_platform,
            )
        return await self._load_legacy_messages(max_tokens=max_tokens)

    async def _load_legacy_messages(self, max_tokens: int) -> list[dict]:

        n = settings.memory.conv_load_recent_turns
        db = await get_db()

        cross_ids = [aid for aid in self.cross_agent_ids if aid != self.agent_id]
        session_filter = self._runtime_session_id



        SELECT_COLS = (
            "id, role, content, tool_calls_json, tool_call_id, name, agent_id, created_at"
        )

        if not cross_ids:
            if session_filter:
                cursor = await db.execute(
                    f"""
                    SELECT {SELECT_COLS} FROM conversation_history
                    WHERE project_id = ? AND agent_id = ? AND session_id = ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (self.project_id, self.agent_id, session_filter, n),
                )
            else:
                cursor = await db.execute(
                    f"""
                    SELECT {SELECT_COLS} FROM conversation_history
                    WHERE project_id = ? AND agent_id = ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (self.project_id, self.agent_id, n),
                )
        else:
            cross_placeholders = ",".join("?" for _ in cross_ids)


            if session_filter:
                cursor = await db.execute(
                    f"""
                    SELECT {SELECT_COLS} FROM conversation_history
                    WHERE project_id = ? AND (
                        (agent_id = ? AND session_id = ?)
                        OR (agent_id IN ({cross_placeholders}) AND role IN ('user', 'assistant'))
                    )
                    ORDER BY id DESC LIMIT ?
                    """,
                    (self.project_id, self.agent_id, session_filter, *cross_ids, n),
                )
            else:
                cursor = await db.execute(
                    f"""
                    SELECT {SELECT_COLS} FROM conversation_history
                    WHERE project_id = ? AND (
                        agent_id = ?
                        OR (agent_id IN ({cross_placeholders}) AND role IN ('user', 'assistant'))
                    )
                    ORDER BY id DESC LIMIT ?
                    """,
                    (self.project_id, self.agent_id, *cross_ids, n),
                )

        rows = await cursor.fetchall()
        rows = list(reversed(rows))


        for i in range(len(rows) - 1, -1, -1):
            if rows[i][1] == "user":
                rows = rows[:i]
                break

        msgs: list[dict] = []
        for row in rows:

            role = row[1]
            content = row[2] or ""
            tc_json = row[3]
            tc_id = row[4]
            name = row[5]
            src = row[6]
            ts_str = _format_sqlite_ts(row[7])
            m = _parse_stored_content(
                role,
                content,
                tool_calls_json=tc_json,
                tool_call_id=tc_id,
                name=name,
            )
            if src and src != self.agent_id:
                base = m.get("content") or ""
                m["content"] = f"[来自 {src}]\n{base}"
            m = _attach_ts_prefix(m, ts_str)
            msgs.append(m)

        return _budget_and_repair(msgs, max_tokens)

    async def _load_layered_messages(
        self,
        max_tokens: int,
        platform_id: str,
    ) -> list[dict]:

        K = settings.memory.conv_load_consensus
        N = settings.memory.conv_load_per_platform
        db = await get_db()

        SELECT_COLS = (
            "id, role, content, tool_calls_json, tool_call_id, name, agent_id, created_at"
        )


        cursor = await db.execute(
            f"""
            SELECT {SELECT_COLS} FROM conversation_history
            WHERE project_id = ? AND agent_id = ?
              AND role IN ('user', 'assistant')
            ORDER BY id DESC LIMIT ?
            """,
            (self.project_id, self.agent_id, K),
        )
        consensus_rows = await cursor.fetchall()


        cursor = await db.execute(
            f"""
            SELECT {SELECT_COLS} FROM conversation_history
            WHERE project_id = ? AND agent_id = ? AND platform_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (self.project_id, self.agent_id, platform_id, N),
        )
        platform_rows = await cursor.fetchall()


        merged: dict[int, tuple] = {row[0]: row for row in consensus_rows}
        for row in platform_rows:
            merged[row[0]] = row
        rows = sorted(merged.values(), key=lambda r: r[0])


        for i in range(len(rows) - 1, -1, -1):
            if rows[i][1] == "user":
                rows = rows[:i]
                break

        msgs: list[dict] = []
        for row in rows:
            ts_str = _format_sqlite_ts(row[7])
            m = _parse_stored_content(
                row[1], row[2] or "",
                tool_calls_json=row[3], tool_call_id=row[4], name=row[5],
            )
            m = _attach_ts_prefix(m, ts_str)
            msgs.append(m)

        return _budget_and_repair(msgs, max_tokens)

    async def save_turn(
        self,
        role: str,
        content: str,
        *,
        tool_call_id: str | None = None,
        tool_calls: list[dict] | None = None,
        platform_id: str | None = None,
        session_id: str | None = None,
    ):



        tool_calls_json = (
            json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None
        )


        col_tool_call_id = tool_call_id if role == "tool" else None

        effective_platform = platform_id or self._runtime_platform_id
        effective_session = session_id or self._runtime_session_id

        db = await get_db()

        next_seq: int | None = None
        if effective_session:
            cursor = await db.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 FROM conversation_history "
                "WHERE session_id = ?",
                (effective_session,),
            )
            row = await cursor.fetchone()
            next_seq = int(row[0]) if row else 0

        await db.execute(
            "INSERT INTO conversation_history (project_id, agent_id, role, content, "
            "tool_calls_json, tool_call_id, name, seq, platform_id, session_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                self.project_id,
                self.agent_id,
                role,
                content,
                tool_calls_json,
                col_tool_call_id,
                None,
                next_seq,
                effective_platform,
                effective_session,
            ),
        )
        await db.commit()




        if effective_session:
            from cancer_claw.agent.recall.session_repo import touch_session_on_save

            await touch_session_on_save(
                project_id=self.project_id,
                session_id=effective_session,
                agent_id=self.agent_id,
                role=role,
                content=content or "",
                tool_calls_count=(len(tool_calls) if tool_calls else 0),
            )

    async def _load_recent_turns(self) -> list[dict]:

        n = settings.memory.conv_load_recent_turns
        db = await get_db()

        all_agent_ids = [self.agent_id] + [
            aid for aid in self.cross_agent_ids if aid != self.agent_id
        ]
        session_filter = self._runtime_session_id

        if len(all_agent_ids) == 1:
            if session_filter:
                cursor = await db.execute(
                    """
                    SELECT id, role, content, agent_id, created_at FROM conversation_history
                    WHERE project_id = ? AND agent_id = ? AND session_id = ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (self.project_id, self.agent_id, session_filter, n),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT id, role, content, agent_id, created_at FROM conversation_history
                    WHERE project_id = ? AND agent_id = ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (self.project_id, self.agent_id, n),
                )
        else:
            placeholders = ",".join("?" for _ in all_agent_ids)
            if session_filter:

                other_ids = [aid for aid in all_agent_ids if aid != self.agent_id]
                other_placeholders = ",".join("?" for _ in other_ids)
                cursor = await db.execute(
                    f"""
                    SELECT id, role, content, agent_id, created_at FROM conversation_history
                    WHERE project_id = ? AND (
                        (agent_id = ? AND session_id = ?)
                        OR agent_id IN ({other_placeholders})
                    )
                    ORDER BY id DESC LIMIT ?
                    """,
                    (self.project_id, self.agent_id, session_filter, *other_ids, n),
                )
            else:
                cursor = await db.execute(
                    f"""
                    SELECT id, role, content, agent_id, created_at FROM conversation_history
                    WHERE project_id = ? AND agent_id IN ({placeholders})
                    ORDER BY id DESC LIMIT ?
                    """,
                    (self.project_id, *all_agent_ids, n),
                )

        rows = await cursor.fetchall()

        return [
            {
                "role": r[1],
                "content": r[2],
                "source_agent": r[3],
                "ts": _format_sqlite_ts(r[4]),
            }
            for r in reversed(rows)
        ]

    def load_recent_onelines_only(self) -> list[str]:

        return self._load_recent_onelines()

    def _load_recent_onelines(self) -> list[str]:

        n = settings.memory.working_memory_onelines
        all_entries: list[tuple[str, str, str]] = []

        for digest_dir in [self._project_digest_dir, self._agent_digest_dir]:
            if not digest_dir.exists():
                continue

            md_files = sorted(digest_dir.glob("????-??-??.md"), reverse=True)
            for md_file in md_files:
                date_str = md_file.stem
                try:
                    content = md_file.read_text(encoding="utf-8")
                except Exception:
                    continue

                for m in _RE_INDEX_LINE.finditer(content):
                    time_str = m.group(1)
                    oneline = m.group(2).strip()
                    all_entries.append((date_str, time_str, oneline))


                if len(all_entries) >= n * 2:
                    break


        all_entries.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [
            f"{date} {time} | {oneline}"
            for date, time, oneline in all_entries[:n]
        ]
