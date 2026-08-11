

import asyncio
import re
import difflib
from pathlib import Path

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult
from cancer_claw.capabilities.toolkit.workspace import resolve_tool_path

class TextOpsTool(BaseTool):


    @property
    def name(self) -> str:
        return "text_ops"

    @property
    def description(self) -> str:
        return "文本搜索、替换、正则匹配、diff 对比、行数统计。用于代码分析和文本处理。"

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "text_ops",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["search", "replace", "grep_files", "diff", "count_lines"],
                            "description": "操作类型"
                        },
                        "text": {
                            "type": "string",
                            "description": "输入文本（search/replace/diff 时使用）"
                        },
                        "pattern": {
                            "type": "string",
                            "description": "搜索/替换的模式（支持正则）"
                        },
                        "replacement": {
                            "type": "string",
                            "description": "替换内容（replace 操作时使用）"
                        },
                        "path": {
                            "type": "string",
                            "description": "文件/目录路径（grep_files/count_lines），相对项目 workspace；grep 可用 . 表示 workspace 根"
                        },
                        "text_b": {
                            "type": "string",
                            "description": "diff 的第二段文本"
                        },
                        "file_pattern": {
                            "type": "string",
                            "description": "grep_files 时的文件过滤模式，如 '*.py'",
                            "default": "*"
                        },
                    },
                    "required": ["action"]
                }
            }
        }

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "")

        try:
            if action == "search":
                return self._search(kwargs.get("text", ""), kwargs.get("pattern", ""))
            elif action == "replace":
                return self._replace(kwargs.get("text", ""), kwargs.get("pattern", ""),
                                     kwargs.get("replacement", ""))
            elif action == "grep_files":

                return await asyncio.to_thread(
                    self._grep_files,
                    kwargs.get("path") if kwargs.get("path") is not None else ".",
                    kwargs.get("pattern", ""),
                    kwargs.get("file_pattern", "*"),
                )
            elif action == "diff":
                return self._diff(kwargs.get("text", ""), kwargs.get("text_b", ""))
            elif action == "count_lines":
                return await asyncio.to_thread(self._count_lines, kwargs.get("path", ""))
            else:
                return ToolResult(success=False, error=f"不支持的操作: {action}")
        except re.error as e:
            return ToolResult(success=False, error=f"正则表达式错误: {str(e)}")

    def _search(self, text: str, pattern: str) -> ToolResult:

        if not pattern:
            return ToolResult(success=False, error="pattern 参数不能为空")

        matches = list(re.finditer(pattern, text))
        if not matches:
            return ToolResult(success=True, output="未找到匹配项", data={"count": 0})

        results = []
        for i, m in enumerate(matches[:100]):
            line_num = text[:m.start()].count("\n") + 1
            results.append(f"  #{i+1} 行{line_num}: {m.group()!r}")

        output = f"找到 {len(matches)} 处匹配:\n" + "\n".join(results)
        return ToolResult(success=True, output=output, data={"count": len(matches)})

    def _replace(self, text: str, pattern: str, replacement: str) -> ToolResult:

        if not pattern:
            return ToolResult(success=False, error="pattern 参数不能为空")

        result, count = re.subn(pattern, replacement, text)
        return ToolResult(
            success=True,
            output=f"替换了 {count} 处。\n替换后文本:\n{result[:10000]}",
            data={"count": count, "result": result},
        )

    def _grep_files(self, dir_path: str, pattern: str, file_pattern: str) -> ToolResult:

        if not pattern:
            return ToolResult(success=False, error="pattern 参数不能为空")

        path, res_err = resolve_tool_path(dir_path)
        if res_err:
            return ToolResult(success=False, error=res_err)
        if not path.exists():
            return ToolResult(success=False, error=f"目录不存在: {dir_path}")

        results = []
        files_searched = 0
        regex = re.compile(pattern)

        for file_path in sorted(path.rglob(file_pattern)):
            if not file_path.is_file():
                continue
            files_searched += 1
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(content.splitlines(), 1):
                    if regex.search(line):
                        results.append(f"  {file_path}:{i}: {line.strip()}")
                        if len(results) >= 200:
                            break
            except Exception:
                continue
            if len(results) >= 200:
                break

        if not results:
            output = f"在 {files_searched} 个文件中未找到匹配 '{pattern}' 的内容"
        else:
            output = f"在 {files_searched} 个文件中找到 {len(results)} 处匹配:\n" + "\n".join(results)
        return ToolResult(success=True, output=output, data={"count": len(results)})

    def _diff(self, text_a: str, text_b: str) -> ToolResult:

        lines_a = text_a.splitlines(keepends=True)
        lines_b = text_b.splitlines(keepends=True)
        diff = difflib.unified_diff(lines_a, lines_b, fromfile="原文", tofile="修改后", lineterm="")
        diff_text = "\n".join(diff)
        if not diff_text:
            return ToolResult(success=True, output="两段文本完全相同", data={"has_diff": False})
        return ToolResult(success=True, output=f"差异:\n{diff_text}", data={"has_diff": True})

    def _count_lines(self, file_path: str) -> ToolResult:

        if not file_path:
            return ToolResult(success=False, error="path 参数不能为空")
        path, res_err = resolve_tool_path(file_path)
        if res_err:
            return ToolResult(success=False, error=res_err)
        if not path.exists():
            return ToolResult(success=False, error=f"文件不存在: {file_path}")
        content = path.read_text(encoding="utf-8", errors="ignore")
        count = len(content.splitlines())
        return ToolResult(success=True, output=f"{file_path}: {count} 行",
                          data={"lines": count, "chars": len(content)})
