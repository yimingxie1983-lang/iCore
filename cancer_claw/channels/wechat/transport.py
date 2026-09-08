"""微信消息收发封装。"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cancer_claw.channels.wechat.account_store import WechatAccountStore
from cancer_claw.channels.wechat.api import WeixinApiError, WeixinOfficialApi
from cancer_claw.channels.wechat.formatting import format_weixin_text, split_weixin_text
from cancer_claw.channels.wechat.media import (
    build_media_item,
    download_and_decrypt,
    infer_media_type,
    upload_file_to_cdn,
)
from cancer_claw.channels.wechat.paths import inbound_dir

MESSAGE_TYPE_BOT = 2
MESSAGE_STATE_FINISH = 2
TEXT_ITEM = 1
TYPING = 1
TYPING_CANCEL = 2
CHUNK_INTERVAL_S = 3.0
MEDIA_MAX_BYTES = 100 * 1024 * 1024


@dataclass
class InboundAttachment:
    path: Path
    kind: str  # image|file|voice|video
    file_name: str = ""


@dataclass
class InboundEvent:
    account_id: str
    peer_id: str
    message_id: str
    text: str
    context_token: str | None = None
    attachments: list[InboundAttachment] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class WechatTransport:
    def __init__(
        self,
        *,
        account_id: str,
        api: WeixinOfficialApi,
        store: WechatAccountStore,
        chunk_interval_s: float = CHUNK_INTERVAL_S,
    ) -> None:
        self.account_id = account_id
        self.api = api
        self.store = store
        self.chunk_interval_s = chunk_interval_s
        self._send_lock = asyncio.Lock()
        self._last_send_at = 0.0
        self._typing_tickets: dict[str, str] = {}
        self._seen_ids: set[str] = set()

    def client_id(self) -> str:
        return f"icore-weixin-{uuid.uuid4()}"

    async def poll_once(self, sync_cursor: str) -> tuple[str, list[InboundEvent]]:
        resp = await asyncio.to_thread(self.api.get_updates, sync_cursor or "")
        next_cursor = str(resp.get("get_updates_buf") or sync_cursor or "")
        msgs = resp.get("msgs") or []
        events: list[InboundEvent] = []
        for msg in msgs:
            if not isinstance(msg, dict):
                continue
            ev = await self._normalize_message(msg)
            if ev is None:
                continue
            events.append(ev)
        return next_cursor, events

    async def _normalize_message(self, msg: dict[str, Any]) -> InboundEvent | None:
        from_user = str(msg.get("from_user_id") or "")
        if not from_user or from_user == self.account_id:
            return None
        message_id = str(msg.get("message_id") or msg.get("client_id") or uuid.uuid4())
        if message_id in self._seen_ids:
            return None
        self._seen_ids.add(message_id)
        if len(self._seen_ids) > 5000:
            self._seen_ids = set(list(self._seen_ids)[-2000:])

        room_id = str(msg.get("room_id") or msg.get("chat_room_id") or "").strip()
        # 首期仅 DM
        if room_id:
            return None
        peer_id = from_user
        context_token = str(msg.get("context_token") or "") or None
        if context_token:
            self.store.set_context_token(self.account_id, peer_id, context_token)

        texts: list[str] = []
        attachments: list[InboundAttachment] = []
        for item in msg.get("item_list") or []:
            if not isinstance(item, dict):
                continue
            item_type = int(item.get("type") or 0)
            if item_type == 1:
                t = str((item.get("text_item") or {}).get("text") or "").strip()
                if t:
                    texts.append(t)
            elif item_type in (2, 3, 4, 5):
                att = await self._download_item(item, peer_id)
                if att:
                    attachments.append(att)

        text = "\n".join(texts).strip()
        if text == "/" and not attachments:
            return None
        if not text and not attachments:
            return None
        return InboundEvent(
            account_id=self.account_id,
            peer_id=peer_id,
            message_id=message_id,
            text=text,
            context_token=context_token or self.store.get_context_token(self.account_id, peer_id),
            attachments=attachments,
            raw=msg,
        )

    async def _download_item(self, item: dict[str, Any], peer_id: str) -> InboundAttachment | None:
        item_type = int(item.get("type") or 0)
        try:
            if item_type == 2:
                img = item.get("image_item") or {}
                media = img.get("media") or {}
                aes_b64 = ""
                if img.get("aeskey"):
                    import base64

                    aes_b64 = base64.b64encode(str(img["aeskey"]).encode("ascii")).decode("ascii")
                elif media.get("aes_key"):
                    aes_b64 = str(media["aes_key"])
                data = await asyncio.to_thread(
                    download_and_decrypt,
                    encrypted_query_param=str(media.get("encrypt_query_param") or ""),
                    aes_key_b64=aes_b64,
                    cdn_base_url=self.api.cdn_base_url,
                    full_url=str(media.get("full_url") or "") or None,
                )
                if len(data) > MEDIA_MAX_BYTES:
                    return None
                dest = inbound_dir(self.account_id) / f"{int(time.time())}_{peer_id[-6:]}.jpg"
                dest.write_bytes(data)
                return InboundAttachment(path=dest, kind="image", file_name=dest.name)

            if item_type == 4:
                file_item = item.get("file_item") or {}
                media = file_item.get("media") or {}
                data = await asyncio.to_thread(
                    download_and_decrypt,
                    encrypted_query_param=str(media.get("encrypt_query_param") or ""),
                    aes_key_b64=str(media.get("aes_key") or ""),
                    cdn_base_url=self.api.cdn_base_url,
                    full_url=str(media.get("full_url") or "") or None,
                )
                if len(data) > MEDIA_MAX_BYTES:
                    return None
                name = str(file_item.get("file_name") or f"file_{int(time.time())}.bin")
                safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)[:120]
                dest = inbound_dir(self.account_id) / f"{int(time.time())}_{safe}"
                dest.write_bytes(data)
                return InboundAttachment(path=dest, kind="file", file_name=safe)

            if item_type == 3:
                # 语音：先落 silk，不做转码
                voice = item.get("voice_item") or {}
                media = voice.get("media") or {}
                data = await asyncio.to_thread(
                    download_and_decrypt,
                    encrypted_query_param=str(media.get("encrypt_query_param") or ""),
                    aes_key_b64=str(media.get("aes_key") or ""),
                    cdn_base_url=self.api.cdn_base_url,
                    full_url=str(media.get("full_url") or "") or None,
                )
                dest = inbound_dir(self.account_id) / f"{int(time.time())}_{peer_id[-6:]}.silk"
                dest.write_bytes(data)
                return InboundAttachment(path=dest, kind="voice", file_name=dest.name)
        except Exception:
            return None
        return None

    async def ensure_typing_ticket(self, peer_id: str, context_token: str | None) -> str | None:
        cached = self._typing_tickets.get(peer_id)
        if cached:
            return cached
        try:
            resp = await asyncio.to_thread(
                self.api.get_config,
                ilink_user_id=peer_id,
                context_token=context_token,
            )
        except Exception:
            return None
        ticket = str(resp.get("typing_ticket") or "")
        if ticket:
            self._typing_tickets[peer_id] = ticket
        return ticket or None

    async def send_typing(self, peer_id: str, *, start: bool, context_token: str | None = None) -> None:
        ticket = await self.ensure_typing_ticket(peer_id, context_token)
        if not ticket:
            return
        try:
            await asyncio.to_thread(
                self.api.send_typing,
                ilink_user_id=peer_id,
                typing_ticket=ticket,
                status=TYPING if start else TYPING_CANCEL,
            )
        except Exception:
            pass

    async def send_text(self, peer_id: str, content: str, *, context_token: str | None = None) -> None:
        formatted = format_weixin_text(content)
        if not formatted:
            return
        token = context_token or self.store.get_context_token(self.account_id, peer_id)
        chunks = split_weixin_text(formatted)
        for chunk in chunks:
            await self._send_one_text(peer_id, chunk, token)

    async def _send_one_text(self, peer_id: str, text: str, context_token: str | None) -> None:
        async with self._send_lock:
            await self._pace()
            msg = {
                "from_user_id": "",
                "to_user_id": peer_id,
                "client_id": self.client_id(),
                "message_type": MESSAGE_TYPE_BOT,
                "message_state": MESSAGE_STATE_FINISH,
                "item_list": [{"type": TEXT_ITEM, "text_item": {"text": text}}],
            }
            if context_token:
                msg["context_token"] = context_token
            await self._send_with_retry(msg)
            self._last_send_at = time.monotonic()

    async def send_media(
        self,
        peer_id: str,
        file_path: Path,
        *,
        caption: str = "",
        context_token: str | None = None,
    ) -> None:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(str(path))
        token = context_token or self.store.get_context_token(self.account_id, peer_id)
        if not token:
            raise RuntimeError("缺少 context_token，无法发送媒体；请先在微信里发一条消息")
        if caption:
            await self.send_text(peer_id, caption, context_token=token)
        media_type = infer_media_type(path)
        uploaded = await asyncio.to_thread(
            upload_file_to_cdn,
            self.api,
            file_path=path,
            to_user_id=peer_id,
            media_type=media_type,
        )
        item = build_media_item(path, uploaded)
        async with self._send_lock:
            await self._pace()
            msg = {
                "from_user_id": "",
                "to_user_id": peer_id,
                "client_id": self.client_id(),
                "message_type": MESSAGE_TYPE_BOT,
                "message_state": MESSAGE_STATE_FINISH,
                "item_list": [item],
                "context_token": token,
            }
            await self._send_with_retry(msg)
            self._last_send_at = time.monotonic()

    async def _pace(self) -> None:
        elapsed = time.monotonic() - self._last_send_at
        if elapsed < self.chunk_interval_s:
            await asyncio.sleep(self.chunk_interval_s - elapsed)

    async def _send_with_retry(self, msg: dict[str, Any], attempts: int = 4) -> None:
        last_err: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                result = await asyncio.to_thread(self.api.send_message, msg)
                ret = int(result.get("errcode") or result.get("ret") or 0)
                if ret == 0:
                    return
                if ret == -2:
                    await asyncio.sleep(attempt * 5)
                    continue
                if ret == -14:
                    raise WeixinApiError("session expired (-14)", code=-14)
                raise WeixinApiError(f"sendmessage failed: {ret}", code=ret)
            except WeixinApiError as e:
                last_err = e
                if e.code == -2:
                    await asyncio.sleep(attempt * 5)
                    continue
                raise
            except Exception as e:
                last_err = e
                await asyncio.sleep(attempt)
        if last_err:
            raise last_err
