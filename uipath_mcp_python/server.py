"""
UiPath Orchestrator — MCP Server

Exposes the full Orchestrator API surface as MCP tools and resources,
allowing AI assistants to manage automations, queues, robots and more.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

import json

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .settings import build_settings
from .orchestrator import Orchestrator

# ── bootstrap ───────────────────────────────────────────────
settings = build_settings()
client = Orchestrator(settings)
mcp = FastMCP("UiPath Orchestrator MCP", dependencies=["httpx", "pydantic"])

# Annotation presets so hosts can distinguish safe reads from state changes.
# Almost every tool here only reads from Orchestrator; the handful that mutate
# state are flagged so an agent host can gate or confirm them.
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)


def _writes(*, destructive: bool, idempotent: bool) -> ToolAnnotations:
    """Annotation for a tool that changes Orchestrator state."""
    return ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=destructive,
        idempotentHint=idempotent,
        openWorldHint=True,
    )


# ════════════════════════════════════════════════════════════
#  TOOLS — organised by domain
# ════════════════════════════════════════════════════════════


# ── Folders ─────────────────────────────────────────────────

@mcp.tool(annotations=READ_ONLY)
async def list_folders(limit: int = 50, skip: int = 0) -> Dict[str, Any]:
    """Return Orchestrator folders (organizational units) with pagination."""
    folders = await client.list_folders(limit=limit, skip=skip)
    return {"folders": [f.model_dump() for f in folders], "count": len(folders)}


# ── Robots & Machines ───────────────────────────────────────

@mcp.tool(annotations=READ_ONLY)
async def list_robots(folder_id: Optional[int] = None, limit: int = 50, skip: int = 0) -> Dict[str, Any]:
    """Return robots registered in the Orchestrator, optionally scoped to a folder."""
    robots = await client.list_robots(folder_id=folder_id, limit=limit, skip=skip)
    return {"robots": [r.model_dump() for r in robots], "count": len(robots)}


@mcp.tool(annotations=READ_ONLY)
async def list_machines(limit: int = 50, skip: int = 0) -> Dict[str, Any]:
    """Return host machines known to the Orchestrator."""
    machines = await client.list_machines(limit=limit, skip=skip)
    return {"machines": [m.model_dump() for m in machines], "count": len(machines)}


# ── Assets ──────────────────────────────────────────────────

@mcp.tool(annotations=READ_ONLY)
async def list_assets(folder_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """List assets (credentials, config values) stored in a folder."""
    assets = await client.list_assets(folder_id=folder_id, limit=limit)
    return [a.model_dump() for a in assets]


@mcp.tool(annotations=READ_ONLY)
async def get_robot_asset(robot_id: int, asset_name: str) -> Dict[str, Any]:
    """Retrieve a specific asset value that has been assigned to a robot."""
    return await client.get_robot_asset(robot_id, asset_name)


# ── Queues ──────────────────────────────────────────────────

@mcp.tool(annotations=READ_ONLY)
async def list_queues(folder_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """List every queue definition in the Orchestrator."""
    queues = await client.list_queues(folder_id=folder_id)
    return [q.model_dump() for q in queues]


@mcp.tool(annotations=_writes(destructive=False, idempotent=False))
async def enqueue_item(
    queue_name: str,
    content: Dict[str, Any],
    folder_id: Optional[int] = None,
    reference: Optional[str] = None,
    priority: str = "Normal",
) -> Dict[str, Any]:
    """Push a new item into a named queue for robot processing."""
    return await client.enqueue_item(
        queue_name, content, priority=priority, reference=reference, folder_id=folder_id
    )


@mcp.tool(annotations=READ_ONLY)
async def query_queue_items(
    queue_id: Optional[int] = None,
    status: Optional[str] = None,
    folder_id: Optional[int] = None,
    limit: int = 50,
    skip: int = 0,
) -> Dict[str, Any]:
    """Search queue items with optional filters on queue ID and status."""
    result = await client.query_queue_items(queue_id=queue_id, status=status, folder_id=folder_id, limit=limit, skip=skip)
    return {"items": [i.model_dump() for i in result["items"]], "total": result["total"]}


@mcp.tool(annotations=READ_ONLY)
async def get_queue_metrics(queue_name: str, folder_id: Optional[int] = None) -> Dict[str, Any]:
    """Compute per-status breakdown and success rate for a queue."""
    m = await client.compute_queue_metrics(queue_name, folder_id=folder_id)
    return m.model_dump()


# ── Jobs ────────────────────────────────────────────────────

@mcp.tool(annotations=READ_ONLY)
async def query_jobs(
    folder_id: Optional[int] = None,
    state: Optional[str] = None,
    release_name: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Search for jobs with optional state and process name filters."""
    jobs = await client.query_jobs(folder_id=folder_id, state=state, release_name=release_name, limit=limit)
    return [j.model_dump() for j in jobs]


@mcp.tool(annotations=READ_ONLY)
async def inspect_job(job_id: int, folder_id: Optional[int] = None) -> Dict[str, Any]:
    """Retrieve full details for a single job by its numeric ID."""
    return await client.inspect_job(job_id, folder_id=folder_id)


@mcp.tool(annotations=_writes(destructive=False, idempotent=False))
async def start_process(
    process_name: str,
    folder_id: Optional[int] = None,
    input_arguments: Optional[Dict[str, Any]] = None,
    count: int = 1,
) -> Dict[str, Any]:
    """Trigger execution of a published process by name."""
    releases = await client.list_releases(folder_id=folder_id)
    match = next((r for r in releases if r.Name == process_name or r.ProcessKey == process_name), None)
    if not match:
        return {"error": f"No release found for '{process_name}'"}
    return await client.launch_process(match.Key, input_args=input_arguments, count=count, folder_id=folder_id)


@mcp.tool(annotations=_writes(destructive=True, idempotent=True))
async def cancel_job(job_id: int, folder_id: Optional[int] = None, force: bool = False) -> Dict[str, Any]:
    """Request graceful stop (or forced kill) of a running job."""
    await client.cancel_job(job_id, force=force, folder_id=folder_id)
    return {"status": "cancel_requested", "job_id": job_id, "strategy": "Kill" if force else "SoftStop"}


@mcp.tool(annotations=READ_ONLY)
async def get_job_metrics(folder_id: Optional[int] = None) -> Dict[str, Any]:
    """Aggregate job counts by state and compute the overall success rate."""
    m = await client.compute_job_metrics(folder_id=folder_id)
    return m.model_dump()


# ── Releases ────────────────────────────────────────────────

@mcp.tool(annotations=READ_ONLY)
async def list_releases(folder_id: Optional[int] = None, process_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """List published process releases, optionally filtered by key."""
    releases = await client.list_releases(folder_id=folder_id, process_key=process_key)
    return [r.model_dump() for r in releases]


# ── Sessions ────────────────────────────────────────────────

@mcp.tool(annotations=READ_ONLY)
async def list_sessions(folder_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """List active robot sessions — shows which machines are connected and their state."""
    sessions = await client.list_sessions(folder_id=folder_id, limit=limit)
    return [s.model_dump() for s in sessions]


# ── Schedules ───────────────────────────────────────────────

@mcp.tool(annotations=READ_ONLY)
async def list_schedules(folder_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """List scheduled triggers (cron expressions, next run times)."""
    schedules = await client.list_schedules(folder_id=folder_id, limit=limit)
    return [s.model_dump() for s in schedules]


# ── Logs ────────────────────────────────────────────────────

@mcp.tool(annotations=READ_ONLY)
async def query_robot_logs(
    folder_id: Optional[int] = None,
    job_key: Optional[str] = None,
    level: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """Retrieve robot execution logs with optional filtering (time range via since/until, ISO-8601)."""
    result = await client.query_robot_logs(
        folder_id=folder_id, job_key=job_key, level=level, since=since, until=until, limit=limit
    )
    return {"entries": [e.model_dump() for e in result["entries"]], "total": result["total"]}


# ── Audit ───────────────────────────────────────────────────

@mcp.tool(annotations=READ_ONLY)
async def query_audit_trail(
    action: Optional[str] = None,
    user: Optional[str] = None,
    component: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
) -> List[Dict[str, Any]]:
    """Search the audit trail — who changed what and when."""
    logs = await client.query_audit_trail(action=action, user=user, component=component, limit=limit, skip=skip)
    return [entry.model_dump() for entry in logs]


# ── Analytics ───────────────────────────────────────────────

@mcp.tool(annotations=READ_ONLY)
async def get_faulted_jobs(folder_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch recent faulted jobs for failure analysis."""
    jobs = await client.get_faulted_jobs(folder_id=folder_id, limit=limit)
    return [j.model_dump() for j in jobs]


@mcp.tool(annotations=READ_ONLY)
async def analyze_process(process_name: str, folder_id: Optional[int] = None, depth: int = 100) -> Dict[str, Any]:
    """Compute success rate and execution statistics for a process."""
    return await client.analyze_process(process_name, folder_id=folder_id, depth=depth)


@mcp.tool(annotations=READ_ONLY)
async def summarize_folder(folder_id: int) -> Dict[str, Any]:
    """Build a health snapshot of a folder: job states, queue/robot counts."""
    overview = await client.summarize_folder(folder_id)
    return overview.model_dump()


@mcp.tool(annotations=READ_ONLY)
async def get_dashboard(folder_id: Optional[int] = None) -> Dict[str, Any]:
    """High-level dashboard with aggregated metrics."""
    return await client.get_dashboard(folder_id=folder_id)


# ── Entity counts & session states ─────────────────────────

@mcp.tool(annotations=READ_ONLY)
async def count_entities() -> Dict[str, int]:
    """Total counts of top-level entities (processes, assets, queues, schedules)."""
    return await client.count_entities()


@mcp.tool(annotations=READ_ONLY)
async def aggregate_session_states() -> Dict[str, int]:
    """Count robots grouped by connection state (Available, Busy, Disconnected …)."""
    return await client.aggregate_session_states()


# ════════════════════════════════════════════════════════════
#  RESOURCES — read-only data endpoints
# ════════════════════════════════════════════════════════════

def _json(data: Any) -> str:
    """Serialize a resource payload as clean, indented JSON text."""
    return json.dumps(data, indent=2, default=str)


@mcp.resource("orchestrator://folders")
async def res_folders() -> str:
    folders = await client.list_folders(limit=100)
    return _json([f.model_dump(mode="json") for f in folders])

@mcp.resource("orchestrator://robots")
async def res_robots() -> str:
    robots = await client.list_robots(limit=100)
    return _json([r.model_dump(mode="json") for r in robots])

@mcp.resource("orchestrator://machines")
async def res_machines() -> str:
    machines = await client.list_machines(limit=100)
    return _json([m.model_dump(mode="json") for m in machines])

@mcp.resource("orchestrator://queues")
async def res_queues() -> str:
    queues = await client.list_queues()
    return _json([q.model_dump(mode="json") for q in queues])

@mcp.resource("orchestrator://jobs/recent")
async def res_recent_jobs() -> str:
    jobs = await client.query_jobs(limit=20)
    return _json([j.model_dump(mode="json") for j in jobs])

@mcp.resource("orchestrator://releases")
async def res_releases() -> str:
    releases = await client.list_releases()
    return _json([r.model_dump(mode="json") for r in releases])

@mcp.resource("orchestrator://dashboard")
async def res_dashboard() -> str:
    return _json(await client.get_dashboard())

@mcp.resource("orchestrator://sessions")
async def res_sessions() -> str:
    sessions = await client.list_sessions(limit=100)
    return _json([s.model_dump(mode="json") for s in sessions])

@mcp.resource("orchestrator://assets")
async def res_assets() -> str:
    assets = await client.list_assets(limit=100)
    return _json([a.model_dump(mode="json") for a in assets])

@mcp.resource("orchestrator://schedules")
async def res_schedules() -> str:
    schedules = await client.list_schedules(limit=100)
    return _json([s.model_dump(mode="json") for s in schedules])


# ── entry point ─────────────────────────────────────────────

def main() -> None:
    """Console-script / ``python -m`` entry point — starts the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
