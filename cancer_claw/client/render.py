"""把 agent 事件画到终端，风格靠近 Codex exec。"""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text


def _truncate(text: str, limit: int = 240) -> str:
    text = (text or "").replace("\r\n", "\n").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _args_preview(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, (dict, list)):
        try:
            return _truncate(json.dumps(raw, ensure_ascii=False))
        except TypeError:
            return _truncate(str(raw))
    text = str(raw).strip()
    if text.startswith("{") or text.startswith("["):
        try:
            return _truncate(json.dumps(json.loads(text), ensure_ascii=False))
        except (json.JSONDecodeError, TypeError):
            pass
    return _truncate(text)


class EventRenderer:
    def __init__(self, console: Console) -> None:
        self.console = console
        self._last_kind: str | None = None

    def render(self, event: dict[str, Any]) -> None:
        kind = str(event.get("type") or "")
        if not kind or kind.startswith("_"):
            return
        handler = getattr(self, f"_on_{kind}", None)
        if handler is None:
            self._on_generic(kind, event)
            return
        handler(event)
        self._last_kind = kind

    def _on_session_started(self, event: dict[str, Any]) -> None:
        sid = event.get("session_id") or ""
        title = event.get("title") or ""
        line = f"session {sid}"
        if title:
            line += f"  ·  {title}"
        self.console.print(f"[dim]{line}[/dim]")

    def _on_thinking(self, event: dict[str, Any]) -> None:
        content = (event.get("content") or "").strip()
        if not content:
            return
        self.console.print(f"[dim italic]{ _truncate(content, 160) }[/dim italic]")

    def _on_assistant_pretext(self, event: dict[str, Any]) -> None:
        content = (event.get("content") or "").strip()
        if content:
            self.console.print(content)

    def _on_tool_call(self, event: dict[str, Any]) -> None:
        name = event.get("tool") or event.get("name") or "tool"
        preview = _args_preview(event.get("arguments"))
        suffix = f"  [dim]{preview}[/dim]" if preview else ""
        self.console.print(f"[cyan]▶ {name}[/cyan]{suffix}")

    def _on_tool_result(self, event: dict[str, Any]) -> None:
        ok = event.get("success")
        if ok is None:
            ok = not event.get("error")
        mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
        output = event.get("output") or event.get("content") or event.get("error") or ""
        self.console.print(f"{mark} {_truncate(str(output), 200)}")

    def _on_message(self, event: dict[str, Any]) -> None:
        content = (event.get("content") or "").strip()
        if not content:
            return
        if "\n" in content or content.startswith("#") or "```" in content:
            self.console.print(Markdown(content))
        else:
            self.console.print(content)

    def _on_usage(self, event: dict[str, Any]) -> None:
        inp = event.get("input_tokens") or event.get("prompt_tokens")
        out = event.get("output_tokens") or event.get("completion_tokens")
        bits = []
        if inp is not None:
            bits.append(f"in={inp}")
        if out is not None:
            bits.append(f"out={out}")
        if bits:
            self.console.print(f"[dim]tokens {' '.join(bits)}[/dim]")

    def _on_error(self, event: dict[str, Any]) -> None:
        msg = event.get("error") or event.get("message") or "未知错误"
        self.console.print(Panel(Text(str(msg), style="red"), title="error", border_style="red"))

    def _on_notice(self, event: dict[str, Any]) -> None:
        msg = event.get("message") or event.get("content") or ""
        if msg:
            self.console.print(f"[yellow]{msg}[/yellow]")

    def _on_done(self, event: dict[str, Any]) -> None:
        stats = event.get("stats") or {}
        if not isinstance(stats, dict):
            return
        model = stats.get("model_calls")
        tools = stats.get("tool_calls")
        tokens = stats.get("total_tokens")
        parts = []
        if model is not None:
            parts.append(f"模型 {model}")
        if tools is not None:
            parts.append(f"工具 {tools}")
        if tokens is not None:
            parts.append(f"tokens {tokens}")
        if parts:
            self.console.print(f"[dim]完成 · {' · '.join(parts)}[/dim]")

    def _on_process_output(self, event: dict[str, Any]) -> None:
        output = (event.get("output") or "").strip()
        if output:
            self.console.print(f"[dim]{ _truncate(output, 300) }[/dim]")

    def _on_persona_switched(self, event: dict[str, Any]) -> None:
        name = event.get("persona") or event.get("persona_id") or ""
        self.console.print(f"[magenta]persona → {name}[/magenta]")

    def _on_generic(self, kind: str, event: dict[str, Any]) -> None:
        if kind in {
            "squad_started", "squad_concluded", "squad_task_started", "squad_task_done",
            "council_convened", "council_concluded", "council_verdict",
            "council_role_started", "council_role_stance",
            "evidence_warning",
        }:
            label = kind.replace("_", " ")
            extra = event.get("message") or event.get("content") or event.get("verdict") or ""
            line = f"[blue]{label}[/blue]"
            if extra:
                line += f"  [dim]{_truncate(str(extra), 120)}[/dim]"
            self.console.print(line)
