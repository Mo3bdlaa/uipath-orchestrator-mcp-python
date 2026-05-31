# 03 — On-prem queue health (on-prem deployment)

This server treats on-prem as a first-class deployment. The only difference from Cloud
is the auth config — the tools and prompts are identical.

## Setup (`on-prem` auth)

`claude_desktop_config.json` env block, or a local `.env`:

```env
UIPATH_AUTH_TYPE=on-prem
UIPATH_URL=https://orchestrator.corp.internal/
UIPATH_TENANT_NAME=Default
UIPATH_USERNAME=svc_automation
UIPATH_PASSWORD=...
# Self-signed cert on the internal host? (dev only)
UIPATH_DISABLE_SSL_VERIFY=1
```

## Prompt

> "How healthy is the OnboardingEmployees queue — how many items are pending, and what's
> the success rate?"

## Tools the agent picks

1. `query_queue_items` — pending backlog.

   ```json
   { "queue_id": 17, "status": "New", "folder_id": 7, "limit": 1 }
   ```

2. `get_queue_metrics` — per-status breakdown and success rate.

   ```json
   { "queue_name": "OnboardingEmployees", "folder_id": 7 }
   ```

## Expected response shape

```json
{
  "pending": 128,
  "metrics": {
    "queue": "OnboardingEmployees",
    "by_status": { "New": 128, "InProgress": 4, "Successful": 2310, "Failed": 57 },
    "success_rate": 0.976
  }
}
```

The agent reports: *"OnboardingEmployees has 128 items pending and 4 in progress. Over
its history the success rate is 97.6% (57 failed of ~2,370)."*
