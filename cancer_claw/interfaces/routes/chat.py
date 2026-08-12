

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncGenerator

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from cancer_claw.services.identity.deps import (
    compute_project_role,
    get_current_user,
    is_admin,
    require_project_read,
    require_project_runnable,
    require_project_write,
)
from cancer_claw.services.identity import settings_repo
from cancer_claw.services.credits import pricing as billing_pricing
from cancer_claw.services.credits import repo as billing_repo
from cancer_claw.config import settings
from cancer_claw.agent.engine.agent import Agent
from cancer_claw.agent.engine.agent_factory import get_or_create_agent as _factory_get_or_create
from cancer_claw.agent.engine.system_agents import MASTER_AGENT_ID, SYSTEM_AGENT_IDS
from cancer_claw.db import get_db

logger = structlog.get_logger()
router = APIRouter()

class AttachedFileMeta(BaseModel):


    name: str = Field(..., description="文件名（前端展示用）")
    path: str = Field(..., description="相对项目根的 posix 路径")
    size: int = Field(..., ge=0, description="字节数")
    kind: str = Field(
        default="file",
        description="image / file。image 走多模态嵌入 message content 数组",
    )

class ChatRequest(BaseModel):

    message: str = Field(..., min_length=1, description="用户消息")
    agent_id: str | None = Field(None, description="指定智能体 ID，不传则使用默认智能体")
    session_id: str | None = Field(
        default=None,
        description="要继续或恢复的会话 ID；不传时复用 Agent 当前会话或自动新建",
    )
    force_new: bool = Field(
        default=False,
        description="强制新建会话，忽略 Agent 当前的 session_id（前端新对话按钮场景）",
    )
    attached_files: list[AttachedFileMeta] | None = Field(
        default=None,
        description="本轮用户附带的文件（已通过 /uploads 接口上传到 workspace/uploads/）",
    )

class ChatSyncResponse(BaseModel):

    reply: str
    agent_id: str
    agent_name: str
    session_id: str | None = None
    model_calls: int
    tool_calls: int
    total_tokens: int

def _human_size(num_bytes: int) -> str:

    if num_bytes < 0:
        return "?"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    if idx == 0:
        return f"{int(size)} {units[idx]}"
    return f"{size:.1f} {units[idx]}"

def _prepend_attachments(
    message: str,
    files: list[AttachedFileMeta] | None,
) -> str:

    if not files:
        return message

    valid = [
        f for f in files
        if (f.path or "").strip() and (f.name or "").strip()
        and not _is_image_attachment(f)
    ]
    if not valid:
        return message
    lines = ["用户附了以下文件："]
    for f in valid:
        lines.append(f"- {f.name}（{f.path}，{_human_size(f.size)}）")
    return "\n".join(lines) + "\n\n" + message

_IMAGE_EXTS: set[str] = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
}

def _is_image_attachment(meta: AttachedFileMeta) -> bool:

    if (meta.kind or "").lower() == "image":
        return True
    for s in (meta.name, meta.path):
        if not s:
            continue
        lower = s.lower()
        for ext in _IMAGE_EXTS:
            if lower.endswith(ext):
                return True
    return False

_IMAGE_MAX_BYTES: int = 19 * 1024 * 1024

def _guess_image_mime(name: str) -> str:

    lower = (name or "").lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".gif"):
        return "image/gif"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".bmp"):
        return "image/bmp"

    return "image/jpeg"

async def _read_image_to_data_url(
    project_id: str, file_meta: AttachedFileMeta,
) -> str | None:

    import base64

    from cancer_claw.capabilities.toolkit.workspace import get_project_workspace_root

    try:
        ws_root = get_project_workspace_root(project_id)

        rel = (file_meta.path or "").strip().lstrip("/")
        if not rel:
            return None
        abs_path = (ws_root.parent / rel).resolve()

        if not str(abs_path).startswith(str(ws_root.parent.resolve())):
            logger.warning(
                "image_attachment_path_escape",
                project_id=project_id, path=rel,
            )
            return None
        if not abs_path.exists() or not abs_path.is_file():
            logger.warning(
                "image_attachment_missing",
                project_id=project_id, path=rel,
            )
            return None
        size = abs_path.stat().st_size
        if size > _IMAGE_MAX_BYTES:
            logger.warning(
                "image_attachment_too_large",
                project_id=project_id, path=rel, size=size, limit=_IMAGE_MAX_BYTES,
            )
            return None

        def _read_and_encode() -> bytes:
            with abs_path.open("rb") as f:
                return base64.b64encode(f.read())

        b64 = await asyncio.to_thread(_read_and_encode)
        mime = _guess_image_mime(file_meta.name)
        return f"data:{mime};base64,{b64.decode('ascii')}"
    except Exception as e:
        logger.warning(
            "image_attachment_encode_failed",
            project_id=project_id,
            path=getattr(file_meta, "path", "?"),
            error=str(e),
        )
        return None

async def _build_user_content(
    project_id: str,
    text: str,
    files: list[AttachedFileMeta] | None,
) -> str | list[dict]:

    if not files:
        return text
    images = [f for f in files if _is_image_attachment(f)]
    if not images:
        return text


    parts: list[dict] = []
    if text and text.strip():
        parts.append({"type": "text", "text": text})

    success_count = 0
    for img in images:
        data_url = await _read_image_to_data_url(project_id, img)
        if data_url is None:

            parts.append(
                {
                    "type": "text",
                    "text": f"\n[⚠️ 图片附件 {img.name} 读取失败，已忽略]",
                }
            )
            continue
        parts.append({
            "type": "image_url",
            "image_url": {"url": data_url},
        })
        success_count += 1


    if success_count == 0:
        return text




    print(
        f"[chat] 🖼️  打包多模态 content：{len(parts)} 段（text+image）| "
        f"图片 {success_count}/{len(images)} 张成功 base64 化",
        flush=True,
    )
    logger.info(
        "multimodal_content_built",
        project_id=project_id,
        text_len=len(text or ""),
        total_parts=len(parts),
        images_total=len(images),
        images_success=success_count,
    )
    return parts

async def _charge_usage_event(
    *,
    user_id: str,
    project_id: str,
    session_id: str,
    markup: float,
    mode: str,
    flat_credits_per_1m: float,
    flat_output_credits_per_1m: float,
    ev: dict,
) -> None:

    try:
        model = ev.get("model")
        in_tok = int(ev.get("input_tokens", 0) or 0)
        cached = int(ev.get("cached_input_tokens", 0) or 0)
        out_tok = int(ev.get("output_tokens", 0) or 0)
        if in_tok <= 0 and out_tok <= 0:
            return
        credits = billing_pricing.compute_credits(
            model, input_tokens=in_tok, cached_input_tokens=cached,
            output_tokens=out_tok, markup=markup,
            mode=mode, flat_credits_per_1m=flat_credits_per_1m,
            flat_output_credits_per_1m=flat_output_credits_per_1m,
        )
        cost_micro = billing_pricing.compute_cost_micro_cny(
            model, input_tokens=in_tok, cached_input_tokens=cached, output_tokens=out_tok,
        )
        new_balance = await billing_repo.consume(
            user_id, credits,
            cost_micro_cny=cost_micro, model=model,
            session_id=session_id, project_id=project_id,
            input_tokens=in_tok, cached_input_tokens=cached, output_tokens=out_tok,
        )
        ev["credits_charged"] = credits
        ev["credits_balance"] = new_balance
    except Exception as e:
        logger.warning("billing_consume_failed", user_id=user_id, error=str(e))

async def _get_or_create_master_agent() -> Agent:

    return await _factory_get_or_create(MASTER_AGENT_ID)

async def _get_or_create_agent(project_id: str, agent_id: str | None = None) -> Agent:

    try:
        return await _factory_get_or_create(agent_id, project_id=project_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

async def _sse_event_generator(
    agent: Agent,
    message: str | list[dict],
    *,
    prelude_events: list[dict] | None = None,
    project_id: str | None = None,
) -> AsyncGenerator[str, None]:

    session_id: str | None = None



    if prelude_events:
        for ev in prelude_events:
            if ev.get("type") == "session_started":
                session_id = ev.get("session_id")
                break


    if session_id is None:
        session_id = getattr(agent, "_current_session_id", None)



    seq_counter = 0
    if session_id:
        try:
            db = await get_db()
            cur = await db.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM agent_events WHERE session_id = ?",
                (session_id,),
            )
            row = await cur.fetchone()
            seq_counter = int(row[0]) if row else 0
        except Exception:

            seq_counter = 0


    if prelude_events:
        for ev in prelude_events:
            ev_json = json.dumps(ev, ensure_ascii=False, default=str)
            yield f"data: {ev_json}\n\n"
            if session_id:
                seq_counter += 1
                _spawn_persist_event(
                    session_id=session_id,
                    project_id=project_id,
                    agent_id=agent.id,
                    seq=seq_counter,
                    event=ev,
                )


    async for event in agent.chat_stream(message):


        event_json = json.dumps(event, ensure_ascii=False, default=str)
        yield f"data: {event_json}\n\n"


        if session_id:
            seq_counter += 1
            _spawn_persist_event(
                session_id=session_id,
                project_id=project_id,
                agent_id=agent.id,
                seq=seq_counter,
                event=event,
            )

_EVENT_TYPE_DENY_LIST: set[str] = set()

def _spawn_persist_event(
    *,
    session_id: str,
    project_id: str | None,
    agent_id: str,
    seq: int,
    event: dict,
) -> None:

    ev_type = str(event.get("type") or "")
    if not ev_type or ev_type in _EVENT_TYPE_DENY_LIST:
        return
    try:

        import asyncio as _asyncio
        _asyncio.create_task(
            _persist_event(
                session_id=session_id,
                project_id=project_id,
                agent_id=agent_id,
                seq=seq,
                ev_type=ev_type,
                event=event,
            )
        )
    except RuntimeError:

        pass

async def _persist_event(
    *,
    session_id: str,
    project_id: str | None,
    agent_id: str,
    seq: int,
    ev_type: str,
    event: dict,
) -> None:

    import time as _time
    try:
        payload_json = json.dumps(event, ensure_ascii=False, default=str)
        db = await get_db()
        await db.execute(
            "INSERT INTO agent_events "
            "(session_id, project_id, agent_id, seq, type, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, project_id, agent_id, seq, ev_type, payload_json, _time.time()),
        )
        await db.commit()
    except Exception as e:
        import structlog as _structlog
        _structlog.get_logger().warning(
            "agent_event_persist_failed",
            session_id=session_id,
            seq=seq,
            type=ev_type,
            error=str(e),
        )

def _extract_text_for_title(message: str | list[dict] | None) -> str:

    if not message:
        return ""
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        parts: list[str] = []
        for p in message:
            if isinstance(p, dict) and p.get("type") == "text":
                t = p.get("text") or ""
                if isinstance(t, str):
                    parts.append(t)
        return "\n".join(parts)
    return str(message)

async def _resolve_session_for_chat(
    agent: Agent,
    requested_sid: str | None,
    *,
    force_new: bool = False,
    pending_user_message: str | list[dict] = "",
) -> dict[str, Any]:

    final_sid = await agent.start_or_resume_session(
        requested_sid, force_new=force_new,
    )
    from cancer_claw.agent.recall.session_repo import (
        _strip_meta_blocks,
        get_session,
    )

    row = await get_session(final_sid)
    current_title = (row.get("title") if row else "") or ""


    pending_text = _extract_text_for_title(pending_user_message)
    if not current_title.strip() and pending_text.strip():
        stripped = _strip_meta_blocks(pending_text).strip().replace("\n", " ")
        if stripped:
            derived_title = stripped[:30]
            try:
                db = await get_db()

                await db.execute(
                    "INSERT OR IGNORE INTO chat_sessions "
                    "(session_id, project_id, agent_id, title, preview, "
                    " message_count, tool_calls, status) "
                    "VALUES (?, ?, ?, ?, '', 0, 0, 'active')",
                    (
                        final_sid,
                        agent._bound_workspace.project_root.name
                        if agent._bound_workspace else "",
                        agent.id,
                        derived_title,
                    ),
                )


                await db.execute(
                    "UPDATE chat_sessions SET title = ?, "
                    "updated_at = CURRENT_TIMESTAMP "
                    "WHERE session_id = ? AND (title IS NULL OR title = '')",
                    (derived_title, final_sid),
                )
                await db.commit()
                current_title = derived_title

                row = await get_session(final_sid)
            except Exception:

                pass

    if row:
        return {
            "type": "session_started",
            "session_id": final_sid,
            "title": row.get("title") or current_title or "",
            "preview": row.get("preview") or "",
            "message_count": int(row.get("message_count") or 0),
            "status": row.get("status") or "active",
        }
    return {
        "type": "session_started",
        "session_id": final_sid,
        "title": current_title,
        "preview": "",
        "message_count": 0,
        "status": "active",
    }

@router.post("/projects/{project_id}/chat")
async def chat_stream(
    project_id: str,
    body: ChatRequest,
    ctx: dict = Depends(require_project_runnable),
):






    _user = ctx.get("user") if isinstance(ctx, dict) else None
    _user_id = (_user or {}).get("id")
    billing_active = bool(settings.auth.enabled and _user_id and _user_id != "local")
    _billing_markup = 1.0
    _billing_mode = settings_repo.DEFAULT_BILLING_MODE
    _flat_credits_per_1m = float(settings_repo.DEFAULT_FLAT_CREDITS_PER_1M)
    _flat_output_credits_per_1m = float(settings_repo.DEFAULT_FLAT_OUTPUT_CREDITS_PER_1M)
    _billing_enforce = False

    _billing_gate = False
    if billing_active:
        _billing_markup = await settings_repo.get_billing_markup()
        _billing_mode = await settings_repo.get_billing_mode()
        _flat_credits_per_1m = await settings_repo.get_flat_credits_per_1m()
        _flat_output_credits_per_1m = await settings_repo.get_flat_output_credits_per_1m()
        _billing_enforce = await settings_repo.is_billing_enforced()
        _billing_gate = _billing_enforce and not is_admin(_user)

        if _billing_gate:
            _bal = await billing_repo.get_balance(_user_id)
            if _bal <= 0:
                raise HTTPException(
                    status_code=402,
                    detail=f"积分余额不足（当前 {_bal} 积分），请联系管理员充值后再发起对话",
                )


    agent = await _get_or_create_agent(project_id, body.agent_id)


    if body.attached_files:
        _img_n = sum(1 for f in body.attached_files if _is_image_attachment(f))
        _file_n = len(body.attached_files) - _img_n
        print(
            f"[chat] 📥 收到 {len(body.attached_files)} 个附件 | "
            f"图片={_img_n} 普通文件={_file_n} | message={body.message[:80]!r}",
            flush=True,
        )


    text_with_files = _prepend_attachments(body.message, body.attached_files)

    final_message: str | list[dict] = await _build_user_content(
        project_id, text_with_files, body.attached_files,
    )














    from cancer_claw.agent.engine.session_hub import Emitter, get_session_hub
    from cancer_claw.capabilities.toolkit.session_history import _make_session_id





    if body.force_new or not body.session_id:
        final_sid = _make_session_id(agent.id)
    else:
        final_sid = body.session_id


    attachment_metas: list[dict] | None = None
    if body.attached_files:
        attachment_metas = [
            {"name": f.name, "path": f.path, "size": f.size, "kind": f.kind}
            for f in body.attached_files
        ]

    hub = get_session_hub()


    if await hub.is_running(final_sid):
        raise HTTPException(
            status_code=409,
            detail=f"会话 {final_sid} 正在推理中，请等待当前轮完成或刷新页面续看",
        )




    carrier = agent.clone_for_session()

    async def _runner(emitter: Emitter) -> None:

        await carrier.initialize()
        await carrier.prepare()







        await carrier.bind_tool_workspace(project_id)

        carrier._current_user = _user

        session_started_event = await _resolve_session_for_chat(
            carrier,
            final_sid,
            force_new=False,
            pending_user_message=final_message,
        )
        await emitter.emit(session_started_event)
        if attachment_metas:
            carrier._pending_attachment_metas = attachment_metas

        _stream = carrier.chat_stream(final_message)
        _cutoff = False
        async for ev in _stream:


            if billing_active and isinstance(ev, dict) and ev.get("type") == "usage":
                await _charge_usage_event(
                    user_id=_user_id,
                    project_id=project_id,
                    session_id=final_sid,
                    markup=_billing_markup,
                    mode=_billing_mode,
                    flat_credits_per_1m=_flat_credits_per_1m,
                    flat_output_credits_per_1m=_flat_output_credits_per_1m,
                    ev=ev,
                )



                _bal_now = ev.get("credits_balance")
                if (
                    _billing_gate
                    and isinstance(_bal_now, (int, float))
                    and _bal_now <= 0
                ):
                    _cutoff = True
            await emitter.emit(ev)
            if _cutoff:
                await emitter.emit({
                    "type": "notice",
                    "level": "warning",
                    "message": "积分已用尽，本轮对话已自动停止，请联系管理员充值后继续。",
                })
                break
        if _cutoff:

            await _stream.aclose()

    await hub.start(
        final_sid,
        project_id=project_id,
        agent_id=agent.id,
        runner=_runner,
    )

    async def _sse() -> AsyncGenerator[str, None]:

        async for item in hub.subscribe(final_sid, from_seq=0):
            ev = item["event"]
            ev_json = json.dumps(ev, ensure_ascii=False, default=str)
            yield f"data: {ev_json}\n\n"

    return StreamingResponse(
        _sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",

            "X-Session-Id": final_sid,
        },
    )

@router.get("/projects/{project_id}/live_sessions")
async def list_live_sessions(
    project_id: str, _ctx: dict = Depends(require_project_read)
) -> dict:

    from cancer_claw.agent.engine.session_hub import get_session_hub

    return {"running": await get_session_hub().running_session_ids(project_id)}

@router.get("/projects/{project_id}/sessions/{session_id}/live/status")
async def get_session_live_status(
    project_id: str, session_id: str, _ctx: dict = Depends(require_project_read)
) -> dict:

    from cancer_claw.agent.engine.session_hub import get_session_hub

    status = await get_session_hub().get_status(session_id)
    if status is None:
        return {"running": False, "status": "idle", "last_seq": 0}
    return status

@router.post("/projects/{project_id}/sessions/{session_id}/cancel")
async def cancel_session_run(
    project_id: str, session_id: str, _ctx: dict = Depends(require_project_write)
) -> dict:

    from cancer_claw.agent.engine.session_hub import get_session_hub

    hub = get_session_hub()
    status = await hub.get_status(session_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 没有活跃的推理 run")
    if status.get("project_id") and status["project_id"] != project_id:
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不属于项目 {project_id}")
    if status.get("status") != "running":
        return {"ok": True, "cancelled": False, "status": status.get("status")}

    cancelled = await hub.cancel(session_id)
    return {"ok": True, "cancelled": cancelled, "status": "error" if cancelled else status.get("status")}

@router.get("/projects/{project_id}/sessions/{session_id}/live")
async def stream_session_live(
    project_id: str,
    session_id: str,
    from_seq: int = 0,
    _ctx: dict = Depends(require_project_read),
):

    from cancer_claw.agent.engine.session_hub import get_session_hub

    hub = get_session_hub()

    async def _sse() -> AsyncGenerator[str, None]:
        async for item in hub.subscribe(session_id, from_seq=from_seq):
            ev = item["event"]
            ev_json = json.dumps(ev, ensure_ascii=False, default=str)
            yield f"data: {ev_json}\n\n"

    return StreamingResponse(
        _sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@router.post("/chat/sync", response_model=ChatSyncResponse)
async def chat_sync(
    body: ChatRequest,
    project_id: str | None = None,
    user: dict = Depends(get_current_user),
):

    if project_id:

        _project, role = await compute_project_role(user, project_id)
        if _project is None or role is None:
            raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")
        if role == "viewer":
            raise HTTPException(status_code=403, detail="只读成员无写入权限")
        if (_project.get("status") or "active") in ("paused", "frozen"):
            raise HTTPException(status_code=403, detail="项目已暂停或冻结，无法发起新的运行")
        agent = await _get_or_create_agent(project_id, body.agent_id)
    else:

        agent = await _get_or_create_master_agent()


    final_sid = await agent.start_or_resume_session(
        body.session_id, force_new=body.force_new,
    )


    before_calls = agent._model_calls
    before_tools = agent._tool_calls
    before_tokens = agent._total_tokens


    text_with_files = _prepend_attachments(body.message, body.attached_files)
    pid_for_image = project_id or "default"
    final_message: str | list[dict] = await _build_user_content(
        pid_for_image, text_with_files, body.attached_files,
    )


    try:
        reply = await agent.chat(final_message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"对话失败: {str(e)}")

    return ChatSyncResponse(
        reply=reply,
        agent_id=agent.id,
        agent_name=agent.name,
        session_id=final_sid,
        model_calls=agent._model_calls - before_calls,
        tool_calls=agent._tool_calls - before_tools,
        total_tokens=agent._total_tokens - before_tokens,
    )

@router.get("/questions")
async def list_pending_questions(_user: dict = Depends(get_current_user)):

    from cancer_claw.capabilities.toolkit.builtins.ask_user import get_pending_questions
    return {"questions": await get_pending_questions()}

class AnswerRequest(BaseModel):
    answer: str = Field(..., min_length=1, description="用户的回答内容")

@router.post("/questions/{question_id}/answer")
async def submit_question_answer(
    question_id: str, body: AnswerRequest, _user: dict = Depends(get_current_user)
):

    from cancer_claw.capabilities.toolkit.builtins.ask_user import submit_answer
    ok = await submit_answer(question_id, body.answer)
    if not ok:
        raise HTTPException(
            status_code=422,
            detail=f"问题 {question_id} 不存在或已超时过期，请通过 GET /api/questions 查询当前待回答列表",
        )
    return {"ok": True, "question_id": question_id}
