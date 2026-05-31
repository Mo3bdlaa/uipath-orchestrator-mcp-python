# 02 — List, then schedule (multi-step)

The agent can't schedule a process it can't name. This scenario shows the
discover-then-act pattern: list releases to resolve the exact process, confirm there's
no conflicting schedule, then trigger it.

## Prompt

> "Run the Reconciliation process once in the Finance folder, but first check it isn't
> already scheduled to run in the next hour."

## Tools the agent picks

1. `list_releases` — resolve the process name to a real release in the folder.

   ```json
   { "folder_id": 42 }
   ```

2. `list_schedules` — check for an imminent scheduled run.

   ```json
   { "folder_id": 42, "limit": 50 }
   ```

3. `start_process` — only if no conflicting schedule was found.

   ```json
   { "process_name": "Reconciliation", "folder_id": 42, "count": 1 }
   ```

## Expected response shape

```json
{
  "release": { "Name": "Reconciliation", "Key": "f9e8...", "ProcessKey": "Reconciliation" },
  "conflicting_schedule": null,
  "started": { "Id": 90999, "State": "Pending", "Source": "Manual" }
}
```

The agent reports: *"No schedule fires in the next hour, so I started a one-time run of
Reconciliation in Finance — job 90999 is Pending."* If a schedule had been found, it
would pause and ask before launching.
