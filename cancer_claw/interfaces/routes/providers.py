

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from cancer_claw.services.identity.deps import get_current_user, require_admin
from cancer_claw.services.model_router import providers_store
from cancer_claw.services.model_router.strategy import get_router

logger = structlog.get_logger()
router = APIRouter()

class ModelInfo(BaseModel):

    id: str = Field(..., description="模型 ID，如 qwen-plus、deepseek-chat")
    role: str = Field("general", description="模型角色：general | fast | complex")

class ProviderCreate(BaseModel):

    name: str = Field(..., min_length=1, max_length=50, description="供应商显示名称")
    base_url: str = Field(..., description="OpenAI 兼容 API 的基础地址")
    api_key: str = Field(..., description="API 密钥")
    models: list[ModelInfo] = Field(..., min_length=1, description="该供应商下的可用模型列表")
    enabled: bool = Field(True, description="是否启用")
    priority: int = Field(0, description="路由优先级，数字越小优先级越高")

class ProviderUpdate(BaseModel):

    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    models: list[ModelInfo] | None = None
    enabled: bool | None = None
    priority: int | None = None

class ProviderResponse(BaseModel):

    id: str
    name: str
    base_url: str
    api_key_preview: str
    models: list[ModelInfo]
    enabled: bool
    priority: int
    created_at: str

class ProviderListResponse(BaseModel):

    total: int
    items: list[ProviderResponse]

class ProviderStatusResponse(BaseModel):

    id: str
    name: str
    enabled: bool
    healthy: bool
    total_calls: int
    total_errors: int
    avg_latency_ms: float

def _mask_api_key(key: str) -> str:

    # mask for logs
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "***"
    return key[:8] + "***"

def _record_to_response(item: dict) -> ProviderResponse:

    raw_models = item.get("models") or []
    models = [
        ModelInfo(**m) if isinstance(m, dict) else ModelInfo(id=str(m))
        for m in raw_models
    ]
    return ProviderResponse(
        id=item["id"],
        name=item.get("name", ""),
        base_url=item.get("base_url", ""),
        api_key_preview=_mask_api_key(item.get("api_key", "")),
        models=models,
        enabled=bool(item.get("enabled", True)),
        priority=int(item.get("priority", 0) or 0),
        created_at=item.get("created_at", ""),
    )

@router.post("/providers", response_model=ProviderResponse, status_code=201)
async def create_provider(
    body: ProviderCreate,
    _admin: dict[str, Any] = Depends(require_admin),
):

    provider_id = body.name.lower().replace(" ", "_") + "_" + uuid.uuid4().hex[:6]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    record = {
        "id": provider_id,
        "name": body.name,
        "base_url": body.base_url,
        "api_key": body.api_key,
        "models": [m.model_dump() for m in body.models],
        "enabled": body.enabled,
        "priority": body.priority,
        "created_at": now,
    }
    saved = await providers_store.add_provider(record)


    model_router = get_router()
    model_router.add_provider(
        provider_id=provider_id,
        name=body.name,
        base_url=body.base_url,
        api_key=body.api_key,
        models=[m.model_dump() for m in body.models],
        enabled=body.enabled,
        priority=body.priority,
    )

    logger.info("provider_created", id=provider_id, name=body.name)
    return _record_to_response(saved)

@router.get("/providers", response_model=ProviderListResponse)
async def list_providers(_user: dict[str, Any] = Depends(get_current_user)):

    items = await providers_store.list_providers()
    resp_items = [_record_to_response(it) for it in items]
    return ProviderListResponse(total=len(resp_items), items=resp_items)

@router.get("/providers/{provider_id}", response_model=ProviderResponse)
async def get_provider(
    provider_id: str,
    _user: dict[str, Any] = Depends(get_current_user),
):

    item = await providers_store.get_provider(provider_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"供应商 {provider_id} 不存在")
    return _record_to_response(item)

@router.patch("/providers/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: str,
    body: ProviderUpdate,
    _admin: dict[str, Any] = Depends(require_admin),
):

    patch: dict = {}
    if body.name is not None:
        patch["name"] = body.name
    if body.base_url is not None:
        patch["base_url"] = body.base_url


    if body.api_key:
        patch["api_key"] = body.api_key
    if body.models is not None:
        patch["models"] = [m.model_dump() for m in body.models]
    if body.enabled is not None:
        patch["enabled"] = body.enabled
    if body.priority is not None:
        patch["priority"] = body.priority

    if not patch:
        raise HTTPException(status_code=400, detail="没有提供要更新的字段")

    updated = await providers_store.update_provider(provider_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail=f"供应商 {provider_id} 不存在")



    model_router = get_router()
    model_router.remove_provider(provider_id)
    if updated.get("enabled", True):
        model_router.add_provider(
            provider_id=updated["id"],
            name=updated.get("name", ""),
            base_url=updated.get("base_url", ""),
            api_key=updated.get("api_key", ""),
            models=updated.get("models", []),
            enabled=bool(updated.get("enabled", True)),
            priority=int(updated.get("priority", 0) or 0),
        )

    logger.info("provider_updated", id=provider_id)
    return _record_to_response(updated)

@router.delete("/providers/{provider_id}", status_code=204)
async def delete_provider(
    provider_id: str,
    _admin: dict[str, Any] = Depends(require_admin),
):

    ok = await providers_store.delete_provider(provider_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"供应商 {provider_id} 不存在")

    model_router = get_router()
    model_router.remove_provider(provider_id)

    logger.info("provider_deleted", id=provider_id)

@router.get("/providers/status/all", response_model=list[ProviderStatusResponse])
async def get_all_provider_status(_user: dict[str, Any] = Depends(get_current_user)):

    model_router = get_router()
    statuses = model_router.get_all_status()
    return [
        ProviderStatusResponse(
            id=s.id, name=s.name, enabled=s.enabled, healthy=s.healthy,
            total_calls=s.total_calls, total_errors=s.total_errors,
            avg_latency_ms=s.avg_latency_ms,
        )
        for s in statuses
    ]
