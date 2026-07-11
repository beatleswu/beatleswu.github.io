# Rollback Runbook

Use `scripts/release/rollback-release.ps1` for the future rollback path.

## Inputs

- `RollbackManifest`
- `-Execute`
- `-OwnerGate GO_ROLLBACK`

## Required Checks

1. Validate the rollback manifest is unambiguous.
2. Restore the app first.
3. Verify app health before touching the scheduler.
4. Restore the scheduler only after the app is healthy.
5. Confirm both services use the rollback image.
6. Leave PostgreSQL untouched.
7. Preserve the failed candidate image and evidence.

## Safety Boundary

- Default mode is dry-run.
- Real rollback remains gated and is not executed by this PR.
- No secret values should be printed.
