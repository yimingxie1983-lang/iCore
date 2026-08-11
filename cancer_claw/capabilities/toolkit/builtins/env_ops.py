

import os
import platform
import shutil

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

class EnvOpsTool(BaseTool):


    @property
    def name(self) -> str:
        return "env_ops"

    @property
    def description(self) -> str:
        return "环境变量读写和系统信息查询（OS/CPU/内存/磁盘）。"

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "env_ops",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["get_env", "set_env", "system_info"],
                            "description": "操作类型"
                        },
                        "key": {
                            "type": "string",
                            "description": "环境变量名（get_env/set_env 时使用）"
                        },
                        "value": {
                            "type": "string",
                            "description": "环境变量值（set_env 时使用）"
                        },
                    },
                    "required": ["action"]
                }
            }
        }

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "")

        if action == "get_env":
            return self._get_env(kwargs.get("key", ""))
        elif action == "set_env":
            return self._set_env(kwargs.get("key", ""), kwargs.get("value", ""))
        elif action == "system_info":
            return self._system_info()
        else:
            return ToolResult(success=False, error=f"不支持的操作: {action}")

    def _get_env(self, key: str) -> ToolResult:

        if not key:

            env_list = []
            for k, v in sorted(os.environ.items()):

                display_v = v if not any(s in k.upper() for s in ["KEY", "SECRET", "TOKEN", "PASSWORD"]) else "***"
                env_list.append(f"  {k}={display_v}")
            return ToolResult(success=True, output=f"环境变量（{len(env_list)} 项）:\n" + "\n".join(env_list[:100]))

        value = os.environ.get(key)
        if value is None:
            return ToolResult(success=True, output=f"环境变量 {key} 未设置", data={"exists": False})
        return ToolResult(success=True, output=f"{key}={value}", data={"value": value, "exists": True})

    def _set_env(self, key: str, value: str) -> ToolResult:

        if not key:
            return ToolResult(success=False, error="key 参数不能为空")
        os.environ[key] = value
        return ToolResult(success=True, output=f"已设置环境变量: {key}={value}（仅当前进程有效）")

    def _system_info(self) -> ToolResult:

        info = {
            "os": platform.system(),
            "os_version": platform.version(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "hostname": platform.node(),
            "processor": platform.processor() or "未知",
        }


        cpu_count = os.cpu_count()
        info["cpu_cores"] = cpu_count


        disk = shutil.disk_usage(".")
        info["disk_total_gb"] = round(disk.total / (1024**3), 1)
        info["disk_free_gb"] = round(disk.free / (1024**3), 1)
        info["disk_used_percent"] = round((disk.used / disk.total) * 100, 1)


        lines = [
            f"操作系统: {info['os']} {info['os_release']} ({info['os_version']})",
            f"架构: {info['architecture']}",
            f"CPU: {info['processor']}（{cpu_count} 核）",
            f"磁盘: {info['disk_free_gb']}GB 可用 / {info['disk_total_gb']}GB 总计（已用 {info['disk_used_percent']}%）",
            f"Python: {info['python_version']}",
            f"主机名: {info['hostname']}",
        ]
        return ToolResult(success=True, output="\n".join(lines), data=info)
