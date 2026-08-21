# Go Odyssey Wave 2 Items / Cosmetics / Collections Canonical Freeze

## Audit identity

- ORIGIN_MASTER=`ac182ed173620a11e66bebeb6003c121b9ceee95`
- BASE_HEAD=`efc0510b9160dae33a50a94754f1e1d78372f651`
- Branch: `codex/rpg-wave2-content-canonical-freeze-001`
- Worktree: `D:\\go-website-rpg-wave2-content-canonical-freeze-001`
- Mode: narrow canonicalization; manifests, quarantine contract, and deterministic tests only.
- No Collection runtime, economy, payment, drop, XP, combat, DB, Production, merge, or deploy change.

## Frozen Wave 2 counts

| Domain | Count | Frozen status | Authority |
| --- | ---: | --- | --- |
| Canonical non-equipment Items | 24 | canonical | `shop_inventory.item_key` / `pet_inventory.item_key` |
| Item asset closure | 24 / 24 | complete | current registry asset paths |
| Wardrobe appearance records | 64 | 44 pure + 20 effect quarantine | `APPEARANCE_DEFS` + `player_wardrobe` |
| Pure-presentation appearance records | 44 | canonical | `player_wardrobe` ownership; presentation slot state |
| Effect-bearing appearance records | 20 | quarantined existing effects | existing `APPEARANCE_EFFECTS` path; no commerce approval |
| Stone + board skins | 10 | pure presentation | server unlock predicate + selected `player_appearance` state |
| Functional equipment | 15 | separate domain | server `EQUIPMENT_DEFS` + `player_inventory` |
| Current cosmetic commerce products | 3 | existing runtime only | existing server catalog; no new pricing |
| Monetization eligible in principle | 54 | pure presentation only | classification, not a launch catalog |

The rejected legacy reward key is not a canonical Item, Cosmetic, production-batch record, reward contract record, or monetization catalog entry. Existing references are recorded in `go_odyssey_wave2_legacy_reference_audit.json` and remain fail-closed.

## Item contract

The canonical Item registry contains exactly 22 `CONSUMABLE` records and 2 `MATERIAL` records. All 24 have closed current assets and stable IDs. Existing direct-use, immediate-grant bundle, shop inventory, and pet inventory semantics are preserved; no acquisition behavior is invented.

Rules:

- Generic Item authority remains `shop_inventory.item_key` and `pet_inventory.item_key`.
- Bundle products grant existing components and do not create persistent bundle ownership.
- `GET /api/item-journal` remains a read-only projection with `discovery_semantics=NOT_TRACKED`.
- Non-equipment `COMBAT_POWER=NONE`; future Zone/Boss item identity remains a contract-only concern.
- Functional equipment is never represented as a generic Item row.

## Functional equipment boundary

`FUNCTIONAL_EQUIPMENT_TAXONOMY_CONFLICTS=0`. The 15 functional definitions remain solely in server `EQUIPMENT_DEFS` plus `player_inventory`. The legacy Hero `combat_*` keyspace is not merged with Items or Cosmetics by display name, slot, or art. Cosmetic presentation has no combat authority.

## Cosmetic contract

The 64 wardrobe appearance records are split into:

- 44 `PURE_PRESENTATION`: functional power `NO`, selection `presentation-only`, eligible for monetization in principle only as a future Owner decision.
- 20 `EFFECT_BEARING_APPEARANCE_QUARANTINED`: existing XP/drop effects are preserved, but the records are not monetization-eligible. The explicit quarantine manifest records presentation asset, current legacy effect, current effect authority, and required separation.
- No cosmetic record grants direct attack or defense authority.
- Current commerce is reported separately from principle eligibility. No launch pricing is hardcoded, and the existing effect-bearing commerce record is not approved by this freeze.

The 10 stone/board skins use stable `stone.<key>` and `board.<key>` IDs, category `PURE_PRESENTATION`, functional effect count zero, server-authoritative ownership contract, and presentation-only selection. This task does not add automatic grants or a durable ownership table.

## Collection contract

Seven collection families remain projections or contracts only:

1. `ITEM_JOURNAL` — active read-only projection, `NOT_TRACKED`.
2. `EQUIPMENT_COLLECTION` — existing inventory projection, never generic Item rows.
3. `COSMETIC_COLLECTION` — existing wardrobe projection.
4. `CHARACTER_COLLECTION` — existing appearance selection/unlock projection.
5. `COMPANION_COLLECTION` — existing pet domain.
6. `ACHIEVEMENT_BADGE_COLLECTION` — existing badge domain.
7. `WORLD_DISCOVERY` — future Zone/Boss/NPC contract, `WAVE3_DEFERRED`.

For this freeze:

- COLLECTION_RUNTIME_IMPLEMENTATION=NO
- COLLECTION_DISCOVERY_DB=NO
- COLLECTION_WRITER=NO
- COLLECTION_AUTHORITY=WAVE3_DEFERRED
- These flags cover new generic Wave 2 collection runtime only; existing domain-local companion/badge collections remain unchanged.
- Catalog visibility is not durable discovery.
- A GET must not create discovery history or ownership.
- No generic collection authority is introduced.

## Zone / Boss identity contract

A future Zone 5 Item must carry explicit `ZONE_ID=zone_05`, source family/tag, Zone 5 palette/set key, and asset key. The production identity fields remain `ITEM_ID`, `DISPLAY_NAME`, `ZONE_ID`, `BOSS_ID`, `MONSTER_FAMILY`, `SOURCE_TYPE`, `QUEST_ROLE`, `COLLECTION_ROLE`, `SHOP_ALLOWED`, `COMBAT_POWER`, and `ASSET_KEY`. No Zone/Boss drop or collection behavior is activated here.

## Freeze outputs

- `go_odyssey_wave2_item_inventory.json`: exactly 24 canonical Item records.
- `go_odyssey_wave2_cosmetic_inventory.json`: 74 generic records with explicit pure/quarantine/skin classifications.
- `go_odyssey_wave2_effect_bearing_appearance_quarantine.json`: exactly 20 fail-closed effect records.
- `go_odyssey_wave2_legacy_reference_audit.json`: existing legacy references and forbidden new surfaces.
- `go_odyssey_wave2_collection_contract.json`: taxonomy/projection only; runtime deferred.
- `test_rpg_wave2_content_canonical_freeze.py`: deterministic invariant coverage.

## Non-actions

DB_MIGRATION=NO; XP_CHANGED=NO; DROP_CHANGED=NO; SHOP_BEHAVIOR_CHANGED=NO; PAYMENT_CHANGED=NO; COMBAT_CHANGED=NO; COLLECTION_RUNTIME_CHANGED=NO; MERGE=NO; DEPLOY=NO; PRODUCTION_MUTATION=NO.
