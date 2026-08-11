

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import structlog
import yaml

from cancer_claw.config import settings

logger = structlog.get_logger()

DEFAULT_PRICING: dict[str, dict[str, Any]] = {
    "kimi-k2.6": {
        "label": "Kimi K2.6",
        "credits_per_1m_input": 6500,
        "credits_per_1m_cached_input": 1100,
        "credits_per_1m_output": 27000,
        "cny_per_1m_input": 6.5,
        "cny_per_1m_cached_input": 1.1,
        "cny_per_1m_output": 27.0,
        "context_window": 262144,
    },
    "kimi-k2.5": {
        "label": "Kimi K2.5",
        "credits_per_1m_input": 4000,
        "credits_per_1m_cached_input": 1000,
        "credits_per_1m_output": 21000,
        "cny_per_1m_input": 4.0,
        "cny_per_1m_cached_input": 1.0,
        "cny_per_1m_output": 21.0,
        "context_window": 262144,
    },
    "moonshot-v1-128k": {
        "label": "Moonshot v1 128k",
        "credits_per_1m_input": 10000,
        "credits_per_1m_cached_input": 2000,
        "credits_per_1m_output": 30000,
        "cny_per_1m_input": 10.0,
        "cny_per_1m_cached_input": 2.0,
        "cny_per_1m_output": 30.0,
        "context_window": 131072,
    },

    "default": {
        "label": "默认（未知模型兜底）",
        "credits_per_1m_input": 6500,
        "credits_per_1m_cached_input": 1100,
        "credits_per_1m_output": 27000,
        "cny_per_1m_input": 6.5,
        "cny_per_1m_cached_input": 1.1,
        "cny_per_1m_output": 27.0,
        "context_window": 131072,
    },
}

_RATE_FIELDS = (
    "credits_per_1m_input",
    "credits_per_1m_cached_input",
    "credits_per_1m_output",
    "cny_per_1m_input",
    "cny_per_1m_cached_input",
    "cny_per_1m_output",
)

MICRO_CNY_PER_CNY = 1_000_000

def _yaml_path() -> Path:
    return Path(settings.paths.data_dir) / "model_pricing.yaml"

_cache: dict[str, dict[str, Any]] | None = None

def _read_overrides() -> dict[str, dict[str, Any]]:

    path = _yaml_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception as e:
        logger.warning("model_pricing_yaml_read_failed", error=str(e), path=str(path))
        return {}
    if not isinstance(data, dict):
        return {}
    models = data.get("models", data)
    if not isinstance(models, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for k, v in models.items():
        if isinstance(v, dict):
            out[str(k)] = v
    return out

def _write_overrides(models: dict[str, dict[str, Any]]) -> None:

    path = _yaml_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"models": models}
    fd, tmp = tempfile.mkstemp(prefix=".model_pricing.", suffix=".yaml.tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=False)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise

def _build_merged() -> dict[str, dict[str, Any]]:

    merged: dict[str, dict[str, Any]] = {k: dict(v) for k, v in DEFAULT_PRICING.items()}
    for model_key, patch in _read_overrides().items():
        base = dict(merged.get(model_key, merged["default"]))
        for k, v in patch.items():
            if v is not None:
                base[k] = v
        merged[model_key] = base
    return merged

def get_all_pricing() -> dict[str, dict[str, Any]]:

    global _cache
    if _cache is None:
        _cache = _build_merged()
    return _cache

def reload() -> None:

    global _cache
    _cache = None

def pricing_for(model: str | None) -> dict[str, Any]:

    table = get_all_pricing()
    if not model:
        return table["default"]
    if model in table:
        return table[model]

    for key in table:
        if key != "default" and key in model:
            return table[key]
    return table["default"]

def _split_input(input_tokens: int, cached_input_tokens: int) -> tuple[int, int]:

    inp = max(0, int(input_tokens or 0))
    cached = max(0, int(cached_input_tokens or 0))
    cached = min(cached, inp)
    non_cached = inp - cached
    return non_cached, cached

MODE_TIERED = "tiered"
MODE_FLAT = "flat"
MODE_SPLIT = "split"

DEFAULT_FLAT_CREDITS_PER_1M = 6900

DEFAULT_FLAT_OUTPUT_CREDITS_PER_1M = 27000

def compute_credits(
    model: str | None,
    *,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    markup: float = 1.0,
    mode: str = MODE_TIERED,
    flat_credits_per_1m: float = DEFAULT_FLAT_CREDITS_PER_1M,
    flat_output_credits_per_1m: float = DEFAULT_FLAT_OUTPUT_CREDITS_PER_1M,
) -> int:

    inp = max(0, int(input_tokens or 0))
    out = max(0, int(output_tokens or 0))

    if mode == MODE_FLAT:

        total = inp + out
        credits = total / 1_000_000 * max(0.0, float(flat_credits_per_1m))
        return max(0, round(credits * max(0.0, float(markup))))

    if mode == MODE_SPLIT:

        credits = (
            inp / 1_000_000 * max(0.0, float(flat_credits_per_1m))
            + out / 1_000_000 * max(0.0, float(flat_output_credits_per_1m))
        )
        return max(0, round(credits * max(0.0, float(markup))))


    p = pricing_for(model)
    non_cached, cached = _split_input(inp, cached_input_tokens)
    credits = (
        non_cached / 1_000_000 * float(p["credits_per_1m_input"])
        + cached / 1_000_000 * float(p["credits_per_1m_cached_input"])
        + out / 1_000_000 * float(p["credits_per_1m_output"])
    )
    return max(0, round(credits * max(0.0, float(markup))))

def compute_cost_micro_cny(
    model: str | None,
    *,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
) -> int:

    p = pricing_for(model)
    non_cached, cached = _split_input(input_tokens, cached_input_tokens)
    out = max(0, int(output_tokens or 0))
    cny = (
        non_cached / 1_000_000 * float(p["cny_per_1m_input"])
        + cached / 1_000_000 * float(p["cny_per_1m_cached_input"])
        + out / 1_000_000 * float(p["cny_per_1m_output"])
    )
    return max(0, round(cny * MICRO_CNY_PER_CNY))

def list_pricing() -> list[dict[str, Any]]:

    table = get_all_pricing()
    out: list[dict[str, Any]] = []
    for key, v in table.items():
        row = {"model": key, **v}
        out.append(row)
    return out

def set_pricing(model_key: str, patch: dict[str, Any]) -> dict[str, Any]:

    clean: dict[str, Any] = {}
    if "label" in patch and patch["label"] is not None:
        clean["label"] = str(patch["label"])
    for f in _RATE_FIELDS:
        if f in patch and patch[f] is not None:
            val = float(patch[f])
            if val < 0:
                raise ValueError(f"费率 {f} 不能为负")

            clean[f] = int(round(val)) if f.startswith("credits_") else val
    if "context_window" in patch and patch["context_window"] is not None:
        clean["context_window"] = int(patch["context_window"])

    overrides = _read_overrides()
    base = dict(overrides.get(model_key, {}))
    base.update(clean)
    overrides[model_key] = base
    _write_overrides(overrides)
    reload()
    return pricing_for(model_key)
