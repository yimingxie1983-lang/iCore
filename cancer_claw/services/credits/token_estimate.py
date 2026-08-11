

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_PER_MESSAGE_OVERHEAD = 4

_ASCII_CHARS_PER_TOKEN = 4.0

def _is_cjk(ch: str) -> bool:

    o = ord(ch)
    return (
        0x4E00 <= o <= 0x9FFF
        or 0x3400 <= o <= 0x4DBF
        or 0x3000 <= o <= 0x303F
        or 0xFF00 <= o <= 0xFFEF
        or 0x3040 <= o <= 0x30FF
        or 0xAC00 <= o <= 0xD7A3
    )

def estimate_text_tokens(text: str) -> int:

    if not text:
        return 0
    cjk = 0
    other = 0
    for ch in text:
        if ch.isspace():
            other += 0.5
        elif _is_cjk(ch):
            cjk += 1
        else:
            other += 1
    return max(1, int(cjk + other / _ASCII_CHARS_PER_TOKEN))

def _message_text(msg: dict[str, Any]) -> str:

    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for seg in content:
            if isinstance(seg, dict) and isinstance(seg.get("text"), str):
                parts.append(seg["text"])
            elif isinstance(seg, str):
                parts.append(seg)
        return "\n".join(parts)
    return ""

def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:

    total = 0
    for m in messages or []:
        total += _PER_MESSAGE_OVERHEAD + estimate_text_tokens(_message_text(m))
    return total

def _find_moonshot_provider(providers: list[dict[str, Any]]) -> dict[str, Any] | None:

    for p in providers or []:
        base = str(p.get("base_url", "")).lower()
        if not p.get("api_key"):
            continue
        if "moonshot" in base or (p.get("id", "").lower() in ("kimi", "moonshot")):
            return p
    return None

async def estimate_via_moonshot(
    model: str | None,
    messages: list[dict[str, Any]],
    *,
    timeout: float = 3.0,
) -> int | None:

    try:
        import httpx

        from cancer_claw.services.model_router import providers_store

        providers = await providers_store.list_providers()
        prov = _find_moonshot_provider(providers)
        if not prov:
            return None
        base = str(prov["base_url"]).rstrip("/")
        url = f"{base}/tokenizers/estimate-token-count"
        payload = {
            "model": model or (prov.get("models") or [{}])[0].get("id") or "kimi-k2.6",
            "messages": messages,
        }
        headers = {
            "Authorization": f"Bearer {prov['api_key']}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        total = (data or {}).get("data", {}).get("total_tokens")
        return int(total) if total is not None else None
    except Exception as e:
        logger.debug("moonshot_estimate_failed", error=str(e))
        return None

async def estimate_input_tokens(
    model: str | None,
    messages: list[dict[str, Any]],
    *,
    prefer_api: bool = True,
) -> tuple[int, str]:

    if prefer_api:
        api_val = await estimate_via_moonshot(model, messages)
        if api_val is not None and api_val > 0:
            return api_val, "moonshot"
    return estimate_messages_tokens(messages), "heuristic"

def credits_for_tokens(
    total_tokens: int,
    *,
    flat_credits_per_1m: float,
    markup: float = 1.0,
) -> int:

    t = max(0, int(total_tokens or 0))
    credits = t / 1_000_000 * max(0.0, float(flat_credits_per_1m))
    return max(0, round(credits * max(0.0, float(markup))))
