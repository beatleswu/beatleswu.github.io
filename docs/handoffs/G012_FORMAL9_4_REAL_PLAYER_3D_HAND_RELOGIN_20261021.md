# G012 — Formal9 four weapons: genuine synthetic PostgreSQL ownership -> Player Backpack -> Hero WebGL -> fresh session

## Status: PASS (non-production technical acceptance; **NOT** asset release)

Current isolated Git baseline before G012: `8ca21831fe7ea397f92a75ef03a65fa59201a609`.
Preserves original protected 21a2c84a Product candidate. No GitHub master, Oracle deploy or Production player writes.

### Actual tested implementation (no new Product grants, flags or scene renderer)
- Disposable native PostgreSQL cluster, fresh non-admin synthetic A1 player and a separate non-owner synthetic user; no existing QA data overwritten.
- Reuses the canonical server definitions **CANONICAL_EQUIPMENT_DEFS** and `grant_equipment_ownership` solely in disposable PG fixture. Four synthetic grants, no shop purchases or currency spent, no arbitrary browser client grants. Records carry real canonical item IDs.
- Exact Formal9 mapping `schemas/g009_formal9_rights_cleared_replacement_v1.json`: `iron_sword` -> `WEAPON_C43E15596CA6`; `fox_fang` -> `WEAPON_6F06505A7BED`; `riverstone_sabre` -> `WEAPON_EC86CE30E759`; `bamboo_shadow_blade` -> `WEAPON_C84A8635BED2`.
- Default `EQUIPMENT_CANONICAL_LOADOUT_ENABLED` OFF. Original equip attempt 409 `LOADOUT_DISABLED`; other player's attempt 404; untouched shop flag OFF throughout.
- Only disposable pytest process enables server loadout flag and renders **in-memory original Backpack** test variant through already implemented M3 localhost WSGI helper. Shipped HTML remains preview-only/read-only; no production source edited.
- Chrome operates actual Backpack item-detail selection and Equip button four times, issuing exactly four **real** `POST /api/player/inventory/equip` requests. On each switch, native PG holds exactly one equipped weapon, never both; model name is resolved by unchanged exact server inventory projection.
- Navigates original `/hero?tab=equipment`, actually loads A1 character GLB under G008 Three.js renderer, and uses existing G009 shared rig/main-hand host. Per weapon: MAIN_HAND `presentation_id` exactly matches signed canonical replacement and `child_count=1`; the browser independently fetches the actual replacement GLB and calculates SHA-256; output exact bytes per model, real canvas dimensions. **Not mock API or fake 2D.**
- For each weapon, a **different cryptographically signed Flask Session cookie** for same user loads original Hero anew and verifies the same GLB attached and same server inventory item equipped. Separate synthetic player cannot use those ownership row IDs.
- Native PG final state four owned rows, one currently equipped (`bamboo_shadow_blade`), 777 coins unchanged, no currency debits, no Shop purchase. Loadout gate explicitly removed from test environment and confirmed OFF; strict request isolation.
- Test actually executed: `python -m pytest -xq --tb=short --show-capture=no tests/test_g012_formal9_native_pg_real_hero_all4.py` -> **1 PASS / 0 FAIL**, ~40.36 s, four browser switch and four independent relogin cycles, zero unexpected browser pageerrors and HTTP errors.
- Original evidence **outside Product**: `D:\go-odyssey-g010-3d-activation-evidence-20261021\G012_FORMAL9_ALL4_NATIVE_PG_TRUE_HERO_20261021.json`; per-item server IDs, SHA digests, byte lengths, error arrays, no cookies or secrets. New reproducible test scripts: `tests/test_g012_formal9_native_pg_real_hero_all4.py` and `tests/e2e/g012_formal9_true_player_3d_browser.mjs`.
- Existing G009 static grip A1/A3 two real animations and 4 replacements were completed in historical isolated QA; **not reimplemented nor presented as freshly rerun in this stage.**

### Explicit non-release boundary
Owner asset release has **NOT** admitted these four CC0 rights-cleared replacement GLBs. Canonical schema states `RIGHTS_CLEARED_RELEASE_NOT_ADMITTED`, `EQUIP_ENABLED=false`, `PURCHASE_ENABLED=false`, `RELEASE_ENABLED=false`, `PRODUCTION_ASSET_ADMISSION=false`. G009 presentation may render a PG-owned fixture in local QA but must not grant production purchase, drop or equip functionality based on rights alone.

Next milestone: remaining P038 8 mainhand / 4 offhand historical fitting and P022 additional 16 QA models need exact legal release mapping, validated per-hero skeleton attachments and their own synthetic Player/Shop state — cannot be inferred from G012 four-weapon pass. Real iPad Safari Owner UAT and separate GO_MERGE/GO_DEPLOY pending.
