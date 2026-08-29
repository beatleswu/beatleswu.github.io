# Go Odyssey ART003 B02 Production Manifest

## 1. Scope and provenance

| Field | Value |
|---|---|
| Task | `ART003_B02_MONSTER_PRODUCTION_ART_BATCH_001` |
| Track | `ART` |
| Mode | `RECONCILE_GENERATE_QA_DOCUMENT_COMMIT_PUSH` |
| Current origin/master | `6829c4c528adf4800326e90534585a32e390ebec` |
| Base SHA / B01 R2 HEAD | `0b2f4c7ec65f845918bd96a2daec21551d27ff34` |
| Isolated worktree | `D:\go-website-art003-b02` |
| Style system | Locked and Owner-approved; B01 visual family preserved |
| Identity source | `docs/planning/art_120_monster_roster_candidate.json` |
| F034 exact Zone assignment | Not used; Zone labels below are art-direction references only |

This manifest contains exactly the ten requested B02 normal-Monster identities. It does not add a runtime identity, gameplay profile, encounter mapping, Zone gameplay mapping, Boss, Lord or Spirit identity. `M022` is excluded because it is an existing runtime normal Monster and was not redrawn.

## 2. Batch result

```text
B02_COUNT=10
B02_GENERATED_COUNT=10
B02_IDS=M013,M014,M015,M016,M017,M018,M019,M020,M021,M023
M022_REDRAWN=NO
M_IDENTITY_PRESERVED=YES
B02_TECHNICAL_QA=PASS
B02_OWNER_ACCEPTANCE=PENDING
OWNER_PASS_COUNT=0
OWNER_REVIEW_PENDING_COUNT=10
CANONICAL_B02_ART_COUNT=0
RUNTIME_MAPPED_NEW_ART=0
```

Each candidate is a new isolated transparent PNG. The files are ready for Owner visual review; “canonical” and “Owner approved” remain `NO`/`PENDING` until that separate gate occurs.

## 3. B02 asset records

All Zone values in this table are copied from the existing ART002 candidate identity source for art context. They are not F034 authority and were not used to change any M-ID → Zone mapping.

| M-ID | ZH name | EN name | Identity / production brief | Asset path | Dimensions | SHA-256 | Technical QA | Visual QA | Owner |
|---|---|---|---|---|---:|---|---|---|---|
| M013 | 泡泡蛙 | Bubble Frog | Pond-frog quadruped; wide squat wedge; bubble throat pouch; reed flute; bouncy/optimistic; three trailing bubbles; MAGIC | `art/monsters/M013_bubble_frog.png` | 1536×1024 | `05B1B68AFDC2194E8C556C8A4591F3E4A152FD0159655CCBEC667D2CDD7E163E` | PASS | `READY_FOR_OWNER_REVIEW` | PENDING |
| M014 | 風箏蜻蜓 | Kite Dragonfly | Field-insect winged body; cross-shaped span; kite-pattern wings; thread tail with diamond kite; daring/curious; FLYING | `art/monsters/M014_kite_dragonfly.png` | 1536×1024 | `4D0C86CB682CF5BB3B5CE245136AAB3FCE681264B25E214F0368571BB576A327` | PASS | `READY_FOR_OWNER_REVIEW` | PENDING |
| M015 | 草籽羊 | Grassseed Lamb | Meadow-grazer quadruped; soft wool oval; tiny horns; seed-pod curls; gentle/stubborn; no prop; TANK | `art/monsters/M015_grassseed_lamb.png` | 1536×1024 | `AAA618C8688AB2DF06429F5493F890CC768796C8503DB4A1A33BAE8A9272A1D0` | PASS | `READY_FOR_OWNER_REVIEW` | PENDING |
| M016 | 水窪蟹 | Puddle Crab | Water-edge crawler; low sideways shield; blue puddle claws; shell cup; one claw is a shallow bowl; cheeky/alert; ARMORED | `art/monsters/M016_puddle_crab.png` | 1536×1024 | `E5807B0EB27426105EE05F4EABCEA8DC0EC394A2393863111179CFCB823D1200` | PASS | `READY_FOR_OWNER_REVIEW` | PENDING |
| M017 | 彈簧蚱蜢 | Spring Grasshopper | Meadow-insect crawler; tall folded-knee profile; lime spring hind legs; overconfident/funny; no prop; FAST | `art/monsters/M017_spring_grasshopper.png` | 1536×1024 | `45133093DA514F9407454FF44095C3DF13BDD1E976D2A9EEAFA1C36F224B9BDC` | PASS | `READY_FOR_OWNER_REVIEW` | PENDING |
| M018 | 果凍魚 | Jellyfish | Rain-jelly blob; soft bell and ribbon base; rainbow gel stripe; tiny umbrella through the bell; dreamy/slow; MAGIC | `art/monsters/M018_jellyfish.png` | 1173×1341 | `BC1C334FE21F2F557FA86EBA5A6FE0B221F1248409A464658D5F6AB39BA7F83F` | PASS | `READY_FOR_OWNER_REVIEW` | PENDING |
| M019 | 彩傘菇獸 | Parasol Funglet | Field-fungus plant; mushroom cap over feet; painted cap spots; leaf parasol; cautious/polite; cap opens like a fan; RANGED | `art/monsters/M019_parasol_funglet.png` | 1230×1278 | `B0355111163C595EE47CB71101B6E60E288E72943F5C1CD7C2C710F864DDCAE6` | PASS | `READY_FOR_OWNER_REVIEW` | PENDING |
| M020 | 旋風田鼠 | Whirl Vole | Wind-vole quadruped; round body; large spiral tail; wind-swept whiskers; seed satchel; busy/bright; FAST | `art/monsters/M020_whirl_vole.png` | 1536×1024 | `5501608A189629265D048715003C5AED965D673D6689D45F4461D77A99476BA3` | PASS | `READY_FOR_OWNER_REVIEW` | PENDING |
| M021 | 水珠鹿 | Dewdrop Fawn | Morning-grazer quadruped; slender legs; teardrop ears; exactly two dew beads between ears; quiet/observant; no prop; BASIC | `art/monsters/M021_dewdrop_fawn.png` | 1224×1285 | `9309E1E3451477481FBDFEEC55DD7F07B30C0CE5290449743031E2D6E02B745B` | PASS | `READY_FOR_OWNER_REVIEW` | PENDING |
| M023 | 銅帽哥布林 | Coppercap Goblin | Goblin-scavenger biped; narrow body; pointed cap with copper rim; folding pick; clever/boastful; TRICKSTER | `art/monsters/M023_coppercap_goblin.png` | 1230×1278 | `59A3F4BE1B948B30267D3D5311694285CED6F228BDE1CB97435A60748CD89C67` | PASS | `READY_FOR_OWNER_REVIEW` | PENDING |

## 4. Per-asset visual QA

The following is production-side visual QA, not Owner approval. Every item passed the pre-review checks for silhouette readability, anatomy coherence, style match and identity match. The final gate remains `READY_FOR_OWNER_REVIEW`.

| M-ID | Silhouette readability | Anatomy coherence | Style match | Identity match | VISUAL_QA |
|---|---|---|---|---|---|
| M013 | PASS | PASS | PASS | PASS | READY_FOR_OWNER_REVIEW |
| M014 | PASS | PASS | PASS | PASS | READY_FOR_OWNER_REVIEW |
| M015 | PASS | PASS | PASS | PASS | READY_FOR_OWNER_REVIEW |
| M016 | PASS | PASS | PASS | PASS | READY_FOR_OWNER_REVIEW |
| M017 | PASS | PASS | PASS | PASS | READY_FOR_OWNER_REVIEW |
| M018 | PASS | PASS | PASS | PASS | READY_FOR_OWNER_REVIEW |
| M019 | PASS | PASS | PASS | PASS | READY_FOR_OWNER_REVIEW |
| M020 | PASS | PASS | PASS | PASS | READY_FOR_OWNER_REVIEW |
| M021 | PASS | PASS | PASS | PASS | READY_FOR_OWNER_REVIEW |
| M023 | PASS | PASS | PASS | PASS | READY_FOR_OWNER_REVIEW |

Review notes for Owner:

- M013: confirm the bubble throat pouch and reed flute remain the intended identity markers.
- M014: confirm the diamond tail-kite read is stronger than any generic insect-wing read.
- M016: confirm the large blue puddle claw does not overpower the low shield silhouette.
- M017: confirm the spring hind legs remain the primary read and wings remain secondary.
- M019: confirm the small bipedal mushroom presentation remains clearly a plant monster, not an NPC.
- M021: confirm the two dew beads remain distinct from the six canonical Spirit identities.
- M023: confirm the clothing detail remains monster-coded and the folding pick is the only combat prop.

## 5. Technical QA evidence

Every listed PNG was reopened after writing and passed `PNG_READABLE=YES`, `RGBA=YES`, `TRANSPARENT_BACKGROUND=YES`, `NONEMPTY_ALPHA=YES`, `NO_VISUAL_CLIPPING=YES` and `UNIQUE_SHA256=YES`. Transparent background was verified by zero alpha at all four corners; clipping was checked against the non-zero alpha bounding box.

```text
B02_GENERATED_COUNT=10
PNG_READABLE_COUNT=10
RGBA_COUNT=10
TRANSPARENT_BACKGROUND_COUNT=10
NONEMPTY_ALPHA_COUNT=10
NO_VISUAL_CLIPPING_COUNT=10
UNIQUE_SHA256_COUNT=10
B02_TECHNICAL_QA=PASS
```

The ten B01 PNG Git blobs were independently compared with the same paths at B01 R2 `0b2f4c7ec65f845918bd96a2daec21551d27ff34`; all ten matched exactly. Therefore `B01_PIXEL_MUTATIONS=0` and `B01_REGENERATION=0`.

## 6. Authority and parallel-safety firewall

```text
RUNTIME_MAPPED_NEW_ART=0
ART_CONTENT_ZONE_GAMEPLAY_AUTHORITY=NO
F034_EXACT_ZONE_ASSIGNMENT_USED=NO
E046_SCOPE_TOUCHED=NO
GAMEPLAY_AUTHORITY_CHANGED=NO
APP_PY_CHANGED=NO
RUNTIME_SOURCE_CHANGED=NO
MONSTER_STATS_CHANGED=NO
A043_SCOPE_TOUCHED=NO
B057_SCOPE_TOUCHED=NO
C050_SCOPE_TOUCHED=NO
F034_R1_SCOPE_TOUCHED=NO
LC015_SCOPE_TOUCHED=NO
```

No existing runtime Monster art, B01 art, NPC art, player art, equipment art, Boss, Lord or Spirit asset was changed. No runtime mapping, MonsterCatalog wiring, encounter wiring, Zone gameplay mapping, HP/ATK, taxonomy or gameplay number was changed.

## 7. Owner gate

This batch is not self-canonicalized. The ten images are production candidates only:

```text
OWNER_PASS_COUNT=0
OWNER_REVIEW_PENDING_COUNT=10
B02_OWNER_ACCEPTANCE=PENDING
CANONICAL_B02_ART_COUNT=0
STATUS=READY_FOR_OWNER_VISUAL_REVIEW
```

Owner review should cover identity fidelity, silhouette differentiation, consistency with the locked B01 style system, prop load, and the fact that the art does not imply F034 gameplay Zone authority. Do not begin B03 automatically from this manifest.

## 8. Release boundary

```text
MASTER_MERGE=NO
PRODUCTION_QUERY=NO
PRODUCTION_MUTATION=NO
DEPLOY=NO
SECRET_KEY_TOUCHED=NO
TASK_INTRODUCED_FAILURES=0
UNEXPECTED_FILES=0
```

## 9. Result

```text
RESULT=PASS_ART003_B02_MONSTER_PRODUCTION_ART_BATCH_READY_FOR_OWNER_REVIEW
READY_FOR_OWNER_B02_VISUAL_REVIEW=YES
```
