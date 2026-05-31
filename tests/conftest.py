"""Shared fixtures for the test suite.

None of these tests touch the network: the ``Orchestrator`` HTTP layer
(``_call``) is mocked, so only client-side logic is exercised.
"""

import pytest

from uipath_mcp_python.orchestrator import Orchestrator
from uipath_mcp_python.schemas import OrchestratorSettings


def make_settings(**overrides) -> OrchestratorSettings:
    """Build settings with sensible defaults, overridable per test."""
    defaults = dict(
        auth_strategy="cloud-oauth",
        base_url="https://cloud.uipath.com/acme/Default/",
        tenant="Default",
        client_id="cid",
        client_secret="secret",
    )
    defaults.update(overrides)
    return OrchestratorSettings(**defaults)


@pytest.fixture
def make_client():
    """Factory that yields Orchestrator instances and closes them afterwards."""
    created: list[Orchestrator] = []

    def _factory(**overrides) -> Orchestrator:
        client = Orchestrator(make_settings(**overrides))
        created.append(client)
        return client

    yield _factory

    for client in created:
        # AsyncClient.aclose is async; closing the underlying transport
        # synchronously is enough to avoid resource warnings in tests.
        client._http._transport = None  # type: ignore[attr-defined]
