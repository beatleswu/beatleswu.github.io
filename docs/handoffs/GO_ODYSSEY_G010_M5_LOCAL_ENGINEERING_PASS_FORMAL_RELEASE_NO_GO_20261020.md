# Go Odyssey | G010 M5 Final Engineering Candidate & External GO/NO_GO Handoff
Date: 2026-10-20 | G MASTER | Owner goal: finish M5 | status: LOCAL_ENGINEERING_CANDIDATE_PASS / OWNER_RELEASE_GATE_NO_GO

## Definitive scope & truth
G010 M1, M2, M3 and M4 locally accepted before M5. M5 repaired local Docker packaging for new M4 Quest UI, tested the integrated codebase, fixed a Chrome tablet Lord question-advance race in the E2E runner, and proved an entire M1->M4 gameplay/claim/purchase/equip/Lord flow FOR ONE SINGLE DISPOSABLE PLAYER. Independent signed source adoption, Owner physical iPad UAT and formal Product release authorization HAVE NOT OCCURRED. Do not mark the overall M5 as RELEASE_READY/CLOSED until these external gates are actually satisfied.

## Code changes in the isolated uncommitted Product candidate
- Dockerfile: explicit COPY both newly added g010_m4_quest_leaderboard.js and .css into app root.
- deploy/build-manifest.json: these two assets added to required tracked build inputs, plus /app/community.html, /app/g010_m4_quest_leaderboard.js and /app/g010_m4_quest_leaderboard.css added to post_build_verification_files.
- tests/e2e/run_20261020_g010_zone2_lord_20_wgo_browser.mjs: true Chrome touch mode waits for a UNIQUE next question ID, current _bossQueue index and two browser animation frames before each WGo click; fixes intermittent early reuse of preceding board answer. Does not bypass grading, skip reviews, alter question IDs or force boss passes.
- tests/test_20261020_g010_m5_unified_one_player_pg.py: user UID 716020 (test-only); entire product flow with native PostgreSQL, existing API boundaries and real original browser UI actions. Allows legitimate first-clear equipment in addition to purchased wood sword; asserts exactly one shop transaction and purchase ownership.
- tests/_run_g010_m5_sanitized_docker_candidate.py: clean Git archive from frozen HEAD with explicit nine-file reviewed local overlay, refuses common secret files and builds a LOCAL-ONLY OCI image without push or deployment. Hashes all overlaid sources, verifies three UI assets inside a no-network read-only Docker run.

## Direct Stage M5 acceptance results
A. Integrated ALL M1-M4 runner:
`SHOP_E_RUN_INTEGRATION=1 python -B -m pytest -q tests/test_20261020_g010_m1_zone2_monster_lord_native_pg.py tests/test_20261020_g010_m2_reward_closed_loop_native_pg.py tests/test_20261020_g010_m3_shop_player_native_pg.py tests/test_20261020_g010_m4_quest_rank_native_pg.py tests/test_20261020_g010_zone2_quest_claim_native_pg.py tests/test_20261020_shop_native_pg_relogin.py tests/test_shop_e_16_sku_end_to_end_acceptance.py tests/test_20261019_three_stars_real_map_pg.py --tb=short --show-capture=no --disable-warnings --maxfail=1`
RESULT: 65 PASSED, zero FAIL and zero SKIP (264.31s). Desktop Chrome and tablet emulation included. A FIRST run before test-side WGo transition guard caught a flaky Chrome emulated tablet 18/20 stall; final full replay after guard passed. Earlier failure was real and MUST NOT be erased from engineering history.

B. Authorized server invariants and safe DEFAULT OFF:
`python -B -m pytest -q tests/test_adventure_zone1_2_monster_runtime_provider.py tests/test_monster_settlement.py tests/test_adventure_boss_finish_server_authoritative.py tests/test_c048_shop_default_purchase_authority.py tests/test_c053_option_b_shop_ui_containment.py tests/test_community_leaderboard_rewards.py tests/test_community_leaderboard_rewards_scheduler.py tests/test_monthly_leaderboard_launch.py tests/test_d015_quest_claim_reward.py tests/test_d017_quest_runtime.py tests/test_g009_12_surface_visual_authority_consume.py tests/test_g009_eqf_flag_off_effect_closure.py --tb=short --show-capture=no --disable-warnings --maxfail=1`
RESULT: 192 PASSED, zero FAIL and zero SKIP (67.34s).

C. ONE actual test PLAYER crosses all stages (NOT disjoint fixtures):
`python -B -m pytest -q tests/test_20261020_g010_m5_unified_one_player_pg.py --tb=short --show-capture=no --disable-warnings --maxfail=1`
RESULT: 1 PASSED, zero FAIL and zero SKIP (32.49s). One UID: Zone1 Lord 20 server-judged reviews -> Zone2 20 actual Map Battle answers (exactly one governed Monster kill, no unapproved drops) -> Chrome Community claim +20 XP/+15 Coins/+1 Spirit candy -> XP leaderboards update while weekly/monthly unchanged -> local test-only Shop gate, one real Chrome purchase wooden_sword -300 from 1015 to 715 -> real Backpack equip -> synthetic previously-earned potion use one D5C use operation (not purchased in retired shop) -> Zone2 Lord 20 server-judged reviews -> Star1 and Zone3 unlock exactly once -> new session confirms inventory, currency, Quest claim and leaderboard. Correctly preserves additional legitimate Lord reward equipment bamboo_shadow_blade and jade_river_bead, not duplicate shop purchases.

TOTAL DISTINCT VERIFIED G010 M5 tests = 258 PASSED, 0 FAIL = 65+192+1. This count excludes earlier stages or replays of same test. A legacy retired-cosmetic compatibility test in broader codebase, and PG16.14-specific D017 environment preflight, remain unaddressed independent verification items (do not call entire Product regression all green).

D. Docker offline candidate Build:
`python -B tests/_run_g010_m5_sanitized_docker_candidate.py`
RESULT: SUCCESS, two local runs; final exact-current-manifest run exit 0; isolated image tag go-odyssey:g010-m5-local-candidate-20261020; final image ID sha256:ad3baf13342d5f9e23acaf2770cc6b8e0f937222b7678c24a166afb64877644e. /app/community.html and both M4 JS/CSS present inside image; no local secret_key.txt or .env copied; temporary clean context deleted. Evidence docs/handoffs/G010_M5_LOCAL_CANDIDATE_BUILD_EVIDENCE_20261020.json includes explicit reviewed nine-file SHA256 and Docker log tail.
IMPORTANT: Git baseline efd4524c3a3b5669b693ee0be50acf586c73ad90 plus uncommitted local overlay. Docker BuildKit may write local provenance metadata, but NO independent trusted source signature / formal production Build attestation was obtained. The image is neither a signed release nor suitable for unreviewed Oracle deploy.

## Actual stage release gates still OPEN (cannot self certify)
1. Owner physical iPad UAT: NO DEVICE was connected/available on authorized Windows beatles. Existing Chrome tablet touch emulation PASS is NOT iPad Safari. Perform actual new-player flow, WGo 20-question Lord, Map Monster, Quest, Backpack, Map stars and Community on the OWNER iPad using authorized candidate/staging URL; record per-screen pass/fail. A010 Owner Real iPad Map UAT also remains pending.
2. Independent source and build admission: adopt and review selected candidate diffs and source hashes via trusted provider. Current Git origin PUSH is DISABLED; master is not merged. Official source signature, external verifying runner, complete original PowerShell build matrix remain separate governance gates. Do not bypass or infer authorization from this report or image label.
3. Policy blockers outside G010 happy-path acceptance: D5C retired cosmetic shop route old test expects HTTP200 but current protected endpoint returns409; cannot safely re-enable legacy path. D017 one exact PostgreSQL 16.14 preflight not certified on available PG17.10; 3 version-agnostic DB tests were separately PASS. 13 historical Zone1 second-stars Oracle correction still admission gated.
4. Deployment remains OWNER DECISION: explicit separate GO for master merge, signed formal Product Build, Oracle upload/restart and rollback. Formal godokoro.com and real player DB were untouched here. V4 Guest OAuth and autonomous Codex/Claude Goal Loop are independently NO_GO and not claimed here.

## Owner-ready proof sequence (never in production without explicit gates)
1. Review final code diff and named review bundle; verify sha256 of nine overlay files against JSON build evidence. Do not stage secret_key.txt.
2. Run M5 native PG 65-case integration, 192-case policy regression, one-identity end-to-end, Docker clean candidate Build and verify image files. All had a final local PASS here.
3. Owner connect REAL iPad to an authorized staging build, complete hardware acceptance; ensure no surprise auto shop/Quest activation in formally gated mode.
4. Obtain independent trusted source+Build attestation, ensure required original release matrix/known red conditions resolved or governance accepted; only then ask Owner separately to authorize commit/merge/release actions.

## State
CODE_READY_LOCAL_CANDIDATE=TRUE. FORMAL_M5_ALL_GATES_COMPLETE=FALSE. PRODUCTION_DEPLOYED=FALSE. TRUE_I_PAD_UAT=FALSE. NO_GITHUB_PUSH, NO_MASTER_MERGE, NO_ORACLE_PRODUCTION_DB_WRITE, NO_SECRET_ACCESS. No untrusted code delegation claimed.
Workspace: D:\\go-odyssey-sixroute-20261019\\g ; branch candidate/go-product-integrated-20261019 ; HEAD efd4524 ; dirty candidate uncommitted and intentionally unchanged master.
