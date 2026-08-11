

import asyncio
import sys
import tempfile
from pathlib import Path

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

class CodeExecTool(BaseTool):


    @property
    def name(self) -> str:
        return "code_exec"

    @property
    def description(self) -> str:
        return "执行 Python 代码片段（沙箱隔离，有超时限制）。用于计算、数据处理、格式转换等任务。"

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "code_exec",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["exec_python"],
                            "description": "操作类型"
                        },
                        "code": {
                            "type": "string",
                            "description": "要执行的 Python 代码"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "超时时间（秒），默认 30",
                            "default": 30
                        },
                    },
                    "required": ["action", "code"]
                }
            }
        }

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "exec_python")
        code = kwargs.get("code", "")
        timeout = kwargs.get("timeout", 30)

        if action != "exec_python":
            return ToolResult(success=False, error=f"不支持的操作: {action}")
        if not code.strip():
            return ToolResult(success=False, error="code 参数不能为空")

        return await self._exec_python(code, timeout)

    async def _exec_python(self, code: str, timeout: int = 30) -> ToolResult:


        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )
        try:
            tmp.write(code)
            tmp.close()


            process = await asyncio.create_subprocess_exec(
                sys.executable, tmp.name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(success=False, error=f"代码执行超时（{timeout}秒）")

            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")
            exit_code = process.returncode


            max_chars = 20000
            if len(stdout_text) > max_chars:
                stdout_text = stdout_text[:max_chars] + "\n... [输出过长，已截断]"

            output_parts = []
            if stdout_text:
                output_parts.append(stdout_text)
            if stderr_text:
                output_parts.append(f"[stderr]\n{stderr_text}")

            return ToolResult(
                success=(exit_code == 0),
                output="\n".join(output_parts) if output_parts else "(无输出)",
                data={"exit_code": exit_code},
                error=stderr_text if exit_code != 0 else "",
            )
        finally:

            Path(tmp.name).unlink(missing_ok=True)
