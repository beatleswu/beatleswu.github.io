# PR #55 Deploy-Day Verification Checklist

**DEPLOYMENT STATUS: OWNER-GATED — DO NOT EXECUTE**

This document is a preparation checklist only. It does not authorize running
`deploy-release-image.ps1 -Execute`, `rollback-release.ps1 -Execute`, or any
other Production-mutating command. Execution requires the owner to give an
explicit go-ahead at the time of the actual deploy attempt, per
[ADR-0001](../architecture/ADR-0001-canonical-repository-and-deployment.md)
("merge and deployment are separate, owner-gated operations").

## Confirmed Live Topology (read-only, verified 2026-07-11)

- compose file: `/opt/go-odyssey/docker-compose.prod.yml`
- working dir: `/opt/go-odyssey`
- single compose file: confirmed (no comma-separated multi-`-f` label) —
  `rollback-release.ps1`'s `-f $rollbackComposeFile` assumption is safe.
- current running image (both app and scheduler): `go-odyssey-app:latest`,
  `sha256:f9a876e888be8e2ee43872c97e5ecfb81afb06b9aa226309fdb022f632b60cfd`
- Postgres: `go-odyssey-postgres` (`postgres:16-alpine`), independent container,
  never targeted by deploy/rollback compose commands as long as `--no-deps`
  is present (confirmed present in all four `compose up --force-recreate`
  call sites in `deploy-release-image.ps1` and `rollback-release.ps1`).

## Target Release Identity (PR #55 artifact)

- image tag: `go-odyssey-app:23d1fab2`
- image ID: `sha256:523faa7b773675dadebf825b586da790995a7bc88f51bb9245371e7eaeba5ee3`
- platform: `linux/arm64`
- OCI revision: `23d1fab2f2e82a0c24bc2a709eacae24b4831dfb`

Re-verify these three values against the current release manifest before
proceeding — do not assume they are still current without checking.

---

## 1. Pre-Deploy Read-Only Baseline

- [ ] External HTTP: `/healthz`, `/login`, `/` all return 200
- [ ] `go-odyssey-app`, `go-odyssey-scheduler`: healthy, 0 restarts
- [ ] `go-odyssey-postgres`: healthy, 0 restarts, untouched uptime
- [ ] `questions.json` inside app container: parses, record count matches
      last known good baseline (41591 at last check — confirm current count)
- [ ] No leftover `go-odyssey-candidate-*` or `*-diag-*` containers running
- [ ] `git rev-parse origin/master` matches the SHA the release manifest was
      built from
- [ ] Working tree on the machine running the deploy tooling is clean
      (tracked files) — `Test-TrackedTreeClean` / `Assert-TrackedTreeClean`

## 2. Exact Artifact Confirmation

- [ ] Release manifest `release_git_sha` matches the intended PR #55 merge
      commit SHA
- [ ] Local image `docker image inspect go-odyssey-app:23d1fab2` → image ID
      matches manifest `image_id`
- [ ] Local image platform is `linux/arm64`
- [ ] Local image `org.opencontainers.image.revision` label matches
      `release_git_sha`
- [ ] Release archive SHA-256 matches manifest `archive_sha256`
- [ ] `deploy-release-image.ps1` dry-run (no `-Execute`) passes and echoes
      the same identity values above

## 3. Canary Verification (no public traffic)

Run only as part of the actual deploy attempt (`-Execute -OwnerGate GO_DEPLOY`),
not standalone against Production containers.

- [ ] Candidate canary container starts and reports `public_traffic_attached: false`
- [ ] Candidate canary reports `scheduler_started: false`
- [ ] Candidate canary image ID matches expected release image ID
- [ ] Candidate canary healthcheck test is canonical exec form
      (`CMD python -c ... 127.0.0.1:8080/healthz`)
- [ ] Candidate canary state is `running`, health is `healthy` or
      `no-healthcheck`
- [ ] Candidate canary runtime readiness report: `readiness_mode = helper`,
      `readiness.ok = true`
- [ ] Candidate canary questions gate passes (`Assert-QuestionsReportSatisfiesGate`)
- [ ] Candidate canary container-local HTTP: `/healthz`, `/login`, `/` all 200
- [ ] Candidate canary daily-challenge endpoint is not 503
- [ ] On failure at this stage: canary is removed, **no rollback needed**
      because nothing on the real app/scheduler was touched yet

## 4. Formal App Switch — Post-Switch Health

- [ ] App container image tag/ID match the release manifest exactly
- [ ] App container healthcheck test is canonical exec form
- [ ] App container health reaches `healthy` (script waits up to 120s —
      do not manually interrupt this wait)
- [ ] App runtime readiness (`readiness_mode = helper`) reports `ok = true`
- [ ] Questions gate passes on the live app container
- [ ] Public `/healthz`, `/login`, `/` all return 200
- [ ] Daily challenge endpoint is not 503
- [ ] Scheduler switch only proceeds after the above all pass
- [ ] Scheduler container image ID matches app container image ID exactly
- [ ] nginx restarted, no stale upstream IP (per known nginx gotcha)

## 5. Gameplay Smoke Test (manual, browser-driven)

Not automated by the release scripts — must be performed by hand against the
live site after the formal switch, before declaring acceptance.

- [ ] Practice/Adventure board renders correctly
- [ ] A move/answer can be submitted (Review POST succeeds, no error toast)
- [ ] **Board remains visible after answering** — does not blank out or
      unmount
- [ ] **Question advances normally** to the next item after a correct/incorrect
      answer
- [ ] Answer/progress persistence: reload the page, prior state is retained
      as expected (not silently reset)
- [ ] Browser console: **`pageerror` count is 0** for the smoke session
- [ ] Browser console: no uncaught blocking JS errors during board render,
      answer submission, or question advance
- [ ] No `null.style` or similar DOM-access exceptions in console

## 6. Feature-Area Spot Checks

- [ ] Daily Challenge: loads, does not 503, one challenge can be opened
- [ ] SRS (spaced repetition) queue: loads without error, one review item
      answerable
- [ ] Shadow Dashboard: loads, shows recent shadow-judging events (no blank
      page, no traceback)
- [ ] `shadow_judging.py --selftest` on the live app container reports
      `SELFTEST OK (10/10)`
- [ ] App container logs (`docker logs --tail 400`) contain no
      `premium_weekly_job` references or Python tracebacks

## 7. Container / Infra State Confirmation

- [ ] `go-odyssey-app`: running, healthy, correct image
- [ ] `go-odyssey-scheduler`: running, correct image, same image ID as app
- [ ] `go-odyssey-postgres`: **unchanged** — same container ID and uptime as
      pre-deploy baseline (i.e. it was never recreated)
- [ ] `go-odyssey-nginx`: running after restart, serving 200s

## 8. QUESTIONS_JSON_PATH / Dataset Readiness

- [ ] `QUESTIONS_JSON_PATH` env var on the app container resolves to the
      expected mount destination from the release layout
- [ ] File at that path exists, is readable, parses as a non-empty JSON list
- [ ] Structural record check passes (sampled records have `id` / `source` /
      `content` / `sgf` populated)
- [ ] Record count is consistent with the pre-deploy baseline (no silent
      truncation)

## 9. Rollback Trigger Conditions

Automatic rollback fires (via the deploy script's catch block) once
`$rollbackRequired` flips true — i.e. **after** the formal app switch begins.
Any of the following after that point must result in rollback, not a retry:

- [ ] App container fails to reach `healthy` within the wait timeout
- [ ] App/scheduler image ID mismatch against the release manifest
- [ ] Any required HTTP gate (`/healthz`, `/login`, `/`) fails
- [ ] Daily challenge returns 503
- [ ] Runtime readiness helper reports `ok != true`
- [ ] Questions gate fails (missing/empty/unparseable/structurally invalid)
- [ ] `verify-production-release.ps1` throws for any reason
- [ ] Manual owner decision to abort, even if all automated gates pass

Do **not** attempt a second live `-Execute` deploy immediately after a
failure to "just try again" — that pattern is what turned the previous
incident into a multi-hour outage. Stop, capture evidence, decide manually.

## 10. Post-Rollback Verification

- [ ] Rollback script restored app first, verified healthy, **then**
      restored scheduler (not simultaneously)
- [ ] App and scheduler both report the rollback image tag/ID, matching
      each other
- [ ] Rollback used the compose file/working dir derived from the live
      scheduler's compose labels — not a hardcoded `docker-compose.release.yml`
      path (this was the root cause of the questions.json loss during the
      last incident)
- [ ] Postgres was not recreated during rollback (`--no-deps` present in the
      rollback compose commands, confirmed in current script)
- [ ] Public `/healthz`, `/login`, `/` return 200 post-rollback
- [ ] Questions gate passes post-rollback
- [ ] `verify-production-release.ps1` run against the rollback identity
      succeeds

## 11. Final Production Acceptance Judgment

Deploy is **ACCEPTED** only if ALL of the following hold simultaneously:

- [ ] App and scheduler both run `go-odyssey-app:23d1fab2` /
      `sha256:523faa7b773675dadebf825b586da790995a7bc88f51bb9245371e7eaeba5ee3`
- [ ] `verify-production-release.ps1` completed with no thrown errors
- [ ] Gameplay smoke test (Section 5) fully passed, including board
      persistence, question advance, and zero `pageerror`
- [ ] Feature-area spot checks (Section 6) all passed
- [ ] No rollback was triggered

If rollback was triggered at any point, the final state is **FAILED —
ROLLED BACK**, regardless of how far the deploy progressed, and PR #55 is
not considered deployed. Re-attempting deploy after a failure requires a
fresh owner `GO_DEPLOY` decision, not an automatic retry.
