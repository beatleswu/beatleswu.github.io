# RELEASE-FIX-A — Canonical Static Release Integrity Contract

```
Sprint: RELEASE-FIX-A
Branch: feature/release-fix-a-static-integrity
Base: master @ f621a5ccff329b3b5ef4bf08f2e8260843ed01d9
Production mutation target: static generation switch only (no app/scheduler
image change, no DB change, no E9 code change)
```

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
- **`assets/` and `icons/` are explicitly excluded** (see
  `deploy/live-static-asset-inventory.json`'s `excluded_prefixes`) — these
  are externally-versioned media content (757MB+) with their own separate
  lifecycle, matching the Dockerfile's own "Content and asset boundary"
  philosophy; they are not git-tracked application code with a canonical
  source commit the way `i18n.js`/`sw.js` are.
- **`E9.1B`'s `t(key, fallback)` fallback-helper defect is NOT fixed here**
  — that is `RELEASE-FIX-B / E9-I18N-FALLBACK`, an independent code-level
  defect in `js/e9/{top_hud,right_cards,world_stage}.js`, deliberately kept
  out of this infrastructure-only PR.

## Release flow

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
