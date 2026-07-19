# E9 gap register

Status: evidence-based audit record, 2026-07-19.

## E9-ADMIN-ACCEPT1 update

* Result: `E9_ADMIN_ACCEPTANCE_PARTIAL`.
* Evidence: existing admin session reported `is_admin=true` but the server
  rollout decision was `eligible=false`, `reason=global_disabled`, with all
  effective flags false. Logged-out pages returned to Legacy/login without an
  E9 root. No approved non-admin account was available.
* Safety: no account role, feature flag, player state, database, container, or
  deployment mutation occurred.
* Routing: continue `E9-ADMIN-ACCEPT1`; do not begin lifecycle hardening or
  rollout expansion until positive admin and non-admin journeys are captured.

## E9-GAP-001

* Category: Production acceptance
* Description: No tracked proof covers an eligible admin and non-admin against
  the currently served release, including refresh, logout, and re-login.
* Evidence: Stage C source/tests and sanitized fixtures exist; no authenticated
  production report was found.
* Impact: The admin-only gate cannot be called accepted.
* Recommended owner: Product owner plus designated acceptance operator.
* Recommended Sprint: `E9-ADMIN-ACCEPT1`.
* Blocking: YES, for rollout expansion or beta-accepted status.

## E9-GAP-002

* Category: Operational
* Description: Public probes establish asset reachability but not the current
  container image, source label, or server rollout environment.
* Evidence: Public assets returned 200; owner-provided source/image identity
  was not independently exposed by the safe public surface.
* Impact: Deployment and acceptance must remain separate claims.
* Recommended owner: Release owner.
* Recommended Sprint: `E9-ADMIN-ACCEPT1` evidence capture only.
* Blocking: YES, for a `PRODUCTION_ACCEPTED` assertion.

## E9-GAP-003

* Category: Lifecycle and test
* Description: The shell has idempotent initial mounting and Legacy/E9
  exclusivity, but no explicit unmount, listener/timer/observer cleanup,
  stale-auth generation guard, or remount-after-unmount contract.
* Evidence: `js/e9/shell.js` has `mountStarted` and no corresponding teardown
  path; existing tests exercise ownership and initial idempotence only.
* Impact: A future same-document session transition could retain stale async
  work or mounted component effects.
* Recommended owner: E9 frontend owner.
* Recommended Sprint: `E9-BETA-LIFECYCLE1`, after acceptance closes GAP-001.
* Blocking: NO for a strictly navigational admin acceptance; YES before a
  long-lived dynamic-cohort rollout.

## E9-GAP-004

* Category: Naming and planning
* Description: `C2`, `C2.1`, and `C2.2` have no canonical definition or
  historical mapping.
* Evidence: Canonical search confirms Stage C but not those terms.
* Impact: Mislabeling can falsely imply completed work.
* Recommended owner: Product/roadmap owner.
* Recommended Sprint: `E9-ADMIN-ACCEPT1` documentation addendum, if needed.
* Blocking: YES for any decision whose approval depends on a C2 label.
