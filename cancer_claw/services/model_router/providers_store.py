

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
import yaml

from cancer_claw.config import settings

logger = structlog.get_logger()

def _yaml_path() -> Path:

    return Path(settings.paths.data_dir) / "providers.yaml"

_write_lock = asyncio.Lock()

def _read_yaml() -> list[dict[str, Any]]:

    path = _yaml_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception as e:
        logger.warning("providers_yaml_read_failed", error=str(e), path=str(path))
        return []

    if data is None:
        return []
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        items = data.get("providers", [])
        return [d for d in items if isinstance(d, dict)]
    return []

def _write_yaml(items: list[dict[str, Any]]) -> None:

    path = _yaml_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {"providers": items}

    fd, tmp_path = tempfile.mkstemp(
        prefix=".providers.", suffix=".yaml.tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(
                payload, fh, allow_unicode=True, sort_keys=False, default_flow_style=False
            )
        os.replace(tmp_path, path)
    except Exception:

        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise

def list_providers_sync() -> list[dict[str, Any]]:

    return _read_yaml()

async def list_providers() -> list[dict[str, Any]]:

    items = await asyncio.to_thread(_read_yaml)
    items.sort(key=lambda x: int(x.get("priority", 0) or 0))
    return items

async def get_provider(provider_id: str) -> dict[str, Any] | None:

    items = await list_providers()
    for it in items:
        if it.get("id") == provider_id:
            return it
    return None

async def add_provider(item: dict[str, Any]) -> dict[str, Any]:

    if not item.get("id"):
        raise ValueError("provider 必须有 id")

    async with _write_lock:
        items = await asyncio.to_thread(_read_yaml)
        if any(it.get("id") == item["id"] for it in items):
            raise ValueError(f"provider id 已存在: {item['id']}")

        record = dict(item)
        record.setdefault("created_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        items.append(record)
        await asyncio.to_thread(_write_yaml, items)
        return record

async def update_provider(
    provider_id: str, patch: dict[str, Any]
) -> dict[str, Any] | None:

    async with _write_lock:
        items = await asyncio.to_thread(_read_yaml)
        for i, it in enumerate(items):
            if it.get("id") != provider_id:
                continue
            updated = dict(it)
            for k, v in patch.items():
                if v is not None:
                    updated[k] = v
            items[i] = updated
            await asyncio.to_thread(_write_yaml, items)
            return updated
    return None

async def delete_provider(provider_id: str) -> bool:

    async with _write_lock:
        items = await asyncio.to_thread(_read_yaml)
        new_items = [it for it in items if it.get("id") != provider_id]
        if len(new_items) == len(items):
            return False
        await asyncio.to_thread(_write_yaml, new_items)
        return True

async def ensure_initialized(initial: list[dict[str, Any]]) -> bool:

    path = _yaml_path()
    if path.exists():
        return False

    async with _write_lock:
        if path.exists():
            return False
        records: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for raw in initial:
            rec = dict(raw)
            rec.setdefault("created_at", now)
            records.append(rec)
        await asyncio.to_thread(_write_yaml, records)
        logger.info("providers_yaml_initialized", count=len(records), path=str(path))
        return True
