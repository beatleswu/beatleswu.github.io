# W1-01 WORLD — Owner-B Style Lock and Zone 3–10 Content Production Specification

**TASK:** W1_01_WORLD_STYLE_B_LOCK_AND_ZONE3_10_CONTENT_PRODUCTION_003
**ASSIGNEE:** CODEX
**TASK CLASS:** WAVE_1_CONTENT_PRODUCTION
**PRIORITY:** P1
**STATUS:** OWNER_APPROVED_DIRECTION_B_PRODUCTION_SPEC
**OWNER DECISION:** GO_ART_STYLE_ACCEPTANCE=GRANTED
**OWNER SELECTED DIRECTION:** B — STYLIZED_ADVENTURE
**AUTHORITATIVE CANONICAL BASE:** 616d51b17abe010de1e862382ca4db7bec65936f
**STYLE LOCK CANDIDATE:** e5943e91c135085b10b7bcd1d1d5603ea3664eab
**CANDIDATE PARENT:** 616d51b17abe010de1e862382ca4db7bec65936f
**ARTWORK GENERATION:** NOT_PERFORMED
**RUNTIME INTEGRATION:** NOT_PERFORMED
**PRODUCTION SCOPE:** bounded planning/manifests only

This is the accepted Direction B production specification for canonical Zones
3–10. It converts the approved visual choice into reusable style rules, exact
per-Zone requirements, content-production paths, audio slots, story beats, and
the WORLD-to-HERO Lord handoff.

No final art or audio files are fabricated by this task. The manifests define
where Owner/ChatGPT visual or audio production may place reviewed source and
runtime derivatives later.

## 1. Canonical identity protection

Current canonical runtime identity is read from app.py ADVENTURE_ZONES and
ADVENTURE_BOSS_META at the supplied base. It outranks historical labels and
presentation filenames.

| Zone | Key | Exact canonical identity | Stage / band | Lord |
|---|---|---|---|---|
| 3 | k16_20 | 哥布林洞穴 / Goblin Cave | LV3 / 16–20級 | goblin_centurion / 哥布林百夫長 / Goblin Centurion |
| 4 | k11_15 | 迷霧森林 / Misty Forest | LV4 / 11–15級 | misty_phantom_rabbit_king / 迷霧幻影兔王 / Misty Phantom Rabbit King |
| 5 | k6_10 | 獸人部落 / Orc Tribe | LV5 / 6–10級 | iron_orc_chieftain / 鋼鐵獸人酋長 / Iron Orc Chieftain |
| 6 | k1_5 | 龍之谷 / Dragon Valley | LV6 / 1–5級 | grand_temple_knight / 聖殿大騎士長 / Grand Temple Knight |
| 7 | d1_2 | 賢者之塔 / Sage Tower | LV7 / 1–2段 | archmage_phantom / 大魔法師幻影 / Archmage Phantom |
| 8 | d3_4 | 魔王城前線 / Demon Castle Front | LV8 / 3–4段 | chaos_lord / 混沌領主 / Chaos Lord |
| 9 | d5_6 | 諸神黃昏 / Ragnarök | LV9 / 5–6段 | fallen_war_god_statue / 墮落戰神古像 / Fallen War-God Statue |
| 10 | d7_plus | 上古終焉神殿 / Ancient Doom Temple | LV10 / 7段＋ | source_of_black_white_order / 黑白秩序之源 / Source of Black-White Order |

The task brief’s English forms are normalized as follows for production safety:
Goblin Caves → Goblin Cave; Mist Forest → Misty Forest; Demon Castle
Frontline → Demon Castle Front; Ragnarok → Ragnarök; Ancient Final Temple →
Ancient Doom Temple. These are request shorthands only. They are
REFERENCE_ONLY for labels and do not authorize a runtime rename.

Canonical books remain unchanged:

- Zone 3: 5哥布林洞穴, 6哥布林巡邏隊
- Zone 4: 7迷霧森林, 8迷霧森林深處
- Zone 5: 9獸人部落, 10獸人角鬥場
- Zone 6: 11飛龍討伐, 12龍之谷守衛
- Zone 7: 13賢者之塔, 14大魔法師試煉
- Zone 8: 15皇家騎士團遠征, 16魔王城前線, 17混沌領主的考驗
- Zone 9: 18諸神黃昏
- Zone 10: 19東方神祕結界, 20上古終焉神殿

## 2. Owner-approved Direction B lock

### 2.1 Shared visual grammar

The lock sentence is:

**A stylized adventure-RPG world with readable silhouettes, simplified but
polished forms, rich controlled color, clear depth layers, approachable
character shapes, and environmental storytelling that grows in scale and drama
from Zone 3 to Zone 10 without losing one-game continuity.**

Required characteristics:

- stylized adventure-RPG presentation;
- readable silhouettes at normal play scale;
- simplified, polished environmental forms;
- rich but controlled colors;
- explicit foreground / midground / background separation;
- mobile portrait, tablet portrait, and tablet landscape readability;
- approachable mood rather than grimdark severity;
- mildly cartoon-stylized monsters and characters where it helps readability;
- environmental storytelling through props, routes, materials, and landmarks;
- immediate Zone recognition through silhouette, material, and composition;
- progressive scale and drama from Zone 3 through Zone 10.

Anti-drift guardrails:

- no photorealistic dark fantasy;
- no muddy low-contrast environment;
- no generic cinematic realism;
- no excessive horror or grimdark treatment;
- no monochromatic purple endgame treatment;
- no unrelated art style between Zones;
- no baked replacement Zone names, gameplay state, reward, price, or
  equipment state inside replaceable art;
- no chess-board substitution for the canonical Go vocabulary;
- no effect, glow, sound, or scale treatment that creates gameplay authority.

Later Zones may be darker, larger, stranger, and more epic. They must retain the
same contour, value grouping, material readability, camera discipline, and
approachable adventure grammar.

### 2.2 Shared palette and material rules

The shared bridge palette is warm ivory, charcoal/ink, deep blue-teal, muted
brass, and controlled natural ground colors. Each Zone adds a primary and
secondary accent, but color never carries state alone.

Use:

- soft upper-left or clearly motivated practical lighting;
- three-value grouping: readable light, form midtone, grounded shadow;
- tactile material cues: stone, wood, cloth, metal, clay, paper, crystal, ash,
  and water;
- dark blue-brown contour language from the accepted Zone 1 baseline;
- warm ivory/charcoal Go stones and muted brass for continuity;
- restrained black/white Go currents only when the screenplay calls for them;
- clear negative space around faces, hands, stones, answer feedback, and nodes.

Avoid:

- surface noise so dense that silhouettes disappear;
- over-bloom that erases color/value separation;
- red/green-only state communication;
- neon cyan/magenta spectacle;
- arbitrary aura colors that imply power tiers or combat status.

### 2.3 Camera, layer, and responsive rules

Every production master has three intentional layers:

1. Background: sky, atmospheric depth, major landform, distant structure, and
   the Zone’s largest identity shape.
2. Midground: route, landmark, practical activity, board/trial place where
   required, and encounter context.
3. Foreground: Hero, Companion, NPC, encounter subject, and one readable prop.

The foreground must not hide the Lord or the primary action. The Zone identity
must survive desaturation and a reduced-motion presentation.

Safe-crop contract:

- 16:9 master keeps the full three-layer read and the route/status lane.
- 9:16 mobile keeps Hero/primary subject, canonical Zone label, and action
  feedback in the center-safe band; secondary depth moves above or behind.
- 4:3 tablet portrait keeps one landmark and the vertical route without a
  stretched desktop panorama.
- 4:3 tablet landscape keeps lateral route, status, current-player marker, and
  the main action lane; it must not crop a Lord, answer feedback, or critical
  dialogue.
- All replaceable art leaves UI clearance for semantic labels and controls.
- Text remains UI text, never a baked image label.

### 2.4 Encounter hierarchy

The visual hierarchy is locked:

MONSTER < ELITE < BATTLEFIELD BOSS < LORD

- Monster: ordinary encounter silhouette and current admitted rarity surface.
- Elite: shared Elite treatment only when current encounter authority admits Elite.
- Battlefield Boss: explicit Battlefield Boss frame, label, and presentation;
  it is not a Lord and does not grant a Zone clear by presentation.
- Lord: separate Lord Trial/cinematic composition with canonical Lord identity,
  stronger ritual/scale/quiet, and server-backed entry.

No Lord may be implemented as a scaled Battlefield Boss. No visual hierarchy
change modifies combat, progression, reward, retry, or eligibility authority.

### 2.5 Motion and accessibility

Ambient motion is slow, sparse, and subordinate to information. Reduced motion
removes camera push, parallax sweeps, rapid particles, screen shake, repeated
flashes, and nonessential idles while preserving state, timing, focus, captions,
and visible feedback.

Every production pack must provide:

- visible equivalent for dialogue or meaningful audio;
- readable non-color distinction for state and encounter hierarchy;
- semantic name/alt description for nondecorative art;
- captions/transcripts for meaningful dialogue or SFX;
- focus-safe UI clearance;
- no flashing or rapid luminance pattern;
- no critical identity, answer, route, reward, or Lord state conveyed only by
  audio, motion, darkness, or color.

## 3. Exact Zone 3–10 production specifications

The following specifications are the content source for the environment and
audio manifests in this packet. Narrative beats remain bounded by
docs/planning/e10_final_screenplay_v1.md; this document does not invent a new
storyline or alter gameplay.

### Zone 3 — 哥布林洞穴 / Goblin Cave

| Field | Specification |
|---|---|
| VISUAL_IDENTITY | Bright, clever cave adventure: inhabited limestone, practical goblin movement, resourcefulness, and a first mature moral turn from raid expectation to negotiated trust. |
| PRIMARY_PALETTE | Limestone cream, charcoal teal, lantern amber, moss green. |
| SECONDARY_PALETTE | Copper, warm ivory, muted berry red, damp blue-gray. |
| ENVIRONMENT_MOTIFS | Cave mouth, fleeing supplies, lantern pools, rope bridges, storage alcoves, echo pockets, fungus, ore, and the natural Go-board wall. |
| ARCHITECTURE | Layered limestone chambers and improvised routes; a believable occupied settlement with a visually reserved last door, not a raid dungeon. |
| LIGHTING | Warm lantern pools against cool cave shafts; readable recesses and soft reflected amber; no horror blackout. |
| GROUND_MATERIALS | Worn limestone, packed cave dust, smooth worn stone, rope shadow, damp mineral patches. |
| FOREGROUND_ELEMENTS | Hero, Companion, one lantern or supply prop, Grik at eye level, and later the Centurion’s planted spear. |
| BACKGROUND_LANDMARK | Cave-mouth route and last door; proposed replacement landmark path is assets/e10/art/zone3/environment/zone3_map_landmark.webp. Existing zone-03-goblin-cave.webp remains reverify-before-admission. |
| MONSTER_PRESENTATION_LANGUAGE | Crouched, angular, asymmetrical, tool-aware silhouettes; mildly cartoon-stylized faces; copper/amber accents; no gore or disposable enemy framing. |
| ELITE_PRESENTATION_LANGUAGE | Sharper angular silhouette, disciplined lantern accent, and shared Elite label/frame only when the current encounter admits Elite. |
| BATTLEFIELD_BOSS_PRESENTATION_LANGUAGE | Larger cave silhouette with the shared explicit Battlefield Boss frame and label; never use Goblin Centurion or a Lord ritual frame. |
| LORD_PRESENTATION_LANGUAGE | goblin_centurion / Goblin Centurion: still, level-angle, spear planted, “last door” identity; ceasefire and trust are the resolution, not a kill trophy. |
| ENTRY_BEAT | Goblins flee with supplies; Hero restrains the Wooden Sword; Grik explains they are moving again. The entry makes “retreat, not raid” legible before gameplay. |
| CLEAR_BEAT | Ceasefire is shown through action, then Grik hands over the Stone Shard. The cave faction is not destroyed and the shard is not a magical pointer. |
| REPLAY_STATE | Revisit lantern route, Grik, last door, and handoff staging without a repeat Stone Shard grant, reward, star, or unlock. |
| BGM_DIRECTION | Tense low folk instrument, dry plucked texture, light hand percussion, and a quiet resolution instead of a victory fanfare. |
| AMBIENCE | Cave air, fading footsteps, lantern hiss, distant calls, rope tension, and settling stone. |
| SFX_DIRECTION | Footfalls, rope creak, supply movement, lantern metal, stone-board contact, and restrained stone-on-stone handoff. |
| NARRATIVE_TONE | Retreat, not raid; curiosity and negotiated trust; cave residents retain agency. |
| MOBILE_READABILITY_RULE | Keep Hero, one lantern/supply route, and one readable cave landmark in the center-safe band; move bridges and distant silhouettes behind the subject. |
| TABLET_READABILITY_RULE | Preserve lateral route and last-door depth in both tablet orientations; retain one foreground prop without flattening the cave into a tunnel. |

### Zone 4 — 迷霧森林 / Misty Forest

| Field | Specification |
|---|---|
| VISUAL_IDENTITY | Approachable mystery without menace: fog creates uncertainty while natural anchors and the Water Spirit Horse create trust. |
| PRIMARY_PALETTE | Deep teal, moss green, lavender fog, muted moon gold. |
| SECONDARY_PALETTE | Fern green, warm ivory, soft rose, wet blue-gray. |
| ENVIRONMENT_MOTIFS | Fern paths, moon pools, old trunks, hanging vines, soft clearings, fog layers, and a stable route marker. |
| ARCHITECTURE | Natural gates, root arches, stone markers, and a moon-pool clearing; no historical Twilight Forest label or horror shrine. |
| LIGHTING | Soft moon-gold path through lavender haze; warm face/cloth fill against cool mist; fog edge remains readable. |
| GROUND_MATERIALS | Damp soil, moss, roots, wet stone, leaf litter, and shallow reflective water. |
| FOREGROUND_ELEMENTS | Hero, Water Spirit Horse, a fern/stone route marker, and controlled phantom-copy silhouettes in later beats. |
| BACKGROUND_LANDMARK | Moon pool or fern-ring grove; proposed path assets/e10/art/zone4/environment/zone4_map_landmark.webp. Current zone-04-twilight-forest.webp is REFERENCE_ONLY. |
| MONSTER_PRESENTATION_LANGUAGE | Long tails, leaf crests, soft asymmetry, quiet movement, and readable silhouettes; phantom copies are presentation compositing, never duplicate combat authority. |
| ELITE_PRESENTATION_LANGUAGE | Clearer leaf/antler silhouette, moon-gold edge, and shared Elite label/shape; no horror face treatment. |
| BATTLEFIELD_BOSS_PRESENTATION_LANGUAGE | Shared explicit Battlefield Boss frame and label emerging from mist; do not use a phantom copy or Rabbit King staging. |
| LORD_PRESENTATION_LANGUAGE | misty_phantom_rabbit_king / Misty Phantom Rabbit King is voice-led and partly obscured or voice-only where scripted; no human villain pose or defeat speech. |
| ENTRY_BEAT | Fog swallows the route; the Water Spirit Horse remains stable. The protected line 小水。帶我走。 is visible/captioned, not audio-only. |
| CLEAR_BEAT | Fog opens to the Black/White Fruit and a safe path. The forest remains alive; no extermination card or Lord defeat speech. |
| REPLAY_STATE | Replay fog, riddle rhythm, route reveal, and fruit presentation without repeat fruit acquisition, reward, star, or unlock. |
| BGM_DIRECTION | Sparse breathy woodwind, warm glassy tones, an uneasy dissonance for copies, and a clear trust note. |
| AMBIENCE | Leaves, damp footfalls, distant water, fog movement, moon-pool air, and separated creature/voice layers. |
| SFX_DIRECTION | Soft leaves, wet steps, moon-pool chimes, restrained copy whispers, and no jump-scare sting. |
| NARRATIVE_TONE | Trust, not out-calculation; uncertainty invites observation and cooperation. |
| MOBILE_READABILITY_RULE | Keep Hero, Water Spirit Horse, and stable route marker together; use mist as a side/depth layer, never a full-screen veil. |
| TABLET_READABILITY_RULE | Portrait keeps a trunk/fern anchor and moon-pool depth; landscape retains enough fog layers to show a route without shrinking characters. |

### Zone 5 — 獸人部落 / Orc Tribe

| Field | Specification |
|---|---|
| VISUAL_IDENTITY | Warm communal frontier of craft, work, respect, and spectacle; strength is broad and approachable, not a hateful caricature. |
| PRIMARY_PALETTE | Terracotta, red clay, ochre, ember, dark teal, cream. |
| SECONDARY_PALETTE | Bronze, hide brown, charcoal smoke, muted blue, warm ivory. |
| ENVIRONMENT_MOTIFS | Circular arena, drum circles, banners, forge, Smith-Elder, basalt, axe marks, and a northward route. |
| ARCHITECTURE | Clan arena, forge/workshop, basalt shelves, banners, and practical settlement structures; the arena is social before combative. |
| LIGHTING | Warm fire and ember practicals with cool open-air fill; controlled heat shimmer, no permanent angry-red wash. |
| GROUND_MATERIALS | Red clay, compact dust, basalt, worn timber, leather, bronze, and ash around the forge. |
| FOREGROUND_ELEMENTS | Hero, Chieftain, Smith-Elder, axe, corrupted ore, and one readable arena/forge prop. |
| BACKGROUND_LANDMARK | Arena ring plus forge/banner gate; proposed path assets/e10/art/zone5/environment/zone5_map_landmark.webp. Current zone-05-sky-tower.webp is REFERENCE_ONLY. |
| MONSTER_PRESENTATION_LANGUAGE | Broad shoulders, horns, shields, chunky feet, hide/leather/wood/bronze craft details; no realistic warfare or hateful “evil orc” code. |
| ELITE_PRESENTATION_LANGUAGE | Deliberate stance, crafted bronze/hide detail, shared Elite label/frame, and shape/material distinction rather than red-only signaling. |
| BATTLEFIELD_BOSS_PRESENTATION_LANGUAGE | Public arena scale with the shared explicit Battlefield Boss presentation when currently admitted; never Chieftain Lord framing and never implied Zone clear. |
| LORD_PRESENTATION_LANGUAGE | iron_orc_chieftain / Iron Orc Chieftain is respected. Voluntary axe release and northward clue are the resolution; no kneel-as-humiliation, death, or trophy. |
| ENTRY_BEAT | Drums and crowd lead Hero into the arena; the Smith-Elder’s corrupted-ore warning precedes confrontation. Zone 2 Corrupted Crystal Fragment and ore remain Corruption Evidence. |
| CLEAR_BEAT | The pillar mark and voluntary axe release communicate earned respect. The Smith-Elder gives geographic information; ore is not a magical pointer. |
| REPLAY_STATE | Replay arena rhythm, Smith-Elder warning, and respect exchange without repeat ore acquisition, reward, star, or unlock. |
| BGM_DIRECTION | Layered communal percussion and low strings with call-and-response; widen on respect, never as a kill fanfare. |
| AMBIENCE | Crowd murmur, forge, wind, fire, drum preparation, leather movement, and open-air dust. |
| SFX_DIRECTION | Drums, forge strikes, leather/wood/bronze handling, measured steps, axe whoosh, grounded axe impact, and pillar carving. |
| NARRATIVE_TONE | Earned respect, not humiliation; powerful community with its own values and a corruption warning. Preserve 我不知道。 where scripted. |
| MOBILE_READABILITY_RULE | Keep Hero and the Chieftain/Smith-Elder focal exchange in the center-safe grouping; move crowd and banners to shallow side depth. |
| TABLET_READABILITY_RULE | Preserve arena circle and forge/route relation in portrait; landscape keeps crowd scale without competing with dialogue/action. |

### Zone 6 — 龍之谷 / Dragon Valley

| Field | Specification |
|---|---|
| VISUAL_IDENTITY | High sky/fire valley where imposing order is questioned through height, wind, heat, and an engineered boundary. |
| PRIMARY_PALETTE | Cobalt sky, ember, gold, volcanic plum, basalt smoke. |
| SECONDARY_PALETTE | Crystal blue, rope tan, warm ivory, ash gray, muted copper. |
| ENVIRONMENT_MOTIFS | Cliffs, lava seams, crystal nests, rope bridges, wind tunnels, wyverns, ruined watchtower, command tower, and background dragon-engraved Go jar. |
| ARCHITECTURE | Severe cliff/command tower, ruined watchtower, bridges, and boundary structures; no royal-castle substitution. |
| LIGHTING | High-altitude cobalt and ember practicals with transparent smoke; crystal highlights are sparse and controlled. |
| GROUND_MATERIALS | Basalt, ash, lava glass, weathered stone, rope, iron, and crystal. |
| FOREGROUND_ELEMENTS | Hero, warming Zone 5 ore, boundary line, Grand Temple Knight, and later Dragon Scale. |
| BACKGROUND_LANDMARK | Cliff/bridge/heat-haze/tower landmark; proposed path assets/e10/art/zone6/environment/zone6_map_landmark.webp. Current zone-06-royal-castle.webp is REFERENCE_ONLY. |
| MONSTER_PRESENTATION_LANGUAGE | Wings, horns, tails, triangles, airborne diagonals, scale, basalt, crystal, ember glass, and rope; no deity or final Boss dragon silhouette. |
| ELITE_PRESENTATION_LANGUAGE | Sharper wing/horn silhouette and controlled ember edge with shared Elite label; never resemble Grand Temple Knight. |
| BATTLEFIELD_BOSS_PRESENTATION_LANGUAGE | Grounded large creature/encounter silhouette with explicit Battlefield Boss label; no Knight, Lord frame, or dragon deity substitution. |
| LORD_PRESENTATION_LANGUAGE | grand_temple_knight / Grand Temple Knight is a composed Lord boundary. No death animation, no corpse, no resolved final fate; fate remains intentionally unresolved. |
| ENTRY_BEAT | Zone 5 ore warms at the valley boundary. “No one can approach” is staged as a character/order boundary, not a newly invented unlock rule. |
| CLEAR_BEAT | Preserve the command question and lines 那你和我，有什麼不同？ and 命令沒有改。 Dragon Scale enters the Journey Relic chain through the authored boundary, not Boss loot or a magical pointer. |
| REPLAY_STATE | Replay boundary conversation and ore/wind resonance without repeat Dragon Scale grant; MID_PLAY pause/resume remains a separate runtime capability gate. |
| BGM_DIRECTION | High open-air drones, sparse frame drums, bowed metal/strings, and a disciplined pulse that can fracture into silence. |
| AMBIENCE | Wind shear, distant wyverns, smoke lift, rope tension, crystal air, and low heat rumble. |
| SFX_DIRECTION | Wind, rope strain, wing beats, basalt/metal contact, heat rumble, restrained crystal resonance, and unspectacular boundary strike. |
| NARRATIVE_TONE | Order without exception, questioned; authority is a relationship/boundary, not a kill target. |
| MOBILE_READABILITY_RULE | Keep Hero and boundary in the safe center; use cliffs and height as a vertical backdrop, never crop the route marker or face. |
| TABLET_READABILITY_RULE | Portrait retains cliff/bridge verticality and tower edge; landscape restores wind-tunnel depth and ore/character relation. |

### Zone 7 — 賢者之塔 / Sage Tower

| Field | Specification |
|---|---|
| VISUAL_IDENTITY | Geometric curiosity and spellcraft expressed as learning, evidence, and synthesis; welcoming wonder rather than haunted wizard horror. |
| PRIMARY_PALETTE | Indigo, parchment, brass, cyan, violet. |
| SECONDARY_PALETTE | Ink charcoal, warm ivory, ceramic, muted rose, star white. |
| ENVIRONMENT_MOTIFS | Spiral stair, floating rooms, library, brass observatory, star windows, suspended boards, paper, cloth, and crystal. |
| ARCHITECTURE | Vertical tower of spiral stairs, observatory, library shelves, suspended platforms, and open star windows; no star-sea passage label. |
| LIGHTING | Crisp star-window shafts and warm brass bounce; controlled cyan/violet without spectacle. |
| GROUND_MATERIALS | Worn stone stair, wood, ceramic tile, brass platform, paper, cloth, and crystal. |
| FOREGROUND_ELEMENTS | Hero, board, four Journey Relic memories, Archmage, and forming Heartstone. |
| BACKGROUND_LANDMARK | Spiral tower and star-window landmark; proposed path assets/e10/art/zone7/environment/zone7_map_landmark.webp. Current zone-07-star-sea-passage.webp is REFERENCE_ONLY. |
| MONSTER_PRESENTATION_LANGUAGE | Geometric, levitating, page/ring/stacked silhouettes using ink, paper, brass, crystal, ceramic, and cloth; no Spirit clones or horror. |
| ELITE_PRESENTATION_LANGUAGE | More coherent ring/page geometry and controlled brass edge with shared Elite label; glow alone cannot signal rank. |
| BATTLEFIELD_BOSS_PRESENTATION_LANGUAGE | Distinct hostile structure/creature with shared Battlefield Boss label; separate from Archmage Phantom and Heartstone formation. |
| LORD_PRESENTATION_LANGUAGE | archmage_phantom / Archmage Phantom is a conceptual knowledge presence, not a Spirit clone or generic wizard portrait. |
| ENTRY_BEAT | Hero climbs into a star-lit vertical reveal; Archmage meets the arrival without a lecture; the star-board transformation becomes the Zone’s core image. |
| CLEAR_BEAT | Heartstone forms and remembers only the four Journey Relics: Wooden Sword, Stone Shard, Black/White Fruit, Dragon Scale. No physical relic is consumed. |
| REPLAY_STATE | Replay formation as a readable relationship diagram without repeat acquisition/fusion reward; eligibility remains server/state-owned. |
| BGM_DIRECTION | Sparse arpeggiated strings/keys, warm brass, high quiet room tone, and a four-chime convergence at formation. |
| AMBIENCE | Tower air, paper, distant star resonance, soft footsteps, brass/ceramic movement, and suspended dust. |
| SFX_DIRECTION | Footsteps, paper lift, ceramic, brass gear, soft stone placement, harmonic resonance, and one clear Heartstone formation cue. |
| NARRATIVE_TONE | The Heartstone forms; knowledge is relational and playable. Preserve 可棋不是考卷。 |
| MOBILE_READABILITY_RULE | Center Hero, board, and Heartstone in a vertical stack; place spiral depth above/below; never reduce formation to an unreadable particle effect. |
| TABLET_READABILITY_RULE | Portrait keeps stair spiral and central board; landscape adds one library/observatory context without shrinking the formation. |

### Zone 8 — 魔王城前線 / Demon Castle Front

| Field | Specification |
|---|---|
| VISUAL_IDENTITY | Organized frontier under pressure: large threat, practical resistance, and human-scale agency rather than demon-horror spectacle. |
| PRIMARY_PALETTE | Navy, rust, ash, charcoal, muted signal blue, controlled signal red. |
| SECONDARY_PALETTE | Camp amber, iron, warm ivory, rope tan, smoke gray. |
| ENVIRONMENT_MOTIFS | Fortifications, moat, broken gate, supply yard, signal towers, blue flag, black spire, and march line. |
| ARCHITECTURE | Working frontline of gates, walls, yards, bridges, and signal routes; preserve Serel’s command space. |
| LIGHTING | Navy/ash open-air light with camp amber and restrained signal red; black spire is a shape, not an all-consuming void. |
| GROUND_MATERIALS | Packed earth, broken stone, timber, iron, leather, rope, ash, and signal cloth. |
| FOREGROUND_ELEMENTS | Hero, Serel, blue flag, one stabilizing stone, and the living-rune Chaos Lord. |
| BACKGROUND_LANDMARK | Gate/signal-tower/frontline landmark; proposed path assets/e10/art/zone8/environment/zone8_map_landmark.webp. Current zone-08-abyssal-forge.webp is REFERENCE_ONLY. |
| MONSTER_PRESENTATION_LANGUAGE | Plated, wedge, shield, and organic-mechanical silhouettes; obsidian/iron/leather/rope/signal cloth; no final-Lord regalia for ordinary monsters. |
| ELITE_PRESENTATION_LANGUAGE | Organized wedge/plate silhouette and compact signal accent with shared Elite label; ordinary soldiers do not become Chaos Lord authority. |
| BATTLEFIELD_BOSS_PRESENTATION_LANGUAGE | Separate heavy battlefield silhouette and explicit label; never Chaos Lord and never the dissolution resolution. |
| LORD_PRESENTATION_LANGUAGE | chaos_lord / Chaos Lord is a living rune. One placed stone stabilizes distortion; the Lord dissolves, not falls or dies. CHAOS_LORD_KILLED_BY_HERO=FALSE. |
| ENTRY_BEAT | War-scale march and Serel’s blue-flag command establish functioning agency. Heartstone may reveal relationships but never command people or army. |
| CLEAR_BEAT | Stabilization gathers the rune distortion; Chaos Lord dissolves and Serel remains commander. The front restores agency rather than displaying a conquest trophy. |
| REPLAY_STATE | Replay march, stabilization, and dissolution without repeat stone, reward, star, or progression grant; retain nonlethal Lord resolution. |
| BGM_DIRECTION | Percussive march, restrained low brass, and harmonic distortion resolving into open air; dialogue remains intelligible. |
| AMBIENCE | Boots, supply yard, flags, rope, gate strain, marching column, ash, and distant fire. |
| SFX_DIRECTION | Boots, leather/metal, signal horn, rope, gate strain, rune vibration, placed stone, and clean stabilization release. |
| NARRATIVE_TONE | Pressure and organized resistance; agency and relationships remain human/agentic. |
| MOBILE_READABILITY_RULE | Keep Hero, Serel/signal lane, and stabilization action centered; march and spire become vertical side depth. |
| TABLET_READABILITY_RULE | Portrait retains gate/signal tower; landscape shows fortification route and march scale without pushing Serel or Lord resolution to the edge. |

### Zone 9 — 諸神黃昏 / Ragnarök

| Field | Specification |
|---|---|
| VISUAL_IDENTITY | Mythic weather and broken order with a readable human choice at the center; cosmic scale without opaque cosmic horror. |
| PRIMARY_PALETTE | Dusk purple, storm cyan, moon white, restrained gold. |
| SECONDARY_PALETTE | Ash gray, bronze, cloud glass, storm silk, warm skin/cloth. |
| ENVIRONMENT_MOTIFS | Storm temple, aurora bridge, fractured monument, cloud shelf, settled ash, and fallen war-god statue. |
| ARCHITECTURE | Fractured storm temple, ancient platforms, cloud shelves, and broken monuments; not a generic eternal-night shrine. |
| LIGHTING | Broad dusk/weather layers with sparse lightning punctuation; no constant flashes or purple wash. |
| GROUND_MATERIALS | Settled ash, cracked stone, bronze, starstone, cloud glass, and moon-metal fragments. |
| FOREGROUND_ELEMENTS | Hero, choice boundary, statue, controlled illusion silhouettes, and the living black/white stones. |
| BACKGROUND_LANDMARK | Fractured monument/storm-temple landmark; proposed path assets/e10/art/zone9/environment/zone9_map_landmark.webp. Current zone-09-eternal-night-shrine.webp is REFERENCE_ONLY. |
| MONSTER_PRESENTATION_LANGUAGE | Tall, cosmic, orbiting silhouettes using starstone, bronze, cloud glass, storm silk, and moon metal; no deity copies or body horror. |
| ELITE_PRESENTATION_LANGUAGE | Precise orbit/storm-silk silhouette with shared Elite label; no god mask or Lord regalia and no cyan-only distinction. |
| BATTLEFIELD_BOSS_PRESENTATION_LANGUAGE | Separate statue/creature threat with shared explicit Battlefield Boss treatment; scale does not make the war-god a Boss or Lord automatically. |
| LORD_PRESENTATION_LANGUAGE | fallen_war_god_statue / Fallen War-God Statue presents ancient memory and sincere exhaustion; no kill and no Final Stone/Heartstone consumption in Zone 9. |
| ENTRY_BEAT | Settled ash and ancient grief lead into a memory of well-intentioned over-correction; the Zone begins quietly, not as a continuation of the battlefield fight. |
| CLEAR_BEAT | Hero refuses to take choice away; the single-color overlay destabilizes as consequence, not as magical destruction. Preserve protected lines and no five-relic narration. |
| REPLAY_STATE | Replay memory/choice sequence without final-stone consumption or progression mutation; replay is not a second moral choice that rewrites state. |
| BGM_DIRECTION | Wide low strings, serene choral air without lyrical text, sparse bell/metal, and deliberate silence around the choice. |
| AMBIENCE | Settled ash, distant rain, broad wind, sparse thunder, monument creak, and quiet breath/footstep. |
| SFX_DIRECTION | Wind, stone fracture, cloth snap, glass-shard chime, statue grind, overlay instability, and no impact-only choice cue. |
| NARRATIVE_TONE | THE CHOICE: responsibility without domination; grief becomes a conversation, not a boss kill. |
| MOBILE_READABILITY_RULE | Keep Hero and choice boundary central; crop weather/aurora laterally before face, protected dialogue, or statue relationship. |
| TABLET_READABILITY_RULE | Portrait keeps vertical monument and storm shelf; landscape opens aurora bridge/statue depth while preserving dialogue/action. |

### Zone 10 — 上古終焉神殿 / Ancient Doom Temple

| Field | Specification |
|---|---|
| VISUAL_IDENTITY | Ancient ending and still collectible: tactile temple, measured negative space, quiet mechanism, and a final move rather than a kill spectacle. |
| PRIMARY_PALETTE | Ivory, obsidian, muted gold, quiet violet, soft stone gray. |
| SECONDARY_PALETTE | Weathered black/white, dust beige, lotus green, restrained blue, ordinary earth brown. |
| ENVIRONMENT_MOTIFS | Temple stone, void windows, time scars, silent courtyards, lotus pond, guardian archway, nested gates, open gate, ordinary stone. |
| ARCHITECTURE | Ancient temple court, nested geometry, void windows, archways, and mechanism spaces; no Origin Core or replacement endgame name. |
| LIGHTING | Soft controlled shafts, strongest contrast at the open gate/logic relation, no constant glow or purple endgame wash. |
| GROUND_MATERIALS | Ancient stone, obsidian, ivory, dust, muted gold, quiet violet, grass, and ordinary earth. |
| FOREGROUND_ELEMENTS | Hero, ordinary/final stone, open gate/mechanism, lotus/guardian gesture; Source remains non-character. |
| BACKGROUND_LANDMARK | Open-gate temple landmark; proposed path assets/e10/art/zone10/environment/zone10_map_landmark.webp. Current filename aligns, but legacy “Ancient Omega Temple” tier label is REFERENCE_ONLY. |
| MONSTER_PRESENTATION_LANGUAGE | Monolith, shell, gate, and nested-geometry silhouettes; no gore, Spirit copies, or Lord/Boss replicas. |
| ELITE_PRESENTATION_LANGUAGE | More complex nested silhouette and quiet gold edge with shared Elite label; geometry never creates combat authority. |
| BATTLEFIELD_BOSS_PRESENTATION_LANGUAGE | Distinct grounded threat with explicit Battlefield Boss label; never Source of Black-White Order or silent guardian authority. |
| LORD_PRESENTATION_LANGUAGE | source_of_black_white_order / Source of Black-White Order is a silent mechanism/logic relationship: FACE=NONE, VOICE=NONE, DIALOGUE=NONE, PERSONALITY=NONE. No humanoid canonical face or voice. |
| ENTRY_BEAT | Dream/lotus/guardian silence leads to a mechanism vision. GO_LOGIC_GATE_01=OPEN is the open-gate condition; no invented board state. |
| CLEAR_BEAT | Final move resolves to half-point with winning color unspecified; Heartstone becomes an ordinary stone. No THROWN, DESTROYED, REMOVED, or SPENT_AS_GONE state. 走吧。 remains the final spoken line at the canonical shot. |
| REPLAY_STATE | Quiet revisit with no stone consumption, reward duplication, or altered final state. Skip still leaves a complete visible final-state summary. |
| BGM_DIRECTION | Minimal temple air, low sustained tone, sparse single-note piano/stone resonance, and deliberate near-silence; Source has no voice. |
| AMBIENCE | Courtyard air, lotus/water, dust, distant stone, quiet cloth, and ordinary daylight/birdsong in the exit. |
| SFX_DIRECTION | Gate mechanism, stone contact, crystal crack, ordinary stone placement, soft courtyard air, and a clean quiet tail; no explosive final sting. |
| NARRATIVE_TONE | THE FINAL MOVE: stop over-correction, accept the open logic gate, and continue. |
| MOBILE_READABILITY_RULE | Keep Hero, open gate/mechanism, and ordinary final stone in a central vertical read; negative space is intentional, not missing content. |
| TABLET_READABILITY_RULE | Portrait preserves nested gate depth and central stone; landscape widens courtyard/void window without turning the Source into a character. |

## 4. Bounded production structure

The following files are created by this candidate. They are planning/manifest
artifacts only; no target art or audio file is created here.

| Deliverable | File | Status |
|---|---|---|
| Owner-B visual lock and exact Zone specs | docs/planning/w1_01_world_style_b_lock_and_zone_content_production_v1.md | OWNER_APPROVED_DIRECTION_B |
| Environment asset-production manifest | docs/planning/w1_01_world_zone_environment_asset_manifest_v1.json | MANIFEST_READY_ARTWORK_NOT_GENERATED |
| Audio-production manifest | docs/planning/w1_01_world_audio_production_manifest_v1.json | MANIFEST_READY_AUDIO_NOT_GENERATED |
| Story/onboarding beat manifest | docs/planning/w1_01_world_story_onboarding_beat_manifest_v1.json | BEAT_SPEC_READY_WIRING_DEFERRED |
| WORLD ↔ HERO Lord dependency manifest | docs/planning/w1_01_world_hero_lord_dependency_manifest_v1.json | DEPENDENCY_SPEC_READY_ASSETS_PENDING |

### 4.1 Environment file convention

For each Zone, the environment manifest reserves:

- one Owner source master PNG;
- one runtime WebP derivative after source acceptance;
- one map landmark source/runtime pair;
- one entry backplate source/runtime pair;
- one clear backplate source/runtime pair;
- one replay backplate source/runtime pair;
- one conditional Battlefield Boss context pair only if the current runtime
  encounter surface admits such a presentation.

All production masters carry crop-safe metadata for 16:9, 9:16, 4:3 portrait,
and 4:3 landscape. The current landmark references in js/e9/world_stage.js are
held as evidence and are not rebound by this task.

### 4.2 Audio file convention

For each Zone, the audio manifest reserves:

- discovery, escalation, and recovery BGM slots;
- primary and recovery ambience slots;
- entry, encounter, Battlefield Boss, and clear SFX slots;
- Lord emergence, Lord resolution, and Lord failure SFX slots;
- shot/beat dialogue paths in zh-TW and en when the accepted screenplay has
  dialogue for that shot/beat.

No new dialogue text is invented. Dialogue production must use the accepted
screenplay and the locked cast boundary. Water Spirit Horse remains nonverbal.
Meaningful audio always has a visible equivalent.

## 5. Exact ownership and integration boundaries

### 5.1 This task owns

Codex may create and update only the five new docs/planning files listed in
Section 4 on this branch. This task owns:

- Direction B style rules and anti-drift checks;
- canonical Zone identity normalization for content production;
- environment and audio target path conventions;
- story/onboarding beat handoff specification;
- WORLD-to-HERO Lord dependency contract;
- classification of unaccepted/historical landmark references.

### 5.2 Owner/production lanes own

- Owner/ChatGPT visual production owns source artwork generation and visual
  acceptance. No final art is fabricated in this task.
- Audio production owns source recording/generation, audition, bilingual lock,
  source SHA-256, and runtime derivative selection.
- HERO owns player/Companion presentation assets, Lord portrait/cutout
  production, and its own character manifest. A World spec never creates a
  player appearance, equipment, loadout, or combat class.
- A later static/asset lane owns packaging accepted source and runtime
  derivatives through the reviewed release process.
- A later runtime/world-stage lane owns any landmark rebind or presentation
  consumption after separate review.

### 5.3 Explicitly out of scope

The following paths and systems are unchanged and remain prohibited in this
task:

- app.py;
- index.html;
- i18n.js;
- js/game/cinematic_replay.js;
- sw.js;
- js/e9/world_stage.js;
- components/adventure/world_stage.html;
- combat, progression, unlock, Lord eligibility, Lord retry, or reward logic;
- database schema/migrations or persistence;
- Shop, equipment, loadout, payment, Premium, or revenue authority;
- production files, deployment commands, merges, pushes, and Production state.

The style and manifests do not change server ownership. In particular:

Monster defeat != Zone clear
Battlefield Boss != Lord
Acquire != Equip
Purchase != Equip
Acquire != Consume
Replay != second reward

## 6. Integration contracts

### 6.1 World-stage handoff

A future consumer may bind accepted environment art only through the exact
server-projected zone key. It must use:

- current_zone_key as current-player authority;
- server bootstrap name/status/entry permission;
- selected node only as ephemeral UI selection;
- shared E10 node/state assets;
- semantic labels outside art;
- the exact identities in Section 1.

No manifest path is a runtime path until the corresponding source is Owner
accepted, runtime derivative is hash-verified, and a later integration lane is
authorized.

### 6.2 Lord handoff

The Lord dependency manifest uses the same six presentation roles as the
existing Zone 2 package shape: ritual key art, challenge backplate, failure
backplate, first-star success backplate, Lord portrait, and success Lord
portrait. The roles are visual surfaces, not reward authority.

The World lane supplies canonical Lord identity, environment, narrative/fate
constraints, crop-safe composition, and entry/clear/replay intent. The Hero lane
supplies Hero/Companion cutouts and any accepted character presentation
surfaces. The runtime Lord surface must keep the Lord above Battlefield Boss in
presentation hierarchy without changing Lord rules.

### 6.3 Story and journey handoff

The story manifest separates:

- current screenplay beats;
- new content-production beat slots;
- onboarding spine requirements;
- shell/runtime wiring work;
- reward-idempotency conditions.

The first-session journey remains Opening → World reveal → Hero/Companion
introduction → first Adventure action → first board/question → feedback →
attack/hit → victory → reward reveal → canonical appearance explanation →
XP/growth → next action → progression → Zone 3 arrival. This packet specifies
the content but does not edit shared shell files or wire the journey.

Zone 6 true MID_PLAY pause/resume, Zone 7 compositing, and Zone 10
GO_LOGIC_GATE_01 are explicitly separate engineering gates. Their content is
specified here without claiming implementation.

## 7. Validation contract

The Coordinator’s final report must prove:

- ALL_8_CANONICAL_ZONE_IDENTITIES_EXACT=YES;
- OWNER_STYLE_B_PRESERVED=YES;
- PHOTOREALISTIC_DRIFT=NO;
- GRIMDARK_DRIFT=NO;
- MONOCHROMATIC_PURPLE_DRIFT=NO;
- LORD_BOSS_SEPARATION_DEFINED=YES;
- ZONE10_CANONICAL_IDENTITY_PRESERVED=YES;
- GAMEPLAY_AUTHORITY_CHANGED=NO;
- APP_PY_CHANGED=NO;
- RUNTIME_PRODUCT_FILES_CHANGED=NO;
- only the five explicit planning/manifest paths changed;
- all JSON manifests parse;
- all target asset paths are marked proposed/not generated;
- no merge, deploy, push, or Production mutation occurred.

**READY_FOR_ZONE_ASSET_PRODUCTION:** YES — exact Direction B spec and paths are
ready; final artwork still requires Owner/visual-production execution and
acceptance.

**READY_FOR_HERO_LORD_PRODUCTION:** YES — exact World/Hero dependency roles and
canonical Lord identities are ready; character assets remain pending production.

**READY_FOR_AUDIO_PRODUCTION:** YES — exact track slots, directions, voice
boundaries, and beat path convention are ready; audio files remain pending
production.

**READY_FOR_JOURNEY_WIRING:** NO — content is specified, but shared shell and
runtime wiring are separately owned and prohibited here.

**STATUS:** STOP_AFTER_REPORT
