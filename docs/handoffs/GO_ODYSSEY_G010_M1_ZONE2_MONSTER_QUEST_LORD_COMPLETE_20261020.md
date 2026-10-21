# Go Odyssey | G010 M1 completed engineering handoff
Date: 2026-10-20 | owner: G MASTER | outcome: ISOLATED_PRODUCT_CANDIDATE_PASS

## Scope
G010 M1: Zone2 continuous gameplay, exact server-owned Monster identity and actual kill, Quest progress/reward, 20-question Lord victory, once-only first clear, Zone3 unlock, replay/new-session persistence, original Chrome WGo gameplay.
This is the engineering acceptance in synthetic, disposable native PostgreSQL; it is NOT formal Oracle deployment, GitHub master merge, physical iPad UAT, or final G010 M1-M5 DoD.

## Actual engineering changes (candidate branch only)
1. app.py: fixed provider-bound Zone1/2 Monster defeat tail. Previous state: Map Battle committed server-judged HP=0 on 12th correct answer but /api/adventure/map-battles/v1/answers responded 503 adventure_progression_pending because optional Monster settlement entered legacy Battlefield identity/profile route, which is not the correct Zone1/2 authority. New path restores the exact persisted server M-ID through existing Map Battle provider boundary.
2. app.py: _settle_zone1_2_defeat_without_deferred_rewards records one D5A MONSTER_DEFEATED event for the authentic server HP before >0 and after=0, pinned to Z1/Z2 profile and settlement ID. It rejects unbound/non-Z1/2 authority and replay conflicts. Zero Coin grants, zero functional/appearance drops, no invented taxonomy or policy. The original DEFER_Z1_Z2_REWARD_DROP_POLICY remains respected.
3. app.py: D017 Quest V2 consumes server-owned Monster defeat evidence; a correct answer with no trusted identity cannot create a fake kill. Existing legacy/z3/zone4+ branches unchanged.
4. map_battle_runtime.py: exports the same Zone1/2 immutable source and deferred reward policy through the already admitted provider boundary; app.py has no direct import of the separate Zone1/2 module. Older architecture guard remains PASS.
5. New test: tests/test_20261020_g010_m1_zone2_monster_lord_native_pg.py (3 tests incl desktop & simulated touch browser). New runner: tests/e2e/run_20261020_g010_zone2_lord_20_wgo_browser.mjs.

## E2E positive and negative proof
- Fresh synthetic user clears Zone1: 20 server-reviewed Lord questions, real first clear, Zone2 unlocked.
- Synthetic 26-question Zone2 corpus: server-judged Map Battle HP decrements through correct answers and a canonical zone2 monster reaches HP=0 on the 12th answer; Quest V2 daily:kill_monsters increments; no 503.
- Exactly one D5A MONSTER_DEFEATED for the defeat: persistent M-ID, Z2 zone, deferred reward marker; zero Monster Coin debit/grant and no equipment drops. Replay the same signed Map Battle answer/nonce -> duplicate, no second event.
- 20 eligible correct Zone2 Map Battle answers -> server boss_ready. Bogus boss finish before 20 server reviews is refused.
- Native PG Zone2 Lord 20/20 real server judged trial -> first clear -> single Zone2 first star -> Zone3 unlock; fresh session persists; a new replay of all 20 Lord questions does not reissue first-clear reward, star1 or next-zone unlock.
- Original index.html E9 real Chrome actual WGo clicks for second-zone Lord: desktop_mouse and chrome_tablet_touch both pass the canonical pass score at least 16/20, complete first-clear and unlock Zone3; touch uses visible drawer CTA, not force clicking hidden redundant map CTA. Actual physical iPad NOT tested.
- Companion G010 M1a native PG: three Zone2 server-authoritative Map Battle correct results -> daily:streak_correct Quest V2 -> +15 Coins and +1 go_spirit_candy once -> re-login Shop and pet/Backpack source APIs reflect reward. Quest V2 gate default OFF, test-only ON.
- Previous Zone2 real training E9 WGo Chrome mouse/tablet and Zone star 60/100 contracts continue passing.

## Exact end-stage verdict
RUN A: python -B -m pytest -q tests/test_adventure_zone1_2_monster_runtime_provider.py tests/test_monster_settlement.py tests/test_adventure_boss_finish_server_authoritative.py --tb=short --show-capture=no --disable-warnings --maxfail=1
RESULT A: 84 passed in 54.29s.
RUN B: python -B -m pytest -q tests/test_20261020_g010_m1_zone2_monster_lord_native_pg.py tests/test_20261020_g010_zone2_quest_claim_native_pg.py tests/test_20261020_zone2_first_play_native_pg.py tests/test_d017_quest_runtime.py tests/test_20261019_three_stars_real_map_pg.py tests/test_e10_zone2_final_bilingual_integration.py --tb=short --show-capture=no --disable-warnings --maxfail=1
RESULT B: 32 passed in 141.46s.
TOTAL: 116 passed, 0 failed; none reported skipped. Python compile app.py/map_battle_runtime.py/new test PASS; git diff --check PASS. M1 status: LOCAL_CANDIDATE_PASS.

## Strict release and further milestones
- G010 M1 DONE only for scoped isolated engineering acceptance. G010 M2-M5 remain OPEN: broader economy/reward UX, quests/ranking presentation, full physical Owner iPad UAT, formal Build/Deploy candidate and source admission.
- Zone1/2 reward/drop policies are explicitly deferred: no new Monster reward was authorized in this stage; existing Quest V2 reward still available only when isolated flag enabled.
- Do not claim real production gamers received a fix. No Oracle DB writes, no production stars updated, no GitHub master merge/push, no official godokoro.com deployment.
- First-zone 13 historical second-star correction remains independent formal trusted execution HOLD.
- V4 trusted Linux Guest one-time identity/OAuth and permission remains NO_GO; do not claim autonomous Codex/Claude dispatch from this Product stage.
- Do not stage secret_key.txt or JUnit/unrelated untracked artifacts; do not use git add .
Product root: D:\\go-odyssey-sixroute-20261019\\g | branch candidate/go-product-integrated-20261019 | known HEAD efd4524, working tree dirty.
