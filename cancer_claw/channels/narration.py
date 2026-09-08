"""精简 episode 叙述（服务端，供微信进度推送）。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EpisodeAccumulator:
    """从 chat_stream 事件收成短进度句。"""

    episodes: list[str] = field(default_factory=list)
    _pending_think: str = ""
    _tools: list[dict[str, Any]] = field(default_factory=list)
    _emitted: int = 0

    def feed(self, event: dict[str, Any]) -> str | None:
        et = str(event.get("type") or "")
        if et in {"thinking", "reasoning"}:
            content = str(event.get("content") or event.get("text") or "").strip()
            if content:
                self._pending_think = content[-200:]
            return None

        if et == "notice":
            text = str(event.get("content") or event.get("text") or "").strip()
            if len(text) >= 4:
                self._flush()
                line = f"进度：{ _truncate(text, 80) }"
                return self._emit(line)
            return None

        if et == "tool_call":
            name = str(event.get("tool") or event.get("name") or "tool")
            args = event.get("arguments") or event.get("args") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            if not isinstance(args, dict):
                args = {}
            self._tools.append({"tool": name, "args": args, "ok": None})
            return None

        if et == "tool_result":
            name = str(event.get("tool") or event.get("name") or "")
            ok = event.get("success")
            if ok is None:
                ok = not bool(event.get("error"))
            for t in reversed(self._tools):
                if t.get("ok") is None and (not name or t["tool"] == name):
                    t["ok"] = bool(ok)
                    break
            # 攒到一定数量再吐一句，避免逐步刷屏
            if len(self._tools) >= 3:
                return self._flush()
            return None

        if et in {"message", "done", "error"}:
            return self._flush()

        return None

    def flush_remaining(self) -> str | None:
        return self._flush()

    def _flush(self) -> str | None:
        if not self._tools and not self._pending_think:
            return None
        why = _why_from_think(self._pending_think)
        what = _summarize_tools(self._tools)
        self._tools = []
        self._pending_think = ""
        if not what:
            return None
        if why:
            line = f"正在{what}，以便{why}"
        else:
            line = f"正在{what}"
        return self._emit(line)

    def _emit(self, line: str) -> str:
        self._emitted += 1
        self.episodes.append(line)
        return line


def _why_from_think(text: str) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    if len(t) < 8:
        return ""
    # 取首句碎片
    for sep in ("。", "；", ";", "\n"):
        if sep in t:
            t = t.split(sep, 1)[0]
            break
    return _truncate(t, 36)


def _summarize_tools(tools: list[dict[str, Any]]) -> str:
    if not tools:
        return ""
    names = [str(t.get("tool") or "") for t in tools]
    # present_file 优先
    presents = [t for t in tools if t.get("tool") == "present_file"]
    if presents:
        paths = []
        for t in presents:
            args = t.get("args") or {}
            p = args.get("path") or args.get("paths") or args.get("file")
            if isinstance(p, list) and p:
                paths.append(_basename(str(p[0])))
            elif p:
                paths.append(_basename(str(p)))
        if paths:
            return f"整理结果文件（{', '.join(paths[:2])}）"
        return "整理结果文件"

    reads = [t for t in tools if t.get("tool") in {"read_file", "list_dir", "search_files", "grep"}]
    writes = [t for t in tools if t.get("tool") in {"write_file", "edit_file", "apply_patch"}]
    cmds = [t for t in tools if t.get("tool") in {"run_command", "bash", "shell"}]
    web = [t for t in tools if "web" in str(t.get("tool") or "") or t.get("tool") == "http_request"]

    parts: list[str] = []
    if reads:
        target = _tool_target(reads[0])
        parts.append(f"查阅{target}" if target else "查阅项目文件")
    if writes:
        target = _tool_target(writes[0])
        parts.append(f"修改{target}" if target else "修改项目文件")
    if cmds:
        parts.append("运行命令检查结果")
    if web:
        parts.append("检索外部资料")
    if not parts:
        # fallback
        uniq = []
        for n in names:
            if n and n not in uniq:
                uniq.append(n)
        if not uniq:
            return ""
        return f"执行 {', '.join(uniq[:3])}"
    return "、".join(parts[:2])


def _tool_target(tool: dict[str, Any]) -> str:
    args = tool.get("args") or {}
    for key in ("path", "file", "pattern", "query", "command", "url"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            if key in {"path", "file"}:
                return _basename(val)
            return _truncate(val, 24)
    return ""


def _basename(path: str) -> str:
    p = path.replace("\\", "/").strip()
    parts = [x for x in p.split("/") if x]
    return parts[-1] if parts else p


def _truncate(s: str, max_len: int) -> str:
    t = re.sub(r"\s+", " ", s or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"
