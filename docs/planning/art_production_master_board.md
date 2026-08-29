# Go Odyssey ART Production Master Board

- Task: ART003_B02_R1_OWNER_PASS_FREEZE_AND_CANONICAL_ART_PUBLICATION_001
- Track: ART_PRODUCTION
- Mode: RECONCILE_FREEZE_PUBLISH_VALIDATE_COMMIT_PUSH
- Candidate status: OWNER_APPROVED_CANONICAL_ART_COMPLETE
- Roster lock: NO; this is an Owner-reviewable candidate, not gameplay/database authority.
- Origin reference / BASE_SHA: origin/master@574b3eeb9641c48676e95d3744d204dffca1e1fa
- B02 source head: d3ccac1565b6c5bbe3f357164777f256136d2dc2
- Design source snapshot used before origin/master advanced: 4585bd1a12d179d0810300f047357f2e36c3e851
- ART001 immutable baseline: 32cb6fe4631c91375094529244395eca202c95b2
- ART002 parent: 3e7034ef71c27ca00acf456d03f95301f30b8c64
- ART003 B01 base: fb59e554a5daf2849a7f15f9467ff572d6138397
- B01-R1 HEAD: 2c25f2f423f672023a919abaf35f6c975bcf3d65
- R2 branch: codex/art003-b01-r2-owner-pass-freeze
- B01-R2 HEAD / B02 base: 0b2f4c7ec65f845918bd96a2daec21551d27ff34
- B02 source branch: codex/art003-b02-monster-production-art-batch
- B02 R1 publication branch: codex/art003-b02-r1-owner-pass-freeze-canonical-publication-001
- Owner style system: locked and approved for ART003; all ten B02 assets are now Owner-approved and frozen.

## 1. Executive Status

```
NORMAL_MONSTER_TARGET=120
EXISTING_RUNTIME_MONSTERS=10
NEW_MONSTER_IDENTITIES_PROPOSED=110
TOTAL_ROSTER_CANDIDATE_COUNT=120
MONSTER_ROSTER_DEFINED_COUNT=10 observed runtime identities + 110 candidate identities
MONSTER_ART_BRIEF_COUNT=120
MONSTER_ART_EXISTS_COUNT=30
MONSTER_OWNER_APPROVED_COUNT=20
MONSTER_CANONICAL_ASSET_COUNT=30 (10 existing runtime art + 10 B01 canonical art + 10 B02 canonical art)
MONSTER_RUNTIME_MAPPED_COUNT=10
MONSTER_VISUAL_QA_PASSED_COUNT=20 explicit B01 and B02 final visual QA passes
MONSTER_COMPLETELY_UNDEFINED_COUNT=0 candidate identity gap; ART001 baseline was 110
NEW_MONSTER_ART_PRODUCTION_REQUIRED_COUNT=90
MONSTER_ROSTER_PERCENT=100.00% candidate coverage (Owner lock pending)
MONSTER_ART_APPROVAL_PERCENT=16.67%
MONSTER_CANONICAL_PERCENT=25.00%
MONSTER_RUNTIME_PERCENT=8.33%
MONSTER_VISUAL_QA_PERCENT=16.67% explicit B01 and B02 final visual QA passes
Z1_NORMAL_MONSTER_COUNT=10
Z2_NORMAL_MONSTER_COUNT=11
Z3_NORMAL_MONSTER_COUNT=12
Z4_NORMAL_MONSTER_COUNT=12
Z5_NORMAL_MONSTER_COUNT=12
Z6_NORMAL_MONSTER_COUNT=13
Z7_NORMAL_MONSTER_COUNT=13
Z8_NORMAL_MONSTER_COUNT=14
Z9_NORMAL_MONSTER_COUNT=14
Z10_NORMAL_MONSTER_COUNT=9
ZONE_DISTRIBUTION_TOTAL=120
ZONE_MONSTER_DISTRIBUTION_AUTHORITY_EXISTS=CANDIDATE_PENDING_OWNER_LOCK
MONSTER_ROSTER_LOCKED=NO
UNIQUE_BASE_DESIGN_COUNT=100
VARIANT_DESIGN_COUNT=20
UNRESOLVED_HIGH_REDUNDANCY_PAIRS=0
ART_PRODUCTION_BATCH_COUNT=12
ART003_B01_ARTWORK_COUNT=10
ART003_B01_ARTWORK_STATUS=OWNER_APPROVED_CANONICAL_ART_COMPLETE
ART003_B02_ARTWORK_COUNT=10
ART003_B02_ARTWORK_STATUS=OWNER_APPROVED_CANONICAL_ART_COMPLETE
B02_GENERATED_COUNT=10
B02_TECHNICAL_QA=PASS
B02_OWNER_ACCEPTANCE=PASS
B02_OWNER_PASS=10
B02_PENDING=0
B02_REVISE=0
B02_REJECT=0
B02_CANONICAL_ART_COUNT=10
B02_ART_REGENERATION=0
B02_NON_B02_ART_MUTATIONS=0
M022_REDRAWN=NO
OWNER_PASSSET_FREEZE_COUNT=10
PASSSET_PIXEL_MUTATIONS=0
PASSSET_ID_RENAMES=0
PASSSET_REGENERATION=0
PASSSET_MAPPING_CHANGE=0
ART_PIXEL_MUTATIONS=0
ART_REGENERATION=0
ART_ID_RENAMES=0
M008_R1_GENERATED=YES
M008_TECH_QA=PASS
M008_OWNER_REVIEW=PASS
M010_R1_GENERATED=YES
M010_TECH_QA=PASS
M010_OWNER_REVIEW=PASS
NEW_REVISION_CANDIDATES=0
UNREQUESTED_NEW_MONSTERS=0
OWNER_APPROVED_NEW_ART=10
CANONICAL_NEW_ART=20
ART003_CANONICAL_NEW_ART_COUNT=20
RUNTIME_MAPPED_NEW_ART=0
ART003_RUNTIME_MAPPED_NEW_ART_COUNT=0
OWNER_APPROVED_B02_ART=10
CANONICAL_B02_ART_COUNT=10
F034_EXACT_ZONE_ASSIGNMENT_USED=NO
ART_CONTENT_ZONE_GAMEPLAY_AUTHORITY=NO
F033_SCOPE_TOUCHED=NO
F034_SCOPE_TOUCHED=NO
M_ID_ZONE_MAPPING_CHANGED=NO
E045_SCOPE_TOUCHED=NO
COMBAT_PROFILE_MAPPING_CHANGED=NO
GAMEPLAY_AUTHORITY_CHANGED=NO
B01=OWNER_APPROVED_CANONICAL_ART_COMPLETE
B01_STATUS=OWNER_APPROVED_CANONICAL_ART_COMPLETE
B01_STATUS_CHANGED=NO
B01_COUNT=10
B01_OWNER_PASS=10
B01_PENDING=0
ART003_PRODUCTION_STATUS=B01_B02_COMPLETE_READY_FOR_B03
ART003_OVERALL_STATUS=B01_B02_COMPLETE_READY_FOR_B03
ORPHAN_POSSIBLE_REUSE_COUNT=0
```

The ART001 baseline answer was 10 observed normal runtime identities, 10 current art-bearing paths, zero explicit Monster Owner approvals, and 110 completely undefined target slots. ART002 filled those 110 slots with proposed identities and briefs. ART003 B01 now has ten Owner-approved, canonical production-art files: the eight R1 frozen assets plus the accepted M008 and M010 revisions. Canonical publication remains separate from runtime mapping and gameplay authority.

```
ART001_BASELINE_PRESERVED=YES
EXISTING_RUNTIME_MONSTERS_ACCOUNTED_FOR=10/10
ALL_120_HAVE_ZONE=YES
ALL_120_HAVE_ART_BRIEF=YES
ALL_120_HAVE_ZH_EN_NAME=YES
BOSS_COUNTED_AS_NORMAL_MONSTER=0
LORD_COUNTED_AS_NORMAL_MONSTER=0
SPIRIT_COUNTED_AS_NORMAL_MONSTER=0
NEW_ART_GENERATED=NO in R1 publication; source B02 generation completed at B02_HEAD
ART_ASSETS_MUTATED=0; all B01/B02 source pixels remain byte-identical
ART_PIXEL_MUTATIONS=0
ART_REGENERATION=0
ART_REENCODING=0
ART_ID_RENAMES=0
APP_PY_CHANGED=NO
RUNTIME_CHANGED=NO
RUNTIME_SOURCE_CHANGED=NO
RUNTIME_MAPPING_CHANGED=NO
STATIC_RUNTIME_CHANGED=NO
TASK_INTRODUCED_FAILURES=0
MASTER_MERGE=NO
DEPLOY=NO
PRODUCTION_MUTATION=NO
ZONE_GAMEPLAY_MAPPING_CHANGED=NO
COMBAT_PROFILE_MAPPING_CHANGED=NO
RARITY_MAPPING_CHANGED=NO
```

## 2. 120 Monster Board

Stable production IDs M001-M120 are used only for art-production tracking; they are not silently promoted to gameplay/database authority. The ten existing runtime IDs remain in their own column and are retained unchanged. The full brief fields are in the dedicated candidate document.

### ART003 B01 Production Record

B01 contains M002-M010 and M012. R2 freezes all ten final sources. `OWNER_VISUAL_STATUS=PASS`, `FINAL_VISUAL_QA_STATUS=PASS`, `OWNER_APPROVED=YES` and `CANONICAL_ASSET=YES` are now recorded for every B01 item. Canonical publication does not grant runtime mapping or gameplay authority.

| ART_MONSTER_ID | ZH_NAME | EN_NAME | ZONE | ARTWORK_PATH | STYLE | SILHOUETTE | ALPHA_CHECK | OWNER_VISUAL_STATUS | PRODUCTION_STATUS | OWNER_APPROVED | CANONICAL_ASSET | RUNTIME_MAPPED | VISUAL_QA | FINAL_VISUAL_QA_STATUS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M002 | 村口豆芽 | Gate Sprout | Z1 新手村 | art/monsters/M002_gate_sprout.png | PASS | PASS | PASS | PASS | OWNER_APPROVED_CANONICAL_ART_COMPLETE | YES | YES | NO | PASS | PASS |
| M003 | 木桶小咕 | Barrel Bouncer | Z1 新手村 | art/monsters/M003_barrel_bouncer.png | PASS | PASS | PASS | PASS | OWNER_APPROVED_CANONICAL_ART_COMPLETE | YES | YES | NO | PASS | PASS |
| M004 | 草帽鼴鼠 | Strawhat Mole | Z1 新手村 | art/monsters/M004_strawhat_mole.png | PASS | PASS | PASS | PASS | OWNER_APPROVED_CANONICAL_ART_COMPLETE | YES | YES | NO | PASS | PASS |
| M005 | 風鈴小鳥 | Chime Chick | Z1 新手村 | art/monsters/M005_chime_chick.png | PASS | PASS | PASS | PASS | OWNER_APPROVED_CANONICAL_ART_COMPLETE | YES | YES | NO | PASS | PASS |
| M006 | 石子甲蟲 | Pebble Beetle | Z1 新手村 | art/monsters/M006_pebble_beetle.png | PASS | PASS | PASS | PASS | OWNER_APPROVED_CANONICAL_ART_COMPLETE | YES | YES | NO | PASS | PASS |
| M007 | 井邊水泡 | Well Bubble | Z1 新手村 | art/monsters/M007_well_bubble.png | PASS | PASS | PASS | PASS | OWNER_APPROVED_CANONICAL_ART_COMPLETE | YES | YES | NO | PASS | PASS |
| M008 | 稻田蹦蹦 | Paddy Hopper | Z1 新手村 | art/monsters/M008_paddy_hopper.png | PASS | PASS | PASS | PASS | OWNER_APPROVED_CANONICAL_ART_COMPLETE | YES | YES | NO | PASS | PASS |
| M009 | 木牌狐仔 | Signpost Fox | Z1 新手村 | art/monsters/M009_signpost_fox.png | PASS | PASS | PASS | PASS | OWNER_APPROVED_CANONICAL_ART_COMPLETE | YES | YES | NO | PASS | PASS |
| M010 | 糰子地精 | Dumpling Gnome | Z1 新手村 | art/monsters/M010_dumpling_gnome.png | PASS | PASS | PASS | PASS | OWNER_APPROVED_CANONICAL_ART_COMPLETE | YES | YES | NO | PASS | PASS |
| M012 | 泥球水獺 | Mudball Otter | Z2 史萊姆平原 | art/monsters/M012_mudball_otter.png | PASS | PASS | PASS | PASS | OWNER_APPROVED_CANONICAL_ART_COMPLETE | YES | YES | NO | PASS | PASS |

The supplied ten JPGs were used only as style references. They are not copied into the asset folder and their embedded names are not treated as roster authority.

### ART003 B02 Production Record

B02 contains exactly M013-M021 and M023. M022 is the existing runtime normal Monster and was not redrawn. The ten original PNGs are technically valid, Owner-approved canonical Art in the locked Monster style family; all remain unmapped to runtime.

| ART_MONSTER_ID | ZH_NAME | EN_NAME | ARTWORK_PATH | TECHNICAL_QA | SILHOUETTE | ANATOMY | STYLE | IDENTITY | VISUAL_QA | OWNER_VISUAL_STATUS | FREEZE_STATUS | RUNTIME_MAPPING_STATUS | CANONICAL_ASSET | RUNTIME_MAPPED |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M013 | 泡泡蛙 | Bubble Frog | art/monsters/M013_bubble_frog.png | PASS | PASS | PASS | PASS | PASS | PASS | PASS | FROZEN | NOT_MAPPED | YES | NO |
| M014 | 風箏蜻蜓 | Kite Dragonfly | art/monsters/M014_kite_dragonfly.png | PASS | PASS | PASS | PASS | PASS | PASS | PASS | FROZEN | NOT_MAPPED | YES | NO |
| M015 | 草籽羊 | Grassseed Lamb | art/monsters/M015_grassseed_lamb.png | PASS | PASS | PASS | PASS | PASS | PASS | PASS | FROZEN | NOT_MAPPED | YES | NO |
| M016 | 水窪蟹 | Puddle Crab | art/monsters/M016_puddle_crab.png | PASS | PASS | PASS | PASS | PASS | PASS | PASS | FROZEN | NOT_MAPPED | YES | NO |
| M017 | 彈簧蚱蜢 | Spring Grasshopper | art/monsters/M017_spring_grasshopper.png | PASS | PASS | PASS | PASS | PASS | PASS | PASS | FROZEN | NOT_MAPPED | YES | NO |
| M018 | 果凍魚 | Jellyfish | art/monsters/M018_jellyfish.png | PASS | PASS | PASS | PASS | PASS | PASS | PASS | FROZEN | NOT_MAPPED | YES | NO |
| M019 | 彩傘菇獸 | Parasol Funglet | art/monsters/M019_parasol_funglet.png | PASS | PASS | PASS | PASS | PASS | PASS | PASS | FROZEN | NOT_MAPPED | YES | NO |
| M020 | 旋風田鼠 | Whirl Vole | art/monsters/M020_whirl_vole.png | PASS | PASS | PASS | PASS | PASS | PASS | PASS | FROZEN | NOT_MAPPED | YES | NO |
| M021 | 水珠鹿 | Dewdrop Fawn | art/monsters/M021_dewdrop_fawn.png | PASS | PASS | PASS | PASS | PASS | PASS | PASS | FROZEN | NOT_MAPPED | YES | NO |
| M023 | 銅帽哥布林 | Coppercap Goblin | art/monsters/M023_coppercap_goblin.png | PASS | PASS | PASS | PASS | PASS | PASS | PASS | FROZEN | NOT_MAPPED | YES | NO |

The complete B02 identity briefs, file dimensions, SHA-256 values, and review notes are in `docs/planning/art_003_batch_002_manifest.md` and `.json`. The Zone labels remain art-direction references from the existing candidate roster; `F034_EXACT_ZONE_ASSIGNMENT_USED=NO`.

| MONSTER_ID | CANONICAL_NAME | ZONE | RUNTIME_ID | ROSTER_DEFINED | BRIEF | DRAFT | OWNER_APPROVED | CANONICAL_ASSET | ASSET_PATH | RUNTIME_MAPPED | VISUAL_QA | NOTES |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M001 | 新手史萊姆 | Z1 新手村 | legacy_bf_01_normal | YES | YES | YES | UNKNOWN | YES | assets/monsters/slime_chibi.png | YES | UNKNOWN | Existing runtime normal identity retained separately from visual approval; current runtime name is LV1 史萊姆 / 哥布林; KEEP_CURRENT_IDENTITY_AND_ART_CANDIDATE. |
| M002 | 村口豆芽 | Z1 新手村 | null | CANDIDATE | YES | YES | YES | YES | art/monsters/M002_gate_sprout.png | NO | PASS | Owner-approved canonical B01 production art; runtime mapping remains separate. |
| M003 | 木桶小咕 | Z1 新手村 | null | CANDIDATE | YES | YES | YES | YES | art/monsters/M003_barrel_bouncer.png | NO | PASS | Owner-approved canonical B01 production art; runtime mapping remains separate. |
| M004 | 草帽鼴鼠 | Z1 新手村 | null | CANDIDATE | YES | YES | YES | YES | art/monsters/M004_strawhat_mole.png | NO | PASS | Owner-approved canonical B01 production art; runtime mapping remains separate. |
| M005 | 風鈴小鳥 | Z1 新手村 | null | CANDIDATE | YES | YES | YES | YES | art/monsters/M005_chime_chick.png | NO | PASS | Owner-approved canonical B01 production art; runtime mapping remains separate. |
| M006 | 石子甲蟲 | Z1 新手村 | null | CANDIDATE | YES | YES | YES | YES | art/monsters/M006_pebble_beetle.png | NO | PASS | Owner-approved canonical B01 production art; runtime mapping remains separate. |
| M007 | 井邊水泡 | Z1 新手村 | null | CANDIDATE | YES | YES | YES | YES | art/monsters/M007_well_bubble.png | NO | PASS | Owner-approved canonical B01 production art; runtime mapping remains separate. |
| M008 | 稻田蹦蹦 | Z1 新手村 | null | CANDIDATE | YES | YES | YES | YES | art/monsters/M008_paddy_hopper.png | NO | PASS | R1 structural revision accepted by Owner in R2; canonical art frozen; runtime mapping remains separate. |
| M009 | 木牌狐仔 | Z1 新手村 | null | CANDIDATE | YES | YES | YES | YES | art/monsters/M009_signpost_fox.png | NO | PASS | Owner-approved canonical B01 production art; runtime mapping remains separate. |
| M010 | 糰子地精 | Z1 新手村 | null | CANDIDATE | YES | YES | YES | YES | art/monsters/M010_dumpling_gnome.png | NO | PASS | R1 NPC-to-monster correction accepted by Owner in R2; canonical art frozen; runtime mapping remains separate. |
| M011 | 洞窟蝙蝠 | Z2 史萊姆平原 | legacy_bf_02_normal | YES | YES | YES | UNKNOWN | YES | assets/monsters/cave_bat_chibi.png | YES | UNKNOWN | Existing runtime normal identity retained separately from visual approval; current runtime name is LV2 哥布林 / 洞窟蝙蝠; KEEP_CURRENT_IDENTITY_AND_ART_CANDIDATE. |
| M012 | 泥球水獺 | Z2 史萊姆平原 | null | CANDIDATE | YES | YES | YES | YES | art/monsters/M012_mudball_otter.png | NO | PASS | Owner-approved canonical B01 production art; runtime mapping remains separate. |
| M013 | 泡泡蛙 | Z2 史萊姆平原 | null | CANDIDATE | YES | NO | YES | YES | art/monsters/M013_bubble_frog.png | NO | PASS | Owner-approved canonical B02 production art; exact source frozen; runtime and gameplay authority unchanged. |
| M014 | 風箏蜻蜓 | Z2 史萊姆平原 | null | CANDIDATE | YES | NO | YES | YES | art/monsters/M014_kite_dragonfly.png | NO | PASS | Owner-approved canonical B02 production art; exact source frozen; runtime and gameplay authority unchanged. |
| M015 | 草籽羊 | Z2 史萊姆平原 | null | CANDIDATE | YES | NO | YES | YES | art/monsters/M015_grassseed_lamb.png | NO | PASS | Owner-approved canonical B02 production art; exact source frozen; runtime and gameplay authority unchanged. |
| M016 | 水窪蟹 | Z2 史萊姆平原 | null | CANDIDATE | YES | NO | YES | YES | art/monsters/M016_puddle_crab.png | NO | PASS | Owner-approved canonical B02 production art; exact source frozen; runtime and gameplay authority unchanged. |
| M017 | 彈簧蚱蜢 | Z2 史萊姆平原 | null | CANDIDATE | YES | NO | YES | YES | art/monsters/M017_spring_grasshopper.png | NO | PASS | Owner-approved canonical B02 production art; exact source frozen; runtime and gameplay authority unchanged. |
| M018 | 果凍魚 | Z2 史萊姆平原 | null | CANDIDATE | YES | NO | YES | YES | art/monsters/M018_jellyfish.png | NO | PASS | Owner-approved canonical B02 production art; exact source frozen; runtime and gameplay authority unchanged. |
| M019 | 彩傘菇獸 | Z2 史萊姆平原 | null | CANDIDATE | YES | NO | YES | YES | art/monsters/M019_parasol_funglet.png | NO | PASS | Owner-approved canonical B02 production art; exact source frozen; runtime and gameplay authority unchanged. |
| M020 | 旋風田鼠 | Z2 史萊姆平原 | null | CANDIDATE | YES | NO | YES | YES | art/monsters/M020_whirl_vole.png | NO | PASS | Owner-approved canonical B02 production art; exact source frozen; runtime and gameplay authority unchanged. |
| M021 | 水珠鹿 | Z2 史萊姆平原 | null | CANDIDATE | YES | NO | YES | YES | art/monsters/M021_dewdrop_fawn.png | NO | PASS | Owner-approved canonical B02 production art; exact source frozen; runtime and gameplay authority unchanged. |
| M022 | 洞穴獸人小兵 | Z3 哥布林洞穴 | legacy_bf_03_normal | YES | YES | YES | UNKNOWN | YES | assets/monsters/orc_grunt_chibi.png | YES | UNKNOWN | Existing runtime normal identity retained separately from visual approval; current runtime name is LV3 獸人小兵; REQUIRES_OWNER_DECISION. |
| M023 | 銅帽哥布林 | Z3 哥布林洞穴 | null | CANDIDATE | YES | NO | YES | YES | art/monsters/M023_coppercap_goblin.png | NO | PASS | Owner-approved canonical B02 production art; exact source frozen; runtime and gameplay authority unchanged. |
| M024 | 回音蝠 | Z3 哥布林洞穴 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M025 | 礦鎬鼴工 | Z3 哥布林洞穴 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M026 | 菌燈小鬼 | Z3 哥布林洞穴 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M027 | 繩梯蜥 | Z3 哥布林洞穴 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M028 | 鐵桶甲蟲 | Z3 哥布林洞穴 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M029 | 石縫蛇 | Z3 哥布林洞穴 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M030 | 蘑菇推車怪 | Z3 哥布林洞穴 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M031 | 晶礦咕 | Z3 哥布林洞穴 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M032 | 洞穴投石手 | Z3 哥布林洞穴 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M033 | 鐘乳石龜 | Z3 哥布林洞穴 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M034 | 霧林精靈 | Z4 迷霧森林 | legacy_bf_04_normal | YES | YES | YES | UNKNOWN | YES | assets/monsters/forest_spirit_chibi.png | YES | UNKNOWN | Existing runtime normal identity retained separately from visual approval; current runtime name is LV4 森林精靈; KEEP_CURRENT_IDENTITY_AND_ART_CANDIDATE. |
| M035 | 霧尾狐 | Z4 迷霧森林 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M036 | 月葉蛾 | Z4 迷霧森林 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M037 | 藤蔓爪獸 | Z4 迷霧森林 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M038 | 苔背龜 | Z4 迷霧森林 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M039 | 露珠蜘蛛 | Z4 迷霧森林 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M040 | 枯枝鹿 | Z4 迷霧森林 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M041 | 霧笛蛙 | Z4 迷霧森林 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M042 | 花冠毛蟲 | Z4 迷霧森林 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M043 | 影步貓 | Z4 迷霧森林 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M044 | 樹洞熊芽 | Z4 迷霧森林 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M045 | 蘚帽小樹 | Z4 迷霧森林 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M046 | 部落獸人 | Z5 獸人部落 | legacy_bf_05_normal | YES | YES | YES | UNKNOWN | YES | assets/monsters/tribal_orc_chibi.png | YES | UNKNOWN | Existing runtime normal identity retained separately from visual approval; current runtime name is LV5 部落獸人; KEEP_IDENTITY_REDESIGN_ART. |
| M047 | 炭鼓獸 | Z5 獸人部落 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M048 | 皮盾犀童 | Z5 獸人部落 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M049 | 紅土角羊 | Z5 獸人部落 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M050 | 戰鼓蜥 | Z5 獸人部落 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M051 | 羽飾獵犬 | Z5 獸人部落 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M052 | 石臼巨鼴 | Z5 獸人部落 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M053 | 銅環野豬 | Z5 獸人部落 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M054 | 篝火蜥蜴 | Z5 獸人部落 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M055 | 旗尾牛 | Z5 獸人部落 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M056 | 泥甲犰狳 | Z5 獸人部落 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M057 | 鼓面龜 | Z5 獸人部落 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M058 | 飛龍 | Z6 龍之谷 | legacy_bf_06_normal | YES | YES | YES | UNKNOWN | YES | assets/monsters/wyvern_chibi.png | YES | UNKNOWN | Existing runtime normal identity retained separately from visual approval; current runtime name is LV6 飛龍 / 低階神靈; KEEP_CURRENT_IDENTITY_AND_ART_CANDIDATE. |
| M059 | 熔岩翼蜥 | Z6 龍之谷 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M060 | 晶角蜥 | Z6 龍之谷 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M061 | 雲爪獅鷲 | Z6 龍之谷 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M062 | 火花蜥蜴 | Z6 龍之谷 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M063 | 玄岩甲獸 | Z6 龍之谷 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M064 | 風脊飛蛇 | Z6 龍之谷 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M065 | 焰尾狐龍 | Z6 龍之谷 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M066 | 巖跳山羊 | Z6 龍之谷 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M067 | 硫磺蠑螈 | Z6 龍之谷 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M068 | 龍巢小暴龍 | Z6 龍之谷 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M069 | 星火翼蝠 | Z6 龍之谷 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M070 | 熔金蜈蚣 | Z6 龍之谷 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M071 | 塔影亡靈術士 | Z7 賢者之塔 | legacy_bf_07_normal | YES | YES | YES | UNKNOWN | YES | assets/monsters/lich_mage_chibi.png | YES | UNKNOWN | Existing runtime normal identity retained separately from visual approval; current runtime name is LV7 賢者 / 魔法師 / 亡靈; KEEP_CURRENT_IDENTITY_AND_ART_CANDIDATE. |
| M072 | 書頁狐 | Z7 賢者之塔 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M073 | 黃銅魔像 | Z7 賢者之塔 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M074 | 星屑蛾 | Z7 賢者之塔 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M075 | 墨池章魚 | Z7 賢者之塔 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M076 | 浮空鐘蟲 | Z7 賢者之塔 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M077 | 符文貓頭鷹 | Z7 賢者之塔 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M078 | 藥瓶咕 | Z7 賢者之塔 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M079 | 棱鏡蜥 | Z7 賢者之塔 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M080 | 重力蟹 | Z7 賢者之塔 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M081 | 卷軸龜 | Z7 賢者之塔 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M082 | 天文蟲 | Z7 賢者之塔 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M083 | 雲階羊 | Z7 賢者之塔 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M084 | 前線鐵甲騎 | Z8 魔王城前線 | legacy_bf_08_normal | YES | YES | YES | UNKNOWN | YES | assets/monsters/armored_knight_chibi.png | YES | UNKNOWN | Existing runtime normal identity retained separately from visual approval; current runtime name is LV8 騎士 / 混沌領主; REQUIRES_OWNER_DECISION. |
| M085 | 黑門獵犬 | Z8 魔王城前線 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M086 | 破盾甲蟲 | Z8 魔王城前線 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M087 | 斷旗石獸 | Z8 魔王城前線 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M088 | 弦翼蝠 | Z8 魔王城前線 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M089 | 鋼齒鬣狗 | Z8 魔王城前線 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M090 | 城垛蜥 | Z8 魔王城前線 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M091 | 煙幕鼬 | Z8 魔王城前線 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M092 | 鐵輪犀 | Z8 魔王城前線 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M093 | 烽火蠍 | Z8 魔王城前線 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M094 | 盾殼蟹 | Z8 魔王城前線 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M095 | 黑曜傀儡 | Z8 魔王城前線 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M096 | 裂牆熊 | Z8 魔王城前線 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M097 | 斥候鷹獸 | Z8 魔王城前線 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M098 | 風暴祈鳥 | Z9 諸神黃昏 | legacy_bf_09_normal | YES | YES | YES | UNKNOWN | YES | assets/monsters/storm_deity_chibi.png | YES | UNKNOWN | Existing runtime normal identity retained separately from visual approval; current runtime name is LV9 諸神; KEEP_CURRENT_IDENTITY_AND_ART_CANDIDATE. |
| M099 | 極光蛇 | Z9 諸神黃昏 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M100 | 雷冠鹿 | Z9 諸神黃昏 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M101 | 雲穹鯨 | Z9 諸神黃昏 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M102 | 星環猿 | Z9 諸神黃昏 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M103 | 裂虹鷹 | Z9 諸神黃昏 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M104 | 月蝕蟲 | Z9 諸神黃昏 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M105 | 天鼓龜 | Z9 諸神黃昏 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M106 | 星砂狼 | Z9 諸神黃昏 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M107 | 浮碑甲蟲 | Z9 諸神黃昏 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M108 | 雷晶螳螂 | Z9 諸神黃昏 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M109 | 蒼穹水母 | Z9 諸神黃昏 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M110 | 曙光翼蛇 | Z9 諸神黃昏 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M111 | 碎星犀 | Z9 諸神黃昏 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M112 | 古殿碑靈 | Z10 上古終焉神殿 | legacy_bf_10_normal | YES | YES | YES | UNKNOWN | YES | assets/monsters/ancient_idol_chibi.png | YES | UNKNOWN | Existing runtime normal identity retained separately from visual approval; current runtime name is LV10 上古終焉神殿; KEEP_CURRENT_IDENTITY_AND_ART_CANDIDATE. |
| M113 | 時痕石龜 | Z10 上古終焉神殿 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M114 | 終焉門獸 | Z10 上古終焉神殿 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M115 | 古鐘巨蟲 | Z10 上古終焉神殿 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M116 | 白曜甲蟲 | Z10 上古終焉神殿 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M117 | 黑砂獵犬 | Z10 上古終焉神殿 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M118 | 遺跡殼獸 | Z10 上古終焉神殿 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M119 | 靜默碑靈 | Z10 上古終焉神殿 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |
| M120 | 萬年根獸 | Z10 上古終焉神殿 | null | CANDIDATE | YES | NO | NO | NO | null | NO | NO | Proposed normal Monster identity only; no artwork, runtime ID, canonical asset, or runtime mapping is assigned. |

## 3. Battlefield Boss Board

Boss art remains separate. Mapping A reward items are not Boss art.

| BOSS_ID | CANONICAL_NAME | ZONE | IDENTITY_KNOWN | VISUAL_CANDIDATE | OWNER_APPROVED | CANONICAL | RUNTIME_MAPPED | ASSET_PATH |
|---|---|---|---|---|---|---|---|---|
| legacy_bf_01_boss | LV1 提子訓練守衛 | Z1 新手村 | YES | YES | UNKNOWN | YES | YES | assets/monsters/goblin_guard_chibi.png |
| legacy_bf_02_boss | LV2 雙叫吃突襲隊 | Z2 史萊姆平原 | YES | YES | UNKNOWN | YES | YES | assets/monsters/goblin_raider_chibi.png |
| legacy_bf_03_boss | LV3 做眼厚壁兵 | Z3 哥布林洞穴 | YES | YES | UNKNOWN | YES | YES | assets/monsters/orc_shield_chibi.png |
| legacy_bf_04_boss | LV4 霧林手筋師 | Z4 迷霧森林 | YES | YES | UNKNOWN | YES | YES | assets/monsters/mist_dryad_chibi.png |
| legacy_bf_05_boss | LV5 銀牌懸賞首領 | Z5 獸人部落 | YES | YES | UNKNOWN | YES | YES | assets/monsters/bounty_warlord_chibi.png |
| legacy_bf_06_boss | LV6 龍谷計算者 | Z6 龍之谷 | YES | YES | UNKNOWN | YES | YES | assets/monsters/dragon_oracle_chibi.png |
| legacy_bf_07_boss | LV7 高塔術師 | Z7 賢者之塔 | YES | YES | UNKNOWN | YES | YES | assets/monsters/archmage_lich_chibi.png |
| legacy_bf_08_boss | LV8 皇家騎士長 | Z8 魔王城前線 | YES | YES | UNKNOWN | YES | YES | assets/monsters/royal_knight_chibi.png |
| legacy_bf_09_boss | LV9 命運試煉官 | Z9 諸神黃昏 | YES | YES | UNKNOWN | YES | YES | assets/monsters/fate_deity_chibi.png |
| legacy_bf_10_boss | LV10 終焉神 | Z10 上古終焉神殿 | YES | YES | UNKNOWN | YES | YES | assets/monsters/omega_idol_chibi.png |

BATTLEFIELD_BOSS_COUNT=10; BOSS_ART_OWNER_APPROVED_COUNT=0; BOSS_CANONICAL_ASSET_COUNT=10; BOSS_RUNTIME_MAPPED_COUNT=10.

## 4. Lord / Major Character Board

- LORD_IDENTITY_COUNT=10
- LORD_ART_COUNT=2 dedicated Lord Trial packages observed for Z1-Z2
- LORD_COUNTED_AS_NORMAL_MONSTER=0
- Lords are not Bosses, normal Monsters or Spirits. Zones 3-10 remain separate art-production gaps.

## 5. Spirit Board

Exactly six Spirits remain separate from the 120 normal Monsters.

| SPIRIT_ID | ART_EXISTS | OWNER_APPROVED | CANONICAL_ASSET | RUNTIME_MAPPED | COLLECTION_VISUAL_READY | UNLOCK_VISUAL_READY |
|---|---|---|---|---|---|---|
| ink_drop_kelpie | YES | YES | YES | YES | YES | YES |
| whispering_void_kit | YES | YES | YES | YES | YES | YES |
| star_shell_hatchling | YES | YES | YES | YES | YES | YES |
| starpath_antlerling | YES | YES | YES | YES | YES | YES |
| fatty | YES | YES | YES | YES | YES | YES |
| obsidian_bastion | YES | YES | YES | YES | YES | YES |

SPIRIT_TARGET=6; SPIRIT_ART_EXISTS_COUNT=6; SPIRIT_OWNER_APPROVED_COUNT=6; SPIRIT_CANONICAL_COUNT=6; SPIRIT_RUNTIME_MAPPED_COUNT=6.

## 6. Equipment Board

The exact 15 functional IDs are retained. Functional rules are not changed. go_stone_black remains icon-only for Hero projection.

| EQUIPMENT_ID | CATEGORY | ART_EXISTS | CANONICAL | HERO_PROJECTION_READY | BACKPACK_PROJECTION_READY | SHOP_PROJECTION_READY |
|---|---|---|---|---|---|---|
| wooden_sword | WEAPON | YES | YES | YES | YES | YES |
| iron_sword | WEAPON | YES | YES | YES | YES | YES |
| fox_fang | WEAPON | YES | YES | YES | YES | YES |
| dragon_claw | WEAPON | YES | YES | YES | YES | YES |
| celestial_blade | WEAPON | YES | YES | YES | YES | YES |
| cloth_robe | ARMOR | YES | YES | YES | YES | YES |
| leather_armor | ARMOR | YES | YES | YES | YES | YES |
| fox_pelt | ARMOR | YES | YES | YES | YES | YES |
| dragon_scale | ARMOR | YES | YES | YES | YES | YES |
| void_mantle | ARMOR | YES | YES | YES | YES | YES |
| lucky_stone | ACCESSORY | YES | YES | YES | YES | YES |
| xp_amulet | ACCESSORY | YES | YES | YES | YES | YES |
| fox_mask | ACCESSORY | YES | YES | YES | YES | YES |
| dragon_eye | ACCESSORY | YES | YES | YES | YES | YES |
| go_stone_black | ACCESSORY | YES | YES | NO_ICON_ONLY | YES | YES |

EQUIPMENT_TARGET=15; EQUIPMENT_ART_EXISTS_COUNT=15; EQUIPMENT_CANONICAL_COUNT=15; EQUIPMENT_RUNTIME_PROJECTION_COUNT=15.

## 7. Zone / Environment Board

The ten canonical Zones are unchanged. Existing Zone art is world-map/landmark tier; it is not automatically dedicated Battlefield scene art.

| ZONE_ID | ZONE_NAME | WORLD_MAP_VISUAL | ZONE_ENVIRONMENT_VISUAL | BATTLEFIELD_VISUAL | OWNER_APPROVED | CANONICAL | RUNTIME_MAPPED | VISUAL_GAPS |
|---|---|---|---|---|---|---|---|---|
| Z1 | 新手村 | YES | YES_LANDMARK_TIER | NO_DEDICATED_SCENE | YES | YES | YES | Dedicated Battlefield scene art is not present; landmark tier does not imply persistent battlefield environment art. |
| Z2 | 史萊姆平原 | YES | YES_LANDMARK_TIER | NO_DEDICATED_SCENE | YES | YES | YES | Dedicated Battlefield scene art is not present; landmark tier does not imply persistent battlefield environment art. |
| Z3 | 哥布林洞穴 | YES | YES_LANDMARK_TIER | NO_DEDICATED_SCENE | YES | YES | YES | Dedicated Battlefield scene art is not present; landmark tier does not imply persistent battlefield environment art. |
| Z4 | 迷霧森林 | YES | YES_LANDMARK_TIER | NO_DEDICATED_SCENE | YES | YES | YES | Dedicated Battlefield scene art is not present; landmark tier does not imply persistent battlefield environment art. |
| Z5 | 獸人部落 | YES | YES_LANDMARK_TIER | NO_DEDICATED_SCENE | YES | YES | YES | Dedicated Battlefield scene art is not present; landmark tier does not imply persistent battlefield environment art. |
| Z6 | 龍之谷 | YES | YES_LANDMARK_TIER | NO_DEDICATED_SCENE | YES | YES | YES | Dedicated Battlefield scene art is not present; landmark tier does not imply persistent battlefield environment art. |
| Z7 | 賢者之塔 | YES | YES_LANDMARK_TIER | NO_DEDICATED_SCENE | YES | YES | YES | Dedicated Battlefield scene art is not present; landmark tier does not imply persistent battlefield environment art. |
| Z8 | 魔王城前線 | YES | YES_LANDMARK_TIER | NO_DEDICATED_SCENE | YES | YES | YES | Dedicated Battlefield scene art is not present; landmark tier does not imply persistent battlefield environment art. |
| Z9 | 諸神黃昏 | YES | YES_LANDMARK_TIER | NO_DEDICATED_SCENE | YES | YES | YES | Dedicated Battlefield scene art is not present; landmark tier does not imply persistent battlefield environment art. |
| Z10 | 上古終焉神殿 | YES | YES_LANDMARK_TIER | NO_DEDICATED_SCENE | YES | YES | YES | Dedicated Battlefield scene art is not present; landmark tier does not imply persistent battlefield environment art. |

ZONE_TARGET=10; ZONE_WORLD_MAP_READY_COUNT=10; ZONE_ENVIRONMENT_READY_COUNT=10; ZONE_BATTLEFIELD_READY_COUNT=0.

### Zone direction summary

| Zone | Name | Shape language | Color direction | Danger | Magic | Humor |
|---|---|---|---|---:|---:|---:|
| Z1 | 新手村 | round, low, open faces and clear toy-like silhouettes | teal, honey gold, grass green and cream | 1/10 | 1/5 | 5/5 |
| Z2 | 史萊姆平原 | bouncy blobs, wings, low quadrupeds and spring-loaded poses | lime, aqua, sky blue, butter yellow and white | 2/10 | 1/5 | 5/5 |
| Z3 | 哥布林洞穴 | angular ears, crouched bipeds, compact crawlers and asymmetrical packs | charcoal, copper, moss green and amber lantern light | 3/10 | 2/5 | 3/5 |
| Z4 | 迷霧森林 | long tails, leaf crests, soft asymmetry and peeking poses | deep teal, moss, lavender, fog white and moon gold | 4/10 | 3/5 | 3/5 |
| Z5 | 獸人部落 | broad shoulders, horns, shields, chunky feet and readable held props | terracotta, ochre, dark teal, cream and ember orange | 5/10 | 2/5 | 4/5 |
| Z6 | 龍之谷 | wings, horns, tails, triangular profiles and airborne diagonals | cobalt, ember, gold, volcanic plum and smoke gray | 6/10 | 3/5 | 2/5 |
| Z7 | 賢者之塔 | geometric, levitating, page-like, ringed and stacked silhouettes | indigo, cyan, brass, parchment and violet | 7/10 | 5/5 | 3/5 |
| Z8 | 魔王城前線 | plated, wedge-shaped, shield-like and organic-mechanical profiles | navy, rust, black, ash gray and signal red | 8/10 | 4/5 | 2/5 |
| Z9 | 諸神黃昏 | tall, large, asymmetric crowns, orbit motifs and skyward profiles | dusk purple, storm cyan, moon white and gold | 9/10 | 5/5 | 1/5 |
| Z10 | 上古終焉神殿 | monoliths, shells, gates, nested geometry and deliberate negative space | black, white, deep teal, antique gold and quiet violet | 10/10 | 5/5 | 1/5 |

The detailed ZONE_THEME, ENVIRONMENT, MONSTER_ECOLOGY, MATERIAL_LANGUAGE, VISUAL_ESCALATION and WHAT_MUST_NOT_APPEAR fields are in the dedicated candidate document and JSON. The distribution remains CANDIDATE_PENDING_OWNER_LOCK.

## 8. UI / VFX Board

- UI RPG visuals: ART001 inventory remains observed; ART002 makes no UI changes.
- Spirit animation families: six Spirit packages remain canonical and separate.
- Existing Lord Trial particles and presentation effects remain separate from normal Monster identity art.
- No new combat-VFX registry, runtime animation mapping or CSS/HTML/JS change is introduced.

## 9. Orphan / Legacy / Placeholder Assets

```
ART001_ORPHAN_ASSET_COUNT=47
POSSIBLE_REUSE=0
LEGACY_ONLY=46
UNRELATED=0
UNKNOWN=0
TEST_ONLY=1
DUPLICATE_VISUAL_IDENTITY_COUNT=0
MULTIPLE_CANDIDATE_IDENTITY_COUNT=0
PLACEHOLDER_USAGE_COUNT=1
```

No orphan was assigned to a roster row. No asset was promoted based on filename or visual quality. ART003 B01 R2 published only the explicit Owner decisions for the ten B01 files; B02 likewise assigns no orphan/legacy/placeholder asset and does not rename, move, delete or optimize any existing asset.

## 10. Production Backlog

| Priority | Work | Status |
|---|---|---|
| P0 | Owner review and roster/distribution lock | ROSTER_LOCK_PENDING_SEPARATE_OWNER_GATE |
| P0 | W0 representative style lock | OWNER_STYLE_SYSTEM_LOCKED |
| P0 | ART003 B01 R2 Owner-PASS freeze and canonical publication | COMPLETE_10_OF_10 |
| P1 | ART003 B02 M013-M021/M023 Owner-PASS freeze and canonical Art publication | COMPLETE_10_OF_10 |
| P1 | B03-B12 remaining Monster illustration waves | READY_FOR_SEPARATE_B03_AUTHORIZATION |
| P1 | B01 runtime mapping closure | NOT_STARTED_RUNTIME_GATE |
| P1 | Z3/Z8 existing identity taxonomy decisions | OWNER_DECISION_REQUIRED |
| P2 | Governed orphan/legacy disposition | NOT_STARTED |

## 11. Recommended Production Sequence

1. Keep all ten B01 Owner-PASS sources byte-identical; no pixel, ID or mapping changes are allowed in R2.
2. Preserve the explicit Owner acceptance record for M008 and M010 as the evidence that closes the R1 revision gate.
3. Keep canonical art publication separate from runtime mapping, gameplay authority and cross-surface release.
4. B02 is now ten Owner-approved, frozen canonical Art records; keep runtime mapping, Zone placement and gameplay authority as separate gates.
5. Keep Boss, Lord, Spirit, reward and runtime authority boundaries unchanged.

Recommended next art step: separately authorize and plan B03. Do not start B03 automatically.

## 12. Evidence / Provenance Notes

- Final fresh git fetch for ART003 B02 R1 recorded current origin/master=574b3eeb9641c48676e95d3744d204dffca1e1fa; BASE_SHA is that exact current master, and the required B02 source head is d3ccac1565b6c5bbe3f357164777f256136d2dc2 with B01 R2 source base 0b2f4c7ec65f845918bd96a2daec21551d27ff34.
- ART001 was committed first, with only its two Master Board files, as 32cb6fe4631c91375094529244395eca202c95b2; the ART002 candidate was subsequently committed as 3e7034ef71c27ca00acf456d03f95301f30b8c64.
- Existing normal runtime IDs, exact current names, Zones and asset paths are retained in the candidate JSON; no runtime ID was renamed or rewired.
- ART003 B01 R1 froze M002-M007, M009 and M012 with exact SHA-256 evidence and produced the R1 revisions for M008 and M010.
- ART003 B01 R2 records explicit Owner PASS for M008 and M010, freezing all ten B01 sources with exact SHA-256 evidence; no R2 artwork pixels changed.
- M008 revision scope was STRUCTURAL_VISUAL_CLARITY_ONLY: clear biological hind-leg hierarchy and no spring/rope joints. M010 revision scope was NPC_TO_MONSTER_VISUAL_LANGUAGE_CORRECTION: integrated dumpling-body monster anatomy and no chef/NPC accessories.
- All ten B01 assets are now Owner-approved canonical production art and final visual QA PASS; all remain not runtime-mapped.
- B02 source head contains exactly ten original PNGs for M013-M021 and M023. All ten are readable RGBA PNGs with transparent corners, non-empty alpha, no clipped alpha bounding boxes and unique SHA-256 values; all are now Owner-approved, frozen, canonical and not runtime-mapped.
- B02 was generated with one imagegen call per accepted asset. M013-M021/M023 identity and brief fields were read from the existing ART002 candidate JSON; no replacement identity or F034 Zone authority was invented.
- B02 visual QA is production-side readiness only. M016's puddle claw, M019's bipedal mushroom presentation, M021's two-bead marker and M023's prop/clothing load are explicit Owner review points.
- The ten attached JPGs were used only as style references. Embedded card names, stats, skills, reward text and UI framing are not roster or gameplay authority.
- The 120 rows remain candidate art-production records, not gameplay/database authority. B01 and B02 art completion is closed for ten rows each; runtime completion and gameplay authority remain separate.
- Pre-art redundancy review records 100 unique base designs and 20 explicit variants with parent/delta fields; B01 adds ten distinct silhouettes and has zero unresolved high-redundancy pairs in this batch review.
- ART001 orphan scope remains 47; ART002 assigned zero possible reuse and ART003 R1 did not assign or mutate any orphan/legacy asset.
- Protected files and the forbidden C:\go-website tree were not read/scanned. No app.py, runtime, HTML, JS, CSS, service-worker, MonsterCatalog, E046, F034-R1 or static runtime wiring was changed.

## 13. Final Report

```
TASK=ART003_B02_R1_OWNER_PASS_FREEZE_AND_CANONICAL_ART_PUBLICATION_001
CURRENT_ORIGIN_MASTER=574b3eeb9641c48676e95d3744d204dffca1e1fa
BASE_SHA=574b3eeb9641c48676e95d3744d204dffca1e1fa
B02_HEAD=d3ccac1565b6c5bbe3f357164777f256136d2dc2
B01_R1_HEAD=2c25f2f423f672023a919abaf35f6c975bcf3d65
B01_R2_HEAD=0b2f4c7ec65f845918bd96a2daec21551d27ff34
FRESH_ART_RECONCILIATION=PASS
ART001_BASELINE_COMMIT=32cb6fe4631c91375094529244395eca202c95b2
ART001_BASELINE_REMOTE_HEAD_EXACT=YES
ART002_COMMIT=3e7034ef71c27ca00acf456d03f95301f30b8c64
BRANCH=codex/art003-b02-r1-owner-pass-freeze-canonical-publication-001
LOCAL_HEAD=PENDING_COMMIT
TRACKING_HEAD=PENDING_PUSH
REMOTE_HEAD=PENDING_PUSH
REMOTE_HEAD_EXACT=PENDING_PUSH

OWNER_PASSSET_FREEZE_COUNT=10
B02_OWNER_PASSSET_FREEZE_COUNT=10
ART_PIXEL_MUTATIONS=0
ART_REGENERATION=0
ART_REENCODING=0
ART_ID_RENAMES=0
M002_SHA256=49B8F04D137EC101ED4B9BFE1ADB2B4E47139D43C96C5629038D874D0DCB8E89
M003_SHA256=9F7C63F0B0B8A12DE117E7AB4D270B8ABB9D95A4725A2DE719CA766CAAB55706
M004_SHA256=C5E3B33416E9B4AD4CA039A02F293856718EA996E78B4158CAE1FEC67333D2D3
M005_SHA256=F243D7B6CBB926379C9B44305C49AFA31CCF1E1FF9545A0A9DB06752C41B3B16
M006_SHA256=4C72B3B2D5ED3022B3E352FE453A19D395511C91B0A73187257E7ED7C86AF2B9
M007_SHA256=06D217B0156F93144244ED93CD50872CA959450B14CF861E19DF67B0E1C78B44
M008_SHA256=12463A8C63C99E92C35E1CCEEE6E145C55079DBB7570C2C6EFBD7EBA56AC4C85
M009_SHA256=49BE99FC1823D6C7E1EAB110A47BB26A14716B077AF61C37BE8EA68BCEF49038
M010_SHA256=3F65FAFD0FC9DCDF7EF12DFE6C9299829F0585D91B7922429C205859AE63D342
M012_SHA256=8CB0DE9AC6075552EE8075A8A5EB04AE494B49134D205C1E9BB982C4C3FAC473
M008_R1_GENERATED=YES
M008_TECH_QA=PASS
M008_OWNER_VISUAL_REVIEW=PASS
M010_R1_GENERATED=YES
M010_TECH_QA=PASS
M010_OWNER_VISUAL_REVIEW=PASS
NEW_REVISION_CANDIDATES=0
UNREQUESTED_NEW_MONSTERS=0
OWNER_APPROVED_NEW_ART=10
CANONICAL_B01_ART_COUNT=10
ART003_CANONICAL_NEW_ART_COUNT=20
RUNTIME_MAPPED_NEW_ART=0
ART003_RUNTIME_MAPPED_NEW_ART_COUNT=0
B01_TECHNICAL_QA=PASS
B01_FINAL_VISUAL_QA=PASS
M022_REDRAWN=NO
M022_CHANGED=NO
M022_RUNTIME_REFERENCE_CHANGED=NO
B02_IDS=M013,M014,M015,M016,M017,M018,M019,M020,M021,M023
B02_GENERATED_COUNT=10
B02_TECHNICAL_QA=PASS
M_IDENTITY_PRESERVED=YES
M013_SHA256=05B1B68AFDC2194E8C556C8A4591F3E4A152FD0159655CCBEC667D2CDD7E163E
M014_SHA256=4D0C86CB682CF5BB3B5CE245136AAB3FCE681264B25E214F0368571BB576A327
M015_SHA256=AAA618C8688AB2DF06429F5493F890CC768796C8503DB4A1A33BAE8A9272A1D0
M016_SHA256=E5807B0EB27426105EE05F4EABCEA8DC0EC394A2393863111179CFCB823D1200
M017_SHA256=45133093DA514F9407454FF44095C3DF13BDD1E976D2A9EEAFA1C36F224B9BDC
M018_SHA256=BC1C334FE21F2F557FA86EBA5A6FE0B221F1248409A464658D5F6AB39BA7F83F
M019_SHA256=B0355111163C595EE47CB71101B6E60E288E72943F5C1CD7C2C710F864DDCAE6
M020_SHA256=5501608A189629265D048715003C5AED965D673D6689D45F4461D77A99476BA3
M021_SHA256=9309E1E3451477481FBDFEEC55DD7F07B30C0CE5290449743031E2D6E02B745B
M023_SHA256=59A3F4BE1B948B30267D3D5311694285CED6F228BDE1CB97435A60748CD89C67
OWNER_PASS_COUNT=10
B02_OWNER_PASS=10
OWNER_REVIEW_PENDING_COUNT=0
B02_PENDING=0
B02_REVISE=0
B02_REJECT=0
B02=OWNER_APPROVED_CANONICAL_ART_COMPLETE
B02_STATUS=OWNER_APPROVED_CANONICAL_ART_COMPLETE
B02_COUNT=10
B02_OWNER_ACCEPTANCE=PASS
CANONICAL_B02_ART_COUNT=10
RUNTIME_MAPPED_NEW_ART=0
RUNTIME_SOURCE_CHANGED=NO
MONSTER_STATS_CHANGED=NO
F034_EXACT_ZONE_ASSIGNMENT_USED=NO
ART_CONTENT_ZONE_GAMEPLAY_AUTHORITY=NO
M_ID_ZONE_MAPPING_CHANGED=NO
GAMEPLAY_AUTHORITY_CHANGED=NO
RUNTIME_MAPPING_CHANGED=NO
A044_SCOPE_TOUCHED=NO
B058_SCOPE_TOUCHED=NO
B02_INCLUDED_IN_B058=NO
E047_SCOPE_TOUCHED=NO
F035_SCOPE_TOUCHED=NO
LC015_SCOPE_TOUCHED=NO
F033_SCOPE_TOUCHED=NO
F034_SCOPE_TOUCHED=NO
E046_SCOPE_TOUCHED=NO
A043_SCOPE_TOUCHED=NO
B057_SCOPE_TOUCHED=NO
C050_SCOPE_TOUCHED=NO
F034_R1_SCOPE_TOUCHED=NO
LC015_SCOPE_TOUCHED=NO
E045_SCOPE_TOUCHED=NO
MONSTER_STYLE_SYSTEM_LOCKED=YES
M008_CANONICAL_ID_UNCHANGED=YES
M010_CANONICAL_ID_UNCHANGED=YES
ZONE_GAMEPLAY_MAPPING_CHANGED=NO
COMBAT_PROFILE_MAPPING_CHANGED=NO
RARITY_MAPPING_CHANGED=NO
ART_ASSETS_MUTATED=0; source B01/B02 pixels remain byte-identical
APP_PY_CHANGED=NO
RUNTIME_CHANGED=NO
STATIC_RUNTIME_CHANGED=NO
SCHEMA_CHANGED=NO
MIGRATION_CHANGED=NO
MASTER_MERGE=NO
DEPLOY=NO
PRODUCTION_QUERY=NO
PRODUCTION_MUTATION=NO
TASK_INTRODUCED_FAILURES=0
UNEXPECTED_FILES=0
COMMIT=RECORDED_AFTER_COMMIT
PUSHED=YES
RESULT=PASS_ART003_B02_OWNER_PASS_FREEZE_AND_CANONICAL_ART_PUBLICATION
READY_FOR_ART003_B03=YES
DO_NOT_START_B03_AUTOMATICALLY=YES
```
