

from __future__ import annotations

import csv as _csv
import io
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import quote

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from cancer_claw.services.identity.deps import require_project_read
from cancer_claw.config import settings
from cancer_claw.db import get_db
from cancer_claw.text_io import decode_text_bytes, encoding_for_text_open
from cancer_claw.capabilities.toolkit.workspace import _is_descendant

logger = structlog.get_logger()
router = APIRouter()

_TEXT_PREVIEW_HARD_CAP = 200_000

_CSV_DEFAULT_ROWS = 200
_CSV_MAX_ROWS = 2000

_RAW_MAX_BYTES = 500 * 1024 * 1024

_TEXT_MIME_NEEDS_CHARSET: frozenset[str] = frozenset({
    "application/json",
    "application/xml",
    "application/javascript",
    "image/svg+xml",
})

async def _assert_project_exists(project_id: str) -> None:
    db = await get_db()
    cur = await db.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
    if not await cur.fetchone():
        raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")

def _project_root(project_id: str) -> Path:

    projects_dir = Path(settings.paths.projects_dir).expanduser()
    if not projects_dir.is_absolute():
        projects_dir = (Path.cwd() / projects_dir).resolve()
    else:
        projects_dir = projects_dir.resolve()
    return (projects_dir / project_id).resolve()

def _resolve_safe_file(project_id: str, raw_path: str) -> Path:

    raw = (raw_path or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="path 不能为空")

    root = _project_root(project_id)
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"项目目录不存在: {project_id}")

    candidate = Path(raw)
    target = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()

    if not _is_descendant(target, root):
        logger.warning(
            "files_path_escape_blocked",
            project_id=project_id,
            requested=raw,
        )
        raise HTTPException(status_code=400, detail="路径越界，仅允许访问项目根目录之下的文件")

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {raw}")
    if not target.is_file():
        raise HTTPException(status_code=400, detail=f"路径不是文件: {raw}")

    return target

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
    return "application/octet-stream"

def _content_disposition(disposition: str, filename: str) -> str:


    ascii_chars = []
    for ch in filename:
        ascii_chars.append(ch if ord(ch) < 128 else "_")
    ascii_fallback = "".join(ascii_chars) or "file"

    ascii_fallback = ascii_fallback.replace("\\", "\\\\").replace('"', '\\"')

    rfc5987 = quote(filename, safe="")
    return (
        f'{disposition}; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{rfc5987}"
    )

class FilePreviewText(BaseModel):


    kind: str = "text"
    path: str
    size: int
    mime: str
    text: str
    truncated: bool
    encoding: str = "utf-8"

class FilePreviewCsv(BaseModel):


    kind: str = "csv"
    path: str
    size: int
    mime: str
    columns: list[str]
    rows: list[list[str]]
    truncated: bool
    total_rows_returned: int
    delimiter: str = ","

@router.get(
    "/projects/{project_id}/files/raw",
    tags=["项目文件"],
    summary="二进制返回项目内任意文件（图片/PDF/Excel/二进制下载）",
)
async def get_raw_file(
    project_id: str,
    path: str = Query(..., description="项目根之下的文件路径（posix）"),
    download: bool = Query(default=False, description="true=强制 attachment 下载；false=inline"),
    _ctx: dict = Depends(require_project_read),
):

    await _assert_project_exists(project_id)
    target = _resolve_safe_file(project_id, path)

    size = target.stat().st_size
    if size > _RAW_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"文件过大（{size} bytes，上限 {_RAW_MAX_BYTES}），"
                f"为避免浏览器卡死不提供 HTTP 下载。请通过文件系统直接获取。"
            ),
        )

    mime = _guess_mime(target)


    if (mime.startswith("text/") or mime in _TEXT_MIME_NEEDS_CHARSET) and "charset" not in mime:
        mime = f"{mime}; charset=utf-8"
    disposition = "attachment" if download else "inline"
    headers = {
        "Content-Disposition": _content_disposition(disposition, target.name),
    }
    return FileResponse(
        path=str(target),
        media_type=mime,
        headers=headers,
    )

@router.get(
    "/projects/{project_id}/files/preview",
    tags=["项目文件"],
    summary="结构化预览（text 截断字符串 / csv 解析前 N 行）",
)
async def preview_file(
    project_id: str,
    path: str = Query(..., description="项目根之下的文件路径（posix）"),
    max_lines: int = Query(
        default=_CSV_DEFAULT_ROWS,
        ge=1,
        le=_CSV_MAX_ROWS,
        description="csv 模式下返回的最大行数；text 模式忽略（统一按字符截断）",
    ),
    _ctx: dict = Depends(require_project_read),
):

    await _assert_project_exists(project_id)
    target = _resolve_safe_file(project_id, path)

    mime = _guess_mime(target)
    ext = target.suffix.lower()
    size = target.stat().st_size

    if ext in {".csv", ".tsv"}:
        delimiter = "," if ext == ".csv" else "\t"
        return JSONResponse(_preview_csv(target, mime, size, delimiter, max_lines))


    if _looks_binary(target):
        raise HTTPException(
            status_code=400,
            detail=(
                "该文件看起来是二进制，无法做文本预览；请走 /files/raw 直接获取/下载。"
            ),
        )

    return JSONResponse(_preview_text(target, mime, size))

def _preview_text(path: Path, mime: str, size: int) -> dict[str, Any]:

    encoding = "utf-8"
    text = ""
    truncated = False
    try:
        with path.open("rb") as f:
            raw = f.read(_TEXT_PREVIEW_HARD_CAP * 4)
        text, encoding = decode_text_bytes(raw)
        truncated = size > len(raw) or len(text) > _TEXT_PREVIEW_HARD_CAP
        if len(text) > _TEXT_PREVIEW_HARD_CAP:
            text = text[:_TEXT_PREVIEW_HARD_CAP]
    except OSError as e:
        logger.warning("preview_text_failed", path=str(path), error=str(e))
        raise HTTPException(status_code=500, detail=f"读取失败: {e}") from e

    return {
        "kind": "text",
        "path": path.name,
        "size": size,
        "mime": mime,
        "text": text,
        "truncated": truncated,
        "encoding": encoding,
    }

def _preview_csv(
    path: Path,
    mime: str,
    size: int,
    delimiter: str,
    max_rows: int,
) -> dict[str, Any]:

    columns: list[str] = []
    rows: list[list[str]] = []
    truncated = False
    try:
        with path.open("rb") as bf:
            sample = bf.read(65536)
        enc = encoding_for_text_open(sample)

        with path.open("r", encoding=enc, newline="", errors="replace") as f:
            reader = _csv.reader(f, delimiter=delimiter)
            for i, row in enumerate(reader):
                if i == 0:
                    columns = [str(c) for c in row]
                    continue
                if len(rows) >= max_rows:
                    truncated = True
                    break
                rows.append([str(c) for c in row])
    except OSError as e:
        logger.warning("preview_csv_failed", path=str(path), error=str(e))
        raise HTTPException(status_code=500, detail=f"读取失败: {e}") from e

    return {
        "kind": "csv",
        "path": path.name,
        "size": size,
        "mime": mime,
        "columns": columns,
        "rows": rows,
        "truncated": truncated,
        "total_rows_returned": len(rows),
        "delimiter": delimiter,
    }

def _looks_binary(path: Path, sniff_bytes: int = 4096) -> bool:

    try:
        with path.open("rb") as f:
            chunk = f.read(sniff_bytes)
    except OSError:
        return True
    if not chunk:
        return False

    if b"\x00" in chunk:
        return True

    text_chars = bytes(range(0x20, 0x7F)) + b"\r\n\t\b\f"
    nontext = sum(1 for b in chunk if b not in text_chars and b < 0x80)
    return (nontext / len(chunk)) > 0.30
