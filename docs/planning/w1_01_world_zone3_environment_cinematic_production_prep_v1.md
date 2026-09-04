# W1-01 WORLD — Zone 3 Environment and Cinematic Production Prep V1

**Task:** `W1_01_WORLD_ZONE3_ENVIRONMENT_CINEMATIC_PRODUCTION_PREP_005`
**Swarm round:** `W1_R2_ZONE3_VERTICAL_SLICE`
**Base candidate:** `4a6d66f9df4c305811f8782f689f637b66952a27`
**Owner style:** `B — STYLIZED_ADVENTURE`
**Canonical Zone:** `3 / k16_20 / 哥布林洞穴 / Goblin Cave`
**Production status:** `PREPARED_FOR_OWNER_VISUAL_PRODUCTION`
**Artwork generation:** `NOT_PERFORMED`

This package defines the WORLD-owned environment and background work needed for
the Zone 3 vertical slice. It is a production contract, not an art admission,
runtime patch, screenplay rewrite, or gameplay change. The exact machine-readable
slot list and image-generation queue are in
`w1_01_world_zone3_environment_cinematic_asset_manifest_v1.json`.

## 1. Authority and hard boundaries

The current runtime/API identity remains the source of truth:

| Field | Current value |
|---|---|
| Zone key | `k16_20` |
| Zone number | `3` |
| Chinese name | `哥布林洞穴` |
| English name | `Goblin Cave` |
| Stage / band | `LV3 / 16–20級` |
| Lord key | `goblin_centurion` |
| Lord identity | `哥布林百夫長 / Goblin Centurion` |
| Zone clear authority | Existing server-owned Adventure authority |

This package preserves the following boundaries:

- `TEXT_NOT_BAKED_INTO_BASE_IMAGE=YES`
- `ROUTE_NOT_BAKED_INTO_BASE_IMAGE=YES`
- `STATE_NOT_BAKED_INTO_BASE_IMAGE=YES`
- `REWARD_NOT_BAKED_INTO_BASE_IMAGE=YES`
- World art never creates a Monster, Battlefield Boss, Lord, clear, unlock,
  star, reward, equipment, loadout, payment, or progression decision.
- `Battlefield Boss != Lord`. The Lord background slots are separate from any
  generic Battlefield Boss presentation and contain no Lord character art.
- No face, voice, dialogue, route label, state label, reward label, or UI copy
  is authored into a base image.
- The story object is the canonical `STONE SHARD`. “Stone-mark relic” is the
  request-scope description only; it is not a new runtime object or label.
- The Zone 4 hook is environmental and historical. The Stone Shard does not
  glow, point, navigate, unlock, or grant anything.

## 2. Existing WORLD assets and continuity material

The following are reusable as evidence, delivery-pattern references, or shared
runtime surfaces. They are not silently promoted to final Zone 3 art.

| Existing surface | Classification | Reuse in this package | Boundary |
|---|---|---|---|
| `assets/maps/e10_world_stage_v1_base.webp` | `EXISTING_CANONICAL` | Existing map-stage canvas and depth/layout baseline | No map-stage replacement or shell change |
| `assets/maps/e10-vs1f-landmarks/zone-03-goblin-cave.webp` | `EXISTING_BUT_INCOMPLETE` | Visual reference and fallback evidence for the cave landmark | No admission as final; future rebind is separately gated |
| `assets/e10/ui/e10-ui-assets.json` | `EXISTING_CANONICAL` | Shared number frame, lock, selection, completion, progress, and player-marker vocabulary | Art never duplicates or invents state indicators |
| `assets/e10/art/zone1/lord_trial/` | `EXISTING_CANONICAL` delivery reference | Backplate/key-art separation, transparent semantic UI boundary, WebP runtime derivative pattern | Do not copy Zone 1 setting or character art |
| `assets/e10/art/zone2/lord_trial/` | `EXISTING_CANONICAL` delivery reference | 4:3 challenge/failure/success backplate pattern and separate ritual/portrait surfaces | Do not copy Zone 2 setting, Lord, or character art |
| `assets/storyboards/e10_z2_shot01.webp`–`e10_z2_shot10.webp` | `REFERENCE_ONLY` for Zone 3 pixels | Ten-shot production mapping and 16:9 storyboard delivery precedent | No Zone 2 image is a Zone 3 source |
| `components/adventure/world_stage.html` | `EXISTING_CANONICAL` | Current map landmark/details slots, including 320×320 display box | No HTML change in this task |
| `js/e9/world_stage.js` | `EXISTING_CANONICAL` | Current server-projected map contract and landmark lookup boundary | No landmark rebind in this task |
| `js/game/cinematic_replay.js` | `EXISTING_CANONICAL` | Zone-agnostic lifecycle/replay contract | No cinematic runtime code change |
| `docs/planning/e10_final_screenplay_v1.md` | `EXISTING_BUT_INCOMPLETE` production authority | Zone 3 Shots 1–10 visual roles and protected story beats | No dialogue or gameplay rewrite |
| `docs/planning/w1_01_world_style_b_lock_and_zone_content_production_v1.md` | `EXISTING_CANONICAL` for this prep | Direction B grammar and Zone 3 style spec | No style reopening |

There is currently no admitted Zone 3 environment or Zone 3 audio directory in
the candidate worktree. The production roots below are therefore proposed
future roots only:

- Review source: `tools/e10_world_zone_art_review/zone3/`
- Canonical source: `assets/e10/art/zone3/`
- Runtime derivative: `assets/e10/art/zone3/**/*.webp`

## 3. Zone 3 visual lock

Zone 3 is a bright, inhabited limestone cave where the player first learns that
the apparent enemy is retreating rather than raiding. The cave should feel
occupied, defended, and resourceful. It is not a horror dungeon, a loot room,
or a destroyed settlement.

### Shared Direction B grammar

- Stylized adventure-RPG illustration with tactile, simplified forms.
- Clear foreground / midground / background separation in value and silhouette.
- Limestone cream and warm lantern amber are the first read; charcoal teal,
  moss green, copper, and damp blue-gray provide controlled contrast.
- Friendly readability survives grayscale conversion. No identity may depend
  only on saturation, darkness, a glow, or audio.
- Use practical materials first: worn limestone, packed dust, rope, wood,
  metal lanterns, storage baskets, mineral dampness, and hand-built routes.
- Allow mild cartoon stylization in generic distant silhouettes only where a
  future compositor supplies them. This WORLD package supplies no Monster or
  Lord pixels.
- Keep the cave approachable rather than grimdark. No gore, photorealism,
  muddy low contrast, blacked-out recesses, generic cinematic realism, or
  monochromatic purple endgame language.

### Three-layer composition contract

1. **Background:** cavern scale, cave-mouth depth, distant mineral shafts,
   settlement silhouette, or the reserved last door.
2. **Midground:** route, supplies, lantern pools, storage alcoves, rope bridge,
   cave wall, board-wall reveal, or open passage.
3. **Foreground:** empty subject bays for Hero/Companion/Grik/Centurion layers,
   one practical prop, and one restrained depth cue. The art must never bake
   those characters into the World plate.

### Material and motion contract

- Warm lantern pools oppose cool cave shafts without horror blackout.
- Ambient motion, if later animated, is limited to lantern hiss, drifting dust,
  a small mist thread, rope sway, or settling grit. It must not obscure the
  subject bays, cave landmark, Stone Shard, or semantic UI.
- Reduced motion removes camera push, parallax sweeps, particle bursts, rapid
  flicker, and nonessential environmental loops while leaving all visible
  identity and state context intact.

## 4. New WORLD asset slots

All slots below are `NEW_PROPOSED_NOT_GENERATED` unless marked `DERIVED` or
`CONDITIONAL`. Every slot has one master composition and a planned runtime WebP
derivative. The master is the Owner/ChatGPT review source; no runtime derivative
is created by this task.

### 4.1 Slot table

| Asset ID | Purpose | Scene / coverage | Character placement | Camera | Lighting | Palette | Ratio / master | Expected runtime path |
|---|---|---|---|---|---|---|---|---|
| `Z3_MAP_LANDMARK` | Replace the incomplete map landmark after visual acceptance | Cave mouth, amber-lit descent, occupied alcoves, a reserved deeper door; legible at map-card scale | No character pixels; reserve center for node overlay and lower-right for current-player marker | Square, slightly elevated three-quarter establishing view; cave mouth and route form one readable silhouette | Warm mouth/lantern key, cool inner-cave fill, soft edge separation | Limestone cream, charcoal teal, lantern amber, moss green, copper | `1:1`, `1536×1536` | `/assets/e10/art/zone3/environment/zone3_map_landmark.webp` |
| `Z3_ENTRY_ENVIRONMENT` | Zone-entry backplate and Shot 1 cave-mouth reveal | Goblins have just fled with supplies; open cave mouth, broken route, lantern trail, no ambush staging | Empty center subject bay at x=50%; left/rear route bay for future fleeing silhouettes; no named characters | 16:9 wide, mild handheld-feel composition but no baked motion blur | Torch/lantern flicker against cool dawn-like cave spill; readable darks | Limestone cream, amber, moss green, damp blue-gray, restrained berry red | `16:9`, `2048×1152` | `/assets/e10/art/zone3/entry/zone3_entry_backplate.webp` |
| `Z3_CAVE_PRIMARY_ENVIRONMENT` | Primary Zone 3 environment for gameplay context and Shots 2–4 | Inhabited chamber, storage alcoves, rope route, fading supply trail, practical cave wall | Hero/Companion foreground bays; Grik eye-level bay at x=68%; no character pixels | 16:9 medium-wide, eye-level, stable; route leads inward without tunnel collapse | Lantern pools, cool overhead shaft, soft bounce on limestone; no blackout | Limestone cream, charcoal teal, amber, moss green, copper | `16:9`, `2048×1152` | `/assets/e10/art/zone3/environment/zone3_environment_master.webp` |
| `Z3_BOARD_WALL_REVEAL` | Zone core image for Shot 5 | Cracked natural cave wall whose stone spacing reads as a found Go-board pattern; surrounding settlement remains visible | Empty Hero hand/face bay; no constructed board, no Hero or Grik pixels | 16:9 slow-push composition, wall centered but not full-frame; preserve edge context | Narrow shaft catches cracks; ambient amber remains; no magical glow | Pale limestone, charcoal cracks, mineral blue-gray, restrained amber | `16:9`, `2048×1152` | `/assets/e10/art/zone3/cinematic/zone3_shot05_board_wall_reveal.webp` |
| `Z3_LORD_APPROACH_BACKGROUND` | Boss-ready / last-door approach background for Shots 6–7 | Reserved last door, planted-spear ground point, quiet passage, tension through stillness | Empty Centurion bay x=66%, Hero bay x=36%; WORLD supplies only the door, floor, and depth | 16:9 level-angle, symmetrical enough for recognition but not a generic boss card | Lantern pools narrow toward the door; soft rim on stone; tension is stillness, not darkness | Charcoal teal, limestone cream, copper, low amber, damp blue-gray | `16:9`, `2048×1152` | `/assets/e10/art/zone3/cinematic/zone3_shot06_last_door_approach.webp` |
| `Z3_FRAGILE_TRUCE_BACKPLATE` | Post-clear and fragile-truce presentation for Shot 8 | Passage opened without destruction; supplies remain, lantern route settles, last door no longer blocks passage | Empty Hero/Grik/Centurion bays; no combat stance, no defeated body, no trophy pose | 16:9 wide static recovery view; open route reads before any overlay | Warmth returns gradually; cool cave remains; soft dust settle, no victory flash | Warm ivory, limestone, amber, moss green, softened teal | `16:9`, `2048×1152` | `/assets/e10/art/zone3/clear/zone3_clear_backplate.webp` |
| `Z3_STONE_SHARD_HANDOFF_PLATE` | Canonical STONE SHARD prop presentation for Shot 9 | Close environment plate for the handoff: worn stone surface, shard resting between two interaction bays | Two empty hand/prop bays at x=42–58%; no hands, Hero, Grik, or face pixels | 16:9 close, shallow depth without photorealistic blur; shard remains center-safe | Soft lantern top light and stone bounce; shard is ordinary, no pulse or pointer | Warm ivory stone, charcoal edge, muted amber, damp blue-gray | `16:9`, `2048×1152` | `/assets/e10/art/zone3/cinematic/zone3_shot09_stone_shard_handoff.webp` |
| `Z3_ZONE4_HOOK_THRESHOLD` | Post-clear Zone 4 hook for Shot 10 | Deeper cave threshold opens toward a distant natural mist/forest edge; history, not a magical route | Empty Hero/Companion bay in foreground; no arrow, map marker, glowing shard, or character pixels | 16:9 medium-wide, static; off-axis opening lets the player imagine the next route | Cave amber fades into cool natural mist; no supernatural beacon | Damp blue-gray, moss green, limestone, low amber, muted teal | `16:9`, `2048×1152` | `/assets/e10/art/zone3/cinematic/zone3_shot10_zone4_hook.webp` |
| `Z3_LORD_RITUAL_BACKGROUND` | Lord Trial ritual/challenge background only | Abstracted last-door chamber with a stable ritual floor and negative space for the separate Centurion layer | Empty central Lord/metadata bay; no Lord, Hero, weapon, face, voice, label, or button pixels | 4:3 backplate, centered and UI-aware; ritual floor lower-middle | Controlled amber ring/stone reflections; no new magical system or overpowered aura | Charcoal teal, limestone cream, copper, restrained amber | `4:3`, `2048×1536` | `/assets/e10/art/zone3/lord_trial/zone3_lord_ritual_background.webp` |
| `Z3_LORD_RESULT_BACKGROUND` | Lord Trial result/failure/success background only | Same cave continuity after a committed result; open/held last-door state with neutral emotional range | Empty result subject bay; no character, reward, star, clear, or outcome symbol baked in | 4:3 backplate with top/bottom semantic UI clearance | Result tone is supplied by runtime/UI; background uses stable warm/cool balance | Limestone, warm ivory, charcoal teal, quiet amber | `4:3`, `2048×1536` | `/assets/e10/art/zone3/lord_trial/zone3_lord_result_background.webp` |
| `Z3_REPLAY_BACKPLATE` | Replay-safe revisit treatment | Revisit of the lantern route, Grik approach, and last door with a calm hold | Same empty subject bays as primary/approach; no first-clear prop or reward cue | `DERIVED` from accepted primary/approach source; no new scene | Quiet neutral grade; no celebratory flash | Primary Zone 3 palette, reduced contrast | `16:9`, `2048×1152` derivative | `/assets/e10/art/zone3/replay/zone3_replay_backplate.webp` |
| `Z3_BATTLEFIELD_BOSS_CONTEXT` | Conditional generic Battlefield Boss environment context | Reserved only if current runtime later admits a Battlefield Boss surface for Zone 3 | Empty generic encounter bay; must not contain Centurion/Lord identity | `DERIVED_OR_DEFERRED`, 16:9 | Heavier frame may be supplied by runtime presentation, not baked in art | Primary Zone 3 palette with controlled copper emphasis | `16:9`, `2048×1152` if separately admitted | `/assets/e10/art/zone3/encounter/zone3_battlefield_boss_context.webp` |

`Z3_REPLAY_BACKPLATE` is a derivative requirement, not a new image-generation
queue item. `Z3_BATTLEFIELD_BOSS_CONTEXT` is not queued: the current Zone 3
authority defines a Lord identity, not a new Battlefield Boss content request.

### 4.2 Mandatory negative prompts for every generated slot

No baked text, subtitles, Chinese or English Zone names, labels, route arrows,
UI panels, buttons, HP bars, stars, reward icons, coins, inventory/equipment
symbols, map-node state, unlock glow, clear badge, combat damage, loot, face,
voice cue, Monster body, Lord body, humanoid Centurion, generic oversized boss,
photorealism, grimdark horror, gore, muddy low contrast, black void, purple
monochrome, watermark, logo, or border. Do not place the Stone Shard in the
sky, make it glow, or make it point toward Zone 4.

## 5. First-entry cinematic coverage

The current canonical screenplay supplies ten Zone 3 shots. The following
mapping keeps those beats intact while minimizing new World plates:

| Shot | Canonical beat | World slot | Production note |
|---|---|---|---|
| 1 | Cave mouth; goblins flee with supplies | `Z3_ENTRY_ENVIRONMENT` | Environment establishes retreat, not raid; fleeing subjects are supplied later by the cinematic compositor |
| 2 | Hero watches goblins recede | `Z3_CAVE_PRIMARY_ENVIRONMENT` | Keep the route and fading supply trail readable behind the Hero layer |
| 3 | Grik is cornered at eye level | `Z3_CAVE_PRIMARY_ENVIRONMENT` | Hold a level Grik bay; no captured-enemy framing |
| 4 | Grik gestures at the shrinking cave wall | `Z3_CAVE_PRIMARY_ENVIRONMENT` | Wall remains visible and holds the Shot 5 reveal |
| 5 | Natural Go-board wall reveal | `Z3_BOARD_WALL_REVEAL` | Cracks and stone spacing carry the read; no magical grid or explanatory UI |
| 6 | Centurion introduced as the last door | `Z3_LORD_APPROACH_BACKGROUND` | Level angle; reserved door and floor point, no Lord pixels |
| 7 | Core Belief and chance to turn back | `Z3_LORD_APPROACH_BACKGROUND` | Stillness and negative space support HERO Centurion layer |
| 8 | Ceasefire before anyone speaks | `Z3_FRAGILE_TRUCE_BACKPLATE` | Post-clear/fragile-truce environment; no destruction or victory trophy |
| 9 | STONE SHARD handoff | `Z3_STONE_SHARD_HANDOFF_PLATE` | Story prop only; no reward or magical direction signal |
| 10 | Grik gestures toward deeper cave/forest | `Z3_ZONE4_HOOK_THRESHOLD` | Natural mist/forest history; no route arrow or Shard pointer |

The cinematic lifecycle remains server/runtime-owned. A future wiring task may
choose its supported phase split, but this package does not invent a new unlock,
seen-state, clear-state, or replay state. The replay contract is presentation
only and suppresses first-clear/reward/Shard grant visuals on replay.

## 6. ChatGPT image-generation queue

The queue is intentionally minimal and ordered by dependency. Each queue item
is a visual-production request for Owner/ChatGPT; it is not executed by Codex in
this task. Queue item 9 produces two related background outputs from one
composition brief, avoiding redundant cave construction.

| Order | Queue ID | Output slot(s) | Why this order | Status |
|---:|---|---|---|---|
| 1 | `Z3_WORLD_Q01_MAP_LANDMARK` | `Z3_MAP_LANDMARK` | Establishes the map-node identity and tests the cave silhouette at card scale | `QUEUED_NOT_EXECUTED` |
| 2 | `Z3_WORLD_Q02_ENTRY` | `Z3_ENTRY_ENVIRONMENT` | Required before the first-entry cinematic can establish the retreat beat | `QUEUED_NOT_EXECUTED` |
| 3 | `Z3_WORLD_Q03_PRIMARY_CAVE` | `Z3_CAVE_PRIMARY_ENVIRONMENT` | Shared plate for gameplay context and Shots 2–4; proves the three-layer cave read | `QUEUED_NOT_EXECUTED` |
| 4 | `Z3_WORLD_Q04_BOARD_WALL` | `Z3_BOARD_WALL_REVEAL` | Core Zone identity and Shot 5 reveal depend on the primary cave materials | `QUEUED_NOT_EXECUTED` |
| 5 | `Z3_WORLD_Q05_LAST_DOOR` | `Z3_LORD_APPROACH_BACKGROUND` | Boss-ready/approach context depends on the accepted cave depth and material language | `QUEUED_NOT_EXECUTED` |
| 6 | `Z3_WORLD_Q06_FRAGILE_TRUCE` | `Z3_FRAGILE_TRUCE_BACKPLATE` | Post-clear state needs the same cave geography without raid/destruction cues | `QUEUED_NOT_EXECUTED` |
| 7 | `Z3_WORLD_Q07_STONE_SHARD` | `Z3_STONE_SHARD_HANDOFF_PLATE` | The canonical Zone 3 story prop needs a neutral, non-magical close plate | `QUEUED_NOT_EXECUTED` |
| 8 | `Z3_WORLD_Q08_ZONE4_HOOK` | `Z3_ZONE4_HOOK_THRESHOLD` | The next-zone handoff depends on the accepted cave route and mist contrast | `QUEUED_NOT_EXECUTED` |
| 9 | `Z3_WORLD_Q09_LORD_BACKGROUNDS` | `Z3_LORD_RITUAL_BACKGROUND`, `Z3_LORD_RESULT_BACKGROUND` | Ritual/result backgrounds share the last-door environment but require separate neutral state treatments | `QUEUED_NOT_EXECUTED` |

The exact prompts, output naming, negative prompts, source/review paths, and
acceptance checks are machine-readable in the companion JSON manifest. A queue
item may be rejected and requeued after Owner visual review; rejection never
authorizes runtime substitution.

## 7. Responsive, safe-area, and accessibility contract

All percentages are normalized to the full master image before `object-fit` or
runtime crop. The semantic UI remains HTML/runtime text and state.

| Surface | Safe-area contract |
|---|---|
| Desktop 16:9 | Keep the identity anchor and main route inside x=8–92%, y=8–82%. Leave y=84–100% visually quiet for semantic overlays. Preserve all three layers and both subject bays. |
| iPad portrait 4:3 | Keep the identity anchor inside x=14–86%, y=10–76%. Keep one lateral route landmark and the primary subject bay; do not stretch a 16:9 master. Leave the lower 24% for action/status UI. |
| iPad landscape 4:3 | Keep route, cave landmark, subject bay, and semantic status lane inside x=10–90%, y=8–82%. Do not crop the last door, Stone Shard, or result subject bay. |
| Mobile portrait 9:16 | Keep the identity anchor and primary subject bay inside x=27–73%, y=10–64%. Keep the cave mouth/last door/Shard focal point in the center band; leave the lower 30–36% quiet for controls. Secondary route material may crop, but the Zone identity may not. |

Slot-specific anchor rules:

- `Z3_MAP_LANDMARK`: cave mouth/amber entry x=35–65%, route x=25–75%; no
  important landmark at the extreme edge.
- `Z3_ENTRY_ENVIRONMENT`: future Hero bay x=42–58%, retreat route x=18–40%.
- `Z3_CAVE_PRIMARY_ENVIRONMENT`: wall/route x=40–62%, Grik bay x=62–76%,
  Hero/Companion bays x=35–66%.
- `Z3_BOARD_WALL_REVEAL`: crack/board read x=35–65%, interaction bay x=42–58%.
- `Z3_LORD_APPROACH_BACKGROUND`: last door x=58–76%, Hero bay x=28–44%;
  preserve a clear center for semantic Lord metadata.
- `Z3_FRAGILE_TRUCE_BACKPLATE`: open passage x=44–70%, no destruction focal point.
- `Z3_STONE_SHARD_HANDOFF_PLATE`: Shard x=44–56%; interaction bays may be
  composited but must not be pre-drawn as hands.
- `Z3_ZONE4_HOOK_THRESHOLD`: natural mist opening x=56–76%; never turn it into
  a glowing waypoint.
- Lord backgrounds: keep a neutral central subject bay x=36–64% and semantic
  text lanes clear at the top and bottom; runtime supplies names and result state.

Accessibility and reduced motion:

- Zone identity must remain readable in grayscale through silhouette, material,
  value grouping, and landmark placement.
- No critical information is conveyed only by ambient audio, darkness, mist,
  flicker, or particle effects.
- Captions, names, status, reward/result text, and action labels remain outside
  the image and available to assistive technology.
- If motion is later wired, reduced motion removes camera push, parallax, rapid
  flicker, particle bursts, and nonessential loops while preserving the same
  frame, subject location, focus order, and semantic state.
- Do not use flashing or high-frequency contrast changes for the Shard, truce,
  Lord result, or Zone 4 hook.

## 8. WORLD ↔ HERO dependencies

### WORLD supplies

- Accepted environment and background plates listed in the slot table.
- Empty, documented subject bays and pivots for Hero, Companion, Grik, and the
  Goblin Centurion.
- Neutral Stone Shard prop staging without hands, character bodies, text, glow,
  ownership, reward, or journey-state implication.
- Cave depth, last-door continuity, fragile-truce state-neutrality, and Zone 4
  threshold composition.
- Review/canonical/runtime path contract and later static packaging handoff.

### HERO supplies

- Hero base/pose layers for entry restraint, observation, wall gesture, approach,
  ceasefire, and handoff.
- Companion layer and the approved companion visual contract.
- Grik character asset and eye-level presentation.
- `goblin_centurion` Lord character asset, planted-spear pose, readable Lord
  hierarchy, and any accepted transparent portrait/full-body variants.
- Any hands or interaction overlays needed for Shot 9; WORLD does not paint them
  into the background plate.
- Character-side responsive pivots and transparent compositing bounds.

### Shared dependency rules

- The Centurion is Lord-only in this presentation package. A generic
  Battlefield Boss asset may not be substituted into the Lord approach, ritual,
  or result background.
- WORLD and HERO must agree on anchor IDs, not pixels baked into either side.
- Lord ritual/result backgrounds carry no FACE/VOICE authority. Character and
  audio lanes own those decisions; Zone 3 screenplay dialogue remains the
  protected narrative source.
- No dependency in this document changes normal Monster selection, battle
  settlement, Lord eligibility/retry, clear, reward, or progression authority.

## 9. Integration boundary for the next tasks

This package authorizes no integration by itself. A later Owner-gated visual
production task may:

1. Generate or receive Owner-approved PNG review sources under
   `tools/e10_world_zone_art_review/zone3/`.
2. Record source hashes and visual review decisions.
3. Promote accepted sources to `assets/e10/art/zone3/` and create reviewed WebP
   derivatives through the established static packaging gate.
4. Run a separate map/cinematic static-adoption task if runtime paths are to be
   changed.

The following files are explicitly out of scope for this task and remain
untouched: `app.py`, `index.html`, `i18n.js`,
`js/game/cinematic_replay.js`, `sw.js`, all combat/progression/economy/payment
code, and all Production systems.

## 10. Validation record

- `CANONICAL_ZONE_IDENTITY_EXACT=YES` for `k16_20 / 哥布林洞穴 / Goblin Cave`.
- `OWNER_STYLE_B_PRESERVED=YES`.
- `TEXT_NOT_BAKED_INTO_BASE_IMAGE=YES`.
- `ROUTE_NOT_BAKED_INTO_BASE_IMAGE=YES`.
- `STATE_NOT_BAKED_INTO_BASE_IMAGE=YES`.
- `REWARD_NOT_BAKED_INTO_BASE_IMAGE=YES`.
- `MONSTER_LORD_ART_CREATED=NO`.
- `WORLD_ASSET_FILES_CREATED=NO`.
- `APP_PY_CHANGED=NO`.
- `SHARED_SHELL_CHANGED=NO`.
- `GAMEPLAY_AUTHORITY_CHANGED=NO`.
- `RUNTIME_PRODUCT_FILES_CHANGED=NO`.
- JSON shape, slot-field completeness, queue order, canonical paths, forbidden
  baked-content markers, and protected-file diff are validated after authoring.

**Ready for Owner visual production:** `YES`
**Ready for runtime/static integration:** `NO — separate future gate`
**Status:** `READY_FOR_OWNER_VISUAL_PRODUCTION`
