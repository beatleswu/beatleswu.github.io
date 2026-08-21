# Go Odyssey Wave 2 Items / Cosmetics / Collections Production Batches

## Audit identity

- Audit base: `ac182ed173620a11e66bebeb6003c121b9ceee95` (`origin/master`)
- Branch: `codex/rpg-wave2-items-cosmetics-collections-reconcile`
- Current audit candidates: 25 non-equipment Item keys (24 canonical registry records + 1 rejected legacy candidate), 64 wardrobe cosmetics, 10 world presentation skins, and 15 functional equipment records kept outside this scope.
- No runtime, drop-rate, purchase, payment, combat, DB, or Production change is authorized.

## Readiness snapshot

| Domain | READY | NEEDS_ART | NEEDS_RUNTIME | NEEDS_AUTHORITY/PRODUCT_DECISION |
| --- | ---: | ---: | ---: | ---: |
| Items (25 audit candidates) | 24 | 0 | 0 | 1 legacy cleanup |
| Generic cosmetics (74) | 44 | 0 | 0 | 30 |
| Collections (7 families) | 6 active/projection | — | later focused batch | Owner gate |

## ITEM_BATCH_1 — Freeze current canonical Item foundation

Scope: the 24 records in `go_odyssey_wave2_item_inventory.json` whose status is `READY`.

- Freeze the controlled taxonomy: 2 Materials and 22 Consumables (13 direct + 9 immediate-grant bundle products).
- Preserve `shop_inventory.item_key` / `pet_inventory.item_key` authority.
- Preserve existing art/runtime projection and `discovery_semantics=NOT_TRACKED`.
- No new Zone/Boss drop ID or ownership table is introduced.

## ITEM_BATCH_2 — Close rejected legacy key and define Zone/Boss identity

Scope: `appearance_fragment` plus future records; no active future IDs are invented.

- Keep `appearance_fragment` outside `SHOP_ITEMS`, inventory, journal, and reward allowlists; it is `LEGACY_CLEANUP`.
- For future records require `ITEM_ID`, `DISPLAY_NAME`, `ZONE_ID`, `BOSS_ID`, `MONSTER_FAMILY`, `SOURCE_TYPE`, `QUEST_ROLE`, `COLLECTION_ROLE`, `SHOP_ALLOWED`, `COMBAT_POWER`, `ASSET_KEY`.
- Require `COMBAT_POWER=NONE`, `SHOP_ALLOWED=NO` by default, and server settlement ownership.
- Zone 5 must use explicit `zone_05` plus canonical source family/tag, set palette, and asset key.
- Owner gate before any item art, drop rate, quest turn-in, or collection writer.

## COSMETIC_BATCH_1 — Freeze pure presentation complement

Scope: 44 appearance definitions without `APPEARANCE_EFFECTS`.

- Freeze IDs, slots, assets, unlock sources, and renderer mapping.
- Keep `player_wardrobe.item_id` ownership and `player_appearance.<slot>_id` equipped state.
- Keep character bodies separate from wardrobe and keep functional equipment in `player_inventory`.
- No weapon cosmetic authority is created.

## COSMETIC_BATCH_2 — Resolve effect-bearing and world-skin boundary

Scope: 20 effect-bearing appearance IDs plus 10 stone/board skins.

- Decide whether XP/drop effects are removed, separately governed, or reclassified; no new effect model is authorized here.
- Decide whether predicate-selected stone/board skins need durable ownership; do not infer ownership from selected state.
- Existing three-product cosmetic commerce remains unchanged; no P2W offer is approved.
- Revenue/Product Owner gate required before any paid expansion.

## COLLECTION_RUNTIME_BATCH_1 — Projection-only closure

Later focused implementation, not performed here:

- Keep Item Journal GET read-only and `NOT_TRACKED`.
- Link Item, Equipment, Cosmetic, Character, Companion, Badge, and future World families to their existing authorities.
- No discovery table, lazy GET write, generic ownership table, or candidate character registration.
- Add focused authority/non-mutation tests before merge eligibility.

## Wave 2 closeout

### MUST_HAVE_FOR_WAVE2_CLOSEOUT (8)

1. These four planning artifacts are reviewed and accepted.
2. The 24 canonical Item IDs/taxonomy are frozen; `appearance_fragment` remains excluded.
3. The 64 wardrobe IDs and 10 world-skin IDs have authority mappings.
4. `FUNCTIONAL_EQUIPMENT_TAXONOMY_CONFLICTS=0` remains true for generic registries; Hero `combat_*` stays quarantined.
5. Direct cosmetic attack/defense power remains zero.
6. The 20 existing appearance gameplay effects receive explicit Owner disposition; no unapproved premium P2W product is enabled.
7. Collection semantics stay projection-only with no durable discovery writes.
8. Zone/Boss identity contract is accepted before future material art/drop work.

### CAN_DEFER_TO_WAVE3 (5)

1. Actual Zone/Quest/Lore item IDs and server settlement.
2. Durable discovery history, if later required.
3. NPC, Boss, and Zone collection UI/runtime.
4. Full cross-collection UI.
5. Legacy Hero `combat_*` stat-gear authority reconciliation.

### CAN_DEFER_TO_WAVE4_MONETIZATION (4)

1. New premium cosmetic categories.
2. Paid cosmetic bundles and collection-completion offers.
3. Monetized world/board/companion expansions.
4. Any premium effect design; only cosmetic-only offers could proceed.

## Explicit invariants

- `FUNCTIONAL_EQUIPMENT_TAXONOMY_CONFLICTS=0` for canonical generic Item/Cosmetic IDs and ownership stores; `player_appearance.combat_*` is quarantined legacy/stat gear.
- `COSMETICS_GRANT_COMBAT_POWER=NO` for direct attack/defense. Existing 20 XP/drop effects are an Owner decision, not a new approved cosmetic power model.
- `PAY_TO_WIN_PRODUCT_COUNT=0`.
- `DB_MIGRATION=NO`, `MERGE=NO`, `DEPLOY=NO`, `PRODUCTION_MUTATION=NO`.
