# Community rewards controlled W29 recovery

This runbook defines execution control only. It does not authorize Production
access, deployment, preview, grant, retry, replay, backfill, or W30 activity.

## Why the freeze exists

The corrected scheduler can catch up overdue `2026-W29` immediately after
startup. Production's canonical configured value is expected to be
`COMMUNITY_LEADERBOARD_REWARDS_ENABLED=true`. A fixed scheduler must therefore
never start with that value effective before W29 zero-state and the controlled
preview/grant gates are complete.

Three values must not be confused:

- **configured canonical value**: the exact value in the protected host env;
- **temporary deployment override**: the narrow Compose interpolation override
  `COMMUNITY_LEADERBOARD_REWARDS_ENABLED=false`;
- **effective running value**: the value verified inside the scheduler
  container after recreation.

The freeze never edits or prints the protected host env. It verifies that the
configured value is exactly `true`, then temporarily forces `false` through
the reviewed Compose command.

## Owner gates and sequence

`GO_DEPLOY_CONTROLLED_W29` authorizes one canonical deploy with
`-FreezeCommunityLeaderboardRewards`. The operation holds the release lock and
must verify W29 and W30 zero-state plus no W29 advisory lock before mutation.
It then stops and verifies the exact old scheduler, repeats the zero-state and
lock checks from the app container while no scheduler process can race, and
only then recreates the old scheduler on its exact existing image with effective
`false`. It verifies that freeze before it may load or recreate the corrected
app and scheduler. Every corrected-image recreate and automatic rollback uses
the same forced-false override.

After deployment it stops before grant. A fresh exact W29 snapshot and preview
must be reconciled. `GO_GRANT_W29` is a separate authorization for the exact
grant and, only when explicitly included, the resume operation.

Resume uses `resume-community-leaderboard-rewards.ps1`. It requires exact
scheduler image tag and ID, W29 claims present and fully granted, W30 claims,
snapshots, and components absent, and the canonical configured value exactly
`true`. It recreates only
the scheduler, verifies the restored effective value, and never calls preview,
finalize, claim, or reward grant functions.

## Failures and rollback

Any failed precondition aborts before the old scheduler recreation. If failure
occurs after freeze, automatic Community execution remains frozen. Automatic
release rollback receives the same forced-false override; rollback must never
silently restore `true`. Resume always remains a later explicit operation.

Operators must not substitute ad hoc SSH env edits, manual Compose commands,
timing, sleeps, stale previews, or scheduler termination after startup.

## Verification evidence

Before freeze and after deployment record sanitized counts for W29 and W30,
the W29 advisory-lock state, exact app/scheduler identities, scheduler state
and restart count. After each scheduler recreation verify its exact image ID
and the effective Community flag. Do not print environment maps, database URLs,
credentials, recipient data, or preview contents.
