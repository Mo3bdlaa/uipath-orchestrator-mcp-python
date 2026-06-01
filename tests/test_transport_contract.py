"""End-to-end contract tests that drive the *real* HTTP stack.

Unlike ``test_orchestrator.py`` (which mocks ``_call``), these install an
``httpx.MockTransport`` so the full path is exercised — URL resolution, auth
header injection, the folder header, OData parsing, and the retry loop — against
canned Orchestrator responses. Only the socket is faked.
"""

import httpx
import pytest

from uipath_mcp_python.orchestrator import Orchestrator, OrchestratorError
from uipath_mcp_python.schemas import OrchestratorSettings


def _client(handler) -> Orchestrator:
    """A PAT-auth client (no handshake) wired to a MockTransport handler."""
    settings = OrchestratorSettings(
        auth_strategy="cloud-pat",
        base_url="https://cloud.uipath.com/acme/Default/",
        access_token="pat-123",
    )
    client = Orchestrator(settings)
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


async def test_request_shaping_for_folder_scoped_robots():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["folder"] = request.headers.get("X-UIPATH-OrganizationUnitId")
        return httpx.Response(200, json={"value": []})

    client = _client(handler)
    await client.list_robots(folder_id=7, limit=10)

    assert "/acme/Default/orchestrator_/odata/Robots" in seen["url"]
    assert "GetRobotsFromFolder(folderId=7)" in seen["url"]
    assert "%24top=10" in seen["url"] or "$top=10" in seen["url"]
    assert seen["auth"] == "Bearer pat-123"
    assert seen["folder"] == "7"


async def test_job_metrics_groupby_round_trip():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "groupby((State)" in httpx.QueryParams(request.url.query).get("$apply", "")
        return httpx.Response(200, json={"value": [
            {"State": "Successful", "count": 8},
            {"State": "Faulted", "count": 2},
            {"State": "Running", "count": 1},
        ]})

    client = _client(handler)
    m = await client.compute_job_metrics()
    assert m.total == 11
    assert m.successful == 8 and m.faulted == 2
    assert m.success_rate_pct == 80.0


async def test_real_retry_loop_recovers_from_429(monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "1"}, text="slow down")
        return httpx.Response(200, json={"value": [], "@odata.count": 0})

    client = _client(handler)
    total = await client._count("/odata/Jobs")
    assert total == 0
    assert calls["n"] == 2  # one 429, then success


async def test_error_body_is_trimmed_and_typed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="<html>" + "x" * 4000 + "</html>")

    client = _client(handler)
    with pytest.raises(OrchestratorError) as exc:
        await client._call("GET", "/odata/Jobs")
    assert exc.value.status_code == 400
    assert "truncated" in str(exc.value)
