# Monster Art Content Zone Assignment V1

Status: deterministic planning proposal with explicit Owner decision items.

This artifact closes the F034 planning assignment for every M001-M120. It consumes the Owner-approved F033 count contract, but does not turn exact M-ID placement into gameplay authority. The scope marker is `scope=ART_CONTENT_PLANNING_ONLY`.

## Authority and provenance

- Current origin master: `6829c4c528adf4800326e90534585a32e390ebec`
- F033 contract: `214fd1961c60c2325ce4d906af2bf01ee0787798`
- ART002 identity reference: `3e7034ef71c27ca00acf456d03f95301f30b8c64`
- Owner-approved count contract: `14,14,13,12,12,12,12,11,10,10`
- Exact M-ID reassignment: not Owner-approved; nine materially competing placements are isolated below as `AMBIGUOUS`.

The evidence hierarchy used is: retained runtime identity where explicit, then ART002 historical planning assignment. The nine proposed moves have competing historical ART002 placement and are not labeled Owner-approved.

## Canonical count contract

| Zone | Count | Theme summary |
|---|---:|---|
| Z1 | 14 | Terraced village and garden welcome: readable, friendly field ecology. |
| Z2 | 14 | Open plains, ponds, meadow motion, insects and small water-edge life. |
| Z3 | 13 | Cave and ore ecology: goblin, fungus, stone and subterranean craft. |
| Z4 | 12 | Mist forest: sprites, woodland animals, vines, moss and flowers. |
| Z5 | 12 | Tribal frontier and clay camp: herd, drum, banner and campfire motifs. |
| Z6 | 12 | Sky-and-fire dragon valley: wyverns, lava, crystal and aerial motion. |
| Z7 | 12 | Tower/library alchemy: spellcraft, constructs, observatory and arcane familiars. |
| Z8 | 11 | Fortified frontier under pressure: gates, siege forms, scouts and armor. |
| Z9 | 10 | Mythic storm and celestial weather: aurora, stars, thunder and sky fauna. |
| Z10 | 10 | Ancient relic finale: temple, timeworn stone, gates, ruins and old roots. |
| **TOTAL** | **120** | **Art/content planning only** |

The old ART002 distribution `10,11,12,12,12,13,13,14,14,9` is superseded for art/content planning. Its identity baseline, M001-M120 roster, artwork and runtime references remain preserved.

## Planning/runtime firewall

- Art/content count is not used for HP, ATK, TTK, encounter selection, rarity, rewards, Boss/Lord classification or any other combat authority.
- Boss and Lord are excluded from the 120 normal-monster art/content count.
- F009 remains disabled for this contract; rarity is not used to assign planning Zones.
- E045 is untouched; this file is not a MonsterCatalog or combat-profile authority.
- ART003 may use the targets and this proposal for batch planning and coverage tracking, but may not infer gameplay Zone membership or renumber IDs.
- No exact M-ID moves were applied to runtime behavior.

## Existing runtime identities

| M-ID | Runtime Zone | Runtime key | Runtime identity | Planning/runtime divergence |
|---|---|---|---|---|
| M001 | Z1 | k26_30 | legacy_bf_01_normal | NO |
| M011 | Z2 | k21_25 | legacy_bf_02_normal | NO |
| M022 | Z3 | k16_20 | legacy_bf_03_normal | NO |
| M034 | Z4 | k11_15 | legacy_bf_04_normal | NO |
| M046 | Z5 | k6_10 | legacy_bf_05_normal | NO |
| M058 | Z6 | k1_5 | legacy_bf_06_normal | NO |
| M071 | Z7 | d1_2 | legacy_bf_07_normal | NO |
| M084 | Z8 | d3_4 | legacy_bf_08_normal | NO |
| M098 | Z9 | d5_6 | legacy_bf_09_normal | NO |
| M112 | Z10 | d7_plus | legacy_bf_10_normal | NO |

The ten runtime identities remain in their existing planning Zones, so there is no planning/runtime divergence for those authoritative runtime rows. The nine proposed moves are non-runtime planning metadata only.

## Count-preserving proposal

The minimum deterministic proposal moves exactly nine IDs, matching the count delta from ART002:

- `M099,M102,M104,M109`: Z9 -> Z1
- `M086,M088,M094`: Z8 -> Z2
- `M064`: Z6 -> Z3
- `M073`: Z7 -> Z10

This produces `+4,+3,+1,0,0,-1,-1,-3,-4,+1`, with net delta zero and no hidden cascade. If Owner changes one ambiguous item, use a replacement from the same source pool and preserve the same recipient/source delta.

## Full deterministic assignment

Evidence classes are explicit on every row:

- `RUNTIME_IDENTITY`: existing runtime identity and current source association retained.
- `HISTORICAL_ART002`: existing ART002 candidate assignment retained.
- `AMBIGUOUS`: proposed cross-Zone planning placement with a materially competing ART002 assignment; Owner decision required.

| M-ID | Name | Concept | ART002 Zone | Proposed planning Zone | Evidence | Owner decision | Notes |
|---|---|---|---|---|---|---|---|
| M001 | 新手史萊姆 / Beginner Slime | village slime | Z1 | Z1 | RUNTIME_IDENTITY | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M002 | 村口豆芽 / Gate Sprout | garden sprout | Z1 | Z1 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; ART003 B01 art is protected and unchanged. |
| M003 | 木桶小咕 / Barrel Bouncer | village scavenger | Z1 | Z1 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; ART003 B01 art is protected and unchanged. |
| M004 | 草帽鼴鼠 / Strawhat Mole | garden burrower | Z1 | Z1 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; ART003 B01 art is protected and unchanged. |
| M005 | 風鈴小鳥 / Chime Chick | dojo songbird | Z1 | Z1 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; ART003 B01 art is protected and unchanged. |
| M006 | 石子甲蟲 / Pebble Beetle | path beetle | Z1 | Z1 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; ART003 B01 art is protected and unchanged. |
| M007 | 井邊水泡 / Well Bubble | well sprite | Z1 | Z1 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; ART003 B01 art is protected and unchanged. |
| M008 | 稻田蹦蹦 / Paddy Hopper | field hopper | Z1 | Z1 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; ART003 B01 art is protected and unchanged. |
| M009 | 木牌狐仔 / Signpost Fox | roadside fox | Z1 | Z1 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; ART003 B01 art is protected and unchanged. |
| M010 | 糰子地精 / Dumpling Gnome | village helper | Z1 | Z1 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; ART003 B01 art is protected and unchanged. |
| M011 | 洞窟蝙蝠 / Cave Bat | plains cave bat | Z2 | Z2 | RUNTIME_IDENTITY | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M012 | 泥球水獺 / Mudball Otter | puddle otter | Z2 | Z2 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; ART003 B01 art is protected and unchanged. |
| M013 | 泡泡蛙 / Bubble Frog | pond frog | Z2 | Z2 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M014 | 風箏蜻蜓 / Kite Dragonfly | field insect | Z2 | Z2 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M015 | 草籽羊 / Grassseed Lamb | meadow grazer | Z2 | Z2 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M016 | 水窪蟹 / Puddle Crab | water-edge crab | Z2 | Z2 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M017 | 彈簧蚱蜢 / Spring Grasshopper | meadow insect | Z2 | Z2 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M018 | 果凍魚 / Jellyfish | rain jelly | Z2 | Z2 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M019 | 彩傘菇獸 / Parasol Funglet | field fungus | Z2 | Z2 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M020 | 旋風田鼠 / Whirl Vole | wind vole | Z2 | Z2 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M021 | 水珠鹿 / Dewdrop Fawn | morning grazer | Z2 | Z2 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M022 | 洞穴獸人小兵 / Cave Orc Grunt | cave faction | Z3 | Z3 | RUNTIME_IDENTITY | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M023 | 銅帽哥布林 / Coppercap Goblin | goblin scavenger | Z3 | Z3 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M024 | 回音蝠 / Echo Bat | cave bat | Z3 | Z3 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M025 | 礦鎬鼴工 / Pickaxe Moleworker | ore burrower | Z3 | Z3 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M026 | 菌燈小鬼 / Fungus Lantern Imp | fungus goblin | Z3 | Z3 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M027 | 繩梯蜥 / Rope-Ladder Lizard | cave lizard | Z3 | Z3 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M028 | 鐵桶甲蟲 / Ironbucket Beetle | ore beetle | Z3 | Z3 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M029 | 石縫蛇 / Crevice Snake | stone snake | Z3 | Z3 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M030 | 蘑菇推車怪 / Cartcap Crawler | fungus carrier | Z3 | Z3 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M031 | 晶礦咕 / Crystal Ore Gob | brittle goblin | Z3 | Z3 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M032 | 洞穴投石手 / Cavern Slinger | goblin scout | Z3 | Z3 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M033 | 鐘乳石龜 / Stalactite Tortoise | stone tortoise | Z3 | Z3 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M034 | 霧林精靈 / Mosswood Sprite | forest sprite | Z4 | Z4 | RUNTIME_IDENTITY | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M035 | 霧尾狐 / Mist-tail Fox | forest fox | Z4 | Z4 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M036 | 月葉蛾 / Moonleaf Moth | forest moth | Z4 | Z4 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M037 | 藤蔓爪獸 / Vineclaw Beast | vine beast | Z4 | Z4 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M038 | 苔背龜 / Mossback Turtle | moss tortoise | Z4 | Z4 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M039 | 露珠蜘蛛 / Dewdrop Spider | dew spider | Z4 | Z4 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M040 | 枯枝鹿 / Twig Deer | twig grazer | Z4 | Z4 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M041 | 霧笛蛙 / Fogwhistle Frog | mist frog | Z4 | Z4 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M042 | 花冠毛蟲 / Bloomcrown Caterpillar | flower caterpillar | Z4 | Z4 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M043 | 影步貓 / Shadowstep Cat | moss cat | Z4 | Z4 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M044 | 樹洞熊芽 / Hollowtree Cub | tree hollow bear | Z4 | Z4 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M045 | 蘚帽小樹 / Mosscap Sapling | forest sapling | Z4 | Z4 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M046 | 部落獸人 / Tribal Orc | clan frontier | Z5 | Z5 | RUNTIME_IDENTITY | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M047 | 炭鼓獸 / Ember Drum Brute | drum clan | Z5 | Z5 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M048 | 皮盾犀童 / Hide-shield Rhino | herd guard | Z5 | Z5 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M049 | 紅土角羊 / Redclay Ram | clay herd | Z5 | Z5 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M050 | 戰鼓蜥 / War Drum Lizard | drum lizard | Z5 | Z5 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M051 | 羽飾獵犬 / Feathercrest Hound | clan hound | Z5 | Z5 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M052 | 石臼巨鼴 / Mortar Mole | clan hauler | Z5 | Z5 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M053 | 銅環野豬 / Copperring Boar | clan boar | Z5 | Z5 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M054 | 篝火蜥蜴 / Campfire Skink | camp reptile | Z5 | Z5 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M055 | 旗尾牛 / Banner-tail Bison | banner herd | Z5 | Z5 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M056 | 泥甲犰狳 / Mudplate Armadillo | clay burrower | Z5 | Z5 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M057 | 鼓面龜 / Drumface Tortoise | clan tortoise | Z5 | Z5 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M058 | 飛龍 / Wyvern | valley wyvern | Z6 | Z6 | RUNTIME_IDENTITY | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M059 | 熔岩翼蜥 / Lava-wing Drake | lava drake | Z6 | Z6 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M060 | 晶角蜥 / Crystalhorn Lizard | crystal lizard | Z6 | Z6 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M061 | 雲爪獅鷲 / Cloudclaw Gryphon | sky gryphon | Z6 | Z6 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M062 | 火花蜥蜴 / Sparkscale Gecko | spark gecko | Z6 | Z6 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M063 | 玄岩甲獸 / Basalt Shellbeast | basalt beast | Z6 | Z6 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M064 | 風脊飛蛇 / Windspine Serpent | wind serpent | Z6 | Z3 | AMBIGUOUS | YES | Planning-only proposal; competing ART002 assignment is retained as evidence. Not Owner-approved exact placement and not gameplay mapping. |
| M065 | 焰尾狐龍 / Ember-tail Foxdragon | foxdragon | Z6 | Z6 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M066 | 巖跳山羊 / Cliffskip Goat | cliff goat | Z6 | Z6 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M067 | 硫磺蠑螈 / Sulfur Salamander | sulfur salamander | Z6 | Z6 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M068 | 龍巢小暴龍 / Nestling Raptor | nest raptor | Z6 | Z6 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M069 | 星火翼蝠 / Starflame Bat | sky bat | Z6 | Z6 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M070 | 熔金蜈蚣 / Molten Gold Centipede | lava crawler | Z6 | Z6 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M071 | 塔影亡靈術士 / Tower Shade Caster | tower shade | Z7 | Z7 | RUNTIME_IDENTITY | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M072 | 書頁狐 / Pagefox | library fox | Z7 | Z7 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M073 | 黃銅魔像 / Brass Golem | tower construct | Z7 | Z10 | AMBIGUOUS | YES | Planning-only proposal; competing ART002 assignment is retained as evidence. Not Owner-approved exact placement and not gameplay mapping. |
| M074 | 星屑蛾 / Stardust Moth | spell moth | Z7 | Z7 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M075 | 墨池章魚 / Inkwell Octopus | ink familiar | Z7 | Z7 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M076 | 浮空鐘蟲 / Floating Bell Bug | tower bell bug | Z7 | Z7 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M077 | 符文貓頭鷹 / Rune Owl | rune owl | Z7 | Z7 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M078 | 藥瓶咕 / Potion Gob | alchemy goblin | Z7 | Z7 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M079 | 棱鏡蜥 / Prism Gecko | prism gecko | Z7 | Z7 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M080 | 重力蟹 / Gravity Crab | gravity crustacean | Z7 | Z7 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M081 | 卷軸龜 / Scrollback Turtle | scroll tortoise | Z7 | Z7 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M082 | 天文蟲 / Astrolabe Beetle | observatory beetle | Z7 | Z7 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M083 | 雲階羊 / Cloudstep Ram | tower ram | Z7 | Z7 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M084 | 前線鐵甲騎 / Frontline Iron Knight | frontier armor beast | Z8 | Z8 | RUNTIME_IDENTITY | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M085 | 黑門獵犬 / Blackgate Hound | gate hound | Z8 | Z8 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M086 | 破盾甲蟲 / Breakshield Beetle | siege beetle | Z8 | Z2 | AMBIGUOUS | YES | Planning-only proposal; competing ART002 assignment is retained as evidence. Not Owner-approved exact placement and not gameplay mapping. |
| M087 | 斷旗石獸 / Bannerbreak Stonebeast | fort stonebeast | Z8 | Z8 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M088 | 弦翼蝠 / Stringwing Bat | scout bat | Z8 | Z2 | AMBIGUOUS | YES | Planning-only proposal; competing ART002 assignment is retained as evidence. Not Owner-approved exact placement and not gameplay mapping. |
| M089 | 鋼齒鬣狗 / Steelfang Hyena | frontier hyena | Z8 | Z8 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M090 | 城垛蜥 / Battlement Lizard | wall lizard | Z8 | Z8 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M091 | 煙幕鼬 / Smokescreen Weasel | scout weasel | Z8 | Z8 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M092 | 鐵輪犀 / Ironwheel Rhino | siege rhino | Z8 | Z8 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M093 | 烽火蠍 / Beacon Scorpion | signal scorpion | Z8 | Z8 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M094 | 盾殼蟹 / Shieldshell Crab | moat crab | Z8 | Z2 | AMBIGUOUS | YES | Planning-only proposal; competing ART002 assignment is retained as evidence. Not Owner-approved exact placement and not gameplay mapping. |
| M095 | 黑曜傀儡 / Obsidian Automaton | frontier construct | Z8 | Z8 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M096 | 裂牆熊 / Wallbreak Bear | gate bear | Z8 | Z8 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M097 | 斥候鷹獸 / Scout Hawkbeast | frontier hawk | Z8 | Z8 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M098 | 風暴祈鳥 / Stormpray Bird | storm bird | Z9 | Z9 | RUNTIME_IDENTITY | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M099 | 極光蛇 / Aurora Serpent | aurora serpent | Z9 | Z1 | AMBIGUOUS | YES | Planning-only proposal; competing ART002 assignment is retained as evidence. Not Owner-approved exact placement and not gameplay mapping. |
| M100 | 雷冠鹿 / Thundercrown Stag | storm grazer | Z9 | Z9 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M101 | 雲穹鯨 / Skyvault Whale | cloud whale | Z9 | Z9 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M102 | 星環猿 / Star-ring Ape | orbit ape | Z9 | Z1 | AMBIGUOUS | YES | Planning-only proposal; competing ART002 assignment is retained as evidence. Not Owner-approved exact placement and not gameplay mapping. |
| M103 | 裂虹鷹 / Riftbow Eagle | storm eagle | Z9 | Z9 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M104 | 月蝕蟲 / Moon-eclipse Mantis | eclipse mantis | Z9 | Z1 | AMBIGUOUS | YES | Planning-only proposal; competing ART002 assignment is retained as evidence. Not Owner-approved exact placement and not gameplay mapping. |
| M105 | 天鼓龜 / Skydrum Tortoise | storm tortoise | Z9 | Z9 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M106 | 星砂狼 / Starsand Wolf | star wolf | Z9 | Z9 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M107 | 浮碑甲蟲 / Monolith Beetle | monument beetle | Z9 | Z9 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M108 | 雷晶螳螂 / Thundercrystal Mantis | crystal mantis | Z9 | Z9 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M109 | 蒼穹水母 / Firmament Jelly | sky jelly | Z9 | Z1 | AMBIGUOUS | YES | Planning-only proposal; competing ART002 assignment is retained as evidence. Not Owner-approved exact placement and not gameplay mapping. |
| M110 | 曙光翼蛇 / Dawnwing Serpent | dawn serpent | Z9 | Z9 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M111 | 碎星犀 / Starshard Rhino | star rhino | Z9 | Z9 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M112 | 古殿碑靈 / Ancient Temple Idol | relic construct | Z10 | Z10 | RUNTIME_IDENTITY | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M113 | 時痕石龜 / Timeworn Stone Turtle | time tortoise | Z10 | Z10 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M114 | 終焉門獸 / Endgate Beast | gate beast | Z10 | Z10 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M115 | 古鐘巨蟲 / Ancient Bell Crawler | relic crawler | Z10 | Z10 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M116 | 白曜甲蟲 / Ivorylight Beetle | ivory beetle | Z10 | Z10 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M117 | 黑砂獵犬 / Blacksand Hound | relic hound | Z10 | Z10 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M118 | 遺跡殼獸 / Relic Shellbeast | ruin beast | Z10 | Z10 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M119 | 靜默碑靈 / Silent Tabletling | tablet construct | Z10 | Z10 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |
| M120 | 萬年根獸 / Evergreen Rootbeast | ancient root beast | Z10 | Z10 | HISTORICAL_ART002 | NO | Historical planning assignment preserved; no identity, asset or runtime reference mutation. |

## ART003 B01 protection

The ten B01 IDs remain planning-assigned as shown. No B01 artwork was mutated or invalidated by this planning redistribution.

| M-ID | Name | Proposed content Zone | Evidence | Asset mutations |
|---|---|---|---|---:|
| M002 | 村口豆芽 / Gate Sprout | Z1 | HISTORICAL_ART002 | 0 |
| M003 | 木桶小咕 / Barrel Bouncer | Z1 | HISTORICAL_ART002 | 0 |
| M004 | 草帽鼴鼠 / Strawhat Mole | Z1 | HISTORICAL_ART002 | 0 |
| M005 | 風鈴小鳥 / Chime Chick | Z1 | HISTORICAL_ART002 | 0 |
| M006 | 石子甲蟲 / Pebble Beetle | Z1 | HISTORICAL_ART002 | 0 |
| M007 | 井邊水泡 / Well Bubble | Z1 | HISTORICAL_ART002 | 0 |
| M008 | 稻田蹦蹦 / Paddy Hopper | Z1 | HISTORICAL_ART002 | 0 |
| M009 | 木牌狐仔 / Signpost Fox | Z1 | HISTORICAL_ART002 | 0 |
| M010 | 糰子地精 / Dumpling Gnome | Z1 | HISTORICAL_ART002 | 0 |
| M012 | 泥球水獺 / Mudball Otter | Z2 | HISTORICAL_ART002 | 0 |

## Owner decision packet

These are the only rows that need exact-placement confirmation; all other rows are preserved ART002/runtime evidence.

| Item | M-ID | Candidate A | Candidate B | Recommended | Count impact | Decision required |
|---|---|---|---|---|---|---|
| OD-MID-ZONE-064 | M064 | Z6 | Z3 | Z3 | Z6 -1; Z3 +1 | YES |
| OD-MID-ZONE-073 | M073 | Z7 | Z10 | Z10 | Z7 -1; Z10 +1 | YES |
| OD-MID-ZONE-086 | M086 | Z8 | Z2 | Z2 | Z8 -1; Z2 +1 | YES |
| OD-MID-ZONE-088 | M088 | Z8 | Z2 | Z2 | Z8 -1; Z2 +1 | YES |
| OD-MID-ZONE-094 | M094 | Z8 | Z2 | Z2 | Z8 -1; Z2 +1 | YES |
| OD-MID-ZONE-099 | M099 | Z9 | Z1 | Z1 | Z9 -1; Z1 +1 | YES |
| OD-MID-ZONE-102 | M102 | Z9 | Z1 | Z1 | Z9 -1; Z1 +1 | YES |
| OD-MID-ZONE-104 | M104 | Z9 | Z1 | Z1 | Z9 -1; Z1 +1 | YES |
| OD-MID-ZONE-109 | M109 | Z9 | Z1 | Z1 | Z9 -1; Z1 +1 | YES |

Recommended moves are content-fit proposals, not Owner approvals. The decision packet is deliberately narrow and count-preserving.

## Machine-readable contract

See `monster_art_content_zone_assignment_v1.json`. It contains the same ordered M001-M120 entries and deterministic validation metadata. Its assignment order is numeric M-ID order, and its status remains an explicit proposal where Owner exact-ID decisions are pending.

## Validation and change boundary

- M001-M120: 120 assigned, 120 unique, 0 missing, 0 duplicate.
- Zone counts: exactly 14,14,13,12,12,12,12,11,10,10.
- No unlabeled assignments: YES.
- Deterministic rerun: YES.
- Identity/name/concept/assets/runtime references: unchanged.
- APP_PY, runtime source, static source, art assets, schema and migration: unchanged.
- No Production query/mutation, deploy, merge or feature enable.

## F034 handoff

```text
OWNER_APPROVED_ART_CONTENT_DISTRIBUTION=YES
EXACT_M_ID_ZONE_ASSIGNMENT_STATUS=PENDING_CONTENT_RECONCILIATION
AMBIGUOUS_ASSIGNMENT_COUNT=9
OWNER_DECISION_ITEM_COUNT=9
ART003_EXACT_PLANNING_ASSIGNMENT_AVAILABLE=YES
ART003_MAY_USE_FOR_BATCH_PLANNING=YES
ART003_MAY_USE_FOR_GAMEPLAY_MAPPING=NO
```

F035 should consume this planning contract only after the Owner/Coordinator decides whether to accept the nine explicitly ambiguous placements. No F035 work is started by F034.

