

import asyncio
import platform

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult
from cancer_claw.capabilities.toolkit.workspace import resolve_cwd_for_shell, resolve_tool_path

class GitOpsTool(BaseTool):


    @property
    def name(self) -> str:
        return "git_ops"

    @property
    def description(self) -> str:
        return "Git 版本控制操作。支持 clone/init/add/commit/diff/log/branch/checkout/push/pull/status。"

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "git_ops",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["clone", "init", "add", "commit", "diff", "log",
                                     "branch", "checkout", "push", "pull", "status"],
                            "description": "Git 操作类型"
                        },
                        "cwd": {
                            "type": "string",
                            "description": "Git 仓库目录（默认项目 workspace/）。clone 时若指定则为克隆目标目录（相对 workspace 或项目内绝对路径）"
                        },
                        "url": {
                            "type": "string",
                            "description": "远程仓库 URL（clone 时使用）"
                        },
                        "message": {
                            "type": "string",
                            "description": "提交信息（commit 时使用）"
                        },
                        "files": {
                            "type": "string",
                            "description": "文件路径，多个用空格分隔（add 时使用），'.' 表示全部",
                            "default": "."
                        },
                        "branch_name": {
                            "type": "string",
                            "description": "分支名（branch/checkout 时使用）"
                        },
                        "args": {
                            "type": "string",
                            "description": "额外的 git 命令参数"
                        },
                    },
                    "required": ["action"]
                }
            }
        }

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "")


        if action == "clone":
            url = kwargs.get("url", "")
            if not url:
                return ToolResult(success=False, error="clone 需要 url 参数")
            dest = kwargs.get("cwd", ".")
            shell_cwd, err = resolve_cwd_for_shell(None)
            if err:
                return ToolResult(success=False, error=err)
            if dest.strip() in (".", ""):
                cmd = f"git clone {url}"
            else:
                p, err = resolve_tool_path(dest)
                if err:
                    return ToolResult(success=False, error=err)
                cmd = f'git clone {url} "{p}"'
            return await self._run_git(cmd, shell_cwd)
        elif action == "init":
            cmd = "git init"
        elif action == "add":
            files = kwargs.get("files", ".")
            cmd = f"git add {files}"
        elif action == "commit":
            message = kwargs.get("message", "")
            if not message:
                return ToolResult(success=False, error="commit 需要 message 参数")
            cmd = f'git commit -m "{message}"'
        elif action == "diff":
            args = kwargs.get("args", "")
            cmd = f"git diff {args}".strip()
        elif action == "log":
            args = kwargs.get("args", "--oneline -20")
            cmd = f"git log {args}"
        elif action == "branch":
            branch_name = kwargs.get("branch_name", "")
            args = kwargs.get("args", "")
            if branch_name:
                cmd = f"git branch {branch_name} {args}".strip()
            else:
                cmd = f"git branch {args}".strip()
        elif action == "checkout":
            branch_name = kwargs.get("branch_name", "")
            if not branch_name:
                return ToolResult(success=False, error="checkout 需要 branch_name 参数")
            cmd = f"git checkout {branch_name}"
        elif action == "push":
            args = kwargs.get("args", "")
            cmd = f"git push {args}".strip()
        elif action == "pull":
            args = kwargs.get("args", "")
            cmd = f"git pull {args}".strip()
        elif action == "status":
            cmd = "git status"
        else:
            return ToolResult(success=False, error=f"不支持的 Git 操作: {action}")

        wdir, err = resolve_cwd_for_shell(kwargs.get("cwd", "."))
        if err:
            return ToolResult(success=False, error=err)
        return await self._run_git(cmd, wdir)

    async def _run_git(self, cmd: str, cwd: str) -> ToolResult:

        is_windows = platform.system() == "Windows"
        if is_windows:
            shell_cmd = ["powershell", "-NoProfile", "-Command", cmd]
        else:
            shell_cmd = ["bash", "-c", cmd]

        try:
            process = await asyncio.create_subprocess_exec(
                *shell_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
        except asyncio.TimeoutError:
            return ToolResult(success=False, error=f"Git 命令超时（120秒）: {cmd}")
        except Exception as e:
            return ToolResult(success=False, error=f"Git 命令执行失败: {str(e)}")

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")
        exit_code = process.returncode


        output_parts = []
        if stdout_text.strip():
            output_parts.append(stdout_text.strip())
        if stderr_text.strip():
            output_parts.append(stderr_text.strip())

        return ToolResult(
            success=(exit_code == 0),
            output="\n".join(output_parts) if output_parts else "(无输出)",
            data={"exit_code": exit_code},
            error=stderr_text if exit_code != 0 else "",
        )
