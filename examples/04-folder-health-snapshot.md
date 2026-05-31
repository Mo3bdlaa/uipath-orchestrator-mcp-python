# 04 — Folder health snapshot (multiple domains)

A single prompt that pulls jobs, queues, and robots together into one health view.

## Prompt

> "Give me a health snapshot of the Production folder — job states, queue backlogs, and
> robot availability."

## Tools the agent picks

1. `summarize_folder` — the one-shot rollup: job states + queue/robot counts.

   ```json
   { "folder_id": 3 }
   ```

2. `aggregate_session_states` — robot availability across the tenant.

   ```json
   {}
   ```

## Expected response shape

```json
{
  "folder": "Production",
  "jobs": { "Running": 6, "Successful": 412, "Faulted": 9, "Pending": 2 },
  "queues": { "total": 11, "backlogged": ["Invoices", "Onboarding"] },
  "robots": { "total": 14, "Available": 8, "Busy": 5, "Disconnected": 1 }
}
```

The agent reports: *"Production looks healthy: 6 jobs running, 9 faulted today. Two queues
are backlogged (Invoices, Onboarding). 8 of 14 robots are available, 1 disconnected —
worth a look."*
