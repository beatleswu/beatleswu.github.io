# Go Odyssey World NPC Canonical Spec v1

Status: `CANONICAL_FREEZE_REVIEW`

This spec freezes the seven Owner-approved World NPC presentation identities
and defines their read-only runtime projection. It does not create player
characters, functional equipment, combat entities, ownership, or NPC gameplay.

## Authority and source of truth

- Canonical repository base: `origin/master`
- P1 approved art source: `2e117fe11cd1a29a88adf55dd337d6e55d26c9ac`
- P2 approved art source: `73ed39ecfe7029050628c414eb6d8a371237e78e`
- P3 approved art source: `53bd2c9db7e1618d5230515080654fc25330bab9`
- Identity and presentation registry: `docs/planning/rpg_wave2_lane_a_character_identity_registry_v1.json`
- Runtime loader: `rpg_world_npc_registry.py`
- Read-only runtime projection: `GET /api/world-npcs`

The `world_npcs` array in the identity registry is the only canonical World
NPC presentation registry. `canonical_id` is the machine identity field
(`NPC_ID`); `asset_key` is the canonical art identity. P1/P2/P3 review
manifests remain provenance, not competing registries.

The filename `rpg_wave2_lane_a_character_identity_registry_v1.json` is
historical: it was created as the shared Wave 2 character identity registry
before the World NPC freeze. It remains the existing shared registry and its
`world_npc_presentation_registry.world_npcs` section is now the sole World NPC
canonical authority. `rpg_world_npc_registry.py` is only a fail-closed runtime
projection loader, not a second registry.

## Frozen NPC set

| NPC_ID | DISPLAY_NAME | ZONE | ROLE | ART_MASTER | RUNTIME_ASSET | MOBILE_ASSET |
|---|---|---|---|---|---|---|
| `world.village_elder` | 村長 / Village Elder | Zone 1 Newbie Village | Living teacher and keeper of the first Go trial | `wave2_p1/world_village_elder_p1.png` | `wave2_p1/world_village_elder_p1.webp` | same runtime WebP |
| `world.messenger` | 信使 / Messenger | Zone 1 / Shot 10 transition | Courier delivering the missing-caravan hook | `wave2_p1/world_messenger_p1.png` | `wave2_p1/world_messenger_p1.webp` | same runtime WebP |
| `world.smith_elder` | 鐵匠長老 / Smith Elder | Zone 5 Orc Tribe | Elderly smith and corrupted-ore lore authority | `wave2_p2/world_smith_elder_p2.png` | `wave2_p2/world_smith_elder_p2.webp` | same runtime WebP |
| `world.archmage` | 大法師 / Archmage | Zone 7 Sage Tower | High-level mentor and answer-reframing sage | `wave2_p2/world_archmage_p2.png` | `wave2_p2/world_archmage_p2.webp` | same runtime WebP |
| `world.serel` | Serel / 瑟瑞爾 | Zone 8 Demon Castle Front | Frontline officer responsible for real soldiers | `wave2_p2/world_serel_p2.png` | `wave2_p2/world_serel_p2.webp` | same runtime WebP |
| `world.herder` | 牧人 / Herder | Zone 2 Slime Plains | Field caretaker and civilian witness | `wave2_p3/world_herder_p3.png` | `wave2_p3/world_herder_p3.webp` | same runtime WebP |
| `world.eastern_guardian` | 東方守護者 / Eastern Guardian | Zone 10 Ancient Doom Temple | Silent regional guardian communicating by gesture | `wave2_p3/world_eastern_guardian_p3.png` | `wave2_p3/world_eastern_guardian_p3.webp` | same runtime WebP |

All paths above are relative to the repository `assets/world/characters/`
root where abbreviated in the table. The full paths, story references, and
authority flags are machine-checked in the registry and focused tests.

## Asset freeze contract

Exactly seven PNG masters and seven WebP runtime assets are required. Every
master and runtime asset is `1056x1408`; masters are RGBA PNG; runtime assets
retain true alpha and are derived from the approved masters. The responsive
mobile presentation uses the alpha-clean runtime asset; CSS/card sizing may
change, but identity-specific redrawing is not allowed.

Required gates:

- no missing asset paths;
- no duplicate identity hashes;
- no opaque matte, checkerboard residue, or accidental white background;
- transparent pixels carry neutral RGB values;
- no approved P1/P2/P3 master is overwritten;
- no runtime asset is treated as a player appearance or functional item.

`world_messenger_p1.webp` was deterministically re-derived from its approved
PNG master because the inherited derivative had lost alpha. This is a runtime
derivative correction only; the approved PNG master is unchanged.

## Authority boundary

Every record is fixed to:

```text
PLAYER_SELECTABLE=NO
PLAYER_INVENTORY_AUTHORITY=NO
COMBAT_AUTHORITY=NO
EQUIPMENT_AUTHORITY=NO
SHOP_AUTHORITY=NO
OWNERSHIP_MUTATION=NO
```

World NPC art is presentation/story identity. Functional equipment remains
Lane A/Lane B authority, player appearance remains the existing character and
wardrobe authority, and no NPC record is added to either store.

## Story compatibility

Existing story keys, display aliases, dialogue keys, and cinematic names are
preserved. Compatibility aliases include:

- Village Elder: `Elder`, `村長`, `e10.village_elder`
- Messenger: `Messenger`, `Runner`, `runner`, `e10.messenger`
- Herder: `Herder`, `牧人`, `牧者`, `herder`, `e10.zone2.herder`
- Smith Elder: `Smith-elder`, `鐵匠長老`
- Archmage: `Archmage`, `大法師`
- Serel: `Serel`, `瑟瑞爾`
- Eastern Guardian: `Eastern Guardian`, `Eastern guardian`, `東方守護者`

The registry's story references point to existing screenplay, voice, and
dialogue-package files. `BROKEN_STORY_REFERENCE_COUNT` must remain zero.

## Runtime surface audit

| SURFACE_ID | USER_VISIBLE_OR_INTERNAL | CURRENT_CONSUMER | CURRENT_NPC_SOURCE | STATUS |
|---|---|---|---|---|
| `canonical_registry_api` | `INTERNAL_API` | API clients requesting the presentation projection | `world_npc_presentation_registry.world_npcs` via loader | `INTEGRATED` |
| `static_asset_serving` | `USER_VISIBLE` | Existing Flask `/assets/<path>` browser requests | `record.runtime_asset` | `INTEGRATED` |
| `story_cinematic` | `USER_VISIBLE` | E10 screenplay/storyboard timing and cinematic presentation | Existing screenplay names, aliases, and cinematic assets | `LEGACY_NONBLOCKING` |
| `zone_details` | `USER_VISIBLE` | No current Zone detail NPC-art component | None | `DEFERRED` |
| `npc_cards` | `USER_VISIBLE` | No current NPC card component; review HTML is provenance only | None | `DEFERRED` |
| `dialogue_surfaces` | `USER_VISIBLE` | Existing E10 dialogue/audio lookup and playback | Existing voice IDs, speaker keys, and aliases | `LEGACY_NONBLOCKING` |
| `world_map_zone_ui` | `USER_VISIBLE` | Existing world map and Zone UI | Zone map presentation only; no NPC binding | `NOT_REQUIRED` |
| `journal_lore` | `USER_VISIBLE` | Item Journal and player-owned collections | None; World NPCs are not owned items | `NOT_REQUIRED` |

`MISSING_REQUIRED=0`.
`UNCLASSIFIED_MISSING_SURFACE_COUNT=0`.
`INTEGRATED_SURFACE_COUNT=2`.
`MISSING_REQUIRED_SURFACE_COUNT=0`.
`DEFERRED_SURFACE_COUNT=2`.
`LEGACY_NONBLOCKING_SURFACE_COUNT=2`.
`NOT_REQUIRED_SURFACE_COUNT=2`.
Zone details and NPC cards are explicitly deferred
because no current runtime consumer exists; adding either would be new UI
scope rather than closure of the frozen presentation registry.

Responsive validation for the integrated static asset surface uses the same
alpha-clean runtime WebP at desktop, iPad landscape, iPad portrait, and mobile
card sizes. No player-character fallback or viewport-specific NPC identity is
introduced. The API surface is metadata-only.

The API is intentionally not login-gated because it contains public static
world presentation metadata. It performs no database read or write and has no
mutation method.

## Legacy references

Exactly two live legacy reference groups remain, both
`LEGACY_NONBLOCKING`; neither is safe to remove during this freeze:

| FILE | REFERENCE | CURRENT_BEHAVIOR | LIVE_OR_DEAD | SAFE_TO_REMOVE |
|---|---|---|---|---|
| `docs/planning/e10_final_screenplay_v1.md` | Zone 1 Shot 10 `Runner/messenger`, plus existing forms such as `Elder` and `Smith-elder` | Live cinematic/story content resolves display names and does not consume the full-body World NPC runtime asset registry | `LIVE` | `NO` |
| `docs/planning/e10_voice_cast_bible_v1.md`; `assets/e10/audio/zone2/zone2-dialogue-assets.json` | `e10.village_elder`, `e10.messenger`, `e10.zone2.herder`, and `speaker=herder` | Live voice/audio lookup keys drive dialogue playback and remain separate from World NPC art identity | `LIVE` | `NO` |

`UNEXPLAINED_LEGACY_REFERENCE_COUNT=0`. Compatibility aliases remain intact;
they are not alternate NPC registries or ownership authorities.

## Packaging closure

The source closure contains seven approved PNG masters. The production static
release manifest contains exactly the seven WebP runtime assets; mobile assets
are aliases of those same seven runtime paths. PNG masters are deliberately
`SOURCE_ONLY_NOT_DEPLOYED`, so the release does not expose source masters as a
second presentation payload. The previous freeze inventory impact is:

```text
FILES_ADDED=7
BYTES_ADDED=5236664
OWNER_APPROVED_PROJECT_CREATED_ENTRIES_ADDED=7
```

The packaging contract is deterministic and explicitly rejects any
superseded Eastern Guardian shield asset as canonical. No Eastern Guardian
runtime or master path contains a shield variant.

## Mapping discrepancies retained explicitly

1. Messenger is identified by a Zone 1 Shot 10 transition rather than a
   standalone zone label; the registry retains `zone_id=1` and the shot
   locator.
2. The existing `zone-05-sky-tower.webp` map filename is a legacy display label;
   story and identity evidence still place Smith Elder in Zone 5 Orc Tribe.
   The map asset is not renamed.
3. `assets/hero/npc_blacksmith_tall.webp` and
   `assets/hero/npc_blacksmith_full.webp` are generic legacy blacksmith art,
   not the canonical Smith Elder identity. They remain references only.

No discrepancy changes a story key, zone settlement, player selection path, or
gameplay authority.
