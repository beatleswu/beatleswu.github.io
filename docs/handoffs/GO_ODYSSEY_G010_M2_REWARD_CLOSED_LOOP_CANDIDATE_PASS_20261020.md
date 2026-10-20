# GO ODYSSEY | G010 M2 Reward Closed Loop — G MASTER Handoff
Date: 2026-10-20 | scope: isolated Product candidate only | Engineering decision: M2_LOCAL_CANDIDATE_PASS

## Authoritative journey and release policy
M2 closure covers server judged Map Battle XP -> Zone2 Monster defeat with governed NO-REWARD/NO-DROP policy -> daily:streak_correct Quest V2 +20 XP +15 Coins +1 go_spirit_candy -> two replay identities no duplicate rewards -> Zone2 Lord 20-Q first clear and first-star Zone3 unlock -> fresh-session Hero XP, Shop Coins, Backpack candy, Zone map readback in unmodified shipped pages.
Quest V2 is OFF by default. Test-local env only, after additive migrations in disposable PostgreSQL. Real Shop stays browse-preview only. Zone1/2 Monster reward/drop policy stays DEFERRED. No new economy amount or feature gate was invented. All test players, SGF and database rows are synthetic.
Zone3 has one valid synthetic playable SGF in this M2 test corpus. Why: existing app deliberately returns status=locked and can_enter=false for a server-unlocked zone with ZERO eligible questions. This is fail-closed policy, not a Product bug. Original M1 corpus deliberately had no Zone3 questions; extending the fixture tests truthful map readback without weakening authority.

## New code (tests only; Product source remains unchanged by M2)
- tests/test_20261020_g010_m2_reward_closed_loop_native_pg.py
- tests/e2e/run_20261020_g010_m2_reward_readback_browser.mjs
- tests/_run_g010_m2_disposable_pg_claim_concurrency.py
Existing M1 code (app.py and map_battle_runtime.py) remains modified in the candidate, not committed or deployed. Base HEAD efd4524.

## Accepted verification
A. Full real route/native PostgreSQL/synthetic player + unmocked Chrome desktop & Chrome tablet-emulation:
python -B -m pytest -q tests/test_20261020_g010_m2_reward_closed_loop_native_pg.py tests/test_20261020_g010_zone2_quest_claim_native_pg.py tests/test_20261019_hero_xp_adventure_native_pg.py tests/test_20261019_three_stars_real_map_pg.py --tb=short --show-capture=no --disable-warnings --maxfail=1
RESULT: 6 PASSED, 0 failed. M2 new direct E2E 2/2 PASS (desktop and Chrome emulated touch).

B. Quest claim, XP policy, idempotence, M1 Monster settlement, first-clear, shop/backpack/map regression:
python -B -m pytest -q tests/test_d015_quest_claim_reward.py tests/test_d015_quest_claim_reward_postgres.py tests/test_d017_quest_runtime.py tests/test_d017_quest_runtime_postgres.py tests/test_adventure_first_clear_reward.py tests/test_monster_settlement.py tests/test_20261019_map_unlock_ui.py tests/test_e10_backpack_rpg_presentation.py tests/test_e10_backpack_context_handoff_link_closure.py tests/test_e10_adventure_hero_shop_backpack_information_architecture.py tests/test_20261020_shop_native_pg_relogin.py --tb=short --show-capture=no --disable-warnings --maxfail=1
RESULT: 75 PASSED, 8 explicitly SKIPPED (native PG test URL and disposable gate not initially supplied), 0 failed. These 8 were not counted as passes.

C. Separate real concurrency on throwaway loopback native PG, two explicit test-only databases, destroyed on exit:
python -B tests/_run_g010_m2_disposable_pg_claim_concurrency.py
RESULT: D015 4 PASS and D017 version-agnostic tests 3 PASS; disposable cluster DESTROYED. Total 7 additional confirmed passes.
IMPORTANT EXCEPTION: D017 test_postgres_16_14_preflight_and_candidate_migrations_are_rerunnable requires EXACT PostgreSQL 16.14; beatles only has PostgreSQL 17.10. This one exact-version preflight was NOT verified, NOT waived, NOT counted as PASS. One deselected in D017 native group. Do not claim PG16.14 certification.

TOTAL confirmed distinct passes across A+B+C: 88 PASSED, 0 failed; 1 PG16.14-only preflight still requires correct PostgreSQL version. M2 acceptance is scoped to current native PG17.10 candidate runtime, not generic cross-version guarantee.

## Direct anti-fraud and persistence details
- Fake reward request that includes client coins/xp is 400 client_authority_field_rejected.
- Reward claim returns +20 XP, +15 Coins, +1 candy, exactly one quest_claims_v2 row; same claim op ID and second op ID replays do NOT mint additional XP/Coins/candy.
- API total XP, level and rank XP are identical across /api/xp/status, /api/skills/profile, /api/player/presentation on a fresh Flask session.
- Two real Chrome UI modes read the same authoritative XP in Hero, Coins in Hero/Shop/Backpack and one real candy card in Backpack with managed/Spirit link (no illegal shop-use button), Zone2 cleared star1 and Zone3 unlocked.
- Browser tests record no client POST/PUT/DELETE and no API errors while reading; DB rows and coins/candy remained unchanged.
- Monster kill has exactly one durable outbox event and 0 unauthorized coins/drops. Star1 entitlement and successor zone unlock each persisted exactly once.
- First-clear wardrobe back_pack is visible in freshly read /api/player/wardrobe.

## Closed vs outstanding
G010 M2: LOCAL_CANDIDATE_PASS; G010 M1 also LOCAL_CANDIDATE_PASS. G010 M3 shop/backpack PLAYER TRANSACTION UI remains OPEN and deliberately preview-locked; G010 M4 quest/ranking presentation and G010 M5 physical iPad Owner UAT / build governance / release remain OPEN.
PG16.14-only D017 preflight remains NOT VERIFIED; do not invent access or change test condition. V4 trusted Guest Goal Loop still NO_GO. Formal 13-player star correction still gate blocked.
No Oracle production writes, master merge, push, deployed website, private OAuth or token handling. Do not stage untracked secret_key.txt, JUnit XML, or use git add .
Product working root: D:\\go-odyssey-sixroute-20261019\\g | branch candidate/go-product-integrated-20261019 | HEAD efd4524.
