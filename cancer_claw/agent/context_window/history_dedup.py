

from __future__ import annotations

import json
import re
from typing import Any

def compact_duplicate_tool_results(messages: list[dict[str, Any]]) -> None:

    return

def _parse_tool_args(raw: str) -> dict[str, Any]:
    if not raw or not isinstance(raw, str):
        return {}
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}

def _norm_cmd_fingerprint(command: str) -> str:
    if not command:
        return ""
    s = command.strip()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("\\\\", "/").replace("\\", "/")
    return s.lower()

def _dedup_key(tool_name: str, args: dict[str, Any]) -> tuple[Any, ...] | None:

    if tool_name == "file_ops":
        if args.get("action") != "read_file":
            return None
        p = (args.get("path") or "").strip().lower().replace("\\", "/")
        if not p:
            return None
        return ("file_ops", "read_file", p)

    if tool_name == "shell_exec":
        act = args.get("action") or ""
        if act not in ("run_command", "run_background"):
            return None
        cmd = args.get("command") or ""
        fp = _norm_cmd_fingerprint(str(cmd))
        if not fp:
            return None
        return ("shell_exec", act, fp)

    if tool_name == "http_fetch":
        act = (args.get("action") or "get").strip().lower()
        url = (args.get("url") or "").strip().lower()
        if not url:
            return None
        return ("http_fetch", act, url)

    if tool_name == "db_ops":
        if args.get("action") != "query_sql":
            return None
        sql = (args.get("sql") or "").strip().lower()[:800]
        if not sql:
            return None
        return ("db_ops", "query_sql", sql)

    return None

def _legacy_compact_duplicate_tool_results(messages: list[dict[str, Any]]) -> None:

    if not messages:
        return

    current_map: dict[str, tuple[str, dict[str, Any]]] = {}
    tool_entries: list[tuple[int, tuple[Any, ...] | None, str]] = []

    for i, msg in enumerate(messages):
        role = msg.get("role")
        if role == "assistant" and msg.get("tool_calls"):
            current_map = {}
            for tc in msg.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                tid = tc.get("id")
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                args = _parse_tool_args(fn.get("arguments") or "")
                if tid:
                    current_map[str(tid)] = (name, args)
        elif role == "tool":
            tid = str(msg.get("tool_call_id") or "")
            pair = current_map.get(tid)
            if not pair:
                continue
            tname, args = pair
            key = _dedup_key(tname, args)
            content = msg.get("content")
            if not isinstance(content, str):
                content = str(content) if content is not None else ""
            tool_entries.append((i, key, content))

    by_key: dict[tuple[Any, ...], list[int]] = {}
    for i, key, _c in tool_entries:
        if key is None:
            continue
        by_key.setdefault(key, []).append(i)

    for key, indices in by_key.items():
        if len(indices) < 2:
            continue
        keep = max(indices)
        tname = str(key[0]) if key else "?"
        for idx in indices:
            if idx == keep:
                continue
            msg = messages[idx]
            if msg.get("role") != "tool":
                continue
            c = msg.get("content")
            if isinstance(c, str) and c.startswith("[上下文去重]"):
                continue
            msg["content"] = (
                "[上下文去重] 与后文同 key 的工具结果已省略以节省 token。"
                f"（tool={tname}）若仍需此版本输出，请用相同参数重新调用该工具。"
            )
