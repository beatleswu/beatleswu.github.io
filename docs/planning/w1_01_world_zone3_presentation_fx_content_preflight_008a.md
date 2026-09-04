# W1-01 WORLD — Zone 3 Presentation FX Content Preflight 008A

**TASK:** `W1_01_WORLD_ZONE3_PRESENTATION_FX_CONTENT_AND_ASSET_PREFLIGHT_008A`
**ASSIGNEE:** Codex
**TASK CLASS:** `WORLD_PRESENTATION_CONTENT_PREFLIGHT`
**SOURCE WORLD HEAD:** `39c587a216f6cc13efe572066d9d8f0299960f1b`
**SOURCE WORLD TREE:** `676da3ddd4456b83aaa591e830a7adf4dab5c161`
**JOURNEY REFERENCE HEAD:** `f77bce46302974c8a8aa9d296ae0ea548a707691`
**JOURNEY REFERENCE ONLY:** `YES`
**OWNER STYLE:** `B — STYLIZED_ADVENTURE`
**CURRENT ZONE IDENTITY:** `k16_20 / 哥布林洞穴 / Goblin Cave`
**ARTWORK GENERATION:** `NOT_PERFORMED`
**RUNTIME BINDING:** `NOT_PERFORMED`

This is a content and asset preflight. The machine-readable cue sheet is
`w1_01_world_zone3_presentation_fx_cue_manifest_008a.json`. It defines later
audio/compositor inputs without adding playback, trigger, timing, or authority
code.

## 1. Audit result

### Existing Zone 1 and Zone 2 vocabulary

| Surface | Current evidence | Classification |
|---|---|---|
| Zone 1 ambience | One locked ambience: `assets/e10/audio/zone1/ambience/zone1_ambience_village_dawn.mp3` | `PRESENT`; settlement-specific, not a Zone 3 bed |
| Zone 1 SFX | Four locked cinematic SFX in `assets/e10/audio/zone1/sfx/` | `PRESENT`; only stone placement is a safe Zone 3 candidate |
| Zone 1 VFX | No dedicated Zone 1 VFX asset package found | `NO_DEDICATED_ASSET`; shared CSS/DOM presentation mechanisms exist |
| Zone 2 ambience | Four manifest-category ambience assets, including the hive and bee-distance layer | `PRESENT`; Zone 2 identity remains protected |
| Zone 2 SFX | Ten manifest-category SFX assets | `PRESENT`; creature/Lord-specific assets are not Zone 3 reuse |
| Zone 2 VFX | No dedicated Zone 2 VFX asset package found | `NO_DEDICATED_ASSET`; existing cinematic/compositor mechanisms are shared patterns only |

The current Zone 2 bee audio paths are:

- `assets/e10/audio/zone2/sfx/zone2_ambient_bee_distant.mp3`
- `assets/e10/audio/zone2/sfx/zone2_sfx_bee_close.mp3`

Their role is `AMBIENT_SWARM_PRESSURE_ONLY`. The current runtime authority and
focused test identify the accepted Zone 2 boss presentation as the Slime Swarm
Lord, not bee humanoid art. No dedicated bee visual asset or bee-specific visual
effect was found in the inspected Zone 2/runtime surfaces. Bee audio and any
bee visual treatment remain Zone 2 content and are explicitly not reused here.

### Current Zone 3 coverage

| Surface | Result |
|---|---|
| Zone 3 ambience assets | `NO`; `assets/e10/audio/zone3/` is absent |
| Zone 3 event SFX assets | `NO`; no admitted Zone 3 SFX root exists |
| Zone 3 VFX assets | `NO` dedicated Zone 3 VFX package; later effects are code-only proposals |
| Zone 3 Shui audio assets | `NO`; the only reusable candidate is the existing Zone 2 Shui reaction SFX |
| Zone 3 transition assets | `NO`; the Zone 4 atmospheric bridge is a new audio placeholder plus code-only fog |
| Static cinematic art | Present, but excluded from this SFX/VFX audit |

The existing approved art package remains unchanged. No fog, particles, light,
glow, UI, text, route, reward, state, or new character pixels are added to any
ten-shot source master. `SHOT09` remains an ordinary, irregular Stone Shard with
natural marks only.

## 2. Production classification

### Audio evaluation

All fifteen requested audio concepts are evaluated below. `SAFE_REUSE` means an
existing file may be auditioned and reused only in the stated bounded role.

| ID | Decision | Classification / delivery |
|---|---|---|
| `CAVE_ROOM_TONE` | `REQUIRED` | `NEW_ASSET_REQUIRED`; Zone 3 cave bed |
| `DISTANT_CAVE_WIND` | `REQUIRED` | `NEW_ASSET_REQUIRED`; cave-mouth/depth wind |
| `WATER_DRIP` | `REQUIRED` | `NEW_ASSET_REQUIRED`; intermittent cave water |
| `REFUGEE_FOOTSTEPS` | `REQUIRED` | `NEW_ASSET_REQUIRED`; families retreat deeper |
| `BELONGINGS_MOVEMENT` | `REQUIRED` | `NEW_ASSET_REQUIRED`; household objects, not loot |
| `DISTANT_FAMILY_ACTIVITY` | `REQUIRED` | `NEW_ASSET_REQUIRED`; low nonverbal settlement life |
| `SHUI_WATER_SPIRIT_SOUND` | `REQUIRED` | `SAFE_REUSE`; `assets/e10/audio/zone2/sfx/zone2_sfx_shui_reaction_2.mp3` |
| `ROCKFALL` | `REQUIRED` | `NEW_ASSET_REQUIRED`; Shot 05 collapse |
| `BLOCKED_WATER_FLOW` | `REQUIRED` | `NEW_ASSET_REQUIRED`; audible but unreachable water |
| `CENTURION_ARMOR` | `REQUIRED` | `NEW_ASSET_REQUIRED`; grounded protector arrival |
| `CENTURION_SPEAR_PLANT` | `REQUIRED` | `NEW_ASSET_REQUIRED`; physical boundary event |
| `TRIAL_TENSION_AMBIENCE` | `REQUIRED` | `NEW_ASSET_REQUIRED`; stillness, not horror |
| `FRAGILE_TRUCE_AMBIENCE` | `REQUIRED` | `NEW_ASSET_REQUIRED`; quiet guarded peace |
| `STONE_SHARD_PHYSICAL_HANDOFF` | `REQUIRED` | `SAFE_REUSE`; `assets/e10/audio/zone1/sfx/zone1_sfx_shot07_stone_placement.mp3` |
| `MISTY_FOREST_WIND_TRANSITION` | `REQUIRED` | `NEW_ASSET_REQUIRED`; natural Zone 4 bridge |

No existing Zone 1/2 BGM, bee audio, hive bed, slime movement, or Lord event is
promoted to Zone 3. The reusable Stone Shard sound is physical contact only; it
does not imply magic, a map, a rune, a reward, or gameplay authority.

### Visual FX evaluation

The twelve requested visual treatments are content decisions, not new raster
assets. They are specified for later low-cost compositor/DOM/CSS implementation.

| ID | Decision | Delivery constraint |
|---|---|---|
| `CAVE_DUST_MOTES` | `REQUIRED` | Sparse bounded depth motes |
| `SUBTLE_WARM_LIGHT_FLICKER` | `REQUIRED` | Low-amplitude light opacity variation |
| `WATER_REFLECTION_SHIMMER` | `REQUIRED` | Small bounded water overlay |
| `SHUI_WATER_PARTICLES` | `REQUIRED` | Sparse nonverbal Shui support; no combat aura |
| `SHUI_TRANSLUCENT_PULSE` | `OPTIONAL` | Single low-opacity response only |
| `ROCK_DUST_FALL` | `REQUIRED` | Finite Shot 05 burst |
| `SMALL_ROCK_DEBRIS` | `REQUIRED` | Finite grounded transform burst |
| `BLOCKED_WATER_MIST` | `REQUIRED` | Low-opacity mist at unreachable water |
| `CENTURION_SPEAR_DUST_IMPULSE` | `REQUIRED` | Physical boundary contact; no demonic aura |
| `TRIAL_SUBTLE_ENVIRONMENT_TENSION` | `REQUIRED` | Slow environmental variation; no shake/flash |
| `TRUCE_ENVIRONMENT_CALMING` | `REQUIRED` | Finite settling; no celebration |
| `MISTY_FOREST_FOG_TRANSITION` | `REQUIRED` | Bounded cool crossfade; no route/state signal |

`VFX` count in the report excludes the separately categorized warm-light cue and
the separately categorized Zone 4 transition cue: nine required VFX treatments,
one optional VFX treatment, one required `LIGHT`, and one required `TRANSITION`.

## 3. Shot cue sheet

The JSON manifest contains one record per cue with the required content fields
and the later-binding fields. `RUNTIME_TRIGGER_CODE` is intentionally the fixed
value `NOT_DEFINED_IN_008A` for every cue.

| Cue | Shot(s) | Category | Evaluation | Intensity | Loop | Asset / placeholder |
|---|---|---|---|---|---:|---|
| `Z3_A01` | 01–10 | `AMBIENCE` | Cave room tone | LOW | yes | new audio placeholder |
| `Z3_A02` | 01,03,05,06,10 | `AMBIENCE` | Distant cave wind | LOW | yes | new audio placeholder |
| `Z3_A03` | 01,04,06,08 | `AMBIENCE` | Distant family activity | LOW | yes | new audio placeholder |
| `Z3_A04` | 07 | `AMBIENCE` | Trial tension | MEDIUM | yes | new audio placeholder |
| `Z3_A05` | 08 | `AMBIENCE` | Fragile truce | LOW | yes | new audio placeholder |
| `Z3_S01` | 01 | `SFX` | Refugee footsteps | MEDIUM | no | new audio placeholder |
| `Z3_S02` | 02 | `SFX` | Belongings movement | LOW | no | new audio placeholder |
| `Z3_S03` | 03,04,05 | `SFX` | Water drip | LOW | no | new audio placeholder |
| `Z3_S04` | 03,05,08 | `SFX` | Shui water-spirit sound | LOW | no | existing Shui reaction |
| `Z3_S05` | 05 | `SFX` | Rockfall | HIGH | no | new audio placeholder |
| `Z3_S06` | 05 | `SFX` | Blocked water flow | LOW | yes | new audio placeholder |
| `Z3_S07` | 06 | `SFX` | Centurion armor | MEDIUM | no | new audio placeholder |
| `Z3_S08` | 07 | `SFX` | Centurion spear plant | MEDIUM | no | new audio placeholder |
| `Z3_S09` | 09 | `SFX` | Stone Shard physical handoff | LOW | no | existing stone placement |
| `Z3_L01` | 01–10 | `LIGHT` | Subtle warm light flicker | LOW | yes | code-only light |
| `Z3_V01` | 01–10 | `VFX` | Cave dust motes | LOW | yes | code-only VFX |
| `Z3_V02` | 05 | `VFX` | Water reflection shimmer | LOW | yes | code-only VFX |
| `Z3_V03` | 03,05,08 | `VFX` | Shui water particles | LOW | yes | code-only VFX |
| `Z3_V04` | 03,05,08 | `VFX` | Optional Shui translucent pulse | LOW | yes | code-only VFX |
| `Z3_V05` | 05 | `VFX` | Rock dust fall | MEDIUM | no | code-only VFX |
| `Z3_V06` | 05 | `VFX` | Small rock debris | LOW | no | code-only VFX |
| `Z3_V07` | 05 | `VFX` | Blocked water mist | LOW | yes | code-only VFX |
| `Z3_V08` | 07 | `VFX` | Centurion spear dust impulse | MEDIUM | no | code-only VFX |
| `Z3_V09` | 07 | `VFX` | Trial environment tension | LOW | yes | code-only VFX |
| `Z3_V10` | 08 | `VFX` | Truce environment calming | LOW | no | code-only VFX |
| `Z3_T01` | 10 | `TRANSITION` | Misty Forest wind + fog transition | LOW | no | new audio + code-only fog |

Counts:

- `ZONE3_REQUIRED_AMBIENCE_COUNT=5`
- `ZONE3_REQUIRED_EVENT_SFX_COUNT=9`
- `ZONE3_REQUIRED_VFX_COUNT=9`
- `ZONE3_REQUIRED_TRANSITION_COUNT=1`
- `ZONE3_TOTAL_PRESENTATION_CUE_COUNT=26` (including one optional VFX and one required LIGHT)

## 4. Reuse and production inputs

The exact machine manifest records the full classification inventory. The bounded
counts are:

| Count | Value | Meaning |
|---|---:|---|
| `REUSABLE_AUDIO_ASSET_COUNT` | 2 | Stone placement and Shui reaction only |
| `REUSABLE_VFX_ASSET_COUNT` | 0 | No dedicated Zone 1/2 VFX asset admitted |
| `NEW_AUDIO_ASSET_COUNT_REQUIRED` | 13 | Fifteen evaluated audio concepts minus the two safe reuses |
| `NEW_VFX_ASSET_COUNT_REQUIRED` | 0 | All visual FX are code-only treatments, not new raster inputs |
| `CODE_ONLY_VFX_COUNT` | 12 | The twelve evaluated visual treatments, including light/fog entries |

New audio placeholders use the established `assets/e10/audio/zone3/` family. No
placeholder is an admitted runtime file until separately produced, reviewed,
and integrated under the later audio/runtime gate.

## 5. Story, character, and authority contract

- Grik remains a young, cautious person; no monstrous treatment.
- The Centurion remains a protector setting a boundary; no demonic aura or
  attack-state effect.
- Shui remains nonverbal. Its sound and water FX are reaction/presence cues, not
  speech, subtitles, or gameplay effects.
- The fragile truce is quiet and guarded. There is no cheer, victory swell,
  confetti, reward flash, or celebratory FX.
- The Stone Shard is ordinary, non-glowing, irregular, and marked naturally.
  `STONE_SHARD_MAGICAL_SFX_COUNT=0` and `STONE_SHARD_MAGICAL_VFX_COUNT=0`.
- `MONSTER < ELITE < BATTLEFIELD BOSS < LORD` remains a presentation hierarchy
  only. Battlefield Boss and Lord surfaces are not conflated.
- No cue creates Zone clear, unlock, reward, item consumption, Lord eligibility,
  payment, Shop, Loadout, or combat authority.

## 6. Device and accessibility contract

`LOW_END_DEVICE_SAFE_DESIGN=YES`.

- Desktop keeps the 16:9 three-layer read with sparse overlays.
- iPad landscape preserves lateral route and subject lanes while capping
  particles.
- iPad portrait and mobile portrait prefer static depth and low-opacity overlays;
  they do not rely on side-only motion to explain the story.
- Reduced motion disables particles, pulses, camera push, screen shake, and
  repeated flashes; it freezes or simplifies flicker, shimmer, and fog while
  retaining the static story context.
- No critical identity, route, state, dialogue, reward, or feedback is conveyed
  only by sound, color, motion, or darkness. Captions/transcripts remain a later
  shell/runtime responsibility where audio is meaningful.
- No heavy WebGL requirement, large continuous emitter, large blur filter, or
  unbounded animation accumulation is specified.

## 7. Journey handoff and boundaries

`READY_FOR_JOURNEY_RUNTIME_BINDING=YES` means the machine-readable content
contract is complete for a later binding task. It does not mean runtime binding
was implemented here. The referenced Journey head is not merged, cherry-picked,
or modified.

This preflight changes only:

- `docs/planning/w1_01_world_zone3_presentation_fx_content_preflight_008a.md`
- `docs/planning/w1_01_world_zone3_presentation_fx_cue_manifest_008a.json`
- `tests/test_w1_01_zone3_presentation_fx_preflight.py`

It does not modify `app.py`, `index.html`, `i18n.js`,
`js/game/cinematic_replay.js`, `sw.js`, Journey runtime files, existing art/audio,
the DB, or any gameplay/economy/payment authority.

Physical-device acceptance remains `REQUIRED_LATER`.
