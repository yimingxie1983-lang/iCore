"""微信 Bot 扫码登录。"""

from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

from cancer_claw.channels.wechat.account_store import WechatAccountStore
from cancer_claw.channels.wechat.api import FIXED_QR_BASE_URL, WeixinOfficialApi
from cancer_claw.channels.wechat.paths import runtime_dir

OnQr = Callable[[dict[str, Any]], Awaitable[None] | None]
OnStatus = Callable[[dict[str, Any]], Awaitable[None] | None]


async def official_qr_login(
    *,
    account_store: WechatAccountStore | None = None,
    timeout_seconds: int = 480,
    on_qr: OnQr | None = None,
    on_status: OnStatus | None = None,
    bot_type: str = "3",
) -> dict[str, str] | None:
    store = account_store or WechatAccountStore()
    api = WeixinOfficialApi(base_url=FIXED_QR_BASE_URL, token=None)
    qr_resp = api.get_bot_qr(bot_type=bot_type)
    qrcode = str(qr_resp.get("qrcode") or "")
    if not qrcode:
        return None

    await _emit(on_qr, {
        "qrcode": qrcode,
        "qrcode_img_content": str(qr_resp.get("qrcode_img_content") or ""),
        "raw": qr_resp,
    })

    deadline = asyncio.get_event_loop().time() + timeout_seconds
    current_base = FIXED_QR_BASE_URL
    last_status: str | None = None

    while asyncio.get_event_loop().time() < deadline:
        poll_api = api.with_base_url(current_base)
        try:
            status_resp = await asyncio.to_thread(poll_api.get_qr_status, qrcode)
        except TimeoutError:
            await asyncio.sleep(1)
            continue

        status = str(status_resp.get("status") or "wait")
        if status != last_status:
            last_status = status
            await _emit(on_status, {"status": status, "qrcode": qrcode, "raw": status_resp})

        if status == "scaned_but_redirect":
            host = str(status_resp.get("redirect_host") or "").strip()
            if host:
                current_base = f"https://{host}"
            await asyncio.sleep(1)
            continue

        if status == "expired":
            qr_resp = await asyncio.to_thread(api.get_bot_qr, bot_type)
            qrcode = str(qr_resp.get("qrcode") or "")
            current_base = FIXED_QR_BASE_URL
            await _emit(on_qr, {
                "qrcode": qrcode,
                "qrcode_img_content": str(qr_resp.get("qrcode_img_content") or ""),
                "raw": qr_resp,
            })
            await asyncio.sleep(1)
            continue

        if status == "confirmed":
            account_id = str(status_resp.get("ilink_bot_id") or "")
            token = str(status_resp.get("bot_token") or "")
            base_url = str(status_resp.get("baseurl") or FIXED_QR_BASE_URL)
            user_id = str(status_resp.get("ilink_user_id") or "")
            if not account_id or not token:
                return None
            store.clear_context_tokens(account_id)
            store.save_account(
                account_id=account_id,
                token=token,
                base_url=base_url,
                user_id=user_id,
            )
            return {
                "account_id": account_id,
                "token": token,
                "base_url": base_url,
                "user_id": user_id,
            }

        await asyncio.sleep(1)

    return None


async def _emit(cb: OnQr | OnStatus | None, payload: dict[str, Any]) -> None:
    if cb is None:
        return
    result = cb(payload)
    if asyncio.iscoroutine(result):
        await result


def save_qr_png(
    qrcode_img_content: str,
    dest: Path | None = None,
    *,
    qrcode: str | None = None,
) -> Path | None:
    """把登录二维码落成可扫的 PNG。

    iLink 返回的 qrcode_img_content 常见形态：
    - data:image/...;base64,...  → 直接解码
    - https://...                → 用该 URL 生成二维码图（与 CodexBridge 一致）
    """
    raw = (qrcode_img_content or "").strip()
    path = dest or (runtime_dir() / "login-qr.png")
    path.parent.mkdir(parents=True, exist_ok=True)

    if raw.lower().startswith("data:image/") and "," in raw:
        try:
            b64 = raw.split(",", 1)[1]
            data = base64.b64decode(b64)
            if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:2] == b"\xff\xd8":
                path.write_bytes(data)
                return path
        except Exception:
            pass

    payload = ""
    if raw.lower().startswith("http://") or raw.lower().startswith("https://"):
        payload = raw
    elif qrcode:
        # 兜底：部分环境只给 qrcode id，仍尝试生成可扫图（通常不如 URL）
        payload = raw or qrcode

    if not payload:
        return None

    try:
        import qrcode
    except ImportError as e:
        raise RuntimeError("需要 qrcode 库：pip install 'qrcode[pil]'") from e

    img = qrcode.make(payload)
    img.save(path)
    return path if path.is_file() and path.stat().st_size > 100 else None


def print_qr_hint(qrcode: str, png_path: Path | None, source_url: str | None = None) -> None:
    print("请使用微信扫描二维码登录 iCore 微信助手。", file=sys.stderr)
    if png_path and png_path.is_file():
        print(f"二维码已保存: {png_path}", file=sys.stderr)
    if source_url:
        print(f"也可在浏览器打开该链接辅助确认: {source_url}", file=sys.stderr)
    if qrcode:
        print(f"qrcode={qrcode[:32]}…", file=sys.stderr)
