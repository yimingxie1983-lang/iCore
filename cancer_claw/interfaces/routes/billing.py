

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from cancer_claw.services.identity import repo as user_repo
from cancer_claw.services.identity import settings_repo
from cancer_claw.services.identity.deps import get_current_user, require_admin
from cancer_claw.services.credits import pricing
from cancer_claw.services.credits import repo as billing_repo
from cancer_claw.services.credits import token_estimate

logger = structlog.get_logger()
router = APIRouter()

_MICRO_CNY = pricing.MICRO_CNY_PER_CNY

class BalanceResp(BaseModel):
    user_id: str
    balance: int
    total_recharged: int = 0
    total_consumed: int = 0
    total_cost_micro_cny: int = 0
    total_cost_cny: float = 0.0
    consume_count: int = 0

class TxItem(BaseModel):
    id: int
    user_id: str
    type: str
    amount: int
    balance_after: int
    reason: str = ""
    operator_id: str | None = None
    session_id: str | None = None
    project_id: str | None = None
    model: str | None = None
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    cost_micro_cny: int = 0
    cost_cny: float = 0.0
    created_at: Any = None

class TxListResp(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[TxItem]

class RechargeReq(BaseModel):
    amount: int = Field(..., gt=0, description="充值积分（正整数）")
    reason: str = Field("", max_length=200)

class AdjustReq(BaseModel):
    delta: int = Field(..., description="增减积分（正=加，负=扣，不能为 0）")
    reason: str = Field("", max_length=200)

class BillingConfigResp(BaseModel):
    enforce: bool
    initial_grant: int
    markup: float
    mode: str = "split"
    flat_credits_per_1m: float = 6900
    flat_output_credits_per_1m: float = 27000

class BillingConfigUpdateReq(BaseModel):
    enforce: bool | None = None
    initial_grant: int | None = Field(None, ge=0)
    markup: float | None = Field(None, ge=0)
    mode: str | None = None
    flat_credits_per_1m: float | None = Field(None, ge=0)
    flat_output_credits_per_1m: float | None = Field(None, ge=0)

class GlobalSummaryResp(BaseModel):
    total_consumed_credits: int
    total_recharged_credits: int
    total_cost_micro_cny: int
    total_cost_cny: float
    consume_count: int
    total_outstanding_balance: int
    config: BillingConfigResp

class PricingItem(BaseModel):
    model: str
    label: str = ""
    credits_per_1m_input: int = 0
    credits_per_1m_cached_input: int = 0
    credits_per_1m_output: int = 0
    cny_per_1m_input: float = 0.0
    cny_per_1m_cached_input: float = 0.0
    cny_per_1m_output: float = 0.0
    context_window: int = 0

class PricingListResp(BaseModel):
    items: list[PricingItem]
    markup: float = 1.0
    mode: str = "split"
    flat_credits_per_1m: float = 6900
    flat_output_credits_per_1m: float = 27000

class EstimateReq(BaseModel):
    text: str = ""
    model: str | None = None
    reserved_output_tokens: int = Field(1024, ge=0)
    prefer_api: bool = True

class EstimateResp(BaseModel):
    input_tokens: int
    reserved_output_tokens: int
    total_tokens: int
    estimated_credits: int
    source: str

class PricingUpdateReq(BaseModel):
    label: str | None = None
    credits_per_1m_input: float | None = Field(None, ge=0)
    credits_per_1m_cached_input: float | None = Field(None, ge=0)
    credits_per_1m_output: float | None = Field(None, ge=0)
    cny_per_1m_input: float | None = Field(None, ge=0)
    cny_per_1m_cached_input: float | None = Field(None, ge=0)
    cny_per_1m_output: float | None = Field(None, ge=0)
    context_window: int | None = Field(None, ge=0)

def _micro_to_cny(micro: int) -> float:
    return round(int(micro or 0) / _MICRO_CNY, 6)

def _tx_to_item(t: dict[str, Any]) -> TxItem:
    return TxItem(**t, cost_cny=_micro_to_cny(t.get("cost_micro_cny", 0)))

def _summary_to_resp(s: dict[str, Any]) -> BalanceResp:
    return BalanceResp(
        user_id=s["user_id"],
        balance=s["balance"],
        total_recharged=s.get("total_recharged", 0),
        total_consumed=s.get("total_consumed", 0),
        total_cost_micro_cny=s.get("total_cost_micro_cny", 0),
        total_cost_cny=_micro_to_cny(s.get("total_cost_micro_cny", 0)),
        consume_count=s.get("consume_count", 0),
    )

async def _require_existing_user(user_id: str) -> dict[str, Any]:
    u = await user_repo.get_user_by_id(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    return u

@router.get("/me/credits", response_model=BalanceResp)
async def my_credits(user: dict[str, Any] = Depends(get_current_user)) -> BalanceResp:
    s = await billing_repo.user_billing_summary(user["id"])
    return _summary_to_resp(s)

@router.get("/me/credits/transactions", response_model=TxListResp)
async def my_transactions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    tx_type: str | None = Query(None, alias="type"),
    user: dict[str, Any] = Depends(get_current_user),
) -> TxListResp:
    rows, total = await billing_repo.list_transactions(
        user["id"], limit=limit, offset=offset, tx_type=tx_type
    )
    return TxListResp(
        total=total, limit=limit, offset=offset,
        items=[_tx_to_item(r) for r in rows],
    )

@router.get("/billing/pricing", response_model=PricingListResp)
async def get_pricing(_user: dict[str, Any] = Depends(get_current_user)) -> PricingListResp:

    items = [PricingItem(**p) for p in pricing.list_pricing()]
    markup = await settings_repo.get_billing_markup()
    mode = await settings_repo.get_billing_mode()
    flat = await settings_repo.get_flat_credits_per_1m()
    flat_out = await settings_repo.get_flat_output_credits_per_1m()
    return PricingListResp(
        items=items, markup=markup, mode=mode,
        flat_credits_per_1m=flat, flat_output_credits_per_1m=flat_out,
    )

@router.post("/billing/estimate", response_model=EstimateResp)
async def estimate_cost(
    body: EstimateReq, _user: dict[str, Any] = Depends(get_current_user)
) -> EstimateResp:

    text = body.text or ""
    messages = [{"role": "user", "content": text}]
    input_tokens, source = await token_estimate.estimate_input_tokens(
        body.model, messages, prefer_api=body.prefer_api,
    )
    reserved_out = max(0, int(body.reserved_output_tokens or 0))
    total = input_tokens + reserved_out

    mode = await settings_repo.get_billing_mode()
    markup = await settings_repo.get_billing_markup()
    if mode == "flat":
        flat = await settings_repo.get_flat_credits_per_1m()
        est_credits = token_estimate.credits_for_tokens(
            total, flat_credits_per_1m=flat, markup=markup,
        )
    elif mode == "split":

        flat = await settings_repo.get_flat_credits_per_1m()
        flat_out = await settings_repo.get_flat_output_credits_per_1m()
        est_credits = pricing.compute_credits(
            body.model, input_tokens=input_tokens, cached_input_tokens=0,
            output_tokens=reserved_out, markup=markup, mode="split",
            flat_credits_per_1m=flat, flat_output_credits_per_1m=flat_out,
        )
    else:

        est_credits = pricing.compute_credits(
            body.model, input_tokens=input_tokens, cached_input_tokens=0,
            output_tokens=reserved_out, markup=markup,
        )
    return EstimateResp(
        input_tokens=input_tokens,
        reserved_output_tokens=reserved_out,
        total_tokens=total,
        estimated_credits=est_credits,
        source=source,
    )

@router.get("/users/{user_id}/credits", response_model=BalanceResp)
async def get_user_credits(
    user_id: str, _admin: dict[str, Any] = Depends(require_admin)
) -> BalanceResp:
    await _require_existing_user(user_id)
    s = await billing_repo.user_billing_summary(user_id)
    return _summary_to_resp(s)

@router.get("/users/{user_id}/credits/transactions", response_model=TxListResp)
async def get_user_transactions(
    user_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    tx_type: str | None = Query(None, alias="type"),
    _admin: dict[str, Any] = Depends(require_admin),
) -> TxListResp:
    await _require_existing_user(user_id)
    rows, total = await billing_repo.list_transactions(
        user_id, limit=limit, offset=offset, tx_type=tx_type
    )
    return TxListResp(
        total=total, limit=limit, offset=offset,
        items=[_tx_to_item(r) for r in rows],
    )

@router.post("/users/{user_id}/credits/recharge", response_model=BalanceResp)
async def recharge_user(
    user_id: str, body: RechargeReq, admin: dict[str, Any] = Depends(require_admin)
) -> BalanceResp:
    await _require_existing_user(user_id)
    try:
        await billing_repo.recharge(
            user_id, body.amount, operator_id=admin["id"], reason=body.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    logger.info("credits_recharged", target=user_id, amount=body.amount, by=admin.get("username"))
    s = await billing_repo.user_billing_summary(user_id)
    return _summary_to_resp(s)

@router.post("/users/{user_id}/credits/adjust", response_model=BalanceResp)
async def adjust_user(
    user_id: str, body: AdjustReq, admin: dict[str, Any] = Depends(require_admin)
) -> BalanceResp:
    await _require_existing_user(user_id)
    try:
        await billing_repo.adjust(
            user_id, body.delta, operator_id=admin["id"], reason=body.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    logger.info("credits_adjusted", target=user_id, delta=body.delta, by=admin.get("username"))
    s = await billing_repo.user_billing_summary(user_id)
    return _summary_to_resp(s)

@router.get("/admin/billing/summary", response_model=GlobalSummaryResp)
async def billing_summary(_admin: dict[str, Any] = Depends(require_admin)) -> GlobalSummaryResp:
    s = await billing_repo.global_billing_summary()
    cfg = await settings_repo.get_billing_config()
    return GlobalSummaryResp(
        total_consumed_credits=s["total_consumed_credits"],
        total_recharged_credits=s["total_recharged_credits"],
        total_cost_micro_cny=s["total_cost_micro_cny"],
        total_cost_cny=_micro_to_cny(s["total_cost_micro_cny"]),
        consume_count=s["consume_count"],
        total_outstanding_balance=s["total_outstanding_balance"],
        config=BillingConfigResp(**cfg),
    )

@router.get("/admin/billing/config", response_model=BillingConfigResp)
async def get_billing_config(_admin: dict[str, Any] = Depends(require_admin)) -> BillingConfigResp:
    return BillingConfigResp(**await settings_repo.get_billing_config())

@router.put("/admin/billing/config", response_model=BillingConfigResp)
async def set_billing_config(
    body: BillingConfigUpdateReq, admin: dict[str, Any] = Depends(require_admin)
) -> BillingConfigResp:
    if body.enforce is not None:
        await settings_repo.set_billing_enforced(body.enforce)
    if body.initial_grant is not None:
        await settings_repo.set_initial_grant(body.initial_grant)
    if body.markup is not None:
        await settings_repo.set_billing_markup(body.markup)
    if body.mode is not None:
        await settings_repo.set_billing_mode(body.mode)
    if body.flat_credits_per_1m is not None:
        await settings_repo.set_flat_credits_per_1m(body.flat_credits_per_1m)
    if body.flat_output_credits_per_1m is not None:
        await settings_repo.set_flat_output_credits_per_1m(body.flat_output_credits_per_1m)
    logger.info("billing_config_updated", by=admin.get("username"))
    return BillingConfigResp(**await settings_repo.get_billing_config())

@router.put("/admin/billing/pricing/{model}", response_model=PricingItem)
async def update_pricing(
    model: str, body: PricingUpdateReq, admin: dict[str, Any] = Depends(require_admin)
) -> PricingItem:
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="至少要改一个费率字段")
    try:
        merged = pricing.set_pricing(model, patch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    logger.info("pricing_updated", model=model, by=admin.get("username"))
    return PricingItem(model=model, **merged)
