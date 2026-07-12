# RELEASE-TOOLING-HOTFIX-02: ARM64 build contract

```
Branch: hotfix/release-build-arm64-contract
Base: master
Scope: scripts/build-production-image.ps1, scripts/release/ReleaseTooling.psm1,
       tests/deployment/*, docs/deployment/*
Production mutation: NONE
Deployment: NONE
```

## Trigger

Building the PREMIUM-UPSELL-HOTFIX-01 target release
(`b7ed3417281d3532b20d5b42a08f1736ade02a74`) via
`build-release-image.ps1 -ExpectedGitSha b7ed3417...` succeeded with no
errors, but the resulting image was the wrong architecture:

```
docker image inspect go-odyssey-app:b7ed3417 --format '{{.Os}}/{{.Architecture}}'
linux/amd64
```

Confirmed directly (not assumed) that production is real `aarch64`
hardware, and its currently-running image is `linux/arm64`:

```
ssh oracle_godoyssey "docker image inspect go-odyssey-app:latest --format '{{.Os}}/{{.Architecture}}' && uname -m"
linux/arm64
aarch64
```

Deploying the `linux/amd64` image built on this Windows/amd64 machine to
that host would not have worked correctly.

## Root cause

`scripts/build-production-image.ps1` ran a plain `docker build` with no
`--platform` flag at all. Plain `docker build` always targets the local
Docker daemon's native platform — on this Windows/amd64 development
machine, that silently produced a `linux/amd64` image every time, with
**no error or warning** that it didn't match production's `linux/arm64`
architecture. `deploy-release-image.ps1` does have an `-ExpectedPlatform
'linux/arm64'` check that would eventually have caught this — but only at
deploy time, much later, after a build+package cycle had already been spent
on the wrong artifact. This closes the gap at build time instead.

## Capability audit (performed before any code change, per the task's own requirement)

```
docker buildx version   -> v0.34.1-desktop.1 (available)
docker buildx ls         -> "desktop-linux" builder, status running,
                             platforms include linux/arm64
docker buildx inspect    -> confirms linux/arm64 in the active builder's
                             platform list
```

Then a real, minimal end-to-end capability test (before touching the real
build script): `docker buildx build --platform linux/arm64 --load` on a
trivial `alpine`-based Dockerfile, followed by `docker run` on the loaded
image. The image inspected as `linux/arm64` and **actually ran** (printed
`aarch64` from inside the container via QEMU/binfmt emulation) — confirming
not just that buildx claims arm64 support, but that a single-platform
`--load` arm64 image genuinely works end-to-end on this machine.

Only after this capability audit passed was the real fix implemented, per
the requirement not to build first and hope.

## Fix

- **`scripts/build-production-image.ps1`**:
  - New `-Platform` parameter, defaulting to `'linux/arm64'` — the
    production contract. Changing it requires explicitly passing
    `-Platform`; there is no environment variable or config file that can
    silently override it, and no fallback path if the requested platform
    isn't supported.
  - A capability preflight (`docker buildx version`, then `docker buildx
    inspect` parsed for the target platform in the active builder's
    platform list) runs **before** any build attempt. Failing either check
    calls the script's own `Fail` (exit 1) with a message naming the gap —
    never silently downgrades to plain `docker build`.
  - The build itself now uses `docker buildx build --platform $Platform
    --load` (never plain `docker build`), so the rest of the pipeline
    (`package-release-image.ps1`, `deploy-release-image.ps1`) still finds
    the image in the local Docker image store exactly as before.
  - **Immediately after build**, the resulting image's actual platform is
    inspected (via the new shared `Get-ImagePlatform` helper) and compared
    against `$Platform`. A mismatch calls `Fail` — the image is never
    handed off to the rest of the pipeline un-flagged. This is deliberately
    not the only platform check in the pipeline (`deploy-release-image.ps1`'s
    `-ExpectedPlatform` check is untouched and still runs later), but it is
    no longer the *first* line of defense.
- **`scripts/release/ReleaseTooling.psm1`**: new shared `Get-ImagePlatform`
  function (`docker image inspect <tag> --format '{{.Os}}/{{.Architecture}}'`,
  trimmed and lowercased), so the build script's new check and any future
  platform check read this the same way instead of each inlining their own
  format string. `build-production-image.ps1` now imports this module
  (it did not before).

## What was deliberately NOT changed

- `Dockerfile` — untouched.
- Application code — untouched.
- `deploy-release-image.ps1`'s existing `-ExpectedPlatform` check, owner
  gate, and rollback semantics — untouched. This hotfix adds an earlier
  gate; it does not touch or weaken the existing later one.
- Production — no SSH mutation, no deploy, no rollback triggered.

## Verification performed

- Real rebuild of the current branch tip (`-SkipCleanCheck`, since the
  working tree had this hotfix's own uncommitted changes) via the actual
  fixed script: package downloads showed `aarch64`/`arm64` wheels
  throughout, build succeeded, and the script's own post-build check printed
  `Verified image platform: linux/arm64` with `"platform": "linux/arm64"`
  in the final JSON record. Image removed after the test (`go-odyssey-app:e635c2fe`,
  a build-tooling test only — not the actual release artifact).
- Deliberate failure-path test: ran the script with `-Platform
  'linux/does-not-exist'` — failed closed with a clear message naming the
  capability gap (`"The active buildx builder does not report support for
  linux/does-not-exist..."`), did not attempt any build, did not fall back
  to any other platform.
- 9 new automated tests in `tests/deployment/test_release_tooling.py`:
  buildx used (not plain `docker build`), default platform is arm64,
  `-Platform` is a real overridable parameter, `--platform`/`--load` passed
  to buildx, capability preflight exists before any build attempt, platform
  verified immediately after build (not before), mismatch fails closed, no
  silent fallback between the capability check and the build call, and the
  shared `Get-ImagePlatform` helper exists/is exported/is actually imported
  by the build script.
- Full `tests/deployment/` suite: 152 passed (was 151 pre-existing + 1 new
  file's worth, all passing; one pre-existing test,
  `test_build_script_safety.py::test_script_never_deploys_or_touches_remote_hosts`,
  initially false-failed because an early draft of this fix's own
  documentation comment contained the literal substring `ssh ` while
  explaining how the production architecture was confirmed — reworded to
  remove that false positive, not to weaken the check).

## Important structural note for the "rebuild target commit b7ed34172" step

`build-release-image.ps1` builds from a **detached worktree checked out at
the exact target commit**, and invokes `scripts\build-production-image.ps1`
**from that worktree** — i.e. it always runs the build script *as it
existed at the target commit*, not whatever version exists on the branch
doing the invoking. This is deliberate (byte-for-byte reproducible builds
of a specific historical commit, not silently influenced by later tooling
changes).

Consequence: literally re-running `-ExpectedGitSha
b7ed3417281d3532b20d5b42a08f1736ade02a74` after this hotfix merges will
**still use `b7ed34172`'s own (unfixed) `build-production-image.ps1`** and
reproduce the same wrong-architecture bug — because that commit predates
this fix. Once this PR merges, "rebuilding the target release" in practice
means building the new `master` tip (which contains `b7ed34172`'s changes
in its ancestry, plus this fix, plus RELEASE-TOOLING-HOTFIX-01), not the
literal old SHA. This is a decision for whoever resumes the deploy step —
flagged here explicitly rather than silently assumed away.

## Status

```
RELEASE-TOOLING-HOTFIX-02: READY FOR REVIEW
```

Do not deploy from this branch. Do not merge without review. The wrong-arch
local image `go-odyssey-app:b7ed3417` (linux/amd64) was left untouched for
inspection, per instruction — not packaged, not deployed, not used to
update any manifest.
