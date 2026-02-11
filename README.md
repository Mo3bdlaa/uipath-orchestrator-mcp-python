# UiPath Orchestrator — Python MCP Server

A Model Context Protocol server that connects AI assistants to your UiPath Orchestrator.
Built with Python's `asyncio` ecosystem for clean, typed, and testable automation management.

## Authentication

Three strategies are supported — pick the one that matches your Orchestrator deployment:

| Strategy | `UIPATH_AUTH_TYPE` | Required variables |
|---|---|---|
| **Cloud OAuth** (default) | `cloud-oauth` | `UIPATH_CLIENT_ID`, `UIPATH_CLIENT_SECRET` |
| **On-premises** | `on-prem` | `UIPATH_USERNAME`, `UIPATH_PASSWORD` |
| **Personal Access Token** | `cloud-pat` | `UIPATH_PAT` |

All strategies also require `UIPATH_URL` (your Orchestrator root URL).

## Quick Start

```bash
# 1. Clone and enter the project
cd uipath_mcp_python

# 2. Create a virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and fill in your credentials
copy .env.example .env  # then edit .env

# 5. Run the MCP server
python src/server.py
```

## Configuration

Copy `.env.example` → `.env` and fill in the values:

```env
UIPATH_AUTH_TYPE=cloud-oauth       # or: on-prem, cloud-pat
UIPATH_URL=https://cloud.uipath.com/your-org/your-tenant/
UIPATH_TENANT_NAME=Default

# Cloud OAuth
UIPATH_CLIENT_ID=...
UIPATH_CLIENT_SECRET=...

# On-prem (uncomment if using)
# UIPATH_USERNAME=admin
# UIPATH_PASSWORD=...

# PAT (uncomment if using)
# UIPATH_PAT=rt_...
```

| Variable | Description |
|---|---|
| `UIPATH_FOLDER_ID` | Default Organizational Unit for API calls |
| `UIPATH_DISABLE_SSL_VERIFY` | Set `1` to skip TLS checks (dev only) |

## Available Tools

The server exposes **29 tools** across these domains:

### Folders & Infrastructure
- `list_folders` — Orchestrator folders (organizational units)
- `list_robots` — Registered robots
- `list_machines` — Host machines
- `list_sessions` — Active robot connections
- `list_assets` — Credentials and config values
- `get_robot_asset` — Asset value assigned to a specific robot

### Processes & Jobs
- `list_releases` — Published process packages
- `query_jobs` — Search jobs by state / process
- `inspect_job` — Full details for a single job
- `start_process` — Trigger a process by name
- `cancel_job` — Stop or kill a running job
- `list_schedules` — Scheduled triggers

### Queues
- `list_queues` — Queue definitions
- `enqueue_item` — Push data into a queue
- `query_queue_items` — Search items by status

### Analytics & Monitoring
- `get_job_metrics` — Job counts by state + success rate
- `get_queue_metrics` — Queue item breakdown + success rate
- `get_faulted_jobs` — Recent failures
- `analyze_process` — Process success rate over recent runs
- `summarize_folder` — Health snapshot of a folder
- `get_dashboard` — Aggregated dashboard metrics
- `count_entities` — Top-level entity counts
- `aggregate_session_states` — Robot states breakdown

### Logs & Audit
- `query_robot_logs` — Execution logs with filtering
- `query_audit_trail` — Who changed what and when

### Licensing (stubs)
- `get_consumption_license_stats`
- `get_license_stats`
- `get_runtime_licenses`
- `get_named_user_licenses`

## Resources (Read-only Endpoints)

| URI | Description |
|---|---|
| `orchestrator://folders` | All folders |
| `orchestrator://robots` | All robots |
| `orchestrator://machines` | All machines |
| `orchestrator://queues` | Queue definitions |
| `orchestrator://jobs/recent` | Last 20 jobs |
| `orchestrator://releases` | Published processes |
| `orchestrator://dashboard` | Dashboard metrics |
| `orchestrator://sessions` | Active sessions |
| `orchestrator://assets` | Stored assets |
| `orchestrator://schedules` | Configured schedules |

## MCP Client Configuration

Add to your MCP client (e.g. Claude Desktop) settings:

```json
{
  "mcpServers": {
    "uipath": {
      "command": "python",
      "args": ["src/server.py"],
      "cwd": "/path/to/uipath_mcp_python"
    }
  }
}
```

## Project Structure

```
src/
├── schemas.py        # Pydantic models for every Orchestrator entity
├── orchestrator.py   # Async API client with 3 auth strategies
├── settings.py       # Environment-to-config loader
└── server.py         # MCP tool & resource definitions
```

## License

Proprietary — see [LICENSE](./LICENSE) for details.
