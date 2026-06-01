"""Tests for MCP tool annotations and tool-surface composition.

Importing the server requires valid-looking settings; we inject dummy
cloud-oauth credentials via the environment before import.
"""

import os

os.environ.setdefault("UIPATH_URL", "https://cloud.uipath.com/acme/Default/")
os.environ.setdefault("UIPATH_AUTH_TYPE", "cloud-oauth")
os.environ.setdefault("UIPATH_CLIENT_ID", "cid")
os.environ.setdefault("UIPATH_CLIENT_SECRET", "secret")

from uipath_mcp_python import server  # noqa: E402

WRITE_TOOLS = {"start_process", "enqueue_item", "cancel_job"}


async def _tool_map():
    tools = await server.mcp.list_tools()
    return {t.name: t for t in tools}


async def test_license_stub_tools_are_gone():
    names = set((await _tool_map()).keys())
    for gone in ("get_license_stats", "get_runtime_licenses",
                 "get_consumption_license_stats", "get_named_user_licenses"):
        assert gone not in names


async def test_tool_count_is_25():
    assert len(await _tool_map()) == 25


async def test_write_tools_flagged_not_readonly():
    tools = await _tool_map()
    for name in WRITE_TOOLS:
        ann = tools[name].annotations
        assert ann is not None and ann.readOnlyHint is False, name


async def test_cancel_job_marked_destructive():
    ann = (await _tool_map())["cancel_job"].annotations
    assert ann.destructiveHint is True
    assert ann.idempotentHint is True


async def test_read_tools_are_readonly():
    tools = await _tool_map()
    for name, tool in tools.items():
        if name in WRITE_TOOLS:
            continue
        assert tool.annotations is not None and tool.annotations.readOnlyHint is True, name


async def test_parameterised_resource_templates_registered():
    templates = await server.mcp.list_resource_templates()
    uris = {t.uriTemplate for t in templates}
    assert "orchestrator://folders/{folder_id}/summary" in uris
    assert "orchestrator://queues/{queue_name}/metrics" in uris


def test_every_tool_delegates_to_a_real_client_method():
    """Static guard: every ``client.<x>(...)`` in server.py must exist on Orchestrator.

    Catches drift between the tool layer and the client (typos, removed methods).
    """
    import ast
    import inspect

    from uipath_mcp_python.orchestrator import Orchestrator

    source = inspect.getsource(server)
    referenced = {
        node.func.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "client"
    }
    assert referenced, "expected server.py to call client methods"
    missing = [name for name in referenced if not hasattr(Orchestrator, name)]
    assert not missing, f"server.py calls client methods that do not exist: {missing}"
