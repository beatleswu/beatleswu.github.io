# Evidence note: `community_leaderboard_weekly` fails closed every 60s

**Status:** OPEN — evidence only, deliberately NOT fixed here.
**Raised by:** GO_ODYSSEY_GNUGO_GTP_PROCESS_STARVATION_HARDENING_004.
**Source incident:** GO_ODYSSEY_PRODUCTION_504_POST_RECOVERY_ROOT_CAUSE_ANALYSIS_003.

This is an **independent defect** found while investigating the 2026-09-03 504
incident. It was explicitly kept out of the GnuGo hardening patch so two
unrelated failures do not share one `app.py` change.

## Observation

Production app container log, boot `f63bc045`, image `go-odyssey-app:959c3842`:

```
[2026-09-03 00:15:03,972] ERROR in community_leaderboard_rewards_scheduler:
  [community_leaderboard_weekly]
  {"exception_type":"ValueError","job":"community_leaderboard_weekly",
   "period_key":"2026-W35","result":"failed_closed"}
```

| Fact | Value |
| --- | --- |
| First occurrence | 2026-09-03T00:15:03Z (container boot) |
| Last observed | 2026-09-03T20:20:43Z (restart boundary) |
| Occurrences | 1215 |
| Cadence | once per ~60s, constant, ~180ms drift per iteration |
| Period key | `2026-W35` (unchanged throughout) |
| Result | `failed_closed` — rewards are **not** being issued |

Runs in both the app and scheduler containers: `app.py`
`_start_community_leaderboard_weekly_scheduler()` starts a daemon `worker()`
that calls `run_community_leaderboard_weekly_cycle`, catches `Exception`, logs,
sleeps `SCHEDULER_WAKE_INTERVAL_SECONDS`, and repeats forever.

## Relationship to the 504 incident: CORRELATED_ONLY

Explicitly **not** the cause of the outage:

- It began at container boot, **11h 8m before** the first 504 (11:23:36Z).
- Its rate and drift were unchanged before, during and after the incident.
- No accumulation curve matches incident onset; 1215 iterations do not map onto
  the 124 observed CLOSE_WAIT sockets.
- The outage was root-caused to GnuGo GTP hub starvation (task 004), which is
  fixed separately.

## Why it still matters

The weekly leaderboard reward cycle for `2026-W35` has been failing closed
continuously. Failing closed is the safe direction — no incorrect rewards are
issued — but it means **no rewards are being issued at all** for that period,
and the condition is self-perpetuating rather than self-healing. The retry loop
will keep failing every 60s indefinitely.

## What the next task needs to determine

1. The exact `ValueError` site and message inside
   `run_community_leaderboard_weekly_cycle` (the handler logs
   `exception_type` only, so the message and traceback are not currently
   captured — the log call may need widening first).
2. Whether `period_key` `2026-W35` is malformed, unresolvable, or missing
   backing data.
3. Whether any prior period also failed closed, i.e. how many weeks of rewards
   are outstanding.
4. Whether the 60s retry cadence is correct for a *weekly* job, or whether it
   should back off — 1440 failed attempts/day produce no progress and bury the
   log.

## Constraints carried forward

- `COMMUNITY_LEADERBOARD_CHANGED=NO` in task 004; nothing here has been
  modified.
- Any fix is an `app.py` / `community_leaderboard_rewards_scheduler` change and
  needs its own single-writer slot.
