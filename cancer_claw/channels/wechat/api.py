"""微信 iLink Bot HTTP API。"""

from __future__ import annotations

import base64
import json
import random
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

ILINK_APP_ID = "bot"
ILINK_APP_CLIENT_VERSION = (2 << 16) | (2 << 8) | 0
DEFAULT_CHANNEL_VERSION = "2.2.0"
FIXED_QR_BASE_URL = "https://ilinkai.weixin.qq.com"
DEFAULT_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
DEFAULT_LONG_POLL_TIMEOUT_MS = 35_000
DEFAULT_API_TIMEOUT_MS = 15_000


def build_base_info(channel_version: str = DEFAULT_CHANNEL_VERSION) -> dict[str, str]:
    return {"channel_version": channel_version}


def _random_wechat_uin() -> str:
    value = random.randint(0, 0xFFFFFFFF)
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def build_headers(
    *,
    token: str | None = None,
    authorized: bool = True,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    headers = {
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
        "X-WECHAT-UIN": _random_wechat_uin(),
    }
    if extra:
        headers.update(extra)
    if authorized and token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def join_url(base_url: str, endpoint: str) -> str:
    return f"{str(base_url).rstrip('/')}/{str(endpoint).lstrip('/')}"


class WeixinApiError(RuntimeError):
    def __init__(self, message: str, *, code: int = 0) -> None:
        super().__init__(message)
        self.code = code


class WeixinOfficialApi:
    def __init__(
        self,
        *,
        base_url: str = FIXED_QR_BASE_URL,
        token: str | None = None,
        timeout_ms: int = DEFAULT_API_TIMEOUT_MS,
        cdn_base_url: str = DEFAULT_CDN_BASE_URL,
    ) -> None:
        self.base_url = (base_url or FIXED_QR_BASE_URL).rstrip("/")
        self.token = token
        self.timeout_ms = timeout_ms
        self.cdn_base_url = (cdn_base_url or DEFAULT_CDN_BASE_URL).rstrip("/")

    def with_base_url(self, base_url: str) -> "WeixinOfficialApi":
        return WeixinOfficialApi(
            base_url=base_url,
            token=self.token,
            timeout_ms=self.timeout_ms,
            cdn_base_url=self.cdn_base_url,
        )

    def get_bot_qr(self, bot_type: str = "3") -> dict[str, Any]:
        return self._request_json(
            "GET",
            f"ilink/bot/get_bot_qrcode?bot_type={urllib.parse.quote(bot_type)}",
            authorized=False,
            timeout_ms=DEFAULT_LONG_POLL_TIMEOUT_MS,
        )

    def get_qr_status(self, qrcode: str) -> dict[str, Any]:
        return self._request_json(
            "GET",
            f"ilink/bot/get_qrcode_status?qrcode={urllib.parse.quote(qrcode)}",
            authorized=False,
            timeout_ms=DEFAULT_LONG_POLL_TIMEOUT_MS,
        )

    def get_updates(self, get_updates_buf: str = "") -> dict[str, Any]:
        try:
            return self._request_json(
                "POST",
                "ilink/bot/getupdates",
                payload={"get_updates_buf": get_updates_buf or ""},
                timeout_ms=DEFAULT_LONG_POLL_TIMEOUT_MS,
            )
        except TimeoutError:
            return {
                "ret": 0,
                "msgs": [],
                "get_updates_buf": get_updates_buf or "",
            }

    def send_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "ilink/bot/sendmessage",
            payload={"msg": msg},
        )

    def send_typing(
        self,
        *,
        ilink_user_id: str,
        typing_ticket: str,
        status: int,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "ilink/bot/sendtyping",
            payload={
                "ilink_user_id": ilink_user_id,
                "typing_ticket": typing_ticket,
                "status": status,
            },
            timeout_ms=10_000,
        )

    def get_config(
        self,
        *,
        ilink_user_id: str,
        context_token: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"ilink_user_id": ilink_user_id}
        if context_token:
            payload["context_token"] = context_token
        return self._request_json(
            "POST",
            "ilink/bot/getconfig",
            payload=payload,
            timeout_ms=10_000,
        )

    def get_upload_url(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json("POST", "ilink/bot/getuploadurl", payload=payload)

    def _request_json(
        self,
        method: str,
        endpoint: str,
        *,
        payload: dict[str, Any] | None = None,
        authorized: bool = True,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        url = join_url(self.base_url, endpoint)
        body: bytes | None = None
        headers = build_headers(token=self.token, authorized=authorized)
        if method.upper() == "POST":
            data = dict(payload or {})
            data["base_info"] = build_base_info()
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
            headers["AuthorizationType"] = "ilink_bot_token"
            headers["Content-Length"] = str(len(body))
        timeout_s = max(1.0, (timeout_ms if timeout_ms is not None else self.timeout_ms) / 1000.0)
        req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:200]
            raise WeixinApiError(
                f"iLink HTTP {e.code} {method} {endpoint}: {detail}",
                code=int(e.code),
            ) from e
        except TimeoutError as e:
            raise TimeoutError(f"iLink timeout {method} {endpoint}") from e
        except Exception as e:
            raise WeixinApiError(f"iLink request failed {method} {endpoint}: {e}") from e
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise WeixinApiError(f"iLink invalid JSON {method} {endpoint}: {raw[:200]}") from e
