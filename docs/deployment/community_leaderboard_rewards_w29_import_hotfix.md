# Community leaderboard rewards W29 import hotfix safety

Status: implementation and review only. This document does not authorize a
merge, deployment, flag change, scheduler restart, preview, grant, retry,
replay, backfill, or Production repair.

## Incident state

The `2026-W29` automatic cycle became due at 2026-07-19 16:10 UTC
(2026-07-20 00:10 Asia/Taipei). Production generated its operation `snapshot.json` and
`preview.json`, then failed closed before database persistence because the
grant modules were imported as top-level modules even though the image packages
them under `tools/`.

W29 remains ungranted. The last read-only Production audit found this exact
zero-state:

- claims: 0;
- database snapshots: 0;
- reward components: 0.

W30 was untouched.

## Deployment hazard

Production currently has `COMMUNITY_LEADERBOARD_REWARDS_ENABLED=true`. The
scheduler polls every 60 seconds and treats an overdue, uncompleted weekly
target as immediately eligible. Correcting the imports therefore arms W29
catch-up: a fixed scheduler can attempt real grants immediately after startup.

Deploy and grant authorization are separate Owner gates. This hotfix must not
be deployed until an Owner-approved execution-control plan prevents an
unreviewed catch-up race. A code review or merge is not `GO_DEPLOY` and is not
`GO_GRANT`.

Immediately before any later authorized recovery, a fresh read-only audit must
reconfirm W29 claims, database snapshots, and components are all zero and that
W30 remains untouched. Operation files or an old preview must not be trusted
blindly: the exact Production preview must be regenerated and reconciled under
the approved recovery plan, followed by idempotency and duplicate checks and a
separate explicit Owner grant authorization.

## Failure observability

Unexpected scheduler exceptions remain fail-closed and roll back the database
transaction. The ERROR event contains only the stable job name, period key,
`failed_closed` result, and exception type. Exception messages and tracebacks
are deliberately excluded because arbitrary downstream errors may contain
recipient, balance, database, or configuration details.
