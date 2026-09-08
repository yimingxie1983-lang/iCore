"""交互 REPL：当前目录即工作区，斜杠命令对齐 Codex。"""

from __future__ import annotations

import asyncio
import contextlib

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cancer_claw.client.host import LocalHost
from cancer_claw.client.render import EventRenderer
from cancer_claw.config import settings

_HELP = """\
[bold]/help[/bold]              显示本帮助
[bold]/new[/bold]               开启新会话
[bold]/resume [id][/bold]       恢复最近或指定会话
[bold]/sessions[/bold]          列出本目录最近会话
[bold]/status[/bold]            当前工作区与会话
[bold]/quit[/bold]  [bold]/exit[/bold]     退出
提交一行后开始推理；Ctrl+C 中断本轮。
"""


class ClientRepl:
    def __init__(self, *, host: LocalHost, console: Console) -> None:
        self.host = host
        self.console = console
        self.renderer = EventRenderer(console)

    def banner(self) -> None:
        root = self.host.root or ""
        self.console.print(
            Panel(
                f"[bold]iCore[/bold]  {settings.app.version}  ·  {root}\n"
                "[dim]当前目录就是工作区。输入任务开始，/help 查看命令。[/dim]",
                border_style="cyan",
                title="client",
            )
        )

    async def _print_sessions(self) -> None:
        rows = await self.host.list_sessions(limit=8)
        if not rows:
            self.console.print("[dim]还没有会话。[/dim]")
            return
        table = Table(show_header=True, header_style="bold")
        table.add_column("session")
        table.add_column("title")
        table.add_column("updated")
        for row in rows:
            sid = str(row.get("session_id") or "")
            mark = "● " if sid == self.host.session_id else "  "
            table.add_row(
                mark + sid,
                str(row.get("title") or ""),
                str(row.get("updated_at") or ""),
            )
        self.console.print(table)

    async def _handle_slash(self, raw: str) -> str:
        """返回 'quit' / 'ok'。"""
        parts = raw.strip().split()
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        if cmd in ("/quit", "/exit", "/q"):
            return "quit"
        if cmd == "/help":
            self.console.print(_HELP)
            return "ok"
        if cmd == "/new":
            self.host.new_session()
            self.console.print("[dim]已开启新会话。[/dim]")
            return "ok"
        if cmd == "/sessions":
            await self._print_sessions()
            return "ok"
        if cmd == "/status":
            self.console.print(
                f"cwd={self.host.root}\nproject={self.host.project_id}\n"
                f"session={self.host.session_id or '(new)'}\n"
                f"agent={getattr(self.host.agent, 'id', '')}"
            )
            return "ok"
        if cmd == "/resume":
            try:
                sid = await self.host.resume(arg or "LAST")
            except FileNotFoundError as e:
                self.console.print(f"[yellow]{e}[/yellow]")
                return "ok"
            self.console.print(f"[dim]恢复会话 {sid}[/dim]")
            return "ok"
        self.console.print(f"[yellow]未知命令 {cmd}，输入 /help。[/yellow]")
        return "ok"

    async def run_message(self, message: str) -> None:
        try:
            async for ev in self.host.run_message(message):
                self.renderer.render(ev)
        except asyncio.CancelledError:
            self.console.print("\n[yellow]已中断。[/yellow]")
            raise

    async def loop(self, first_prompt: str | None = None) -> int:
        self.banner()
        if first_prompt:
            try:
                await self.run_message(first_prompt)
            except asyncio.CancelledError:
                pass

        while True:
            try:
                line = await asyncio.to_thread(input, "\nicore › ")
            except EOFError:
                self.console.print()
                return 0
            except KeyboardInterrupt:
                self.console.print()
                return 0

            text = (line or "").strip()
            if not text:
                continue
            if text.startswith("/"):
                if await self._handle_slash(text) == "quit":
                    return 0
                continue
            task = asyncio.create_task(self.run_message(text))
            try:
                await task
            except (asyncio.CancelledError, KeyboardInterrupt):
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task
                self.console.print("\n[yellow]已中断。[/yellow]")
        return 0
