"""iCore 本地客户端入口，命令面靠近 Codex CLI。

用法：
    icore                     在当前目录打开交互会话
    icore "查一下文献缺口"      带首条消息进入交互
    icore exec "总结这个目录"   非交互跑完一轮后退出
    icore resume              恢复本目录最近一次会话
    icore resume <session>    恢复指定会话
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from cancer_claw import __version__

_COMMANDS = {"exec", "resume", "wechat"}
_VALUE_FLAGS = {"-C", "--cd", "--resume"}


def _extract_command(raw: list[str]) -> tuple[str, list[str]]:
    for i, tok in enumerate(raw):
        if tok not in _COMMANDS:
            continue
        if i > 0 and raw[i - 1] in _VALUE_FLAGS:
            continue
        return tok, raw[:i] + raw[i + 1 :]
    return "chat", raw


def parse_argv(argv: list[str] | None = None) -> argparse.Namespace:
    raw = list(sys.argv[1:] if argv is None else argv)
    command, raw = _extract_command(raw)

    if command == "wechat":
        # 交给微信子 CLI；保留原始剩余参数
        ns = argparse.Namespace(command="wechat", wechat_argv=raw)
        return ns

    prog = "icore" if command == "chat" else f"icore {command}"
    parser = argparse.ArgumentParser(
        prog=prog,
        description="iCore 本地客户端：当前目录即工作区，智能体在本机跑工具。",
    )
    parser.add_argument(
        "-C",
        "--cd",
        dest="workdir",
        default=None,
        help="先切换到该目录再启动（默认当前目录）",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="打印智能体内部日志",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"icore {__version__}",
    )

    if command == "exec":
        parser.add_argument(
            "--resume",
            nargs="?",
            const="LAST",
            default=None,
            help="在已有会话上继续；省略 id 则用最近一次",
        )
        parser.add_argument(
            "prompt",
            help="任务描述；传 - 则从 stdin 读取",
        )
    elif command == "resume":
        parser.add_argument(
            "session_id",
            nargs="?",
            default="LAST",
            help="会话 id；省略则恢复最近一次",
        )
    else:
        parser.add_argument(
            "--resume",
            nargs="?",
            const="LAST",
            default=None,
            help="恢复最近或指定会话后进入交互",
        )
        parser.add_argument(
            "prompt",
            nargs="?",
            default=None,
            help="可选的首条用户消息",
        )

    args = parser.parse_args(raw)
    args.command = command
    if command == "resume":
        args.resume = args.session_id or "LAST"
        args.prompt = None
        args.command = "chat"
    if getattr(args, "workdir", None):
        args.workdir = str(Path(args.workdir).expanduser())
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_argv(argv)
    except SystemExit as e:
        code = e.code
        return int(code) if isinstance(code, int) else 0

    if getattr(args, "command", None) == "wechat":
        from cancer_claw.channels.wechat.cli import main as wechat_main

        return wechat_main(getattr(args, "wechat_argv", None))

    from cancer_claw.client.app import run_client

    try:
        return asyncio.run(run_client(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
