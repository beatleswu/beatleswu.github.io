# Live-Static Drift Impact Audit — 2026-07-12

```
Scope: assess which past commits/Sprints' i18n.js / sw.js changes were
       actually served to real production browsers, versus masked by the
       stale live-static generation discovered during E9.1B-ACCEPT1.
Method: compare served file SHA-256 against git blob SHA-256 across every
        commit that touched these two files; classify by evidence, not
        assumption.
```

## Ground truth collected

```
Production served (as of 2026-07-12, pre-FIX-A):
  /opt/go-odyssey-static/current -> releases/20260710-163737-0d8407496-v177-sgf-fe-hotfix1a-node-parser
  i18n.js sha256: bf84cca277addbdc408e83c55e93559cdb94e710b0a68fe8e43a9ea64c6e672a
  sw.js   sha256: 150e0ecbef379637c48d53a6e43c20a6610dc384e1adf782a674e8775f9b4aed
  sw.js VERSION (served): v177-sgf-fe-hotfix1a-node-parser
```

`git log --all -- i18n.js` (45 commits touching the file across every ref
this repo has) does **not** contain a blob matching the served SHA-256.
This is consistent with `i18n.js`'s documented provenance category — per
`deploy/runtime-source-provenance.json`, this file's Git history in this
repository is itself "local Git provenance -- not previously pushed to
canonical origin," i.e. recovered from Graph A/Codex branches with murky
history, not a clean linear history this repo can fully reconstruct. The
served content most likely came from a deploy predating this repo's own
adoption of `i18n.js` as a tracked, canonical file, via the (now known to
be broken) `deploy-static.ps1` path directly from a working tree — not
from any commit this audit can name.

## Classification

| Item | Classification | Evidence |
|---|---|---|
| Everything up to and including the `v177-sgf-fe-hotfix1a-node-parser` release (2026-07-10 16:43) | **Unaffected** | This IS the content actually served; whatever `deploy-static.ps1` run produced it succeeded at the time. Includes the "RQ-HOTFIX2" i18n retrofit referenced in provenance history (predates this drift by definition — it's part of what was captured *as* the July 10 baseline, not a later change). |
| `E9.1A2` (PR #79, `e9.*` keys, `sw.js` v178) | **Definitely not served** | `sw.js` VERSION jump v177→v178 never appeared in production; confirmed served VERSION was still v177 as of this audit. |
| `E9.1A2 Rev2` (i18n stale-rescan fix commit, `sw.js` v179) | **Definitely not served** | Same reasoning — v179 never appeared in production. |
| `E9.1A2-FIX1` (Dockerfile packaging fix) | **Unaffected by this specific bug** | FIX1 did not change `i18n.js`/`sw.js` content or VERSION — it fixed `js/e9/`, `css/e9/`, `components/adventure/` packaging, which are NOT in `_LIVE_STATIC_ELIGIBLE_FILES` at all (confirmed: `app.py`'s live-static allowlist has no entry for those three subpath trees' *specific files*, only the `assets/`/`icons/` prefixes and 38 named root files — the E9 static routes added in E9.1A2 delegate straight to `_serve_live_static_or_baked_subpath` with `live_static_subdir='js/e9'` etc., which DOES check the live-static root by the same mechanism, but no generation ever populated `js/e9/`, `css/e9/`, or `components/adventure/` under `/opt/go-odyssey-static/current/` -- confirmed absent, so those files correctly fell back to the (correctly FIX1-packaged) Docker image the whole time). |
| `E9.1B` (adapters, `sw.js` v180, new `e9.*` i18n keys) | **Definitely not served** | This is the exact defect E9.1B-ACCEPT1 caught: served `daily_challenge_available`/`daily_challenge_done` keys render as raw key text. |
| Any other non-E9 feature that touched `i18n.js`/`sw.js` between 2026-07-10 16:43 and this audit | **Needs manual smoke** (none identified) | `git log --oneline master..HEAD` for the period between the last static-release generation and RELEASE-FIX-A's start shows only E9-prefixed commits touching these two files (verified via `git log -- i18n.js sw.js`); no other feature branch's `i18n.js`/`sw.js` change reached `master` in that window as of this audit. |

## Conclusion

The blast radius is fully bounded to the four E9 Sprints (E9.1A2 onward).
No pre-existing, non-E9 production feature is known to depend on an
`i18n.js`/`sw.js` change made after 2026-07-10 16:43 — the representative
regression smoke in Section 18/29.4 of RELEASE-FIX-A's task book (Legacy
Adventure, Admin, Shadow Dashboard, Premium Upsell, zh-TW⇄English) exists
to confirm this by direct observation rather than by this audit's
inference alone.
