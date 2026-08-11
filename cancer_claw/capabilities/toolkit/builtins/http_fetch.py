

import json as json_module

import httpx

from cancer_claw.capabilities.toolkit._web_fetch import (
    WebFetchError,
    fetch_text,
    looks_like_tls_fingerprint_block,
)
from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult
from cancer_claw.capabilities.toolkit.workspace import resolve_tool_path

class HttpFetchTool(BaseTool):


    @property
    def name(self) -> str:
        return "http_fetch"

    @property
    def description(self) -> str:
        return "发起 HTTP 请求（GET/POST/PUT/DELETE）和下载文件。用于调用外部 API 或获取网页内容。"

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "http_fetch",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["get", "post", "put", "delete", "download_file"],
                            "description": "HTTP 方法"
                        },
                        "url": {
                            "type": "string",
                            "description": "请求 URL"
                        },
                        "headers": {
                            "type": "object",
                            "description": "请求头（可选）"
                        },
                        "body": {
                            "type": "object",
                            "description": "请求体 JSON（POST/PUT 时使用）"
                        },
                        "save_path": {
                            "type": "string",
                            "description": "保存路径（相对项目 workspace 或项目内绝对路径）"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "超时时间（秒），默认 30",
                            "default": 30
                        },
                    },
                    "required": ["action", "url"]
                }
            }
        }

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "get")
        url = kwargs.get("url", "")
        headers = kwargs.get("headers", {})
        body = kwargs.get("body")
        timeout = kwargs.get("timeout", 30)

        if not url:
            return ToolResult(success=False, error="url 参数不能为空")

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                if action == "download_file":
                    return await self._download(client, url, kwargs.get("save_path", ""), headers)


                if action == "get":
                    try:
                        resp = await client.get(url, headers=headers)
                    except (httpx.ConnectError, httpx.ReadError) as e:


                        if looks_like_tls_fingerprint_block(e):
                            return await self._get_via_stdlib(url, headers, timeout)
                        raise
                elif action == "post":
                    resp = await client.post(url, headers=headers, json=body)
                elif action == "put":
                    resp = await client.put(url, headers=headers, json=body)
                elif action == "delete":
                    resp = await client.delete(url, headers=headers)
                else:
                    return ToolResult(success=False, error=f"不支持的 HTTP 方法: {action}")

                return self._format_response(resp)

        except httpx.TimeoutException:
            return ToolResult(success=False, error=f"请求超时（{timeout}秒）: {url}")
        except Exception as e:
            return ToolResult(success=False, error=f"HTTP 请求失败: {str(e)}")

    async def _get_via_stdlib(self, url: str, headers: dict, timeout: int) -> ToolResult:

        try:
            status, text, _final = await fetch_text(
                url, headers=headers or None, timeout=timeout
            )
        except WebFetchError as e:
            return ToolResult(success=False, error=f"HTTP 请求失败: {e}")

        max_chars = 30000
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars] + "\n... [响应过长，已截断]"
        return ToolResult(
            success=(200 <= status < 400),
            output=f"HTTP {status}\n{text}",
            data={"status_code": status, "truncated": truncated, "via": "stdlib"},
            error="" if status < 400 else f"HTTP {status}",
        )

    def _format_response(self, resp: httpx.Response) -> ToolResult:


        text = resp.text
        max_chars = 30000
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars] + "\n... [响应过长，已截断]"

        output = f"HTTP {resp.status_code}\n{text}"
        return ToolResult(
            success=(200 <= resp.status_code < 400),
            output=output,
            data={
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "truncated": truncated,
            },
            error="" if resp.status_code < 400 else f"HTTP {resp.status_code}",
        )

    async def _download(self, client: httpx.AsyncClient, url: str,
                        save_path: str, headers: dict) -> ToolResult:

        if not save_path:
            return ToolResult(success=False, error="download_file 需要 save_path 参数")

        path, res_err = resolve_tool_path(save_path)
        if res_err:
            return ToolResult(success=False, error=res_err)
        path.parent.mkdir(parents=True, exist_ok=True)

        resp = await client.get(url, headers=headers)
        if resp.status_code >= 400:
            return ToolResult(success=False, error=f"下载失败: HTTP {resp.status_code}")

        path.write_bytes(resp.content)
        return ToolResult(
            success=True,
            output=f"文件已下载: {path}（{len(resp.content)} 字节）",
            data={"path": str(path), "size": len(resp.content)},
        )
