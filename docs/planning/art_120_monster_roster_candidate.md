# Go Odyssey ART002 120-Monster Roster and Zone Distribution Candidate

- Task: ART002_120_MONSTER_ROSTER_AND_ZONE_DISTRIBUTION_LOCK_CANDIDATE_001
- Track: ART_PRODUCTION
- Status: READY_FOR_OWNER_120_MONSTER_ROSTER_REVIEW
- Candidate lock: NO; this document is not gameplay/database authority.
- Origin reference: origin/master@92127b25ff1570836ce1e8f2dd2c813b893be03a
- Design source snapshot used before origin/master advanced: 4585bd1a12d179d0810300f047357f2e36c3e851
- ART001 baseline: 32cb6fe4631c91375094529244395eca202c95b2

## 1. Candidate Summary

```
NORMAL_MONSTER_TARGET=120
EXISTING_RUNTIME_MONSTERS=10
NEW_MONSTER_IDENTITIES_PROPOSED=110
TOTAL_ROSTER_CANDIDATE_COUNT=120
UNASSIGNED_MONSTERS=0
ZONE_DISTRIBUTION_TOTAL=120
MONSTER_ROSTER_LOCKED=NO
READY_FOR_OWNER_120_MONSTER_ROSTER_REVIEW=YES
```

This candidate gives every target slot a proposed normal-Monster identity, Zone, bilingual name and production brief. The ten existing runtime identities remain separately identified through their exact runtime IDs and current asset paths. The 110 new identities have no artwork, runtime ID, canonical asset or runtime mapping.

Taxonomy is locked for this candidate: NORMAL MONSTER != BATTLEFIELD BOSS; BATTLEFIELD BOSS != LORD; SPIRIT != MONSTER; MONSTER_DEFEAT != ZONE_CLEAR. No Boss, Lord or Spirit is counted in the 120.

## 2. Zone Distribution Candidate

| Zone | Name | Count | Direction | Danger | Magic | Humor |
|---|---|---:|---|---:|---:|---:|
| Z1 | 新手村 | 10 | Welcome to the Way of Go | 1/10 | 1/5 | 5/5 |
| Z2 | 史萊姆平原 | 11 | Playful motion across open land | 2/10 | 1/5 | 5/5 |
| Z3 | 哥布林洞穴 | 12 | Clever cave faction | 3/10 | 2/5 | 3/5 |
| Z4 | 迷霧森林 | 12 | Mystery without menace | 4/10 | 3/5 | 3/5 |
| Z5 | 獸人部落 | 12 | Boisterous clan frontier | 5/10 | 2/5 | 4/5 |
| Z6 | 龍之谷 | 13 | Sky and fire dragon valley | 6/10 | 3/5 | 2/5 |
| Z7 | 賢者之塔 | 13 | Curiosity becomes spellcraft | 7/10 | 5/5 | 3/5 |
| Z8 | 魔王城前線 | 14 | Frontier under pressure | 8/10 | 4/5 | 2/5 |
| Z9 | 諸神黃昏 | 14 | Mythic weather and broken order | 9/10 | 5/5 | 1/5 |
| Z10 | 上古終焉神殿 | 9 | Ancient ending, still collectible | 10/10 | 5/5 | 1/5 |

Total: 120. The distribution is deliberately non-uniform. Counts grow as Zones become longer, more factional and more visually complex through Z9; Z10 is a compact finale with fewer but more iconic encounters. This supports progression, encounter reuse and manageable review waves without assuming 12 per Zone.

## 3. Zone Identity Before Quantity

### Z1 新手村
- ZONE_THEME: Welcome to the Way of Go
- ENVIRONMENT: terraced village, dojo yard, garden paths and warm wooden gates
- MONSTER_ECOLOGY: garden blobs, tiny sprites, burrowers and helpful-looking scavengers
- SHAPE_LANGUAGE: round, low, open faces and clear toy-like silhouettes
- MATERIAL_LANGUAGE: wood, straw, clay, soft stone and woven cord
- COLOR_DIRECTION: teal, honey gold, grass green and cream
- DANGER_LEVEL: 1/10
- MAGIC_LEVEL: 1/5
- HUMOR_LEVEL: 5/5
- VISUAL_ESCALATION: tutorial-scale, friendly and highly readable
- WHAT_MUST_NOT_APPEAR: gore, skulls, heavy armor, horror faces, giant bodies or boss regalia

### Z2 史萊姆平原
- ZONE_THEME: Playful motion across open land
- ENVIRONMENT: rolling grass, puddles, reed beds, breeze ribbons and slime pools
- MONSTER_ECOLOGY: slimes, insects, grazers, reeds and harmless water-edge hunters
- SHAPE_LANGUAGE: bouncy blobs, wings, low quadrupeds and spring-loaded poses
- MATERIAL_LANGUAGE: wet gel, reed, seed pod, shell and smooth river stone
- COLOR_DIRECTION: lime, aqua, sky blue, butter yellow and white
- DANGER_LEVEL: 2/10
- MAGIC_LEVEL: 1/5
- HUMOR_LEVEL: 5/5
- VISUAL_ESCALATION: more motion and group behaviors without heavy menace
- WHAT_MUST_NOT_APPEAR: dark cave mood, gore, oversized armor, firearms or military realism

### Z3 哥布林洞穴
- ZONE_THEME: Clever cave faction
- ENVIRONMENT: lantern limestone, ore seams, fungus shelves, rope bridges and echo pockets
- MONSTER_ECOLOGY: goblin-coded scavengers, burrowers, beetles, cave birds and ore constructs
- SHAPE_LANGUAGE: angular ears, crouched bipeds, compact crawlers and asymmetrical packs
- MATERIAL_LANGUAGE: stone, iron, fungus, rope, leather and chipped crystal
- COLOR_DIRECTION: charcoal, copper, moss green and amber lantern light
- DANGER_LEVEL: 3/10
- MAGIC_LEVEL: 2/5
- HUMOR_LEVEL: 3/5
- VISUAL_ESCALATION: first faction gear and tactical silhouettes
- WHAT_MUST_NOT_APPEAR: firearms, boss regalia, realistic violence, gore or Lord identity

### Z4 迷霧森林
- ZONE_THEME: Mystery without menace
- ENVIRONMENT: misty forest, fern clearings, moon pools, old trunks and hanging vines
- MONSTER_ECOLOGY: stealth beasts, moths, plants, gentle crawlers and dusk browsers
- SHAPE_LANGUAGE: long tails, leaf crests, soft asymmetry and peeking poses
- MATERIAL_LANGUAGE: bark, leaf, dew, vine, seed husk and smooth antler-like wood
- COLOR_DIRECTION: deep teal, moss, lavender, fog white and moon gold
- DANGER_LEVEL: 4/10
- MAGIC_LEVEL: 3/5
- HUMOR_LEVEL: 3/5
- VISUAL_ESCALATION: more camouflage and magic cues, still child-safe
- WHAT_MUST_NOT_APPEAR: horror faces, eyes everywhere, gore, dark undead or Spirit identity copies

### Z5 獸人部落
- ZONE_THEME: Boisterous clan frontier
- ENVIRONMENT: red-clay plazas, drum circles, basalt steps, banners and cooking fires
- MONSTER_ECOLOGY: armored herd beasts, orc-like clans, haulers, scouts and camp reptiles
- SHAPE_LANGUAGE: broad shoulders, horns, shields, chunky feet and readable held props
- MATERIAL_LANGUAGE: leather, clay, wood, bronze, hide and woven banners
- COLOR_DIRECTION: terracotta, ochre, dark teal, cream and ember orange
- DANGER_LEVEL: 5/10
- MAGIC_LEVEL: 2/5
- HUMOR_LEVEL: 4/5
- VISUAL_ESCALATION: faction identity and armor increase, comedy keeps it approachable
- WHAT_MUST_NOT_APPEAR: realistic warfare, gore, hateful caricature, Lord or Boss regalia

### Z6 龍之谷
- ZONE_THEME: Sky and fire dragon valley
- ENVIRONMENT: cliffs, lava rills, crystal nests, rope bridges and wind tunnels
- MONSTER_ECOLOGY: juvenile dragons, winged reptiles, stone beasts and heat-loving crawlers
- SHAPE_LANGUAGE: wings, horns, tails, triangular profiles and airborne diagonals
- MATERIAL_LANGUAGE: scale, basalt, crystal, ember glass and weathered rope
- COLOR_DIRECTION: cobalt, ember, gold, volcanic plum and smoke gray
- DANGER_LEVEL: 6/10
- MAGIC_LEVEL: 3/5
- HUMOR_LEVEL: 2/5
- VISUAL_ESCALATION: larger profiles and elemental accents, no Boss scale
- WHAT_MUST_NOT_APPEAR: giant Boss dragons, gore, realistic fire, royal crowns or deity identity

### Z7 賢者之塔
- ZONE_THEME: Curiosity becomes spellcraft
- ENVIRONMENT: floating tower rooms, library stacks, brass observatories and star windows
- MONSTER_ECOLOGY: enchanted creatures, constructs and non-Spirit magical familiars
- SHAPE_LANGUAGE: geometric, levitating, page-like, ringed and stacked silhouettes
- MATERIAL_LANGUAGE: ink, paper, brass, crystal, ceramic and stitched cloth
- COLOR_DIRECTION: indigo, cyan, brass, parchment and violet
- DANGER_LEVEL: 7/10
- MAGIC_LEVEL: 5/5
- HUMOR_LEVEL: 3/5
- VISUAL_ESCALATION: strong spell language and floating forms, still collectible
- WHAT_MUST_NOT_APPEAR: NPC replicas, canonical Spirit clones, horror eyes or human wizard portraits

### Z8 魔王城前線
- ZONE_THEME: Frontier under pressure
- ENVIRONMENT: fortifications, moats, broken gates, supply yards and signal towers
- MONSTER_ECOLOGY: siege-adapted beasts, constructs, scouts and defensive scavengers
- SHAPE_LANGUAGE: plated, wedge-shaped, shield-like and organic-mechanical profiles
- MATERIAL_LANGUAGE: obsidian, iron, leather, charcoal, rope and signal cloth
- COLOR_DIRECTION: navy, rust, black, ash gray and signal red
- DANGER_LEVEL: 8/10
- MAGIC_LEVEL: 4/5
- HUMOR_LEVEL: 2/5
- VISUAL_ESCALATION: elite-normal silhouettes and stronger defensive read
- WHAT_MUST_NOT_APPEAR: final Boss or Lord regalia, realistic weapons, gore or demon horror

### Z9 諸神黃昏
- ZONE_THEME: Mythic weather and broken order
- ENVIRONMENT: storm temples, aurora bridges, fractured monuments and cloud shelves
- MONSTER_ECOLOGY: mythic beasts, cosmic birds, serpents and fragments of old order
- SHAPE_LANGUAGE: tall, large, asymmetric crowns, orbit motifs and skyward profiles
- MATERIAL_LANGUAGE: starstone, bronze, cloud glass, storm silk and moon metal
- COLOR_DIRECTION: dusk purple, storm cyan, moon white and gold
- DANGER_LEVEL: 9/10
- MAGIC_LEVEL: 5/5
- HUMOR_LEVEL: 1/5
- VISUAL_ESCALATION: mythic scale and cosmic motifs without unreadable abstraction
- WHAT_MUST_NOT_APPEAR: direct deity or Lord copies, body horror, gore or opaque cosmic noise

### Z10 上古終焉神殿
- ZONE_THEME: Ancient ending, still collectible
- ENVIRONMENT: black-and-white temple stone, void windows, time scars and silent courtyards
- MONSTER_ECOLOGY: primordial constructs, relic beasts, gate guardians and memory-shaped fauna
- SHAPE_LANGUAGE: monoliths, shells, gates, nested geometry and deliberate negative space
- MATERIAL_LANGUAGE: ancient stone, obsidian, ivory, muted gold and restrained violet glass
- COLOR_DIRECTION: black, white, deep teal, antique gold and quiet violet
- DANGER_LEVEL: 10/10
- MAGIC_LEVEL: 5/5
- HUMOR_LEVEL: 1/5
- VISUAL_ESCALATION: ancient and iconic finale silhouettes, not horror
- WHAT_MUST_NOT_APPEAR: gore, cosmic horror, canonical Spirit, Boss or Lord replicas, visual noise

## 4. Existing Runtime Monster Accounting

EXISTING_RUNTIME_MONSTERS_ACCOUNTED_FOR=10/10. The following is the exact ART001 runtime identity inventory. Runtime identity, current art candidate and Owner visual approval are separate facts.

| ART_MONSTER_ID | RUNTIME_ID | CURRENT_RUNTIME_NAME | ZONE | CURRENT_ASSET | REUSE_DECISION | GAMEPLAY_ROLE |
|---|---|---|---|---|---|---|
| M001 | legacy_bf_01_normal | LV1 史萊姆 / 哥布林 | Z1 新手村 | assets/monsters/slime_chibi.png | KEEP_CURRENT_IDENTITY_AND_ART_CANDIDATE | UNKNOWN |
| M011 | legacy_bf_02_normal | LV2 哥布林 / 洞窟蝙蝠 | Z2 史萊姆平原 | assets/monsters/cave_bat_chibi.png | KEEP_CURRENT_IDENTITY_AND_ART_CANDIDATE | UNKNOWN |
| M022 | legacy_bf_03_normal | LV3 獸人小兵 | Z3 哥布林洞穴 | assets/monsters/orc_grunt_chibi.png | REQUIRES_OWNER_DECISION | UNKNOWN |
| M034 | legacy_bf_04_normal | LV4 森林精靈 | Z4 迷霧森林 | assets/monsters/forest_spirit_chibi.png | KEEP_CURRENT_IDENTITY_AND_ART_CANDIDATE | UNKNOWN |
| M046 | legacy_bf_05_normal | LV5 部落獸人 | Z5 獸人部落 | assets/monsters/tribal_orc_chibi.png | KEEP_IDENTITY_REDESIGN_ART | UNKNOWN |
| M058 | legacy_bf_06_normal | LV6 飛龍 / 低階神靈 | Z6 龍之谷 | assets/monsters/wyvern_chibi.png | KEEP_CURRENT_IDENTITY_AND_ART_CANDIDATE | UNKNOWN |
| M071 | legacy_bf_07_normal | LV7 賢者 / 魔法師 / 亡靈 | Z7 賢者之塔 | assets/monsters/lich_mage_chibi.png | KEEP_CURRENT_IDENTITY_AND_ART_CANDIDATE | UNKNOWN |
| M084 | legacy_bf_08_normal | LV8 騎士 / 混沌領主 | Z8 魔王城前線 | assets/monsters/armored_knight_chibi.png | REQUIRES_OWNER_DECISION | UNKNOWN |
| M098 | legacy_bf_09_normal | LV9 諸神 | Z9 諸神黃昏 | assets/monsters/storm_deity_chibi.png | KEEP_CURRENT_IDENTITY_AND_ART_CANDIDATE | UNKNOWN |
| M112 | legacy_bf_10_normal | LV10 上古終焉神殿 | Z10 上古終焉神殿 | assets/monsters/ancient_idol_chibi.png | KEEP_CURRENT_IDENTITY_AND_ART_CANDIDATE | UNKNOWN |

Current-art decisions: KEEP_CURRENT_IDENTITY_AND_ART_CANDIDATE=7, KEEP_IDENTITY_REDESIGN_ART=1, REQUIRES_OWNER_DECISION=2. Z3 requires a taxonomy decision because the current runtime name/art are Orc-themed in Goblin Cave; Z8 requires a taxonomy decision because the current runtime name contains Chaos Lord language. Neither is silently renamed here.

## 5. 120-Monster Identity and Brief Board

Every row below has ZH_NAME, EN_NAME, Zone and a structured brief. ROSTER_DEFINED=YES applies only to the ten existing runtime identities. ROSTER_DEFINED=CANDIDATE applies to the 110 proposed identities. New rows are deliberately DRAFT=NO, OWNER_APPROVED=NO, CANONICAL_ASSET=NO, RUNTIME_MAPPED=NO and VISUAL_QA=NO.

| ART_MONSTER_ID | RUNTIME_ID | ZH_NAME | EN_NAME | ZONE | ROSTER_DEFINED | BRIEF | DRAFT | OWNER_APPROVED | CANONICAL_ASSET | ASSET_PATH | RUNTIME_MAPPED | VISUAL_QA | ROLE | DESIGN | BATCH |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M001 | legacy_bf_01_normal | 新手史萊姆 | Beginner Slime | Z1 新手村 | YES | YES | YES | UNKNOWN | YES | assets/monsters/slime_chibi.png | YES | UNKNOWN | BASIC | UNIQUE_BASE | W0-STYLE-LOCK |
| M002 | null | 村口豆芽 | Gate Sprout | Z1 新手村 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | MAGIC | UNIQUE_BASE | B01 |
| M003 | null | 木桶小咕 | Barrel Bouncer | Z1 新手村 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B01 |
| M004 | null | 草帽鼴鼠 | Strawhat Mole | Z1 新手村 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | VARIANT | B01 |
| M005 | null | 風鈴小鳥 | Chime Chick | Z1 新手村 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FLYING | UNIQUE_BASE | B01 |
| M006 | null | 石子甲蟲 | Pebble Beetle | Z1 新手村 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | ARMORED | UNIQUE_BASE | B01 |
| M007 | null | 井邊水泡 | Well Bubble | Z1 新手村 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TRICKSTER | UNIQUE_BASE | B01 |
| M008 | null | 稻田蹦蹦 | Paddy Hopper | Z1 新手村 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | VARIANT | B01 |
| M009 | null | 木牌狐仔 | Signpost Fox | Z1 新手村 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TRICKSTER | UNIQUE_BASE | B01 |
| M010 | null | 糰子地精 | Dumpling Gnome | Z1 新手村 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | BASIC | UNIQUE_BASE | B01 |
| M011 | legacy_bf_02_normal | 洞窟蝙蝠 | Cave Bat | Z2 史萊姆平原 | YES | YES | YES | UNKNOWN | YES | assets/monsters/cave_bat_chibi.png | YES | UNKNOWN | FLYING | UNIQUE_BASE | W0-STYLE-LOCK |
| M012 | null | 泥球水獺 | Mudball Otter | Z2 史萊姆平原 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TRICKSTER | UNIQUE_BASE | B01 |
| M013 | null | 泡泡蛙 | Bubble Frog | Z2 史萊姆平原 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | MAGIC | UNIQUE_BASE | B02 |
| M014 | null | 風箏蜻蜓 | Kite Dragonfly | Z2 史萊姆平原 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FLYING | VARIANT | B02 |
| M015 | null | 草籽羊 | Grassseed Lamb | Z2 史萊姆平原 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B02 |
| M016 | null | 水窪蟹 | Puddle Crab | Z2 史萊姆平原 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | ARMORED | UNIQUE_BASE | B02 |
| M017 | null | 彈簧蚱蜢 | Spring Grasshopper | Z2 史萊姆平原 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | UNIQUE_BASE | B02 |
| M018 | null | 果凍魚 | Jellyfish | Z2 史萊姆平原 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | MAGIC | VARIANT | B02 |
| M019 | null | 彩傘菇獸 | Parasol Funglet | Z2 史萊姆平原 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | RANGED | UNIQUE_BASE | B02 |
| M020 | null | 旋風田鼠 | Whirl Vole | Z2 史萊姆平原 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | UNIQUE_BASE | B02 |
| M021 | null | 水珠鹿 | Dewdrop Fawn | Z2 史萊姆平原 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | BASIC | UNIQUE_BASE | B02 |
| M022 | legacy_bf_03_normal | 洞穴獸人小兵 | Cave Orc Grunt | Z3 哥布林洞穴 | YES | YES | YES | UNKNOWN | YES | assets/monsters/orc_grunt_chibi.png | YES | UNKNOWN | BASIC | UNIQUE_BASE | W0-STYLE-LOCK |
| M023 | null | 銅帽哥布林 | Coppercap Goblin | Z3 哥布林洞穴 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TRICKSTER | UNIQUE_BASE | B02 |
| M024 | null | 回音蝠 | Echo Bat | Z3 哥布林洞穴 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | RANGED | UNIQUE_BASE | B03 |
| M025 | null | 礦鎬鼴工 | Pickaxe Moleworker | Z3 哥布林洞穴 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B03 |
| M026 | null | 菌燈小鬼 | Fungus Lantern Imp | Z3 哥布林洞穴 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | MAGIC | UNIQUE_BASE | B03 |
| M027 | null | 繩梯蜥 | Rope-Ladder Lizard | Z3 哥布林洞穴 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | VARIANT | B03 |
| M028 | null | 鐵桶甲蟲 | Ironbucket Beetle | Z3 哥布林洞穴 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | ARMORED | UNIQUE_BASE | B03 |
| M029 | null | 石縫蛇 | Crevice Snake | Z3 哥布林洞穴 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TRICKSTER | UNIQUE_BASE | B03 |
| M030 | null | 蘑菇推車怪 | Cartcap Crawler | Z3 哥布林洞穴 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B03 |
| M031 | null | 晶礦咕 | Crystal Ore Gob | Z3 哥布林洞穴 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | MAGIC | VARIANT | B03 |
| M032 | null | 洞穴投石手 | Cavern Slinger | Z3 哥布林洞穴 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | RANGED | UNIQUE_BASE | B03 |
| M033 | null | 鐘乳石龜 | Stalactite Tortoise | Z3 哥布林洞穴 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B03 |
| M034 | legacy_bf_04_normal | 霧林精靈 | Mosswood Sprite | Z4 迷霧森林 | YES | YES | YES | UNKNOWN | YES | assets/monsters/forest_spirit_chibi.png | YES | UNKNOWN | MAGIC | UNIQUE_BASE | W0-STYLE-LOCK |
| M035 | null | 霧尾狐 | Mist-tail Fox | Z4 迷霧森林 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TRICKSTER | UNIQUE_BASE | B04 |
| M036 | null | 月葉蛾 | Moonleaf Moth | Z4 迷霧森林 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FLYING | UNIQUE_BASE | B04 |
| M037 | null | 藤蔓爪獸 | Vineclaw Beast | Z4 迷霧森林 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | UNIQUE_BASE | B04 |
| M038 | null | 苔背龜 | Mossback Turtle | Z4 迷霧森林 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B04 |
| M039 | null | 露珠蜘蛛 | Dewdrop Spider | Z4 迷霧森林 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TRICKSTER | VARIANT | B04 |
| M040 | null | 枯枝鹿 | Twig Deer | Z4 迷霧森林 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | BASIC | UNIQUE_BASE | B04 |
| M041 | null | 霧笛蛙 | Fogwhistle Frog | Z4 迷霧森林 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | RANGED | UNIQUE_BASE | B04 |
| M042 | null | 花冠毛蟲 | Bloomcrown Caterpillar | Z4 迷霧森林 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | MAGIC | UNIQUE_BASE | B04 |
| M043 | null | 影步貓 | Shadowstep Cat | Z4 迷霧森林 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | VARIANT | B04 |
| M044 | null | 樹洞熊芽 | Hollowtree Cub | Z4 迷霧森林 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B04 |
| M045 | null | 蘚帽小樹 | Mosscap Sapling | Z4 迷霧森林 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | BASIC | UNIQUE_BASE | B05 |
| M046 | legacy_bf_05_normal | 部落獸人 | Tribal Orc | Z5 獸人部落 | YES | YES | YES | UNKNOWN | YES | assets/monsters/tribal_orc_chibi.png | YES | UNKNOWN | ARMORED | UNIQUE_BASE | W0-STYLE-LOCK |
| M047 | null | 炭鼓獸 | Ember Drum Brute | Z5 獸人部落 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B05 |
| M048 | null | 皮盾犀童 | Hide-shield Rhino | Z5 獸人部落 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B05 |
| M049 | null | 紅土角羊 | Redclay Ram | Z5 獸人部落 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | BASIC | UNIQUE_BASE | B05 |
| M050 | null | 戰鼓蜥 | War Drum Lizard | Z5 獸人部落 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | VARIANT | B05 |
| M051 | null | 羽飾獵犬 | Feathercrest Hound | Z5 獸人部落 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | UNIQUE_BASE | B05 |
| M052 | null | 石臼巨鼴 | Mortar Mole | Z5 獸人部落 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B05 |
| M053 | null | 銅環野豬 | Copperring Boar | Z5 獸人部落 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | ARMORED | UNIQUE_BASE | B05 |
| M054 | null | 篝火蜥蜴 | Campfire Skink | Z5 獸人部落 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | MAGIC | VARIANT | B05 |
| M055 | null | 旗尾牛 | Banner-tail Bison | Z5 獸人部落 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | ARMORED | UNIQUE_BASE | B05 |
| M056 | null | 泥甲犰狳 | Mudplate Armadillo | Z5 獸人部落 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | ARMORED | UNIQUE_BASE | B06 |
| M057 | null | 鼓面龜 | Drumface Tortoise | Z5 獸人部落 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B06 |
| M058 | legacy_bf_06_normal | 飛龍 | Wyvern | Z6 龍之谷 | YES | YES | YES | UNKNOWN | YES | assets/monsters/wyvern_chibi.png | YES | UNKNOWN | FLYING | UNIQUE_BASE | W0-STYLE-LOCK |
| M059 | null | 熔岩翼蜥 | Lava-wing Drake | Z6 龍之谷 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FLYING | UNIQUE_BASE | B06 |
| M060 | null | 晶角蜥 | Crystalhorn Lizard | Z6 龍之谷 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | MAGIC | UNIQUE_BASE | B06 |
| M061 | null | 雲爪獅鷲 | Cloudclaw Gryphon | Z6 龍之谷 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FLYING | UNIQUE_BASE | B06 |
| M062 | null | 火花蜥蜴 | Sparkscale Gecko | Z6 龍之谷 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | VARIANT | B06 |
| M063 | null | 玄岩甲獸 | Basalt Shellbeast | Z6 龍之谷 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B06 |
| M064 | null | 風脊飛蛇 | Windspine Serpent | Z6 龍之谷 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FLYING | UNIQUE_BASE | B06 |
| M065 | null | 焰尾狐龍 | Ember-tail Foxdragon | Z6 龍之谷 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TRICKSTER | UNIQUE_BASE | B06 |
| M066 | null | 巖跳山羊 | Cliffskip Goat | Z6 龍之谷 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | VARIANT | B06 |
| M067 | null | 硫磺蠑螈 | Sulfur Salamander | Z6 龍之谷 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | MAGIC | UNIQUE_BASE | B07 |
| M068 | null | 龍巢小暴龍 | Nestling Raptor | Z6 龍之谷 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | UNIQUE_BASE | B07 |
| M069 | null | 星火翼蝠 | Starflame Bat | Z6 龍之谷 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | RANGED | UNIQUE_BASE | B07 |
| M070 | null | 熔金蜈蚣 | Molten Gold Centipede | Z6 龍之谷 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | SWARM | UNIQUE_BASE | B07 |
| M071 | legacy_bf_07_normal | 塔影亡靈術士 | Tower Shade Caster | Z7 賢者之塔 | YES | YES | YES | UNKNOWN | YES | assets/monsters/lich_mage_chibi.png | YES | UNKNOWN | MAGIC | UNIQUE_BASE | W0-STYLE-LOCK |
| M072 | null | 書頁狐 | Pagefox | Z7 賢者之塔 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TRICKSTER | UNIQUE_BASE | B07 |
| M073 | null | 黃銅魔像 | Brass Golem | Z7 賢者之塔 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B07 |
| M074 | null | 星屑蛾 | Stardust Moth | Z7 賢者之塔 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FLYING | VARIANT | B07 |
| M075 | null | 墨池章魚 | Inkwell Octopus | Z7 賢者之塔 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | MAGIC | UNIQUE_BASE | B07 |
| M076 | null | 浮空鐘蟲 | Floating Bell Bug | Z7 賢者之塔 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | RANGED | UNIQUE_BASE | B07 |
| M077 | null | 符文貓頭鷹 | Rune Owl | Z7 賢者之塔 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | RANGED | UNIQUE_BASE | B07 |
| M078 | null | 藥瓶咕 | Potion Gob | Z7 賢者之塔 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | MAGIC | UNIQUE_BASE | B08 |
| M079 | null | 棱鏡蜥 | Prism Gecko | Z7 賢者之塔 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | VARIANT | B08 |
| M080 | null | 重力蟹 | Gravity Crab | Z7 賢者之塔 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | ARMORED | UNIQUE_BASE | B08 |
| M081 | null | 卷軸龜 | Scrollback Turtle | Z7 賢者之塔 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B08 |
| M082 | null | 天文蟲 | Astrolabe Beetle | Z7 賢者之塔 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | RANGED | UNIQUE_BASE | B08 |
| M083 | null | 雲階羊 | Cloudstep Ram | Z7 賢者之塔 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | UNIQUE_BASE | B08 |
| M084 | legacy_bf_08_normal | 前線鐵甲騎 | Frontline Iron Knight | Z8 魔王城前線 | YES | YES | YES | UNKNOWN | YES | assets/monsters/armored_knight_chibi.png | YES | UNKNOWN | ARMORED | UNIQUE_BASE | W0-STYLE-LOCK |
| M085 | null | 黑門獵犬 | Blackgate Hound | Z8 魔王城前線 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | UNIQUE_BASE | B08 |
| M086 | null | 破盾甲蟲 | Breakshield Beetle | Z8 魔王城前線 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | ARMORED | UNIQUE_BASE | B08 |
| M087 | null | 斷旗石獸 | Bannerbreak Stonebeast | Z8 魔王城前線 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B08 |
| M088 | null | 弦翼蝠 | Stringwing Bat | Z8 魔王城前線 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FLYING | VARIANT | B08 |
| M089 | null | 鋼齒鬣狗 | Steelfang Hyena | Z8 魔王城前線 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | UNIQUE_BASE | B09 |
| M090 | null | 城垛蜥 | Battlement Lizard | Z8 魔王城前線 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | ARMORED | UNIQUE_BASE | B09 |
| M091 | null | 煙幕鼬 | Smokescreen Weasel | Z8 魔王城前線 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TRICKSTER | UNIQUE_BASE | B09 |
| M092 | null | 鐵輪犀 | Ironwheel Rhino | Z8 魔王城前線 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B09 |
| M093 | null | 烽火蠍 | Beacon Scorpion | Z8 魔王城前線 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | RANGED | VARIANT | B09 |
| M094 | null | 盾殼蟹 | Shieldshell Crab | Z8 魔王城前線 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | ARMORED | UNIQUE_BASE | B09 |
| M095 | null | 黑曜傀儡 | Obsidian Automaton | Z8 魔王城前線 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | ELITE_NORMAL | UNIQUE_BASE | B09 |
| M096 | null | 裂牆熊 | Wallbreak Bear | Z8 魔王城前線 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B09 |
| M097 | null | 斥候鷹獸 | Scout Hawkbeast | Z8 魔王城前線 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | RANGED | UNIQUE_BASE | B09 |
| M098 | legacy_bf_09_normal | 風暴祈鳥 | Stormpray Bird | Z9 諸神黃昏 | YES | YES | YES | UNKNOWN | YES | assets/monsters/storm_deity_chibi.png | YES | UNKNOWN | FLYING | UNIQUE_BASE | W0-STYLE-LOCK |
| M099 | null | 極光蛇 | Aurora Serpent | Z9 諸神黃昏 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | MAGIC | UNIQUE_BASE | B09 |
| M100 | null | 雷冠鹿 | Thundercrown Stag | Z9 諸神黃昏 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | MAGIC | UNIQUE_BASE | B10 |
| M101 | null | 雲穹鯨 | Skyvault Whale | Z9 諸神黃昏 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | VARIANT | B10 |
| M102 | null | 星環猿 | Star-ring Ape | Z9 諸神黃昏 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | UNIQUE_BASE | B10 |
| M103 | null | 裂虹鷹 | Riftbow Eagle | Z9 諸神黃昏 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | RANGED | UNIQUE_BASE | B10 |
| M104 | null | 月蝕蟲 | Moon-eclipse Mantis | Z9 諸神黃昏 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TRICKSTER | UNIQUE_BASE | B10 |
| M105 | null | 天鼓龜 | Skydrum Tortoise | Z9 諸神黃昏 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B10 |
| M106 | null | 星砂狼 | Starsand Wolf | Z9 諸神黃昏 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | UNIQUE_BASE | B10 |
| M107 | null | 浮碑甲蟲 | Monolith Beetle | Z9 諸神黃昏 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | ARMORED | VARIANT | B10 |
| M108 | null | 雷晶螳螂 | Thundercrystal Mantis | Z9 諸神黃昏 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | RANGED | UNIQUE_BASE | B10 |
| M109 | null | 蒼穹水母 | Firmament Jelly | Z9 諸神黃昏 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | MAGIC | UNIQUE_BASE | B10 |
| M110 | null | 曙光翼蛇 | Dawnwing Serpent | Z9 諸神黃昏 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FLYING | UNIQUE_BASE | B11 |
| M111 | null | 碎星犀 | Starshard Rhino | Z9 諸神黃昏 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | ELITE_NORMAL | UNIQUE_BASE | B11 |
| M112 | legacy_bf_10_normal | 古殿碑靈 | Ancient Temple Idol | Z10 上古終焉神殿 | YES | YES | YES | UNKNOWN | YES | assets/monsters/ancient_idol_chibi.png | YES | UNKNOWN | ARMORED | UNIQUE_BASE | W0-STYLE-LOCK |
| M113 | null | 時痕石龜 | Timeworn Stone Turtle | Z10 上古終焉神殿 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B11 |
| M114 | null | 終焉門獸 | Endgate Beast | Z10 上古終焉神殿 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | ELITE_NORMAL | UNIQUE_BASE | B11 |
| M115 | null | 古鐘巨蟲 | Ancient Bell Crawler | Z10 上古終焉神殿 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | SWARM | UNIQUE_BASE | B11 |
| M116 | null | 白曜甲蟲 | Ivorylight Beetle | Z10 上古終焉神殿 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | MAGIC | VARIANT | B11 |
| M117 | null | 黑砂獵犬 | Blacksand Hound | Z10 上古終焉神殿 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | FAST | UNIQUE_BASE | B11 |
| M118 | null | 遺跡殼獸 | Relic Shellbeast | Z10 上古終焉神殿 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | ARMORED | UNIQUE_BASE | B11 |
| M119 | null | 靜默碑靈 | Silent Tabletling | Z10 上古終焉神殿 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | MAGIC | VARIANT | B11 |
| M120 | null | 萬年根獸 | Evergreen Rootbeast | Z10 上古終焉神殿 | CANDIDATE | YES | NO | NO | NO | null | NO | NO | TANK | UNIQUE_BASE | B11 |

## 6. Full Brief Fields

The machine-readable JSON contains each brief as fields and as ART_BRIEF. This table makes the production intent reviewable without inventing combat stats.

| ID | Identity | Zone | Family | Body | Silhouette | Key Feature | Prop | Personality | Size | Role | Distinctive | Variant Of |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M001 | 新手史萊姆 / Beginner Slime | Z1 新手村 | village slime | blob | round wobble | clear teal face and one soft crest | none | eager, bashful and welcoming | small | BASIC | single leaf-shaped highlight | — |
| M002 | 村口豆芽 / Gate Sprout | Z1 新手村 | garden sprout | plant | two-leaf upright teardrop | bright seed eyes | tiny welcome flag | polite and curious | small | MAGIC | flag bends like a smile | — |
| M003 | 木桶小咕 / Barrel Bouncer | Z1 新手村 | village scavenger | blob | barrel body with spring feet | wooden rim hat | empty bucket | cheerful and clumsy | small | TANK | one chipped barrel ring | — |
| M004 | 草帽鼴鼠 / Strawhat Mole | Z1 新手村 | garden burrower | quadruped | low wedge with broad hat | pink digging nose | straw hat | shy but determined | small | FAST | hat brim creates a strong circle | M002 |
| M005 | 風鈴小鳥 / Chime Chick | Z1 新手村 | dojo songbird | winged | upright teardrop with bell wings | blue throat chime | two hanging bells | musical and excitable | small | FLYING | bells form twin diamond tips | — |
| M006 | 石子甲蟲 / Pebble Beetle | Z1 新手村 | path beetle | crawler | low oval with pebble shell | three pale shell dots | none | patient and sturdy | small | ARMORED | uneven pebble ridge | — |
| M007 | 井邊水泡 / Well Bubble | Z1 新手村 | well sprite | blob | floating bubble with short fins | water-drop face | wooden dipper | friendly and distractible | small | TRICKSTER | dipper swings beneath body | — |
| M008 | 稻田蹦蹦 / Paddy Hopper | Z1 新手村 | field hopper | beast | long-legged diamond | golden rice tuft | rice-straw anklets | restless and playful | small | FAST | oversized spring knees | M006 |
| M009 | 木牌狐仔 / Signpost Fox | Z1 新手村 | roadside fox | quadruped | fox wedge with tall tail | painted arrow cheek mark | wooden sign shard | helpful and proud | small | TRICKSTER | tail ends in an arrow | — |
| M010 | 糰子地精 / Dumpling Gnome | Z1 新手村 | village helper | biped | round cap over tiny boots | three-dot cheek pattern | wooden spoon | hungry, comic and kind | small | BASIC | stacked dumpling hat | — |
| M011 | 洞窟蝙蝠 / Cave Bat | Z2 史萊姆平原 | plains cave bat | winged | wide V-wing with teardrop body | aqua ear membranes | none | sleepy but speedy | small | FLYING | single split-wing notch | — |
| M012 | 泥球水獺 / Mudball Otter | Z2 史萊姆平原 | puddle otter | quadruped | low oval with paddle tail | mud freckles | smooth river pebble | mischievous and warm | small | TRICKSTER | tail curls into a question mark | — |
| M013 | 泡泡蛙 / Bubble Frog | Z2 史萊姆平原 | pond frog | quadruped | wide squat wedge | bubble throat pouch | reed flute | bouncy and optimistic | small | MAGIC | three bubbles trail behind | — |
| M014 | 風箏蜻蜓 / Kite Dragonfly | Z2 史萊姆平原 | field insect | winged | cross-shaped wing span | kite-pattern wings | thread tail | daring and curious | small | FLYING | diamond tail kite | M013 |
| M015 | 草籽羊 / Grassseed Lamb | Z2 史萊姆平原 | meadow grazer | quadruped | soft wool oval with tiny horns | seed-pod curls | none | gentle and stubborn | small | TANK | seed-shaped wool tufts | — |
| M016 | 水窪蟹 / Puddle Crab | Z2 史萊姆平原 | water-edge crab | crawler | sideways low shield | blue puddle claws | shell cup | cheeky and alert | small | ARMORED | one claw is a shallow bowl | — |
| M017 | 彈簧蚱蜢 / Spring Grasshopper | Z2 史萊姆平原 | meadow insect | crawler | tall folded-knee profile | lime spring legs | none | overconfident and funny | small | FAST | coiled hind legs | — |
| M018 | 果凍魚 / Jellyfish | Z2 史萊姆平原 | rain jelly | blob | soft bell with ribbon base | rainbow gel stripe | tiny umbrella | dreamy and slow | small | MAGIC | umbrella stem through the bell | M016 |
| M019 | 彩傘菇獸 / Parasol Funglet | Z2 史萊姆平原 | field fungus | plant | mushroom cap over feet | painted cap spots | leaf parasol | cautious and polite | small | RANGED | cap opens like a fan | — |
| M020 | 旋風田鼠 / Whirl Vole | Z2 史萊姆平原 | wind vole | quadruped | round body with spiral tail | wind-swept whiskers | seed satchel | busy and bright | small | FAST | tail spiral reads at icon size | — |
| M021 | 水珠鹿 / Dewdrop Fawn | Z2 史萊姆平原 | morning grazer | quadruped | slender legs and teardrop ears | dew bead antlers | none | quiet and observant | small | BASIC | two dew beads between ears | — |
| M022 | 洞穴獸人小兵 / Cave Orc Grunt | Z3 哥布林洞穴 | cave faction | biped | compact crouched biped | ochre brow stripe | stone club | rough, loyal and readable | medium | BASIC | one oversized ear ring | — |
| M023 | 銅帽哥布林 / Coppercap Goblin | Z3 哥布林洞穴 | goblin scavenger | biped | pointed cap over narrow body | copper cap rim | folding pick | clever and boastful | small | TRICKSTER | cap makes a sharp roof silhouette | — |
| M024 | 回音蝠 / Echo Bat | Z3 哥布林洞穴 | cave bat | winged | twin-lobed wing fan | glowing throat ring | pebble rattle | nervous and inquisitive | small | RANGED | echo ring visible in profile | — |
| M025 | 礦鎬鼴工 / Pickaxe Moleworker | Z3 哥布林洞穴 | ore burrower | quadruped | low wedge with pick tail | dusty goggles | short pickaxe | focused and sleepy | small | TANK | pick forms a rear hook | — |
| M026 | 菌燈小鬼 / Fungus Lantern Imp | Z3 哥布林洞穴 | fungus goblin | biped | tiny biped under mushroom lamp | lantern-cap glow | mushroom lantern | helpful prankster | small | MAGIC | cap stem is a bright vertical | — |
| M027 | 繩梯蜥 / Rope-Ladder Lizard | Z3 哥布林洞穴 | cave lizard | quadruped | long low body with ladder tail | rope-pattern scales | coiled rope | nimble and practical | small | FAST | tail has two ladder rungs | M025 |
| M028 | 鐵桶甲蟲 / Ironbucket Beetle | Z3 哥布林洞穴 | ore beetle | crawler | round shell with bucket rim | iron faceplate | loose bucket lid | stubborn and comic | medium | ARMORED | lid tilts as a brow | — |
| M029 | 石縫蛇 / Crevice Snake | Z3 哥布林洞穴 | stone snake | crawler | thin S-curve | lantern-colored eyes | ore shard | quiet and watchful | small | TRICKSTER | head is a wedge key | — |
| M030 | 蘑菇推車怪 / Cartcap Crawler | Z3 哥布林洞穴 | fungus carrier | crawler | cap body with wheel feet | cartwheel spots | tiny ore cart | busy and grumpy | medium | TANK | cap and cart read as one shape | — |
| M031 | 晶礦咕 / Crystal Ore Gob | Z3 哥布林洞穴 | brittle goblin | biped | short biped with crystal shoulder | one cyan ore shoulder | ore sample pouch | proud and possessive | small | MAGIC | shoulder crystal is a single spike | M029 |
| M032 | 洞穴投石手 / Cavern Slinger | Z3 哥布林洞穴 | goblin scout | biped | lean biped with sling loop | amber cheek paint | cloth sling | playful and competitive | small | RANGED | sling loop creates a side halo | — |
| M033 | 鐘乳石龜 / Stalactite Tortoise | Z3 哥布林洞穴 | stone tortoise | quadruped | low dome with hanging spikes | safe rounded stalactites | none | slow, calm and unshakable | medium | TANK | three blunt ceiling spikes | — |
| M034 | 霧林精靈 / Mosswood Sprite | Z4 迷霧森林 | forest sprite | spirit-like | leafy upright teardrop | moss mask and fern collar | none | quiet, kind and elusive | small | MAGIC | fern collar creates a soft crown | — |
| M035 | 霧尾狐 / Mist-tail Fox | Z4 迷霧森林 | forest fox | quadruped | low fox with two curling tails | mist-white tail tips | none | clever and observant | small | TRICKSTER | tails overlap into a mist loop | — |
| M036 | 月葉蛾 / Moonleaf Moth | Z4 迷霧森林 | forest moth | winged | broad leaf wings | crescent wing markings | leaf satchel | gentle and curious | small | FLYING | wings close like a leaf | — |
| M037 | 藤蔓爪獸 / Vineclaw Beast | Z4 迷霧森林 | vine beast | quadruped | long forelimbs and hooked leaves | vine claws | fallen branch | playful and sneaky | medium | FAST | front claws make a forked silhouette | — |
| M038 | 苔背龜 / Mossback Turtle | Z4 迷霧森林 | moss tortoise | quadruped | round shell with fern ridge | mossy shell garden | none | patient and sleepy | medium | TANK | one fern leans backward | — |
| M039 | 露珠蜘蛛 / Dewdrop Spider | Z4 迷霧森林 | dew spider | crawler | eight legs under a round bead | large dew abdomen | silk loop | shy and precise | small | TRICKSTER | one silk loop trails like a lasso | M037 |
| M040 | 枯枝鹿 / Twig Deer | Z4 迷霧森林 | twig grazer | quadruped | slim body with branch antlers | dry-leaf ear tips | none | timid and alert | medium | BASIC | branch antlers stay soft and rounded | — |
| M041 | 霧笛蛙 / Fogwhistle Frog | Z4 迷霧森林 | mist frog | quadruped | squat body with trumpet throat | pale throat spiral | reed whistle | dramatic but harmless | small | RANGED | throat points forward like a horn | — |
| M042 | 花冠毛蟲 / Bloomcrown Caterpillar | Z4 迷霧森林 | flower caterpillar | crawler | segmented curve with flower head | petal crown | fallen petal cape | sleepy and sweet | small | MAGIC | petal crown is wider than body | — |
| M043 | 影步貓 / Shadowstep Cat | Z4 迷霧森林 | moss cat | quadruped | arched back and long paws | lavender paw shadows | leaf scarf | curious and sly | medium | FAST | shadow paws offset the feet | M041 |
| M044 | 樹洞熊芽 / Hollowtree Cub | Z4 迷霧森林 | tree hollow bear | biped | round cub with trunk shoulders | hollow belly window | acorn cap | brave and cuddly | medium | TANK | belly hollow is a dark circle | — |
| M045 | 蘚帽小樹 / Mosscap Sapling | Z4 迷霧森林 | forest sapling | plant | two-legged trunk with cap | moss cap and root toes | twig wand | earnest and easily startled | small | BASIC | cap tilts opposite the wand | — |
| M046 | 部落獸人 / Tribal Orc | Z5 獸人部落 | clan frontier | biped | broad biped with round shoulders | teal clan stripe | wooden shield | boisterous and protective | medium | ARMORED | shield has a friendly sun notch | — |
| M047 | 炭鼓獸 / Ember Drum Brute | Z5 獸人部落 | drum clan | biped | barrel chest with drum shoulders | ember cheek dots | hand drum | loud, joyful and rhythmic | medium | TANK | drum rim frames the torso | — |
| M048 | 皮盾犀童 / Hide-shield Rhino | Z5 獸人部落 | herd guard | quadruped | low rhino wedge with shield flank | soft horn cap | hide shield | brave and bashful | large | TANK | shield follows the horn curve | — |
| M049 | 紅土角羊 / Redclay Ram | Z5 獸人部落 | clay herd | quadruped | compact body with spiral horns | red-clay horn bands | none | stubborn and sunny | medium | BASIC | horns form a clay spiral pair | — |
| M050 | 戰鼓蜥 / War Drum Lizard | Z5 獸人部落 | drum lizard | quadruped | upright lizard with drum tail | painted scale chevrons | waist drum | competitive and comic | medium | FAST | tail drum creates a rear circle | M048 |
| M051 | 羽飾獵犬 / Feathercrest Hound | Z5 獸人部落 | clan hound | quadruped | broad hound with feather crest | blue feather mane | wood whistle | loyal and eager | medium | FAST | feather crest points forward | — |
| M052 | 石臼巨鼴 / Mortar Mole | Z5 獸人部落 | clan hauler | quadruped | heavy low mole with bowl back | stone nose guard | small mortar bowl | patient and hungry | large | TANK | bowl back is an oval hump | — |
| M053 | 銅環野豬 / Copperring Boar | Z5 獸人部落 | clan boar | quadruped | square boar body | copper ear rings | banner cord | bold and friendly | medium | ARMORED | rings are large readable loops | — |
| M054 | 篝火蜥蜴 / Campfire Skink | Z5 獸人部落 | camp reptile | quadruped | upright skink with flame tail | warm belly glow | charcoal cup | curious and cheeky | small | MAGIC | tail flame bends sideways | M052 |
| M055 | 旗尾牛 / Banner-tail Bison | Z5 獸人部落 | banner herd | quadruped | large bison wedge | banner-pattern tail | cloth banner | steady and proud | large | ARMORED | tail banner rises like a pennant | — |
| M056 | 泥甲犰狳 / Mudplate Armadillo | Z5 獸人部落 | clay burrower | quadruped | low segmented oval | mud plate bands | none | wary and determined | medium | ARMORED | plates are broad, not spiky | — |
| M057 | 鼓面龜 / Drumface Tortoise | Z5 獸人部落 | clan tortoise | quadruped | domed shell with front drum | painted drum face | wooden mallet | calm and ceremonial | large | TANK | shell front reads as a drum | — |
| M058 | 飛龍 / Wyvern | Z6 龍之谷 | valley wyvern | winged | compact winged dragon | cobalt wing membrane | none | proud and young | large | FLYING | short snout and broad wings | — |
| M059 | 熔岩翼蜥 / Lava-wing Drake | Z6 龍之谷 | lava drake | winged | sharp wing triangle and tail | ember wing veins | basalt scale | hot-headed and playful | medium | FLYING | wing edge has three ember cuts | — |
| M060 | 晶角蜥 / Crystalhorn Lizard | Z6 龍之谷 | crystal lizard | quadruped | low lizard with tall horn | cyan crystal horn | none | alert and vain | medium | MAGIC | one horn leans forward | — |
| M061 | 雲爪獅鷲 / Cloudclaw Gryphon | Z6 龍之谷 | sky gryphon | winged | chest-forward winged profile | cloud feather ruff | wind ribbon | noble but curious | large | FLYING | cloud ruff is a rounded fan | — |
| M062 | 火花蜥蜴 / Sparkscale Gecko | Z6 龍之谷 | spark gecko | quadruped | small arched gecko | spark-dot scales | none | hyper and cheerful | small | FAST | spark dots form a zigzag | M060 |
| M063 | 玄岩甲獸 / Basalt Shellbeast | Z6 龍之谷 | basalt beast | quadruped | heavy shell-backed quadruped | hex basalt plates | stone shard | quiet and dependable | large | TANK | back rises in two steps | — |
| M064 | 風脊飛蛇 / Windspine Serpent | Z6 龍之谷 | wind serpent | crawler | long airborne S-curve | fin-like wind spine | cloud bead | restless and graceful | medium | FLYING | spine fins create a saw rhythm | — |
| M065 | 焰尾狐龍 / Ember-tail Foxdragon | Z6 龍之谷 | foxdragon | quadruped | fox body with dragon tail | ember tail tuft | ribbon charm | clever and theatrical | medium | TRICKSTER | tail splits into a flame fork | — |
| M066 | 巖跳山羊 / Cliffskip Goat | Z6 龍之谷 | cliff goat | quadruped | springing goat silhouette | crystal hoof tips | cliff rope | fearless and bouncy | medium | FAST | hooves form four bright points | M064 |
| M067 | 硫磺蠑螈 / Sulfur Salamander | Z6 龍之谷 | sulfur salamander | crawler | low salamander with raised back | yellow heat spots | warm pebble | sleepy and warm | medium | MAGIC | spots trace a crescent | — |
| M068 | 龍巢小暴龍 / Nestling Raptor | Z6 龍之谷 | nest raptor | biped | small upright reptile with oversized feet | nest-feather collar | egg-shell buckler | impatient and cute | medium | FAST | feet are larger than head | — |
| M069 | 星火翼蝠 / Starflame Bat | Z6 龍之谷 | sky bat | winged | star-wing fan | star sparks in membrane | crystal bead | dramatic and shy | small | RANGED | one star is a four-point cut | — |
| M070 | 熔金蜈蚣 / Molten Gold Centipede | Z6 龍之谷 | lava crawler | crawler | long segmented ribbon | golden heat plates | ore bead chain | busy and fearless | medium | SWARM | plates alternate gold and plum | — |
| M071 | 塔影亡靈術士 / Tower Shade Caster | Z7 賢者之塔 | tower shade | spirit-like | hooded geometric biped | cyan rune face window | floating tome | quiet and bookish | medium | MAGIC | hood is a clean triangle | — |
| M072 | 書頁狐 / Pagefox | Z7 賢者之塔 | library fox | quadruped | fox wedge with page tail | paper-fold ears | bookmark ribbon | clever and distracted | small | TRICKSTER | tail unfolds into two pages | — |
| M073 | 黃銅魔像 / Brass Golem | Z7 賢者之塔 | tower construct | construct | stacked rectangular body | brass gear chest | loose key | patient and formal | large | TANK | one shoulder is a gear | — |
| M074 | 星屑蛾 / Stardust Moth | Z7 賢者之塔 | spell moth | winged | diamond wing silhouette | constellation wing dots | star map scrap | dreamy and precise | small | FLYING | dots form a tiny arc | M073 |
| M075 | 墨池章魚 / Inkwell Octopus | Z7 賢者之塔 | ink familiar | crawler | round head with eight ribbon arms | blue ink swirl | inkwell collar | creative and mischievous | medium | MAGIC | one arm holds a quill | — |
| M076 | 浮空鐘蟲 / Floating Bell Bug | Z7 賢者之塔 | tower bell bug | winged | bell abdomen with tiny wings | gold bell body | thread loop | punctual and nervous | small | RANGED | bell silhouette is a clear oval | — |
| M077 | 符文貓頭鷹 / Rune Owl | Z7 賢者之塔 | rune owl | winged | square feathered body | rune brow mark | stone tablet | wise and easily surprised | medium | RANGED | brow rune is a diamond | — |
| M078 | 藥瓶咕 / Potion Gob | Z7 賢者之塔 | alchemy goblin | biped | round biped with bottle belly | colored liquid window | cork vial | experimental and messy | small | MAGIC | vial belly glows without smoke | — |
| M079 | 棱鏡蜥 / Prism Gecko | Z7 賢者之塔 | prism gecko | quadruped | faceted low gecko | rainbow cheek facet | crystal tile | showy and quick | small | FAST | back facet makes a kite | M077 |
| M080 | 重力蟹 / Gravity Crab | Z7 賢者之塔 | gravity crustacean | crawler | wide crab under floating shell | orbiting shell stone | magnet ring | serious and wobbling | medium | ARMORED | shell floats one finger-width above body | — |
| M081 | 卷軸龜 / Scrollback Turtle | Z7 賢者之塔 | scroll tortoise | quadruped | dome shell with rolled edges | paper shell bands | sealed scroll | slow and scholarly | medium | TANK | shell edge curls like scrolls | — |
| M082 | 天文蟲 / Astrolabe Beetle | Z7 賢者之塔 | observatory beetle | crawler | round beetle with ring wings | brass orbit rings | star pointer | focused and tiny | small | RANGED | rings create a miniature orrery | — |
| M083 | 雲階羊 / Cloudstep Ram | Z7 賢者之塔 | tower ram | quadruped | floating ram with stair hooves | cloud hooves | paper stair token | proud and absent-minded | medium | FAST | four hooves step at different heights | — |
| M084 | 前線鐵甲騎 / Frontline Iron Knight | Z8 魔王城前線 | frontier armor beast | biped | plated biped with wedge shoulders | navy visor slit | blunt training lance | disciplined and uncertain | large | ARMORED | shoulders form a gate shape | — |
| M085 | 黑門獵犬 / Blackgate Hound | Z8 魔王城前線 | gate hound | quadruped | low hound with gate ears | red signal collar | gate tag | alert and loyal | medium | FAST | ears form twin battlements | — |
| M086 | 破盾甲蟲 / Breakshield Beetle | Z8 魔王城前線 | siege beetle | crawler | shield oval over six legs | cracked shell emblem | round shield scrap | determined and stubborn | medium | ARMORED | crack is decorative and nonviolent | — |
| M087 | 斷旗石獸 / Bannerbreak Stonebeast | Z8 魔王城前線 | fort stonebeast | quadruped | rocky wedge with flag back | split-color stone face | short banner pole | solemn but friendly | large | TANK | flag bends away from body | — |
| M088 | 弦翼蝠 / Stringwing Bat | Z8 魔王城前線 | scout bat | winged | thin wings with looped edges | signal-red wing thread | message ribbon | quick and watchful | small | FLYING | wing threads make two loops | M086 |
| M089 | 鋼齒鬣狗 / Steelfang Hyena | Z8 魔王城前線 | frontier hyena | quadruped | sloped back and broad jaw | steel tooth caps | supply tag | wry and energetic | medium | FAST | jaw has one bright rounded cap | — |
| M090 | 城垛蜥 / Battlement Lizard | Z8 魔王城前線 | wall lizard | quadruped | upright lizard with square back | brick-like scales | stone pennant | patient and tactical | medium | ARMORED | back scales are three blocks | — |
| M091 | 煙幕鼬 / Smokescreen Weasel | Z8 魔王城前線 | scout weasel | quadruped | long body with cloud tail | soft smoke puff | signal pouch | sly and helpful | small | TRICKSTER | tail is a clean smoke spiral | — |
| M092 | 鐵輪犀 / Ironwheel Rhino | Z8 魔王城前線 | siege rhino | quadruped | heavy rhino with wheel flank | iron wheel shoulder | rope harness | steady and unstoppable | large | TANK | wheel is an icon-like circle | — |
| M093 | 烽火蠍 / Beacon Scorpion | Z8 魔王城前線 | signal scorpion | crawler | raised tail with beacon tip | warm beacon bulb | signal cup | dramatic and fussy | medium | RANGED | tail ends in a lantern shape | M090 |
| M094 | 盾殼蟹 / Shieldshell Crab | Z8 魔王城前線 | moat crab | crawler | wide shield shell with side legs | navy shell face | small flag | defensive and cheeky | medium | ARMORED | shell is a front-facing badge | — |
| M095 | 黑曜傀儡 / Obsidian Automaton | Z8 魔王城前線 | frontier construct | construct | tall block with jointed arms | red core window | maintenance key | quiet and reliable | large | ELITE_NORMAL | one arm is a wedge brace | — |
| M096 | 裂牆熊 / Wallbreak Bear | Z8 魔王城前線 | gate bear | biped | broad bear with square paws | brick-paw markings | wooden ram cap | brave and embarrassed | large | TANK | paws are oversized rounded blocks | — |
| M097 | 斥候鷹獸 / Scout Hawkbeast | Z8 魔王城前線 | frontier hawk | winged | upright hawk with folded shield wings | signal-eye feather | map pennant | focused and impatient | medium | RANGED | folded wings make a shield silhouette | — |
| M098 | 風暴祈鳥 / Stormpray Bird | Z9 諸神黃昏 | storm bird | winged | tall bird with fan crest | cyan storm crest | bronze prayer tag | solemn and curious | large | FLYING | crest forks like lightning | — |
| M099 | 極光蛇 / Aurora Serpent | Z9 諸神黃昏 | aurora serpent | crawler | long ribbon S-curve | gradient aurora bands | star bead | calm and mesmerizing | medium | MAGIC | bands break at three points | — |
| M100 | 雷冠鹿 / Thundercrown Stag | Z9 諸神黃昏 | storm grazer | quadruped | tall deer with branching crown | cyan lightning antlers | cloud ribbon | noble and alert | large | MAGIC | antlers are lightning, not a crown | — |
| M101 | 雲穹鯨 / Skyvault Whale | Z9 諸神黃昏 | cloud whale | beast | large floating whale oval | star-window belly | cloud fin ribbon | gentle and immense | large | TANK | tail is a small cloud fan | M100 |
| M102 | 星環猿 / Star-ring Ape | Z9 諸神黃昏 | orbit ape | biped | upright ape with ring shoulders | orbit halo fragments | bronze bead | clever and restless | medium | FAST | rings sit behind shoulders | — |
| M103 | 裂虹鷹 / Riftbow Eagle | Z9 諸神黃昏 | storm eagle | winged | sharp upward wing V | split rainbow feather | glass shard | bold and observant | medium | RANGED | one feather makes a rainbow slash | — |
| M104 | 月蝕蟲 / Moon-eclipse Mantis | Z9 諸神黃昏 | eclipse mantis | crawler | tall folded mantis | dark moon abdomen | moon disc | patient and theatrical | medium | TRICKSTER | disc sits behind the head | — |
| M105 | 天鼓龜 / Skydrum Tortoise | Z9 諸神黃昏 | storm tortoise | quadruped | floating dome with cloud feet | drum-cloud shell | bronze mallet | slow and thunderous | large | TANK | shell has one central drum mark | — |
| M106 | 星砂狼 / Starsand Wolf | Z9 諸神黃昏 | star wolf | quadruped | long-legged wolf silhouette | star-sand mane | hourglass charm | quiet and loyal | medium | FAST | mane trails upward | — |
| M107 | 浮碑甲蟲 / Monolith Beetle | Z9 諸神黃昏 | monument beetle | crawler | vertical beetle with slab shell | floating stone plates | rune chip | serious and small | medium | ARMORED | shell plates hover in a stack | M104 |
| M108 | 雷晶螳螂 / Thundercrystal Mantis | Z9 諸神黃昏 | crystal mantis | crawler | angular raised forearms | crystal elbow sparks | storm bead | precise and proud | medium | RANGED | forearms make two lightning hooks | — |
| M109 | 蒼穹水母 / Firmament Jelly | Z9 諸神黃昏 | sky jelly | blob | bell with long cloud tendrils | constellation bell | tiny moon ring | distant and peaceful | medium | MAGIC | tendrils end in dots | — |
| M110 | 曙光翼蛇 / Dawnwing Serpent | Z9 諸神黃昏 | dawn serpent | crawler | winged ribbon curve | sunrise wing fins | golden thread | hopeful and swift | medium | FLYING | fins open like a sunrise | — |
| M111 | 碎星犀 / Starshard Rhino | Z9 諸神黃昏 | star rhino | quadruped | large wedge with crystal brow | star-shard horn | bronze neck ring | steady and heroic | large | ELITE_NORMAL | horn splits into three blunt points | — |
| M112 | 古殿碑靈 / Ancient Temple Idol | Z10 上古終焉神殿 | relic construct | construct | small monolith with feet | teal eye inset | none | silent and watchful | large | ARMORED | single inset eye is not organic | — |
| M113 | 時痕石龜 / Timeworn Stone Turtle | Z10 上古終焉神殿 | time tortoise | quadruped | layered dome with square feet | clock-like shell scar | stone token | patient and ancient | large | TANK | scar is a clean arc | — |
| M114 | 終焉門獸 / Endgate Beast | Z10 上古終焉神殿 | gate beast | quadruped | arched back with doorway chest | void-window chest | stone key | solemn and protective | large | ELITE_NORMAL | chest arch frames the face | — |
| M115 | 古鐘巨蟲 / Ancient Bell Crawler | Z10 上古終焉神殿 | relic crawler | crawler | long body with bell segments | ivory bell plates | bronze clapper | slow and resonant | medium | SWARM | three bell segments repeat cleanly | — |
| M116 | 白曜甲蟲 / Ivorylight Beetle | Z10 上古終焉神殿 | ivory beetle | crawler | bright oval shell with legs | white-gold shell cut | stone chip | timid and luminous | small | MAGIC | shell has one black inset | M114 |
| M117 | 黑砂獵犬 / Blacksand Hound | Z10 上古終焉神殿 | relic hound | quadruped | low hound with sand tail | black sand mane | ancient tag | quiet and loyal | medium | FAST | tail dissolves into square grains | — |
| M118 | 遺跡殼獸 / Relic Shellbeast | Z10 上古終焉神殿 | ruin beast | quadruped | nested shell rings | golden ruin bands | broken tile | calm and ponderous | large | ARMORED | shell rings are nested squares | — |
| M119 | 靜默碑靈 / Silent Tabletling | Z10 上古終焉神殿 | tablet construct | biped | upright tablet with tiny legs | white glyph face | blank tablet | serious and endearing | medium | MAGIC | glyph face remains one simple mark | M117 |
| M120 | 萬年根獸 / Evergreen Rootbeast | Z10 上古終焉神殿 | ancient root beast | plant | rooted quadruped with stone crown | deep teal root beard | antique seed | slow, wise and patient | large | TANK | roots form a stable tripod | — |

## 7. Species Families, Variants and Redundancy

- UNIQUE_BASE_DESIGN_COUNT=100
- VARIANT_DESIGN_COUNT=20
- UNRESOLVED_HIGH_REDUNDANCY_PAIRS=0
- DUPLICATE_ART_MONSTER_IDS=0
- DUPLICATE_RUNTIME_IDS=0

The 20 variants have explicit VARIANT_OF and VARIANT_DELTA fields in JSON. A variant must change silhouette, feature, prop or geometry; it is not a palette-only slot. The pre-art audit checks body class, silhouette geometry, species family, prop and defining feature. No unresolved high-redundancy pair remains, but Owner illustration review is still required before lock.

## 8. Boss, Lord and Spirit Boundary

Battlefield Bosses remain the ten ART001 Boss records and are not in the 120 rows. Lords remain a separate ten-identity registry; ART001 found dedicated Lord Trial art for Zones 1-2 only. Spirits remain exactly:
ink_drop_kelpie, whispering_void_kit, star_shell_hatchling, starpath_antlerling, fatty, obsidian_bastion.

Normal-Monster briefs intentionally avoid direct Boss, Lord and canonical Spirit copies. In particular, Z7 magical creatures are not the six Spirits, and Z10 relic constructs are not the final Boss or Lord.

## 9. Orphan Asset Review

ART001_ORPHAN_ASSET_COUNT=47. ART002 assigns no orphan to a proposed identity:
POSSIBLE_REUSE=0, LEGACY_ONLY=46, UNRELATED=0, UNKNOWN=0, TEST_ONLY=1. No image is renamed, moved, deleted, rewritten, promoted or generated.

## 10. Production Batches

ART_PRODUCTION_BATCH_COUNT=12, counting W0 style-lock representatives plus B01-B11 new-identity batches. W0 contains one current runtime identity per Zone. B01-B11 contain ten new identities each and follow adjacent Zone/theme transitions.

| Batch | Kind | Scope | Count | IDs |
|---|---|---|---:|---|
| W0-STYLE-LOCK | representative review | one existing runtime identity per Zone | 10 | M001, M011, M022, M034, M046, M058, M071, M084, M098, M112 |
| B01 | new identity illustration batch | Z1 + Z2 | 10 | M002, M003, M004, M005, M006, M007, M008, M009, M010, M012 |
| B02 | new identity illustration batch | Z2 + Z3 | 10 | M013, M014, M015, M016, M017, M018, M019, M020, M021, M023 |
| B03 | new identity illustration batch | Z3 | 10 | M024, M025, M026, M027, M028, M029, M030, M031, M032, M033 |
| B04 | new identity illustration batch | Z4 | 10 | M035, M036, M037, M038, M039, M040, M041, M042, M043, M044 |
| B05 | new identity illustration batch | Z4 + Z5 | 10 | M045, M047, M048, M049, M050, M051, M052, M053, M054, M055 |
| B06 | new identity illustration batch | Z5 + Z6 | 10 | M056, M057, M059, M060, M061, M062, M063, M064, M065, M066 |
| B07 | new identity illustration batch | Z6 + Z7 | 10 | M067, M068, M069, M070, M072, M073, M074, M075, M076, M077 |
| B08 | new identity illustration batch | Z7 + Z8 | 10 | M078, M079, M080, M081, M082, M083, M085, M086, M087, M088 |
| B09 | new identity illustration batch | Z8 + Z9 | 10 | M089, M090, M091, M092, M093, M094, M095, M096, M097, M099 |
| B10 | new identity illustration batch | Z9 | 10 | M100, M101, M102, M103, M104, M105, M106, M107, M108, M109 |
| B11 | new identity illustration batch | Z9 + Z10 | 10 | M110, M111, M113, M114, M115, M116, M117, M118, M119, M120 |

## 11. Recommended Production Order

1. W0-STYLE-LOCK: review one existing identity per Zone and approve the cross-Zone visual system; this does not approve current Monster art.
2. Produce B01-B11 in order, retaining the Zone direction and checking each batch for silhouette/family/prop redundancy.
3. For each accepted illustration, record Owner approval, canonical asset path and runtime mapping as separate gates.
4. Run visual QA on Desktop, iPad landscape, iPad portrait and Mobile only after accepted canonical assets are mapped.
5. Do not lock the roster or alter runtime from this candidate without an explicit Owner decision.

The first actual art wave should be W0 representative style-lock review, followed by B01 as the first new-identity illustration wave. ART002 does not start either wave.

## 12. Owner Review Checklist

Owner review must explicitly cover:
- Zone counts and progression rationale.
- All 120 bilingual identities and names.
- All 120 brief fields, including family balance and silhouette diversity.
- The seven keep-candidate decisions, one redesign-art decision and two decision-required identities.
- Variant parent/delta relationships and the zero unresolved high-redundancy target.
- Batch scope and review load.
- Boss/Lord/Spirit boundary and the Z3/Z8 taxonomy questions.

After approval only: MONSTER_ROSTER_LOCKED=YES. Until then this remains a candidate.

## 13. No-Mutation Statement

```
NEW_ART_GENERATED=NO
ART_ASSETS_MUTATED=0
APP_PY_CHANGED=NO
RUNTIME_CHANGED=NO
STATIC_RUNTIME_CHANGED=NO
MASTER_MERGE=NO
DEPLOY=NO
PRODUCTION_MUTATION=NO
TASK_INTRODUCED_FAILURES=0
```
