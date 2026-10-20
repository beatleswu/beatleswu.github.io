# GO ODYSSEY G MASTER — G010 M3 Shop/Backpack Player-Operation Closeout
2026-10-20 | scope: isolated Product candidate | verdict: M3_LOCAL_ENGINEERING_PASS

## Definition fulfilled (test-only activated UI; production remains G009 Coming Soon)
Real Chrome player click: the canonical server-origin 9-item equipment catalog -> wooden_sword offer shop.static.wooden_sword -> one UI /api/shop/buy -> -300 Coins from 1000 to 700 -> exactly one durable C019 operation, debit and player_inventory acquisition -> in-app Go to Backpack link -> one UI /api/player/inventory/equip -> equipped=true -> new independently created Flask session still owns/equips and new UI Shop marks already owned.
Double-click UI does not duplicate the POST. No second debit or second ownership row; server computes the price and ownership, browser cannot supply currency authority.
Second independent, synthetic already-owned consumable: xp_potion quantity 1 from a fixture grant (NOT a sale, retired legacy consumables cannot be purchased); real Backpack Use button -> exactly one /api/shop/use -> D5C item_use_operations SUCCESS -> inventory qty 0 -> one active_effects xp_potion factor 1.5; XP total is NOT minted by activating a booster. Fresh session no longer shows used potion. This is separate from purchasing/equipping wooden_sword.

## Isolation & release boundary
- Shop release source retains `const G009_SHOP_BROWSE_PREVIEW_ONLY = true;` and Backpack source retains `const G009_BACKPACK_READ_ONLY = true;`. No production purchase, equipment or legacy-item-sale exposure.
- The test WSGI serves ONLY on 127.0.0.1, for GET /shop and GET /inventory, with an in-memory HTML copy that flips the two G009 constants and E10 Backpack view-mode and replaces Backpack body G009 visual marker. ORIGINAL source files on disk stay release locked. Every /api request goes through the actual unmodified Flask WSGI app, with purchase/loadout flags temporarily enabled in synthetic isolated test process only.
- `shop.html` candidate source gained a bounded C053 catalog readiness expansion: retain 3-validated-offer starter policy; accept >3 only if canonical server `purchase_enabled=true`, all raw offers satisfy C043 strict offer validation, no duplicated offer IDs and a real integer nonnegative server coin balance. Real PG returned 9 approved equipment offers; before this edit all 9 were incorrectly hidden. This change is not a request to release the Shop.
- No `inventory.html` Product source change remains. Its G009 CSS `body[data-g009-surface=backpack] #functional-detail-action {display:none!important}` is preserved; test HTML only removes the visual marker in loopback activation variant.
- G009 preview remains unchanged on normal /shop and /inventory. C053 preview/static regression is green.
- D5C item_use_operations candidate migration is applied explicitly only inside fresh disposable PG fixture, never app startup or Production/Oracle.

## New source and evidence
tests/test_20261020_g010_m3_shop_player_native_pg.py
tests/e2e/run_20261020_g010_m3_shop_purchase_equip_real_browser.mjs
tests/e2e/test_20261020_g010_m3_expanded_offer_admission.cjs
tests/_run_g010_m3_disposable_pg_item_use.py
shop.html candidate C053 readiness function updated only; no automatic deployment.

## Green suites / confirmed distinct tests
A. `SHOP_E_RUN_INTEGRATION=1 python -B -m pytest -q tests/test_20261020_g010_m3_shop_player_native_pg.py tests/test_20261020_shop_native_pg_relogin.py tests/test_shop_e_16_sku_end_to_end_acceptance.py tests/test_c047_equipment_commerce_live_route.py --tb=short --show-capture=no --disable-warnings --maxfail=1`
    80 PASSED, 0 FAILED. Includes 2/2 actual desktop and emulated touch Chrome player purchase/equip/consumable-use/relogin, 16-SKU native PG correctness, preexisting read-only baseline, and commerce route contracts.
B. `python -B -m pytest -q tests/test_c043_equipment_commerce_service.py tests/test_c044_equipment_shop_refresh_contract.py tests/test_c045_equipment_shop_starter_catalog.py tests/test_c046_authoritative_equipment_offers.py tests/test_c048_shop_default_purchase_authority.py tests/test_c053_option_b_shop_ui_containment.py tests/test_e030_r1_shop_equipment_runtime_integration.py tests/test_e030_shop_coin_purchase_and_equipment_runtime_integration.py tests/test_e10_backpack_rpg_presentation.py tests/test_e10_backpack_context_handoff_link_closure.py tests/test_20261019_shop_nav_ui.py tests/test_g009_12_surface_visual_authority_consume.py tests/test_g009_eqf_flag_off_effect_closure.py --tb=short --show-capture=no --disable-warnings --maxfail=1`
    174 PASSED, 0 FAILED, no skips. G009 public preview and C053 original static contract both remain green.
C. `python -B -m pytest -q tests/test_d5c_item_use_operation_lineage.py -k 'not cosmetic_purchase_emits_scoped_acquisition_evidence_without_owning_from_event' --tb=short --show-capture=no --disable-warnings --maxfail=1`
    9 PASSED, 2 SKIPPED because no disposable URL was provided in this run, 1 DESELECTED legacy cosmetic test.
D. `python -B tests/_run_g010_m3_disposable_pg_item_use.py` creates and destroys its own loopback native PostgreSQL; executes two D5C PG concurrency tests: 2 PASSED, 10 DESELECTED; `G010_M3_D5C_DISPOSABLE_PG_DESTROYED=TRUE`.
E. `node --test tests/e2e/test_20261020_g010_m3_expanded_offer_admission.cjs`: 4 PASSED, 0 FAILED. C053 3-starter/9-expanded/malformed/duplicates/default preview checks.
Total DISTINCT M3 relevant accepted: **269 passed** = 80+174+9+2+4. Excluded/deselected/skipped are not counted.

## Known pre-existing legacy red; DO NOT misreport all tests green
Unfiltered tests/test_d5c_item_use_operation_lineage.py has test_cosmetic_purchase_emits_scoped_acquisition_evidence_without_owning_from_event that expects `POST /api/cosmetic-commerce/purchase` for retired `cosmetic.outfit.robe_plain` to return HTTP 200; in current G009 protected Product it returns 409. 9 earlier tests passed before that legacy assertion stopped the run. M3 did not edit that API or the test. Do NOT enable retired Outfit Coin purchase to make old test pass. It remains an explicit compatibility test maintenance item under a separate approved cosmetic authority decision.

## Stages after this one
G010 M1=local candidate PASS; M2=local candidate PASS; M3=local candidate PASS for governed synthetic UI, not formal production commerce release; M4=quests/ranking presentation; M5=complete Player UAT incl actual iPad/official signed Build/Publish gate.
V4 Guest/Supervisor real autonomous Goal Loop still NO_GO. Oracle DB production writes, GH master merge/push, godokoro.com deploy and 13 historical Zone1 second-stars still OFF/GATED.
Never stage untracked secret_key.txt or use git add .; HEAD remains efd4524 candidate/go-product-integrated-20261019 unless separately approved.
