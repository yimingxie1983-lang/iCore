

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

SESSIONS_DIR_NAME = ".sessions"

def get_sessions_dir(workspace_root: Path) -> Path:

    d = workspace_root / SESSIONS_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d

def _make_session_id(agent_id: str) -> str:

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    short = (agent_id or "agent").split("_")[-1][:16] or "agent"
    return f"{ts}_{short}"

def dump_session(
    workspace_root: Path,
    agent_id: str,
    messages: list[dict[str, Any]],
    *,
    started_at: float | None = None,
    summary: str = "",
    session_id: str | None = None,
) -> tuple[str, Path] | None:

    if not messages:
        return None
    try:
        sdir = get_sessions_dir(workspace_root)
        if not session_id:
            session_id = _make_session_id(agent_id)
        jsonl_path = sdir / f"{session_id}.jsonl"
        meta_path = sdir / f"{session_id}.meta.json"


        with jsonl_path.open("w", encoding="utf-8", newline="\n") as fh:
            for msg in messages:
                fh.write(json.dumps(msg, ensure_ascii=False) + "\n")


        tool_calls = sum(
            len(m.get("tool_calls") or [])
            for m in messages
            if m.get("role") == "assistant"
        )
        started_iso = (
            datetime.fromtimestamp(started_at, tz=timezone.utc).astimezone().isoformat(
                timespec="seconds"
            )
            if started_at
            else ""
        )
        ended_iso = (
            datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds")
        )
        meta = {
            "session_id": session_id,
            "agent_id": agent_id,
            "started_at": started_iso,
            "ended_at": ended_iso,
            "message_count": len(messages),
            "tool_calls": tool_calls,
            "summary": (summary or "").strip()[:400],
            "jsonl_path": str(jsonl_path),
        }
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        logger.info(
            "session_dumped",
            session_id=session_id,
            messages=len(messages),
            tool_calls=tool_calls,
            path=str(jsonl_path),
        )
        return session_id, jsonl_path
    except Exception as e:
        logger.warning("session_dump_failed", agent_id=agent_id, error=str(e), exc_info=True)
        return None

def list_sessions(
    workspace_root: Path,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:

    sdir = workspace_root / SESSIONS_DIR_NAME
    if not sdir.exists():
        return []

    metas: list[dict[str, Any]] = []
    for meta_path in sdir.glob("*.meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta.setdefault("_mtime", meta_path.stat().st_mtime)
            metas.append(meta)
        except Exception as e:
            logger.debug("session_meta_unreadable", path=str(meta_path), error=str(e))


    for jsonl_path in sdir.glob("*.jsonl"):
        sid = jsonl_path.stem
        if any(m.get("session_id") == sid for m in metas):
            continue
        metas.append({
            "session_id": sid,
            "jsonl_path": str(jsonl_path),
            "_mtime": jsonl_path.stat().st_mtime,
        })

    metas.sort(key=lambda m: m.get("_mtime", 0), reverse=True)
    return metas[:limit]

def read_session(
    workspace_root: Path,
    session_id: str,
    *,
    offset: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]] | None:

    sdir = workspace_root / SESSIONS_DIR_NAME
    jsonl_path = sdir / f"{session_id}.jsonl"
    if not jsonl_path.exists():
        return None
    msgs: list[dict[str, Any]] = []
    try:
        with jsonl_path.open("r", encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i < offset:
                    continue
                if len(msgs) >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msgs.append(json.loads(line))
                except json.JSONDecodeError:
                    msgs.append({"role": "raw", "content": line})
    except OSError as e:
        logger.warning("session_read_failed", session_id=session_id, error=str(e))
        return None
    return msgs

def grep_sessions(
    workspace_root: Path,
    pattern: str,
    *,
    session_id: str | None = None,
    max_matches: int = 50,
    flags: int = re.IGNORECASE,
) -> list[dict[str, Any]]:

    try:
        rx = re.compile(pattern, flags)
    except re.error as e:
        logger.warning("session_grep_bad_pattern", pattern=pattern, error=str(e))
        return []

    sdir = workspace_root / SESSIONS_DIR_NAME
    if not sdir.exists():
        return []

    if session_id:
        files = [sdir / f"{session_id}.jsonl"]
    else:
        files = sorted(sdir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)

    matches: list[dict[str, Any]] = []
    for jsonl_path in files:
        if not jsonl_path.exists():
            continue
        sid = jsonl_path.stem
        try:
            with jsonl_path.open("r", encoding="utf-8", errors="replace") as fh:
                for line_no, line in enumerate(fh, start=1):
                    if len(matches) >= max_matches:
                        return matches
                    if not rx.search(line):
                        continue
                    try:
                        msg = json.loads(line)
                        role = msg.get("role", "?")

                        m = rx.search(line)
                        start = max(0, (m.start() if m else 0) - 60)
                        end = min(len(line), (m.end() if m else 0) + 60)
                        snippet = line[start:end].strip()
                    except Exception:
                        role = "?"
                        snippet = line[:200].strip()
                    matches.append({
                        "session_id": sid,
                        "line_no": line_no,
                        "role": role,
                        "snippet": snippet,
                    })
        except OSError as e:
            logger.debug("session_grep_io_error", path=str(jsonl_path), error=str(e))
            continue
    return matches
