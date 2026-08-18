# Deployment Workflow V3: Bounded Operational Recovery

Status: new (this document). Introduces `GO_DEPLOY_WITH_BOUNDED_RECOVERY`, an additive owner-gate
concept alongside the existing `GO_DEPLOY`/`GO_ROLLBACK` gates documented in
[production_deployment_governance.md](production_deployment_governance.md). It does not replace,
weaken, or reinterpret any existing gate, script, or fail-closed check.

## Why

Every prior deployment execution model in this repository treated *any* unexpected operational
issue during an authorized deploy attempt as a hard stop: the executor reports `BLOCKED`, the
Owner reviews, a new task is dispatched, a new authorization is given, and the whole attempt is
retried from scratch. That is correct for real authority/safety boundaries, but it is needlessly
brittle for ordinary transient operational failures (a hung SSH child, a temporarily unavailable
`docker buildx` builder, a readiness check that needs one more poll) that have nothing to do with
whether the Owner's authorization to promote a given SHA is still valid.

Deployment Workflow V3 changes the *default* for operational failures from **stop and escalate**
to **classify, recover, verify, retry, continue** — while keeping every existing fail-closed gate,
identity check, and Owner-boundary condition completely intact. STOP remains mandatory whenever
continuing would cross a real authority/safety boundary; it is simply no longer the default
response to "something unexpected happened."

## Root cause fixed: unbounded remote/native command execution (RELEASE-TOOLING-HOTFIX-04)

Investigated directly against the current canonical source (not assumed, not inferred from a
prior task's claims — see the git history note below). Two real, distinct gaps were found and
fixed in `scripts/release/ReleaseTooling.psm1`:

1. **`Invoke-RemoteShellCommand` had no process-level timeout at all.** Its two internal helpers
   (`Invoke-ProcessWithUtf8NoBomStdin`, `Invoke-ProcessWithSeparateOutput`) each call a bare
   `$proc.WaitForExit()` with no timeout argument. This is the function `rollback-static-release.ps1`
   routes *every* remote call through, and the function most calls in `deploy-release-image.ps1`,
   `rollback-release.ps1`, `verify-production-release.ps1`, `preflight-production.ps1`, and
   `set-e9-rollout.ps1` route through as well — meaning the exact class of unbounded ~15-minute SSH
   hang documented against `Invoke-BoundedNativeCommand`'s own history
   (`RELEASE-FIX-A2-STATIC-DEPLOY-FIX1`) remained fully reachable through every one of those
   scripts; only `deploy-static-release.ps1` itself was fully hardened against it. Fixed by making
   `Invoke-RemoteShellCommand` delegate to `Invoke-BoundedNativeCommand` instead of the two
   unbounded helpers (`-TimeoutSeconds`, default 120s, added as an optional parameter — no existing
   call site needed to change).

2. **Even `Invoke-BoundedNativeCommand` itself (the already-bounded primitive) had an ordering
   gap.** The previous implementation wrote `-StdinText` via a *synchronous*
   `StandardInput.Write()` call before `WaitForExit(timeout)` was ever reached. If the child process
   never reads stdin at all (e.g. it hung immediately on connect, before a remote shell ever
   started) and the payload exceeds the OS pipe buffer, that write blocks the calling thread
   indefinitely — and because the block happens earlier in the source than the timeout is armed,
   the hard timeout could never fire. This was real and previously untested (no existing test
   exercised `-StdinText` against a non-reading child). Fixed by writing via the raw stream's
   `WriteAsync` (non-blocking) with a short, separately-bounded wait (3s, independent of the
   caller's own `-TimeoutSeconds`) before closing stdin — long enough for any normally-responsive
   child (`sh -s`, `python -`, `cat`) to see EOF and proceed, short enough that a genuinely hung
   child still can't delay `WaitForExit(timeout)` by more than a few seconds.

Both fixes are covered by executable tests in
`tests/deployment/test_remote_shell_command_bounded_timeout.py`, including direct reproduction of
the previously-real hang using a real hung child process, not a mock. A related but separate
defect in the same family — a null-array crash while parsing `docker buildx inspect` output in
`scripts/build-production-image.ps1` — was fixed earlier as RELEASE-TOOLING-HOTFIX-03; see that
script's `Get-BuildxReportedPlatforms` function and
`tests/deployment/test_buildx_platform_parser_hotfix.py`.

A note on provenance: this task's own dispatch referenced a prior "Task 055" coordinated-rollback
incident as the origin of this investigation. Task 055's operational execution is not
independently verifiable from Git history: no commit, PR, or unique branch content attributable to
it was found in this repository at implementation time (the branches with adjacent names pointed
at existing master merge commits with no unique content of their own). Deployment operations do
not inherently create commits, so this absence of Git evidence does not by itself establish
whether or how Task 055 ran. The two root causes documented above were instead found and verified
independently, by direct, first-hand investigation of the current canonical source (parallel
read-only agents plus live reproduction), so this fix does not depend on Task 055's provenance
either way.

## Canonical bounded remote-command contract

Every canonical release script's remote/native command execution must satisfy:

| Property | Guarantee |
|---|---|
| `BOUNDED_EXECUTION` | Every remote/native invocation has a hard, finite upper bound on wall-clock time. |
| `HARD_TIMEOUT` | Enforced via `Process.WaitForExit(timeoutMs)`, never an unbounded wait. |
| `CHILD_PROCESS_TERMINATION_ON_TIMEOUT` | `taskkill /F /T /PID` (process-tree) with a plain `Kill()` fallback. |
| `STDOUT_DRAINED` / `STDERR_DRAINED` | Read asynchronously (`ReadToEndAsync`), never a source of secondary deadlock. |
| `STDIN_CLOSED` | Written asynchronously; closed as soon as the write completes within a short, separately-bounded wait. |
| `EXIT_CODE_CAPTURED` | Always, on both the success and timeout paths. |
| `TIMEOUT_CLASSIFIED` | A timeout is reported as `possible_timeout`, not conflated with a definite failure — see reconciliation below. |

This contract is implemented once, in `Invoke-BoundedNativeCommand`, and every remote-command
helper in `ReleaseTooling.psm1` now delegates to it.

## Post-timeout state reconciliation (never blindly retry a possibly-non-idempotent mutation)

A timed-out command may have: (A) never started remotely, (B) completed successfully but the
local client lost the result, (C) still be running remotely, (D) partially mutated state, or (E)
failed cleanly. Deployment Workflow V3 does not assume any of these — for the two phases that
actually mutate Production (`PROMOTE_STATIC`, `PROMOTE_APP`), a phase result that reports
`possible_timeout = $true` triggers an independent `GetCurrentState` read *before* any retry
decision. If current state already shows the expected identity landed, the state machine advances
to the next phase without re-invoking the mutating command — closing exactly the "duplicate a
non-idempotent mutation after a spurious timeout" risk.

## Recovery levels

- **L1 — local/pre-mutation.** Failures in `PRECHECK`, `BUILD_APP`, `PACKAGE_APP`,
  `PACKAGE_STATIC`, `SNAPSHOT_BASELINE`, or `VERIFY_ROLLBACK_READY`. Nothing in these phases can
  have touched Production by construction. Retried directly, no rollback needed, no Owner gate
  required.
- **L2 — Production mutation occurred but rollback is proven.** Failures in `PROMOTE_STATIC`,
  `VERIFY_STATIC`, `PROMOTE_APP`, `VERIFY_APP`, `JOINT_PROVENANCE`, or `PRODUCTION_SMOKE`, where a
  concrete baseline was already captured this run (so a rollback target unambiguously exists).
  Recovery: coordinated rollback of whatever was actually promoted → independent
  `GetCurrentState` verification that the baseline is restored → same-SHA retry from
  `PROMOTE_STATIC` (build/package artifacts remain valid; they are not redone).
- **L3 — authority/source/data boundary. STOP.** Forced whenever a phase result explicitly reports
  `requires_source_change` or `requires_gate_bypass`, or a post-mutation phase fails with no
  baseline ever captured this run (rollback target unavailable), or a rollback's own final-state
  verification cannot confirm the baseline was actually restored. STOP is always accompanied by a
  best-effort baseline restoration attempt when a baseline exists.

Classification is **structural**, not name/message-based: it never inspects the failure's error
type or text. Which phase failed (pre- vs. post-mutation, tracked by the state machine's own fixed
phase order) and whether a baseline was actually captured in *this* run determine L1 vs. L2 by
default; only the three explicit boundary flags above force L3. This is what lets a completely
novel failure — one with no name, no prior recovery recipe, and no entry in any list this workflow
maintains — still be classified and recovered correctly. Proven directly:
`tests/deployment/test_coordinated_release_state_machine.py::test_f8_unknown_operational_failure_with_no_whitelist_entry_recovers`
throws a synthetic error string that appears nowhere else in the module's source, in a
post-mutation phase, and the state machine still recovers it via the ordinary L2 path.

## Bounded retry budget

`MAX_AUTOMATIC_RECOVERY_ATTEMPTS_PER_ROOT_CAUSE = 2`. A third occurrence of the *same* (phase,
root-cause-class) pair escalates to STOP rather than retrying a fourth time. Budgets are tracked
per root-cause key, not globally — an unrelated LOW/MEDIUM failure in a different phase, or a
differently-classified failure in the same phase, gets its own independent budget and is not
penalized by a prior, unrelated failure's exhausted retries.

## Coordinated transaction: THREE governed identities

An Architecture V1 release is not two identities but three: `deploy-release-image.ps1` switches
**two** container images within one operation (the app *and* the scheduler), alongside the static
generation. So the coordinated contract is:

```
APP_SOURCE_GIT_SHA == SCHEDULER_SOURCE_GIT_SHA == STATIC_SOURCE_GIT_SHA
```

Each is established **independently**, in the SHA domain, from its own authoritative source —
never inferred from one another and never conflated with the separate image-tag / image-id /
generation-path identities that are tracked alongside them:

| Identity | Source of truth |
|---|---|
| `APP_SOURCE_GIT_SHA` | `org.opencontainers.image.revision` OCI label on the running **app** image |
| `SCHEDULER_SOURCE_GIT_SHA` | the same label on the running **scheduler** image (read separately) |
| `STATIC_SOURCE_GIT_SHA` | `release_git_sha` in the active generation's own `manifest.json` |

`JOINT_PROVENANCE` independently re-reads all three via `GetCurrentState` (never trusting a prior
phase's self-reported identity) and fails — forcing the L2 rollback path — unless all three agree
*and* match the authorized `-ExpectedGitSha`.

The only two states this workflow can end a run in are `CANDIDATE_CANDIDATE` (all three on the
authorized SHA) or `BASELINE_BASELINE` (all three restored to a *coherent* pre-run identity).
Anything else — including a candidate app beside a baseline scheduler — is reported honestly as
`MIXED_OR_UNVERIFIED` by `Get-ReleaseStateDomain`, never as a safe outcome.

### Baseline coherence is a pre-mutation gate

If the captured baseline is itself mixed (the three identities disagree *before* this run mutates
anything), the run STOPS at `SNAPSHOT_BASELINE` with `stop_reason=baseline_not_coherent`, as an L3
Owner boundary — promoting on top of an already-incoherent state would leave no coherent state to
roll back to. `Get-ReleaseStateDomain` also refuses to call a mixed captured baseline
`BASELINE_BASELINE` even when current state matches it field-for-field: restoring an incoherent
state is not a safe end.

### A timeout may skip replay only on a *fully proven* postcondition

`PROMOTE_APP` is not complete merely because the app container switched — the canonical deploy
performs app switch → app readiness → scheduler switch → scheduler identity → nginx refresh →
production verification. So after an ambiguous timeout the state machine requires **both**:

1. every identity the phase owns is observably on the candidate (for `PROMOTE_APP`: app **and**
   scheduler), and
2. the phase's own canonical verification independently passes (`VerifyApp` re-runs
   `verify-production-release.ps1`; `VerifyStatic` re-checks the static postcondition).

Only then does it advance without replaying a possibly-non-idempotent mutation
(`RECONCILED_FULL_POSTCONDITION_PROVEN_NO_DUPLICATE_MUTATION`). If identity landed but the full
postcondition cannot be proven, it records
`CANDIDATE_IDENTITY_PRESENT_BUT_FULL_POSTCONDITION_UNPROVEN` and falls through to the ordinary
coordinated rollback → verify baseline → retry-same-SHA path. Rollback *scope* is likewise decided
from observed per-identity state versus the baseline, never from a phase's own self-reported
booleans.

## Fault injection

`tests/deployment/test_coordinated_release_state_machine.py` exercises F1-F10 against the real
`Invoke-CoordinatedReleaseStateMachine`, with injected fake phase scriptblocks that track mutable
app/static SHA state locally — no Docker, SSH, or Production contact:

| # | Scenario | Expected | Test |
|---|---|---|---|
| F1 | SSH child hangs before remote mutation | Local recovery, retry succeeds | `test_f1_pre_mutation_transient_recovers_and_retries_directly` |
| F2 | SSH disconnect after remote command actually completed | Reconcile, no duplicate mutation | `test_f2_post_timeout_reconciliation_does_not_duplicate_mutation` |
| F3 | Static succeeds, app fails before app mutation | Static rollback, baseline/baseline, retry permitted | `test_f3_static_success_app_premutation_fail_rolls_back_to_baseline` |
| F4 | Static+app succeed, post-app verification fails | Coordinated rollback, baseline/baseline | `test_f4_post_app_verification_failure_triggers_coordinated_rollback` |
| F5 | Docker/buildx temporarily unavailable before build | Local recovery, same-SHA retry | `test_f5_buildx_transient_before_build_recovers_locally` |
| F6 | Temporary health failure resolving within the bounded window | Bounded retry, continue | `test_f6_temporary_health_failure_resolves_within_bounded_window` |
| F7 | Persistent health failure | Rollback, coherent baseline, STOP | `test_f7_persistent_health_failure_stops_at_coherent_baseline` |
| F8 | Unknown synthetic operational error, no whitelist entry | Generic recovery, not an automatic STOP | `test_f8_unknown_operational_failure_with_no_whitelist_entry_recovers` |
| F9 | Simulated L3: source SHA change required | STOP, no automatic source modification | `test_f9_source_change_required_stops_no_automatic_modification` |
| F10 | Rollback target unavailable/ambiguous | STOP before continuing mutation | `test_f10_rollback_target_unavailable_stops_before_mutation`, `test_f10_variant_explicit_rollback_target_unavailable_at_post_mutation_is_l3` |

Plus a full coordinated happy-path simulation and a coordinated rollback simulation asserting the
final observed state is *exactly* baseline/baseline, never mixed.

## Recovery evidence

Every recovery attempt appends a structured entry to the run's `recovery_log`: `recovery_id`,
`root_cause_class`, `classification` (L1/L2/L3), `classification_reason`, `failure_phase`,
`mutation_occurred`, `failure_detail`, `failure_was_unstructured_exception`, `retry_count`,
`retry_allowed`, `recovery_action`, `post_recovery_state`, `final_outcome`. No Owner interaction is
required to produce this evidence — it is emitted unconditionally as part of the state machine's
return value.

## Operator/agent recovery contract

- `DEFAULT_ACTION_ON_OPERATIONAL_FAILURE = RECOVER_AND_CONTINUE`
- `STOP_IS_EXCEPTION = YES` — reserved for the L3 conditions above.
- `UNKNOWN_ERROR_IS_NOT_AUTOMATIC_STOP = YES` — an error with no name, no whitelist entry, and no
  prior recovery recipe is still classified and (if L1/L2) recovered automatically.
- The deploy executor does not need a new Owner approval for each recoverable operational problem
  within the same authorized SHA. A **new**, explicit `GO_DEPLOY`-family gate is required only for
  a genuinely new deployment attempt (a different SHA, or after this run itself reaches STOP).

### `GO_DEPLOY_WITH_BOUNDED_RECOVERY`

Authorizes safe promotion of **one exact Git SHA**, passed via `-OwnerGate` to
`scripts/release/deploy-coordinated-release.ps1 -Execute` (exact-string match via the same
`Assert-OwnerGate` mechanism every other gate uses — no allowlist, no inference). Within that
authorization, the executor may: retry transient commands; recover Docker/buildx readiness;
recover SSH/process state; terminate confirmed-stalled local children; reconcile remote state after
a timeout; perform canonical rollback; restore a coherent baseline; retry the same SHA; continue
the deployment; and handle previously unknown LOW/MEDIUM operational issues safely — all without a
new Owner interaction.

It may **not**: change the source SHA; modify repository or release-tooling source during the
deploy; create a hotfix commit; bypass any existing gate; modify the database, SGF judging state,
or rollout/flag scope beyond what the authorized release mechanically does; or accept an
unverifiable Production state and proceed anyway. Every one of those remains a hard L3 stop.

## Orchestrator

`scripts/release/deploy-coordinated-release.ps1` is the CLI entrypoint. It contains no
recovery/classification logic of its own — it only wires
`scripts/release/CoordinatedReleaseStateMachine.psm1`'s injected phase scriptblocks to the
existing, already-governed release scripts (`build-release-image.ps1`,
`package-release-image.ps1`, `package-static-release.ps1`, `deploy-release-image.ps1`,
`deploy-static-release.ps1`, `rollback-release.ps1`, `rollback-static-release.ps1`,
`preflight-production.ps1`), each invoked as its own bounded child process via
`Invoke-BoundedNativeCommand`. No low-level build/package/deploy/rollback logic is duplicated.

Without `-Execute` it is a pure, local, read-only plan/precondition report — it never builds,
packages, promotes, or contacts Production, exactly like every other canonical release script's
dry-run mode (`tests/deployment/test_deploy_coordinated_release_cli.py` covers this contract,
including gate enforcement, directly).

**This task did not perform any real `-Execute` run against Production or any live host** — that
remains explicitly out of scope (`NO_GO_DEPLOY_IN_THIS_TASK`), consistent with the rest of this
document. The orchestrator's phase-executor wiring to the real scripts was built from direct
source review of each script's exact parameter and JSON-output contract, and is covered by the
dry-run/gate tests above plus the state-machine's own fault-injection suite (which proves the
orchestration/recovery logic the wiring drives is correct) — but the wiring itself has not been
exercised end-to-end against a real host. A real, Owner-authorized dry-run/staging exercise is
expected before this orchestrator's first live `-Execute` use, exactly as would be expected of any
new release-tooling entrypoint.
