# M001-M120 Owner-Approved Exact Art/Content Zone Assignment V1

Status: OWNER_APPROVED_CANONICAL_ART_CONTENT_PLANNING

This is the F035 frozen planning contract for all M001-M120. Its scope is ART_CONTENT_PLANNING_ONLY. It is not gameplay Zone authority, encounter authority, combat authority, MonsterCatalog authority or runtime mapping authority.

## Fresh authority and lineage

- Current origin master: 574b3eeb9641c48676e95d3744d204dffca1e1fa
- F035 base SHA: 574b3eeb9641c48676e95d3744d204dffca1e1fa
- F033 count lock: 214fd1961c60c2325ce4d906af2bf01ee0787798
- F034 initial exact proposal: ea6458318e73f9ef81ce0b6083a0a4729a05f994
- F034-R1 replacement packet: 62e060961dfed0766763240bdea044a686c8d232
- F034-R2 final candidate packet: 6447bc965c201042e0023400c324f877cd5bb09e
- ART002 identity reference: 3e7034ef71c27ca00acf456d03f95301f30b8c64
- ART002 old distribution status: SUPERSEDED_FOR_ART_CONTENT_PLANNING

## Final count contract

| Zone | Count | Art/content theme |
|---|---:|---|
| Z1 | 14 | Terraced village and garden welcome; readable early field ecology. |
| Z2 | 14 | Open plains, ponds, meadow motion, insects and water-edge life. |
| Z3 | 13 | Cave and ore ecology; goblin, fungus, stone and subterranean craft. |
| Z4 | 12 | Mist forest; sprites, woodland animals, vines, moss and flowers. |
| Z5 | 12 | Tribal frontier and clay camp; herd, drum, banner and campfire motifs. |
| Z6 | 12 | Sky-and-fire dragon valley; wyverns, lava, crystal and aerial motion. |
| Z7 | 12 | Tower/library alchemy; spellcraft, constructs, observatory and familiars. |
| Z8 | 11 | Fortified frontier under pressure; gates, siege forms, scouts and armor. |
| Z9 | 10 | Mythic storm and celestial weather; stars, thunder and sky fauna. |
| Z10 | 10 | Ancient relic finale; temple, timeworn stone, gates, ruins and old roots. |
| **TOTAL** | **120** | **Art/content planning only** |

## Owner-approved moves

Exactly nine Owner-approved planning moves were applied. No additional move was inferred from balancing.

| M-ID | Move | Decision source |
|---|---|---|
| M060 | Z6 -> Z3 | OWNER_APPROVED_F034_R1 |
| M073 | Z7 -> Z10 | OWNER_APPROVED_F034_R1 |
| M088 | Z8 -> Z2 | OWNER_APPROVED_F034_R1 |
| M094 | Z8 -> Z2 | OWNER_APPROVED_F034_R1 |
| M091 | Z8 -> Z2 | OWNER_APPROVED_F034_R1 |
| M107 | Z9 -> Z1 | OWNER_APPROVED_F034_R2 |
| M110 | Z9 -> Z1 | OWNER_APPROVED_F034_R2 |
| M100 | Z9 -> Z1 | OWNER_APPROVED_F034_R2 |
| M105 | Z9 -> Z1 | OWNER_APPROVED_F034_R2 |

## Rejected and retained decisions

These seven IDs are recorded as rejected/retained and remain in their original ART002 planning Zones.

| M-ID | Retained Zone | Decision source | Final status |
|---|---|---|---|
| M064 | Z6 | OWNER_REJECTED_F034_R1 | OWNER_REJECTED_RETAINED |
| M086 | Z8 | OWNER_REJECTED_F034_R1 | OWNER_REJECTED_RETAINED |
| M099 | Z9 | OWNER_REJECTED_F034_R1 | OWNER_REJECTED_RETAINED |
| M102 | Z9 | OWNER_REJECTED_F034_R1 | OWNER_REJECTED_RETAINED |
| M104 | Z9 | OWNER_REJECTED_F034_R1 | OWNER_REJECTED_RETAINED |
| M109 | Z9 | OWNER_REJECTED_F034_R1 | OWNER_REJECTED_RETAINED |
| M106 | Z9 | OWNER_REJECTED_F034_R2 | OWNER_REJECTED_RETAINED |

Unselected F034-R2 candidates M111, M103, M108 and M101 were not moved and remain in Z9.

## Runtime anchors

All ten existing runtime identity anchors remain in their original planning Zones. Runtime/planning divergence is zero.

| M-ID | Runtime Zone | Runtime key | Runtime identity |
|---|---|---|---|
| M001 | Z1 | k26_30 | legacy_bf_01_normal |
| M011 | Z2 | k21_25 | legacy_bf_02_normal |
| M022 | Z3 | k16_20 | legacy_bf_03_normal |
| M034 | Z4 | k11_15 | legacy_bf_04_normal |
| M046 | Z5 | k6_10 | legacy_bf_05_normal |
| M058 | Z6 | k1_5 | legacy_bf_06_normal |
| M071 | Z7 | d1_2 | legacy_bf_07_normal |
| M084 | Z8 | d3_4 | legacy_bf_08_normal |
| M098 | Z9 | d5_6 | legacy_bf_09_normal |
| M112 | Z10 | d7_plus | legacy_bf_10_normal |

## Complete final assignment

Every entry carries identity, original ART002 Zone, final planning Zone, Owner move status, decision source and explicit planning scope in the machine-readable artifact.

| M-ID | Identity | Concept | Original ART002 Zone | Final planning Zone | Owner move status | Decision source |
|---|---|---|---|---|---|---|
| M001 | Beginner Slime | village slime | Z1 | Z1 | UNCHANGED_RUNTIME_ANCHOR | RUNTIME_ANCHOR_AND_ART002 |
| M002 | Gate Sprout | garden sprout | Z1 | Z1 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M003 | Barrel Bouncer | village scavenger | Z1 | Z1 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M004 | Strawhat Mole | garden burrower | Z1 | Z1 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M005 | Chime Chick | dojo songbird | Z1 | Z1 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M006 | Pebble Beetle | path beetle | Z1 | Z1 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M007 | Well Bubble | well sprite | Z1 | Z1 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M008 | Paddy Hopper | field hopper | Z1 | Z1 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M009 | Signpost Fox | roadside fox | Z1 | Z1 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M010 | Dumpling Gnome | village helper | Z1 | Z1 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M011 | Cave Bat | plains cave bat | Z2 | Z2 | UNCHANGED_RUNTIME_ANCHOR | RUNTIME_ANCHOR_AND_ART002 |
| M012 | Mudball Otter | puddle otter | Z2 | Z2 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M013 | Bubble Frog | pond frog | Z2 | Z2 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M014 | Kite Dragonfly | field insect | Z2 | Z2 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M015 | Grassseed Lamb | meadow grazer | Z2 | Z2 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M016 | Puddle Crab | water-edge crab | Z2 | Z2 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M017 | Spring Grasshopper | meadow insect | Z2 | Z2 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M018 | Jellyfish | rain jelly | Z2 | Z2 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M019 | Parasol Funglet | field fungus | Z2 | Z2 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M020 | Whirl Vole | wind vole | Z2 | Z2 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M021 | Dewdrop Fawn | morning grazer | Z2 | Z2 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M022 | Cave Orc Grunt | cave faction | Z3 | Z3 | UNCHANGED_RUNTIME_ANCHOR | RUNTIME_ANCHOR_AND_ART002 |
| M023 | Coppercap Goblin | goblin scavenger | Z3 | Z3 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M024 | Echo Bat | cave bat | Z3 | Z3 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M025 | Pickaxe Moleworker | ore burrower | Z3 | Z3 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M026 | Fungus Lantern Imp | fungus goblin | Z3 | Z3 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M027 | Rope-Ladder Lizard | cave lizard | Z3 | Z3 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M028 | Ironbucket Beetle | ore beetle | Z3 | Z3 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M029 | Crevice Snake | stone snake | Z3 | Z3 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M030 | Cartcap Crawler | fungus carrier | Z3 | Z3 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M031 | Crystal Ore Gob | brittle goblin | Z3 | Z3 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M032 | Cavern Slinger | goblin scout | Z3 | Z3 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M033 | Stalactite Tortoise | stone tortoise | Z3 | Z3 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M034 | Mosswood Sprite | forest sprite | Z4 | Z4 | UNCHANGED_RUNTIME_ANCHOR | RUNTIME_ANCHOR_AND_ART002 |
| M035 | Mist-tail Fox | forest fox | Z4 | Z4 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M036 | Moonleaf Moth | forest moth | Z4 | Z4 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M037 | Vineclaw Beast | vine beast | Z4 | Z4 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M038 | Mossback Turtle | moss tortoise | Z4 | Z4 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M039 | Dewdrop Spider | dew spider | Z4 | Z4 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M040 | Twig Deer | twig grazer | Z4 | Z4 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M041 | Fogwhistle Frog | mist frog | Z4 | Z4 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M042 | Bloomcrown Caterpillar | flower caterpillar | Z4 | Z4 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M043 | Shadowstep Cat | moss cat | Z4 | Z4 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M044 | Hollowtree Cub | tree hollow bear | Z4 | Z4 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M045 | Mosscap Sapling | forest sapling | Z4 | Z4 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M046 | Tribal Orc | clan frontier | Z5 | Z5 | UNCHANGED_RUNTIME_ANCHOR | RUNTIME_ANCHOR_AND_ART002 |
| M047 | Ember Drum Brute | drum clan | Z5 | Z5 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M048 | Hide-shield Rhino | herd guard | Z5 | Z5 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M049 | Redclay Ram | clay herd | Z5 | Z5 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M050 | War Drum Lizard | drum lizard | Z5 | Z5 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M051 | Feathercrest Hound | clan hound | Z5 | Z5 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M052 | Mortar Mole | clan hauler | Z5 | Z5 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M053 | Copperring Boar | clan boar | Z5 | Z5 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M054 | Campfire Skink | camp reptile | Z5 | Z5 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M055 | Banner-tail Bison | banner herd | Z5 | Z5 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M056 | Mudplate Armadillo | clay burrower | Z5 | Z5 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M057 | Drumface Tortoise | clan tortoise | Z5 | Z5 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M058 | Wyvern | valley wyvern | Z6 | Z6 | UNCHANGED_RUNTIME_ANCHOR | RUNTIME_ANCHOR_AND_ART002 |
| M059 | Lava-wing Drake | lava drake | Z6 | Z6 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M060 | Crystalhorn Lizard | crystal lizard | Z6 | Z3 | OWNER_APPROVED_MOVE | OWNER_APPROVED_F034_R1 |
| M061 | Cloudclaw Gryphon | sky gryphon | Z6 | Z6 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M062 | Sparkscale Gecko | spark gecko | Z6 | Z6 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M063 | Basalt Shellbeast | basalt beast | Z6 | Z6 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M064 | Windspine Serpent | wind serpent | Z6 | Z6 | OWNER_REJECTED_RETAINED | OWNER_REJECTED_F034_R1 |
| M065 | Ember-tail Foxdragon | foxdragon | Z6 | Z6 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M066 | Cliffskip Goat | cliff goat | Z6 | Z6 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M067 | Sulfur Salamander | sulfur salamander | Z6 | Z6 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M068 | Nestling Raptor | nest raptor | Z6 | Z6 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M069 | Starflame Bat | sky bat | Z6 | Z6 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M070 | Molten Gold Centipede | lava crawler | Z6 | Z6 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M071 | Tower Shade Caster | tower shade | Z7 | Z7 | UNCHANGED_RUNTIME_ANCHOR | RUNTIME_ANCHOR_AND_ART002 |
| M072 | Pagefox | library fox | Z7 | Z7 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M073 | Brass Golem | tower construct | Z7 | Z10 | OWNER_APPROVED_MOVE | OWNER_APPROVED_F034_R1 |
| M074 | Stardust Moth | spell moth | Z7 | Z7 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M075 | Inkwell Octopus | ink familiar | Z7 | Z7 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M076 | Floating Bell Bug | tower bell bug | Z7 | Z7 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M077 | Rune Owl | rune owl | Z7 | Z7 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M078 | Potion Gob | alchemy goblin | Z7 | Z7 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M079 | Prism Gecko | prism gecko | Z7 | Z7 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M080 | Gravity Crab | gravity crustacean | Z7 | Z7 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M081 | Scrollback Turtle | scroll tortoise | Z7 | Z7 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M082 | Astrolabe Beetle | observatory beetle | Z7 | Z7 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M083 | Cloudstep Ram | tower ram | Z7 | Z7 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M084 | Frontline Iron Knight | frontier armor beast | Z8 | Z8 | UNCHANGED_RUNTIME_ANCHOR | RUNTIME_ANCHOR_AND_ART002 |
| M085 | Blackgate Hound | gate hound | Z8 | Z8 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M086 | Breakshield Beetle | siege beetle | Z8 | Z8 | OWNER_REJECTED_RETAINED | OWNER_REJECTED_F034_R1 |
| M087 | Bannerbreak Stonebeast | fort stonebeast | Z8 | Z8 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M088 | Stringwing Bat | scout bat | Z8 | Z2 | OWNER_APPROVED_MOVE | OWNER_APPROVED_F034_R1 |
| M089 | Steelfang Hyena | frontier hyena | Z8 | Z8 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M090 | Battlement Lizard | wall lizard | Z8 | Z8 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M091 | Smokescreen Weasel | scout weasel | Z8 | Z2 | OWNER_APPROVED_MOVE | OWNER_APPROVED_F034_R1 |
| M092 | Ironwheel Rhino | siege rhino | Z8 | Z8 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M093 | Beacon Scorpion | signal scorpion | Z8 | Z8 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M094 | Shieldshell Crab | moat crab | Z8 | Z2 | OWNER_APPROVED_MOVE | OWNER_APPROVED_F034_R1 |
| M095 | Obsidian Automaton | frontier construct | Z8 | Z8 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M096 | Wallbreak Bear | gate bear | Z8 | Z8 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M097 | Scout Hawkbeast | frontier hawk | Z8 | Z8 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M098 | Stormpray Bird | storm bird | Z9 | Z9 | UNCHANGED_RUNTIME_ANCHOR | RUNTIME_ANCHOR_AND_ART002 |
| M099 | Aurora Serpent | aurora serpent | Z9 | Z9 | OWNER_REJECTED_RETAINED | OWNER_REJECTED_F034_R1 |
| M100 | Thundercrown Stag | storm grazer | Z9 | Z1 | OWNER_APPROVED_MOVE | OWNER_APPROVED_F034_R2 |
| M101 | Skyvault Whale | cloud whale | Z9 | Z9 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M102 | Star-ring Ape | orbit ape | Z9 | Z9 | OWNER_REJECTED_RETAINED | OWNER_REJECTED_F034_R1 |
| M103 | Riftbow Eagle | storm eagle | Z9 | Z9 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M104 | Moon-eclipse Mantis | eclipse mantis | Z9 | Z9 | OWNER_REJECTED_RETAINED | OWNER_REJECTED_F034_R1 |
| M105 | Skydrum Tortoise | storm tortoise | Z9 | Z1 | OWNER_APPROVED_MOVE | OWNER_APPROVED_F034_R2 |
| M106 | Starsand Wolf | star wolf | Z9 | Z9 | OWNER_REJECTED_RETAINED | OWNER_REJECTED_F034_R2 |
| M107 | Monolith Beetle | monument beetle | Z9 | Z1 | OWNER_APPROVED_MOVE | OWNER_APPROVED_F034_R2 |
| M108 | Thundercrystal Mantis | crystal mantis | Z9 | Z9 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M109 | Firmament Jelly | sky jelly | Z9 | Z9 | OWNER_REJECTED_RETAINED | OWNER_REJECTED_F034_R1 |
| M110 | Dawnwing Serpent | dawn serpent | Z9 | Z1 | OWNER_APPROVED_MOVE | OWNER_APPROVED_F034_R2 |
| M111 | Starshard Rhino | star rhino | Z9 | Z9 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M112 | Ancient Temple Idol | relic construct | Z10 | Z10 | UNCHANGED_RUNTIME_ANCHOR | RUNTIME_ANCHOR_AND_ART002 |
| M113 | Timeworn Stone Turtle | time tortoise | Z10 | Z10 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M114 | Endgate Beast | gate beast | Z10 | Z10 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M115 | Ancient Bell Crawler | relic crawler | Z10 | Z10 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M116 | Ivorylight Beetle | ivory beetle | Z10 | Z10 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M117 | Blacksand Hound | relic hound | Z10 | Z10 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M118 | Relic Shellbeast | ruin beast | Z10 | Z10 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M119 | Silent Tabletling | tablet construct | Z10 | Z10 | UNCHANGED_ART002 | UNCHANGED_ART002 |
| M120 | Evergreen Rootbeast | ancient root beast | Z10 | Z10 | UNCHANGED_ART002 | UNCHANGED_ART002 |

## ART002 and ART003 preservation

- ART002 identities, art assets and historical documentation are preserved.
- ART002 old distribution remains superseded only for art/content planning.
- ART003 may consume this exact assignment for art batch planning, coverage bookkeeping and Zone-themed organization.
- ART003 may not use it for gameplay mapping.
- ART003 B01 IDs remain protected: M002, M003, M004, M005, M006, M007, M008, M009, M010, M012.
- No B01/B02 artwork was mutated.

## Authority firewall

- GAMEPLAY_AUTHORITY=NO
- RUNTIME_ZONE_AUTHORITY=NO
- ART_CONTENT_COUNT_USED_FOR_COMBAT=NO
- F009_ENABLED=NO
- RARITY_USED_FOR_ZONE_ASSIGNMENT=NO
- MONSTER_STATS_CHANGED=NO
- COMBAT_PROFILE_MAPPING_CHANGED=NO
- MONSTER_CATALOG_GAMEPLAY_ZONE_CHANGED=NO
- BOSS_INCLUDED_IN_120_COUNT=NO
- LORD_INCLUDED_IN_120_COUNT=NO

F035 does not touch E047, A044, B058, LC015 or ART003 asset scope. F035 is not included in B058.

## Validation

- Assigned IDs: 120
- Unassigned IDs: 0
- Duplicate assignments: 0
- Owner-approved move trace count: 9
- Owner-rejected decision trace count: 7
- Runtime anchors: 10
- Runtime/planning divergence: 0
- Deterministic rerun: PASS
- APP_PY/runtime/source/assets/schema/migration changed: NO

F035 freezes the exact planning assignment only. Gameplay and runtime work remain separate future authority decisions.
