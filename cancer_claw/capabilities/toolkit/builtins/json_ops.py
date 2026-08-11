

import asyncio
import json

import yaml

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult
from cancer_claw.capabilities.toolkit.workspace import resolve_tool_path

class JsonOpsTool(BaseTool):


    @property
    def name(self) -> str:
        return "json_ops"

    @property
    def description(self) -> str:
        return "JSON/YAML 文件的读写和数据查询。支持 read_json/write_json/read_yaml/write_yaml/jq_query。"

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "json_ops",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["read_json", "write_json", "read_yaml", "write_yaml", "jq_query"],
                            "description": "操作类型"
                        },
                        "path": {
                            "type": "string",
                            "description": "文件路径"
                        },
                        "data": {
                            "type": "object",
                            "description": "要写入的数据（write_json/write_yaml 时使用）"
                        },
                        "query": {
                            "type": "string",
                            "description": "查询路径表达式，如 '.key1.key2[0].name'（jq_query 时使用）"
                        },
                        "json_text": {
                            "type": "string",
                            "description": "JSON 文本（jq_query 对文本操作时使用）"
                        },
                    },
                    "required": ["action"]
                }
            }
        }

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "")


        try:
            if action == "read_json":
                return await asyncio.to_thread(self._read_json, kwargs.get("path", ""))
            elif action == "write_json":
                return await asyncio.to_thread(self._write_json, kwargs.get("path", ""), kwargs.get("data"))
            elif action == "read_yaml":
                return await asyncio.to_thread(self._read_yaml, kwargs.get("path", ""))
            elif action == "write_yaml":
                return await asyncio.to_thread(self._write_yaml, kwargs.get("path", ""), kwargs.get("data"))
            elif action == "jq_query":
                return await asyncio.to_thread(
                    self._jq_query, kwargs.get("path", ""), kwargs.get("query", ""),
                    kwargs.get("json_text", ""),
                )
            else:
                return ToolResult(success=False, error=f"不支持的操作: {action}")
        except Exception as e:
            return ToolResult(success=False, error=f"json_ops.{action} 失败: {str(e)}")

    def _read_json(self, file_path: str) -> ToolResult:

        if not file_path:
            return ToolResult(success=False, error="path 参数不能为空")
        path, err = resolve_tool_path(file_path)
        if err:
            return ToolResult(success=False, error=err)
        if not path.exists():
            return ToolResult(success=False, error=f"文件不存在: {file_path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        formatted = json.dumps(data, ensure_ascii=False, indent=2)
        return ToolResult(success=True, output=formatted[:30000], data={"parsed": data})

    def _write_json(self, file_path: str, data) -> ToolResult:

        if not file_path:
            return ToolResult(success=False, error="path 参数不能为空")
        if data is None:
            return ToolResult(success=False, error="data 参数不能为空")
        path, err = resolve_tool_path(file_path)
        if err:
            return ToolResult(success=False, error=err)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data, ensure_ascii=False, indent=2)
        path.write_text(text, encoding="utf-8")
        return ToolResult(success=True, output=f"已写入 JSON 文件: {file_path}")

    def _read_yaml(self, file_path: str) -> ToolResult:

        if not file_path:
            return ToolResult(success=False, error="path 参数不能为空")
        path, err = resolve_tool_path(file_path)
        if err:
            return ToolResult(success=False, error=err)
        if not path.exists():
            return ToolResult(success=False, error=f"文件不存在: {file_path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))

        formatted = json.dumps(data, ensure_ascii=False, indent=2) if data else "(空文件)"
        return ToolResult(success=True, output=formatted[:30000], data={"parsed": data})

    def _write_yaml(self, file_path: str, data) -> ToolResult:

        if not file_path:
            return ToolResult(success=False, error="path 参数不能为空")
        if data is None:
            return ToolResult(success=False, error="data 参数不能为空")
        path, err = resolve_tool_path(file_path)
        if err:
            return ToolResult(success=False, error=err)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = yaml.dump(data, allow_unicode=True, default_flow_style=False)
        path.write_text(text, encoding="utf-8")
        return ToolResult(success=True, output=f"已写入 YAML 文件: {file_path}")

    def _jq_query(self, file_path: str, query: str, json_text: str) -> ToolResult:

        if not query:
            return ToolResult(success=False, error="query 参数不能为空")


        if file_path:
            path, err = resolve_tool_path(file_path)
            if err:
                return ToolResult(success=False, error=err)
            if not path.exists():
                return ToolResult(success=False, error=f"文件不存在: {file_path}")
            data = json.loads(path.read_text(encoding="utf-8"))
        elif json_text:
            data = json.loads(json_text)
        else:
            return ToolResult(success=False, error="需要 path 或 json_text 参数")


        result = self._navigate(data, query)
        formatted = json.dumps(result, ensure_ascii=False, indent=2) if not isinstance(result, str) else result
        return ToolResult(success=True, output=formatted, data={"result": result})

    @staticmethod
    def _navigate(data, query: str):

        import re

        parts = re.findall(r'\.(\w+)|\[(\d+)\]', query)
        current = data
        for key_part, index_part in parts:
            if key_part:
                if isinstance(current, dict):
                    current = current[key_part]
                else:
                    raise KeyError(f"无法在 {type(current).__name__} 上访问属性 '{key_part}'")
            elif index_part:
                idx = int(index_part)
                if isinstance(current, (list, tuple)):
                    current = current[idx]
                else:
                    raise IndexError(f"无法在 {type(current).__name__} 上使用索引 [{idx}]")
        return current
