# Go Odyssey Wave 2 Items / Cosmetics / Collections Production Batches

## Audit identity

- ORIGIN_MASTER=`ac182ed173620a11e66bebeb6003c121b9ceee95`
- BASE_HEAD=`efc0510b9160dae33a50a94754f1e1d78372f651`
- Branch: `codex/rpg-wave2-content-canonical-freeze-001`
- 24 canonical non-equipment Items, 64 wardrobe appearances, 10 world presentation skins, and 15 separate functional equipment records are in scope.
- No runtime, drop-rate, purchase, payment, combat, DB, or Production change is authorized.

## Readiness snapshot

| Domain | READY / PURE | QUARANTINED | NEEDS_ART | NEEDS_RUNTIME | NEEDS_DECISION |
| --- | ---: | ---: | ---: | ---: | ---: |
| Canonical Items | 24 | 0 | 0 | 0 | 0 |
| Wardrobe appearances | 44 | 20 existing effects | 0 | 0 | 0 |
| Stone + board skins | 10 | 0 | 0 | 0 | 0 |
| Collection families | 6 active/projection | 1 contract-only | — | deferred | 0 |

## ITEM_BATCH_1 — Freeze the canonical Item registry

Scope: exactly 24 records in `go_odyssey_wave2_item_inventory.json`.

- Freeze 2 Materials and 22 Consumables.
- Preserve existing `shop_inventory.item_key` / `pet_inventory.item_key` authority.
- Preserve current assets and runtime projections.
- Keep Item Journal GET read-only and `NOT_TRACKED`.
- Do not add Zone/Boss drops, ownership tables, or new acquisition behavior.

## ITEM_BATCH_2 — Legacy quarantine and future Zone/Boss identity

Scope: existing rejected legacy references plus future contract-only records.

- Keep rejected legacy references outside canonical Item, Cosmetic, production, reward, and monetization surfaces.
- Preserve existing runtime rejection/compatibility paths; do not delete them in this freeze.
- Future records require `ITEM_ID`, `DISPLAY_NAME`, `ZONE_ID`, `BOSS_ID`, `MONSTER_FAMILY`, `SOURCE_TYPE`, `QUEST_ROLE`, `COLLECTION_ROLE`, `SHOP_ALLOWED`, `COMBAT_POWER`, and `ASSET_KEY`.
- Require `COMBAT_POWER=NONE), `SHOP_ALLOWED=NO` by default, and server settlement ownership.
- Zone 5 uses explicit `zone_05` plus canonical source family/tag, set palette, and asset key.
- Owner gate is required before future art, drops, quest turn-in, or collection writer work.

## COSMETIC_BATCH_1 — Freeze pure presentation

Scope: 44 wardrobe appearances without existing gameplay effects.

- Freeze IDs, slots, assets, unlock source, and renderer mapping.
- Keep `player_wardrobe.item_id` as ownership and `player_appearance.<slot>_id` as selected state.
- `FUNCTIONAL_POWER=NO`; selection is presentation-only.
- Keep character bodies separate from wardrobe and functional equipment.
- No weapon-cosmetic authority is created.

## COSMETIC_BATCH_2 — Quarantine effects and normalize world skins

Scope: 20 effect-bearing appearances plus 10 stone/board skins.

- Preserve the 20 current XP/drop effects; do not remove or expand them here.
- Freeze the quarantine manifest with `MONETIZATION_ALLOWED=NO` and `SEPARATION_REQUIRED=YES`.
- Classify all 10 stone/board skins as `PURE_PRESENTATION`, functional effect count zero, server-authoritative ownership contract, and presentation-only selection.
- Report current commerce separately from principle eligibility; do not hardcode launch pricing.
- No paid functional advantage, reward multiplier, Go rank benefit, or guaranteed victory is permitted.

## COLLECTION_RUNTIME_BATCH_1 — Deferred projection-only implementation

Not performed in this task:

- Keep Item Journal read-only and `NOT_TRACKED`.
- Link future collection surfaces to existing authorities only.
- Do not create a discovery table, lazy GET writer, generic ownership table, or collection writer.
- This is limited to new generic Wave 2 collection runtime; existing pet/badge domain writers remain unchanged.
- Persistent collection authority is `WAVE3_DEFERRED`.
- Any later runtime work requires focused non-mutation and authority tests.

## Wave 2 closeout boundary

### MUST_HAVE_FOR_WAVE2_CLOSEOUT

1. Owner acceptance of the canonical Item, Cosmetic, quarantine, skin, and collection contracts.
2. Exactly 24 canonical Item IDs with 24/24 asset closure.
3. Exactly 44 pure-presentation appearances and 20 explicit effect quarantine records.
4. Exactly 10 stone/board skins with zero functional effects.
5. Functional equipment remains separate with zero taxonomy conflicts.
6. No pay-to-win product is approved or enabled.
7. Collection remains projection-only with no discovery DB or writer.
8. Future Zone/Boss identity contract is accepted before new content activation.

### CAN_DEFER_TO_WAVE3

1. Actual Zone/Quest/Lore Item IDs and server settlement.
2. Durable discovery history, if later required.
3. NPC, Boss, and Zone collection UI/runtime.
4. Full cross-collection UI.
5. Reconciliation of legacy Hero `combat_*` stat-gear authority.

### CAN_DEFER_TO_WAVE4_MONETIZATION

1. New premium cosmetic categories.
2. Paid cosmetic bundles or collection-completion offers.
3. Monetized world, board, or companion expansions.
4. Any effect-bearing or advantage-bearing commerce design.

## Explicit invariants

- `FUNCTIONAL_EQUIPMENT_TAXONOMY_CONFLICTS=0`.
- `COSMETICS_GRANT_COMBAT_POWER=NO`.
- `MONETIZABLE_EFFECT_BEARING_COUNT=0`.
- `PAY_TO_WIN_PRODUCT_COUNT=0`.
- `COLLECTION_RUNTIME_IMPLEMENTATION=NO`.
- `DB_MIGRATION=NO`; `MERGE=NO`; `DEPLOY=NO`; `PRODUCTION_MUTATION=NO`.
