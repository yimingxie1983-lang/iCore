"""本地客户端编排：启动运行时、绑定 cwd、跑 exec 或 REPL。"""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console

from cancer_claw.client.host import LocalHost
from cancer_claw.client.render import EventRenderer
from cancer_claw.client.repl import ClientRepl


async def run_client(args) -> int:
    verbose = bool(getattr(args, "verbose", False))
    workdir = getattr(args, "workdir", None) or Path.cwd()
    host = LocalHost(verbose=verbose)
    console = Console(file=sys.__stdout__)
    await host.start(workdir)
    try:
        session_id = getattr(args, "resume", None)
        if session_id:
            try:
                await host.resume(session_id)
            except FileNotFoundError as e:
                console.print(f"[red]{e}[/red]")
                return 1

        prompt = getattr(args, "prompt", None)
        if prompt == "-":
            prompt = sys.stdin.read()

        if args.command == "exec":
            if not (prompt or "").strip():
                console.print("[red]exec 需要一条提示词。[/red]")
                return 2
            renderer = EventRenderer(console)
            async for ev in host.run_message(prompt):
                renderer.render(ev)
            return 0

        repl = ClientRepl(host=host, console=console)
        return await repl.loop(first_prompt=prompt)
    finally:
        await host.shutdown()
