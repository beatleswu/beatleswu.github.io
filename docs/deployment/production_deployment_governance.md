# Production Deployment Governance

Status: current (supersedes the "PENDING GOVERNANCE AUDIT" language previously in CLAUDE.md)
Reconciled: 2026-07-15
Audit closed by: ADR-0001 "Deployment Governance" section, commit `01af7c2f5` ("DEPLOY-GOV-1")

This document is the operational summary. For the full audit narrative and evidence trail, read
[ADR-0001](../architecture/ADR-0001-canonical-repository-and-deployment.md) and
[canonical_production_deployment_audit.md](canonical_production_deployment_audit.md) (historical).

## Approved entry points

- **Full deployment**: `scripts/release/deploy-release-image.ps1`. Builds/verifies an exact-SHA
  container image, canaries it on the production host before touching live traffic, recreates the
  app and scheduler services, and auto-rolls-back on failure.
- **Static-only deployment**: `scripts/release/deploy-static-release.ps1`. Verifies an
  already-built static bundle/archive against its manifest, uploads a new generation, atomically
  switches the `current` symlink, and restarts the app/scheduler containers (required — a symlink
  switch alone is filesystem-correct but functionally inert on already-running containers, which
  resolve the target once at start; this was discovered live in a real production deploy).
- **Rollback**: `scripts/release/rollback-release.ps1`.
- **`deploy.ps1` does not exist in this repository's tracked history and is absent from the
  production host's container filesystem.** It must never be invented, restored, or guessed at.

## Owner gates

- **GO_MERGE** — authorizes merging a PR into `master`. Never implies deployment.
- **GO_DEPLOY** — authorizes running `deploy-release-image.ps1 -Execute` or
  `deploy-static-release.ps1 -Execute`. Passed via `-OwnerGate GO_DEPLOY`; without `-Execute`, both
  scripts dry-run only and report identity/readiness.
- **GO_ROLLBACK** — authorizes `rollback-release.ps1 -Execute -OwnerGate GO_ROLLBACK`.

Each gate is a separate, explicit owner decision at execution time. A merged PR, a passing test
suite, or the mere existence of these scripts never substitutes for the gate.

## Required preflight

- Canonical repo: `D:\go-website`. `C:\go-website` is archived/non-canonical — never a deploy
  source.
- Deployment source must be the exact `origin/master` SHA the owner named, verified by
  `git rev-parse` against the manifest, not inferred from branch names or local files.
- Tracked working tree and index must be clean before build/package.
- `sw.js` VERSION must be bumped whenever shell-served files change; a pinned test
  (`tests/test_e9_adventure_shell_integration.py::test_sw_version_bumped`) guards this for e9-era
  changes.
- `deploy/runtime-source-provenance.json` entries must byte-match their recorded source commit for
  every non-`sgf_engine` runtime dependency (`tests/deployment/test_runtime_dependency_provenance.py`).
- Target platform: `linux/arm64` (verified by manifest/image inspection, not assumed).
- Full `tests/deployment/*.py` suite must pass before build. **There is no CI that runs this
  automatically** — it must be run manually before every deploy attempt.

## Static alignment

Three identities must independently agree, verified by byte size, SHA-256, HTTP status, and
Content-Type — not by symlink presence alone:

1. Host's current static generation (the target of the `current` symlink).
2. Static files visible inside the running app container.
3. Public HTTPS response identity.

Container recreation is required after any static-generation switch — verify all three only after
recreation, not immediately after the symlink switch.

## Prohibited actions

- Inventing, restoring, or reconstructing `deploy.ps1` or any deployment command not in
  `scripts/release/`.
- Copying files directly into a live static directory instead of going through the atomic
  generation-switch flow.
- Ungoverned SSH edits to production files.
- DB rebuild or migration as part of a deployment (out of scope for these scripts; requires
  separate explicit authorization).
- SGF Engine edits (vendored from a separate development line; re-vendored deliberately, never
  hand-edited).
- Force push.
- Deploying from a feature branch instead of the exact owner-named `origin/master` SHA.

## Success evidence

A deployment is only reportable as successful once all of the following are recorded:

- Production image tag and image ID (or static generation identifier).
- Deployed `sw.js` VERSION.
- `deploy/runtime-source-provenance.json` state used for the build.
- Health check results (`/healthz`, homepage, login).
- Host/container/public static identity agreement (SHA-256 + HTTP status + Content-Type per file).
- Rollback readiness status (previous image/generation identity captured before switching).

## Known gaps (tracked, non-blocking)

- **TECH-DEBT-001**: helper-function duplication across `scripts/release/*.ps1` should be
  consolidated into `ReleaseTooling.psm1`. Deliberately deferred; does not block deploy-day
  execution. See [TECH_DEBT_BACKLOG.md](TECH_DEBT_BACKLOG.md).
- **No CI enforcement**: `tests/deployment/*.py` and `tests/deployment` in general are not run
  automatically by any CI workflow (no `.github/workflows` exists in this repository). Passing
  state must be verified manually immediately before any deploy attempt, not assumed from a past
  run.
