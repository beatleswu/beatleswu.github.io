# E9 canonical status reconstruction

Status: `E9_STATUS_RECONSTRUCTED_WITH_EVIDENCE_GAPS`
Audit date: 2026-07-19
Audit base: `origin/master` at `d560fed638df8e65ac0b19f85ed7827ff1b99ab2`

## Executive conclusion

E9 implementation is substantially merged into the canonical line: foundation,
Legacy shell integration, runtime packaging, canonical data adapters, shell
exclusivity, server-side Stage C targeting, admin-only rollout configuration,
navigation, authenticated handoff, and deployment-convergence tooling all have
merged PR evidence. The audit does not find a complete authenticated
Production acceptance record for admin, non-admin, refresh, logout, and
re-login. Therefore this is not a `PRODUCTION_ACCEPTED` or `C2.1_COMPLETE`
claim. The unique next Sprint is **`E9-ADMIN-ACCEPT1`**, limited to
production-safe acceptance evidence.

## Evidence method and safety

Evidence was reconstructed from Git ancestry, GitHub PR metadata, tracked
source/tests/docs, and unauthenticated public HTTP probes. Merge, deployment,
and acceptance are recorded as separate claims. No environment values,
cookies, accounts, databases, SGF files, questions, player state, feature
flags, containers, locks, or Production configuration were read or changed.

Owner-provided runtime identity is source
`0951c9a33ec287c57f21906c2dbcd9d7fd5ff314` and image
`sha256:f719687bd0bd2269ac22dacf68dcfdbe85d9d56dc8314826c867e6b2445814d8`.
The current source is an ancestor of the E9 merge commits below; that does not
prove an individual milestone was separately deployed or accepted.

## Canonical milestone table

| Milestone | PR | Merge SHA | In master | Deployed | Accepted | Canonical status |
| --- | --- | --- | --- | --- | --- | --- |
| E9 preflight / inventory | #77 | NOT MERGED | NO | N/A | N/A | `IMPLEMENTED_NOT_MERGED` |
| E9.1A1 component foundation | #78 | `2026f47c2bb55364d0132823b0eaabef2606c588` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| E9.1A2 legacy shell integration | #79 | `68c0b04d910b82dbd1eb23445e1474cdbf61bd92` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| E9.1A2-FIX1 runtime asset packaging | #85 | `9d7cb09132b57a5e60ec98ca746f73ab50b3e36f` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| E9.1B real data contract | #86 | `f621a5ccff329b3b5ef4bf08f2e8260843ed01d9` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| E9.1D1 shell exclusivity | #98 | `d464d5651006a8c3d60c65e44fa27e6b8209e1cf` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| Stage C server targeting | #114 | `f2d9350f2cf8aeee56adf5f20c8f4b46dc9e09f8` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| Stage C admin-only package | #117 | `466e834bca5e92dab566542b5c4a6de68336fd66` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| Governed E9 rollout configuration | #132 | `8a296a50ed74814b05b63b003938db6db5cefb42` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| Core navigation / adventure entry | #143 | `be5796e8656794f6e760f64a8b0ffafbb9911897` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| Canonical CTA handoff | #150 | `57e50f403b1587e6823e3a19f25e5df6b2d935d1` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| Auth-handoff re-init | #153 | `590b45ef4eab62e171429808e32da304921d741b` | YES | EVIDENCE INCOMPLETE | NOT FOUND | `MERGED_NOT_DEPLOYED` |
| C3.2 deployment convergence | #154/#155 | `4bca483c98d0adbe9ebae2c6601120e7b76900f8` / `551e5650f3486e1d544cb99bd1be17c55e9879d3` | YES | Owner-provided prior deployment evidence only | NOT FOUND | `DEPLOYED_NOT_ACCEPTED` |
| Named allowlist | no separately merged milestone | NOT FOUND | capability exists in guarded config | NOT FOUND | NOT FOUND | `EVIDENCE_INCOMPLETE` |
| Cohort rollout | NOT FOUND | NOT FOUND | NO | NOT FOUND | NOT FOUND | `EVIDENCE_INCOMPLETE` |

For each row, the PR supplies the branch, feature commit(s), changed files,
implementation, and test evidence; Git supplies merge date and ancestry. No
row has a preserved independent Production acceptance report. PR #132 is a
four-key, default-off configuration/setter package and explicitly excludes
allowlist or percentage rollout. PRs #143, #150, and #153 are follow-up
navigation and handoff fixes, not beta acceptance.

## Git and PR timeline

PR #78 (2026-07-12) added the component foundation and default-off flags; #79
integrated the Legacy shell; #85 packaged runtime assets; #86 wired canonical
runtime data; #98 enforced exclusive shell ownership; #114 and #117 added
server-side Stage C targeting and the admin-only package; #132 added governed
rollout configuration; #143, #150, and #153 corrected navigation and
authenticated handoff; #154 and #155 stabilized release convergence. PR #77
remains open and unmerged. No later revert of these E9 source changes was
found. PR #127 is adjacent encounter separation, not a core E9 milestone.

## Feature flag and eligibility architecture

| Question | Actual behavior | Locator | Confidence |
| --- | --- | --- | --- |
| Flag names | `e9Shell`, `e9TopHud`, `e9LeftNav`, `e9RightCards`, `e9BottomDock`, `e9WorldStage` | `js/e9/feature_flags.js`, `app.py` `_E9_FLAG_KEYS` | HIGH |
| Defaults | Client flags false; server scope `admin_only`; global/admin switches false | `scripts/release/e9_rollout_config.py` | HIGH |
| Source | `/api/auth/me` returns `e9_rollout.effective_flags`; bootstrap stores `__GO_E9_SERVER_FLAGS__` | `app.py`, `index.html` | HIGH |
| Eligibility | Authenticated `users.is_admin`, global enabled, admin enabled, valid config | `app.py` `_e9_rollout_decision` | HIGH |
| Unauthenticated/non-admin | All flags false; Legacy remains active | `app.py`, rollout tests | HIGH in source; Production session evidence incomplete |
| Auth handoff | Re-primes ownership and calls `E9.initShell()` after auth flags arrive | `index.html` | HIGH |
| Logout | Posts logout then navigates to `/login`; no same-document unmount/recalculation | `index.html` `doLogout` | HIGH |
| Legacy fallback | Ownership resolves to Legacy; `recoverToLegacy()` restores it after critical failure | `js/e9/shell.js` | HIGH |

`E9.initShell()` is called from the initial page bootstrap and again from the
authenticated handoff. Refresh re-runs bootstrap. A same-document logout does
not provide a separate teardown contract.

## Shell lifecycle inventory

| Capability | Exists | Locator | Test coverage | Risk |
| --- | --- | --- | --- | --- |
| Idempotent initial init/mount | YES | `js/e9/shell.js` `mountStarted` | Node exclusivity tests | No reset after auth transition |
| Legacy/E9 exclusivity | YES | `applyShellState()` | Python + Node tests | No authenticated Production matrix |
| Critical fallback | YES | `recoverToLegacy()` | integration tests | Partial effects may remain |
| Explicit unmount | NO | NOT FOUND | NOT FOUND | Logout relies on navigation |
| Listener/timer/observer cleanup | NOT FOUND | NOT FOUND | NOT FOUND | Same-document lifecycle risk |
| AbortController/stale-auth generation | NOT FOUND | NOT FOUND | NOT FOUND | Prior async work not explicitly cancelled |
| Remount after unmount | NO | NOT FOUND | NOT FOUND | No teardown/reset contract |

## Production read-only observations

Public `https://godokoro.com/healthz`, `/`, `sw.js`, E9 flag/shell assets, CSS,
and World Stage fragment returned HTTP 200. Public `sw.js` reported
`v196-e9-adventure-cta-activation-fix`; homepage used `/i18n.js?v=20260710a`;
the served flag asset reported `ASSET_VERSION = 'e9-c3-navigation'` and
default client flags false. These observations prove reachability only. They
do not prove the current image/source, authenticated admin decision, or human
acceptance. No authenticated fixture was run for this audit.

## Test coverage matrix

| Behavior | Test source | Audit result | Production acceptance |
| --- | --- | --- | --- |
| Foundation/loader | `tests/test_e9_adventure_shell_foundation.py` | PASS | NOT FOUND |
| Legacy integration/static routes | `tests/test_e9_adventure_shell_integration.py` | PASS | NOT FOUND |
| Real-data contract | `tests/test_e9_1b_real_data_contract.py` | PASS | NOT FOUND |
| Exclusivity/auth handoff | `tests/test_e9_shell_exclusivity.py`, Node harness | PASS | NOT FOUND |
| Server targeting | `tests/test_e9_server_rollout_targeting.py` | PASS | NOT FOUND |
| Auth fixture matrix | `tests/test_e9_authenticated_fixture_matrix.py` | PASS | Sanitized fixture only |
| C3 navigation | `tests/test_e9_c3_core_navigation.py` | PASS | NOT FOUND |
| Rollout setter | `tests/deployment/test_e9_rollout_setter.py` | PASS | Not an execution |
| Static/SW/provenance contracts | tracked integration and release tests | PASS | Public reachability only |

Audit commands and results: the eight E9 pytest modules plus rollout setter
reported **194 passed**; `node tests/e9_node_tests/run_shell_exclusivity_tests.js`
reported **6 passed**. No test changed runtime code.

## Stage C naming provenance

`Stage C` is present in tracked planning/source material; PR #114 is the first
confirmed merged PR explicitly titled Stage C targeting and #117 is the formal
admin-only package. `C2`, `C2.1`, `C2.2`, `admin-only beta`, and `authenticated
beta` have no confirmed canonical planning, PR, or commit naming source.

Conclusion: **`STAGE_C_NAMING_NOT_CANONICALLY_ESTABLISHED`** for C2/C2.1/C2.2.
Historical PRs must not be retroactively relabeled.

## Gap register and selected next Sprint

See `docs/planning/e9_gap_register.md`. The unique next Sprint is
**`E9-ADMIN-ACCEPT1`** because the admin-only gate exists in source but
Production authenticated acceptance evidence is incomplete. Deferred work:
rollout expansion, RPG Analysis Phase 2, E9.2 Visual Foundation, and lifecycle
hardening until the acceptance boundary is documented.

## Safety confirmation

This audit changed documentation only. No runtime code, feature flag, Shadow
state, deployment, rollback, drill, database, SGF, questions, or player state
was changed.
