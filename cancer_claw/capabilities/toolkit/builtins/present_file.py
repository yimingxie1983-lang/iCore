

from __future__ import annotations

import json as _json
import mimetypes
from pathlib import Path
from typing import Any

import structlog

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult
from cancer_claw.text_io import decode_text_bytes
from cancer_claw.capabilities.toolkit.workspace import (
    get_tool_workspace,
    resolve_tool_path,
)

logger = structlog.get_logger()

_RENDER_BY_EXT: dict[str, str] = {

    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".webp": "image",
    ".bmp": "image",
    ".svg": "image",

    ".md": "markdown",
    ".markdown": "markdown",

    ".py": "code",
    ".r": "code",
    ".sh": "code",
    ".bash": "code",
    ".js": "code",
    ".ts": "code",
    ".tsx": "code",
    ".jsx": "code",
    ".sql": "code",
    ".yaml": "code",
    ".yml": "code",
    ".toml": "code",
    ".ini": "code",
    ".cfg": "code",

    ".json": "json",

    ".csv": "csv",
    ".tsv": "csv",

    ".pdf": "pdf",

    ".txt": "code",
    ".log": "code",

    ".xlsx": "download",
    ".xls": "download",

    ".zip": "download",
    ".tar": "download",
    ".gz": "download",
    ".7z": "download",
    ".rar": "download",
    ".bin": "download",
    ".db": "download",
    ".sqlite": "download",

    ".bam": "download",
    ".bai": "download",
    ".vcf": "code",
    ".gz": "download",
    ".h5": "download",
    ".h5ad": "download",
    ".rds": "download",
    ".parquet": "download",
    ".feather": "download",
}

_TEXTUAL_RENDER_KINDS = {"markdown", "code", "csv", "json"}

_PREVIEW_HARD_CAP = 4000

_MAX_FILES_PER_CALL = 12

_SENTINEL_OPEN = "<!--CC:PRESENTATION:v1-->"
_SENTINEL_CLOSE = "<!--/CC:PRESENTATION-->"

def _infer_render_kind(path: Path, override: str = "auto") -> str:

    override = (override or "").strip().lower() or "auto"
    if override == "inline":
        override = "code"
    if override in {"image", "markdown", "code", "csv", "json", "pdf", "download"}:
        return override
    if override != "auto":
        logger.warning("present_file_unknown_render_override", override=override)

    ext = path.suffix.lower()
    return _RENDER_BY_EXT.get(ext, "download")

def _guess_mime(path: Path) -> str:

    guess, _ = mimetypes.guess_type(path.name)
    if guess:
        return guess
    ext = path.suffix.lower()
    if ext in {".md", ".markdown"}:
        return "text/markdown"
    if ext in {".csv", ".tsv"}:
        return "text/csv"
    if ext == ".log":
        return "text/plain"
    if ext == ".h5ad":
        return "application/x-hdf5"
    return "application/octet-stream"

def _read_preview_safe(path: Path, max_chars: int = _PREVIEW_HARD_CAP) -> tuple[str, bool]:

    try:

        with path.open("rb") as f:
            raw = f.read(max_chars * 4)
        if not raw:
            return "", False
        text, _enc = decode_text_bytes(raw)
        truncated = path.stat().st_size > len(raw)
        if len(text) > max_chars:
            text = text[:max_chars]
            truncated = True
        return text, truncated
    except OSError as e:
        logger.warning("present_file_preview_read_failed", path=str(path), error=str(e))
        return "", False

def _relative_to_workspace(abs_path: Path) -> str:

    ws = get_tool_workspace()
    if ws is None:

        return str(abs_path)
    try:

        return abs_path.relative_to(ws.project_root).as_posix()
    except ValueError:

        return abs_path.as_posix()

class PresentFileTool(BaseTool):


    @property
    def name(self) -> str:
        return "present_file"

    @property
    def description(self) -> str:
        return (
            "把已在 workspace 里生成的文件**直接展示到对话气泡**供用户预览/下载，"
            "免去用户翻文件系统的麻烦。"
            "\n\n"
            "**何时必须调用此工具**（**强制**触发条件——出现以下任一信号都要立刻调）：\n"
            "1. 用户原话出现交付意图词：『**发给我 / 给我看 / 给我那份 / 给我那张 / "
            "把 X 发我 / 拿过来 / 我要那份 / 我要那张图 / 贴上来 / 直接放对话框 / "
            "现在就要 / 直接给我**』等任一表达\n"
            "2. 用户说『**写完直接发我 / 跑完图给我 / 写一份... 给我 / 整一份... 发我**』"
            "等先做后给的复合指令\n"
            "3. 你写完一份**用户明确点名要的产物**（评分报告、综述 md、KM 曲线、清洗后表、"
            "病例摘要、最终交付文档）—— 此时即使用户没补一句『发我』也应主动调，"
            "因为交付意图在初始 prompt 里已经表达过\n"
            "\n"
            "**绝不要**调用此工具的情况：\n"
            "- 用户没要文件，你只是**内部跑了个脚本**产生中间文件（如临时参数 json、"
            "调试用 .py 脚本、log 文件、缓存中间表）—— 这些是你工程过程，不是交付物\n"
            "- 用户在做**纯对话 / 问答 / 概念解释**，没有任何文件交付意图\n"
            "- 你只是**写了代码**给某个工程内部用 —— 除非用户明确说『把代码发我看一下』\n"
            "- **大量批量文件 / 整个目录** —— 单次最多 12 个，超过先 ask_user 确认要展示哪几份\n"
            "\n"
            "支持的渲染：图片（内联 <img>）/ markdown / 代码（语言高亮）/ CSV/TSV（表格前 N 行）"
            "/ JSON（折叠）/ PDF（嵌入）/ 其它二进制（仅下载按钮）。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "present_file",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "paths": {
                            "description": (
                                "要展示的文件路径（相对项目根的 posix 路径，"
                                "或绝对路径但必须落在项目根之内）。"
                                "可传单个字符串或字符串数组。"
                            ),
                            "oneOf": [
                                {"type": "string"},
                                {"type": "array", "items": {"type": "string"}},
                            ],
                        },
                        "title": {
                            "type": "string",
                            "description": "整组附件的标题（可选，会作为卡片组顶部小标题展示）",
                            "default": "",
                        },
                        "description": {
                            "type": "string",
                            "description": "对附件的简短说明（可选）",
                            "default": "",
                        },
                        "render": {
                            "type": "string",
                            "enum": [
                                "auto",
                                "image",
                                "markdown",
                                "code",
                                "csv",
                                "json",
                                "pdf",
                                "download",
                                "inline",
                            ],
                            "description": (
                                "渲染方式覆盖；auto（默认）按扩展名推断。"
                                "想强制图片用 image、强制 markdown 用 markdown、"
                                "只显示下载按钮用 download。"
                            ),
                            "default": "auto",
                        },
                    },
                    "required": ["paths"],
                },
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        raw_paths = kwargs.get("paths")
        if raw_paths is None:
            return ToolResult(success=False, error="paths 不能为空")


        if isinstance(raw_paths, str):
            path_strs = [s.strip() for s in raw_paths.split(",") if s.strip()]
            if not path_strs:
                path_strs = [raw_paths.strip()]
        elif isinstance(raw_paths, list):
            path_strs = [str(s).strip() for s in raw_paths if str(s).strip()]
        else:
            return ToolResult(
                success=False,
                error=f"paths 应为字符串或字符串数组，收到 {type(raw_paths).__name__}",
            )

        if not path_strs:
            return ToolResult(success=False, error="paths 解析后为空")

        if len(path_strs) > _MAX_FILES_PER_CALL:
            return ToolResult(
                success=False,
                error=(
                    f"单次最多展示 {_MAX_FILES_PER_CALL} 个文件（收到 {len(path_strs)}）。"
                    f"请分多次调用，或精简到最重要的几份。"
                ),
            )

        title = (kwargs.get("title") or "").strip()
        description = (kwargs.get("description") or "").strip()
        render_override = (kwargs.get("render") or "auto").strip().lower()


        files: list[dict[str, Any]] = []
        errors: list[str] = []
        for raw in path_strs:
            abs_path, err = resolve_tool_path(raw)
            if err:
                errors.append(f"{raw}: {err}")
                continue
            if not abs_path.exists():
                errors.append(f"{raw}: 文件不存在（请确认已经写入磁盘）")
                continue
            if abs_path.is_dir():
                errors.append(f"{raw}: 是目录而不是文件（暂不支持展示整个目录）")
                continue

            try:
                size = abs_path.stat().st_size
            except OSError as e:
                errors.append(f"{raw}: 读取大小失败: {e}")
                continue

            render_kind = _infer_render_kind(abs_path, render_override)
            mime = _guess_mime(abs_path)
            rel = _relative_to_workspace(abs_path)

            entry: dict[str, Any] = {
                "name": abs_path.name,
                "path": rel,
                "size": size,
                "mime": mime,
                "render_kind": render_kind,
            }


            if render_kind in _TEXTUAL_RENDER_KINDS and size > 0:
                snippet, truncated = _read_preview_safe(abs_path)
                entry["preview"] = snippet
                entry["preview_truncated"] = truncated

            files.append(entry)

        if not files:
            return ToolResult(
                success=False,
                error="所有文件都无法展示：\n  - " + "\n  - ".join(errors),
            )


        names = ", ".join(f["name"] for f in files)
        output_lines = [
            f"已在对话气泡中展示 {len(files)} 个文件：{names}",
            "用户可直接在前端预览 / 下载，**不要在回复正文里重复 dump 这些文件的全部内容**——",
            "如需引用其中的具体片段，简短引述即可。",
        ]
        if errors:
            output_lines.append("")
            output_lines.append(f"⚠️ {len(errors)} 个路径展示失败：")
            output_lines.extend(f"  - {e}" for e in errors)

        presentation: dict[str, Any] = {
            "kind": "files",
            "files": files,
        }
        if title:
            presentation["title"] = title
        if description:
            presentation["description"] = description




        sentinel_payload = _json.dumps(
            presentation, ensure_ascii=False, separators=(",", ":")
        )
        output_text = (
            "\n".join(output_lines)
            + "\n\n"
            + _SENTINEL_OPEN
            + sentinel_payload
            + _SENTINEL_CLOSE
        )

        return ToolResult(
            success=True,
            output=output_text,
            data={"presentation": presentation},
        )
