# Release Tooling Tech Debt Backlog

## TECH-DEBT-001

**Title:** Consolidate duplicated release readiness, database,
compose-environment, and questions-probe helpers into `ReleaseTooling.psm1`.

**Problem:** The following logic is independently copy-pasted across
multiple `scripts/release/*.ps1` files instead of living once in the shared
module:

- `Get-DatabaseUrlComponents` — duplicated in `deploy-release-image.ps1`,
  `rollback-release.ps1`
- `Get-RemoteComposeEnvironmentPrefix` — duplicated in
  `deploy-release-image.ps1`, `rollback-release.ps1`
- `Try-Get-RemoteReadinessReport` — duplicated in `deploy-release-image.ps1`,
  `rollback-release.ps1`, `preflight-production.ps1`,
  `verify-production-release.ps1`
- `Get-RemoteQuestionsReport` — duplicated in `deploy-release-image.ps1`,
  `rollback-release.ps1`, `preflight-production.ps1`,
  `verify-production-release.ps1`
- `Get-AppReadinessGateReport` — duplicated in `deploy-release-image.ps1`,
  `rollback-release.ps1`

A fix to any one of these (e.g. adding a new readiness field, changing DB
URL parsing) must currently be replicated by hand across 2–4 files, which is
exactly the failure mode that turned the PR #55 hotfix into ~20 sequential
PRs during the 2026-07-11 incident — each patch fixed one script while the
same edge case remained live in another.

**Priority:** After PR #55 production closeout. Not urgent — current
Production is stable and this does not block deploy-day execution.

**E9 blocking:** No. This work must not be pulled into the E9 main line.

**Scope when picked up:** Move the five functions above into
`ReleaseTooling.psm1`, update all call sites, re-run
`tests/deployment/test_release_tooling.py` in full, and confirm no
behavioral drift via dry-run parity checks before merging.
