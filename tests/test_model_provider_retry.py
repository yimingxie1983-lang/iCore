from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from openai import APIStatusError

import cancer_claw.services.model_router.provider as provider_module
from cancer_claw.services.model_router.provider import ModelProvider


def _status_error(status_code: int) -> APIStatusError:
    request = httpx.Request("POST", "http://127.0.0.1:11434/v1/chat/completions")
    response = httpx.Response(status_code, request=request, text="temporary gateway error")
    return APIStatusError("temporary gateway error", response=response, body=None)


@pytest.mark.asyncio
async def test_local_transient_502_is_retried():
    provider = ModelProvider(
        provider_id="ollama_test",
        name="Ollama Test",
        base_url="http://127.0.0.1:11434/v1",
        api_key="",
        models=[{"id": "qwen3:8b", "role": "general"}],
    )
    result = MagicMock(name="successful completion")
    provider._openai_client = MagicMock()
    provider._openai_client.chat.completions.create = AsyncMock(
        side_effect=[_status_error(502), result]
    )

    with patch("asyncio.sleep", new=AsyncMock()):
        returned = await provider._create_openai_resilient(
            {"model": "qwen3:8b", "stream": False}
        )

    assert returned is result
    assert provider._openai_client.chat.completions.create.await_count == 2


def test_local_provider_uses_direct_http_client():
    http_client_factory = MagicMock(name="httpx.AsyncClient")
    openai_factory = MagicMock(name="AsyncOpenAI")

    with patch.object(
        provider_module.httpx, "AsyncClient", http_client_factory
    ), patch.object(provider_module, "AsyncOpenAI", openai_factory):
        provider = ModelProvider(
            provider_id="ollama_test",
            name="Ollama Test",
            base_url="http://127.0.0.1:11434/v1",
            api_key="",
            models=[{"id": "qwen3:8b", "role": "general"}],
        )

    assert provider.id == "ollama_test"
    http_client_factory.assert_called_once()
    assert http_client_factory.call_args.kwargs["trust_env"] is False
    assert openai_factory.call_args.kwargs["http_client"] is http_client_factory.return_value
