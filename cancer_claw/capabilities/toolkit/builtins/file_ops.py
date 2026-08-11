

import asyncio
import shutil
from pathlib import Path

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult
from cancer_claw.capabilities.toolkit.file_read_cache import get_file_read_cache
from cancer_claw.capabilities.toolkit.workspace import resolve_tool_path, resolve_two_paths

_IGNORED_DIR_NAMES: set[str] = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    "dist", "build", "out", ".next", ".nuxt", ".turbo",
    ".idea", ".vscode", ".vs",
    "target",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    ".cache", ".parcel-cache",
    ".DS_Store",
}

def _verify_hint(path: Path) -> str:

    suffix = path.suffix.lower()
    if suffix == ".py":
        return f"\n建议下一步：shell_exec 跑 `python -c \"import {path.stem}\"` 或 pytest 验证。"
    if suffix in (".ts", ".tsx", ".js", ".jsx"):
        return "\n建议下一步：shell_exec 跑 tsc / lint / 单测验证。"
    if suffix in (".json", ".yaml", ".yml", ".toml"):
        return "\n建议下一步：shell_exec 跑 schema 校验或 reload 配置。"
    return ""

class FileOpsTool(BaseTool):


    @property
    def name(self) -> str:
        return "file_ops"

    @property
    def description(self) -> str:
        return (
            "文件读写、目录操作。路径相对当前项目的 workspace/；访问 memory 等可用 ../memory/…。"
            "须通过项目对话使用。禁止访问 iCore 框架安装目录。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "file_ops",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["read_file", "write_file", "str_replace", "append_file", "copy",
                                     "move", "delete", "list_dir", "mkdir", "exists", "glob"],
                            "description": (
                                "要执行的操作。改文件的优先级（高→低）：\n"
                                "1) `str_replace` —— **单点小改（1-3 行）首选**。old_string 全等匹配+唯一性检查，"
                                "schema 极简、模型最熟、出错率最低。\n"
                                "2) `write_file` —— **仅**用于：(1) 新建文件；(2) 改动量 > 70% 的整文件重写。"
                                "改已有文件用 write_file 整文件重写很容易撞 max_tokens 截断 → **改文件必须先 str_replace**。\n"
                                "改之前必须先 read_file 看清现有结构。\n"
                                "read_file 准则：带具体问题去读（报错位置、契约确认、改前勘察）；"
                                "不要反复读同一文件，想验证改动是否生效改用 shell_exec 跑起来。"
                            )
                        },
                        "path": {
                            "type": "string",
                            "description": "相对项目 workspace 的路径（如 hello.py、subdir/a.txt），或项目内的绝对路径。"
                        },
                        "content": {
                            "type": "string",
                            "description": "写入的内容（write_file/append_file 时使用）"
                        },
                        "old_string": {
                            "type": "string",
                            "description": (
                                "str_replace 时要替换掉的原文本。必须与文件中的内容**完全一致**，"
                                "包括缩进（tab vs 空格不能错）、换行、空白。\n"
                                "在文件中必须**唯一**——不唯一会失败，请扩大 old_string 包含更多上下文行使其唯一，"
                                "或显式设 replace_all=True 全部替换。\n"
                                "建议带 3-5 行上下文行确保唯一性。"
                            )
                        },
                        "new_string": {
                            "type": "string",
                            "description": (
                                "str_replace 时替换为的新文本。必须与 old_string 不同。"
                                "保持与周围代码一致的缩进风格。"
                            )
                        },
                        "replace_all": {
                            "type": "boolean",
                            "description": (
                                "str_replace 时是否替换全部匹配项。默认 false（要求 old_string 唯一）。"
                                "改变量名 / 重命名标识符等需要全局替换时设为 true。"
                            ),
                            "default": False,
                        },
                        "destination": {
                            "type": "string",
                            "description": "目标路径（copy/move 时使用），规则同 path"
                        },
                        "pattern": {
                            "type": "string",
                            "description": "glob 匹配模式（glob 操作时使用），如 '*.py'"
                        },
                        "encoding": {
                            "type": "string",
                            "description": "文件编码，默认 utf-8",
                            "default": "utf-8"
                        },
                        "offset": {
                            "type": "integer",
                            "description": (
                                "起始位置（行级语义，与 Cursor 一致）。"
                                "read_file 时为起始行号（1-indexed），支持负数从末尾倒数：offset=-100 表示读最后 100 行。"
                                "list_dir 时为跳过的项数（用于分页）。"
                                "建议读大文件时不传 offset/limit 仅得首 200 行；要更多请传 offset=201&limit=400。"
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "description": (
                                "最多读取数量（行级 / 项级）。"
                                "read_file 时为最多读取的行数（显式带 offset 时默认 1500；"
                        "不传 offset 时由工具内部默认首窗 200 行，勿与 limit 混用）。"
                                "list_dir 时为本页最多显示的项数（默认 200）。"
                                "data.next_line / data.next_offset 会告诉你下页从哪继续。"
                            ),
                        },
                        "include_ignored": {
                            "type": "boolean",
                            "description": (
                                "list_dir 时是否包含被自动隐藏的噪音目录（node_modules / .git / __pycache__ / "
                                ".venv / dist / build / .idea / .vscode 等）。"
                                "默认 false（隐藏，避免灌爆 context）；想看完整目录树时设为 true。"
                            ),
                            "default": False,
                        },
                    },
                    "required": ["action", "path"]
                }
            }
        }

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "")
        path_str = kwargs.get("path", "")

        try:
            if action == "copy":
                pair, err = resolve_two_paths(path_str, kwargs.get("destination", ""))
                if err:
                    return ToolResult(success=False, error=err)
                return await self._copy(pair[0], pair[1])
            elif action == "move":
                pair, err = resolve_two_paths(path_str, kwargs.get("destination", ""))
                if err:
                    return ToolResult(success=False, error=err)
                return await self._move(pair[0], pair[1])
            path, err = resolve_tool_path(path_str)
            if err:
                return ToolResult(success=False, error=err)
            if action == "read_file":
                return await self._read_file(
                    path,
                    kwargs.get("encoding", "utf-8"),
                    offset=kwargs.get("offset"),
                    limit=kwargs.get("limit"),
                )
            elif action == "write_file":
                return await self._write_file(path, kwargs.get("content", ""), kwargs.get("encoding", "utf-8"))
            elif action == "str_replace":
                return await self._str_replace(
                    path,
                    kwargs.get("old_string", ""),
                    kwargs.get("new_string", ""),
                    kwargs.get("encoding", "utf-8"),
                    bool(kwargs.get("replace_all", False)),
                )
            elif action == "append_file":
                return await self._append_file(path, kwargs.get("content", ""), kwargs.get("encoding", "utf-8"))
            elif action == "delete":
                return await self._delete(path)
            elif action == "list_dir":
                return await self._list_dir(
                    path,
                    offset=int(kwargs.get("offset") or 0),
                    limit=int(kwargs.get("limit") or 200),
                    include_ignored=bool(kwargs.get("include_ignored", False)),
                )
            elif action == "mkdir":
                return await self._mkdir(path)
            elif action == "exists":
                return await self._exists(path)
            elif action == "glob":
                return await self._glob(path, kwargs.get("pattern", "*"))
            else:
                return ToolResult(success=False, error=f"不支持的操作: {action}")
        except Exception as e:
            return ToolResult(success=False, error=f"file_ops.{action} 失败: {str(e)}")

    async def _read_file(
        self,
        path: Path,
        encoding: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> ToolResult:

        if not path.exists():
            return ToolResult(success=False, error=f"文件不存在: {path}")
        if not path.is_file():
            return ToolResult(success=False, error=f"路径不是文件: {path}")









        _cache = get_file_read_cache()
        _hit_meta = _cache.check_hit(path, offset, limit)


        size = path.stat().st_size


        def _read_lines() -> list[str]:
            try:
                with path.open("r", encoding=encoding, errors="replace") as fh:
                    return fh.read().splitlines()
            except LookupError:
                with path.open("r", encoding="utf-8", errors="replace") as fh:
                    return fh.read().splitlines()

        all_lines = await asyncio.to_thread(_read_lines)

        total_lines = len(all_lines)
        if total_lines == 0:
            _cache.record(path, offset, limit)
            _empty_out = "File is empty."
            if _hit_meta is not None:
                _empty_out += _hit_meta["note"]
            return ToolResult(
                success=True,
                output=_empty_out,
                data={"total_lines": 0, "size": size, "next_line": 1, "eof": True},
            )


        DEFAULT_FIRST_WINDOW = 200
        DEFAULT_LIMIT = 1500
        LARGE_FILE_CAP = 1500


        if offset is None and limit is None:
            if total_lines <= DEFAULT_FIRST_WINDOW:
                start_line = 1
                end_line = total_lines
            else:
                start_line = 1
                end_line = DEFAULT_FIRST_WINDOW
        else:
            eff_offset = offset if offset is not None else 1
            eff_limit = limit if limit is not None else DEFAULT_LIMIT
            if eff_limit <= 0:
                return ToolResult(success=False, error=f"limit 必须 > 0，收到 {eff_limit}")

            if eff_offset < 0:
                start_line = max(1, total_lines + eff_offset + 1)
            elif eff_offset == 0:
                start_line = 1
            else:
                start_line = eff_offset

            if start_line > total_lines:
                return ToolResult(
                    success=True,
                    output=f"[已到文件末尾，total_lines={total_lines}，offset={eff_offset} 超出]",
                    data={
                        "total_lines": total_lines,
                        "size": size,
                        "start_line": start_line,
                        "end_line": start_line - 1,
                        "next_line": total_lines + 1,
                        "eof": True,
                    },
                )
            end_line = min(total_lines, start_line + eff_limit - 1)

            if offset is not None and limit is None and end_line - start_line + 1 >= LARGE_FILE_CAP:
                end_line = min(total_lines, start_line + LARGE_FILE_CAP - 1)


        rendered = []
        for line_num in range(start_line, end_line + 1):
            rendered.append(f"{line_num:>6}|{all_lines[line_num - 1]}")
        body = "\n".join(rendered)

        truncated = end_line < total_lines
        next_line = end_line + 1
        eof = end_line >= total_lines

        header = (
            f"[file_ops.read_file] {path.name} | total_lines={total_lines} | "
            f"showing {start_line}-{end_line}"
        )
        if truncated:
            header += (
                f" | 还有 {total_lines - end_line} 行未读，"
                f"传 offset={next_line} 继续；或读尾部传 offset=-100"
            )
        header += "\n" + ("─" * 40) + "\n"




        _cache.record(path, offset, limit)

        _output = header + body
        if _hit_meta is not None:
            _output += _hit_meta["note"]

        return ToolResult(
            success=True,
            output=_output,
            data={
                "total_lines": total_lines,
                "size": size,
                "start_line": start_line,
                "end_line": end_line,
                "next_line": next_line,
                "eof": eof,
                "truncated": truncated,
                "cache_repeat_read": _hit_meta is not None,
            },
        )

    async def _write_file(self, path: Path, content: str, encoding: str) -> ToolResult:

        path.parent.mkdir(parents=True, exist_ok=True)

        await asyncio.to_thread(path.write_text, content, encoding=encoding)


        get_file_read_cache().invalidate(path)

        return ToolResult(
            success=True,
            output=f"已写入文件: {path}（{len(content)} 字符）{_verify_hint(path)}",
            data={"path": str(path), "size": len(content)},
        )

    async def _str_replace(
        self,
        path: Path,
        old_string: str,
        new_string: str,
        encoding: str,
        replace_all: bool,
    ) -> ToolResult:

        if not path.exists():
            return ToolResult(success=False, error=f"文件不存在: {path}")
        if not path.is_file():
            return ToolResult(success=False, error=f"路径不是文件: {path}")
        if not old_string:
            return ToolResult(success=False, error="old_string 不能为空")
        if old_string == new_string:
            return ToolResult(success=False, error="old_string 与 new_string 相同，无需替换")

        try:
            content = await asyncio.to_thread(path.read_text, encoding=encoding)
        except UnicodeDecodeError as e:
            return ToolResult(success=False, error=f"读取文件解码失败（encoding={encoding}）: {e}")

        count = content.count(old_string)
        if count == 0:
            return ToolResult(
                success=False,
                error=(
                    f"old_string 在 {path.name} 中未找到。"
                    f"请检查：(1) 缩进是否完全一致（tab vs 空格不能错）；"
                    f"(2) 是否漏抄/多抄了字符或换行；"
                    f"(3) 必要时先 read_file 重新确认现状再写 old_string。"
                ),
            )
        if count > 1 and not replace_all:
            return ToolResult(
                success=False,
                error=(
                    f"old_string 在 {path.name} 中出现 {count} 次，无法精确定位。"
                    f"请扩大 old_string 包含更多上下文行使其唯一；"
                    f"或确实需要全部替换则设 replace_all=True。"
                ),
            )

        new_content = content.replace(old_string, new_string)
        await asyncio.to_thread(path.write_text, new_content, encoding=encoding)

        get_file_read_cache().invalidate(path)

        replaced = count if replace_all else 1
        return ToolResult(
            success=True,
            output=(
                f"已替换 {path}（{replaced} 处）"
                f"{_verify_hint(path)}"
            ),
            data={
                "path": str(path),
                "replaced": replaced,
                "old_size": len(content),
                "new_size": len(new_content),
            },
        )

    async def _append_file(self, path: Path, content: str, encoding: str) -> ToolResult:

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding=encoding) as f:
            f.write(content)
        get_file_read_cache().invalidate(path)
        return ToolResult(
            success=True,
            output=f"已追加到文件: {path}（追加 {len(content)} 字符）",
        )

    async def _copy(self, src: Path, dst: Path) -> ToolResult:

        if not src.exists():
            return ToolResult(success=False, error=f"源路径不存在: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            await asyncio.to_thread(shutil.copytree, str(src), str(dst), dirs_exist_ok=True)
        else:
            await asyncio.to_thread(shutil.copy2, str(src), str(dst))

        get_file_read_cache().invalidate(dst)
        return ToolResult(success=True, output=f"已复制: {src} → {dst}")

    async def _move(self, src: Path, dst: Path) -> ToolResult:

        if not src.exists():
            return ToolResult(success=False, error=f"源路径不存在: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

        _c = get_file_read_cache()
        _c.invalidate(src)
        _c.invalidate(dst)
        return ToolResult(success=True, output=f"已移动: {src} → {dst}")

    async def _delete(self, path: Path) -> ToolResult:

        if not path.exists():
            return ToolResult(success=False, error=f"路径不存在: {path}")
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            await asyncio.to_thread(shutil.rmtree, str(path))
        get_file_read_cache().invalidate(path)
        return ToolResult(success=True, output=f"已删除: {path}")

    async def _list_dir(
        self,
        path: Path,
        *,
        offset: int = 0,
        limit: int = 200,
        include_ignored: bool = False,
    ) -> ToolResult:

        if not path.exists():
            return ToolResult(success=False, error=f"目录不存在: {path}")
        if not path.is_dir():
            return ToolResult(success=False, error=f"路径不是目录: {path}")

        all_items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        total = len(all_items)

        if not include_ignored:
            visible = [p for p in all_items if p.name not in _IGNORED_DIR_NAMES]
        else:
            visible = all_items
        skipped_noise = total - len(visible)

        if offset < 0:
            offset = 0
        page = visible[offset : offset + limit]

        lines = []
        for item in page:
            entry_type = "dir" if item.is_dir() else "file"
            size = item.stat().st_size if item.is_file() else 0
            size_str = f"  ({size} bytes)" if size else ""
            lines.append(f"  [{entry_type}] {item.name}{size_str}")

        header_parts = [f"目录 {path}"]
        header_parts.append(f"总计 {total} 项")
        if skipped_noise:
            header_parts.append(f"已隐藏 {skipped_noise} 项噪音目录(node_modules/.git 等)")
        header_parts.append(f"显示 {offset+1}-{offset+len(page)} / {len(visible)}")
        header = " | ".join(header_parts) + "\n"

        next_offset = offset + len(page)
        has_more = next_offset < len(visible)
        footer = ""
        if has_more:
            footer = (
                f"\n... 还有 {len(visible) - next_offset} 项未显示。"
                f"用 offset={next_offset} 继续看下一页。"
            )
        if skipped_noise and not include_ignored:
            footer += (
                f"\n（噪音目录被自动隐藏；如需查看 node_modules 等，"
                f"传 include_ignored=true）"
            )

        body = "\n".join(lines) if lines else "（本页为空）"
        return ToolResult(
            success=True,
            output=header + body + footer,
            data={
                "total": total,
                "visible": len(visible),
                "skipped_noise": skipped_noise,
                "offset": offset,
                "next_offset": next_offset,
                "has_more": has_more,
                "page_count": len(page),
            },
        )

    async def _mkdir(self, path: Path) -> ToolResult:

        path.mkdir(parents=True, exist_ok=True)
        return ToolResult(success=True, output=f"目录已创建: {path}")

    async def _exists(self, path: Path) -> ToolResult:

        exists = path.exists()
        path_type = "不存在"
        if exists:
            path_type = "目录" if path.is_dir() else "文件"
        return ToolResult(
            success=True,
            output=f"{path}: {'存在' if exists else '不存在'}" + (f"（{path_type}）" if exists else ""),
            data={"exists": exists, "type": path_type},
        )

    async def _glob(self, path: Path, pattern: str) -> ToolResult:

        if not path.exists():
            return ToolResult(success=False, error=f"目录不存在: {path}")

        matches = await asyncio.to_thread(lambda: sorted(str(p) for p in path.glob(pattern)))

        max_results = 200
        truncated = len(matches) > max_results
        if truncated:
            matches = matches[:max_results]

        output = f"匹配 '{pattern}'（共 {len(matches)} 项）:\n" + "\n".join(f"  {m}" for m in matches)
        if truncated:
            output += f"\n  ... 结果过多，已截断"
        return ToolResult(success=True, output=output, data={"count": len(matches)})






