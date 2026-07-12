# INCIDENT — Full-Site Static Asset Outage (2026-07-12)

```
Status:      Root cause confirmed, evidence preserved, remediation = RELEASE-FIX-A2
Detected via: manual browser report of broken images on landing/curriculum pages
Scope:       site-wide (not landing-only) -- 180 of 184 referenced local images
Root cause:  RELEASE-FIX-A's static-generation switch orphaned an undocumented,
             untracked assets/ tree that had been living inside the
             pre-switch "current" generation directory
Mitigation chosen: RELEASE-FIX-A2 (canonical asset import + closure), NOT a
             static-generation rollback -- see "Rollback path rejected" below
```

## Timeline

- **2026-07-10 16:37** — generation `20260710-163737-0d8407496-v177-sgf-fe-hotfix1a-node-parser`
  becomes `current`. At some undocumented point, a complete 757 MB `assets/`
  tree (1,391 files) is placed directly inside this generation directory —
  outside any tracked release contract. This is the *only* one of 94
  historical generations ever to carry an `assets/` subtree.
- **2026-07-12 13:35** — RELEASE-FIX-A deploys. Per its own (correctly
  scoped) contract it packages only `i18n.js` + `sw.js` into a fresh
  generation `20260712-133312-82db3cc5-v180-e9-1b-real-data-contract` and
  atomically switches `current` to it.
- **immediately after** — the new `current` has no `assets/` subdirectory.
  Every `/assets/<path>` request, site-wide, starts returning the themed
  Flask 404 page (`Content-Type: text/html`), not a real image response.
  `i18n.js`/`sw.js` (the only files RELEASE-FIX-A's contract manages) are
  unaffected and correct.

## Full-Site Asset Closure Audit (Phase 1-4 findings)

Scanned `*.html`, `*.js`, `*.py`, `*.json`, `*.css` at `master`
(`cb6b25c021271a9b0474a5fc0705f50cf2cce706`) for every locally-served image
reference — 344 reference sites resolving to **184 unique paths** across 28
files (`index.html`, `shop.html`, `bot.html`, `rating_test.html`,
`daily_challenge.html`, `play.html`, `upgrade.html`, `login.html`,
`landing.html`, `hero.html`, `games.html`, `curriculum.html`,
`messages.html`, `premium_weekly.html`, 10 blog files, `app.py`,
`manifest.json`, `sw.js`, `pwa.js`).

- **180 / 184** referenced paths return 404 in production (all
  `/assets/**`). The remaining 4 (`/icon-192.png`, `/icon-512.png`,
  `/og-image.jpg`, `/favicon.ico`) are tracked in `D:\go-website`, baked
  into the image, and unaffected.
- By category: storyboards (45), shop (23), monsters (22, selected
  server-side by `app.py` dict literals), go_rpg_assets_v3 (14),
  guild_bounty_assets (13), go_rpg_assets (12), rating_test (10), pets (9),
  upgrade_page_assets (8), play_page_assets (8), landing_page_assets (7,
  the original incident scope), hero (3), community (1).
- **Class C (dead reference, no candidate anywhere) = 0.** Every referenced
  path resolved to a real file somewhere.
- **178 / 180** referenced files exist, byte-identical (SHA-256 verified),
  in both `C:\go-website` (frozen candidate repo) and the orphaned
  production generation.
- **2 / 180** (`assets/go_rpg_assets/claire_avatar.webp`,
  `assets/shop/title_badge_recruit.webp`) exist only on the production
  host's orphaned generation — absent from `C:\go-website`.

## Rollback path rejected — why

A static-generation rollback to `20260710-163737-0d8407496-v177-sgf-fe-hotfix1a-node-parser`
was planned and fully specified (target/current generation IDs, i18n.js/sw.js
SHA-256 and VERSION on both sides, production health baseline: app healthy/0
restarts, postgres ID `45dd5cc8b101355b83ad651cff5909877580939b0143b01dd186bb2c8619e174`
RestartCount 0, questions.json = 41,591, `/healthz`/`/login`/`/` = 200).

**Blocker**: `scripts/release/rollback-static-release.ps1` reads
`manifest.json` from *inside* the target generation directory as its sole
source of truth. That target generation predates the RELEASE-FIX-A tooling
entirely and has no `manifest.json`. The only way to make the canonical
script run against it would be to author a manifest.json post-hoc, directly
on the production host, with `release_git_sha: null` (no commit's `i18n.js`
byte-matches that generation's copy — checked against `c33fd19bc`, the
commit that bumped `sw.js` to the matching `VERSION` string, and it does
not match). A rollback whose own manifest cannot cite real git provenance
undermines exactly the guarantee RELEASE-FIX-A's tooling exists to provide.

**Decision**: superseded in favor of RELEASE-FIX-A2 — a forward-fix that
imports the 180 referenced files as new, fully-provenanced, tracked
`D:\go-website` content and extends the canonical static-release contract
to manage `assets/` going forward, rather than reinstating an
undocumented historical directory as a live dependency again.

## Disposition of the original landing/login/blog HTML-only fix

The 12-file HTML simplification attempted under
`incident/20260712-landing-assets-fix1` (removing the 7
`landing_page_assets/*` references via CSS/icon substitution) is
**abandoned, not merged** — superseded by RELEASE-FIX-A2's asset import,
which restores the original images rather than removing/replacing them.
Those 12 files are restored to `HEAD` (`cb6b25c0`) unchanged.

## RELEASE-FIX-A3 addendum — the 180-path closure was incomplete

After RELEASE-FIX-A2 deployed its governed 180-file closure to production
(generation `20260712-180921-6b44f289-v181-release-fix-b-e9-i18n-fallback`),
live browser network audits of `/hero`, `/curriculum`, `/community`,
`/shop`, `/bot`, `/rating_test`, `/play`, `/upgrade`, `/landing`, and
`/login` still showed extensive broken images: hero character/gear/
accessory tiers, guild/tavern UI, and other runtime-composed paths.

**Root cause of the gap**: RELEASE-FIX-A2's closure manifest was built by
statically grep-ing tracked source for string literals containing a full
`/assets/...` path. That scan is blind to:

- Query-string-suffixed references (`/assets/shop/newbie_gift_pack.webp?v=1`)
  that never normalized to their bare path.
- A module-level "root" constant concatenated with a literal filename or
  a dict-literal lookup (e.g. `HERO_GEAR_ROOT + 'armor_t1.webp'`,
  `` `${HERO_ITEM_ROOT}unknown.svg` ``, `'/assets/hero/characters/' +
  CHARACTER_ART[key]`) — every one of these composes a real, fixed path at
  runtime, but no literal string in the source contains it.
- Genuinely data-driven composition (`root + value + '.webp'` where
  `value` comes from a database field or API response, or
  `(item.root || HERO_GEAR_ROOT) + (variant || item.art)` where `item`
  comes from a data array) — these can reference any member of a large,
  evolving set of images that a one-time literal scan can never fully
  enumerate no matter how it's improved.

**Conclusion**: a runtime-reference-derived allowlist is not an adequate
ownership boundary for this asset tree — it will always undercount by
however many dynamic-composition patterns exist in the code at scan time,
and silently miss new ones added later. The RELEASE-FIX-A2 180-file
closure was a real improvement over the RELEASE-FIX-A i18n/sw.js-only
scope, but it inherited the same "narrow to what we can currently prove is
referenced" framing that caused RELEASE-FIX-A's gap in the first place,
just one layer further out.

**New canonical ownership boundary**: `deploy/canonical-image-pack-manifest.json`
— the complete, byte-verified historical production image tree (1,298
files, 753,319,229 bytes; source generation
`20260710-163737-0d8407496-v177-sgf-fe-hotfix1a-node-parser`), independent
of what any static or runtime scan can currently prove is referenced.
Reference scanning (`scripts/release/asset_reference_scanner.py`,
`tests/test_release_fix_a2_asset_closure.py`,
`tests/test_release_fix_a3_canonical_image_pack.py`) remains valuable as a
**regression/observability layer** — it still catches a genuinely dead or
newly-introduced reference — but it is no longer the boundary that decides
what ships. `deploy/live-static-asset-inventory.json`'s `required_subtrees`
entry for `assets/` now points at the image-pack manifest instead of the
superseded 180-file closure manifest (which remains on disk, unreferenced,
as a historical record of the earlier fix).

**Correction to the static release contract**: this incident's earlier
"Rollback path rejected" section, and `docs/deployment/canonical_static_release_contract.md`,
both need to state plainly that `scripts/release/deploy-static-release.ps1`
manages only the `current` symlink — it has never written or maintained a
`previous` symlink. The `previous` symlink observed on the production host
is a legacy artifact that predates this tooling; `rollback-static-release.ps1`
has always taken an explicit `-TargetGenerationPath` parameter and never
reads `previous`. Any operator expecting `previous` to be a live, tooling-
maintained rollback pointer would be wrong to rely on it.
