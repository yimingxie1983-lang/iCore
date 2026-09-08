"""渠道侧跑一轮 iCore Agent（进程内，仿 CLI LocalHost）。"""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, AsyncGenerator

from cancer_claw.agent.engine.agent_factory import get_or_create_agent
from cancer_claw.agent.engine.system_agents import MASTER_AGENT_ID
from cancer_claw.channels.narration import EpisodeAccumulator
from cancer_claw.client.session import run_turn
from cancer_claw.db import get_db
from cancer_claw.services.privacy.desensitizer import desensitize_text

_PRESENT_RE = re.compile(
    r"<!--CC:PRESENTATION:v1-->(.*?)<!--/CC:PRESENTATION-->",
    re.DOTALL,
)


async def load_user(user_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cur = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = await cur.fetchone()
    if row is None:
        return None
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    cols = [d[0] for d in cur.description]
    return {cols[i]: row[i] for i in range(len(cols))}


async def load_project(project_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cur = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = await cur.fetchone()
    if row is None:
        return None
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    cols = [d[0] for d in cur.description]
    return {cols[i]: row[i] for i in range(len(cols))}


async def ensure_agent_for_project(project: dict[str, Any], user: dict[str, Any]):
    project_id = str(project["id"])
    root = Path(str(project.get("workspace_path") or "")).expanduser()
    if not root.is_dir():
        # 回退到框架 projects_dir
        from cancer_claw.config import settings

        root = Path(settings.paths.projects_dir) / project_id
        root.mkdir(parents=True, exist_ok=True)
    agent = await get_or_create_agent(MASTER_AGENT_ID, project_id=None)
    await agent.bind_local_workspace(project_id, root)
    agent._current_user = dict(user)
    return agent, root


def stage_attachments(root: Path, attachments: list[Any]) -> list[Path]:
    uploads = root / "workspace" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []
    for att in attachments or []:
        src = Path(getattr(att, "path", att))
        if not src.is_file():
            continue
        name = getattr(att, "file_name", None) or src.name
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in str(name))[:120]
        dest = uploads / f"{int(time.time())}_{safe}"
        shutil.copy2(src, dest)
        staged.append(dest)
    return staged


def build_message_with_attachments(text: str, staged: list[Path]) -> str:
    parts: list[str] = []
    if text.strip():
        parts.append(text.strip())
    if staged:
        lines = ["[微信附件已保存到工作区]"]
        for p in staged:
            lines.append(f"- {p.as_posix()}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts).strip()


def desensitize_inbound(message: str, *, project_id: str | None = None) -> str:
    from cancer_claw.config import settings

    if not settings.privacy.enabled or not settings.privacy.desensitize_on_chat_input:
        return message
    ctx = {"source": "wechat", "project_id": project_id or ""}
    return desensitize_text(message, context=ctx).text


def extract_presentations(tool_output: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in _PRESENT_RE.finditer(tool_output or ""):
        try:
            payload = json.loads(m.group(1))
        except Exception:
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out


def presentation_local_paths(presentation: dict[str, Any], root: Path) -> list[Path]:
    files = presentation.get("files") or []
    paths: list[Path] = []
    for f in files:
        if not isinstance(f, dict):
            continue
        rel = str(f.get("path") or f.get("relative_path") or "").strip()
        if not rel:
            continue
        p = Path(rel)
        if not p.is_absolute():
            p = root / rel
        if p.is_file():
            paths.append(p)
    return paths


async def iter_channel_turn(
    *,
    user: dict[str, Any],
    project: dict[str, Any],
    message: str,
    session_id: str | None,
    force_new: bool,
    attachments: list[Any] | None = None,
    verbose: bool = False,
) -> AsyncGenerator[dict[str, Any], None]:
    agent, root = await ensure_agent_for_project(project, user)
    staged = stage_attachments(root, attachments or [])
    raw_message = build_message_with_attachments(message, staged)
    safe_message = desensitize_inbound(raw_message, project_id=str(project.get("id") or ""))
    if not safe_message:
        yield {"type": "error", "content": "空消息"}
        return

    # 提示工作区运行时平台
    try:
        if hasattr(agent, "working_memory") and agent.working_memory:
            agent.working_memory.set_runtime_hint(platform_id="wechat")
    except Exception:
        pass

    async for ev in run_turn(
        agent,
        safe_message,
        session_id=session_id,
        force_new=force_new,
        verbose=verbose,
        current_user=user,
    ):
        yield ev
