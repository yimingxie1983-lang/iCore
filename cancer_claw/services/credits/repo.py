

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from cancer_claw.config import settings
from cancer_claw.db import get_db, get_read_db, transaction

logger = structlog.get_logger()

TX_GRANT = "grant"
TX_RECHARGE = "recharge"
TX_CONSUME = "consume"
TX_ADJUST = "adjust"
VALID_TX_TYPES = (TX_GRANT, TX_RECHARGE, TX_CONSUME, TX_ADJUST)

_write_lock = asyncio.Lock()

async def get_balance(user_id: str) -> int:

    db = await get_read_db()
    cur = await db.execute(
        "SELECT COALESCE(credits_balance, 0) FROM users WHERE id = ?", (user_id,)
    )
    row = await cur.fetchone()
    return int(row[0]) if row else 0

async def _apply_delta(
    *,
    user_id: str,
    delta: int,
    tx_type: str,
    reason: str = "",
    operator_id: str | None = None,
    session_id: str | None = None,
    project_id: str | None = None,
    model: str | None = None,
    input_tokens: int = 0,
    cached_input_tokens: int = 0,
    output_tokens: int = 0,
    cost_micro_cny: int = 0,
) -> int:

    if tx_type not in VALID_TX_TYPES:
        raise ValueError(f"非法交易类型: {tx_type}")

    _insert_tx = (
        """INSERT INTO credit_transactions
           (user_id, type, amount, balance_after, reason, operator_id,
            session_id, project_id, model,
            input_tokens, cached_input_tokens, output_tokens, cost_micro_cny)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    )

    def _tx_params(new_balance: int) -> tuple:
        return (
            user_id, tx_type, int(delta), new_balance, reason or "", operator_id,
            session_id, project_id, model,
            int(input_tokens or 0), int(cached_input_tokens or 0),
            int(output_tokens or 0), int(cost_micro_cny or 0),
        )

    if settings.database.is_postgres:

        async with transaction() as tx:
            cur = await tx.execute(
                "UPDATE users SET credits_balance = COALESCE(credits_balance, 0) + ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ? RETURNING credits_balance",
                (int(delta), user_id),
            )
            row = await cur.fetchone()
            if row is None:
                raise ValueError(f"用户不存在: {user_id}")
            new_balance = int(row[0])
            await tx.execute(_insert_tx, _tx_params(new_balance))
            return new_balance


    async with _write_lock:
        db = await get_db()
        cur = await db.execute(
            "SELECT COALESCE(credits_balance, 0) FROM users WHERE id = ?", (user_id,)
        )
        row = await cur.fetchone()
        if row is None:
            raise ValueError(f"用户不存在: {user_id}")
        new_balance = int(row[0]) + int(delta)
        await db.execute(
            "UPDATE users SET credits_balance = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (new_balance, user_id),
        )
        await db.execute(_insert_tx, _tx_params(new_balance))
        await db.commit()
        return new_balance

async def grant_initial(user_id: str, amount: int, *, reason: str = "新用户注册赠送") -> int:

    amount = int(amount)
    if amount <= 0:
        return await get_balance(user_id)
    return await _apply_delta(
        user_id=user_id, delta=amount, tx_type=TX_GRANT, reason=reason,
    )

async def recharge(
    user_id: str, amount: int, *, operator_id: str | None, reason: str = ""
) -> int:

    amount = int(amount)
    if amount <= 0:
        raise ValueError("充值积分必须为正整数")
    return await _apply_delta(
        user_id=user_id, delta=amount, tx_type=TX_RECHARGE,
        reason=reason, operator_id=operator_id,
    )

async def adjust(
    user_id: str, delta: int, *, operator_id: str | None, reason: str = ""
) -> int:

    delta = int(delta)
    if delta == 0:
        raise ValueError("调整值不能为 0")
    return await _apply_delta(
        user_id=user_id, delta=delta, tx_type=TX_ADJUST,
        reason=reason, operator_id=operator_id,
    )

async def consume(
    user_id: str,
    credits: int,
    *,
    cost_micro_cny: int = 0,
    model: str | None = None,
    session_id: str | None = None,
    project_id: str | None = None,
    input_tokens: int = 0,
    cached_input_tokens: int = 0,
    output_tokens: int = 0,
) -> int:

    credits = int(credits)
    if credits <= 0:
        return await get_balance(user_id)
    return await _apply_delta(
        user_id=user_id, delta=-credits, tx_type=TX_CONSUME,
        model=model, session_id=session_id, project_id=project_id,
        input_tokens=input_tokens, cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens, cost_micro_cny=cost_micro_cny,
    )

def _row_to_tx(r: Any) -> dict[str, Any]:
    return {
        "id": r[0],
        "user_id": r[1],
        "type": r[2],
        "amount": int(r[3]),
        "balance_after": int(r[4]),
        "reason": r[5] or "",
        "operator_id": r[6],
        "session_id": r[7],
        "project_id": r[8],
        "model": r[9],
        "input_tokens": int(r[10] or 0),
        "cached_input_tokens": int(r[11] or 0),
        "output_tokens": int(r[12] or 0),
        "cost_micro_cny": int(r[13] or 0),
        "created_at": r[14],
    }

_TX_COLS = (
    "id, user_id, type, amount, balance_after, reason, operator_id, "
    "session_id, project_id, model, input_tokens, cached_input_tokens, "
    "output_tokens, cost_micro_cny, created_at"
)

async def list_transactions(
    user_id: str, *, limit: int = 50, offset: int = 0, tx_type: str | None = None
) -> tuple[list[dict[str, Any]], int]:

    db = await get_read_db()
    where = "WHERE user_id = ?"
    params: list[Any] = [user_id]
    if tx_type:
        where += " AND type = ?"
        params.append(tx_type)

    cur = await db.execute(
        f"SELECT COUNT(*) FROM credit_transactions {where}", params
    )
    row = await cur.fetchone()
    total = int(row[0]) if row else 0

    cur = await db.execute(
        f"SELECT {_TX_COLS} FROM credit_transactions {where} "
        f"ORDER BY id DESC LIMIT ? OFFSET ?",
        (*params, int(limit), int(offset)),
    )
    rows = await cur.fetchall()
    return [_row_to_tx(r) for r in rows], total

async def user_billing_summary(user_id: str) -> dict[str, Any]:

    db = await get_read_db()
    balance = await get_balance(user_id)
    cur = await db.execute(
        """SELECT
             COALESCE(SUM(CASE WHEN type IN ('recharge','grant') THEN amount ELSE 0 END), 0),
             COALESCE(SUM(CASE WHEN type = 'consume' THEN -amount ELSE 0 END), 0),
             COALESCE(SUM(cost_micro_cny), 0),
             COALESCE(SUM(CASE WHEN type = 'consume' THEN 1 ELSE 0 END), 0)
           FROM credit_transactions WHERE user_id = ?""",
        (user_id,),
    )
    r = await cur.fetchone()
    return {
        "user_id": user_id,
        "balance": balance,
        "total_recharged": int(r[0] or 0),
        "total_consumed": int(r[1] or 0),
        "total_cost_micro_cny": int(r[2] or 0),
        "consume_count": int(r[3] or 0),
    }

async def global_billing_summary() -> dict[str, Any]:

    db = await get_read_db()
    cur = await db.execute(
        """SELECT
             COALESCE(SUM(CASE WHEN type = 'consume' THEN -amount ELSE 0 END), 0),
             COALESCE(SUM(CASE WHEN type IN ('recharge','grant') THEN amount ELSE 0 END), 0),
             COALESCE(SUM(cost_micro_cny), 0),
             COALESCE(SUM(CASE WHEN type = 'consume' THEN 1 ELSE 0 END), 0)
           FROM credit_transactions""",
    )
    r = await cur.fetchone()
    cur2 = await db.execute(
        "SELECT COALESCE(SUM(COALESCE(credits_balance,0)), 0) FROM users"
    )
    r2 = await cur2.fetchone()
    return {
        "total_consumed_credits": int(r[0] or 0),
        "total_recharged_credits": int(r[1] or 0),
        "total_cost_micro_cny": int(r[2] or 0),
        "consume_count": int(r[3] or 0),
        "total_outstanding_balance": int(r2[0] or 0),
    }
