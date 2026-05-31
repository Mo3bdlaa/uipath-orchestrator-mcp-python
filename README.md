# uipath-orchestrator-mcp-python

> Python MCP server for UiPath Orchestrator — drive your automations from Claude Desktop and any MCP-aware agent.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![MCP](https://img.shields.io/badge/MCP-1.x-6E56CF)
![License: MIT](https://img.shields.io/badge/License-MIT-green)

## What is this?

A [Model Context Protocol](https://modelcontextprotocol.io) server that exposes your
UiPath Orchestrator as a set of agent tools. Point Claude Desktop (or Cline, Continue,
or a custom agent) at it and ask, in plain language, to start jobs, inspect failures,
manage queues, and read audit logs — across Cloud, on-prem, and PAT deployments.

It's a **typed async Python client** (29 tools, Pydantic models, three production auth
strategies) wrapped as a **native MCP server** — not a REST wrapper, not a bespoke
integration.

## Why does it exist?

REST APIs aren't MCP servers — an agent can't discover or call them without glue code.
And the MCP servers that do exist don't cover UiPath Orchestrator, especially **on-prem
and sovereign deployments** where most examples stop at SaaS. This fills that gap:
production auth coverage (Cloud OAuth · On-prem · PAT) behind a single MCP surface.

## What you can ask the agent

Once it's connected, these are the kinds of prompts you can send:

- *"Schedule the Invoice Processing job to run weekdays at 9 AM in the Finance folder."*
- *"List all jobs that failed in the last 24 hours, grouped by process, with the error message for the most common failure."*
- *"How many items are pending in the OnboardingEmployees queue, and which robots are configured to process it?"*
- *"Run a one-time execution of the Reconciliation process in the AsiaTenant, then notify me when it finishes."*
- *"Pull yesterday's audit log entries for any folder permission changes."*
- *"Show me the assets defined in the HR folder that look like credentials (don't print their values)."*
- *"Give me a health snapshot of the Production folder — job states, queue backlogs, robot availability."*

## Install (Claude Desktop)

**1. Clone and install:**

```bash
git clone https://github.com/Mo3bdlaa/uipath-orchestrator-mcp-python.git
cd uipath-orchestrator-mcp-python
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
```

**2. Add to your `claude_desktop_config.json`:**

```json
{
  "mcpServers": {
    "uipath-orchestrator": {
      "command": "python",
      "args": ["-m", "uipath_mcp_python.server"],
      "env": {
        "UIPATH_URL": "https://cloud.uipath.com/your-org/your-tenant/",
        "UIPATH_AUTH_TYPE": "cloud-oauth",
        "UIPATH_CLIENT_ID": "...",
        "UIPATH_CLIENT_SECRET": "...",
        "UIPATH_TENANT_NAME": "Default"
      }
    }
  }
}
```

Use the **absolute path** to your virtualenv's interpreter for `command` (e.g.
`/path/to/uipath-orchestrator-mcp-python/.venv/bin/python`) so Claude Desktop launches
the server with the dependencies installed. After `pip install -e .` you can also use
the `uipath-mcp` console script instead of `python -m uipath_mcp_python.server`.

Config file location:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Restart Claude Desktop and the `uipath-orchestrator` tools appear in the 🔌 menu.

## Configure auth

Pick the one strategy that matches your deployment. All strategies also need
`UIPATH_URL` and `UIPATH_TENANT_NAME`.

| Use case | `UIPATH_AUTH_TYPE` | Required variables |
|---|---|---|
| Cloud (SaaS Orchestrator) | `cloud-oauth` | `UIPATH_CLIENT_ID`, `UIPATH_CLIENT_SECRET` |
| **On-prem (regulated / sovereign)** | `on-prem` | `UIPATH_USERNAME`, `UIPATH_PASSWORD` |
| Personal scripts / quick prototyping | `cloud-pat` | `UIPATH_PAT` |

**On-prem is the deployment most MCP/UiPath examples never cover** — and it's the one
that matters for regulated and sovereign environments. It's a first-class strategy here,
not an afterthought.

For local development, copy `.env.example` → `.env` and fill in the values instead of
using the `env` block above.

## Tools exposed

The server exposes **29 tools**, grouped by Orchestrator domain:

### Folders & Infrastructure
| Tool | Description |
|---|---|
| `list_folders` | Return Orchestrator folders (organizational units) with pagination. |
| `list_robots` | Return robots registered in the Orchestrator, optionally scoped to a folder. |
| `list_machines` | Return host machines known to the Orchestrator. |
| `list_sessions` | List active robot sessions — which machines are connected and their state. |
| `aggregate_session_states` | Count robots grouped by connection state (Available, Busy, Disconnected …). |
| `count_entities` | Total counts of top-level entities (processes, assets, queues, schedules). |

### Assets
| Tool | Description |
|---|---|
| `list_assets` | List assets (credentials, config values) stored in a folder. |
| `get_robot_asset` | Retrieve a specific asset value that has been assigned to a robot. |

### Processes & Jobs
| Tool | Description |
|---|---|
| `list_releases` | List published process releases, optionally filtered by key. |
| `query_jobs` | Search for jobs with optional state and process name filters. |
| `inspect_job` | Retrieve full details for a single job by its numeric ID. |
| `start_process` | Trigger execution of a published process by name. |
| `cancel_job` | Request graceful stop (or forced kill) of a running job. |

### Queues
| Tool | Description |
|---|---|
| `list_queues` | List every queue definition in the Orchestrator. |
| `enqueue_item` | Push a new item into a named queue for robot processing. |
| `query_queue_items` | Search queue items with optional filters on queue ID and status. |

### Schedules
| Tool | Description |
|---|---|
| `list_schedules` | List scheduled triggers (cron expressions, next run times). |

### Logs & Audit
| Tool | Description |
|---|---|
| `query_robot_logs` | Retrieve robot execution logs with optional filtering. |
| `query_audit_trail` | Search the audit trail — who changed what and when. |

### Analytics
| Tool | Description |
|---|---|
| `get_job_metrics` | Aggregate job counts by state and compute the overall success rate. |
| `get_queue_metrics` | Compute per-status breakdown and success rate for a queue. |
| `get_faulted_jobs` | Fetch recent faulted jobs for failure analysis. |
| `analyze_process` | Compute success rate and execution statistics for a process. |
| `summarize_folder` | Build a health snapshot of a folder: job states, queue/robot counts. |
| `get_dashboard` | High-level dashboard with aggregated metrics. |

### Licensing
| Tool | Description |
|---|---|
| `get_consumption_license_stats` | Consumption-based license usage statistics. |
| `get_license_stats` | Tenant license usage statistics. |
| `get_runtime_licenses` | Runtime license allocation by robot type. |
| `get_named_user_licenses` | Named-user license allocation by robot type. |

> The tool list above is generated from the docstrings in
> [`uipath_mcp_python/server.py`](./uipath_mcp_python/server.py) — that file is the
> source of truth as tools change.

## Resources (read-only endpoints)

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

## Project structure

```
uipath_mcp_python/
├── schemas.py        # Pydantic models for every Orchestrator entity
├── orchestrator.py   # Async API client with 3 auth strategies
├── settings.py       # Environment-to-config loader
└── server.py         # MCP tool & resource definitions
```

See [`examples/`](./examples) for worked agent interactions, including a multi-step
list-then-schedule flow and an on-prem deployment.

## Development

```bash
pip install -e ".[test]"
pytest          # unit tests — no live Orchestrator required
ruff check uipath_mcp_python/ tests/
```

## License

[MIT](./LICENSE) — free to use, modify, and distribute.

---

Built by [Mohammed Shaker](https://mohammedshaker.com)
