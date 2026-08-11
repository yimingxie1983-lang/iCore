

from __future__ import annotations

from datetime import datetime, timezone

from cancer_claw.config import settings
from cancer_claw.db import get_db, get_read_db

KEY_ALLOW_REGISTRATION = "allow_registration"

KEY_BILLING_ENFORCE = "billing_enforce"
KEY_BILLING_INITIAL_GRANT = "billing_initial_grant"
KEY_BILLING_MARKUP = "billing_markup"
KEY_BILLING_MODE = "billing_mode"
KEY_FLAT_CREDITS_PER_1M = "billing_flat_credits_per_1m"
KEY_FLAT_OUTPUT_CREDITS_PER_1M = "billing_flat_output_credits_per_1m"

DEFAULT_BILLING_ENFORCE = True
DEFAULT_BILLING_INITIAL_GRANT = 50000
DEFAULT_BILLING_MARKUP = 1.0

DEFAULT_BILLING_MODE = "split"
DEFAULT_FLAT_CREDITS_PER_1M = 6900

DEFAULT_FLAT_OUTPUT_CREDITS_PER_1M = 27000

_BILLING_MODES = ("flat", "tiered", "split")

_TRUE_TOKENS = {"1", "true", "yes", "on"}

def _to_bool(raw: str | None, default: bool) -> bool:

    if raw is None:
        return default
    return raw.strip().lower() in _TRUE_TOKENS

async def get_setting(key: str) -> str | None:

    db = await get_read_db()
    cur = await db.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
    row = await cur.fetchone()
    return row[0] if row else None

async def set_setting(key: str, value: str) -> None:

    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO system_settings (key, value, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                          updated_at = excluded.updated_at""",
        (key, value, now),
    )
    await db.commit()

async def is_registration_open() -> bool:

    raw = await get_setting(KEY_ALLOW_REGISTRATION)
    return _to_bool(raw, default=bool(settings.auth.allow_registration))

async def set_registration_open(open_: bool) -> None:

    await set_setting(KEY_ALLOW_REGISTRATION, "true" if open_ else "false")

def _to_int(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    try:
        return int(float(raw.strip()))
    except (ValueError, AttributeError):
        return default

def _to_float(raw: str | None, default: float) -> float:
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except (ValueError, AttributeError):
        return default

async def is_billing_enforced() -> bool:

    return _to_bool(await get_setting(KEY_BILLING_ENFORCE), DEFAULT_BILLING_ENFORCE)

async def set_billing_enforced(enforce: bool) -> None:
    await set_setting(KEY_BILLING_ENFORCE, "true" if enforce else "false")

async def get_initial_grant() -> int:

    return _to_int(await get_setting(KEY_BILLING_INITIAL_GRANT), DEFAULT_BILLING_INITIAL_GRANT)

async def set_initial_grant(amount: int) -> None:
    await set_setting(KEY_BILLING_INITIAL_GRANT, str(max(0, int(amount))))

async def get_billing_markup() -> float:

    return _to_float(await get_setting(KEY_BILLING_MARKUP), DEFAULT_BILLING_MARKUP)

async def set_billing_markup(markup: float) -> None:
    await set_setting(KEY_BILLING_MARKUP, str(max(0.0, float(markup))))

async def get_billing_mode() -> str:

    raw = await get_setting(KEY_BILLING_MODE)
    mode = (raw or DEFAULT_BILLING_MODE).strip().lower()
    return mode if mode in _BILLING_MODES else DEFAULT_BILLING_MODE

async def set_billing_mode(mode: str) -> None:
    m = (mode or "").strip().lower()
    await set_setting(KEY_BILLING_MODE, m if m in _BILLING_MODES else DEFAULT_BILLING_MODE)

async def get_flat_credits_per_1m() -> float:

    return _to_float(await get_setting(KEY_FLAT_CREDITS_PER_1M), float(DEFAULT_FLAT_CREDITS_PER_1M))

async def set_flat_credits_per_1m(value: float) -> None:
    await set_setting(KEY_FLAT_CREDITS_PER_1M, str(max(0.0, float(value))))

async def get_flat_output_credits_per_1m() -> float:

    return _to_float(
        await get_setting(KEY_FLAT_OUTPUT_CREDITS_PER_1M),
        float(DEFAULT_FLAT_OUTPUT_CREDITS_PER_1M),
    )

async def set_flat_output_credits_per_1m(value: float) -> None:
    await set_setting(KEY_FLAT_OUTPUT_CREDITS_PER_1M, str(max(0.0, float(value))))

async def get_billing_config() -> dict:

    return {
        "enforce": await is_billing_enforced(),
        "initial_grant": await get_initial_grant(),
        "markup": await get_billing_markup(),
        "mode": await get_billing_mode(),
        "flat_credits_per_1m": await get_flat_credits_per_1m(),
        "flat_output_credits_per_1m": await get_flat_output_credits_per_1m(),
    }
