# RELEASE-FIX-A — Canonical Static Release Integrity Contract

```
Sprint: RELEASE-FIX-A
Branch: feature/release-fix-a-static-integrity
Base: master @ f621a5ccff329b3b5ef4bf08f2e8260843ed01d9
Production mutation target: static generation switch, plus an app/scheduler
container RESTART (not an image change -- same image, same tag; see
"Second discovery" below for why the restart turned out to be required)
```

## Second discovery, made live during this Sprint's own production deploy

The atomic symlink switch (`ln -sfnT` + `mv -Tf`) is filesystem-correct
immediately -- `sha256sum` on the HOST showed the new file the instant the
switch completed. But the running `go-odyssey-app` container, reading the
exact same bind-mounted path, kept serving the OLD content:

```
$ sha256sum /opt/go-odyssey-static/current/i18n.js         # host
0f21f945...   (new)
$ docker exec go-odyssey-app sha256sum /opt/go-odyssey-static/current/i18n.js
bf84cca2...   (still old!)
```

The container's bind mount resolves the `current` symlink's target **once,
at container start** -- changing what the symlink points to on the host
afterward has zero effect on the running container's view until it
restarts. `deploy-static-release.ps1`'s own public-HTTP verification step
correctly caught this (it fetches the real, external `https://godokoro.com/`
response, not the host filesystem) and auto-rolled the symlink back exactly
as designed -- proving the safety net works, at the cost of revealing that
the switch alone was insufficient. Both `deploy-static-release.ps1` and
`rollback-static-release.ps1` now restart `app`+`scheduler` (with a health-check
wait and a container-internal hash re-check) immediately after every
symlink switch, before the public verification step. This means a static
release deploy is **not** the zero-container-impact operation the untracked
`deploy-static.ps1` claimed ("App/scheduler container rebuild: none") --
that claim was never actually validated against this host's real bind-mount
behavior. The image itself is unchanged; only a restart is required.

## Third discovery, RELEASE-FIX-A2 (2026-07-12, the day after this Sprint's own deploy)

This Sprint's "Deferred scope" section originally claimed `assets/` was
"already absent from the drifted `/opt/go-odyssey-static/current` directory
the whole time" and therefore out of scope. **That claim was wrong.** Direct
host inspection during RELEASE-FIX-A2 found that the generation this
Sprint's own switch replaced —
`20260710-163737-0d8407496-v177-sgf-fe-hotfix1a-node-parser` — physically
contained a complete, undocumented, untracked 757MB `assets/` tree (1,391
files) alongside the stale `i18n.js`/`sw.js` this Sprint was correctly
fixing. Only that one generation, out of 94 historical ones, ever carried
an `assets/` subtree — evidence of a manual, out-of-band host copy at some
prior point, never part of any tracked release process.

Because this Sprint's own contract scoped `required_in_generation` to just
`i18n.js`/`sw.js` (a correct, narrow fix for the confirmed i18n drift), the
new generation it created had no `assets/` subdirectory. Switching `current`
to it — the exact operation this Sprint's tooling exists to perform safely —
silently orphaned every image on the site (see
`docs/incidents/2026-07-12-full-site-asset-outage.md` for the full RCA: 180
of 184 referenced images returned 404 immediately after this Sprint's
deploy).

**Lesson**: "confirmed absent" must mean confirmed by direct inspection of
the specific generation being replaced, not inferred from what the
tooling's own contract happens to manage. RELEASE-FIX-A2 moves `assets/`
into `required_subtrees` (see `deploy/live-static-asset-inventory.json`),
staged from a declarative closure manifest
(`deploy/canonical-asset-closure-manifest.json`) covering exactly the 180
files a live runtime-reference scan found in use — not the full 757MB
historical tree, and not a wholesale directory copy.

## Root cause (confirmed, not assumed)

`app.py`'s `_serve_live_static_or_baked` / `_serve_live_static_or_baked_subpath`
check `GO_ODYSSEY_LIVE_STATIC_ROOT` (`/opt/go-odyssey-static/current`, a
read-only bind mount into the app/scheduler containers) **first**, falling
back to the file baked into the Docker image only if the live-static file is
absent. Confirmed via direct host inspection during E9.1B-ACCEPT1:

```
$ ssh oracle_godoyssey "ls -la /opt/go-odyssey-static/current/i18n.js /opt/go-odyssey-static/current/sw.js"
-rw-rw-r-- 1 ubuntu ubuntu 331211 Jul 10 16:43 i18n.js
-rw-rw-r-- 1 ubuntu ubuntu   5555 Jul 10 16:43 sw.js
```

Both files are dated **2026-07-10 16:43** and contain zero `e9.*` i18n keys;
the served `sw.js` VERSION was `v177-sgf-fe-hotfix1a-node-parser` — the
value from *before* E9.1A2 started, not the `v180-e9-1b-real-data-contract`
baked into the current release image (`go-odyssey-app:f621a5cc`). Every
`i18n.js`/`sw.js` change across E9.1A2, E9.1A2 Rev2, E9.1A2-FIX1, and E9.1B
was correctly committed, correctly baked into four separate Docker images,
and correctly passed every existing test — but never reached a real
browser, because the live-static override silently took priority.

## Discovery: an existing, undocumented, un-tracked mechanism

The host already runs a fairly sophisticated immutable-generation system,
just not one this repository tracks or the current release pipeline
invokes:

```
/opt/go-odyssey-static/
  current  -> releases/20260710-163737-0d8407496-v177-sgf-fe-hotfix1a-node-parser
  previous -> releases/20260704-173425-fa8c1e8e8f
  releases/   (93 generation directories, named <timestamp>-<short-sha>-<sw-version-label>)
```

The tool that produced these generations, `/opt/go-odyssey/deploy-static.ps1`,
lives **only on the production host** (not in this Git repository) and is
hard-coded to a single historical branch:

```powershell
$expectedBranch = "optimize-pets-map-images"
```

Any invocation from `master` or any E9 feature branch would immediately
`Fail "Branch mismatch..."` — this is the direct mechanical reason no prior
Sprint's `i18n.js`/`sw.js` change ever reached this publish step: the tool
itself refuses to run from any branch used since. This matches the
already-documented, already-known gap in
`docs/deployment/canonical_image_build.md`:

```
PENDING — STATIC RELEASE TOOLING
```

`deploy-static.ps1`'s design is otherwise sound (atomic `ln -sfnT` +
`mv -Tf` symlink switch, remote SHA-256 validation post-upload, public
cache-busted content verification, a printed rollback command) and is used
below as a design reference — but it is not adopted as-is. It is an
untracked, host-only script of exactly the kind ADR-0001's governance model
exists to supersede (the same category as the frozen `C:\go-website\deploy.ps1`).
This Sprint builds new, tracked, tested equivalents in `scripts/release/`.

## Architecture decision: Option B (release-bound static generation)

**Chosen over Option A (image-only serving)** because:

1. The host's existing `releases/<gen>/` + `current`/`previous` symlink
   structure already IS this design, with 93 generations of established
   operational history — ripping it out (Option A) would be a larger, less
   reversible change disconnected from proven practice, for no
   corresponding safety benefit (Option B closes the actual gap: nothing
   invokes the publish step, not that the mechanism itself is unsound).
2. Removing the live-static override would require an `app.py` route
   semantics change, explicitly out of scope for this Sprint.
3. The `current`/`previous` symlink pair already gives O(1) rollback
   without touching image/container state — valuable independent of the
   image-based canary/rollback this repo's release pipeline already has.

**This Sprint reuses the existing generation naming convention and
directory layout** (`releases/<YYYYMMDD-HHMMSS>-<short-sha>-<sw-version-label>/`,
atomic `current`/`current.next` symlink switch) rather than inventing a new
one, for continuity with the 93 pre-existing generations and because it is
already a proven pattern on this exact host.

## Deferred scope (explicit, not silent)

- **Only `i18n.js` and `sw.js`** are managed by this Sprint's tooling (see
  `deploy/live-static-asset-inventory.json`'s `required_in_generation`).
  These are the only two files confirmed physically present in the drifted
  `/opt/go-odyssey-static/current` directory — every other file in
  `_LIVE_STATIC_ELIGIBLE_FILES` (36 HTML pages) was absent from that
  directory the whole time and was therefore already correctly falling
  back to the Docker image's baked copy, unaffected by this bug. Widening
  static-release management to cover those 36 files is a separate, future
  decision, not silently bundled into this fix.
- **`icons/` is explicitly excluded** (see
  `deploy/live-static-asset-inventory.json`'s `excluded_prefixes`) — no
  current runtime reference resolves to it.
- **`assets/` was excluded here, and that was wrong** — see "Third
  discovery" below. RELEASE-FIX-A2 moved it to `required_subtrees`.
- **`E9.1B`'s `t(key, fallback)` fallback-helper defect is NOT fixed here**
  — that is `RELEASE-FIX-B / E9-I18N-FALLBACK`, an independent code-level
  defect in `js/e9/{top_hud,right_cards,world_stage}.js`, deliberately kept
  out of this infrastructure-only PR.

## Release flow

### Tooling modes

`deploy-static-release.ps1` has three deliberately separate modes:

1. **Dry-run** (`-Execute` omitted): local validation and plan generation only.
   It does not validate the owner gate, open SSH, inspect Production, switch
   `current`, restart services, or write an accepted deployment record. Its
   result is `dry_run: true` with `result: DRY_RUN_COMPLETE`.
2. **Read-only Production preflight**: `preflight-production.ps1` owns remote
   identity, health, drift, and rollback-readiness checks.
3. **Execute** (`-Execute -OwnerGate GO_DEPLOY`): the mutation path, followed
   by verification and automatic rollback on failure.

This separation prevents a local plan from being confused with a remote
preflight while keeping the mutation gate explicit.

```
1. package-static-release.ps1  -- from an exact-SHA detached worktree,
   stage i18n.js + sw.js per the inventory, compute SHA-256, parse sw.js
   VERSION, write a static release manifest (mirrors the existing image
   release manifest shape).
2. deploy-static-release.ps1   -- upload the two files + manifest to a
   NEW remote releases/<gen>/ directory (fails if that exact path already
   exists -- never overwrites a generation), verify remote SHA-256 for
   each file, atomically switch current -> releases/<gen>/ via
   ln -sfnT + mv -Tf (recording the previous target first), then verify
   the PUBLIC HTTPS-served bytes (not just the container filesystem or the
   host directory) match the manifest's checksums and that sw.js's VERSION
   is readable from https://godokoro.com/sw.js.
3. rollback-static-release.ps1 -- switch current back to a named previous
   generation, with the same public-HTTP verification.
```

`preflight-production.ps1` is extended to report the current live-static
generation identity and its file hashes as part of the standard
pre-deploy baseline, so any future drift between the declared release and
what a browser actually receives is visible before deploy, not discovered
after the fact by a real player (or another Acceptance sprint).

## Correction (RELEASE-FIX-A3): `previous` is not managed by this tooling

The "Release flow" section above, written when this contract was first
adopted, describes step 2 as "recording the previous target first" and
step 3 as switching "back to a named previous generation" — this reads as
though `deploy-static-release.ps1` maintains `/opt/go-odyssey-static/previous`
as a live rollback pointer. It never has:

- `deploy-static-release.ps1` reads the pre-switch `current` target into a
  local variable (`$previousCurrentTarget`) solely so its own catch block
  can auto-rollback if the *same deploy* fails after the symlink switch —
  it is a transient in-memory value, included informationally in the
  result JSON, and is never written to a `previous` symlink on disk.
- `rollback-static-release.ps1` has always taken an explicit
  `-TargetGenerationPath` parameter and reads that target generation's own
  `manifest.json` as its sole source of truth. It has never read or relied
  on a host `previous` symlink.
- The `previous -> releases/20260704-173425-fa8c1e8e8f` symlink shown in
  the "Discovery" section above is a legacy artifact left over from the
  untracked, host-only `deploy-static.ps1` that predates this repo's
  tooling entirely. Nothing in `scripts/release/` updates it, and an
  operator should not expect it to reflect the generation this tooling
  most recently deployed away from.

**Practical implication**: rollback always requires citing an explicit,
known-good generation path (e.g. from `preflight-production.ps1`'s history
or a prior deploy's own output) — never "roll back to `previous`" as a
bare instruction, since that symlink's target is not guaranteed to be
anything this tooling put there.

## Security boundary

`deploy/live-static-asset-inventory.json`'s `forbidden_patterns` plus the
tooling's own path-traversal/absolute-path/symlink-escape checks are the
same class of defense-in-depth `deploy-static.ps1` already proved out
(`Assert-Safe-RelativePath`, `Assert-Allowed-StaticFile`) — re-implemented
here as tracked, tested code rather than copied from the untracked host
script.

## Service Worker safety

This Sprint does not change `sw.js`'s cache strategy. The static release
tooling's public-verification step specifically re-fetches
`https://godokoro.com/sw.js` with a cache-busting query parameter
(`?deploy-verify=<sha>`, matching `deploy-static.ps1`'s own proven pattern)
so a stale CDN/browser cache cannot mask a successful switch as a failure,
or vice versa.

## Scale-aware public verification budget

Public hash verification uses a bounded deadline derived from manifest file
count, verification concurrency, per-request timeout, and attempt count.
The budget includes 30 seconds of startup allowance, 30 seconds of completion
allowance, and a 60-second scheduling/TLS/cache safety margin. It is clamped
between 120 and 7,200 seconds. Attempt count means the initial request plus
configured retries; the current verifier uses one attempt.

The deployment record reports file count, verified results, HTTP failures,
hash mismatches, request timeouts, global-deadline cancellations, unexpected
exceptions, and remaining work. A global-deadline cancellation is not
reported as a request timeout. Operators must not manually alter verifier
timeouts to bypass this contract.
