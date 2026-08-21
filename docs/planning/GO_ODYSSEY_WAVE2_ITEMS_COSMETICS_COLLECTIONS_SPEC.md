# Go Odyssey Wave 2 Items / Cosmetics / Collections Reconciliation Specification

## Audit identity

- `ORIGIN_MASTER=ac182ed173620a11e66bebeb6003c121b9ceee95`
- Branch: `codex/rpg-wave2-items-cosmetics-collections-reconcile`
- Worktree: `D:\\go-website-rpg-wave2-items-cosmetics-collections-reconcile`
- Mode: read-only swarm audit; planning/manifest files only.
- No runtime, DB, Production, drop-rate, price, payment, XP, or combat change.

## Frozen inventory counts

| Domain | Count | Authority |
| --- | ---: | --- |
| Canonical non-equipment Item Journal records | 24 | `shop_inventory` / `pet_inventory` |
| Item audit candidates including rejected legacy key | 25 | 24 active + 1 `LEGACY_CLEANUP` |
| Wardrobe appearance records | 64 | `APPEARANCE_DEFS` + `player_wardrobe` |
| Stone + board skins | 10 | `player_appearance` selected state + server predicates |
| Active player character appearance IDs | 10 | `player_appearance.character_key` |
| Functional equipment | 15 | `EQUIPMENT_DEFS` + `player_inventory` |
| Companion catalog | 3 | `PET_CATALOG` + `pet_collection` |
| Static badge definitions | 84 | `BADGE_DEFS` + `badges_earned` |

## Item contract

Controlled categories:

- `MATERIAL`: 2 — `rare_appearance_fragment`, `pet_evolution_core`.
- `CONSUMABLE`: 22 — 13 direct consumables + 9 repo `TreasureBundle` products that immediately grant components.
- `QUEST_ITEM`, `LORE_ITEM`, `COLLECTION_ITEM`, `CURRENCY_LIKE`: no current canonical Item Journal records.
- `LEGACY_OR_UNKNOWN`: 1 — `appearance_fragment`, explicitly rejected by `community_leaderboard_rewards.py:2087-2115`; do not create an authority for it.

Item rules: `COMBAT_POWER=NONE`; no new ownership table; bundles are not owned products; journal GET stays read-only; `catalog_visible` is not discovery; quantities are read from existing stores; recentness is log-derived only.

## Equipment boundary

`FUNCTIONAL_EQUIPMENT_TAXONOMY_CONFLICTS=0` for canonical generic Item/Cosmetic IDs and ownership stores. The 15 functional definitions remain solely in `EQUIPMENT_DEFS` + `player_inventory`.

The Hero `COMBAT_GEAR` / `player_appearance.combat_*` keyspace is quarantined legacy/stat gear. It must not be merged with generic Items or Cosmetics by display name, slot, or art; for example, Hero `weapon_t3` and functional `iron_sword` are separate authorities.

## Cosmetic boundary

Generic Cosmetic records = 74:

- 64 wardrobe definitions mapped as outfit→`ARMOR_COSMETIC`, hat/back/accessory→`ACCESSORY_COSMETIC`, pet→`COMPANION_COSMETIC`, aura→`WORLD_COSMETIC`, title→`PROFILE_COSMETIC`.
- 5 stone + 5 board world skins.
- No current `WEAPON_COSMETIC` record.
- Player character bodies are excluded from generic Cosmetic count and remain the 10 active `character_key` IDs.

`COSMETICS_GRANT_COMBAT_POWER=NO` means no direct attack/defense authority. The audit found 20 existing `APPEARANCE_EFFECTS` XP/drop records; these are a product/authority decision gate, especially for premium IDs, not an approved new cosmetic power model. `PAY_TO_WIN_PRODUCT_COUNT=0`.

## Collection boundary

Seven families are frozen:

1. `ITEM_JOURNAL` — current read-only projection, `NOT_TRACKED`.
2. `EQUIPMENT_COLLECTION` — inventory projection, not generic Item rows.
3. `COSMETIC_COLLECTION` — wardrobe projection.
4. `CHARACTER_COLLECTION` — current ten-character presentation and unlock predicates.
5. `COMPANION_COLLECTION` — existing pet domain.
6. `ACHIEVEMENT_BADGE_COLLECTION` — existing badge domain.
7. `WORLD_DISCOVERY` — contract-only umbrella for future Zone/Boss/NPC lore entries.

Current repo has no durable generic discovery state, no generic NPC collection registry, and no generic Boss/Zone collection writer. Existing `RelicsZone` and `AchievementsBadges` are sections/contracts, not proof of active collection records.

## Zone/Boss identity

A future Zone 5 item must carry `ZONE_ID=zone_05`, canonical source family/tag, Zone 5 material palette/set key, and an asset key. The production contract also requires `ITEM_ID`, `DISPLAY_NAME`, `BOSS_ID`, `MONSTER_FAMILY`, `SOURCE_TYPE`, `QUEST_ROLE`, `COLLECTION_ROLE`, `SHOP_ALLOWED`, `COMBAT_POWER`, and `ASSET_KEY`. Non-equipment `COMBAT_POWER=NONE`; `SHOP_ALLOWED=NO` by default; server settlement owns grants; client only renders returned IDs/quantities.

No Zone/Boss drop or collection behavior is activated here.

## Production gates

- `ITEM_BATCH_1`: freeze 24 canonical Item records.
- `ITEM_BATCH_2`: keep the rejected legacy key out of active registries, then contract future Zone/Boss items.
- `COSMETIC_BATCH_1`: freeze 44 pure presentation appearance records.
- `COSMETIC_BATCH_2`: Owner decision for 20 effect-bearing records and 10 world-skin ownership semantics.
- `COLLECTION_RUNTIME_BATCH_1`: later projection-only implementation with authority/non-mutation tests.

Wave 2 must-have, Wave 3 deferrals, and Wave 4 monetization deferrals are bounded in `go_odyssey_wave2_content_production_batches.md`.

## Non-actions

`DB_MIGRATION=NO`; `XP_CHANGED=NO`; `SHOP_CHANGED=NO`; `COSMETIC_RUNTIME_CHANGED=NO`; `COMBAT_CHANGED=NO`; `MERGE=NO`; `DEPLOY=NO`; `PRODUCTION_MUTATION=NO`.
