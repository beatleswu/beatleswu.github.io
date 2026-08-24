# A024 Player/Hero Presentation Readiness Recon V1

## Status and provenance

| Field | Value |
|---|---|
| Task | `A024_PLAYER_HERO_PRESENTATION_READINESS_RECON_V1_001` |
| Start `origin/master` | `58d9b7047f285751a048fc551c955909c87984ac` |
| Branch | `codex/a024-player-presentation-readiness-recon` |
| Mode | Read-only recon, static validation, docs only |
| B028 accepted input | `2c8b879a8667c0247c23e560475ee29fafad508d` |
| B028 ancestor of start master | No; the accepted B028 module is not present in the start tree |

This report treats B028 as the accepted contract input, not as a runtime
dependency that is already deployed or integrated. No application, API,
frontend, schema, asset, or production file was changed by A024.

## Executive conclusion

The current player-facing surfaces do not directly consume the accepted B028
read model. The safe next integration step is one authenticated, read-only
Player Presentation endpoint backed by B028, followed by thin per-surface
adapters. This removes duplicated reads without creating a second authority.

The endpoint must expose the B028 projection and preserve these boundaries:

- Hero identity is presentation-only and comes from
  `player_appearance.character_key`.
- XP/level and persistent HP are read projections from `user_stats`.
- Functional equipment ownership/equipped state comes from
  `player_inventory`; `equip` is not `consume`.
- Spirit presentation consumes the one server B022/D008 active-Spirit
  projection; no second Spirit state is created.
- Cosmetic ownership/selection comes from `player_wardrobe` and
  `player_appearance`; cosmetics do not imply combat power.
- World progression and encounter HP remain outside the Player/Hero read
  model.

### Readiness counts

The surface classes below are mutually exclusive. `B028_COMPATIBLE=YES` means
that a safe subset can consume B028 after an adapter; it does not mean that a
current page already calls B028.

| Metric | Count |
|---|---:|
| Player/Hero presentation surfaces inventoried | 14 |
| Current direct B028 consumers | 0 |
| Needs B028 API adapter | 5 |
| Needs separate authority | 6 |
| Legacy compatibility required | 2 |
| Owner decision required | 1 |
| Active runtime Hero character keys | 10 |
| `APPEARANCE_DEFS` records | 64 |
| Pure presentation registry records | 44 |
| Hidden/unreleased appearance IDs | 5 |
| Effect-bearing appearance IDs | 20 |
| Canonical Spirit identities | 6 |
| Spirit stage presentation records | 18 |

## B028 contract used by the recon

The accepted B028 builder is a read-only projection with the following
top-level sections:

```text
read_model
read_model_version
projection_status
read_only
mutates
player_id
hero
progression
hp
equipment
spirit
cosmetics
world
provenance
```

Important B028 fields and boundaries:

- `hero.hero_id` is resolved from `player_appearance.character_key` and is
  explicitly `presentation_only`; invalid or absent values fail closed to the
  presentation default rather than creating gameplay Hero authority.
- `progression` reads `user_stats` and carries XP, rank level, normalized
  level, rank XP, Go rank, correct/streak counters, and persistent HP inputs.
- `hp.persistent_player_hp` and `hp.persistent_player_max_hp` are distinct
  from `hp.encounter_hp`, which is intentionally not projected and remains
  owned by `encounter_local_battle_state`.
- `equipment.slots` and `equipment.owned_items` are derived from
  `player_inventory` and the existing `EQUIPMENT_DEFS` catalog. Conflicted
  equipped slots fail closed; combat stats are not projected.
- `spirit.active` is the single active Spirit projection with
  `spirit_id`, `enabled`, ownership validation, evolution stage, and
  progression level. Combat effects are not projected.
- `cosmetics.selected` and `cosmetics.owned_items` are presentation-only
  projections from `player_wardrobe` and `player_appearance`.
- `world.projected=false`; selected zone, stars, completion, Lord readiness,
  and unlock progression remain World authority.

## Current Player/Hero surface inventory

The complete machine-readable matrix is in
[`a024_player_presentation_surface_matrix.json`](a024_player_presentation_surface_matrix.json).

| Surface | Current sources | B028 use | Readiness class | Main gap |
|---|---|---|---|---|
| `hero_overview` | `hero.html`; `/api/skills/profile`, `/api/player/appearance`, `/api/pet/status`, `/api/user/coins`, `/api/auth/me` | Safe identity, progression, Hero, Spirit, cosmetic subsets | `NEEDS_API_ADAPTER` | The page consumes a legacy aggregate containing combat/effect fields and multiple parallel calls. |
| `hero_appearance_wardrobe` | `hero.html`; `/api/player/appearance`, `/api/skills/profile`, equip/unequip routes | Safe `hero` and cosmetic owned/selected projection | `NEEDS_API_ADAPTER` | Legacy wardrobe mixes presentation metadata, effect-bearing appearances, and hidden filtering behavior. |
| `hero_equipment_loadout` | `hero.html`; `/api/player/inventory`, `/api/skills/profile`, legacy `/api/skills/character` | Safe equipment ownership, slots, equipped state | `NEEDS_API_ADAPTER` | Two equipment presentations coexist; combat loadout fields are not the B028 functional-equipment projection. |
| `hero_spirit_panel` | `hero.html`; `/api/pet/status` and Spirit interaction routes | Safe single active Spirit presentation fields | `NEEDS_API_ADAPTER` | Payload includes legacy pet state and bonuses beside `b022_active_spirit`; interaction mutations remain separate. |
| `hero_achievement_badges` | `hero.html`; `/api/badges/definitions`, `/api/badges/earned` | No B028 badge authority; B028 may provide context only | `NEEDS_SEPARATE_AUTHORITY` | Badge progress, earned history, and title collection are not Player/Hero read-model fields. |
| `adventure_world_identity` | `index.html`, adventure components, E9 player/adventure adapters | Safe player identity/avatar/level subset; World remains separate | `NEEDS_API_ADAPTER` | Current page joins player calls with authoritative zone/bootstrap state; a Player endpoint must not absorb World fields. |
| `adventure_encounter_result` | `index.html`; `/api/question`, `/api/monster/battle`, `/api/adventure/map-battles/v1/*` | Persistent HP can refresh after settlement; encounter state cannot come from B028 | `NEEDS_SEPARATE_AUTHORITY` | Battle payload owns encounter HP, Monster HP, damage, correctness, and settlement result. |
| `backpack_inventory` | `inventory.html`; `/api/player/inventory`, `/api/shop/catalog`, `/api/pet/status` | Functional equipment subset only | `NEEDS_SEPARATE_AUTHORITY` | Backpack also owns non-equipment item quantities in `shop_inventory` and `pet_inventory`; these are outside B028. |
| `item_journal` | `item_journal.html`; `/api/item-journal` | No direct B028 replacement | `NEEDS_SEPARATE_AUTHORITY` | The journal intentionally excludes functional equipment and wardrobe ownership and uses its own item registry. |
| `shop_cosmetic_and_item_preview` | `shop.html`; cosmetic-commerce, Premium, shop catalog and purchase/preview APIs | Owned/equipped presentation can be read from B028 after adaptation | `NEEDS_SEPARATE_AUTHORITY` | Catalog, price, purchase, Premium, Gacha, and entitlement authorities remain Shop/Commerce/Premium domains. |
| `public_profile` | `profile.html`; `/api/profile/<username>` and public game routes | No direct authenticated B028 reuse | `OWNER_DECISION_REQUIRED` | Public privacy and field redaction must be decided before exposing any Player read model projection. |
| `stats_dashboard` | `stats.html`; `/api/auth/me`, `/api/stats/dashboard`, quest/monster stats, appearance | Basic identity/XP can be refreshed from B028 | `LEGACY_COMPAT_REQUIRED` | Historical analytics and charts require the existing stats authority; the page cannot be replaced by a snapshot read model. |
| `premium_account_display` | `upgrade.html`; subscription, Premium offer/status and claim routes | No Premium authority in B028 | `NEEDS_SEPARATE_AUTHORITY` | Entitlement, expiry, offer, claim, payment, and grace semantics are intentionally outside Player/Hero presentation. |
| `quest_reward_result` | `index.html`; question, quest, training, shop-use and Premium result flows | B028 can refresh post-settlement player state | `LEGACY_COMPAT_REQUIRED` | Reward settlement and result messaging must continue to consume the committed result; B028 must never infer a reward. |

### Responsive variants

The same data contracts are used by the responsive variants; there is no
separate mobile authority. `hero.html` and `inventory.html` have materially
different mobile layout branches, while World Map/HUD and battle panels use
responsive CSS/DOM presentation over the same API payloads. The adapter must
therefore return stable semantic fields, not viewport-specific values.

## B028 field-to-UI matrix

| Category | B028 path / contract | Authority | Presentation safe | Current consumers | Future consumers | API / transform need | Missing semantics or boundary |
|---|---|---|---|---|---|---|---|
| PLAYER | `player_id`; display name is not a B028 field | `users.id`; current display label is session/user-derived | `YES` for authenticated identity; public use is unresolved | Hero, HUD, stats, adventure | All authenticated Player surfaces | API: yes; transform: display-label adapter | Define display-name fallback and privacy; never accept client-authored identity. |
| HERO | `hero.hero_id`, `identity_status`, `authority_scope=presentation_only`, fallback ID | `player_appearance.character_key` | `YES` | Hero, HUD avatar, World marker | Hero roster, HUD, World marker | API: yes; transform: map key to canonical asset | Asset lookup remains a presentation adapter; no Hero combat/class authority. |
| XP_LEVEL | `progression.xp`, `rank_level`, `level`, `rank_xp`, `go_rank`, counters | `user_stats`; existing level resolver | `YES` for display | Hero, HUD, stats, quest progress | Hero/HUD/player endpoint | API: yes; transform: legacy `lv`/`lv_xp` names and progress bar | Do not copy XP curves into the client; Go rank is not paid or Hero power. |
| PERSISTENT_HP | `hp.persistent_player_hp`, `hp.persistent_player_max_hp` | `user_stats.player_hp/player_max_hp` | `YES` when labelled persistent/player state | No current general Hero/HUD consumer; battle setup may use legacy state | Hero summary or safe player HUD | API: yes; transform: label as persistent | Must not replace encounter HP or be combined with Monster battle HP. |
| PERSISTENT_HP | `hp.encounter_hp.projected=false` | `encounter_local_battle_state` | `NO` as a B028 value | Battle UI uses battle result `player_hp` fields | Battle/encounter presentation only | API: separate battle read/result; transform: none | Encounter HP requires active battle context and remains outside Player/Hero read model. |
| EQUIPMENT | `equipment.slots`, `owned_items`, `equipped`, `functional_status` | `player_inventory` + `EQUIPMENT_DEFS` | `YES` for ownership/slot presentation | Hero gear, inventory | Hero gear and post-mutation refresh | API: yes; transform: display projection only | Equip is not consume; conflicted equipped slots fail closed; combat stats are not projected. |
| EQUIPMENT | `equipment.combat_stats_projected=false` | Combat/effect authorities | `NO` as B028 data | Legacy profile/gear displays may request combat fields | A separately governed combat projection | API: separate if ever approved; transform: no client calculation | Never infer power from Shop catalog or cosmetic metadata. |
| SPIRIT | `spirit.active` with `spirit_id`, enabled, ownership validation, evolution stage, progression level | `pet_collection` + `user_pets` through B022/D008 projection | `YES` for active identity/stage/level | Hero Spirit panel, World follower, Adventure | All read-only Spirit presentation | API: yes; transform: map Spirit ID to A021 asset manifest | One active Spirit only; combat effects remain unprojected and separately governed. |
| SPIRIT | `combat_effects_projected=false` | B022/B027 settlement/effect authority | `NO` for numeric effects | Legacy pet payload may include bonus fields | Future effect summary only after authority contract | API: separate; transform: no fabricated value | Do not display a bonus merely because a legacy payload contains a field. |
| COSMETIC | `cosmetics.selected`, `owned_items`, `presentation_only=true` | `player_wardrobe` + `player_appearance` | `YES` | Hero Appearance, Shop preview, profile/avatar context | Wardrobe, Hero, in-world panels | API: yes; transform: release-state and asset projection | Keep owned, selected, available, and unreleased states distinct. |
| COSMETIC | `gameplay_effects_projected=false` | Existing legacy effect registry where applicable | `NO` as pure-cosmetic claim | Hero currently renders effect-bearing appearances separately | Future effect-aware presentation | API: separate legacy effect projection; transform: explicit taxonomy | Current `APPEARANCE_EFFECTS` has 20 IDs; these must not be silently labelled pure appearance. |
| WORLD_BOUNDARY | `world.projected=false`, `selected_zone_is_not_player_progression=true` | World/adventure progression system | `YES` as an exclusion marker only | Adventure World Map | World shell and zone panels | API: no B028 extension; separate World API | Current zone, selected zone, stars, completion, Lord readiness, and next unlock stay out of Player/Hero authority. |
| WORLD_BOUNDARY | No B028 path for zone progression | `/api/adventure/bootstrap`, `/api/adventure/map-state`, `/api/adventure/progress` | `NO` as Player/Hero data | World Map and Adventure | World-specific adapters | API: separate World endpoint; transform: World normalizer | Never manufacture World state from Hero level, XP, or equipment. |

## Legacy consumer and adapter gap map

| Consumer | Legacy behavior | Required disposition |
|---|---|---|
| `js/e9/adapters/player_state.js` | Parallel reads of `/api/skills/profile`, `/api/user/coins`, and `/api/player/appearance`; maps `character_key` to a ten-key asset table | `SAFE_TO_REPLACE_WITH_B028` for identity/level/coins after the Player endpoint includes an explicit display/coins contract; preserve the asset mapping as a presentation adapter. |
| `hero.html` aggregate profile | Reads a broad `/api/skills/profile` payload containing progression, wardrobe, `active_effects`, combat stats, and legacy fields; also derives bonus totals in client code | `NEEDS_ADAPTER`; replace only read projection consumers first; keep effect/combat controls on their existing authorities. |
| `hero.html` character loadout | Uses `COMBAT_STORAGE_KEY`/local state for UI selection and calls `/api/skills/character` for the legacy combat loadout | `LEGACY_COMPAT_REQUIRED`; B028 must not become functional Hero authority. |
| `/api/player/appearance` consumer | Returns wardrobe/selected appearance plus legacy `combat_*` fields and calls `ensure_premium_rewards` during a read | `NEEDS_ADAPTER`; remove no behavior in A024, but the future read adapter must project only presentation state and must not inherit the read-side mutation. |
| `/api/pet/status` consumer | Payload combines legacy pet catalog/state, food/training data, bonuses, and `b022_active_spirit` | `NEEDS_ADAPTER`; use only the server B022 active-Spirit projection for read-only Spirit identity/stage. |
| `/api/xp/status` consumer | Legacy XP endpoint normalizes a battle/learning view and currently has `INSERT OR IGNORE`/commit behavior | `LEGACY_COMPAT_REQUIRED`; B028 should replace read use after endpoint review, never by copying its side effects. |
| `inventory.html` Backpack | Reads `player_inventory` for functional equipment and `shop_inventory`/`pet_inventory` for other items; emoji fallback remains a presentation concern | `NEEDS_SEPARATE_AUTHORITY`; use B028 for the equipment slice only and preserve non-equipment item journal/shop authorities. |
| `item_journal.html` | Uses `/api/item-journal`, which deliberately excludes equipment and cosmetic ownership | `NEEDS_SEPARATE_AUTHORITY`; do not fold the journal into B028. |
| `shop.html` | Catalog/preview/price/purchase/Premium/Gacha flows are separate commerce authorities; owned state is server-projected | `NEEDS_SEPARATE_AUTHORITY`; B028 may supply a read-only owned/selected overlay, never catalog or purchase truth. |
| `index.html` World Map | Player identity is joined with Adventure bootstrap/map-state/progress and battle/learning calls | `NEEDS_ADAPTER` for the player fragment; `NEEDS_SEPARATE_AUTHORITY` for World and battle fragments. |
| `index.html` battle result | Uses `player_hp`, `monster_hp`, answer correctness, damage, and settlement response fields | `NEEDS_SEPARATE_AUTHORITY`; these are encounter/result authority, not B028 Player/Hero fields. |
| `profile.html` public profile | Reads a public username route and public game records | `OWNER_DECISION_REQUIRED`; design a separately redacted public projection before reuse. |
| `stats.html` | Reads historical/statistical dashboards and quest/monster summaries | `LEGACY_COMPAT_REQUIRED`; B028 can provide header identity/progression only. |

No current UI surface is allowed to infer ownership from a Shop catalog. The
Shop response may carry server-projected owned state for convenience, but
ownership remains `player_inventory` or `player_wardrobe` according to item
family.

## HP classification

| Display or source | Classification | Evidence / handling |
|---|---|---|
| B028 `hp.persistent_player_hp` / `persistent_player_max_hp` | `PERSISTENT` | Read from `user_stats`; suitable for a labelled persistent player summary. |
| `index.html` battle board `#ba-player-hp-*` | `ENCOUNTER` | Updated from battle result `player_hp`/`player_hp_after`; paired with Monster HP and battle feedback. |
| `index.html` `#monster-hp-*` | `ENCOUNTER` | Monster/encounter authority only. |
| `js/map_battle_v1_adapter.js` `playerHp` / `monsterHp` | `ENCOUNTER` | Local battle presentation state derived from the authoritative battle response. |
| `components/adventure/top_hud.html` | `NOT_APPLICABLE` | Current HUD deliberately does not show HP; it shows identity/level/coins. |
| Hero, Backpack, Wardrobe, Shop, Profile, Stats headers | `NOT_APPLICABLE` | No persistent or encounter HP is displayed by the inspected current surface. |

`PERSISTENT_HP_ENCOUNTER_HP_BOUNDARY=PASS`. The source vocabulary is legacy,
but the inspected displays can be classified unambiguously when traced to
their endpoint. A future Player endpoint must not expose encounter HP as a
Player/Hero field.

## Authority contract for future UI integration

### Allowed direct use after a read endpoint exists

- `hero.hero_id` and its presentation asset mapping.
- Name/level/XP/rank display fields after server normalization.
- Persistent HP with an explicit persistent label.
- Equipment owned/equipped/slot/functional-status presentation.
- One active Spirit identity, evolution stage, and progression level.
- Cosmetic owned/selected/presentation metadata after hidden/release-state
  filtering.

### Must remain separate

- Functional Hero authority: none exists and none is created.
- Equipment mutations: existing server equip/unequip endpoints.
- Appearance mutations: existing wardrobe equip/unequip endpoints.
- Spirit ownership/selection/training/interactions: existing server routes.
- Encounter correctness, damage, Monster HP, and battle settlement.
- World progression, zone selection, stars, completion, Lord readiness.
- Badges, achievement history, title collection authority.
- Backpack non-equipment quantities and Item Journal registry.
- Shop catalog, prices, purchases, Gacha, Premium and payment flows.
- Public profile privacy projection.

### Recommended conceptual response

`ONE_PLAYER_PRESENTATION_ENDPOINT_RECOMMENDED=YES`.

Recommend a future authenticated, read-only endpoint that returns the B028
projection in one consistent snapshot, with a narrowly defined identity
presentation adapter for display name and asset metadata:

```json
{
  "read_model": "player_hero_state",
  "read_model_version": "player_hero_state_v1",
  "player": {"player_id": 123, "display_name": "server-derived"},
  "hero": {},
  "progression": {},
  "hp": {"persistent_player_hp": 0, "persistent_player_max_hp": 0},
  "equipment": {},
  "spirit": {},
  "cosmetics": {},
  "world": {
    "projected": false,
    "authority": "world_progression_system"
  }
}
```

The `player` wrapper above is a response-shape proposal; B028’s exact
canonical identity is still `player_id` plus provenance. The endpoint must
not add `zone`, `stars`, `lord readiness`, `encounter_hp`, combat totals,
purchase state, Premium entitlement, or client-authored fields. Existing
mutation endpoints remain separate, and the client only renders the returned
projection.

One endpoint is recommended because it gives Hero, HUD, World identity,
Backpack equipment, Wardrobe, and Spirit panels one read snapshot and one
failure/projection-status contract. It is not a replacement for World,
Battle, Shop, Premium, public-profile, badge, or Item Journal endpoints.

## Static validation performed

- Current branch began clean at `58d9b7047f285751a048fc551c955909c87984ac`.
- B028 accepted SHA was inspected directly; it is not an ancestor of the
  current start master, so no current UI was claimed to be B028-integrated.
- `EQUIPMENT_DEFS`: 15/15 records resolve; supported slots are exactly
  `weapon`, `armor`, and `accessory`.
- `APPEARANCE_DEFS`: 64/64 IDs resolve; the pure presentation registry is
  44/44; the hidden set is exactly
  `robe_snow`, `hat_scholar`, `back_lantern`, `back_scroll`, and
  `acc_goban_seal`.
- `APPEARANCE_EFFECTS`: 20 effect-bearing appearance IDs are registered;
  none overlap the 44 pure presentation registry records. They remain a
  separate legacy/effect-aware presentation class.
- Active Hero presentation keys: 10/10 asset paths resolve under
  `assets/hero/characters`.
- Canonical Spirit IDs: 6/6 match `spirit_lineage.KNOWN_SPIRIT_IDS` and the
  A021A presentation manifest; 18/18 stage runtime asset paths exist and
  decode successfully through Pillow.
- Wardrobe dynamic IDs use the server `APPEARANCE_DEFS` catalog; no second
  frontend wardrobe ID authority was found. Catalog closure is 64/64.
- Shop ownership authority: PASS. Shop is a commerce/read projection and
  does not become ownership authority; equipment and cosmetics remain
  `player_inventory` and `player_wardrobe`.
- HP classification: PASS. No inspected surface was left unclassified as
  persistent, encounter, or not applicable.
- Protected files, DB/schema, app.py, runtime, frontend, payment, and
  Production were untouched by A024.

## Owner decision packet

```text
READY_SURFACES=14
NEEDS_API_ADAPTER=5
NEEDS_SEPARATE_AUTHORITY=6
LEGACY_COMPAT_SURFACES=2
OWNER_DECISION_REQUIRED=1

HERO_PRESENTATION_ONLY_BOUNDARY=PASS
FUNCTIONAL_HERO_AUTHORITY_CREATED=NO
PERSISTENT_HP_ENCOUNTER_HP_BOUNDARY=PASS
EQUIPMENT_AUTHORITY_PRESERVED=PASS
SPIRIT_AUTHORITY_PRESERVED=PASS
WARDROBE_AUTHORITY_PRESERVED=PASS
SHOP_OWNERSHIP_AUTHORITY=NO
WORLD_FIELDS_EXCLUDED_FROM_PLAYER_AUTHORITY=PASS
ONE_PLAYER_PRESENTATION_ENDPOINT_RECOMMENDED=YES
```

`RECOMMENDATION_A=BUILD_PLAYER_PRESENTATION_READ_API_NEXT`.

The one Owner decision is the privacy/redaction contract for public profile
consumption. It should be resolved separately; it does not block building an
authenticated Player Presentation read API for the six in-scope domains.

## Scope guard

```text
APP_PY_CHANGED=NO
RUNTIME_CHANGED=NO
FRONTEND_CHANGED=NO
SCHEMA_CHANGED=NO
PRODUCTION_MUTATION=NO
DEPLOY=NO
MASTER_MERGE=NO
```
