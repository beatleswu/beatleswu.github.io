# A041 Loadout client-cache browser and static-release validation

## Scope and lineage

- `CURRENT_ORIGIN_MASTER=6829c4c528adf4800326e90534585a32e390ebec`
- `BASE_SHA=0287031118375f5dd0786ff0d41c9420a6a0dd5a`
- `A040_HEAD=0287031118375f5dd0786ff0d41c9420a6a0dd5a`
- `FRESH_MASTER_RECONCILIATION=PASS`
- `FRESH_MASTER_IS_ANCESTOR=YES`
- The A041 worktree is isolated from `D:\go-website`; A040 is not assumed to
  be merged into `origin/master`.

## Browser evidence

The actual A040 `hero.html`, `inventory.html`, `index.html`, `curriculum.html`,
and `bot.html` were served by a disposable same-origin fixture. The fixture
returned deterministic server-owned `/api/player/*` and `/api/skills/profile`
payloads and did not import `app.py`, open a database, or mutate repository
data.

The established `E10_PLAYWRIGHT_CORE` path was available at
`D:\go-website\node_modules\playwright-core` (version `1.61.1`), and the
Codex in-app browser executed the checks. Physical-device proof was not
claimed.

For Desktop (`1440x900`), iPad landscape (`1180x820`), iPad portrait
(`820x1180`), and Mobile (`390x844`), every run showed:

- Hero server hydration ready, with `wooden_sword`, `cloth_robe`, and
  `lucky_stone` projected from the fixture inventory.
- Backpack status ready, with four server inventory cards and three equipped
  cards matching Hero.
- The un-equipped `iron_sword` selection displayed `尚未開放裝備` / `Equip
  unavailable` with a disabled action, so Loadout remained gated.
- No horizontal overflow and no console errors.

The stale-cache scenarios seeded a conflicting valid cache, invalid JSON, and
unknown/unowned equipment. After loading Hero, all scenarios still showed the
server-owned equipment and `character-authority=ready`; no fabricated ownership
or crash occurred. The storage handoff used an isolated prior-user-like cache
and a fixed fixture user (`user_id=41041`), so no cross-user cache leak was
observed.

The changed Index, Curriculum, and Bot surfaces also loaded with no overflow or
console errors. The Index service worker registered normally. A clean request
log recorded zero static 404s and HTTP 200 for the guard requests:
`/js/hero_legacy_cache_guard.js?v=20260829a0401`.

## Static-release result

A040's source references are present exactly twice, in `hero.html` and
`index.html`, and `js/hero_legacy_cache_guard.js` exists. The source HTML is
therefore browser-reachable, but the governed release bundle is not:

- `deploy/live-static-asset-inventory.json` does not list the guard in
  `eligible_files.entries`.
- It also does not list the guard in `required_in_generation.entries`.
- It is not part of the declared E10 dependency closure.
- `scripts/release/ReleaseTooling.psm1::New-StaticReleaseBundle` stages the
  required-generation list, so the guard would be omitted while
  `index.html` references it.
- `deploy/build-manifest.json` also lacks the guard from
  `build_inputs.tracked_in_canonical_branch_this_sprint`.

Therefore:

```text
LEGACY_CACHE_GUARD_GOVERNED=NO
LEGACY_CACHE_GUARD_STAGED=NO
LEGACY_CACHE_GUARD_RELEASE_REACHABLE=NO
A040_PACKAGING_GAP_FOUND=YES
A040_B056_RELEASE_COMPATIBILITY=BLOCKED_ADDITIONAL_PACKAGING_CHANGE_REQUIRED
```

A041 deliberately did not change the manifests or release tooling. B057 must
add the exact guard path to `eligible_files.entries` and
`required_in_generation.entries`, add it to the build-input/provenance records
required by the release contract, and generate the governed hash/size entry.
The four A040 HTML files are already present in the build-input inventory.

The `?v=20260829a0401` cache-busting reference is valid; `sw.js` was not
changed and the browser service-worker/cache behavior remained intact. This
does not compensate for the missing governed static entry.

## Boundaries and regressions

No `app.py`, runtime source, `sw.js`, C049, B056, or other active-lane file was
modified. No schema/data migration, Shop/Loadout enablement, production
query/mutation, deployment, or merge was performed.

Focused A034-A040/equipment tests passed (`78 passed, 4 skipped`), the A040
Node guard suite passed (`9 passed`), the A028 Hero presentation Node suite
passed (`14 passed`), damage/equipment regression passed (`23 passed`), and
the xp_amulet/shop boundary suite passed (`32 passed`).

Existing baseline failures remain outside A041's changed scope:

- runtime dependency closure has ten pre-existing Docker omissions;
- E9 CSS inventory has the pre-existing `adventure_spirit_unlock.css` drift;
- static-release tooling has seven pre-existing failures, including the
  PowerShell environment's missing `Get-FileHash` command and the existing
  allowlist drift;
- the E10 global-navigation test has the pre-existing duplicate event
  producer observation.

These are reported as pre-existing; `TASK_INTRODUCED_FAILURES=0`.

## Classification

`BLOCKED_LOADOUT_CLIENT_CACHE_BROWSER_AND_STATIC_RELEASE_VALIDATION`

The A040 browser/cache behavior is validated, but the required B057 governed
static packaging metadata is missing. A042 was not started.
