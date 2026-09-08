
from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


def _solve_challenge(challenge):
    m = re.match(r"(\d+)\s*\+\s*(\d+) = \?", challenge["question"])
    assert m, challenge["question"]
    return str(int(m.group(1)) + int(m.group(2)))


async def _register_admin(client, username="prov_admin"):
    resp = await client.get("/api/auth/captcha")
    assert resp.status_code == 200, resp.text
    challenge = resp.json()
    resp = await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "StrongPass1!",
            "email": f"{username}@example.com",
            "display_name": username,
            "captcha": {"id": challenge["id"], "answer": _solve_challenge(challenge)},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
async def admin_headers(client, tmp_path, monkeypatch):
    from cancer_claw.config import settings

    monkeypatch.setattr(settings.paths, "data_dir", str(tmp_path / "state"))
    data = await _register_admin(client)
    return {"Authorization": f"Bearer {data['access_token']}"}


async def test_create_provider_allows_empty_api_key(client, admin_headers):
    resp = await client.post(
        "/api/providers",
        headers=admin_headers,
        json={
            "name": "Ollama",
            "base_url": "http://127.0.0.1:11434/v1",
            "api_key": "",
            "models": [{"id": "llama3.2", "role": "general"}],
            "enabled": True,
            "priority": 0,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Ollama"
    assert body["base_url"] == "http://127.0.0.1:11434/v1"
    assert body["api_key_preview"] == ""
    assert body["models"][0]["id"] == "llama3.2"


async def test_probe_provider_lists_models(client, admin_headers):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "object": "list",
        "data": [{"id": "llama3.2"}, {"id": "qwen2.5"}],
    }
    mock_resp.text = ""

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cancer_claw.interfaces.routes.providers.httpx.AsyncClient", return_value=mock_client):
        resp = await client.post(
            "/api/providers/probe",
            headers=admin_headers,
            json={"base_url": "http://127.0.0.1:11434/v1", "api_key": ""},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["models"] == ["llama3.2", "qwen2.5"]
    mock_client.get.assert_awaited()
    called_url = mock_client.get.await_args.args[0]
    assert called_url == "http://127.0.0.1:11434/v1/models"


async def test_probe_provider_retries_local_transient_502(client, admin_headers):
    bad_resp = MagicMock()
    bad_resp.status_code = 502
    bad_resp.text = "temporary local gateway error"
    good_resp = MagicMock()
    good_resp.status_code = 200
    good_resp.json.return_value = {"data": [{"id": "qwen3:8b"}]}
    good_resp.text = ""

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[bad_resp, good_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cancer_claw.interfaces.routes.providers.httpx.AsyncClient", return_value=mock_client):
        resp = await client.post(
            "/api/providers/probe",
            headers=admin_headers,
            json={"base_url": "http://127.0.0.1:11434/v1", "api_key": ""},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["models"] == ["qwen3:8b"]
    assert mock_client.get.await_count == 2


async def test_probe_provider_local_url_ignores_proxy_environment(client, admin_headers, monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7897")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:7897")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"id": "qwen3:8b"}]}
    mock_resp.text = ""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "cancer_claw.interfaces.routes.providers.httpx.AsyncClient",
        return_value=mock_client,
    ) as client_factory:
        resp = await client.post(
            "/api/providers/probe",
            headers=admin_headers,
            json={"base_url": "http://127.0.0.1:11434/v1", "api_key": ""},
        )

    assert resp.status_code == 200, resp.text
    assert client_factory.call_args.kwargs.get("trust_env") is False


async def test_probe_provider_connect_error(client, admin_headers):
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cancer_claw.interfaces.routes.providers.httpx.AsyncClient", return_value=mock_client):
        resp = await client.post(
            "/api/providers/probe",
            headers=admin_headers,
            json={"base_url": "http://127.0.0.1:11434/v1"},
        )
    assert resp.status_code == 400, resp.text
    assert "无法连接" in resp.text or "连接" in resp.text
