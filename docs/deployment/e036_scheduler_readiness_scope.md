# E036 scheduler readiness scope

Status: implementation candidate for release-tooling review. This change is
limited to `scripts/release/preflight-production.ps1`; it does not deploy,
enable a feature, run a migration, or change application runtime code.

## Finding

The standalone scheduler entrypoint is `scheduler.py`. It imports `app`,
calls `app.init_db()`, starts the premium and community scheduler hooks, and
then idles. The app deployment-readiness helper is not the scheduler's
readiness contract: `_read_runtime_deployment_readiness()` also validates the
questions dataset, live static root, and shadow-event path. Those are app
paths and are not consumed by `scheduler.py` or by its current scheduler
hooks.

E036 therefore adds a role-specific, read-only
`Get-RemoteSchedulerReadinessReport` probe. The app continues to use the
E035 helper/fallback path. The scheduler probe does not call `init_db()` or a
reward cycle, and does not enumerate container environment variables.

## Readiness-field classification

The classification is role-specific where the same report shape is used for
both processes.

| Readiness field | App | Scheduler | Evidence / boundary |
|---|---|---|---|
| `app.git_sha`, `app.image_revision` | `SHARED_REQUIRED` | `SHARED_REQUIRED` | Each container must expose release identity for provenance; no secret or full environment is emitted. |
| `app.build_date`, `app.questions_json_commit` | `APP_REQUIRED` | `NOT_REQUIRED` | App release/content evidence; the standalone scheduler does not load the question dataset. |
| `questions` | `APP_REQUIRED` | `NOT_REQUIRED` | App helper checks dataset existence, parsing, count, and structure. Scheduler has no question-read path. |
| `static_root` | `APP_REQUIRED` | `NOT_REQUIRED` | App serves live static content; scheduler serves no HTTP/static content. |
| `shadow_events` | `APP_REQUIRED` | `NOT_REQUIRED` | App shadow-event readiness is not a scheduler entrypoint/job dependency. |
| `database.identity` | `SHARED_REQUIRED` | `SHARED_REQUIRED` | App and scheduler must point at the same server-owned database; only sanitized identity is reported by the outer preflight. |
| `database.reachable` | `SHARED_REQUIRED` | `SHARED_REQUIRED` | Both processes require database connectivity. The scheduler probe uses read-only `SELECT 1`. |
| `database.tables` | `APP_REQUIRED` | `SCHEDULER_REQUIRED` | Each role checks the tables required by its active runtime; scheduler base checks are `users`, `review_log`, and `user_stats`, with community reward tables conditional on the exact enable flag. |
| `scheduler.entrypoint` | `NOT_REQUIRED` | `SCHEDULER_REQUIRED` | `scheduler.py` must be present and importable in the scheduler container. |
| `scheduler.community_job` | `NOT_REQUIRED` | `SCHEDULER_REQUIRED` | The community module and operation path are checked only when `COMMUNITY_LEADERBOARD_REWARDS_ENABLED` is exactly `true`; otherwise the job is explicitly not required. |
| `scheduler.premium_job` | `NOT_REQUIRED` | `SCHEDULER_REQUIRED` | The retired premium scheduler must remain disabled; an exact true-like enablement is a fail-closed readiness failure. |
| `role`, `ok`, `failures` | `SHARED_REQUIRED` | `SHARED_REQUIRED` | The role-specific report and aggregate gate must be explicit; a failing scheduler report is now enforced by the preflight. |

`APP_ONLY_PATHS_NOT_REQUIRED_BY_SCHEDULER=PASS`: the scheduler report marks
`questions`, `static_root`, and `shadow_events` as `required=false` with
`status=not_required`; it does not invoke the app helper that would otherwise
make those paths a scheduler gate.

## Scheduler database and job checks

The probe is intentionally narrower than `app.init_db()`, because a
preflight must remain read-only. It checks:

1. database connectivity with `SELECT 1`;
2. the base scheduler query tables `users`, `review_log`, and `user_stats`;
3. `scheduler.py` presence/importability;
4. the community scheduler module and its operation directory only when the
   exact community flag is enabled;
5. that the unsupported premium scheduler is not enabled.

The conditional community check adds `player_appearance`,
`leaderboard_snapshots`, `leaderboard_reward_claims`, and
`leaderboard_reward_component_log`. It does not run a reward cycle and does
not grant or mutate rewards.

`SCHEDULER_DB_REACHABILITY_CHECK=PASS` and
`SCHEDULER_REQUIRED_PATH_CHECKS=PASS` mean the checks above are represented
in the role-specific probe. They do not claim live Production success; E036
does not access Production.

## Environment boundary

E035's `Get-RemoteExactEnvValue` remains the only exact-key fallback for the
app path. The scheduler probe reads only the individual values needed to
determine release identity, database connection, and scheduler feature
state inside the remote Python process. It never requests
`{{json .Config.Env}}`, never returns the full `.Config.Env` list, and emits
no secret-bearing value.

Required E036 evidence:

```text
FULL_REMOTE_ENV_READ_COUNT=0
APP_FULL_ENV_INSPECT_COUNT=0
SCHEDULER_FULL_ENV_INSPECT_COUNT=0
SECRET_VALUES_OUTPUT=NO
```

The final main preflight now fails closed when the scheduler-specific report
has `ok=false`; it no longer silently ignores a failing scheduler readiness
report.

## Validation boundary

The focused E036 tests exercise the real PowerShell function body with a
sanitized local response seam. They verify role routing, scheduler DB/job
requirements, omission of app-only environment paths, fail-closed report
propagation, and the existing dry-run parse contract. Existing E035 and
release-tooling suites remain required regression gates.

No Production query, deployment, migration, feature enablement, or source
runtime change is part of E036. The next full exact deployment preflight
remains a separate, Owner-gated task after B045 readiness.
