# Shadow Judging kill switch

Status: **PENDING OWNER-GATED DRILL**

This runbook defines the technical contract for changing only
`SHADOW_JUDGING_ENABLED`. The implementation and synthetic tests do not
authorize a Production change. A Production drill may happen only after the
change is merged, the owner explicitly approves the drill, and the operator
supplies the `GO_DEPLOY` gate under the canonical DEPLOY-GOV-1 release/config
governance.

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
./scripts/release/set-shadow-judging.ps1 -Operation disable -LayoutFile ./deploy/release-layout.production.json -Execute -OwnerGate GO_DEPLOY
./scripts/release/set-shadow-judging.ps1 -Operation enable -LayoutFile ./deploy/release-layout.production.json -Execute -OwnerGate GO_DEPLOY
./scripts/release/set-shadow-judging.ps1 -Operation rollback -LayoutFile ./deploy/release-layout.production.json -Execute -OwnerGate GO_DEPLOY
```

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

## Post-deploy owner drill checklist

This checklist is intentionally unexecuted in this work item. The owner must
record evidence for every step in one approved drill window:

- [ ] Record the initial governed flag status and initial Shadow event count.
- [ ] Disable Shadow through the owner-gated setter.
- [ ] Verify all covered player routes remain healthy and Legacy responses are
  unchanged.
- [ ] Verify zero new Shadow events are written during a bounded observation
  window with representative route traffic.
- [ ] Verify the Admin Shadow dashboard remains readable.
- [ ] Re-enable Shadow through the owner-gated setter.
- [ ] Verify Shadow events resume while Legacy responses remain unchanged.
- [ ] Record final governed flag status and before/disabled/after event counts.
- [ ] If any gate fails, run the governed rollback operation and retain its
  sanitized result with the drill evidence.

Until all boxes have owner-recorded evidence, the completion state remains:

```text
PENDING OWNER-GATED DRILL
```
