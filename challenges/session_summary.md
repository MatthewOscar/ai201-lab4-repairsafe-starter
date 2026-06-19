# Optional Challenge 3 — Session Summary Every 5 Interactions

After every 5th logged interaction, the auditor appends one aggregate record to
`logs/session_summary.jsonl`. This is the production pattern of keeping rolled-up
metrics alongside the per-interaction record.

## Where it lives

- `config.py`: `SESSION_SUMMARY_FILE = "logs/session_summary.jsonl"`
- `auditor.py`: `_maybe_write_session_summary()`, called at the end of
  `log_interaction()` after the audit line is written.

## Fields in each summary record

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | str | ISO 8601 UTC, when the summary was written |
| `total_interactions` | int | Total interactions logged so far |
| `tier_distribution` | object | Count per tier across the whole log |
| `recent_questions` | array | The 3 most recent questions |

## Design decision: read the log, do not keep a counter

The summary recomputes its state by reading `logs/audit.jsonl`, not by keeping an
in-memory counter. Two reasons:

1. **Correct across restarts.** A counter resets to zero every time the app
   restarts, so it would fire the summary at the wrong points and miscount totals.
   Reading the log means the count is always the true number of interactions.
2. **The log is the record of truth.** Deriving aggregates from the same file
   that holds the per-interaction records guarantees the summary and the detail
   never disagree. This is exactly how production aggregation works: metrics are
   computed from the event log, not tracked in a parallel variable that can drift.

The trigger is `total % 5 == 0` on a positive total, so a summary lands at
interaction 5, 10, 15, and so on. The function never raises; a summary failure
prints a warning and the user-facing answer is unaffected.

## Real run

Starting from a log that already held 7 interactions (including several from
manual app testing), adding 3 more crossed the 10 mark and produced this summary
line:

```
{"timestamp": "2026-06-19T20:07:00.036230Z", "total_interactions": 10, "tier_distribution": {"safe": 4, "caution": 2, "refuse": 4}, "recent_questions": ["How do I install a ceiling fan where a light fixture is?", "Can I add a new outlet to my garage?", "How do I paint a bedroom wall?"]}
```

A console line is also printed when a summary fires:

```
[SUMMARY] 10 interactions | caution=2, refuse=4, safe=4
```

Validation confirmed the summary fired only on the multiple of 5, the tier
distribution summed to the total, and exactly 3 recent questions were captured.
