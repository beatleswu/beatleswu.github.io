# Go Odyssey | G MASTER P1 hero-growth/adventure cross-system repair | 2026-10-19

**State:** LOCAL PRODUCT CANDIDATE, NOT FORMAL SOURCE/BUILD/DEPLOY.
**Base:** isolated candidate `7978ec1a4f3adb89fa51d660ad953628b476984b`.
The existing monthly prize ancestor `00e9120d`, spirit operations, genuine GLB turntable, and quest fail-closed fixes must remain preserved.

## Proven defect

The A028 Hero Player Presentation response uses `progression.xp` from
`user_stats.xp`, which is **cumulative lifetime XP**. Legacy
`/api/skills/profile.xp_next` represents only the *next current-level*
XP requirement. Hero UI incorrectly divided cumulative XP by that
current-level requirement to fill `#char-xp-bar`, so a player above LV1
could appear 100% filled long before the next level.

Server canonical facts:
- `app.lv_progress(321) == (4, 41, 200)` (example)
- `user_stats.rank_xp` is the within-level numerator; `xp` is the total.
- `/api/xp/status` computes LV, rank_xp and denominator from the total.
- A028 Player Presentation already transports `progression.rank_xp`,
  but the visible Hero A028 consumer previously discarded it.

## Actual implementation

Modified `hero.html`, A028 *read-only presentation* block only:
- Accept and validate canonical non-negative safe-integer total XP,
  canonical within-level `progression.rank_xp`, and LV1–100.
- Reuse legacy `xp_next` only when **numeric** cross-route
  `total_xp`, `level`, and within-level `lv_xp` all match the
  authoritative A028 projection; no silent mixing of stale snapshots.
- Render **within-level XP / required XP** plus explicitly labeled
  **total XP** and corresponding percentage. At LV100, display cap
  correctly (100%). For missing/stale scale display total without
  inventing a current-level percentage.
- Apply identical display semantics to Hero overview and XP progress
  bar. No new XP or Go-rank calculations, no change to server authority,
  no world-clear/unlock writes and no new privileges.

Changed/added test files:
- `tests/e9_node_tests/run_a028_hero_overview_player_presentation_tests.js`
  expanded with coherent LV4 41/200, stale cross-route, LV100,
  invalid/missing rank_xp and invalid fractional XP.
- `tests/e9_node_tests/run_20261019_hero_real_api_projection.js`
  runs the actual shipped A028 JS on real Flask API payloads handed
  from an isolated native PostgreSQL fixture; no production account.
- `tests/test_20261019_hero_xp_adventure_native_pg.py`
  creates a new disposable native PostgreSQL cluster and uses the
  actual `_grant_quest_xp` writer (Quest/Daily XP, NOT a Boss-clear
  completion), real Flask `/api/player/presentation`,
  `/api/skills/profile`, `/api/xp/status` and
  `/api/adventure/bootstrap`; confirms consistent LV/XP, original
  world unlock/clear state preserved, and a fresh Flask session reads
  the same durable data. This is **not** production Test02 login.

## Executed acceptance evidence

- Cross-system native PostgreSQL tests: **2/2 PASS**, actual backend
  writer -> 4 real GET routes -> shipped Hero JS; confirms 119/120 XP
  (LV1) -> 0/160 XP (LV2), world state unaltered and fresh session
  consistent. The game XP writer was used; no fake HTTP response.
- Broader Hero/XP/Adventure/Player-Presentation tests: **221/221 PASS**,
  Python `pytest` with real services and native PG.
- Legacy A028 Hero Node suite: **14 reported PASS** (expanded
  assertions, historic suite count unchanged).
- Disposable Docker PostgreSQL 16.14 real
  `test_d011_adventure_first_clear_postgres.py`: **3/3 PASS**
  proving first-clear CAS, replay and rollback. Disposable container
  was removed, not attached to production.
- Existing real WebGL Chrome GLB 360 browser test re-ran with exit
  code **0**. Inline classic scripts parsed after excluding the
  browser-only `importmap` JSON script.
- `git diff --check`: zero failures.

Evidence files:
`docs/handoffs/GO_ODYSSEY_HERO_XP_ADVENTURE_NATIVE_PG_20261019.xml`
`docs/handoffs/GO_ODYSSEY_HERO_XP_ADVENTURE_REGRESSION_20261019.xml`
`docs/handoffs/GO_ODYSSEY_HERO_XP_ADVENTURE_FINAL_REGRESSION_R2_20261019.xml`
(the final R2 suite was rerun after tightening integer input validation:
**221 passed, exit 0**; other suite results reported separately).

## Remaining Owner gates and product priorities

- Actual **new, never pre-scripted** iPad Safari Test02 UAT,
  360 model drag and spirit pat/feed, real XP earned from an Adventure
  **question answer** through final game presentation, boss clear and
  progression, Quest V2 production gating, final leaderboard UI,
  monthly prize actual logout/login: NOT validated by this isolated test.
- Trusted canonical source adoption, formal Build, relevant Docker
  release test matrix, rollback rehearsal and explicit Owner
  GO_MERGE/GO_DEPLOY: all pending.
- Oracle production site and GitHub master must remain unchanged.
- V4 R15 autonomous development Goal Loop remains **NO_GO**.

A–F:
A: Spirit operations / GLB turntable candidates preserved, Test02 pending.
B: canonical player cumulative/level XP Hero display **fixed and accepted locally**;
   battle-end player XP E2E and iPad remain pending.
C: Quest fail-closed client and XP settlement tests preserved.
D: Adventure persisted clear/unlock invariant and Docker CAS PASS;
   actual iPad map journey pending.
E: ranking UI and monthly reward candidate retained.
F: shop/inventory candidate retained, formal release pending.

Never stage untracked secret material (including the existing local
`secret_key.txt`); candidate commit should name only the listed files.
