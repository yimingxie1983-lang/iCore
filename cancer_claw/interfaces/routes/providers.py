
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
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
    api_key: str = Field("", description="API 密钥；本地 OpenAI 兼容端点可留空")
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


class ProviderProbeRequest(BaseModel):

    base_url: str = Field(..., min_length=1, description="OpenAI 兼容 API 的基础地址")
    api_key: str = Field("", description="可选 API 密钥")


class ProviderProbeResponse(BaseModel):

    ok: bool = True
    models: list[str] = Field(default_factory=list)


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


def _extract_model_ids(payload: Any) -> list[str]:
    raw_items: list[Any]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            raw_items = data
        elif isinstance(payload.get("models"), list):
            raw_items = payload["models"]
        else:
            raw_items = []
    elif isinstance(payload, list):
        raw_items = payload
    else:
        raw_items = []

    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        model_id = ""
        if isinstance(item, dict):
            model_id = str(item.get("id") or item.get("name") or "").strip()
        elif isinstance(item, str):
            model_id = item.strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        out.append(model_id)
    return out


def _is_local_base_url(base_url: str) -> bool:
    try:
        parsed = urlparse(base_url)
        return parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    except ValueError:
        return False


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
        "api_key": body.api_key or "",
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
        api_key=body.api_key or "",
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


@router.post("/providers/probe", response_model=ProviderProbeResponse)
async def probe_provider(
    body: ProviderProbeRequest,
    _admin: dict[str, Any] = Depends(require_admin),
):
    """探测 OpenAI 兼容端点的 /models 列表（本地或云端均可，不落库）。"""
    base = (body.base_url or "").strip().rstrip("/")
    if not base:
        raise HTTPException(status_code=400, detail="base_url 不能为空")

    url = f"{base}/models"
    headers: dict[str, str] = {"Accept": "application/json"}
    key = (body.api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            trust_env=not _is_local_base_url(base),
        ) as client:
            resp = None
            for attempt in range(3):
                resp = await client.get(url, headers=headers)
                code = resp.status_code
                if code not in {502, 503, 504} or not _is_local_base_url(base) or attempt == 2:
                    break
                logger.warning(
                    "provider_probe_transient_retry",
                    base_url=base,
                    attempt=attempt + 1,
                    status_code=code,
                    body=resp.text[:300],
                )
                await asyncio.sleep(0.8 * (attempt + 1))
    except httpx.ConnectError:
        raise HTTPException(
            status_code=400,
            detail=f"无法连接 {url}（连接被拒绝，请确认本地服务已启动）",
        ) from None
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=400,
            detail=f"连接 {url} 超时，请检查地址或服务是否响应过慢",
        ) from None
    except httpx.HTTPError as e:
        raise HTTPException(status_code=400, detail=f"请求失败: {e}") from e

    if resp.status_code >= 400:
        detail = resp.text.strip()[:300] or f"HTTP {resp.status_code}"
        raise HTTPException(
            status_code=400,
            detail=f"探测失败（HTTP {resp.status_code}）: {detail}",
        )

    try:
        payload = resp.json()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="端点返回的不是 JSON，请确认 base_url 指向 OpenAI 兼容的 /v1",
        ) from None

    models = _extract_model_ids(payload)
    if not models:
        raise HTTPException(
            status_code=400,
            detail="端点已连通，但未返回任何模型 ID",
        )
    return ProviderProbeResponse(ok=True, models=models)


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
