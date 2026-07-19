# E9 canonical status reconstruction

Status: `E9_STATUS_RECONSTRUCTED_WITH_EVIDENCE_GAPS`
Audit date: 2026-07-19
Audit base: `origin/master` at `d560fed638df8e65ac0b19f85ed7827ff1b99ab2`

## Executive conclusion

E9 is not an unimplemented proposal.  Its component foundation, legacy-shell
integration, runtime packaging, canonical data adapters, exclusive shell
ownership, server-side Stage C targeting, admin-only package, authenticated
handoff, navigation fixes, and release-tooling convergence work are merged into
the canonical line.

The safe conclusion is nevertheless not that an admin beta was accepted.
`E9_ROLLOUT_SCOPE` defaults to `admin_only`, but both server enable switches
default to false.  The audit found no tracked, authenticated production
acceptance record proving the admin, non-admin, refresh, logout, and re-login
matrix against the currently served release.  The one next implementation
Sprint is therefore **`E9-ADMIN-ACCEPT1`**, a production-safe acceptance and
evidence Sprint; it must not broaden eligibility or change E9 behavior.

## Evidence method and safety boundary

This reconstruction used canonical Git ancestry, GitHub PR metadata, tracked
source and tests, and unauthenticated public HTTP probes.  Merge, deployment,
and acceptance are intentionally recorded separately.  No environment values,
cookies, accounts, databases, SGF files, questions, or player state were read
or changed.  No deployment, flag change, rollback, restart, or service-worker
change occurred.

The owner-provided production identity was `0951c9a33ec287c57f21906c2dbcd9d7fd5ff314`
and image ID `sha256:f719687bd0bd2269ac22dacf68dcfdbe85d9d56dc8314826c867e6b2445814d8`.
All listed E9 merge commits through PR #155 are ancestors of that source SHA.
The source and image ID were not independently obtainable through the public
surface, so they remain owner-provided runtime evidence rather than a new
runtime-hash assertion by this audit.

## Canonical milestone table

| Milestone | PR | Merge SHA | In master | Deployed | Accepted | Canonical status |
| --- | --- | --- | --- | --- | --- | --- |
| E9 preflight / inventory | #77 | NOT FOUND | NO | N/A | N/A | `PLANNED` (PR remains OPEN) |
| E9.1A1 component foundation | #78 | `2026f47c…` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| E9.1A2 legacy shell integration | #79 | `68c0b04d…` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| E9.1A2-FIX1 runtime asset packaging | #85 | `9d7cb091…` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| E9.1B real data contract | #86 | `f621a5cc…` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| E9.1D1 shell exclusivity | #98 | `d464d565…` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| Stage C server targeting | #114 | `f2d9350f…` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| Stage C admin-only package | #117 | `466e834b…` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| Auth-handoff re-init | #153 | `590b45ef…` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| C3.2 deployment convergence | #154/#155 | `4bca483c…` / `551e5650…` | YES | owner-provided prior deployment evidence only | NOT FOUND | `DEPLOYED_NOT_ACCEPTED` |
| Named allowlist | no separately merged milestone | NOT FOUND | capability exists | NOT FOUND | NOT FOUND | `EVIDENCE_INCOMPLETE` |
| Cohort rollout | NOT FOUND | NOT FOUND | NO | NOT FOUND | NOT FOUND | `EVIDENCE_INCOMPLETE` |

The early milestones are components of the later source lineage, but no
tracked artifact-to-production mapping identifies each individual merge as a
separate production deployment.  They must not be promoted to accepted status.

## Git and PR timeline

* #78 (2026-07-12): five component fragments, E9 CSS/JS, loader, default-off
  flags, and foundation tests.
* #79 (2026-07-12): `index.html` and static-route integration; legacy remains
  the default shell.
* #85 (2026-07-12): Docker and build-manifest packaging contract for E9 assets.
* #86 (2026-07-12): canonical player/activity/adventure adapters and their
  runtime contract tests.
* #98 (2026-07-13): exclusive E9/Legacy ownership, focus management, and
  idempotent fragment mounting.
* #114 and #117 (2026-07-15): server-side targeting followed by the formal
  admin-only, default-off rollout package.
* #143, #150, and #153 (2026-07-17): navigation/CTA and authenticated
  handoff corrections.
* #154 and #155 (2026-07-17): production-convergence tooling, not an
  authenticated E9 acceptance record.

No later revert of these E9 source changes was found in the canonical history.

## Eligibility architecture

| Question | Evidence and behavior | Confidence |
| --- | --- | --- |
| Flag names | `e9Shell`, `e9TopHud`, `e9LeftNav`, `e9RightCards`, `e9BottomDock`, `e9WorldStage` in `js/e9/feature_flags.js` and `app.py` `_E9_FLAG_KEYS`. | HIGH |
| Default | Client production flags are all false. Server scope defaults to `admin_only`; global and admin enable switches are false unless environment-set. | HIGH |
| Authoritative source | `/api/auth/me` calls `_e9_rollout_decision()` and supplies `e9_rollout.effective_flags`; client consumes it as `__GO_E9_SERVER_FLAGS__`. | HIGH |
| Admin source | The server passes the authoritative `users.is_admin` result to `_e9_rollout_decision()`, not a client identity heuristic. | HIGH |
| Unauthenticated / non-admin | Decision fails closed and returns all false flags; Legacy stays active. | HIGH in source/tests; production session evidence incomplete |
| Eligible admin | Requires authenticated identity, `admin_only`, global enabled, admin enabled, and valid config. | HIGH in source/tests; production enablement evidence incomplete |
| Auth handoff | `index.html` re-primes ownership and calls `E9.initShell()` after `/api/auth/me` flags arrive. | HIGH |
| Logout | `doLogout()` posts `/api/auth/logout`, which clears the server session, then navigates to `/login`; there is no same-document E9 unmount/recalculation hook. | HIGH |
| Legacy fallback | `shell.js` resolves non-E9 ownership to Legacy and `recoverToLegacy()` restores Legacy visibility/readiness on critical failure. | HIGH |

Relevant locators: `app.py:120-171`, `app.py:5882-5953`,
`js/e9/feature_flags.js:19-68`, `js/e9/shell.js:98-238`, and
`index.html:14488-14492`.

## Shell lifecycle inventory

| Lifecycle capability | Exists | Exact locator | Test coverage | Known risk |
| --- | --- | --- | --- | --- |
| Idempotent init/mount guard | YES | `shell.js` `mountStarted` | Node exclusivity test | It only prevents a second initial mount. |
| Exclusive Legacy/E9 ownership | YES | `applyShellState()` | Python + Node exclusivity tests | Source-level coverage, no production authenticated matrix. |
| Critical failure fallback | YES | `recoverToLegacy()` | integration tests | Does not unmount already loaded non-critical slots. |
| Auth re-init | YES | `index.html` auth handoff | shell tests | Re-init does not reset mount state. |
| Explicit unmount | NO | NOT FOUND | NOT FOUND | Logout/session switch relies on navigation. |
| Listener/timer/observer cleanup | NOT FOUND | NOT FOUND | NOT FOUND | Repeated lifecycle transitions have no explicit cleanup inventory. |
| AbortController/stale-auth generation | NOT FOUND in shell | NOT FOUND | NOT FOUND | Async data from a prior auth state is not explicitly generation-guarded. |
| Remount after unmount | NO | NOT FOUND | NOT FOUND | There is no unmount/reset contract to test. |

## Production read-only observations

At audit time, public `https://godokoro.com/healthz`, `/`, `sw.js`, the E9
flag and shell JavaScript, E9 shell CSS, and the World Stage fragment each
returned HTTP 200.  Public `sw.js` reported
`v196-e9-adventure-cta-activation-fix`; the homepage used
`/i18n.js?v=20260710a`; the served feature-flags asset reported
`ASSET_VERSION = 'e9-c3-navigation'` and default client flags false.

Those probes establish public asset reachability, not a container-image hash,
server environment, an authenticated admin decision, or human acceptance.
The unauthenticated page cannot establish that an admin-only rollout is
currently enabled; it does establish that the public asset retains a default
false client fallback.

## Test coverage matrix

| Behavior | Test source | Result on audit base | Production acceptance |
| --- | --- | --- | --- |
| foundation and loader | `test_e9_adventure_shell_foundation.py` | PASS | NOT FOUND |
| legacy integration/static routes | `test_e9_adventure_shell_integration.py` | PASS | NOT FOUND |
| data contract | `test_e9_1b_real_data_contract.py` | PASS | NOT FOUND |
| exclusivity and auth handoff | `test_e9_shell_exclusivity.py` plus Node harness | PASS | NOT FOUND |
| server targeting | `test_e9_server_rollout_targeting.py` | PASS | NOT FOUND |
| authenticated fixtures | `test_e9_authenticated_fixture_matrix.py` | PASS | sanitized fixture only |
| C3 navigation | `test_e9_c3_core_navigation.py` | PASS | NOT FOUND |
| rollout setter contract | `tests/deployment/test_e9_rollout_setter.py` | PASS | NOT an execution |

Command: `python -m pytest -q` over the eight E9 test modules and rollout
setter contract. Result: **194 passed**.  Command:
`node tests/e9_node_tests/run_shell_exclusivity_tests.js`. Result: **6 passed**.

## Stage C naming provenance

`Stage C` first appears in the tracked E9.1A1 planning document and
`feature_flags.js` as the conceptual stage permitted to flip `e9Shell` true.
PR #114 is the first confirmed merged PR explicitly titled Stage C targeting;
PR #117 is the formal Stage C admin-only rollout package.  The terms `C2`,
`C2.1`, `C2.2`, `admin-only beta`, and `authenticated beta` have no confirmed
canonical planning, PR, or commit naming source in the canonical tree.

Conclusion: `STAGE_C_NAMING_NOT_CANONICALLY_ESTABLISHED` for C2/C2.1/C2.2.
Do not retroactively relabel the historical PRs as C2 milestones.

## Gap register and next Sprint

See `docs/planning/e9_gap_register.md` for the complete, actionable register.
The selected next Sprint is **`E9-ADMIN-ACCEPT1`**: the admin-only gate exists,
but its present production decision and authenticated acceptance evidence are
incomplete.  Deferred work: rollout expansion, RPG Analysis Phase 2, E9.2
Visual Foundation, and lifecycle hardening until acceptance establishes the
current beta boundary.
