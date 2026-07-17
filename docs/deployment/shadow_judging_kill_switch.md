# Shadow Judging kill switch

Status: **PENDING OWNER-GATED DRILL**

This runbook defines the technical contract for changing only
`SHADOW_JUDGING_ENABLED`. The implementation and synthetic tests do not
authorize a Production change. A Production drill may happen only after the
change is merged, the owner explicitly approves the drill, and the operator
supplies the operation-specific owner gate under the canonical DEPLOY-GOV-1
release/config governance.

`scripts/release/set-shadow-judging.ps1` is the only supported operator. Do
not manually edit the protected Production configuration, use a generic
environment editor, open an ad-hoc remote shell, or directly invoke container
lifecycle commands. The setter sends a fixed allowlist-only helper through the
bounded release transport and never downloads or prints the full environment.

## Supported operations

Read-only inspection and planning do not accept an execution gate:

```powershell
./scripts/release/set-shadow-judging.ps1 -Operation status -LayoutFile ./deploy/release-layout.production.json
./scripts/release/set-shadow-judging.ps1 -Operation dry-run -Desired disable -LayoutFile ./deploy/release-layout.production.json
./scripts/release/set-shadow-judging.ps1 -Operation dry-run -Desired enable -LayoutFile ./deploy/release-layout.production.json
```

Every mutation requires both explicit execution intent and the owner gate:

```powershell
./scripts/release/set-shadow-judging.ps1 -Operation disable -LayoutFile ./deploy/release-layout.production.json -Execute -OwnerGate GO_DISABLE_SHADOW
./scripts/release/set-shadow-judging.ps1 -Operation enable -LayoutFile ./deploy/release-layout.production.json -Execute -OwnerGate GO_ENABLE_SHADOW
./scripts/release/set-shadow-judging.ps1 -Operation rollback -LayoutFile ./deploy/release-layout.production.json -Execute -OwnerGate GO_SHADOW_ROLLBACK
```

`GO_ENABLE_SHADOW`, `GO_DISABLE_SHADOW`, and `GO_SHADOW_ROLLBACK` authorize
only their named operation. Cross-operation gates, empty values, arbitrary
strings, Identity gates, and `GO_DEPLOY` are rejected. GO_DEPLOY does not
authorize Shadow enable, Shadow disable, Shadow rollback, or a kill-switch
drill.

The compose contract defaults an unset setting to `false`. The helper accepts
the application's existing true and false aliases when reporting effective
state, but mutations persist only canonical `true` or `false`. An unknown or
malformed value is reported as `invalid_fail_closed` and is treated as off.
Enabling from that state is refused; an owner-gated disable can remediate it to
canonical `false`.

## Mutation and recovery contract

For each mutation, the setter:

1. Acquires a non-reentrant host lock.
2. Creates a checksum-bound governed backup and metadata record.
3. Replaces the protected configuration atomically while preserving its
   owner, group, mode, and every non-Shadow byte.
4. Recreates only `app` and `scheduler` with the canonical release compose
   file, the exact currently running application image, and the existing named
   questions volume.
5. Uses bounded probes to require a healthy app, running scheduler and proxy,
   HTTP 200 from the canonical health endpoint, and matching normalized flag
   state in both application services.

If any post-change step fails, the setter uses the governed backup path to
restore the pre-change state, recreates the two application services again,
and verifies recovery. `rollback` selects the latest checksum-valid backup;
it first backs up the current state so a failed rollback can itself be
reversed. Output and audit records contain only normalized state, identifiers,
hashes, and health results—never unrelated keys or values.

## Governed kill-switch drill

The only supported public drill entry point is:

```powershell
./scripts/release/run-shadow-kill-switch-drill.ps1 -LayoutFile ./deploy/release-layout.production.json -Execute -OwnerGate GO_KILL_SWITCH_DRILL
```

`GO_KILL_SWITCH_DRILL` authorizes one bounded drill only. It does not authorize
an ordinary enable, disable, rollback, deployment, Identity mutation, GF-003
activation, or authoritative-judging change. `GO_DEPLOY` does not authorize
the drill.

The drill records initial effective state and requires three independent kinds
of evidence. `legacy_infrastructure_healthy` covers app/scheduler convergence,
the health endpoint, homepage, and login only; it is not evidence of judging
correctness. Real event-store observation proves that Shadow writes stop while
disabled and, when initially enabled, resume after restoration. The actual
Legacy judging canary directly invokes the rating answer flow's existing
server-side Legacy verifier with the tracked in-memory synthetic fixture and
expects its deterministic `correct` result. It does not load the puzzle corpus,
use a database or player request, invoke Shadow judging, or cause gameplay side
effects.

The Legacy judging canary must pass before mutation, while Shadow is disabled,
and after restoration. An unavailable, unsupported, skipped, indeterminate, or
unexpected result fails closed. Drill success requires infrastructure health,
real Shadow event-store observation, dashboard readability, all three Legacy
canary checkpoints, exact configuration restoration, and event resumption when
applicable. The report exposes only the canary name and expected/actual result
labels—never puzzle contents—plus both backup identities, final effective state,
and partial-state/restoration fields. Failure stages distinguish
`legacy_baseline`, `legacy_disabled`, and `legacy_restored`.

## Post-deploy owner drill checklist

This checklist is intentionally unexecuted in this work item. The owner must
record evidence for every step in one approved drill window:

- [ ] Record the initial governed flag status and initial Shadow event count.
- [ ] Invoke the wrapper with `GO_KILL_SWITCH_DRILL`; do not run its internal
  steps manually.
- [ ] Record the governed initial configuration backup identity.
- [ ] Verify `legacy_infrastructure_healthy`: app/scheduler convergence and the
  health, homepage, and login probes pass. Do not treat this as judging proof.
- [ ] Verify the actual Legacy judging canary returns its deterministic expected
  result before mutation, while Shadow is disabled, and after restoration.
- [ ] Verify zero new Shadow events are written during a bounded observation
  window with representative route traffic.
- [ ] Verify the Admin Shadow dashboard remains readable.
- [ ] Verify the wrapper restores the exact initial intended state.
- [ ] If initially enabled, verify real Shadow event-store writes resume after
  restoration.
- [ ] Record final governed flag status and before/disabled/after event counts.
- [ ] If any gate fails, retain the wrapper's partial-state report and verify
  its restoration attempt and final-state result.

Until all boxes have owner-recorded evidence, the completion state remains:

```text
PENDING OWNER-GATED DRILL
```
