

from __future__ import annotations

import json

import structlog

from cancer_claw.db import get_db
from cancer_claw.agent.recall.session_repo import list_sessions
from cancer_claw.agent.recall.working import _parse_stored_content
from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult
from cancer_claw.capabilities.toolkit.workspace import get_tool_workspace

logger = structlog.get_logger()

class SessionHistoryTool(BaseTool):


    @property
    def name(self) -> str:
        return "session_history"

    @property
    def description(self) -> str:
        return (
            "查询历史会话（任务结束自动入库 conversation_history 表）。"
            "三个 action：list 看最近 N 个 session 的摘要；"
            "grep 按关键词跨 session（或指定 session）搜内容；"
            "read 读取某 session 的指定区间消息。"
            "适用于'上次跑过这个命令吗 / 上次报过这个错吗 / 我们讨论过这个方案吗'类需求。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "session_history",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["list", "grep", "read"],
                            "description": "list=列最近会话；grep=按关键词搜；read=读消息区间",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "list/read 时的条数上限；list 默认 10，read 默认 50",
                        },
                        "pattern": {
                            "type": "string",
                            "description": "grep 时的关键词（大小写不敏感的 LIKE %...% 匹配）",
                        },
                        "session_id": {
                            "type": "string",
                            "description": "read 必填；grep 可选（不填=跨当前项目所有 session）",
                        },
                        "offset": {
                            "type": "integer",
                            "description": "read 时的起始消息序号（0-indexed），默认 0",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    async def execute(self, **kwargs) -> ToolResult:
        action = (kwargs.get("action") or "").strip().lower()

        ws = get_tool_workspace()
        if ws is None:
            return ToolResult(
                success=False,
                error="未绑定项目工作区，session_history 仅在项目对话中可用。",
            )

        try:
            project_id = ws.project_root.name
        except Exception as e:
            return ToolResult(
                success=False, error=f"无法解析项目 ID：{e}",
            )

        try:
            if action == "list":
                return await self._list(project_id, limit=int(kwargs.get("limit") or 10))
            if action == "grep":
                pattern = (kwargs.get("pattern") or "").strip()
                if not pattern:
                    return ToolResult(success=False, error="grep 需传入 pattern")
                return await self._grep(
                    project_id,
                    pattern=pattern,
                    session_id=(kwargs.get("session_id") or "").strip() or None,
                    max_matches=int(kwargs.get("limit") or 50),
                )
            if action == "read":
                session_id = (kwargs.get("session_id") or "").strip()
                if not session_id:
                    return ToolResult(success=False, error="read 必须传入 session_id")
                return await self._read(
                    project_id,
                    session_id=session_id,
                    offset=int(kwargs.get("offset") or 0),
                    limit=int(kwargs.get("limit") or 50),
                )
            return ToolResult(success=False, error=f"不支持的 action: {action!r}")
        except Exception as e:
            logger.warning("session_history_failed", action=action, error=str(e), exc_info=True)
            return ToolResult(success=False, error=f"session_history.{action} 失败: {e}")



    async def _list(self, project_id: str, *, limit: int) -> ToolResult:
        items = await list_sessions(project_id, limit=limit, offset=0)
        if not items:
            return ToolResult(
                success=True,
                output="尚无历史会话。",
                data={"count": 0, "sessions": []},
            )
        lines = [f"最近 {len(items)} 个会话："]
        rows = []
        for m in items:
            sid = m.get("session_id", "?")
            title = (m.get("title") or "").strip()
            preview = (m.get("preview") or "").replace("\n", " ").strip()[:80]
            updated = m.get("updated_at", "")
            mc = m.get("message_count", "?")
            tc = m.get("tool_calls", "?")
            lines.append(
                f"  - {sid} | {title or '(未命名)'}\n"
                f"      消息 {mc} | 工具调用 {tc} | 最近活动 {updated}\n"
                f"      预览: {preview or '(无)'}"
            )
            rows.append({
                "session_id": sid,
                "title": title,
                "message_count": mc,
                "tool_calls": tc,
                "updated_at": updated,
                "preview": preview,
            })
        lines.append(
            "\n下一步可用：grep pattern=... session_id=... | read session_id=... offset=0 limit=50"
        )
        return ToolResult(
            success=True,
            output="\n".join(lines),
            data={"count": len(items), "sessions": rows},
        )

    async def _grep(
        self,
        project_id: str,
        *,
        pattern: str,
        session_id: str | None,
        max_matches: int,
    ) -> ToolResult:
        db = await get_db()
        if session_id:
            sql = (
                "SELECT id, session_id, role, content, seq, created_at "
                "FROM conversation_history "
                "WHERE project_id = ? AND session_id = ? "
                "  AND content LIKE ? COLLATE NOCASE "
                "ORDER BY id DESC LIMIT ?"
            )
            params: tuple = (project_id, session_id, f"%{pattern}%", max_matches)
        else:
            sql = (
                "SELECT id, session_id, role, content, seq, created_at "
                "FROM conversation_history "
                "WHERE project_id = ? AND session_id IS NOT NULL "
                "  AND content LIKE ? COLLATE NOCASE "
                "ORDER BY id DESC LIMIT ?"
            )
            params = (project_id, f"%{pattern}%", max_matches)
        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()

        if not rows:
            scope = f"session={session_id}" if session_id else "全部 session"
            return ToolResult(
                success=True,
                output=f"在 {scope} 中没有命中 /{pattern}/。",
                data={"count": 0, "matches": []},
            )
        lines = [
            f"命中 {len(rows)} 条 /{pattern}/" + (f"（仅 session={session_id}）" if session_id else "（跨所有 session）") + ":"
        ]
        matches = []
        for r in rows[:50]:
            sid = r[1]
            role = r[2]
            content = (r[3] or "").replace("\n", " ")
            seq = r[4]
            ts = r[5]
            snippet = content[:160]
            if len(content) > 160:
                snippet += "..."
            lines.append(
                f"  [{sid}:seq={seq}, {ts}] role={role}\n      {snippet}"
            )
            matches.append({
                "session_id": sid,
                "seq": seq,
                "role": role,
                "ts": ts,
                "snippet": snippet,
            })
        if len(rows) > 50:
            lines.append(f"\n（共 {len(rows)} 命中，仅展示前 50；如需更多请缩小 pattern）")
        return ToolResult(
            success=True,
            output="\n".join(lines),
            data={"count": len(rows), "matches": matches},
        )

    async def _read(
        self,
        project_id: str,
        *,
        session_id: str,
        offset: int,
        limit: int,
    ) -> ToolResult:
        db = await get_db()

        cursor = await db.execute(
            "SELECT COUNT(*) FROM conversation_history "
            "WHERE project_id = ? AND session_id = ?",
            (project_id, session_id),
        )
        row = await cursor.fetchone()
        total = int(row[0]) if row else 0
        if total == 0:
            return ToolResult(
                success=False,
                error=f"session 不存在或不属于当前项目: {session_id}（先 list 看可用 session）",
            )

        cursor = await db.execute(
            """
            SELECT id, role, content, tool_calls_json, tool_call_id, name,
                   created_at, seq
            FROM conversation_history
            WHERE project_id = ? AND session_id = ?
            ORDER BY seq IS NULL, seq ASC, created_at ASC, id ASC
            LIMIT ? OFFSET ?
            """,
            (project_id, session_id, limit, offset),
        )
        db_rows = await cursor.fetchall()
        if not db_rows:
            return ToolResult(
                success=True,
                output=f"session={session_id} offset={offset} limit={limit} 区间为空（总数 {total}）。",
                data={"count": 0, "messages": [], "total": total},
            )

        msgs: list[dict] = []
        lines = [
            f"session={session_id} 起 offset={offset}（本批 {len(db_rows)} 条，总 {total}）："
        ]
        for i, r in enumerate(db_rows):
            m = _parse_stored_content(
                r[1], r[2] or "",
                tool_calls_json=r[3], tool_call_id=r[4], name=r[5],
            )
            m["created_at"] = r[6]
            m["seq"] = r[7]
            msgs.append(m)

            role = m.get("role", "?")
            tcs = m.get("tool_calls") or []
            if tcs:
                tnames = ",".join(t.get("function", {}).get("name", "?") for t in tcs)
                lines.append(f"  [#{offset + i}] {role} → tool_calls=[{tnames}]")
                for tc in tcs[:3]:
                    args = (tc.get("function", {}).get("arguments") or "")
                    if len(args) > 200:
                        args = args[:200] + "..."
                    lines.append(f"      args: {args}")
            else:
                content = (m.get("content") or "")
                if isinstance(content, list):
                    content = " ".join(str(p) for p in content)
                content = str(content).replace("\n", " ").strip()
                if len(content) > 400:
                    content = content[:400] + "..."
                lines.append(f"  [#{offset + i}] {role}: {content}")
        return ToolResult(
            success=True,
            output="\n".join(lines),
            data={"count": len(msgs), "messages": msgs, "offset": offset, "total": total},
        )
