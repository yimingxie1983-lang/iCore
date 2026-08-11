

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

class StopBackgroundMonitorTool(BaseTool):


    @property
    def name(self) -> str:
        return "stop_background_monitor"

    @property
    def description(self) -> str:
        return (
            "声明对某个后台进程已观察完成（无实际副作用）。"
            "v3 后日志已落盘到 workspace/logs/bg-<pid>.log，"
            "框架不再周期注入；本工具仅供事件流可见性使用。"
            "如需查看进度，直接用 file_ops.read_file 读日志。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "stop_background_monitor",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pid": {
                            "type": "integer",
                            "description": "要停止监控的进程 PID（由 shell_exec 启动后台进程时返回）",
                        },
                        "reason": {
                            "type": "string",
                            "description": "停止监控的原因，例如：'服务已就绪，端口 8080 正常监听' 或 '进程已退出，无需继续监控'",
                        },
                    },
                    "required": ["pid"],
                },
            },
        }

    async def execute(self, pid: int, reason: str = "") -> ToolResult:

        reason_text = f"，判断：{reason}" if reason else ""
        return ToolResult(
            success=True,
            output=(
                f"✅ 已声明 PID={pid} 观察完成{reason_text}。\n"
                f"提示：日志仍持续落盘到对应文件，需要时随时用 file_ops.read_file 读取。"
            ),
            data={"stop_pid": pid, "reason": reason},
        )
