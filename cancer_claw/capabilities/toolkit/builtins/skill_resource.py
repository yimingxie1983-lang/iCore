

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import structlog

from cancer_claw.config import settings
from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult
from cancer_claw.capabilities.toolkit.workspace import get_tool_workspace

logger = structlog.get_logger()

def _get_scan_roots() -> list[Path]:

    roots: list[Path] = []
    for raw in settings.skills.scan_paths:
        p = Path(raw)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        else:
            p = p.resolve()
        if p.is_dir():
            roots.append(p)
    return roots

def _resolve_skill_dir(skill_id: str) -> Path | None:

    from cancer_claw.resources.knowledge.skill_loader import get_skill

    rec = get_skill(skill_id)
    if rec is None:
        return None

    source_file = (rec.skill_compat or {}).get("source_file")
    if source_file:
        p = Path(source_file)
        if p.is_file():
            return p.parent

    return None

def _resolve_skill_resource_path(skill_dir: Path, resource_path: str) -> tuple[Path | None, str | None]:

    if not resource_path or resource_path.strip() in ("", "."):
        return skill_dir, None

    candidate = (skill_dir / resource_path).resolve()


    for root in _get_scan_roots():
        try:
            candidate.relative_to(root)
            return candidate, None
        except ValueError:
            continue

    return None, f"路径越界: {resource_path} 不在 Skill 扫描目录内"

def _list_dir_tree(base: Path, max_depth: int = 3, _depth: int = 0) -> list[dict]:

    items = []
    if not base.is_dir() or _depth > max_depth:
        return items

    try:
        for child in sorted(base.iterdir()):
            if child.name.startswith("."):
                continue
            entry = {
                "name": child.name,
                "type": "dir" if child.is_dir() else "file",
                "path": str(child.relative_to(base.parent.parent if _depth == 0 else base)),
            }
            if child.is_file():
                entry["size"] = child.stat().st_size
            if child.is_dir():
                entry["children"] = _list_dir_tree(child, max_depth, _depth + 1)
            items.append(entry)
    except PermissionError:
        pass

    return items

def _get_workspace_skill_dir() -> Path | None:

    ws = get_tool_workspace()
    if ws is None:
        return None
    target = ws.default_relative_root / ".skill_scripts"
    target.mkdir(parents=True, exist_ok=True)
    return target

class SkillResourceTool(BaseTool):


    @property
    def name(self) -> str:
        return "skill_resource"

    @property
    def description(self) -> str:
        return (
            "访问 Skill 自带的参考脚本和资源文件（examples/*.py、usage-guide.md 等）。\n\n"
            "**使用场景**：activate_craft 激活 Skill 后，想查看/执行它自带的参考脚本时用本工具。\n"
            "**安全边界**：只读访问 Skill 扫描目录，写入仅限 workspace/.skill_scripts/。\n\n"
            "**action 列表**：\n"
            "  list              — 列出 Skill 目录结构\n"
            "  read              — 读取某个资源文件内容\n"
            "  copy_to_workspace — 拷贝到 workspace 供修改执行\n"
            "  exec              — 拷贝并立即执行 Python 脚本"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "skill_resource",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["list", "read", "copy_to_workspace", "exec"],
                            "description": (
                                "list — 列出 Skill 目录结构；"
                                "read — 读取资源文件内容；"
                                "copy_to_workspace — 拷贝到 workspace；"
                                "exec — 拷贝并执行"
                            ),
                        },
                        "skill_id": {
                            "type": "string",
                            "description": (
                                "Skill 的 id（如 skill_bio-alignment-io）。"
                                "来自 craft_search 的搜索结果或 L1 listing。"
                            ),
                        },
                        "path": {
                            "type": "string",
                            "description": (
                                "资源文件的相对路径（相对于 SKILL.md 所在目录）。"
                                "list 时可省略（列出根目录）；"
                                "read/copy_to_workspace/exec 时必填。"
                                "示例：'examples/convert_formats.py'、'usage-guide.md'"
                            ),
                            "default": "",
                        },
                        "args": {
                            "type": "string",
                            "description": (
                                "exec 时传给 Python 脚本的命令行参数（可选）。"
                                "示例：'input.aln output.fasta clustal'"
                            ),
                            "default": "",
                        },
                    },
                    "required": ["action", "skill_id"],
                },
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        action = (kwargs.get("action") or "").strip()
        skill_id = (kwargs.get("skill_id") or "").strip()
        path = (kwargs.get("path") or "").strip()
        args = (kwargs.get("args") or "").strip()

        if not skill_id:
            return ToolResult(success=False, error="skill_id 不能为空")


        skill_dir = _resolve_skill_dir(skill_id)
        if skill_dir is None:
            return ToolResult(
                success=False,
                error=f"找不到 Skill: {skill_id}。请先用 craft_search 确认 id 正确。",
            )

        if action == "list":
            return await self._list(skill_dir, path)
        elif action == "read":
            return await self._read(skill_dir, path)
        elif action == "copy_to_workspace":
            return await self._copy(skill_dir, skill_id, path)
        elif action == "exec":
            return await self._exec(skill_dir, skill_id, path, args, kwargs)
        else:
            return ToolResult(success=False, error=f"不支持的 action: {action}")

    async def _list(self, skill_dir: Path, path: str) -> ToolResult:

        target_dir = skill_dir
        if path:
            resolved, err = _resolve_skill_resource_path(skill_dir, path)
            if err:
                return ToolResult(success=False, error=err)
            target_dir = resolved

        if not target_dir.is_dir():
            return ToolResult(success=False, error=f"目录不存在: {path or '.'}")

        items = _list_dir_tree(target_dir)


        lines = [f"**Skill 目录**: `{skill_dir.name}/`", ""]

        def _render(items: list[dict], indent: int = 0):
            for it in items:
                prefix = "  " * indent
                if it["type"] == "dir":
                    lines.append(f"{prefix}📁 {it['name']}/")
                    if it.get("children"):
                        _render(it["children"], indent + 1)
                else:
                    size = it.get("size", 0)
                    size_str = f"{size}B" if size < 1024 else f"{size / 1024:.1f}KB"
                    lines.append(f"{prefix}📄 {it['name']}  ({size_str})")

        _render(items)


        parent = skill_dir.parent
        parent_extras = []
        if parent.is_dir():
            for p in sorted(parent.iterdir()):
                if p == skill_dir or p.name.startswith("."):
                    continue
                if p.is_file() and p.suffix in (".py", ".sh", ".md"):
                    parent_extras.append(f"📄 ../{p.name}")
                elif p.is_dir() and p.name in ("examples", "scripts"):
                    parent_extras.append(f"📁 ../{p.name}/")

        if parent_extras:
            lines.extend(["", "_父级分类目录也有可用资源：_"])
            lines.extend(f"  {x}" for x in parent_extras)

        return ToolResult(
            success=True,
            output="\n".join(lines),
            data={"skill_dir": str(skill_dir), "items": items},
        )

    async def _read(self, skill_dir: Path, path: str) -> ToolResult:

        if not path:
            return ToolResult(success=False, error="read 需要 path 参数")

        resolved, err = _resolve_skill_resource_path(skill_dir, path)
        if err:
            return ToolResult(success=False, error=err)

        if not resolved.is_file():

            parent_resolved = (skill_dir.parent / path).resolve()
            for root in _get_scan_roots():
                try:
                    parent_resolved.relative_to(root)
                    if parent_resolved.is_file():
                        resolved = parent_resolved
                        break
                except ValueError:
                    continue
            else:
                return ToolResult(success=False, error=f"文件不存在: {path}")


        if resolved.suffix.lower() in (".gz", ".bam", ".bai", ".pdf", ".png", ".jpg", ".zip"):
            size = resolved.stat().st_size
            return ToolResult(
                success=True,
                output=f"二进制文件: {resolved.name} ({size} bytes)，不支持直接读取。用 copy_to_workspace 拷贝后处理。",
                data={"path": str(resolved), "size": size, "binary": True},
            )


        max_chars = 50_000
        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return ToolResult(success=False, error=f"读取失败: {e}")

        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars] + "\n\n… [文件过长，已截断。用 copy_to_workspace 拷贝完整文件]"

        output = f"**`{path}`** ({len(text)} chars)\n```\n{text}\n```"

        return ToolResult(
            success=True,
            output=output,
            data={
                "path": str(resolved),
                "size": resolved.stat().st_size,
                "truncated": truncated,
            },
        )

    async def _copy(self, skill_dir: Path, skill_id: str, path: str) -> ToolResult:

        if not path:
            return ToolResult(success=False, error="copy_to_workspace 需要 path 参数")

        resolved, err = _resolve_skill_resource_path(skill_dir, path)
        if err:
            return ToolResult(success=False, error=err)

        if not resolved.is_file():

            parent_resolved = (skill_dir.parent / path).resolve()
            for root in _get_scan_roots():
                try:
                    parent_resolved.relative_to(root)
                    if parent_resolved.is_file():
                        resolved = parent_resolved
                        break
                except ValueError:
                    continue
            else:
                return ToolResult(success=False, error=f"文件不存在: {path}")

        target_root = _get_workspace_skill_dir()
        if target_root is None:
            return ToolResult(success=False, error="未绑定项目工作区，无法拷贝")



        clean_id = skill_id.replace("skill_", "", 1)
        target = target_root / clean_id / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(resolved), str(target))


        ws = get_tool_workspace()
        try:
            rel = target.relative_to(ws.default_relative_root)
            rel_str = str(rel).replace("\\", "/")
        except ValueError:
            rel_str = str(target)

        return ToolResult(
            success=True,
            output=f"已拷贝到 workspace: `{rel_str}`\n可用 file_ops 编辑或 code_exec 执行。",
            data={
                "source": str(resolved),
                "target": str(target),
                "workspace_path": rel_str,
            },
        )

    async def _exec(
        self, skill_dir: Path, skill_id: str, path: str, args: str, kwargs: dict
    ) -> ToolResult:

        if not path:
            return ToolResult(success=False, error="exec 需要 path 参数")

        if not path.endswith(".py"):
            return ToolResult(success=False, error="exec 仅支持 .py 文件")


        copy_result = await self._copy(skill_dir, skill_id, path)
        if not copy_result.success:
            return copy_result

        target_path = copy_result.data.get("target", "")
        if not target_path:
            return ToolResult(success=False, error="拷贝成功但目标路径为空")


        try:
            script = Path(target_path).read_text(encoding="utf-8")
        except Exception as e:
            return ToolResult(success=False, error=f"读取拷贝后的脚本失败: {e}")


        if args:
            argv_line = f"import sys; sys.argv = ['script.py'] + {repr(args.split())}\n"
            script = argv_line + script


        from cancer_claw.capabilities.toolkit.registry import get_registry
        registry = get_registry()
        code_exec = registry.get_tool("code_exec")
        if code_exec is None:
            return ToolResult(
                success=False,
                error="code_exec 工具未注册，无法执行脚本。请用 copy_to_workspace 手动拷贝后执行。",
            )

        exec_result = await code_exec.run(
            language="python",
            code=script,
            timeout=kwargs.get("timeout", 60),
        )

        workspace_path = copy_result.data.get("workspace_path", path)
        if exec_result.success:
            output = (
                f"**执行 `{workspace_path}`** 成功\n"
                f"{exec_result.output}"
            )
        else:
            output = (
                f"**执行 `{workspace_path}`** 失败\n"
                f"脚本已拷贝到: `{workspace_path}`，可手动修改后重新执行。\n"
                f"错误: {exec_result.error}"
            )

        return ToolResult(
            success=exec_result.success,
            output=output,
            data={
                **copy_result.data,
                "exec_success": exec_result.success,
                "exec_output": exec_result.output,
                "exec_error": exec_result.error,
            },
            error=exec_result.error,
        )
