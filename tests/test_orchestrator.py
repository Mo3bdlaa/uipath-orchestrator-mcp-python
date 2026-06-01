"""Tests for the Orchestrator client's pure logic and computed metrics.

The network layer (``_call``) and the auth handshakes are mocked, so these
tests never reach a live Orchestrator.
"""

import time
import json
from unittest.mock import AsyncMock

import pytest

from uipath_mcp_python.schemas import Job, Session


# ── URL resolution ───────────────────────────────────────────

def test_api_root_on_prem_uses_root(make_client):
    client = make_client(auth_strategy="on-prem", base_url="https://orch.local/",
                         username="u", password="p")
    assert client._api_root == "https://orch.local"


def test_api_root_cloud_appends_orchestrator_when_url_ends_with_tenant(make_client):
    client = make_client(base_url="https://cloud.uipath.com/acme/Default/", tenant="Default")
    assert client._api_root == "https://cloud.uipath.com/acme/Default/orchestrator_"


def test_api_root_cloud_inserts_tenant_when_missing(make_client):
    client = make_client(base_url="https://cloud.uipath.com/acme/", tenant="Default")
    assert client._api_root == "https://cloud.uipath.com/acme/Default/orchestrator_"


def test_api_root_left_alone_when_already_has_orchestrator_segment(make_client):
    url = "https://cloud.uipath.com/acme/orchestrator_"
    client = make_client(base_url=url)
    assert client._api_root == url


def test_identity_endpoint_uses_org_segment(make_client):
    client = make_client(base_url="https://cloud.uipath.com/acme/Default/")
    assert client._identity_endpoint() == "https://cloud.uipath.com/acme/identity_/connect/token"


def test_onprem_auth_endpoint(make_client):
    client = make_client(auth_strategy="on-prem", base_url="https://orch.local/",
                         username="u", password="p")
    assert client._onprem_auth_endpoint() == "https://orch.local/api/account/authenticate"


# ── Token acquisition ────────────────────────────────────────

async def test_pat_token_returned_directly(make_client):
    client = make_client(auth_strategy="cloud-pat", access_token="rt_secret",
                         client_id=None, client_secret=None)
    assert await client._acquire_token() == "rt_secret"


async def test_cached_token_skips_handshake(make_client):
    client = make_client()
    client._token = "cached-token"
    client._token_expiry = time.time() + 10_000
    # If the handshake were called it would explode — proving the cache is used.
    client._oauth_handshake = AsyncMock(side_effect=AssertionError("handshake should not run"))

    assert await client._acquire_token() == "cached-token"


# ── Metrics: jobs ────────────────────────────────────────────

async def test_compute_job_metrics_counts_and_rate(make_client):
    client = make_client()
    # Single $apply groupby round trip returns one row per state.
    grouped = {"value": [
        {"State": "Pending", "count": 2},
        {"State": "Running", "count": 1},
        {"State": "Successful", "count": 8},
        {"State": "Faulted", "count": 2},
    ]}
    client._call = AsyncMock(return_value=grouped)

    m = await client.compute_job_metrics()
    assert client._call.call_count == 1  # not five separate counts
    assert "groupby((State)" in client._call.call_args.kwargs["params"]["$apply"]
    assert m.total == 13
    assert m.successful == 8
    assert m.faulted == 2
    assert m.success_rate_pct == 80.0  # 8 / (8 + 2)


async def test_compute_job_metrics_rate_none_when_nothing_finished(make_client):
    client = make_client()
    client._call = AsyncMock(return_value={"value": []})

    m = await client.compute_job_metrics()
    assert m.total == 0
    assert m.success_rate_pct is None


# ── Metrics: queues ──────────────────────────────────────────

async def test_compute_queue_metrics(make_client):
    client = make_client()

    def fake_call(method, path, *, params=None, body=None, folder_id=None):
        if "$apply" in (params or {}):
            return {"value": [
                {"Status": "New", "count": 3},
                {"Status": "InProgress", "count": 1},
                {"Status": "Successful", "count": 10},
                {"Status": "Failed", "count": 2},
            ]}
        return {"value": [{"Id": 5}]}  # the QueueDefinitions lookup

    client._call = AsyncMock(side_effect=fake_call)

    m = await client.compute_queue_metrics("Invoices")
    assert m.queue_id == 5
    assert m.total == 16
    assert m.successful == 10
    assert m.success_rate_pct == 83.3  # 10 / (10 + 2)
    # Definition lookup + one grouped count = 2 calls, not 1-per-status.
    assert client._call.call_count == 2


# ── Composite analytics ──────────────────────────────────────

async def test_analyze_process_success_rate(make_client):
    client = make_client()
    jobs = [
        Job(Id=1, Key="a", State="Successful", StartTime="t", EndTime="t"),
        Job(Id=2, Key="b", State="Successful", StartTime="t", EndTime="t"),
        Job(Id=3, Key="c", State="Faulted", StartTime="t", EndTime="t"),
        Job(Id=4, Key="d", State="Running"),  # unfinished — excluded from rate
    ]
    client.query_jobs = AsyncMock(return_value=jobs)

    result = await client.analyze_process("Invoices")
    assert result["analyzed"] == 4
    assert result["successful"] == 2
    assert result["success_rate_pct"] == 66.7  # 2 of 3 finished


async def test_analyze_process_handles_no_jobs(make_client):
    client = make_client()
    client.query_jobs = AsyncMock(return_value=[])

    result = await client.analyze_process("Ghost")
    assert result == {"process": "Ghost", "success_rate_pct": 0, "analyzed": 0}


async def test_aggregate_session_states_buckets_by_state(make_client):
    client = make_client()
    client.list_sessions = AsyncMock(return_value=[
        Session(Id=1, State="Available"),
        Session(Id=2, State="Available"),
        Session(Id=3, State="Busy"),
        Session(Id=4, State=None),  # -> "Unknown"
    ])

    assert await client.aggregate_session_states() == {"Available": 2, "Busy": 1, "Unknown": 1}


async def test_get_faulted_jobs_delegates_with_faulted_state(make_client):
    client = make_client()
    client.query_jobs = AsyncMock(return_value=[])

    await client.get_faulted_jobs(limit=10)
    client.query_jobs.assert_awaited_once_with(folder_id=None, state="Faulted", limit=10)


# ── Query construction ───────────────────────────────────────

async def test_query_jobs_builds_combined_filter(make_client):
    client = make_client()
    client._call = AsyncMock(return_value={"value": []})

    await client.query_jobs(state="Running", release_name="Invoices")

    params = client._call.call_args.kwargs["params"]
    assert params["$filter"] == "State eq 'Running' and ReleaseName eq 'Invoices'"


# ── Resilience: retry / 401-refresh ──────────────────────────

def _resp(status, *, json_body=None, headers=None):
    """Build an httpx.Response standing in for a server reply."""
    import httpx
    return httpx.Response(status, json=json_body or {}, headers=headers or {}, request=httpx.Request("GET", "https://x/"))


async def test_call_retries_on_429_then_succeeds(make_client, monkeypatch):
    client = make_client(auth_strategy="cloud-pat", access_token="t", client_id=None, client_secret=None)
    monkeypatch.setattr("asyncio.sleep", AsyncMock())  # don't actually wait

    replies = [_resp(429, headers={"Retry-After": "1"}), _resp(200, json_body={"ok": True})]
    client._http.request = AsyncMock(side_effect=replies)

    result = await client._call("GET", "/odata/Jobs")
    assert result == {"ok": True}
    assert client._http.request.await_count == 2


async def test_call_refreshes_token_once_on_401(make_client, monkeypatch):
    client = make_client()  # cloud-oauth
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    client._oauth_handshake = AsyncMock(return_value=("fresh", time.time() + 1000))
    client._token, client._token_expiry = "stale", time.time() + 1000

    replies = [_resp(401), _resp(200, json_body={"ok": True})]
    client._http.request = AsyncMock(side_effect=replies)

    result = await client._call("GET", "/odata/Jobs")
    assert result == {"ok": True}
    client._oauth_handshake.assert_awaited()  # token was refreshed


async def test_call_raises_after_exhausting_retries(make_client, monkeypatch):
    client = make_client(auth_strategy="cloud-pat", access_token="t", client_id=None, client_secret=None)
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    client._http.request = AsyncMock(return_value=_resp(503))

    with pytest.raises(RuntimeError, match="503"):
        await client._call("GET", "/odata/Jobs", max_retries=2)


# ── Bug fixes / hardening ────────────────────────────────────

async def test_launch_process_serializes_input_arguments_as_json(make_client):
    client = make_client()
    client._call = AsyncMock(return_value={})

    await client.launch_process("release-key", input_args={"a": 1, "b": "x"})

    raw = client._call.call_args.kwargs["body"]["startInfo"]["InputArguments"]
    # Must be valid JSON, not a Python dict repr with single quotes.
    assert json.loads(raw) == {"a": 1, "b": "x"}


async def test_launch_process_omits_input_arguments_when_none(make_client):
    client = make_client()
    client._call = AsyncMock(return_value={})

    await client.launch_process("release-key")

    assert client._call.call_args.kwargs["body"]["startInfo"]["InputArguments"] is None


async def test_query_jobs_escapes_single_quotes(make_client):
    client = make_client()
    client._call = AsyncMock(return_value={"value": []})

    await client.query_jobs(release_name="O'Brien")

    assert client._call.call_args.kwargs["params"]["$filter"] == "ReleaseName eq 'O''Brien'"


async def test_count_entities_counts_each_collection(make_client):
    client = make_client()
    sizes = {
        "/odata/Releases": 5, "/odata/Assets": 3,
        "/odata/QueueDefinitions": 7, "/odata/ProcessSchedules": 2,
    }
    client._call = AsyncMock(side_effect=lambda m, path, **k: {"@odata.count": sizes[path]})

    assert await client.count_entities() == {
        "processes": 5, "assets": 3, "queues": 7, "schedules": 2,
    }


async def test_summarize_folder_populates_releases(make_client):
    client = make_client()

    def fake_call(method, path, *, params=None, body=None, folder_id=None):
        if "GetRobotsFromFolder" in path:
            return {"@odata.count": 4}
        if path == "/odata/QueueDefinitions":
            return {"@odata.count": 6}
        if path == "/odata/Releases":
            return {"@odata.count": 9}
        if path.startswith("/odata/Jobs"):
            return {"@odata.count": 0}
        if path.startswith("/odata/Folders"):
            return {"DisplayName": "Production"}
        return {}

    client._call = AsyncMock(side_effect=fake_call)

    summary = await client.summarize_folder(3)
    assert summary.releases == 9  # was hardcoded 0 before the fix
    assert summary.robots == 4
    assert summary.queues == 6
    assert summary.folder_name == "Production"
