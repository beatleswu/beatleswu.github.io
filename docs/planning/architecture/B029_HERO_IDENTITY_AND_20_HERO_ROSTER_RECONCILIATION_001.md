# B029 Hero Identity and 20-Hero Roster Reconciliation

Status: read-only reconciliation complete; no runtime or player-state change.

Observed canonical base: `58d9b7047f285751a048fc551c955909c87984ac`

The deterministic machine-readable matrix is
[`b029_hero_identity_matrix.json`](b029_hero_identity_matrix.json). This
document records the evidence and the authority decision behind it.

## Executive result

The project has 20 canonical **player Hero content identities**, but only 10
are registered in the current runtime presentation selector. The other ten
are not a hidden second runtime roster:

| Group | Count | Current meaning |
|---|---:|---|
| `ACTIVE_RUNTIME_PRESENTATION` | 10 | The only current `hero.html`/`app.py` selectable presentation keys. |
| `INACTIVE_IMPLEMENTED_CONTENT` | 3 | `trail_apprentice`, `night_runner`, and `constellation_apprentice`; canonical P1 visual/content packages exist, but runtime registration is explicitly not changed. |
| `CONTENT_ONLY` | 7 | The locked final-seven IDs; presentation candidates/default poses exist, but identity-reference/Owner visual review and runtime registration remain incomplete. |
| Legacy aliases | 6 | Compatibility input keys, not additional Hero content identities. |

Therefore the exact reconciliation is:

```text
20 canonical player content IDs
= 10 active runtime presentation IDs
  + 3 inactive implemented P1 IDs
  + 7 content-only final-seven IDs

6 legacy aliases are outside the 20-content count.
```

The current Hero identity authority is `player_appearance.character_key`,
and its scope is **presentation-only**. No functional Hero identity
authority was found. Combat, Equipment effects, Spirit state, and World
progression do not consume Hero identity.

## Provenance and source map

The current source map was inspected from the fresh worktree at the observed
master above.

| Question | Evidence | Finding |
|---|---|---|
| Where are the 20 IDs enumerated? | `docs/planning/go_odyssey_character_20_inventory.json`: `target_player_character_count=20`, `canonical_roster.status=LOCKED_20_OF_20`, and 20 `records`. | This is the exact canonical content inventory. |
| How are the two ten-ID groups defined? | `docs/planning/rpg_wave2_lane_a_character_identity_registry_v1.json`: 10 `player_characters` plus 10 `new_player_character_concepts`; `docs/planning/GO_ODYSSEY_CHARACTER_20_PRODUCTION_PLAN.md` states 10 runtime IDs plus 10 promoted Wave 2 IDs. | The planning/content scope is intentionally wider than runtime registration. |
| Which IDs are active? | `app.py:16486-16500` (`ACTIVE_CHARACTER_KEYS`, `_presentation_character_key`) and `hero.html:3670-3695` (`COMBAT_GEAR.character`). | The same ten active keys are used by the server presentation boundary and the current Hero page. |
| What does selection persist? | `app.py:16502-16553`, `/api/skills/character`; `app.py:15975-15985`, `/api/player/appearance`. | Selection is stored/read in `player_appearance.character_key`; invalid/legacy values resolve to the server presentation fallback. |
| Where are the three P1 packages? | `docs/planning/rpg_wave2_gate2_character_art_p1_manifest.json`, `assets/hero/characters/wave2_p1/`, and `assets/hero/equipment/wearables/wearable_registry.json`. | Presentation packages exist; the manifest explicitly says candidate IDs are not registered in runtime. |
| Where are the final seven? | `docs/planning/rpg_wave2_master_lane_a_final7_default_pose/final7_default_pose_manifest.json` and `assets/hero/characters/wave2_final7_default_pose_v1/`. | Default-pose presentation candidates exist; the manifest says `authority=presentation_only`, `character_combat_authority=NO`, and `runtime_registration=NOT_CHANGED`. |
| What are the six extra keys? | `app.py:16478-16484` (`VALID_CHARACTER_KEYS`) and `index.html:7988-7995` (`LEGACY_HERO_CHARACTER_KEY_MAP`). | They are legacy aliases mapping to active keys, not additional player Hero content. |

The accepted B028 candidate at `2c8b879a8667c0247c23e560475ee29fafad508d`
was also checked. Its architecture document preserves the same rule:
`player_appearance.character_key` is a presentation-only projection and
B028 does not create a functional Hero selector or roster authority.

## Exact 20-Hero matrix

`asset_refs` below identify current repository assets. A “candidate” asset is
not evidence of runtime registration. `currently_selectable=YES` for active
keys means the current selector supports the key; the existing server unlock
predicate may still lock it for an individual player. `display_name_zh=—`
means no canonical Chinese player display name was present in the inspected
content records; no translation is invented here.

| hero_id | display_name_zh | display_name_en | source_file | asset_refs | ACTIVE_CHARACTER_KEYS | currently_selectable | player_appearance_compatible | functional_gameplay_effect | combat_consumer | equipment_consumer | spirit_consumer | world_consumer | status | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `apprentice` | 見習生 | Apprentice | `hero.html` | `chibi_apprentice_normalized.webp`; P1 candidate | YES | YES | YES | NO | NONE | PRESENTATION_ONLY | NONE | NONE | ACTIVE_RUNTIME_PRESENTATION | Tier 0 current selector entry. |
| `apprentice_girl` | 見習少女 | Apprentice (F) | `hero.html` | `chibi_apprentice_girl_normalized.webp` | YES | YES | YES | NO | NONE | PRESENTATION_ONLY | NONE | NONE | ACTIVE_RUNTIME_PRESENTATION | Tier 0 current selector entry. |
| `swordsman` | 劍士 | Swordsman | `hero.html` | `chibi_swordsman_normalized.webp` | YES | YES | YES | NO | NONE | PRESENTATION_ONLY | NONE | NONE | ACTIVE_RUNTIME_PRESENTATION | Tier 1 current selector entry. |
| `rogue` | 盜賊 | Rogue | `hero.html` | `chibi_rogue_normalized.webp` | YES | YES | YES | NO | NONE | PRESENTATION_ONLY | NONE | NONE | ACTIVE_RUNTIME_PRESENTATION | Tier 2 current selector entry. |
| `ranger` | 遊俠 | Ranger | `hero.html` | `chibi_ranger_normalized.webp` | YES | YES | YES | NO | NONE | PRESENTATION_ONLY | NONE | NONE | ACTIVE_RUNTIME_PRESENTATION | Tier 3 current selector entry. |
| `berserker` | 狂戰 | Berserker | `hero.html` | `chibi_berserker_normalized.webp` | YES | YES | YES | NO | NONE | PRESENTATION_ONLY | NONE | NONE | ACTIVE_RUNTIME_PRESENTATION | Tier 4 current selector entry. |
| `guardian` | 重裝 | Guardian | `hero.html` | `chibi_guardian_normalized.webp` | YES | YES | YES | NO | NONE | PRESENTATION_ONLY | NONE | NONE | ACTIVE_RUNTIME_PRESENTATION | Tier 5 current selector entry. |
| `paladin` | 聖騎 | Paladin | `hero.html` | `chibi_paladin_normalized.webp`; P1 candidate | YES | YES | YES | NO | NONE | PRESENTATION_ONLY | NONE | NONE | ACTIVE_RUNTIME_PRESENTATION | Tier 6 current selector entry; P1 art remains presentation packaging. |
| `mage` | 法師 | Mage | `hero.html` | `chibi_mage_normalized.webp`; P1 candidate | YES | YES | YES | NO | NONE | PRESENTATION_ONLY | NONE | NONE | ACTIVE_RUNTIME_PRESENTATION | Tier 7 current selector entry; P1 art remains presentation packaging. |
| `sage` | 賢者 | Sage | `hero.html` | `chibi_sage_normalized.webp` | YES | YES | YES | NO | NONE | PRESENTATION_ONLY | NONE | NONE | ACTIVE_RUNTIME_PRESENTATION | Tier 8/premium current selector entry. |
| `trail_apprentice` | — | Trail Apprentice | P1 art manifest | `wave2_p1/trail_apprentice_p1.png/.webp`; hair mask | NO | NO | NO | NO | NONE | PRESENTATION_ONLY_CANDIDATE | NONE | METADATA_ONLY | INACTIVE_IMPLEMENTED_CONTENT | Owner-canonical P1 package; runtime registration is explicitly absent. |
| `night_runner` | — | Night Runner | P1 art manifest | `wave2_p1/night_runner_p1.png/.webp`; hair mask | NO | NO | NO | NO | NONE | PRESENTATION_ONLY_CANDIDATE | NONE | METADATA_ONLY | INACTIVE_IMPLEMENTED_CONTENT | Owner-canonical P1 package; runtime registration is explicitly absent. |
| `constellation_apprentice` | — | Constellation Apprentice | P1 art manifest | `wave2_p1/constellation_apprentice_p1.png/.webp`; hair mask | NO | NO | NO | NO | NONE | PRESENTATION_ONLY_CANDIDATE | NONE | METADATA_ONLY | INACTIVE_IMPLEMENTED_CONTENT | Owner-canonical P1 package; runtime registration is explicitly absent. |
| `river_wayfinder` | — | River Wayfinder | Final7 default-pose manifest | `wave2_final7_default_pose_v1/river_wayfinder_default_pose_v1.png/.webp` | NO | NO | NO | NO | NONE | PRESENTATION_ONLY_CANDIDATE | NONE | METADATA_ONLY | CONTENT_ONLY | Canonical final-seven ID; identity reference, visual gate, and runtime registration remain open. |
| `stone_caretaker` | — | Stone Caretaker | Final7 default-pose manifest | `wave2_final7_default_pose_v1/stone_caretaker_default_pose_v1.png/.webp` | NO | NO | NO | NO | NONE | PRESENTATION_ONLY_CANDIDATE | NONE | METADATA_ONLY | CONTENT_ONLY | Canonical final-seven ID; identity reference, visual gate, and runtime registration remain open. |
| `duelist_scout` | — | Duelist Scout | Final7 default-pose manifest | `wave2_final7_default_pose_v1/duelist_scout_default_pose_v1.png/.webp` | NO | NO | NO | NO | NONE | PRESENTATION_ONLY_CANDIDATE | NONE | METADATA_ONLY | CONTENT_ONLY | Canonical final-seven ID; identity reference, visual gate, and runtime registration remain open. |
| `bastion_warden` | — | Bastion Warden | Final7 default-pose manifest | `wave2_final7_default_pose_v1/bastion_warden_default_pose_v1.png/.webp` | NO | NO | NO | NO | NONE | PRESENTATION_ONLY_CANDIDATE | NONE | METADATA_ONLY | CONTENT_ONLY | Canonical final-seven ID; identity reference, visual gate, and runtime registration remain open. |
| `forest_pathfinder` | — | Forest Pathfinder | Final7 default-pose manifest | `wave2_final7_default_pose_v1/forest_pathfinder_default_pose_v1.png/.webp` | NO | NO | NO | NO | NONE | PRESENTATION_ONLY_CANDIDATE | NONE | METADATA_ONLY | CONTENT_ONLY | Canonical final-seven ID; identity reference, visual gate, and runtime registration remain open. |
| `archive_scholar` | — | Archive Scholar | Final7 default-pose manifest | `wave2_final7_default_pose_v1/archive_scholar_default_pose_v1.png/.webp` | NO | NO | NO | NO | NONE | PRESENTATION_ONLY_CANDIDATE | NONE | METADATA_ONLY | CONTENT_ONLY | Canonical final-seven ID; identity reference, visual gate, and runtime registration remain open. |
| `worldkeeper` | — | Worldkeeper | Final7 default-pose manifest | `wave2_final7_default_pose_v1/worldkeeper_default_pose_v1.png/.webp` | NO | NO | NO | NO | NONE | PRESENTATION_ONLY_CANDIDATE | NONE | METADATA_ONLY | CONTENT_ONLY | Canonical final-seven ID; identity reference, visual gate, and runtime registration remain open. |

### Legacy aliases outside the 20

| legacy key | current normalization target | evidence |
|---|---|---|
| `hero_male` | `apprentice` | `app.py` valid-input compatibility; `index.html` map |
| `woman` | `apprentice_girl` | `app.py` valid-input compatibility; `index.html` map |
| `boy_child` | `apprentice` | `app.py` valid-input compatibility; `index.html` map |
| `girl_child` | `apprentice_girl` | `app.py` valid-input compatibility; `index.html` map |
| `elder_master` | `sage` | `app.py` valid-input compatibility; `index.html` map |
| `elder_woman` | `sage` | `app.py` valid-input compatibility; `index.html` map |

These aliases are accepted for compatibility but are not current
`ACTIVE_CHARACTER_KEYS`. The server presentation resolver returns only an
active key and falls back to `apprentice` for an invalid/legacy persisted
value; the alias does not create a new Hero identity.

## Authority and dependency findings

### Q5/Q6: Hero identity and Combat

No functional Hero identity source exists outside
`player_appearance.character_key`. No runtime `hero_id`, selected functional
Hero, Hero class, or Hero stat authority was found.

The actual combat boundary is explicit in `app.py:_get_authoritative_combat_stats`:
functional combat stats are derived from `player_inventory` equipped items and
server `EQUIPMENT_DEFS`; `player_appearance.combat_*` is deliberately not
consulted for combat power. The current combat and Map Battle modules do not
read `character_key`.

Conclusion: `HERO_COMBAT_DEPENDENCY=NO` and no Hero-specific gameplay stat or
effect exists today.

### Q7: Equipment

Equipment has a presentation dependency, not a Hero gameplay dependency.
`assets/hero/equipment/wearables/wearable_registry.json` declares:

```text
ownership = player_inventory
equipped = player_inventory.equipped
effects = server EQUIPMENT_DEFS
character = player_appearance.character_key
presentation_only = true
client_combat_authority = false
```

The client wearable renderer uses the character key to select a base/mask and
explicitly returns `gameplayAuthority=none`. B021 functional weapon/armor/
accessory effects remain independent of Hero identity.

Conclusion: `HERO_EQUIPMENT_DEPENDENCY=YES` only as presentation/asset
compatibility; `HERO_EQUIPMENT_FUNCTIONAL_DEPENDENCY=NO`.

### Q8: Spirit

`spirit_runtime.py` resolves canonical Spirit IDs, ownership, active Spirit,
and stage from Spirit state. No Hero key is read. B028 consumes that Spirit
projection, and B027 consumes the Spirit projection separately. There is no
Hero-to-Spirit gameplay branch.

Conclusion: `HERO_SPIRIT_DEPENDENCY=NO`.

### Q9: World progression

The planning registries include world associations for character flavor and
identity briefs. Those are metadata, not progression authority. No current
World/Map/Monster/Lord progression path was found to consume
`player_appearance.character_key` as a gate, reward source, or state key.

Conclusion: `HERO_WORLD_DEPENDENCY=NO`; narrative association metadata must
not be promoted into World authority.

### Q10: Hero-specific gameplay

No current Hero-specific attack, defense, HP, damage, mitigation, XP, drop,
quest, Spirit, or World effect exists. The identity registry and the P1/
final-seven manifests explicitly mark character combat authority as `NO` and
functional weapon baking as false.

## Q11: What would activating the missing ten require?

It is not a registry-only change.

For a **presentation-only** activation, a later authorized task would need to
coordinate the current `ACTIVE_CHARACTER_KEYS`/`VALID_CHARACTER_KEYS`, the
Hero page catalog and server unlock predicate, display-name/i18n content,
approved runtime assets, wearable frame/mask compatibility, and the
`player_appearance` selection contract. Reusing `player_appearance` means a
schema migration is not inherently required, but `app.py` route/registry work
would be required and belongs to the single-owner integration task. The
P1/final-seven packages currently prove content/presentation work, not
runtime selection.

For a **functional** Hero identity, the project would additionally need an
Owner product/gameplay decision, a new or explicitly reused functional
authority, server mutation and replay/security rules, and approved combat/
progression design. No such authority should be inferred from the appearance
key.

## Q12: Is a functional Hero selector needed now?

No. The current RPG loop already has canonical Equipment, Spirit, Monster,
and settlement authorities, and none of those systems has Hero-specific
gameplay. A functional Hero selector would add authority and product surface
without a current gameplay consumer.

## Validation

All validation was non-mutating. No player database was opened for writes.

| Check | Result |
|---|---|
| Canonical inventory JSON parse and record count | PASS — target `20`, records `20`, unique IDs `20`. |
| Identity registry reconciliation | PASS — `10 player_characters + 10 new_player_character_concepts = 20`; union matches the canonical inventory IDs. |
| Runtime active-key reconciliation | PASS — `app.py ACTIVE_CHARACTER_KEYS = hero.html COMBAT_GEAR.character = 10`; all are present in the 20-ID matrix. |
| Legacy alias validation | PASS — 6 explicit aliases; every target is one of the 10 active keys; no alias is counted as a canonical content ID. |
| Asset/config validation | PASS — all 36 matrix asset paths exist; all 20 content records have source evidence; final-seven default-pose manifest contains 7 IDs and marks them presentation-only/runtime unchanged. |
| Duplicate Hero ID detection | PASS — no duplicate canonical IDs; no alias collides with a canonical 20-ID. |
| Functional consumer scan | PASS — no Hero key use in combat/Spirit/Map Battle consumers; equipment use is presentation-only; combat stats use `player_inventory`/`EQUIPMENT_DEFS`. |
| Existing Hero/asset focused pytest set | `30 passed`; 1 pre-existing failure in `tests/test_rpg_wave2_gate2_p3_wearable_production_runtime.py::test_all_runtime_overlays_and_masks_are_true_alpha_and_normalized` because the existing `go_stone_black` overlay file is absent. B029 did not modify that test, registry, or asset. |
| Runtime/static safety | PASS — `app.py`, runtime modules, schema, player data, frontend, and assets were not modified. |

## Decision packet

```text
RECOMMENDATION_A=KEEP_PRESENTATION_ONLY_FOR_V1
```

Keep the current `player_appearance.character_key` projection as
presentation-only for V1. Treat the three P1 IDs as inactive implemented
content and the seven final-seven IDs as content-only until their respective
visual/identity/runtime gates are explicitly closed. Do not create a
functional Hero identity authority until a Hero-specific gameplay consumer
and product rules exist.

This recommendation does not reject the 20-Hero content roster. It separates
content completeness from runtime registration and from functional authority,
which prevents a presentation key from silently becoming combat or
progression authority.

## Scope locks

```text
APP_PY_CHANGED=NO
RUNTIME_CHANGED=NO
SCHEMA_CHANGED=NO
PLAYER_DATA_MUTATED=NO
PRODUCTION_MUTATION=NO
DEPLOY=NO
MASTER_MERGE=NO
```
