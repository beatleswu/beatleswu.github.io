# Production Runtime Canonicalization Runbook

## Purpose

This runbook covers **one thing only**: safely realigning the production
`go-odyssey-app` and `go-odyssey-scheduler` containers to the ADR-0001
canonical release contract (`docker-compose.release.yml` via
`scripts/release/deploy-release-image.ps1`), after the 2026-07-14
`godokoro.com` 502 incident found them running under a non-canonical
`docker-compose.prod.yml` provenance.

**This is not a Community Rewards enablement runbook.** Community and
Premium scheduler flags remain `disabled` before, during, and after this
realignment. Enabling either is a separate, later, independently
owner-gated piece of work (see Phase C).

## Background

- Root cause of the 502: `.env`'s `POSTGRES_PASSWORD` and the actual
  Postgres role password had drifted apart; deploy/rollback tooling used to
  derive DB credentials by inspecting the *existing* scheduler container's
  live environment, silently propagating the drift forward on every deploy.
  Fixed in `fix/release: stop deriving credentials and compose paths from
  runtime containers` (protected-host-env credential source + fail-closed
  TCP `SELECT 1` preflight; see `scripts/release/ReleaseTooling.psm1`'s
  `Assert-ProtectedHostEnvCredentialAndTcpAuthentication`).
- Separately, a Compose-provenance audit found the live app/scheduler
  containers were created via `docker-compose.prod.yml` (a build/bootstrap
  file, never referenced by the canonical release scripts), not
  `docker-compose.release.yml`. The exact actor and command sequence behind
  that drift were not established during the audit (no `auth.log`/sudo
  access) and remain a separate, open attribution question -- **not**
  something this runbook resolves or needs to resolve to proceed safely.
- `COMMUNITY_LEADERBOARD_REWARDS_ENABLED` was also found unwired in
  `docker-compose.release.yml` (fixed in `fix/release: wire scheduler flags
  with disabled defaults`, default `false`).

---

## Phase A -- Local PR Validation

Everything in this phase runs on the developer workstation against the
repository only. **No SSH to production, no mutation of any kind.**

Allowed:
- Confirm repository identity: working directory is `D:\go-website`, never
  `C:\go-website` (frozen, not a deploy source -- see ADR-0001).
- Confirm `git status --short` shows a clean tracked/index state (pre-existing
  untracked workstation debris is expected and must be left alone; it is not
  part of this change).
- Run the full test suite (`tests/deployment/`, plus this runbook's own
  contract test).
- Run PowerShell parse checks on every changed `.ps1`/`.psm1` file.
- Run `scripts/release/deploy-release-image.ps1` and `rollback-release.ps1`
  in their default dry-run mode (no `-Execute`, no `-OwnerGate`) to inspect
  the `dry_run: true` plan output and the effective `docker compose config`
  for `docker-compose.release.yml`.
- Review the changed-files list against the PR's declared allowlist.

Forbidden in this phase:
- Any SSH command that mutates the production host.
- Merging the PR.
- Deploying.
- Editing production `.env`.
- Running `ALTER ROLE` against production Postgres.
- Running a Community Rewards preview or grant.
- Enabling E9.

---

## Phase B -- Owner-Gated Canonical Realignment

This phase requires the owner to issue, verbatim, the gate string:

```
GO_DEPLOY — PRODUCTION RUNTIME CANONICALIZATION
```

This gate authorizes **exactly one outcome**: app and scheduler running
under the canonical `docker-compose.release.yml` contract, with the same
application code/image identity they already had. It is a runtime-contract
correction, not a feature deploy.

In scope:
- Recreate `app` and `scheduler` via `scripts/release/deploy-release-image.ps1`
  using `docker-compose.release.yml`.
- Preserve the already-authorized image identity (same Git SHA / image ID
  presently running) -- this is a realignment, not a code upgrade. If the
  currently-authorized release manifest points at a different image than
  what's live, that discrepancy must be resolved and re-confirmed with the
  owner before proceeding; this runbook does not authorize a silent image
  change.
- Use the protected host env (`production_env_path` from the release
  layout) as the sole DB credential source, gated by the fail-closed TCP
  `SELECT 1` preflight.
- Run the canonical script's existing Nginx upstream refresh step.

Out of scope (must NOT happen during this phase):
- Restarting or recreating the Postgres container.
- Switching the active static generation.
- Enabling `COMMUNITY_LEADERBOARD_REWARDS_ENABLED` or
  `PREMIUM_WEEKLY_SCHEDULER_ENABLED`.
- Enabling E9.
- Anything not listed above.

---

## Phase C -- Future Enablement (explicitly NOT part of this runbook)

The following are separate pieces of work, each requiring its own
independent owner gate, to be planned and executed only after Phase B has
been verified stable:

```
COMMUNITY REWARDS PRODUCTION ENABLEMENT
```

Canonical realignment must never itself set
`COMMUNITY_LEADERBOARD_REWARDS_ENABLED=true`. If a future enablement
runbook exists, it is a different document with its own preview/grant/
idempotency/anti-abuse verification steps -- not this one.

---

## Production Preflight Checklist (before Phase B execution)

### Repository / release identity
- Repo: `D:\go-website` (never `C:\go-website`).
- Branch: `master`.
- Expected merge SHA: the exact `origin/master` SHA this realignment PR
  merges into -- read fresh via `git rev-parse origin/master` at gate time,
  never assumed from memory of an earlier session.
- Tracked/index: clean.

### Authorized application image
Record and verify, all four together (never infer identity from a tag
prefix alone):
- Image tag
- Image ID (`sha256:...`)
- Platform: `linux/arm64`
- Git SHA (`org.opencontainers.image.revision` label)
- Release archive SHA-256
- Release manifest SHA-256

### Protected host env
- `production_env_path` in the release layout matches the actual path used
  on the host.
- File exists, is a regular file (not a symlink), with an owner/group/mode
  consistent with prior known-good state on this host.
- Do not print its contents.
- `COMMUNITY_LEADERBOARD_REWARDS_ENABLED` absent or not exactly `true`.
- `PREMIUM_WEEKLY_SCHEDULER_ENABLED` disabled.
- DB assignments parse safely (no duplicate keys, no CR/LF/NUL, DATABASE_URL
  agrees with the standalone POSTGRES_* fields if both present) --
  `Assert-ProtectedHostEnvCredentialAndTcpAuthentication` performs this.
- TCP password `SELECT 1` passes.

If credential validation fails at any point: **stop.** Do not recreate any
container, do not run `ALTER ROLE`, do not fall back to reading the
scheduler/app container's live environment.

### Runtime baseline (record before touching anything)
- App container: ID, image ID, RestartCount, Compose provenance
  (`com.docker.compose.project.config_files`).
- Scheduler container: same four fields.
- Postgres container: ID, RestartCount.
- Nginx container: ID, RestartCount.
- Active static generation.
- `sw.js` `VERSION`.
- Questions count.
- W28 claims count.
- W28 component log count.
- `COMMUNITY_LEADERBOARD_REWARDS_ENABLED` effective value.
- `PREMIUM_WEEKLY_SCHEDULER_ENABLED` effective value.
- E9 flag state -- use the existing approved E9 production verification
  procedure; do not invent a new command for this runbook. This is a
  `GO_DEPLOY` precondition: if no such approved procedure is available at
  gate time, stop and resolve that first.
- Public `/healthz`, `/`, `/login` all return `200`.

Record these as **actual values captured at this moment**, not against a
hardcoded historical number from a prior incident report -- the post-deploy
checklist below compares against this baseline, not against any number
fixed in this document.

---

## Realignment Execution Contract

Use only:
- `scripts/release/deploy-release-image.ps1`
- `docker-compose.release.yml`

Never use:
- `docker-compose.prod.yml`
- A manual `docker compose up` outside the canonical script
- `docker restart` as a substitute for a Compose recreate
- The live app/scheduler container's own environment as a credential source

Recreate scope: **`app` and `scheduler` only.**

Postgres: do not restart, do not recreate, do not `ALTER ROLE`, do not run
any migration.

Nginx: use the canonical script's existing upstream-refresh step only; do
not layer a second manual restart on top. After the app is healthy,
re-verify public HTTP -- container-`healthy` is not sufficient proof by
itself (see the 2026-07-14 incident, where the app was healthy but Nginx
still 502'd on a stale upstream IP until it was refreshed).

Static: do not switch the active generation.

Rewards: do not run a preview, do not grant, do not create any new claim or
component-log entry.

E9: do not modify E9 code, do not enable it. Flags must read the same
before and after this realignment.

---

## Post-Deploy Verification Checklist

Verify across **multiple health-check intervals**, not a single
point-in-time `healthy` read.

### Container health
- App: healthy.
- Scheduler: stable (no crash-loop).
- RestartCount for app/scheduler does not increase during the observation
  window.
- Postgres container ID unchanged; RestartCount unchanged.
- Nginx: healthy/running.

### Public HTTP
- `/healthz` = 200
- `/` = 200
- `/login` = 200

### Canonical provenance (primary success condition for this runbook)
Confirm, for both app and scheduler:

```
com.docker.compose.project.config_files == <compose_directory>/docker-compose.release.yml
```

Also record `com.docker.compose.project`, `com.docker.compose.service`,
container ID, and image ID for both.

### Data invariants
Compare against the **pre-deploy baseline captured in this run** (see
Preflight Checklist above), not a number hardcoded in this document:
- Questions count unchanged.
- W28 claims count unchanged.
- W28 component log count unchanged.
- No new reward claim or component-log entry created.

### Scheduler flags
- `COMMUNITY_LEADERBOARD_REWARDS_ENABLED`: absent or not exactly `true`.
- `PREMIUM_WEEKLY_SCHEDULER_ENABLED`: disabled.

Check both the protected host `.env` **and** the live scheduler container's
effective environment -- `.env` alone is not sufficient proof, since a
compose-wiring gap (exactly what Commit 3 of this PR fixed) can leave a
`.env` value never actually reaching the running container.

### E9
- E9 flags before this realignment == E9 flags after.
- Production state: all `false`.
- The legacy Adventure experience remains available (E9 was not force-cut
  over as a side effect of this realignment).

### Static
- Active generation unchanged.
- `sw.js` `VERSION` unchanged.

---

## Rollback Gate

Do not roll back on a single failed HTTP request alone. First confirm:
- App/scheduler container health
- DB authentication status
- Nginx upstream state
- Image identity
- Compose provenance

If rollback is genuinely required:
- Use only `scripts/release/rollback-release.ps1`.
- Use only `docker-compose.release.yml` -- rollback must never fall back to
  a snapshot's recorded `compose_config_files` as the executable path (this
  is exactly the drift-perpetuation bug fixed in Commit 2 of this PR).
- Use the current protected host env; pass the same fail-closed TCP
  preflight before any mutation.
- Do not touch Postgres.
- After rollback, re-run the Nginx refresh and the full post-deploy
  verification checklist above.

Rollback must never leave the runtime back on `docker-compose.prod.yml`.

---

## Stop Conditions

Stop immediately -- do not proceed, do not improvise a fix -- if any of the
following is true:

- The canonical repo or expected merge SHA does not match what's actually
  on `origin/master` at gate time.
- The authorized image identity (tag/ID/platform/Git SHA/archive SHA-256/
  manifest SHA-256) does not match across all sources.
- The protected host env fails any structural safety check.
- TCP password authentication fails.
- `COMMUNITY_LEADERBOARD_REWARDS_ENABLED` or `PREMIUM_WEEKLY_SCHEDULER_ENABLED`
  is found enabled anywhere in the pipeline.
- Postgres is unhealthy, or its RestartCount changes during this run.
- The canonical script attempts to touch the Postgres container in any way.
- Anything would switch the active static generation.
- E9 flags are not in the expected (all-off) state.
- W28 counts were already anomalous before this deploy even started.
- `docker compose config`'s effective output for app/scheduler shows an
  unreviewed difference from what this PR's diff describes.

On any stop condition:
- Stop.
- Do not self-repair the database.
- Do not edit `.env`.
- Do not fall back to `docker-compose.prod.yml`.
- Do not enable rewards.
- Escalate to the owner with the specific stop condition that triggered.
