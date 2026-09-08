from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import BinaryIO, Literal

import mimetypes
import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from cancer_claw.capabilities.toolkit.workspace import _is_descendant, get_project_workspace_root
from cancer_claw.config import settings
from cancer_claw.db import get_db
from cancer_claw.services.identity.deps import require_project_read, require_project_write
from cancer_claw.services.privacy.desensitizer import (
    desensitize_file,
    is_textual_upload,
    summarize_hits_zh,
)

logger = structlog.get_logger()
router = APIRouter()

CHUNK_SIZE = 1 << 20

_BAD_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


class UploadAttachmentResp(BaseModel):
    name: str = Field(..., description="客户端原文件名（已 sanitize）")
    path: str = Field(
        ...,
        description="文件相对项目根的 posix 路径，如 'workspace/uploads/1700000000000_foo.csv'",
    )
    size: int = Field(..., description="实际落盘字节数")
    status: Literal["ok", "privacy_review"] = Field(
        "ok",
        description="ok=已完成；privacy_review=检测到敏感信息，等待用户确认是否脱敏/取消",
    )
    privacy_hits: dict[str, int] = Field(
        default_factory=dict, description="敏感类型命中统计（仅 privacy_review）"
    )
    privacy_total: int = Field(0, description="敏感命中总数")
    message: str = Field("", description="面向用户的提示文案")


class UploadPrivacyConfirmReq(BaseModel):
    path: str = Field(..., description="待确认文件的相对项目根路径")
    action: Literal["desensitize", "keep", "abort"] = Field(
        ...,
        description="desensitize=脱敏后保留；keep=不脱敏保留；abort=取消并删除",
    )


def _sanitize_filename(raw: str) -> str:
    name = (raw or "").strip().replace("\\", "/").split("/")[-1]
    name = name.replace("..", "_")
    name = _BAD_NAME_CHARS.sub("_", name)
    name = name.strip(" .")
    if not name or not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", name):
        return "unnamed"
    return name


async def _assert_project_exists(project_id: str) -> None:
    db = await get_db()
    cur = await db.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
    if not await cur.fetchone():
        raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")


def _write_chunks_sync(src_file: BinaryIO, dest: Path, chunk_size: int) -> int:
    written = 0
    with open(dest, "wb") as out:
        while True:
            chunk = src_file.read(chunk_size)
            if not chunk:
                break
            out.write(chunk)
            written += len(chunk)
    return written


def _resolve_upload_target(project_id: str, raw_path: str) -> tuple[Path, Path, str]:
    """返回 (target, uploads_dir, rel_path)。越界则抛 400。"""
    ws_root = get_project_workspace_root(project_id)
    uploads_dir = (ws_root / "uploads").resolve()
    raw = (raw_path or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="path 不能为空")
    candidate = Path(raw)
    if candidate.is_absolute():
        target = candidate.resolve()
    else:
        target = (ws_root.parent / candidate).resolve()
    if not _is_descendant(target, uploads_dir):
        raise HTTPException(
            status_code=400, detail="路径越界，仅允许操作 workspace/uploads/ 下的文件"
        )
    rel_path = target.relative_to(ws_root.parent).as_posix()
    return target, uploads_dir, rel_path


@router.post(
    "/projects/{project_id}/uploads",
    response_model=UploadAttachmentResp,
    tags=["附件"],
)
async def upload_attachment(
    project_id: str,
    file: UploadFile = File(..., description="任意类型文件，单次一文件"),
    _ctx: dict = Depends(require_project_write),
) -> UploadAttachmentResp:
    """上传附件。若启用上传脱敏且检出敏感信息，返回 privacy_review，不自动脱敏。"""
    await _assert_project_exists(project_id)

    if file is None or not file.filename:
        raise HTTPException(status_code=400, detail="未收到文件或文件名为空")

    ws_root = get_project_workspace_root(project_id)
    uploads_dir = ws_root / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _sanitize_filename(file.filename)
    ts_ms = int(time.time() * 1000)
    dest = (uploads_dir / f"{ts_ms}_{safe_name}").resolve()

    if not _is_descendant(dest, uploads_dir.resolve()):
        logger.warning(
            "upload_path_escape_blocked",
            project_id=project_id,
            raw=file.filename,
            sanitized=safe_name,
        )
        raise HTTPException(status_code=400, detail="非法文件名（路径越界）")

    try:
        written = await asyncio.to_thread(
            _write_chunks_sync, file.file, dest, CHUNK_SIZE
        )
    except Exception as e:
        try:
            if dest.exists():
                dest.unlink()
        except Exception:
            pass
        logger.warning(
            "upload_write_failed",
            project_id=project_id,
            filename=file.filename,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"写盘失败: {e}") from e
    finally:
        await file.close()

    rel_path = dest.relative_to(ws_root.parent).as_posix()
    privacy = settings.privacy
    # 不在上传热路径上做全量排查：文本/Office/DICOM 先提示用户，脱敏仅在确认后执行
    ask_privacy = (
        bool(privacy.enabled)
        and privacy.mode != "off"
        and bool(privacy.desensitize_on_upload)
        and is_textual_upload(safe_name)
    )

    if ask_privacy:
        msg = (
            "该文件可能包含身份证、手机号、病历号等敏感信息。"
            "请确认是否继续上传；若继续，请选择是否脱敏后保留。"
        )
        logger.info(
            "upload_privacy_review",
            project_id=project_id,
            path=rel_path,
            deferred_scan=True,
        )
        return UploadAttachmentResp(
            name=safe_name,
            path=rel_path,
            size=written,
            status="privacy_review",
            privacy_hits={},
            privacy_total=0,
            message=msg,
        )

    logger.info(
        "upload_attachment_ok",
        project_id=project_id,
        name=safe_name,
        path=rel_path,
        size=written,
    )
    return UploadAttachmentResp(name=safe_name, path=rel_path, size=written)


@router.post(
    "/projects/{project_id}/uploads/privacy",
    response_model=UploadAttachmentResp,
    tags=["附件"],
)
async def confirm_upload_privacy(
    project_id: str,
    body: UploadPrivacyConfirmReq,
    _ctx: dict = Depends(require_project_write),
) -> UploadAttachmentResp:
    """对 privacy_review 状态的上传做最终确认：脱敏 / 保留原文 / 取消删除。"""
    await _assert_project_exists(project_id)
    target, _uploads_dir, rel_path = _resolve_upload_target(project_id, body.path)

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在或已删除")

    safe_name = target.name.split("_", 1)[-1] if "_" in target.name else target.name
    size = target.stat().st_size

    if body.action == "abort":
        try:
            target.unlink()
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"删除失败: {e}") from e
        logger.info(
            "upload_privacy_aborted",
            project_id=project_id,
            path=rel_path,
        )
        return UploadAttachmentResp(
            name=safe_name,
            path=rel_path,
            size=0,
            status="ok",
            message="已取消上传并删除文件",
        )

    if body.action == "desensitize":
        try:
            result = await asyncio.to_thread(
                desensitize_file,
                target,
                context=f"upload_confirm:{project_id}",
                force=True,
            )
            if result.changed:
                size = target.stat().st_size
            logger.info(
                "upload_desensitized",
                project_id=project_id,
                path=rel_path,
                hits=result.hits,
                changed=result.changed,
            )
            summary = summarize_hits_zh(result.hits) if result.hits else ""
            return UploadAttachmentResp(
                name=safe_name,
                path=rel_path,
                size=size,
                status="ok",
                privacy_hits=dict(result.hits),
                privacy_total=result.total_hits,
                message=(
                    f"已脱敏并保留（{summary}）" if summary else "已按确认完成脱敏并保留"
                ),
            )
        except Exception as e:
            logger.warning(
                "upload_desensitize_failed",
                project_id=project_id,
                path=rel_path,
                error=str(e),
            )
            raise HTTPException(status_code=500, detail=f"脱敏失败: {e}") from e

    # keep — 不脱敏
    logger.info(
        "upload_privacy_kept_raw",
        project_id=project_id,
        path=rel_path,
    )
    return UploadAttachmentResp(
        name=safe_name,
        path=rel_path,
        size=size,
        status="ok",
        message="已保留原文件（未脱敏）",
    )


@router.delete("/projects/{project_id}/uploads", tags=["附件"])
async def delete_attachment(
    project_id: str,
    path: str = Query(..., description="待删除文件的相对项目根路径，如 workspace/uploads/xxx"),
    _ctx: dict = Depends(require_project_write),
) -> dict:
    await _assert_project_exists(project_id)
    target, _uploads_dir, raw = _resolve_upload_target(project_id, path)

    if target.exists():
        try:
            target.unlink()
        except OSError as e:
            logger.warning(
                "delete_attachment_failed",
                project_id=project_id,
                path=raw,
                error=str(e),
            )
            raise HTTPException(status_code=500, detail=f"删除失败: {e}") from e

    logger.info("delete_attachment_ok", project_id=project_id, path=raw)
    return {"ok": True, "path": raw}


@router.get(
    "/projects/{project_id}/files/{file_path:path}",
    tags=["文件资源"],
    summary="安全读取项目工作区内的文件（图片 / 附件等）",
)
async def serve_project_file(
    project_id: str, file_path: str, _ctx: dict = Depends(require_project_read)
):
    await _assert_project_exists(project_id)

    raw = (file_path or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="文件路径不能为空")

    if raw.startswith("/") or raw.startswith("\\") or (len(raw) >= 2 and raw[1] == ":"):
        raise HTTPException(status_code=400, detail="不允许使用绝对路径")

    ws_root = get_project_workspace_root(project_id)
    target = (ws_root.parent / raw).resolve()

    if not _is_descendant(target, ws_root):
        logger.warning(
            "file_serve_path_escape",
            project_id=project_id,
            requested=raw,
            resolved=str(target),
        )
        raise HTTPException(status_code=403, detail="路径越界：只能访问 workspace 下的文件")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(
        path=str(target),
        media_type=media_type,
        filename=target.name,
    )
