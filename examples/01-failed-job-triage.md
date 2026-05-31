# 01 — Failed-job triage (jobs + logs)

A cross-domain request: the agent first finds recent failures, then pulls the logs
for the worst offender to surface the actual error.

## Prompt

> "List the jobs that failed recently in the Finance folder, and show me the error
> message from the most recent one."

## Tools the agent picks

1. `get_faulted_jobs` — recent failures, scoped to the folder.

   ```json
   { "folder_id": 42, "limit": 20 }
   ```

2. `query_robot_logs` — logs for the most recent faulted job, error level only.

   ```json
   { "folder_id": 42, "job_key": "a1b2c3d4-...", "level": "Error", "limit": 10 }
   ```

## Expected response shape

```json
{
  "faulted_jobs": [
    { "Id": 90871, "Key": "a1b2c3d4-...", "ReleaseName": "InvoiceProcessing",
      "State": "Faulted", "EndTime": "2025-05-30T18:04:11Z" }
  ],
  "top_failure": {
    "job": "InvoiceProcessing",
    "error": "Selector not found: <wnd app='excel.exe' />",
    "logged_at": "2025-05-30T18:04:09Z"
  }
}
```

The agent summarizes in prose: *"3 jobs faulted in Finance in the last day. The most
recent — InvoiceProcessing (job 90871) — failed on a missing Excel selector at 18:04."*
