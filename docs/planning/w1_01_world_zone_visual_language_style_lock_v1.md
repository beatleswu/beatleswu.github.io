# W1-01 WORLD — Zone 3–10 Visual Language and Style Lock

**Task:** W1_01_WORLD_ZONE_VISUAL_LANGUAGE_STYLE_LOCK_001
**Lane:** W1-01 WORLD
**Artifact status:** PROPOSED_FOR_OWNER_ACCEPTANCE
**Canonical base:** 616d51b17abe010de1e862382ca4db7bec65936f
**Canonical tree:** f3882ecee3980d310817096e3a15bc469683e9cd
**Branch:** codex/w1-01-world-style-lock
**Scope:** planning and content-production contract only

This document is the Wave 1 world-style contract for Zones 3–10. It keeps the
current server and world-stage identity contracts intact, separates current
authority from historical or incomplete material, and gives art, screenplay,
audio, Lord presentation, and later runtime-wiring work one shared vocabulary.

It does not authorize runtime wiring, asset bulk production, gameplay or
progression changes, database work, shell changes, deployment, or Production
mutation. The document becomes the accepted style lock only after the Owner
accepts the small decision set in Owner acceptance.

## 1. Authority and classification rules

The following source order is binding for this contract:

1. Current canonical runtime definitions and server authority decide Zone keys,
   names, level bands, Lord identities, progression, eligibility, rewards, and
   state.
2. Current accepted screenplay and presentation contracts decide protected
   narrative beats, dialogue, fate boundaries, and presentation separation.
3. Existing Zone 1–2 art, audio, UI, and common visual bibles provide the
   continuity baseline where they are actually accepted for that surface.
4. Current art files and manifests are evidence of what exists; a file is not
   automatically a final, admitted, or runtime-authoritative asset.
5. Historical, candidate, stale, or conflicting planning material remains
   reference material until separately reverified and accepted.

Every surface in this document uses one of these classifications:

- EXISTING_CANONICAL — current authority or an accepted shared contract.
- EXISTING_BUT_INCOMPLETE — present, but missing acceptance, coverage,
  integration, provenance closure, or a required variant.
- REFERENCE_ONLY — useful direction or historical evidence; not current
  authority and not an admission of final art.
- NEW_PROPOSED — introduced by this style-lock artifact for Owner review.
- OWNER_DECISION_REQUIRED — cannot be treated as locked until the Owner makes
  the stated decision.

The style contract is presentation-only. In particular:

- a Monster defeat is not a Zone clear;
- a Battlefield Boss is not a Lord;
- a Lord Trial remains a distinct server-backed presentation surface, not a
  generic encounter tier;
- visual rarity, scale, animation, audio, or map emphasis never grants combat,
  progression, reward, eligibility, or unlock authority;
- replay presentation must not duplicate rewards;
- the existing distinctions Acquire != Equip, Purchase != Equip, and
  Acquire != Consume remain unchanged;
- Tier 1 grandfathered continuity is not trusted correctness.

## 2. Current evidence and status matrix

| Surface or source | Status | Use in this lock | Boundary |
|---|---|---|---|
| app.py ADVENTURE_ZONES and ADVENTURE_BOSS_META | EXISTING_CANONICAL | Exact Zone identity, level band, book mapping, and Lord metadata | Read-only source; no app.py change |
| adventure_zone_progression_authority.py | EXISTING_CANONICAL | Server-owned clear, star, unlock, Lord eligibility, and retry semantics | No progression or Lord-rule change |
| adventure_zone3_monster_authority.py | EXISTING_CANONICAL | Current Zone 3 normal/Lord identity boundary and M022 binding evidence | No roster or authority rebind |
| components/adventure/world_stage.html and js/e9/world_stage.js | EXISTING_CANONICAL | Server-projected map state, current-player marker, node-state semantics, and Lord-entry boundary | No runtime wiring or landmark rebind in this lane |
| assets/e10/ui/e10-ui-assets.json | EXISTING_CANONICAL | Shared node, selection, progress, lock, completion, and player-marker vocabulary | Presentation assets do not add state |
| docs/planning/e10_newbie_village_art_direction_bible.md | EXISTING_CANONICAL | Zone 1 visual baseline: stylized 3D illustration, outline, value grouping, palette roles, crop and UI-clearance rules | Reuse vocabulary; do not copy Zone 1 setting into later zones |
| docs/planning/e10_voice_cast_bible_v1.md | EXISTING_CANONICAL for locked identities | Narrator/Hero/Elder/Messenger/Herder reuse and nonverbal Water Spirit Horse boundary | No recast or new dialogue authority |
| docs/planning/e10_encounter_presentation_framework_a023.md | EXISTING_CANONICAL presentation boundary | Common/Rare/Elite/Battlefield Boss treatment and separate Lord treatment | No combat roster, HP, reward, or tier authority |
| docs/planning/e10_final_screenplay_v1.md | EXISTING_BUT_INCOMPLETE for Zones 3–10 production | Protected narrative beats and fate/dialogue constraints | Shot art/audio coverage and runtime integration remain incomplete |
| docs/planning/e10_final_screenplay_mapping_closure_v1.md | EXISTING_BUT_INCOMPLETE | Historical mapping evidence and explicit missing Zone 3–10 art/audio coverage | Historical counts are not current asset census |
| art/monsters/ and assets/monsters/ | EXISTING_BUT_INCOMPLETE | Existing visual evidence and candidate material | Heterogeneous provenance; not a uniform W1 admission |
| assets/e10/art/zone1, assets/e10/art/zone2, and corresponding audio packages | EXISTING_BUT_INCOMPLETE for this lane | Reusable package shape and continuity reference | Zone 3–10 production is not implied |
| assets/maps/e10-vs1f-landmarks/ and js/e9/world_stage.js landmark map | EXISTING_BUT_INCOMPLETE / OWNER_DECISION_REQUIRED | Evidence of current map image references | Several filenames/settings conflict with canonical Zone names; no rebind here |
| docs/planning/art_120_monster_roster_candidate.md | REFERENCE_ONLY | Candidate creature tone and material guidance | Explicitly not gameplay, database, or final roster authority |
| docs/planning/monster_art_content_zone_assignment_v1.json | EXISTING_BUT_INCOMPLETE planning evidence | Candidate zone groupings and runtime anchors for art intake | Its recorded historical base SHA is stale relative to this lock base; no runtime authority |
| docs/planning/art_production_master_board.md | EXISTING_BUT_INCOMPLETE | Historical production-board context | Historical totals and readiness claims require fresh recheck |
| Legacy assets/tiers/* and unaccepted storyboard/concept references | REFERENCE_ONLY | Mood and composition prompts where they fit the current identity | Baked labels, old names, and historical concepts do not become authority |
| This document | NEW_PROPOSED | Cross-zone style, narrative, audio, crop, motion, and accessibility contract | Owner acceptance is still required |

### 2.1 Canonical identity cross-check

These are the exact current identities. Chinese names, English names, keys,
level bands, stages, and books are preserved; the style lock introduces no
replacement names or gameplay rules.

| Zone | Key | Stage / level band | Canonical name | English name | Canonical books | Lord key / name |
|---|---|---|---|---|---|---|
| 3 | k16_20 | LV3 / 16–20級 | 哥布林洞穴 | Goblin Cave | 5哥布林洞穴, 6哥布林巡邏隊 | goblin_centurion / 哥布林百夫長 — Goblin Centurion |
| 4 | k11_15 | LV4 / 11–15級 | 迷霧森林 | Misty Forest | 7迷霧森林, 8迷霧森林深處 | misty_phantom_rabbit_king / 迷霧幻影兔王 — Misty Phantom Rabbit King |
| 5 | k6_10 | LV5 / 6–10級 | 獸人部落 | Orc Tribe | 9獸人部落, 10獸人角鬥場 | iron_orc_chieftain / 鋼鐵獸人酋長 — Iron Orc Chieftain |
| 6 | k1_5 | LV6 / 1–5級 | 龍之谷 | Dragon Valley | 11飛龍討伐, 12龍之谷守衛 | grand_temple_knight / 聖殿大騎士長 — Grand Temple Knight |
| 7 | d1_2 | LV7 / 1–2段 | 賢者之塔 | Sage Tower | 13賢者之塔, 14大魔法師試煉 | archmage_phantom / 大魔法師幻影 — Archmage Phantom |
| 8 | d3_4 | LV8 / 3–4段 | 魔王城前線 | Demon Castle Front | 15皇家騎士團遠征, 16魔王城前線, 17混沌領主的考驗 | chaos_lord / 混沌領主 — Chaos Lord |
| 9 | d5_6 | LV9 / 5–6段 | 諸神黃昏 | Ragnarök | 18諸神黃昏 | fallen_war_god_statue / 墮落戰神古像 — Fallen War-God Statue |
| 10 | d7_plus | LV10 / 7段＋ | 上古終焉神殿 | Ancient Doom Temple | 19東方神祕結界, 20上古終焉神殿 | source_of_black_white_order / 黑白秩序之源 — Source of Black-White Order |

The following current planning groups are presentation intake hints only, not
runtime or database assignments:

- Zone 3: M022–M033, M060
- Zone 4: M034–M045
- Zone 5: M046–M057
- Zone 6: M058, M059, M061–M070 (M060 remains in the Zone 3 planning group)
- Zone 7: M071, M072, M074–M083 (M073 remains in the Zone 10 planning group)
- Zone 8: M084, M085, M086, M087, M089, M090, M092, M093, M095, M096, M097
- Zone 9: M098, M099, M101–M104, M106, M108, M109, M111 (M100 remains in the Zone 1 planning group)
- Zone 10: M073, M112–M120

These groupings must not be used to create a new roster, change a binding, or
infer Elite/Boss/Lord status.

### 2.2 Current landmark conflict held for Owner review

The current js/e9/world_stage.js landmark references include historical names
for Zones 4–9. This is a traceability and content-intake issue, not permission
to edit the shared map runtime in W1-01.

| Key | Canonical identity | Current landmark reference | Classification | Required disposition |
|---|---|---|---|---|
| k16_20 | Goblin Cave | zone-03-goblin-cave.webp | EXISTING_BUT_INCOMPLETE | Reverify against accepted art; name aligns |
| k11_15 | Misty Forest | zone-04-twilight-forest.webp | REFERENCE_ONLY | Owner chooses replace/rebind after accepted art exists |
| k6_10 | Orc Tribe | zone-05-sky-tower.webp | REFERENCE_ONLY | Owner chooses replace/rebind after accepted art exists |
| k1_5 | Dragon Valley | zone-06-royal-castle.webp | REFERENCE_ONLY | Owner chooses replace/rebind after accepted art exists |
| d1_2 | Sage Tower | zone-07-star-sea-passage.webp | REFERENCE_ONLY | Owner chooses replace/rebind after accepted art exists |
| d3_4 | Demon Castle Front | zone-08-abyssal-forge.webp | REFERENCE_ONLY | Owner chooses replace/rebind after accepted art exists |
| d5_6 | Ragnarök | zone-09-eternal-night-shrine.webp | REFERENCE_ONLY | Owner chooses replace/rebind after accepted art exists |
| d7_plus | Ancient Doom Temple | zone-10-ancient-doom-temple.webp | EXISTING_BUT_INCOMPLETE | Reverify image content; filename aligns, legacy tier label does not |

No current landmark image is silently promoted to final Zone art by this
document.

## 3. Shared cross-zone visual language

### 3.1 Style sentence

**A stylized 3D animated adventure world built from tactile materials, clear
silhouettes, restrained fantasy utility, and a readable black/white Go
vocabulary; every Zone has its own environmental identity while the same camera,
outline, value grouping, and UI-clearance rules make the journey feel like one
game.**

The Zone 1 art-direction baseline remains the continuity anchor:

- high-quality stylized 3D animated adventure illustration;
- shared dark blue-brown contour language;
- controlled three-value shading with a soft upper-left key;
- warm ivory/charcoal stones and muted brass as the bridge between locations;
- practical materials first, restrained fantasy second;
- no painterly wash, flat anime cel treatment, photorealism, chibi proportion,
  generic mobile-splash composition, watermark, baked UI, or baked replacement
  Zone name.

Zone-specific color is an atmosphere and material cue, never the only state
signal. Lock, selection, completion, current-player, and progress states
continue to use the existing shared E10 UI asset vocabulary.

### 3.2 Journey arc

The proposed visual progression is:

cave ingenuity → misty trust → communal fire → sky and heat → geometric
curiosity → organized pressure → mythic choice → ancient stillness.

The arc changes material, scale, density, and sound gradually. It does not
change the rules of battle, progression, Lord eligibility, or rewards.

### 3.3 Layer and camera contract

Every Zone production pack must provide a clear three-layer read:

1. **Background:** sky, atmospheric depth, major landform, distant structure,
   and the large value shape that identifies the Zone at a glance.
2. **Midground:** route, landmark, practical activity, board/trial place where
   story requires it, and the map or encounter context.
3. **Foreground:** Hero, Companion, NPC, encounter subject, readable props, and
   one controlled depth cue. The foreground must not hide the canonical Lord or
   the primary action.

The identity read must survive removal of color. Silhouette, material, light,
and composition must do the work. No critical identity may exist only at the
extreme edge of a crop or only in a sound cue.

### 3.4 Shared encounter boundary

The existing presentation framework remains the single visual vocabulary for
ordinary encounter rarity:

- Common/Rare/Elite use the shared presentation tiers, visible text or symbol,
  frame geometry, and scale/HP treatment already admitted by the current
  surface.
- Battlefield Boss uses its explicit heavier presentation and label. It is not
  the Lord and does not grant a Zone clear merely because it is visually large.
- Lord presentation is a separate trial/cinematic language with an explicit
  Lord name and a server-backed entry. It must never reuse an ordinary
  Battlefield Boss frame as a shortcut.

### 3.5 Map-node contract

Map nodes continue to be server-projected state rendered through the existing
world-stage contract:

- canonical key/name/status/entry permission comes from the Adventure bootstrap;
- current_zone_key remains the authoritative current-player location;
- selected node is ephemeral UI selection, not progression state;
- shared E10 zone-number-frame, available-halo, completed-seal, locked-ring,
  selected-halo, player-location-pin, progress-rail, and star assets are reused;
- a Zone accent may tint a frame or background, but may not introduce a new
  unlock, clear, star, reward, Lord, or eligibility state;
- the node label must use the exact canonical name in Section 2.1;
- map art must preserve a readable route and leave the node, current marker,
  status, and primary action legible at 9:16, 4:3, and 16:9.

### 3.6 Presentation lifecycle

Each Zone pack plans four authored moments:

- **Entry:** orient the player with one environmental reveal and one next-action
  cue; do not front-load a tutorial wall.
- **Clear:** celebrate the server-confirmed clear and show the next route or
  action. A visual clear sequence is not the source of clear authority.
- **Replay:** make the scene rewatchable or re-enterable without granting a
  second reward, star, item, or unlock. Show a quiet replay treatment if the
  existing surface supports it.
- **Lord:** use the separate Lord presentation contract, with no implication
  that ordinary encounter completion is Lord completion.

### 3.7 Audio and motion baseline

- Sound uses the same world: tactile material SFX, restrained fantasy resonance,
  readable transients, and a musical identity that can be shortened or muted.
- Dialogue and important state changes must have a visible equivalent.
- A loopable ambience bed, a short entry cue, a clear/recovery cue, and authored
  encounter/Lord cues are the minimum production slots; exact stems and timing
  are an audio acceptance decision, not created here.
- Ambient motion is low-frequency environmental motion: drifting dust/mist,
  cloth, foliage, embers, distant particles, or a slow light change. It must
  never obscure a node, board, question, character face, or answer feedback.
- Reduced motion removes camera push, parallax sweeps, looping particle bursts,
  rapid flashes, and nonessential character idles while preserving state,
  timing, focus, and readable feedback.

### 3.8 Responsive and accessibility baseline

- **Mobile portrait (9:16):** keep Hero/primary subject and the canonical Zone
  identifier in the safe center band; stack secondary context; reserve the lower
  action zone for controls; never require a wide establishing shot to identify
  the Zone.
- **Tablet portrait (4:3 portrait):** use a centered primary composition with
  enough lateral room for one environmental landmark and the route/status rail;
  avoid a stretched desktop panorama.
- **Tablet landscape (4:3 landscape):** preserve the three-layer read and leave
  a clear interaction lane for the current node, status, and primary action;
  do not crop the Lord or answer feedback out of frame.
- All states have visible text or shape alternatives to color and audio.
- Text is not baked into replaceable artwork; canonical names, status, and
  action labels remain semantic UI text.
- Focus order, keyboard access where supported, and focus visibility must remain
  intact. Decorative motion is not focusable.
- Do not use flashing patterns, rapid luminance changes, tiny-only cues, or
  audio-only critical information.
- Contrast, alt text/accessible name, captions/transcripts where dialogue or
  SFX carries meaning, and a reduced-motion path are acceptance requirements.

## 4. Zone contracts

The tables below are implementation-ready direction. They are proposals for
style and content production, not new runtime authority.

### Zone 3 — 哥布林洞穴 / Goblin Cave

**Identity status:** EXISTING_CANONICAL
**Presentation status:** EXISTING_BUT_INCOMPLETE
**Style status:** NEW_PROPOSED
**Production gate:** OWNER_DECISION_REQUIRED

| Contract field | Style-lock direction |
|---|---|
| Visual language | Clever cave faction: practical, angular, improvised, and observant. Use limestone, rope, ore, fungus, lanterns, and worn Go-board geometry as one believable working culture. |
| Environment / background | Layered limestone chambers, narrow routes, rope bridges, echo pockets, storage alcoves, and a distant “last door”; the cave feels occupied and defended, not like a raid dungeon. |
| Lighting / atmosphere | Warm lantern amber against cool charcoal stone and muted moss. Use pools of visibility and deep but readable recesses; avoid horror blackouts. |
| Foreground / background hierarchy | Foreground: Hero/Companion and one practical cave prop. Midground: route, supplies, and the natural board-wall or trial place. Background: cavern scale and fleeing silhouettes. Keep the last door visually reserved for the Lord beat. |
| Monster presentation | Crouched, asymmetrical, tool-aware silhouettes with copper/amber accents. Existing candidate creature art is intake evidence only; no file is final until admitted. |
| Elite presentation | If a currently admitted encounter is Elite, add a sharper silhouette, disciplined lantern accent, and a compact angular frame treatment. Do not infer Elite from a candidate filename or art count. |
| Battlefield Boss presentation | If the current surface presents a Battlefield Boss, use the shared heavy boss frame and explicit Battlefield Boss label over a larger cave silhouette; it must remain distinct from Goblin Centurion. |
| Lord presentation | goblin_centurion / Goblin Centurion is Lord-only. Present the Centurion as the keeper of the last door and a possible ceasefire, not as an ordinary oversized goblin and not as a kill trophy. |
| Map-node presentation | Use the exact k16_20 key and “哥布林洞穴 / Goblin Cave.” A cave-mouth landmark may use amber entry light; route, node state, and current marker retain shared E10 assets. |
| Entry presentation | Start with a quiet supply trail and an echo or lantern reveal. The player understands “retreat, not raid” before the first question/action cue. |
| Clear presentation | Resolve the ceasefire/trust beat and show the Stone Shard handoff as an authored narrative prop. The clear state is still server-confirmed. Do not show the cave faction destroyed. |
| Replay presentation | Replay can revisit the lantern route, Grik, and the last door. Suppress first-clear reward or Stone Shard regrant visuals on replay. |
| Ambient motion intent | Lantern sway, dust motes in shafts of light, small rope movement, distant fungus pulse, and occasional loose-stone settling; slow and spatially legible. |
| SFX direction | Footfalls on stone, rope creak, lantern metal, distant cave calls, supply movement, soft board-stone contact, and a restrained stone resonance for the handoff. |
| BGM / ambience direction | Low hand percussion and dry plucked texture over cave air and distant echoes. The music should feel resourceful and tense, not villainous. |
| Narrative tone | Retreat, not raid; curiosity and negotiated trust; the cave residents have agency and are not disposable enemy dressing. |
| Mobile crop requirements | Keep the Hero, lantern route, and one readable cave landmark in the center-safe band. Move rope bridges and secondary silhouettes behind the subject rather than cropping the face or action. |
| Tablet crop requirements | Preserve the lateral route and the last-door depth cue in portrait; in landscape retain one foreground prop plus cave scale without making the frame a flat tunnel. |
| Reduced-motion behavior | Remove camera push into the cave, drifting dust loops, rope sway, and echoing screen shake. Keep lantern contrast, visible dialogue, and the door/trust relationship. |
| Accessibility constraints | Do not encode danger or trust only in darkness or sound. Provide captions/transcripts for calls and dialogue, visible Stone Shard and clear-state labels, and non-color silhouette separation. |

### Zone 4 — 迷霧森林 / Misty Forest

**Identity status:** EXISTING_CANONICAL
**Presentation status:** EXISTING_BUT_INCOMPLETE
**Style status:** NEW_PROPOSED
**Production gate:** OWNER_DECISION_REQUIRED
**Reference conflict:** current landmark filename zone-04-twilight-forest.webp is REFERENCE_ONLY.

| Contract field | Style-lock direction |
|---|---|
| Visual language | Mystery without menace: layered mist, gentle uncertainty, and trustworthy natural anchors. The forest should invite careful observation rather than imply horror. |
| Environment / background | Fern paths, moon pools, old trunks, hanging vines, and soft clearings with a stable route marker. Use depth planes so the mist has a readable edge. |
| Lighting / atmosphere | Deep teal and moss under lavender fog with a muted moon-gold path. Preserve warm skin/cloth values so faces remain readable through haze. |
| Foreground / background hierarchy | Foreground: Hero and Water Spirit Horse with a clean silhouette. Midground: fern/stone route and a single stable landmark. Background: mist layers and phantom suggestions, never a confusing duplicate battlefield. |
| Monster presentation | Long tails, leaf crests, soft asymmetry, and quiet movement. Phantom copies are a compositing/presentation motif only and must not become duplicate combat authority. |
| Elite presentation | If an admitted Elite exists, use a clearer leaf/antler silhouette and a moon-gold edge light, with the shared tier label and shape. No horror face treatment. |
| Battlefield Boss presentation | Use the shared explicit Battlefield Boss frame and label with a strong silhouette emerging from the mist; do not use a phantom copy or the Rabbit King’s Lord staging. |
| Lord presentation | misty_phantom_rabbit_king / Misty Phantom Rabbit King is a voice-led Lord encounter. Keep the figure partly obscured or voice-only where the screenplay requires; no defeat speech and no human villain pose. |
| Map-node presentation | Exact k11_15 key and “迷霧森林 / Misty Forest.” Use a fern-ring or moon-pool landmark, not the historical “Twilight Forest” name. |
| Entry presentation | The mist parts around a stable natural marker and the Water Spirit Horse. Give the player the protected short line “小水。帶我走。” as visible dialogue/caption, not an audio-only cue. |
| Clear presentation | Reveal a safe path and the Black/White Fruit as a balanced, readable narrative prop. The forest remains alive; a clear is not a “monster extermination” image. |
| Replay presentation | Preserve the mist route and riddle rhythm while suppressing repeat reward/fruit acquisition. On replay, the player can skip or revisit the reveal without changing progression. |
| Ambient motion intent | Slow mist drift, fern movement, moon-pool ripple, and a restrained tail/cloth idle. Keep the visual center stable. |
| SFX direction | Soft leaves, damp footfalls, distant water, light chimes from the moon pool, and separated creature/voice layers. Avoid jump-scare stingers. |
| BGM / ambience direction | Sparse breathy woodwind, glassy but warm tones, and a continuous forest bed. Leave space for the Rabbit King’s voice-led riddle. |
| Narrative tone | Trust, not out-calculation; uncertainty is a reason to observe and cooperate, not evidence of an enemy attack. |
| Mobile crop requirements | Keep Hero, Water Spirit Horse, and the stable route marker together in the center. Use mist as a side layer, not a full-screen veil. |
| Tablet crop requirements | In portrait, retain a vertical trunk/fern anchor and moon-pool depth. In landscape, preserve enough lateral fog layers to read the route without shrinking the characters. |
| Reduced-motion behavior | Freeze or simplify mist drift, ripples, parallax, and camera float. Replace phantom movement with a static value/shape distinction and keep the riddle/caption timing stable. |
| Accessibility constraints | Never make the correct route, riddle state, or Spirit presence depend on low contrast or sound alone. Use captions, clear focus, and a non-color outline/shape cue for the route marker. |

### Zone 5 — 獸人部落 / Orc Tribe

**Identity status:** EXISTING_CANONICAL
**Presentation status:** EXISTING_BUT_INCOMPLETE
**Style status:** NEW_PROPOSED
**Production gate:** OWNER_DECISION_REQUIRED
**Reference conflict:** current landmark filename zone-05-sky-tower.webp is REFERENCE_ONLY.

| Contract field | Style-lock direction |
|---|---|
| Visual language | Boisterous clan frontier built around craft, work, respect, and communal spectacle. Broad shapes and warm materials convey strength without caricature or humiliation. |
| Environment / background | Red-clay arena, basalt shelves, drum circles, banners, fires, smithing area, and a visible route out of the settlement. The arena is social before it is combative. |
| Lighting / atmosphere | Terracotta, ochre, dark teal, cream, and ember light. Use fire as a warm practical source with cool open-air fill; avoid a permanent angry red wash. |
| Foreground / background hierarchy | Foreground: Hero and the immediate challenge prop. Midground: Chieftain/Smith-Elder relationship and the arena ring. Background: clan activity, banners, and northward route/ore context. |
| Monster presentation | Broad shoulders, horns, shields, chunky feet, hide/leather/wood/bronze, and readable craft details. Avoid realistic warfare, hateful caricature, or generic “evil orc” coding. |
| Elite presentation | If currently admitted, use a more deliberate stance, crafted bronze/hide detail, and the shared Elite label/frame. The visual distinction must be shape/material based, not red-only. |
| Battlefield Boss presentation | Use a public arena scale and the existing explicit Battlefield Boss treatment if applicable; it must not be the Chieftain’s Lord presentation or imply Zone clear. |
| Lord presentation | iron_orc_chieftain / Iron Orc Chieftain is a respected leader. Present the voluntary axe release and northward ore clue; the Chieftain does not kneel, die, or become a defeated prop. |
| Map-node presentation | Exact k6_10 key and “獸人部落 / Orc Tribe.” Use a drum-ring, forge glow, or banner gate as landmark language; do not use a tower silhouette. |
| Entry presentation | Enter through communal sound and work: drum, forge, and the Smith-Elder’s warning about corrupted ore. The Zone2 Corrupted Crystal Fragment resonates as evidence, not as a new authority. |
| Clear presentation | Show earned respect and the Chieftain’s voluntary release of the axe. Point the route north through dialogue/visual geography; do not make ore a magical pointer. |
| Replay presentation | Replay the arena rhythm and respect exchange while suppressing any repeat reward or ore acquisition. Do not make replay look like a second conquest. |
| Ambient motion intent | Banner movement, forge sparks kept below the text/action area, fire breathing, drum hands, dust on the arena floor, and restrained crowd shifts. |
| SFX direction | Low drums, forge strikes, leather/wood/bronze handling, measured footsteps, and one clear grounded axe impact. Avoid battle screams as default ambience. |
| BGM / ambience direction | Layered communal percussion and low strings with a call-and-response shape. The score should widen on respect, not peak as a kill fanfare. |
| Narrative tone | Earned respect, not humiliation; a powerful community with its own values and a warning about corruption. Preserve “我不知道。” as a protected response where scripted. |
| Mobile crop requirements | Keep Hero, Chieftain/Smith-Elder focal exchange, and the arena edge in one center-safe grouping. Place banners/crowd as shallow side depth. |
| Tablet crop requirements | Preserve the arena circle and forge/route relationship in portrait; in landscape retain crowd scale without letting background activity compete with the dialogue/action lane. |
| Reduced-motion behavior | Remove crowd loops, spark bursts, camera shake, and banner sway. Retain static fire/forge contrast, clear dialogue, and the axe’s readable final position. |
| Accessibility constraints | Do not signal respect, threat, or corruption only through red/green or drum volume. Caption dialogue/SFX when meaningful; expose the ore evidence and outcome text visibly. |

### Zone 6 — 龍之谷 / Dragon Valley

**Identity status:** EXISTING_CANONICAL
**Presentation status:** EXISTING_BUT_INCOMPLETE
**Style status:** NEW_PROPOSED
**Production gate:** OWNER_DECISION_REQUIRED
**Reference conflict:** current landmark filename zone-06-royal-castle.webp is REFERENCE_ONLY.

| Contract field | Style-lock direction |
|---|---|
| Visual language | Sky/fire valley where order is visually powerful but morally questioned. Use height, wind, heat, and engineered boundaries rather than a generic dragon dungeon. |
| Environment / background | Cliffs, lava seams, crystal nests, rope bridges, wind tunnels, distant wyverns, and a severe temple/command tower. A worn dragon-engraved Go jar is background texture only. |
| Lighting / atmosphere | Cobalt sky, ember, gold, volcanic plum, and smoke. Heat and altitude alternate; keep smoke transparent enough for faces and route markers. |
| Foreground / background hierarchy | Foreground: Hero and the command boundary. Midground: bridge/tower/ore resonance. Background: cliffs, wind tunnels, and wyvern scale. Reserve the final Knight position for the unresolved fate beat. |
| Monster presentation | Wings, horns, tails, triangles, airborne diagonals, scale, basalt, crystal, ember glass, and rope. No giant deity or final Boss dragon silhouette. |
| Elite presentation | If an admitted Elite exists, use a sharper wing/horn silhouette and controlled ember edge, with the shared Elite label. Never make the Elite look like the Grand Temple Knight. |
| Battlefield Boss presentation | If applicable, use a grounded large creature or encounter silhouette with the shared Battlefield Boss label. Do not use the Grand Temple Knight, a Lord frame, or a dragon deity as a substitute. |
| Lord presentation | grand_temple_knight / Grand Temple Knight is the Lord presentation. The Knight is not killed; no death animation or victory corpse. The final fate remains intentionally unresolved. |
| Map-node presentation | Exact k1_5 key and “龍之谷 / Dragon Valley.” Use a cliff/bridge/heat-haze landmark, not a castle landmark. |
| Entry presentation | The Zone5 ore warms near the boundary. Establish the “no one can approach” rule through staging, not through an invented gameplay lock. |
| Clear presentation | Preserve the command-boundary question and the protected lines “那你和我，有什麼不同？” and “命令沒有改。” The Dragon Scale is acquired through the authored boundary, not as a magical pointer to Zone 7. |
| Replay presentation | Replay the boundary conversation and wind/ore resonance without repeating the Dragon Scale grant. Until a later implementation exists, any required mid-play pause/resume remains a production/runtime gate, not implied by this document. |
| Ambient motion intent | Wind ribbons, distant wyvern glides, smoke lift, crystal glints, rope bridge tension, and slow lava light. Avoid constant screen shake. |
| SFX direction | Wind shear, rope strain, distant wing beats, basalt/metal contact, low heat rumble, and restrained crystal resonance. Keep command dialogue intelligible. |
| BGM / ambience direction | High open-air drones, sparse frame drums, bowed metal/strings, and a disciplined pulse that can fracture into silence at the boundary. |
| Narrative tone | Order without exception, questioned; authority is staged as a boundary and relationship, not a kill target. |
| Mobile crop requirements | Keep Hero and the command boundary in the safe center; move height and cliffs into a vertical background slice. Never crop the only route marker out. |
| Tablet crop requirements | Portrait retains cliff/bridge verticality and the tower edge; landscape restores wind-tunnel depth and a readable ore/character relationship. |
| Reduced-motion behavior | Remove camera drop, flying sweep, smoke loops, crystal flicker, and screen shake. Preserve a static wind/heat value contrast and the dialogue boundary. |
| Accessibility constraints | No critical command, fate, route, or ore state is conveyed by height, roar, flash, or color alone. Provide captions, visible line breaks, focus order, and a static alternative to the heat/wind effect. |

### Zone 7 — 賢者之塔 / Sage Tower

**Identity status:** EXISTING_CANONICAL
**Presentation status:** EXISTING_BUT_INCOMPLETE
**Style status:** NEW_PROPOSED
**Production gate:** OWNER_DECISION_REQUIRED
**Reference conflict:** current landmark filename zone-07-star-sea-passage.webp is REFERENCE_ONLY.

| Contract field | Style-lock direction |
|---|---|
| Visual language | Curiosity and spellcraft expressed through architecture, geometry, and evidence. The Tower is a place of learning and synthesis, not a haunted wizard portrait gallery. |
| Environment / background | Spiral stairs, floating rooms, library shelves, brass observatory elements, star windows, suspended boards, paper, cloth, and crystal. Use vertical navigation as a clear visual rhythm. |
| Lighting / atmosphere | Indigo, cyan, brass, parchment, and violet with crisp star-window shafts. Keep the interior readable and avoid cyan/magenta spectacle. |
| Foreground / background hierarchy | Foreground: Hero, board, and the forming Heartstone. Midground: four-relations/relic evidence and stairs. Background: tower void, shelves, and stars. The Heartstone must not be hidden behind effects. |
| Monster presentation | Geometric, levitating, page/ring/stacked silhouettes with ink, paper, brass, crystal, ceramic, and cloth. No Spirit clones and no horror. |
| Elite presentation | If admitted, use a more coherent ring/page geometry and controlled brass edge, with the shared Elite treatment. Do not infer a magical rank from glow alone. |
| Battlefield Boss presentation | If applicable, frame a distinct hostile structure/creature with the shared Battlefield Boss label. It must remain separate from Archmage Phantom and from the Heartstone formation. |
| Lord presentation | archmage_phantom / Archmage Phantom is a separate Lord presentation. The “phantom” is a conceptual/knowledge presence, not a Spirit clone or a generic wizard portrait. |
| Map-node presentation | Exact d1_2 key and “賢者之塔 / Sage Tower.” Use a spiral tower and star-window landmark; do not use a star-sea passage label. |
| Entry presentation | A vertical reveal aligns the previous relic evidence with the Tower’s board geometry. The player receives a short question/action cue, not a lecture. |
| Clear presentation | The Heartstone forms and fuses only the four Hero Journey Relics already specified: Wooden Sword, Stone Shard, Black/White Fruit, Dragon Scale. No physical relic is consumed and no new persistence is invented. |
| Replay presentation | Replay the formation as a readable diagram/relationship reveal, suppressing repeat acquisition or fusion reward. Preserve the player’s ability to skip/replay where the current shell supports it. |
| Ambient motion intent | Slow paper lift, suspended dust, star-window drift, turning rings, and controlled crystal light. The central board/Heartstone remains visually still enough to read. |
| SFX direction | Paper, ceramic, brass gear, soft stone placement, restrained harmonic resonance, and a single clear Heartstone formation cue. |
| BGM / ambience direction | Sparse arpeggiated strings/keys and warm brass over a high quiet room tone. It should feel exploratory and exact, not portentous horror. |
| Narrative tone | The Heartstone forms; knowledge is relational and playable. Preserve “可棋不是考卷。” as visible authored dialogue. |
| Mobile crop requirements | Keep Hero, board, and Heartstone in the center-safe vertical stack; move spiral depth into the upper/lower background. Never make the formation a tiny particle effect. |
| Tablet crop requirements | Portrait preserves the stair spiral and central board; landscape shows one side library/observatory context without reducing the central object below readable scale. |
| Reduced-motion behavior | Replace orbiting rings, floating pages, camera lift, and star parallax with static layered diagrams and a timed value transition. Preserve the formation order in text/shape. |
| Accessibility constraints | Show the four relic relationships in text and shape, not color/glow alone. Provide semantic labels, captions, focus order, and a non-animated Heartstone state. |

### Zone 8 — 魔王城前線 / Demon Castle Front

**Identity status:** EXISTING_CANONICAL
**Presentation status:** EXISTING_BUT_INCOMPLETE
**Style status:** NEW_PROPOSED
**Production gate:** OWNER_DECISION_REQUIRED
**Reference conflict:** current landmark filename zone-08-abyssal-forge.webp is REFERENCE_ONLY.

| Contract field | Style-lock direction |
|---|---|
| Visual language | Frontier under pressure: organized, tactical, and human-scale amid a large threat. Use practical fortification and signal language instead of demon-horror spectacle. |
| Environment / background | Fortifications, moats, broken gates, supply yards, signal towers, blue flags, a black spire, and the march line. Preserve room for Serel’s command presence. |
| Lighting / atmosphere | Navy, rust, black, ash, and signal red used sparingly. Blue flag and warm camp utility keep the front readable; the black spire is a shape, not an all-consuming void. |
| Foreground / background hierarchy | Foreground: Hero and immediate stabilizing stone/action. Midground: Serel, signal route, and fortification. Background: march, spire, and depth of the front. The Chaos Lord must read as a living rune before dissolution. |
| Monster presentation | Plated, wedge, shield, and organic-mechanical silhouettes from obsidian, iron, leather, charcoal, rope, and signal cloth. Avoid demon-horror faces and final-Lord regalia for ordinary monsters. |
| Elite presentation | If admitted, use an organized wedge/plate silhouette and a compact signal accent with the shared Elite label. Do not turn a standard soldier into Chaos Lord authority. |
| Battlefield Boss presentation | If applicable, use a separate heavy battlefield silhouette and explicit label. It must not be the Chaos Lord and must not dissolve as the Lord resolution. |
| Lord presentation | chaos_lord / Chaos Lord is a distinct living rune. Show dissolution after distortion is stabilized; CHAOS_LORD_KILLED_BY_HERO=FALSE. Do not show a body falling, a kill count, or a victory corpse. |
| Map-node presentation | Exact d3_4 key and “魔王城前線 / Demon Castle Front.” Use a gate/signal-tower landmark, not an abyssal forge label. |
| Entry presentation | Establish the war-scale march and Serel’s command before the distortion dominates. The Heartstone reveals relationships but never commands people or the army. |
| Clear presentation | One stone stabilizes the distortion; Chaos Lord dissolves and Serel remains commander. Present the front’s restored agency, not a conquest trophy. |
| Replay presentation | Replay the march/stabilization/dissolution rhythm while suppressing repeat stone, reward, or progression grants. The Lord’s living-rune resolution remains distinct on replay. |
| Ambient motion intent | Flag and rope movement, ash, supply-yard activity, distant marching, and a controlled distortion shimmer. Keep the central action lane stable. |
| SFX direction | Boots, leather/metal, signal horn, rope, gate strain, low rune vibration, and a clean stabilization release. Avoid constant battle noise under dialogue. |
| BGM / ambience direction | Percussive march with restrained low brass and a harmonic distortion layer that resolves into open air. Serel’s command should remain intelligible. |
| Narrative tone | Pressure and organized resistance; the Chaos Lord dissolves, not killed. Relationships and command remain human/agentic. |
| Mobile crop requirements | Keep Hero, Serel or the signal lane, and the stabilization action in the center-safe band. Treat the march and spire as vertical side depth. |
| Tablet crop requirements | Portrait retains gate/signal-tower verticality; landscape shows the fortification route and march scale without pushing Serel or the Lord resolution to the edge. |
| Reduced-motion behavior | Remove march loops, ash sweep, distortion shimmer, and camera shake. Keep static rune geometry, visible stabilization steps, and the dissolution state change. |
| Accessibility constraints | No command, distortion, or Lord resolution is audio-only or color-only. Caption signal cues; label stabilization and dissolution; maintain keyboard/focus visibility and contrast through ash. |

### Zone 9 — 諸神黃昏 / Ragnarök

**Identity status:** EXISTING_CANONICAL
**Presentation status:** EXISTING_BUT_INCOMPLETE
**Style status:** NEW_PROPOSED
**Production gate:** OWNER_DECISION_REQUIRED
**Reference conflict:** current landmark filename zone-09-eternal-night-shrine.webp is REFERENCE_ONLY.

| Contract field | Style-lock direction |
|---|---|
| Visual language | Mythic weather and broken order. Scale is cosmic but the emotional subject remains a choice made by people; do not make the Zone opaque cosmic horror. |
| Environment / background | Storm temples, aurora bridges, fractured monuments, cloud shelves, and a fallen war-god statue whose age and grief are legible. |
| Lighting / atmosphere | Dusk purple, storm cyan, moon white, and restrained gold with broad weather layers. Use lightning as sparse punctuation, never as a constant flash. |
| Foreground / background hierarchy | Foreground: Hero and the choice boundary. Midground: statue/monument and illusion break. Background: storm architecture and aurora route. Keep the refusal/action line visible through the weather. |
| Monster presentation | Tall, cosmic, orbiting silhouettes from starstone, bronze, cloud glass, storm silk, and moon metal. Avoid deity copies, body horror, or ungrounded opacity. |
| Elite presentation | If admitted, use a precise orbit or storm-silk silhouette with the shared Elite label, not a god mask or Lord regalia. Distinction remains readable without cyan. |
| Battlefield Boss presentation | If applicable, use the shared explicit Battlefield Boss treatment on a separate statue/creature threat. The fallen war-god is not automatically a battlefield boss or a Lord because of scale. |
| Lord presentation | fallen_war_god_statue / Fallen War-God Statue is the Lord presentation. Show ancient memory and sincere exhaustion; the war-god is not killed and no Final Stone/Heartstone consumption occurs here. |
| Map-node presentation | Exact d5_6 key and “諸神黃昏 / Ragnarök.” Use a fractured monument/storm-temple landmark, not an eternal-night shrine label. |
| Entry presentation | Enter through weather and an ancient memory, then establish the choice. Illusions must be visually distinct from canonical people/monsters and never become alternate authority. |
| Clear presentation | Preserve the refusal line “可我不能因為怕錯，就替所有人把選擇拿走。”, the acknowledgment “……我們錯了。”, and “一色的棋盤，是死的。” where scripted. The single-color overlay destabilizes; it is not a reward animation. |
| Replay presentation | Replay the memory/choice sequence with repeat-safe presentation and no final-stone consumption. Do not turn replay into a second moral “choice” that alters progression. |
| Ambient motion intent | Slow cloud shelves, aurora drift, cloth/storm silk, distant rain, and sparse lightning. Keep the choice boundary visually calm enough to read. |
| SFX direction | Wind, distant thunder, stone fracture, cloth snap, quiet breath/footstep, and a low instability tone. Avoid loud impacts as the only evidence of the choice. |
| BGM / ambience direction | Wide low strings, choral air without lyrical text, sparse bell/metal, and a restrained storm pulse. Silence is an authored part of the choice. |
| Narrative tone | THE CHOICE: responsibility without domination; ancient grief becomes a conversation, not a boss kill. |
| Mobile crop requirements | Keep Hero and the choice boundary central; crop weather/aurora laterally before cropping the face, protected dialogue, or statue relationship. |
| Tablet crop requirements | Portrait keeps a vertical monument and storm shelf; landscape allows the aurora bridge and statue depth while preserving the dialogue/action lane. |
| Reduced-motion behavior | Remove lightning flashes, cloud parallax, aurora sweep, camera orbit, and fracture shake. Use a static single-color overlay with a clear text/shape transition. |
| Accessibility constraints | Avoid flashing lightning and color-only moral state. Provide captions, visible overlay/state labels, non-color contrast for the choice boundary, and a static weather alternative. |

### Zone 10 — 上古終焉神殿 / Ancient Doom Temple

**Identity status:** EXISTING_CANONICAL
**Presentation status:** EXISTING_BUT_INCOMPLETE
**Style status:** NEW_PROPOSED
**Production gate:** OWNER_DECISION_REQUIRED
**Reference conflict:** current landmark filename aligns, but legacy tier text “Ancient Omega Temple” is REFERENCE_ONLY.

| Contract field | Style-lock direction |
|---|---|
| Visual language | Ancient ending and still collectible: black/white temple stone, measured negative space, and a final place that feels quiet rather than noisy or cosmic-horror. |
| Environment / background | Temple stone, void windows, time scars, silent courtyards, nested gates, and a clear open route. The final environment must remain tangible and collectible. |
| Lighting / atmosphere | Ivory, obsidian, muted gold, and quiet violet with soft controlled shafts. Reserve the strongest contrast for the open gate/board logic, not for constant effects. |
| Foreground / background hierarchy | Foreground: Hero, ordinary stone, and the readable final action. Midground: gate/guardian/lotus mechanism. Background: silent courtyard, void windows, and nested geometry. The Source never becomes a foreground character. |
| Monster presentation | Monolith, shell, gate, and nested-geometry silhouettes using ancient stone, obsidian, ivory, muted gold, and quiet violet. No gore, Spirit copies, or Lord/Boss replicas. |
| Elite presentation | If an admitted Elite exists, use a more complex nested silhouette and quiet gold edge with the shared Elite label. Do not imply that geometry itself is a new combat authority. |
| Battlefield Boss presentation | If applicable, keep a distinct grounded battlefield silhouette and explicit label. It must not be the Source of Black-White Order or the silent guardian’s final authority. |
| Lord presentation | source_of_black_white_order / Source of Black-White Order is fully silent and non-character. The presentation is a mechanism/logic relationship, not a speaking villain or kill scene. |
| Map-node presentation | Exact d7_plus key and “上古終焉神殿 / Ancient Doom Temple.” Use the open-gate/temple landmark; reject the legacy “Omega” name in labels and UI. |
| Entry presentation | Dream/lotus/guardian silence leads to a mechanism vision. The half-point image is an open gate (GO_LOGIC_GATE_01=OPEN); do not invent a board state or explain it as a new gameplay rule. |
| Clear presentation | At the final authored beat the Heartstone final stone becomes ordinary; no THROWN, DESTROYED, REMOVED, or SPENT state is shown. End on ordinary ground and the protected line “走吧。”; do not use the noncanonical Anna A/B alternative as final authority. |
| Replay presentation | Replay remains a quiet revisit with no stone consumption, reward duplication, or altered final state. If the player skips, the visible final-state summary must still be complete. |
| Ambient motion intent | Slow dust, cloth/lotus movement, distant light shift, and nearly imperceptible time-scar shimmer. Silence and stillness are intentional. |
| SFX direction | Stone contact, a restrained gate mechanism, soft courtyard air, one ordinary-stone placement, and a clean quiet tail. No explosive final sting. |
| BGM / ambience direction | Minimal temple air, low sustained tone, sparse single-note piano/stone resonance, and a deliberate release into near silence. The Source has no voice. |
| Narrative tone | THE FINAL MOVE: stop over-correction, accept the open logic gate, and continue. The ending is a choice to move, not a victory kill. |
| Mobile crop requirements | Keep Hero, open gate/mechanism, and ordinary final stone in the central vertical read. Use negative space above/below; never crop away the only state cue. |
| Tablet crop requirements | Portrait preserves nested gate depth and central ordinary stone; landscape may widen the courtyard and void window but must not turn the Source into a character silhouette. |
| Reduced-motion behavior | Remove dream zoom, lotus/particle loops, light pulses, and camera drift. Use static gate/shape states, visible text, and a timed ordinary-stone transition. |
| Accessibility constraints | No final logic, gate state, or ending is conveyed only by silence, glow, color, or audio. Provide visible state text/labels, focus order, captions for meaningful SFX, safe contrast, and a non-animated ending. |

## 5. Production intake contract

Once the Owner accepts this lock, each Zone 3–10 content package should be
entered with the same minimum metadata. This section is a production contract,
not a request to generate the files in W1-01.

### 5.1 Art package

Each Zone package should identify:

- exact canonical zone_key, Chinese name, English name, and stage;
- one wide environment/master composition with clean 16:9, 4:3, and 9:16
  crop guidance;
- entry, clear, replay, and Lord presentation slots, with a note when the
  screenplay requires a distinct shot rather than a reusable card;
- normal/Elite/Battlefield Boss assets only when their current source surface
  admits them, with Battlefield Boss and Lord explicitly separated;
- foreground/midground/background layer ownership and the UI-clearance safe
  areas;
- palette/material notes, motion notes, reduced-motion fallback, and
  accessibility text/alt-name requirements;
- provenance, source SHA or source package, status classification, and Owner
  acceptance state;
- no baked Zone replacement name, gameplay state, reward, price, equipment
  state, or progress claim in the art.

The package may reference current art/monsters/ candidates and the planning
groups in Section 2.1, but admission requires a fresh review against the exact
current base. Historical art is never admitted by filename or by a stale plan.

### 5.2 Audio package

Each Zone package should identify:

- loopable ambience bed;
- short entry/orientation cue;
- encounter/escalation cue slots with the existing tier boundary;
- clear/recovery cue;
- Lord-specific cue slot separate from Battlefield Boss;
- dialogue identity and reuse of the locked cast where applicable;
- captions/transcripts or visible equivalents for any meaningful cue;
- reduced-motion/reduced-audio behavior and a mute-safe state;
- source/provenance and acceptance status.

The exact musical motifs remain intentionally broad enough for one shared-game
palette. Zone-specific audio must support the narrative tone in Section 4
without changing progression, combat, reward, or Lord authority.

### 5.3 Runtime handoff boundary

The later shell/runtime lane may consume this contract only after acceptance.
That handoff must preserve:

- server bootstrap as the source of Zone state;
- existing node state, current-player marker, Lord-entry, and replay semantics;
- the exact canonical names and keys in Section 2.1;
- no app.py, index.html, i18n.js, cinematic_replay.js, sw.js, or
  gameplay-authority changes from this style-lock task;
- no database migration, payment/economy/loadout activation, or Production
  mutation.

## 6. Owner acceptance

The smallest meaningful acceptance set is four representative visual anchors,
one shared presentation boundary, and one audio-continuity decision:

1. **Shared visual system:** approve the style sentence, material/outline/value
   rules, three-layer hierarchy, crop contract, and “one game” progression arc.
2. **Four representative anchors:** approve one representative direction each
   for Zone 3 cave ingenuity, Zone 5 communal fire, Zone 7 geometric curiosity,
   and Zone 10 ancient stillness. These four anchors cover the largest changes
   in material, scale, atmosphere, and negative space; the other four Zones then
   inherit the same grammar with their local contract.
3. **Encounter boundary:** approve that the existing Common/Rare/Elite/
   Battlefield Boss vocabulary remains separate from the explicit Lord
   presentation for all eight Zones.
4. **Audio continuity:** approve one shared motif/palette family for the four
   anchors and the reuse of the locked cast/nonverbal boundaries. Per-cue stem
   production can follow afterward.
5. **Landmark disposition:** acknowledge the current ZONE_LANDMARKS naming
   conflicts in Section 2.2 and authorize a separately owned rebind/replacement
   decision after accepted art exists. This document does not perform that
   mutation.

The following remain separate Owner gates and are not hidden inside this lock:

- final Lord screenplay/audio/art acceptance per Zone;
- any mid-play pause/resume implementation required by Zone 6;
- Zone 10 GO_LOGIC_GATE_01 presentation validation;
- runtime shell wiring and static manifest changes;
- physical-device acceptance;
- any combat, progression, reward, database, shop, equipment, payment, or
  Production operation.

## 7. Validation record for this candidate

The candidate is valid only if the Coordinator’s final report records all of the
following against the exact base in the header:

- canonical Zone 3–10 keys/names/stages/books/Lord metadata cross-checks PASS;
- no conflicting Zone name is introduced by this document;
- all historical/candidate material is explicitly classified and not promoted;
- only this new planning document is changed on the lane branch;
- git diff --name-only -- app.py is empty;
- no gameplay-authority, shell, service-worker, payment, economy, loadout, or
  database path is changed;
- focused document-structure and identity checks PASS;
- no merge, push, deploy, or Production mutation is performed.

**Expected readiness after those checks:** READY_FOR_ART_STYLE_ACCEPTANCE=YES
**Expected readiness before Owner acceptance:** READY_FOR_W1_CONTENT_PRODUCTION=NO
**Candidate status:** STOP_AFTER_REPORT
