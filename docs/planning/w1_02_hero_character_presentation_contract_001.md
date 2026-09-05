# W1-02 Hero / Character Presentation Contract

`TASK=W1_02_HERO_CHARACTER_PRESENTATION_CONTRACT_001`

`LANE=2`

`ASSIGNEE=CLAUDE`

`TASK_CLASS=CHARACTER_PRODUCT_COMPLETENESS_IMPLEMENTATION_PREP`

`PRIORITY=WAVE_1_PARALLEL`

`STATUS=AUTHORIZED_TO_EXECUTE`

`BASE=origin/master@616d51b17abe010de1e862382ca4db7bec65936f`

`BASE_TREE=f3882ecee3980d310817096e3a15bc469683e9cd`

`BRANCH=codex/w1-02-hero-character-presentation-contract-001`

`WORKTREE=D:\go-website-w1-02-hero-character-presentation-contract`

## Contract result

Wave 1 requires eight dedicated Zone 3–10 Lord presentation packages. Existing
Hero, Spirit, normal Monster, and Battlefield Boss assets are reused; no new
Hero, Companion, Spirit, normal Monster, or Battlefield Boss art is required to
make the Zone 3–10 presentation contract complete. The current generic Lord
emoji/placeholder cannot be accepted as final Lord presentation.

The standard Lord package is six slots, matching the Owner-provided Zone 2
package. Zones 3–9 therefore require 42 new runtime image slots. Zone 10 is a
narrative exception: `source_of_black_white_order` is a silent failed-world-order
mechanism, not an ordinary speaking character. It requires four story-state
visuals and explicitly does not require either Lord portrait slot. The Wave 1
new-production total is therefore **46 runtime image slots**:

* Zones 3–9: 7 Lord identities x 6 standard slots = 42.
* Zone 10: 1 mechanism identity x 4 story-state slots = 4.

No asset in this contract grants character selection, Spirit ownership,
equipment effects, combat authority, progression, rewards, or Lord/Battlefield
Boss equivalence.

The historical equipment number is reverified only at the registry-identity
level: there are 15 functional equipment IDs. Physical renderer evidence is
14 file-backed overlay assets because `go_stone_black` is explicitly
`INVENTORY_ONLY` / `NO_RUNTIME_OVERLAY` in the registry and its declared
overlay file is absent. The P3 manifest's `wearable_ready_with_mask=15` is
therefore not accepted as physical overlay evidence. This discrepancy remains
Wave 2 scope and is not repaired here.

## Authority and inspected surfaces

| Surface | Canonical source inspected | Authority boundary |
| --- | --- | --- |
| Hero appearance | `app.py` appearance endpoints; `hero.html`; `js/e9/adapters/player_state.js` | Server-owned `player_appearance.character_key`; the client resolves presentation only. |
| Hero world marker | `js/e9/world_stage.js`; `components/adventure/world_stage.html` | Consumes one resolved full-body image; it does not own the asset registry, unlocks, equipment, or appearance writes. |
| Spirit / Companion | `app.py` `PET_CATALOG` and pet routes; `hero.html` `PET_FRAME_SETS`; `docs/planning/e10_six_spirit_canonical_runtime_asset_manifest_a021a.json`; `deploy/canonical-image-pack-manifest.json` | Server-owned `user_pets` / `pet_collection` and active Spirit; visual adapter is presentation-only. No second Companion registry is permitted. |
| Lord presentation | `app.py` `ADVENTURE_BOSS_META`; `index.html` `#boss-cinematic`; `js/game/lord_trial_controller.js`; `docs/planning/e10_encounter_presentation_framework_a023.*` | Lord Trial is its own presentation surface and remains separate from generic Battlefield Boss presentation. |
| Normal Monsters | `docs/planning/art_003_batch_001_manifest.json` through `art_003_batch_011_manifest.json`; `art/monsters`; `assets/monsters` | Art admission is separate from runtime roster/mapping. This lane does not map new Monster IDs. |
| Battlefield Bosses | `docs/planning/art_production_master_board.*`; `assets/monsters` | Battlefield Boss is a separate current surface and is never a Lord-art substitute. |
| Wearables | `assets/hero/equipment/wearables/wearable_registry.json`; `docs/planning/rpg_wave2_gate2_p3_wearable_runtime_manifest.json`; `hero.html` | Inventory/equipped state and effects remain server-owned. This lane records dependencies only and does not enable the equipment loop. |

## Classification vocabulary

`STATE` is the verified asset/rendering state. `WAVE` identifies the product
wave that owns the remaining work or the explicit non-requirement. `GATE` is
only used when a style or narrative acceptance gate prevents production
acceptance.

* `CURRENT_FINAL`: the canonical asset package is present and accepted by its
  current source manifest for the inspected surface.
* `CURRENT_PARTIAL`: an asset or renderer exists, but the complete contract,
  cross-surface acceptance, runtime exposure, or owner gate is incomplete.
* `PLACEHOLDER`: a fallback, emoji, generic marker, or prototype is present;
  it is not production character art.
* `MISSING`: the required production asset/package is absent.
* `NOT_REQUIRED`: the current Wave 1 renderer does not require the variant.
* `BLOCKED_BY_WORLD_STYLE_LOCK`: an acceptance gate, not a substitute state;
  no generated or borrowed art may be used to bypass it.

## Current-vs-missing character presentation matrix

| Presentation item | Current evidence and exact finding | STATE | WAVE | Wave 1 effect | GATE |
| --- | --- | --- | --- | --- | --- |
| Hero base presentation | `hero.html` and `js/e9/adapters/player_state.js` expose exactly 10 current runtime keys: `apprentice`, `apprentice_girl`, `swordsman`, `rogue`, `ranger`, `berserker`, `guardian`, `paladin`, `mage`, `sage`, each using a `chibi_*_normalized.webp` asset. | `CURRENT_PARTIAL` | `WAVE_1` reuse; `WAVE_2` standardization | No new Hero art blocks the Zone map or generic encounter surface. The ten existing assets remain the only runtime Hero catalog in this lane. | — |
| Hero fallback | `CHARACTER_FALLBACK_ART` is `assets/hero/characters/chibi_reference_normalized.webp`; the same fallback is used on invalid/unavailable appearance data or image error. | `PLACEHOLDER` | `WAVE_1` safety behavior | Must remain a neutral failure fallback, never be reported as a character variant. | — |
| Gender / canonical variant support | `apprentice_girl` is a distinct canonical runtime key. There is no generic gender toggle and no runtime registration for the planned 20-character set. | `CURRENT_PARTIAL` | `WAVE_2` | Not a Wave 1 blocker; do not add a roster or selection path here. | — |
| Full-body presentation | Existing ten legacy files render as full-body-like chibi presentation. Six P1 packages and seven Final7 default-pose packages also exist as review artifacts, but they are not runtime-registered. The standardized Frame-A contract is therefore not complete for the 20-character plan. | `CURRENT_PARTIAL` | `WAVE_2` | Reuse the existing ten for Wave 1. No P1/Final7 runtime wiring in this lane. | Final7 owner visual pass is pending. |
| Directional variants | `js/e9/world_stage.js` consumes one `presentation.asset` and creates one 96x128 marker. No direction or locomotion state is requested by the current Hero/world contract. | `NOT_REQUIRED` | `WAVE_1` | No directional art is required for Zones 3–10 presentation. | — |
| Hero portrait variants | No distinct Hero portrait registry or portrait renderer exists; current Hero, preview, and map surfaces reuse the resolved full-body asset at different sizes. | `NOT_REQUIRED` | `WAVE_1`; optional `WAVE_3` | Do not create portrait files or a portrait authority for Wave 1. | — |
| Hero battle presentation | Generic encounter/battle surfaces consume the current player presentation and Monster identity; no Hero-specific attack, stance, or battle-state art is part of the current contract. | `CURRENT_PARTIAL` | `WAVE_1` reuse | No new Hero battle asset directly blocks Wave 1. | — |
| Hero victory / damage / reaction | `e10_encounter_presentation_framework_a023.*` provides committed-result feedback layers (`#impact-flash`, speech/result overlays, victory/KO/result presentation), but no Hero-specific reaction or damage animation asset contract. | `NOT_REQUIRED` | `WAVE_1`; optional `WAVE_3` | Keep feedback cosmetic and result-driven; no per-character reaction asset is required for Zone presentation. | — |
| Companion identity / catalog | `app.py` exposes exactly six canonical Spirit IDs and server-owned pet selection/ownership. No additional Companion identity is authorized. | `CURRENT_FINAL` | `WAVE_1` reuse | Reuse the active server-owned Spirit; do not create a second Companion catalog. | — |
| Spirit staged art | Six IDs and 18 stage records are physically present in the A021A manifest. `ink_drop_kelpie`, `whispering_void_kit`, and `star_shell_hatchling` have frame sets; `starpath_antlerling`, `fatty`, and `obsidian_bastion` have staged static WebP forms and currently fall back through `p.image` because no `PET_FRAME_SETS` base entry exists for them. | `CURRENT_PARTIAL` | `WAVE_1` reuse; `WAVE_2` animation parity | No new Spirit art blocks Wave 1. A missing Spirit asset must resolve to the same Spirit's neutral fallback, never another Spirit. | — |
| Zone 1–2 Lord presentation | Owner-provided production packages exist under `assets/e10/art/zone1/lord_trial` and `assets/e10/art/zone2/lord_trial`. Zone 2 establishes the six-slot standard: `LORD_RITUAL_KEY_ART`, `LORD_CHALLENGE_BACKPLATE`, `LORD_FAILURE_BACKPLATE`, `FIRST_STAR_SUCCESS_BACKPLATE`, `LORD_PORTRAIT`, `SUCCESS_LORD_PORTRAIT`. | `CURRENT_FINAL` | `WAVE_1` baseline | Reuse as the reference and renderer contract; do not alter existing Lord surfaces. | — |
| Zone 3–10 dedicated Lord presentation | No `assets/e10/art/zone3` through `zone10` Lord package exists. `index.html` still has a generic `#boss-cinematic-monster` slot with generic text/emoji behavior for these zones. | `MISSING` | `WAVE_1` | Direct blocker for final dedicated Lord character presentation. The world map/CTA can still show readiness, but the generic placeholder cannot pass the character presentation gate. | `BLOCKED_BY_WORLD_STYLE_LOCK` until Owner-approved Lord references/style are accepted. |
| Zone 3–10 Lord portraits | Required for the standard Lord package in Zones 3–9; absent. Zone 10 is explicitly `FACE=NONE`, `VOICE=NONE`, `DIALOGUE=NONE`, `PERSONALITY=NONE`, so both portrait slots are intentionally not required there. | `MISSING` for Z3–Z9; `NOT_REQUIRED` for Z10 | `WAVE_1` for Z3–Z9; `WAVE_1` exception for Z10 | Do not substitute Battlefield Boss art or invent a face for the Source. | `BLOCKED_BY_WORLD_STYLE_LOCK` for Z3–Z9; narrative lock governs Z10. |
| Normal Monster art | Exact recheck: 10 current runtime anchors in `assets/monsters` plus 110 canonical `art/monsters` files admitted by B01–B11 manifests = 120/120 canonical presentation assets. Zone 3–10 candidates are 87 IDs, grouped below. | `CURRENT_FINAL` asset admission; `CURRENT_PARTIAL` runtime exposure | `WAVE_1` reuse | No new Monster art production is required. Only 8 Zone 3–10 anchor IDs are currently runtime-mapped; this lane does not add mappings for the other 79 IDs. | — |
| Zone 3–10 Battlefield Boss art | Current mapped assets exist for `legacy_bf_03_boss` through `legacy_bf_10_boss`: `orc_shield_chibi.png`, `mist_dryad_chibi.png`, `bounty_warlord_chibi.png`, `dragon_oracle_chibi.png`, `archmage_lich_chibi.png`, `royal_knight_chibi.png`, `fate_deity_chibi.png`, `omega_idol_chibi.png`. Owner visual QA is not established by the current board. | `CURRENT_PARTIAL` | `WAVE_1` reuse | No new Boss art is required; Boss art must never be used as a Lord substitute. | — |
| Equipment / wearable rendering dependencies | `wearable_registry.json` verifies 15 functional item IDs, 1 `PLAYER_FRAME_A_STANDARD_CHIBI`, 6 reusable character masks, and 0 item-specific bespoke redraws. Physical recheck finds 14 file-backed overlay assets; `go_stone_black` is `INVENTORY_ONLY` / `NO_RUNTIME_OVERLAY` and its declared overlay file is absent. The P3 claim of 15 wearable-ready items is not physically verified. `hero.html` keeps `HERO_LEGACY_LOADOUT_EFFECTIVE=false` and disabled compatibility controls. | `CURRENT_PARTIAL` | `WAVE_2` | Not a Wave 1 dependency. Record only; do not enable shop, purchase, equip, loadout, or effect projection. | — |

## Zone 3–10 exact character dependency inventory

The Lord IDs and names below are copied from the current `app.py`
`ADVENTURE_BOSS_META` contract. They are Lord Trial identities, not the
separately listed Battlefield Boss identities.

| Zone | Current Lord key / name | Dedicated Lord art | Wave 1 package contract | Direct character blocker |
| --- | --- | --- | --- | --- |
| 3 | `goblin_centurion` / Goblin Centurion | Missing | Standard six slots | Yes |
| 4 | `misty_phantom_rabbit_king` / Misty Phantom Rabbit King | Missing | Standard six slots | Yes |
| 5 | `iron_orc_chieftain` / Iron Orc Chieftain | Missing | Standard six slots | Yes |
| 6 | `grand_temple_knight` / Grand Temple Knight | Missing | Standard six slots | Yes |
| 7 | `archmage_phantom` / Archmage Phantom | Missing | Standard six slots | Yes |
| 8 | `chaos_lord` / Chaos Lord | Missing | Standard six slots | Yes |
| 9 | `fallen_war_god_statue` / Fallen War-God Statue | Missing | Standard six slots | Yes |
| 10 | `source_of_black_white_order` / Source of Black-White Order | Missing | Four story-state slots; portraits intentionally omitted | Yes, but as a mechanism presentation, not a speaking character |

### Standard Lord package: Zones 3–9

Each package is keyed by the existing Lord key and zone. It must contain an
Owner-approved canonical source plus a runtime WebP derivative for each slot:

1. `LORD_RITUAL_KEY_ART` — Lord entrance / ritual / challenge-start visual.
2. `LORD_CHALLENGE_BACKPLATE` — Lord Challenge Card backplate.
3. `LORD_FAILURE_BACKPLATE` — failed trial / retraining result backplate.
4. `FIRST_STAR_SUCCESS_BACKPLATE` — success / recovery / reward result backplate.
5. `LORD_PORTRAIT` — challenge-card focal Lord portrait.
6. `SUCCESS_LORD_PORTRAIT` — success-card focal Lord portrait.

The package must preserve the existing Zone 1/2 delivery pattern: canonical
source evidence is retained, runtime WebP paths are explicit, dimensions and
hashes are recorded, and the page supplies labels/copy as DOM text. Do not
bake HP, attack, drops, rewards, progression, combat outcomes, or UI authority
into the art.

### Zone 10 mechanism package

`source_of_black_white_order` is governed by the screenplay contract, not by a
generic villain portrait. Its Wave 1 package is exactly:

1. `LORD_RITUAL_KEY_ART` — mechanism / temple-heart entry visual.
2. `LORD_CHALLENGE_BACKPLATE` — final confrontation setup visual.
3. `LORD_FAILURE_BACKPLATE` — failed or unresolved stabilization state.
4. `SOURCE_FINAL_STATE_ART` — final stabilization / post-resolution visual.

`LORD_PORTRAIT` and `SUCCESS_LORD_PORTRAIT` are `NOT_REQUIRED` for Zone 10.
`SOURCE_FINAL_STATE_ART` is a package-local semantic slot and must not be
treated as a new character registry or combat entity. The final art must obey
`FACE=NONE`, `VOICE=NONE`, `DIALOGUE=NONE`, `PERSONALITY=NONE`, and
`VILLAIN_SPEECH=NONE`.

### Normal Monster reuse list for Zones 3–10

These are the exact current candidate IDs and counts. They are a production
reuse list, not authorization to change runtime mapping:

| Zone | Current runtime anchor | Existing canonical art IDs to reuse | Count |
| --- | --- | --- | ---: |
| 3 | `M022` | `M022`, `M023`–`M033` | 12 |
| 4 | `M034` | `M034`–`M044` | 12 |
| 5 | `M046` | `M046`–`M055`, `M056`–`M057` | 12 |
| 6 | `M058` | `M058`–`M066`, `M067`–`M070` | 13 |
| 7 | `M071` | `M071`–`M077`, `M078`–`M083` | 13 |
| 8 | `M084` | `M084`–`M088`, `M089`–`M097` | 14 |
| 9 | `M098` | `M098`–`M099`, `M100`–`M109`, `M110`–`M111` | 14 |
| 10 | `M112` | `M112`, `M113`–`M120` | 9 |
| **Total** | **8 mapped anchors** | **87 current canonical IDs** | **87** |

The 8 anchor assets are current runtime presentation. The other 79 Zone 3–10
IDs have canonical admitted art but are not runtime-mapped by this lane. Any
request to expose those IDs in gameplay remains a separate server/runtime
authority gate.

## Wave 1 implementation-ready production list

### New production required

| Work item | Exact deliverable | Quantity | State / wave | Acceptance condition |
| --- | --- | ---: | --- | --- |
| Z3 Lord package | `goblin_centurion`, six standard slots | 6 WebP runtime derivatives plus source evidence | `MISSING`, `WAVE_1` | Owner-approved character/style reference; package keys, dimensions, and hashes recorded. |
| Z4 Lord package | `misty_phantom_rabbit_king`, six standard slots | 6 | `MISSING`, `WAVE_1` | Same standard package contract. |
| Z5 Lord package | `iron_orc_chieftain`, six standard slots | 6 | `MISSING`, `WAVE_1` | Same standard package contract. |
| Z6 Lord package | `grand_temple_knight`, six standard slots | 6 | `MISSING`, `WAVE_1` | Same standard package contract; preserve the screenplay's nonlethal fate. |
| Z7 Lord package | `archmage_phantom`, six standard slots | 6 | `MISSING`, `WAVE_1` | Same standard package contract. |
| Z8 Lord package | `chaos_lord`, six standard slots | 6 | `MISSING`, `WAVE_1` | Same standard package contract; dissolution is presentation/story state, not Hero kill authority. |
| Z9 Lord package | `fallen_war_god_statue`, six standard slots | 6 | `MISSING`, `WAVE_1` | Same standard package contract; the statue is not a defeated combat drop source. |
| Z10 mechanism package | `source_of_black_white_order`, four story-state slots, no portraits | 4 | `MISSING`, `WAVE_1` | Owner-approved mechanism visual obeys the silent `FACE/VOICE/DIALOGUE/PERSONALITY` lock. |
| **Total** | **Dedicated Zone 3–10 Lord / mechanism presentation** | **46 runtime slots** | **`WAVE_1`** | **All packages pass visual, decode, path, and authority-boundary review.** |

### Reuse and explicit no-production items

* Hero: reuse the current ten runtime character assets. No new gender,
  direction, portrait, victory, damage, or reaction asset is required for the
  Wave 1 Zone presentation surface.
* Companion / Spirit: reuse the six server-canonical Spirit IDs and staged
  assets. The active follower must come from server state; no new Companion
  art or registry is created.
* Normal Monsters: reuse the 87 current Zone 3–10 canonical IDs listed above.
  Do not add runtime mappings in this contract.
* Battlefield Bosses: reuse the eight current Zone 3–10 Boss assets. Never
  route them through the Lord Trial art slot.
* Equipment: no Wave 1 asset production or rendering activation is required.
  The 15-item registry is recorded as a verified Wave 2 dependency only.

### Wave 1 art package acceptance

For every new Lord package, the owner-facing review must verify:

1. The asset is keyed to the existing zone/Lord identity; no new authority ID
   is invented.
2. Canonical source evidence and runtime WebP derivative are both retained;
   dimensions, color mode, and SHA-256 are recorded.
3. Missing/decode failure resolves to a neutral same-identity fallback or a
   hidden unavailable state; it never substitutes a different Monster, Boss,
   Lord, or Spirit and never retries forever.
4. DOM copy supplies labels, numbers, rewards, and result state. Art remains
   presentation-only.
5. `LORD_TRIAL` remains separate from `BATTLEFIELD_BOSS` in identifiers,
   renderer selection, and review evidence.
6. No changes are made to `app.py`, `index.html`, `i18n.js`, `sw.js`, shop
   authority, equipment purchase authority, loadout authority, or combat
   resolution.

## Wave 2 deferred

All items below are intentionally outside Wave 1 and remain `WAVE_2`:

* Runtime admission/selection for the three P1 non-runtime identities
  (`trail_apprentice`, `night_runner`, `constellation_apprentice`) and the
  seven Final7 default-pose candidates (`river_wayfinder`,
  `stone_caretaker`, `duelist_scout`, `bastion_warden`, `forest_pathfinder`,
  `archive_scholar`, `worldkeeper`).
* Owner visual acceptance and shared Frame-A standardization for the planned
  20-character set, including the remaining legacy identities
  (`apprentice_girl`, `swordsman`, `rogue`, `ranger`, `berserker`, `guardian`,
  `sage`) whose current files are not a complete standardized package.
* One-hand sword family proofs and any later staff/bow/heavy pose families;
  `wooden_sword`, `iron_sword`, and `fox_fang` remain family reuse, not three
  separate character redraw obligations.
* Full animation frame parity and cross-surface acceptance for the three new
  staged Spirits if product requirements later demand animated treatment.
* Wearable compositor rollout: the reverified 15-item registry, 14 physical
  overlay files, one body frame, six masks, and zero bespoke redraws remain a
  Wave 2 implementation dependency. `go_stone_black` remains inventory-only
  until its physical/runtime treatment is owner-resolved. This contract does
  not enable shop, purchase, equip, loadout, or effects.

## Wave 3 deferred

The following are optional future presentation work and are not Wave 1
acceptance blockers:

* Direction-specific, locomotion-specific, battle-state, victory, damage, or
  reaction variants for Hero characters where a future concrete renderer needs
  them.
* Distinct Hero portrait registry and bespoke character cinematics.
* Lord/Boss defeat-state, reaction, collection, or alternate-portrait packs
  beyond the Zone 3–10 story package, after the Lord style and runtime gates
  are accepted.
* Additional Companion identities or non-canonical Spirit substitutes. Any
  future identity needs a separate owner-approved canonical source and
  server-authority review.

## Blocked by world style lock

* Zone 3–9 Lord packages are `MISSING` and `BLOCKED_BY_WORLD_STYLE_LOCK` until
  Owner-approved references establish the Lord-specific visual language. The
  existing normal Monster style lock and admitted Monster art do not satisfy
  this Lord gate.
* Zone 10 portrait art is intentionally `NOT_REQUIRED`; the screenplay's
  silent mechanism contract is the binding narrative/style lock. Do not draw
  a face, mouth, speaking pose, or villain reaction to fill a generic slot.
* Final7 Hero art remains a `CURRENT_PARTIAL` owner-review candidate. Its
  `FINAL7_DEFAULT_POSE_OWNER_PASS=NOT_PRESENT` state blocks Wave 2 runtime
  admission, not Wave 1 Zone presentation.
* Existing B01–B11 normal Monster package manifests provide the current art
  admission evidence. The older aggregate `art_production_master_board.*`
  still contains stale lower completion metrics; this lane does not rewrite
  that broad board. The exact per-batch manifests and physical tree are the
  evidence used here.

## Non-goals and authority safeguards

* `Lord != ordinary Battlefield Boss` is preserved in all package keys and
  review gates.
* Character and Spirit art is presentation-only. It cannot create damage,
  rewards, drops, unlocks, progression, leaderboard eligibility, or combat
  outcomes.
* No new character, Spirit, Monster, Boss, Lord, equipment, or shop authority
  registry is created by this contract.
* No equipment/shop/loadout activation loop is started.
* No shared shell file is changed. This lane owns this planning contract only.

## Acceptance state

`EXACT_WAVE_1_CHARACTER_PRODUCTION_LIST=YES`

`NO_DUPLICATE_CHARACTER_AUTHORITY=YES`

`LORD_SEPARATE_FROM_BATTLEFIELD_BOSS=YES`

`COSMETIC_PRESENTATION_CREATES_COMBAT_AUTHORITY=NO`

`EQUIPMENT_SHOP_LOADOUT_ENABLED=NO`

`SHARED_SHELL_CONFLICT=NO`

`READY_FOR_CHARACTER_ACCEPTANCE=YES`

`STATUS=READY_FOR_OWNER_CHARACTER_ACCEPTANCE; IMPLEMENTATION_STOPPED_AT_CONTRACT`
