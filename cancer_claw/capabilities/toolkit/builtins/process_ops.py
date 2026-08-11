

import asyncio
import os
import signal
import platform

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult
from cancer_claw.capabilities.toolkit.workspace import resolve_cwd_for_shell

_managed_processes: dict[int, asyncio.subprocess.Process] = {}
_next_pid: int = 1

class ProcessOpsTool(BaseTool):


    @property
    def name(self) -> str:
        return "process_ops"

    @property
    def description(self) -> str:
        return "进程管理：启动后台进程、停止进程、查看进程列表。"

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "process_ops",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["start_process", "stop_process", "list_processes", "wait_process"],
                            "description": "操作类型"
                        },
                        "command": {
                            "type": "string",
                            "description": "要启动的命令（start_process 时使用）"
                        },
                        "process_id": {
                            "type": "integer",
                            "description": "进程管理 ID（stop_process/wait_process 时使用）"
                        },
                        "cwd": {
                            "type": "string",
                            "description": "工作目录（可选，默认项目 workspace/）"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "等待超时（秒），wait_process 时使用，默认 60",
                            "default": 60
                        },
                    },
                    "required": ["action"]
                }
            }
        }

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "")

        if action == "start_process":
            return await self._start(kwargs.get("command", ""), kwargs.get("cwd"))
        elif action == "stop_process":
            return await self._stop(kwargs.get("process_id", 0))
        elif action == "list_processes":
            return self._list()
        elif action == "wait_process":
            return await self._wait(kwargs.get("process_id", 0), kwargs.get("timeout", 60))
        else:
            return ToolResult(success=False, error=f"不支持的操作: {action}")

    async def _start(self, command: str, cwd: str | None = None) -> ToolResult:

        global _next_pid
        if not command:
            return ToolResult(success=False, error="command 参数不能为空")

        is_windows = platform.system() == "Windows"
        if is_windows:
            shell_cmd = ["powershell", "-NoProfile", "-Command", command]
        else:
            shell_cmd = ["bash", "-c", command]

        cdir, cerr = resolve_cwd_for_shell(cwd)
        if cerr:
            return ToolResult(success=False, error=cerr)

        process = await asyncio.create_subprocess_exec(
            *shell_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cdir,
        )

        pid = _next_pid
        _next_pid += 1
        _managed_processes[pid] = process

        return ToolResult(
            success=True,
            output=f"进程已启动: ID={pid}, 系统PID={process.pid}, 命令='{command}'",
            data={"process_id": pid, "system_pid": process.pid},
        )

    async def _stop(self, process_id: int) -> ToolResult:

        process = _managed_processes.get(process_id)
        if not process:
            return ToolResult(success=False, error=f"未找到进程 ID={process_id}")

        if process.returncode is not None:
            return ToolResult(success=True, output=f"进程 {process_id} 已退出（退出码: {process.returncode}）")

        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()

        return ToolResult(success=True, output=f"进程 {process_id} 已停止")

    def _list(self) -> ToolResult:

        if not _managed_processes:
            return ToolResult(success=True, output="没有正在管理的进程")

        lines = []
        for pid, process in _managed_processes.items():
            status = "运行中" if process.returncode is None else f"已退出(code={process.returncode})"
            lines.append(f"  ID={pid}  系统PID={process.pid}  状态={status}")

        return ToolResult(
            success=True,
            output=f"管理的进程（{len(lines)} 个）:\n" + "\n".join(lines),
            data={"count": len(lines)},
        )

    async def _wait(self, process_id: int, timeout: int = 60) -> ToolResult:

        process = _managed_processes.get(process_id)
        if not process:
            return ToolResult(success=False, error=f"未找到进程 ID={process_id}")

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            return ToolResult(success=False, error=f"等待进程 {process_id} 超时（{timeout}秒）")

        stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

        output_parts = []
        if stdout_text:
            output_parts.append(f"[stdout]\n{stdout_text}")
        if stderr_text:
            output_parts.append(f"[stderr]\n{stderr_text}")
        output_parts.append(f"[exit_code] {process.returncode}")

        return ToolResult(
            success=(process.returncode == 0),
            output="\n".join(output_parts),
            data={"exit_code": process.returncode},
        )
