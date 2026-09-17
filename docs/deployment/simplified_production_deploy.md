# Simplified Canonical Production Deployment

Status: current. `scripts/release/deploy-production.ps1` is the recommended primary entrypoint for
deploying an exact Git SHA to Production. It replaces
[Deployment Workflow V3](deployment_workflow_v3_bounded_recovery.md) as the *recommended* path;
V3 remains in the repository as non-primary tooling and is not deleted.

## The command

```powershell
.\scripts\release\deploy-production.ps1 `
    -ExpectedGitSha <40-char SHA> `
    -LayoutFile deploy\release-layout.production.json `
    -Execute `
    -OwnerGate GO_DEPLOY
```

Without `-Execute` the same command runs `PRECHECK → BUILD → PACKAGE → BASELINE` and stops. That
proves the candidate and reads the live baseline without changing anything, which makes it a safe
pre-flight before asking for the owner gate.

The gate vocabulary is unchanged: `GO_DEPLOY` to deploy, `GO_ROLLBACK` for the rollback steps the
script performs on its own when a post-mutation step fails. No new authorization vocabulary was
introduced.

## The eight phases

| Phase | What it establishes |
|---|---|
| `PRECHECK` | Owner gate, 40-char SHA, clean tracked **and** untracked tree, `HEAD == ExpectedGitSha`, layout loads, all artifact paths derived from the SHA |
| `BUILD` | Docker engine reachable, buildx builder active and reporting `linux/arm64`, then the canonical build — or, if an exact candidate already exists, no rebuild at all |
| `PACKAGE` | App and static artifacts exist at their derived paths and their manifests carry the exact SHA |
| `BASELINE` | App, scheduler and static source SHAs read independently and are **all equal**; rollback identities captured |
| `STATIC` | `deploy-static-release.ps1` promotes static, then the live static SHA is re-read |
| `APP` | `deploy-release-image.ps1` promotes app and scheduler, then all three SHAs are re-read |
| `VERIFY` | All three at the expected SHA, canonical production verification, canonical public static acceptance |
| `SUCCESS` | Only reached when every check above passed |

## The two rules that make it predictable

**It never parses a child script's human-readable stdout.** Every fact comes from one of three
deterministic sources:

1. a child process **exit code**;
2. an **artifact file** whose path is derived from the SHA via `Get-ReleaseArtifactBaseName`
   (`release-artifacts/go-odyssey-app_<short>.release.json`, `.static.json`, `.deployment.json`, …);
3. a **direct identity read** — a `--format` template or a file read over SSH.

This is not a stylistic preference. The path this replaced located its child's JSON payload by
scanning stdout for the first `{`. A real build emitted a brace inside an ordinary log line before
its payload, so a completely successful build was reported as a phase failure, discarded, and a
retry slot was burned. Removing stdout scraping removes that entire failure class rather than
hardening it.

**It has no generic recovery machinery.** No state machine, no root-cause taxonomy, no per-error
retry budget. Each phase runs once. The only automatic recovery in the whole script is a single
bounded `docker buildx inspect --bootstrap` when the local builder is not reporting platforms —
and that happens *before* the expensive build begins, so a transient local builder blip no longer
costs a full build gate cycle. If the builder is still unusable afterwards, the script stops
before Production is touched. It never falls back to plain docker and never assumes `linux/arm64`.

## Identity domains are never conflated

Three separate things are read, in their own domains:

- **App / scheduler source SHA** — the `org.opencontainers.image.revision` OCI label on the image
  each container is actually running.
- **Static source SHA** — `release_git_sha` inside `manifest.json` of the generation that
  `current` actually resolves to.
- **Static generation path** — a filesystem path, used as the rollback target.

An image ID is a content digest and a generation path is a path. Neither is a Git SHA, and neither
is ever compared to `-ExpectedGitSha`.

## Failure contract

If any step fails after Production was mutated, the script rolls back exactly what this run
promoted — app first (using the deployment record `deploy-release-image.ps1` itself wrote, which is
the only artifact carrying the pre-promotion image identity), then static (to the generation path
captured in `BASELINE`) — and then **re-reads all three identities**. The rollback tools' own
success reports are not the final word.

- All three back at the original baseline → `FAILED_BASELINE_RESTORED`, exit 1.
- Anything else → `MIXED_OR_UNVERIFIED`, exit 2, and no further mutation is attempted.

A zero exit code from a child is never sufficient on its own. If `deploy-release-image.ps1` exits 0
but only the app moved and the scheduler did not, the identity re-read catches it and the run
rolls back rather than reporting success.

## Result channel

Human phase output and the machine result share stdout, so the final record is emitted through the
repository's existing framed envelope (`__GO_ODYSSEY_POWERSHELL_RESULT_V1__:` +
base64 JSON, via `ConvertTo-FramedJsonRecord`). Anything consuming this script's output should use
`ConvertFrom-FramedJsonRecord` — the same convention `verify-production-release.ps1` and
`rollback-release.ps1` already use behind `-FramedResult`. Possible `result` values:
`DEPLOYMENT_VERIFIED`, `ALREADY_AT_TARGET`, `PREPARED_NOT_EXECUTED`, `FAILED_BASELINE_RESTORED`,
`MIXED_OR_UNVERIFIED`.

## Time bounds

Each child invocation carries its own finite bound, enforced by `Invoke-BoundedNativeCommand`
(process-tree kill on expiry). Because each phase runs its child exactly once, the per-invocation
bound and the per-phase worst case are the same number — there is no replay loop that could
multiply them. The build bound is the largest at 3900s; identity reads are 30s.

## Retirement of V3

The sequence is: replacement → real validation → prove the old path unnecessary → retirement.
`deploy-coordinated-release.ps1`, `CoordinatedReleaseStateMachine.psm1` and their tests are
untouched by this change and remain runnable. Deleting them is gated on `deploy-production.ps1`
having successfully deployed Production at least once.

## Tests

`tests/deployment/test_deploy_production_simplified_path.py` runs the real script inside a
throwaway git sandbox whose child release scripts and `docker`/`ssh` executables are fakes, so the
rollback and identity assertions observe real control flow. It covers the deterministic phase
order, buildx recovery and its failure, build failure, mixed baseline, static failure, app failure
with double rollback, unverifiable rollback, partial promotion, and the success contract — plus
source-level guards that the primary path contains no stdout JSON parsing and no state-machine or
root-cause-taxonomy dependency.
