

import asyncio
import zipfile
import tarfile
from pathlib import Path

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult
from cancer_claw.capabilities.toolkit.workspace import resolve_two_paths

class ArchiveOpsTool(BaseTool):


    @property
    def name(self) -> str:
        return "archive_ops"

    @property
    def description(self) -> str:
        return "压缩解压操作。支持 zip/unzip/tar/untar，处理 zip、tar.gz 等格式。"

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "archive_ops",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["zip", "unzip", "tar", "untar"],
                            "description": "操作类型"
                        },
                        "source": {
                            "type": "string",
                            "description": "源路径：zip/tar 时为要压缩的文件/目录；unzip/untar 时为压缩包路径"
                        },
                        "destination": {
                            "type": "string",
                            "description": "目标路径：zip/tar 时为输出的压缩包路径；unzip/untar 时为解压目录"
                        },
                    },
                    "required": ["action", "source", "destination"]
                }
            }
        }

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "")
        source = kwargs.get("source", "")
        destination = kwargs.get("destination", "")

        if not source or not destination:
            return ToolResult(success=False, error="source 和 destination 参数都不能为空")

        pair, res_err = resolve_two_paths(source, destination)
        if res_err:
            return ToolResult(success=False, error=res_err)
        src_p, dst_p = pair


        try:
            if action == "zip":
                return await asyncio.to_thread(self._zip, src_p, dst_p)
            elif action == "unzip":
                return await asyncio.to_thread(self._unzip, src_p, dst_p)
            elif action == "tar":
                return await asyncio.to_thread(self._tar, src_p, dst_p)
            elif action == "untar":
                return await asyncio.to_thread(self._untar, src_p, dst_p)
            else:
                return ToolResult(success=False, error=f"不支持的操作: {action}")
        except Exception as e:
            return ToolResult(success=False, error=f"archive_ops.{action} 失败: {str(e)}")

    def _zip(self, src_path: Path, dst_path: Path) -> ToolResult:

        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if not src_path.exists():
            return ToolResult(success=False, error=f"源路径不存在: {src_path}")

        file_count = 0
        with zipfile.ZipFile(dst_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if src_path.is_file():
                zf.write(src_path, src_path.name)
                file_count = 1
            else:
                for file_path in src_path.rglob("*"):
                    if file_path.is_file():
                        zf.write(file_path, file_path.relative_to(src_path))
                        file_count += 1

        size = dst_path.stat().st_size
        return ToolResult(
            success=True,
            output=f"已创建 ZIP: {dst_path}（{file_count} 个文件，{size} 字节）",
            data={"file_count": file_count, "size": size},
        )

    def _unzip(self, src_path: Path, dst_path: Path) -> ToolResult:

        if not src_path.exists():
            return ToolResult(success=False, error=f"ZIP 文件不存在: {src_path}")

        dst_path.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(src_path, "r") as zf:
            zf.extractall(dst_path)
            file_count = len(zf.namelist())

        return ToolResult(
            success=True,
            output=f"已解压到 {dst_path}（{file_count} 个文件）",
            data={"file_count": file_count},
        )

    def _tar(self, src_path: Path, dst_path: Path) -> ToolResult:

        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if not src_path.exists():
            return ToolResult(success=False, error=f"源路径不存在: {src_path}")

        with tarfile.open(dst_path, "w:gz") as tf:
            tf.add(str(src_path), arcname=src_path.name)

        size = dst_path.stat().st_size
        return ToolResult(
            success=True,
            output=f"已创建 tar.gz: {dst_path}（{size} 字节）",
            data={"size": size},
        )

    def _untar(self, src_path: Path, dst_path: Path) -> ToolResult:

        if not src_path.exists():
            return ToolResult(success=False, error=f"tar 文件不存在: {src_path}")

        dst_path.mkdir(parents=True, exist_ok=True)

        with tarfile.open(src_path, "r:*") as tf:
            tf.extractall(dst_path)
            file_count = len(tf.getnames())

        return ToolResult(
            success=True,
            output=f"已解压到 {dst_path}（{file_count} 个文件）",
            data={"file_count": file_count},
        )
