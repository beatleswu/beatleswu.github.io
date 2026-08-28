# Go Odyssey ART Production Master Board

- Task: `ART001_GO_ODYSSEY_ART_PRODUCTION_CURRENT_STATE_RECON_AND_MASTER_BOARD_001`
- Track: `ART_PRODUCTION`
- Mode: `READ_ANALYZE_DOCS_ONLY`
- Audit reference: `origin/master@4585bd1a12d179d0810300f047357f2e36c3e851`
- Generated after a fresh `git fetch origin` on 2026-08-28.
- A–F retain system, runtime, gameplay, IDs, Zone mapping, and reward authority. This board is visual-asset authority only.

## 1. Executive Status

### Required truth summary

```
NORMAL_MONSTER_TARGET=120
AUTHORITATIVE_120_MONSTER_ROSTER_EXISTS=NO
MONSTER_ROSTER_DEFINED_COUNT=10
MONSTER_ART_EXISTS_COUNT=10
MONSTER_ART_BRIEF_COUNT=0
MONSTER_DRAFT_COUNT=10
MONSTER_OWNER_APPROVED_COUNT=0
MONSTER_CANONICAL_ASSET_COUNT=10
MONSTER_RUNTIME_MAPPED_COUNT=10
MONSTER_VISUAL_QA_PASSED_COUNT=0
MONSTER_COMPLETELY_UNDEFINED_COUNT=110

MONSTER_ROSTER_PERCENT=8.33%
MONSTER_ART_APPROVAL_PERCENT=0.00%
MONSTER_CANONICAL_PERCENT=8.33%
MONSTER_RUNTIME_PERCENT=8.33%
MONSTER_VISUAL_QA_PERCENT=0.00%

BATTLEFIELD_BOSS_COUNT=10
BOSS_ART_OWNER_APPROVED_COUNT=0
BOSS_CANONICAL_ASSET_COUNT=10
BOSS_RUNTIME_MAPPED_COUNT=10
LORD_ART_COUNT=2

SPIRIT_TARGET=6
SPIRIT_ART_EXISTS_COUNT=6
SPIRIT_OWNER_APPROVED_COUNT=6
SPIRIT_CANONICAL_COUNT=6
SPIRIT_RUNTIME_MAPPED_COUNT=6

EQUIPMENT_TARGET=15
EQUIPMENT_ART_EXISTS_COUNT=15
EQUIPMENT_CANONICAL_COUNT=15
EQUIPMENT_RUNTIME_PROJECTION_COUNT=15

ZONE_TARGET=10
ZONE_WORLD_MAP_READY_COUNT=10
ZONE_ENVIRONMENT_READY_COUNT=10
ZONE_BATTLEFIELD_READY_COUNT=0

DUPLICATE_VISUAL_IDENTITY_COUNT=0
MULTIPLE_CANDIDATE_IDENTITY_COUNT=0
ORPHAN_ASSET_COUNT=47
PLACEHOLDER_USAGE_COUNT=1
```

Interpretation:

- The ten defined Monsters are the ten observed normal identities in the current Battlefield compatibility roster, one per Zone. They are not a locked 120-Monster product roster.
- Every M001–M120 row is intentionally `UNASSIGNED` with `UNKNOWN` state fields. No name, species, Zone, rarity, or 120-slot mapping is invented.
- “Any art” is 10/120: each observed normal runtime identity has a concrete chibi avatar. Those assets are not treated as Owner-approved merely because they exist.
- Explicit Monster Owner approval is 0/120. Canonical current normal asset paths are 10/120. Runtime mappings are 10/120. Visual-QA passes are 0/120; absent evidence remains `UNKNOWN`.
- 110 is the remaining target-slot gap after the ten observed partial-runtime identities. It does not assign identities to the placeholder rows.
- `MONSTER_DEFEAT != ZONE_CLEAR`; `BATTLEFIELD_BOSS != LORD`; `SPIRIT != MONSTER`.

### Scope and safety boundary

```
CURRENT_ART_SCOPE_AUDITED=YES
ART_ASSETS_MUTATED=0
NO_NEW_ART_GENERATED=YES
APP_PY_CHANGED=NO
RUNTIME_CHANGED=NO
STATIC_RUNTIME_CHANGED=NO
TASK_INTRODUCED_FAILURES=0
UNEXPECTED_FILES=0
MASTER_MERGE=NO
DEPLOY=NO
PRODUCTION_QUERY=NO
PRODUCTION_MUTATION=NO
FEATURE_ENABLE=NO
```

The local checkout was already dirty and 30 commits behind before this recon. The audit reference is freshly fetched `origin/master`; unrelated staged/untracked files and protected artifacts were preserved. The forbidden `C:\go-website` tree was not scanned.

### Zone distribution authority

`ZONE_MONSTER_DISTRIBUTION_AUTHORITY_EXISTS=NO`. The compatibility roster has one normal runtime identity per Zone, but that is not a 120-Monster distribution authority.

| Zone | NORMAL_MONSTER_COUNT |
|---|---:|
| Z1 新手村 | UNKNOWN |
| Z2 史萊姆平原 | UNKNOWN |
| Z3 哥布林洞穴 | UNKNOWN |
| Z4 迷霧森林 | UNKNOWN |
| Z5 獸人部落 | UNKNOWN |
| Z6 龍之谷 | UNKNOWN |
| Z7 賢者之塔 | UNKNOWN |
| Z8 魔王城前線 | UNKNOWN |
| Z9 諸神黃昏 | UNKNOWN |
| Z10 上古終焉神殿 | UNKNOWN |

## 2. 120 Monster Board

No authoritative 120-Monster roster exists. The required board is therefore M001–M120 only, with no invented identity data.

| MONSTER_ID | CANONICAL_NAME | ZONE | RUNTIME_ID | ROSTER_DEFINED | BRIEF | DRAFT | OWNER_APPROVED | CANONICAL_ASSET | ASSET_PATH | RUNTIME_MAPPED | VISUAL_QA | NOTES |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M001 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M002 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M003 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M004 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M005 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M006 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M007 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M008 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M009 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M010 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M011 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M012 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M013 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M014 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M015 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M016 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M017 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M018 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M019 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M020 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M021 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M022 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M023 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M024 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M025 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M026 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M027 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M028 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M029 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M030 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M031 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M032 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M033 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M034 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M035 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M036 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M037 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M038 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M039 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M040 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M041 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M042 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M043 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M044 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M045 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M046 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M047 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M048 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M049 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M050 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M051 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M052 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M053 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M054 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M055 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M056 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M057 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M058 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M059 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M060 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M061 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M062 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M063 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M064 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M065 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M066 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M067 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M068 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M069 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M070 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M071 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M072 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M073 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M074 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M075 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M076 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M077 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M078 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M079 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M080 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M081 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M082 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M083 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M084 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M085 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M086 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M087 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M088 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M089 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M090 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M091 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M092 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M093 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M094 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M095 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M096 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M097 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M098 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M099 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M100 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M101 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M102 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M103 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M104 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M105 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M106 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M107 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M108 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M109 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M110 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M111 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M112 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M113 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M114 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M115 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M116 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M117 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M118 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M119 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |
| M120 | UNASSIGNED | UNKNOWN | null | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | null | UNKNOWN | UNKNOWN | Placeholder only; no authoritative 120-Monster identity exists. |

### Observed current normal runtime identities — not promoted to M001–M120

| RUNTIME_ID | CANONICAL_NAME | ZONE | ASSET_PATH | ROSTER_DEFINED | BRIEF | DRAFT | OWNER_APPROVED | CANONICAL_ASSET | RUNTIME_MAPPED | VISUAL_QA |
|---|---|---|---|---|---|---|---|---|---|---|
| legacy_bf_01_normal | LV1 史萊姆 / 哥布林 | Z1 新手村 | assets/monsters/slime_chibi.png | YES | UNKNOWN | YES | UNKNOWN | YES | YES | UNKNOWN |
| legacy_bf_02_normal | LV2 哥布林 / 洞窟蝙蝠 | Z2 史萊姆平原 | assets/monsters/cave_bat_chibi.png | YES | UNKNOWN | YES | UNKNOWN | YES | YES | UNKNOWN |
| legacy_bf_03_normal | LV3 獸人小兵 | Z3 哥布林洞穴 | assets/monsters/orc_grunt_chibi.png | YES | UNKNOWN | YES | UNKNOWN | YES | YES | UNKNOWN |
| legacy_bf_04_normal | LV4 森林精靈 | Z4 迷霧森林 | assets/monsters/forest_spirit_chibi.png | YES | UNKNOWN | YES | UNKNOWN | YES | YES | UNKNOWN |
| legacy_bf_05_normal | LV5 部落獸人 | Z5 獸人部落 | assets/monsters/tribal_orc_chibi.png | YES | UNKNOWN | YES | UNKNOWN | YES | YES | UNKNOWN |
| legacy_bf_06_normal | LV6 飛龍 / 低階神靈 | Z6 龍之谷 | assets/monsters/wyvern_chibi.png | YES | UNKNOWN | YES | UNKNOWN | YES | YES | UNKNOWN |
| legacy_bf_07_normal | LV7 賢者 / 魔法師 / 亡靈 | Z7 賢者之塔 | assets/monsters/lich_mage_chibi.png | YES | UNKNOWN | YES | UNKNOWN | YES | YES | UNKNOWN |
| legacy_bf_08_normal | LV8 騎士 / 混沌領主 | Z8 魔王城前線 | assets/monsters/armored_knight_chibi.png | YES | UNKNOWN | YES | UNKNOWN | YES | YES | UNKNOWN |
| legacy_bf_09_normal | LV9 諸神 | Z9 諸神黃昏 | assets/monsters/storm_deity_chibi.png | YES | UNKNOWN | YES | UNKNOWN | YES | YES | UNKNOWN |
| legacy_bf_10_normal | LV10 上古終焉神殿 | Z10 上古終焉神殿 | assets/monsters/ancient_idol_chibi.png | YES | UNKNOWN | YES | UNKNOWN | YES | YES | UNKNOWN |

Concrete proof is the `app.py` `_BATTLEFIELD_ROSTER` / `_BATTLEFIELD_AVATARS` mapping, backed by `monster_identity.py`, `monster_profiles.py`, and the 20-identity test contract. The current normal names are compatibility-stage names, not a 120 identity set. Alias reuse is recorded but not counted as another roster.

## 3. Battlefield Boss Board

There are 10 separate Battlefield Boss identities, one per Zone. They are not the 10 Lords in `ADVENTURE_BOSS_META`, and their art is not inferred from Mapping A reward items.

| BOSS_ID | CANONICAL_NAME | ZONE | ASSET_PATH | VISUAL_CANDIDATE | OWNER_APPROVED | CANONICAL_ASSET | RUNTIME_MAPPED | VISUAL_QA |
|---|---|---|---|---|---|---|---|---|
| legacy_bf_01_boss | LV1 提子訓練守衛 | Z1 新手村 | assets/monsters/goblin_guard_chibi.png | YES | UNKNOWN | YES | YES | UNKNOWN |
| legacy_bf_02_boss | LV2 雙叫吃突襲隊 | Z2 史萊姆平原 | assets/monsters/goblin_raider_chibi.png | YES | UNKNOWN | YES | YES | UNKNOWN |
| legacy_bf_03_boss | LV3 做眼厚壁兵 | Z3 哥布林洞穴 | assets/monsters/orc_shield_chibi.png | YES | UNKNOWN | YES | YES | UNKNOWN |
| legacy_bf_04_boss | LV4 霧林手筋師 | Z4 迷霧森林 | assets/monsters/mist_dryad_chibi.png | YES | UNKNOWN | YES | YES | UNKNOWN |
| legacy_bf_05_boss | LV5 銀牌懸賞首領 | Z5 獸人部落 | assets/monsters/bounty_warlord_chibi.png | YES | UNKNOWN | YES | YES | UNKNOWN |
| legacy_bf_06_boss | LV6 龍谷計算者 | Z6 龍之谷 | assets/monsters/dragon_oracle_chibi.png | YES | UNKNOWN | YES | YES | UNKNOWN |
| legacy_bf_07_boss | LV7 高塔術師 | Z7 賢者之塔 | assets/monsters/archmage_lich_chibi.png | YES | UNKNOWN | YES | YES | UNKNOWN |
| legacy_bf_08_boss | LV8 皇家騎士長 | Z8 魔王城前線 | assets/monsters/royal_knight_chibi.png | YES | UNKNOWN | YES | YES | UNKNOWN |
| legacy_bf_09_boss | LV9 命運試煉官 | Z9 諸神黃昏 | assets/monsters/fate_deity_chibi.png | YES | UNKNOWN | YES | YES | UNKNOWN |
| legacy_bf_10_boss | LV10 終焉神 | Z10 上古終焉神殿 | assets/monsters/omega_idol_chibi.png | YES | UNKNOWN | YES | YES | UNKNOWN |

Owner-approved Boss-art count is 0: cited monster provenance proves current runtime/canonical paths, not an explicit Boss-art acceptance record.

## 4. Lord / Major Character Board

### Lords

`ADVENTURE_BOSS_META` defines 10 Lords. Dedicated, Owner-provided and runtime-bound Lord Trial art is proven for Zones 1–2 only.

| LORD_ID | CANONICAL_NAME | ZONE | ART_IDENTITY_KNOWN | VISUAL_CANDIDATE | OWNER_APPROVED | CANONICAL | RUNTIME_MAPPED | ASSET_PATHS |
|---|---|---|---|---|---|---|---|---|
| village_examiner | 村莊考核官 / Village Examiner | Z1 新手村 | YES | YES | YES | YES | YES | assets/e10/art/zone1/lord_trial/zone1_lord_ritual_key_art.webp<br>assets/e10/art/zone1/lord_trial/zone1_lord_challenge_backplate.webp<br>assets/e10/art/zone1/lord_trial/zone1_lord_failure_backplate.webp |
| swarm_lord | 史萊姆群領主 / Swarm Lord | Z2 史萊姆平原 | YES | YES | YES | YES | YES | assets/e10/art/zone2/lord_trial/zone2_lord_ritual_key_art.webp<br>assets/e10/art/zone2/lord_trial/zone2_lord_portrait.webp<br>assets/e10/art/zone2/lord_trial/zone2_success_lord_portrait.webp |
| goblin_centurion | 哥布林百夫長 / Goblin Centurion | Z3 哥布林洞穴 | YES | NO | UNKNOWN | NO | NO | null |
| misty_phantom_rabbit_king | 迷霧幻影兔王 / Misty Phantom Rabbit King | Z4 迷霧森林 | YES | NO | UNKNOWN | NO | NO | null |
| iron_orc_chieftain | 鋼鐵獸人酋長 / Iron Orc Chieftain | Z5 獸人部落 | YES | NO | UNKNOWN | NO | NO | null |
| grand_temple_knight | 聖殿大騎士長 / Grand Temple Knight | Z6 龍之谷 | YES | NO | UNKNOWN | NO | NO | null |
| archmage_phantom | 大魔法師幻影 / Archmage Phantom | Z7 賢者之塔 | YES | NO | UNKNOWN | NO | NO | null |
| chaos_lord | 混沌領主 / Chaos Lord | Z8 魔王城前線 | YES | NO | UNKNOWN | NO | NO | null |
| fallen_war_god_statue | 墮落戰神古像 / Fallen War-God Statue | Z9 諸神黃昏 | YES | NO | UNKNOWN | NO | NO | null |
| source_of_black_white_order | 黑白秩序之源 / Source of Black-White Order | Z10 上古終焉神殿 | YES | NO | UNKNOWN | NO | NO | null |

`LORD_ART_COUNT=2` counts dedicated Lord identity packages for Zones 1–2, not the number of files. Zone 1’s Village Elder reference is a World NPC asset, not a Lord asset.

### World NPCs — separate major-character category

| WORLD_NPC_ID | CANONICAL_NAME | ZONE | RUNTIME_ASSET | OWNER_APPROVED | CANONICAL_ASSET | RUNTIME_MAPPED | VISUAL_QA |
|---|---|---|---|---|---|---|---|
| world.village_elder | 村長 / Village Elder | Z1 新手村 | assets/world/characters/wave2_p1/world_village_elder_p1.webp | YES | YES | YES | EMULATED |
| world.messenger | 信使 / Messenger | Z1 新手村 | assets/world/characters/wave2_p1/world_messenger_p1.webp | YES | YES | YES | EMULATED |
| world.smith_elder | 鐵匠長老 / Smith Elder | Z5 獸人部落 | assets/world/characters/wave2_p2/world_smith_elder_p2.webp | YES | YES | YES | EMULATED |
| world.archmage | 大法師 / Archmage | Z7 賢者之塔 | assets/world/characters/wave2_p2/world_archmage_p2.webp | YES | YES | YES | EMULATED |
| world.serel | Serel / 瑟瑞爾 | Z8 魔王城前線 | assets/world/characters/wave2_p2/world_serel_p2.webp | YES | YES | YES | EMULATED |
| world.herder | 牧人 / Herder | Z2 史萊姆平原 | assets/world/characters/wave2_p3/world_herder_p3.webp | YES | YES | YES | EMULATED |
| world.eastern_guardian | 東方守護者 / Eastern Guardian | Z10 上古終焉神殿 | assets/world/characters/wave2_p3/world_eastern_guardian_p3.webp | YES | YES | YES | EMULATED |

## 5. Spirit Board

Exactly six canonical Spirits are tracked. No seventh Spirit exists.

| SPIRIT_ID | ART_EXISTS | OWNER_APPROVED | CANONICAL_ASSET | RUNTIME_MAPPED | COLLECTION_VISUAL_READY | UNLOCK_VISUAL_READY | STAGE ASSETS |
|---|---|---|---|---|---|---|---|
| ink_drop_kelpie | YES | YES | YES | YES | YES | YES | assets/pets/pet_ink_drop_kelpie_lv1.webp<br>assets/pets/horse_anim_lv2/01_idle.webp<br>assets/pets/horse_anim_lv3/01_idle.webp |
| whispering_void_kit | YES | YES | YES | YES | YES | YES | assets/pets/pet_whispering_void_kit_lv1.webp<br>assets/pets/cat_anim_lv2/01_idle.webp<br>assets/pets/cat_anim_lv3/01_idle.webp |
| star_shell_hatchling | YES | YES | YES | YES | YES | YES | assets/pets/pet_star_shell_hatchling_lv1.webp<br>assets/pets/dragon_anim_lv2/01_idle.webp<br>assets/pets/dragon_anim_lv3/01_idle.webp |
| starpath_antlerling | YES | YES | YES | YES | YES | YES | assets/pets/pet_starpath_antlerling_stage1.webp<br>assets/pets/pet_starpath_antlerling_stage2.webp<br>assets/pets/pet_starpath_antlerling_stage3.webp |
| fatty | YES | YES | YES | YES | YES | YES | assets/pets/pet_fatty_stage1.webp<br>assets/pets/pet_fatty_stage2.webp<br>assets/pets/pet_fatty_stage3.webp |
| obsidian_bastion | YES | YES | YES | YES | YES | YES | assets/pets/pet_obsidian_bastion_stage1.webp<br>assets/pets/pet_obsidian_bastion_stage2.webp<br>assets/pets/pet_obsidian_bastion_stage3.webp |

The A021A package is visual/runtime presentation evidence. Its boundary keeps ownership, unlock, active-Spirit, evolution, combat, reward, and catalog authority outside ART001.

## 6. Equipment Board

This is the exact 15-ID functional equipment set. Functional art is presentation-only; effects and equip rules are untouched.

| EQUIPMENT_ID | CATEGORY | ART_EXISTS | CANONICAL | FUNCTIONAL_ICON_PATH | HERO_PROJECTION_READY | BACKPACK_PROJECTION_READY | SHOP_PROJECTION_READY | FULL_BODY_OVERLAY_PATH |
|---|---|---|---|---|---|---|---|---|
| wooden_sword | WEAPON | YES | YES | assets/hero/equipment/functional/wooden_sword.svg | YES | YES | YES | assets/hero/equipment/wearables/overlays/wooden_sword.png |
| iron_sword | WEAPON | YES | YES | assets/hero/equipment/functional/iron_sword.svg | YES | YES | YES | assets/hero/equipment/wearables/overlays/iron_sword.png |
| fox_fang | WEAPON | YES | YES | assets/hero/equipment/functional/fox_fang.svg | YES | YES | YES | assets/hero/equipment/wearables/overlays/fox_fang.png |
| dragon_claw | WEAPON | YES | YES | assets/hero/equipment/functional/dragon_claw.svg | YES | YES | YES | assets/hero/equipment/wearables/overlays/dragon_claw.png |
| celestial_blade | WEAPON | YES | YES | assets/hero/equipment/functional/celestial_blade.svg | YES | YES | YES | assets/hero/equipment/wearables/overlays/celestial_blade.png |
| cloth_robe | ARMOR | YES | YES | assets/hero/equipment/functional/cloth_robe.svg | YES | YES | YES | assets/hero/equipment/wearables/overlays/cloth_robe.png |
| leather_armor | ARMOR | YES | YES | assets/hero/equipment/functional/leather_armor.svg | YES | YES | YES | assets/hero/equipment/wearables/overlays/leather_armor.png |
| fox_pelt | ARMOR | YES | YES | assets/hero/equipment/functional/fox_pelt.svg | YES | YES | YES | assets/hero/equipment/wearables/overlays/fox_pelt.png |
| dragon_scale | ARMOR | YES | YES | assets/hero/equipment/functional/dragon_scale.svg | YES | YES | YES | assets/hero/equipment/wearables/overlays/dragon_scale.png |
| void_mantle | ARMOR | YES | YES | assets/hero/equipment/functional/void_mantle.svg | YES | YES | YES | assets/hero/equipment/wearables/overlays/void_mantle.png |
| lucky_stone | ACCESSORY | YES | YES | assets/hero/equipment/functional/lucky_stone.svg | YES | YES | YES | assets/hero/equipment/wearables/overlays/lucky_stone.png |
| xp_amulet | ACCESSORY | YES | YES | assets/hero/equipment/functional/xp_amulet.svg | YES | YES | YES | assets/hero/equipment/wearables/overlays/xp_amulet.png |
| fox_mask | ACCESSORY | YES | YES | assets/hero/equipment/functional/fox_mask.svg | YES | YES | YES | assets/hero/equipment/wearables/overlays/fox_mask.png |
| dragon_eye | ACCESSORY | YES | YES | assets/hero/equipment/functional/dragon_eye.svg | YES | YES | YES | assets/hero/equipment/wearables/overlays/dragon_eye.png |
| go_stone_black | ACCESSORY | YES | YES | assets/hero/equipment/functional/go_stone_black.svg | NO_ICON_ONLY | YES | YES | null |

All 15 functional SVG icons are present in the canonical image evidence. The 14 full-body overlays are 1056×1408 RGBA PNGs. `go_stone_black` is intentionally icon-only; its stale wearable-registry overlay claim is a reconciliation finding, not an asset to generate.

## 7. Zone / Environment Board

World-map readiness means the runtime world-map base plus the exact Zone landmark. Environment readiness is the landmark tier. Battlefield readiness counts only a dedicated Zone-specific Battlefield scene; current encounter avatars are listed separately.

| ZONE_ID | ZONE_NAME | WORLD_MAP_VISUAL | ZONE_ENVIRONMENT_VISUAL | BATTLEFIELD_VISUAL / AVATAR | OWNER_APPROVED | CANONICAL | RUNTIME_MAPPED | VISUAL_GAPS |
|---|---|---|---|---|---|---|---|---|
| Z1 | 新手村 | YES (assets/maps/e10-vs1f-landmarks/zone-01-beginner-village.webp) | YES_LANDMARK_TIER | NO_DEDICATED_SCENE / YES_RUNTIME_AVATAR_ONLY | YES | YES | YES | No dedicated Battlefield scene; Scene 05 master is documented source-only/no runtime derivative. |
| Z2 | 史萊姆平原 | YES (assets/maps/e10-vs1f-landmarks/zone-02-slime-plains.webp) | YES_LANDMARK_TIER | NO_DEDICATED_SCENE / YES_RUNTIME_AVATAR_ONLY | YES | YES | YES | No dedicated Battlefield scene; storyboard art is not persistent Zone environment art. |
| Z3 | 哥布林洞穴 | YES (assets/maps/e10-vs1f-landmarks/zone-03-goblin-cave.webp) | YES_LANDMARK_TIER | NO_DEDICATED_SCENE / YES_RUNTIME_AVATAR_ONLY | YES | YES | YES | No dedicated Battlefield scene; storyboard art is not persistent Zone environment art. |
| Z4 | 迷霧森林 | YES (assets/maps/e10-vs1f-landmarks/zone-04-twilight-forest.webp) | YES_LANDMARK_TIER | NO_DEDICATED_SCENE / YES_RUNTIME_AVATAR_ONLY | YES | YES | YES | No dedicated Battlefield scene; storyboard art is not persistent Zone environment art. |
| Z5 | 獸人部落 | YES (assets/maps/e10-vs1f-landmarks/zone-05-sky-tower.webp) | YES_LANDMARK_TIER | NO_DEDICATED_SCENE / YES_RUNTIME_AVATAR_ONLY | YES | YES | YES | No dedicated Battlefield scene; landmark filename uses legacy Sky Tower label for runtime Orc Tribe. |
| Z6 | 龍之谷 | YES (assets/maps/e10-vs1f-landmarks/zone-06-royal-castle.webp) | YES_LANDMARK_TIER | NO_DEDICATED_SCENE / YES_RUNTIME_AVATAR_ONLY | YES | YES | YES | No dedicated Battlefield scene; storyboard art is not persistent Zone environment art. |
| Z7 | 賢者之塔 | YES (assets/maps/e10-vs1f-landmarks/zone-07-star-sea-passage.webp) | YES_LANDMARK_TIER | NO_DEDICATED_SCENE / YES_RUNTIME_AVATAR_ONLY | YES | YES | YES | No dedicated Battlefield scene; storyboard art is not persistent Zone environment art. |
| Z8 | 魔王城前線 | YES (assets/maps/e10-vs1f-landmarks/zone-08-abyssal-forge.webp) | YES_LANDMARK_TIER | NO_DEDICATED_SCENE / YES_RUNTIME_AVATAR_ONLY | YES | YES | YES | No dedicated Battlefield scene; storyboard art is not persistent Zone environment art. |
| Z9 | 諸神黃昏 | YES (assets/maps/e10-vs1f-landmarks/zone-09-eternal-night-shrine.webp) | YES_LANDMARK_TIER | NO_DEDICATED_SCENE / YES_RUNTIME_AVATAR_ONLY | YES | YES | YES | No dedicated Battlefield scene; storyboard art is not persistent Zone environment art. |
| Z10 | 上古終焉神殿 | YES (assets/maps/e10-vs1f-landmarks/zone-10-ancient-doom-temple.webp) | YES_LANDMARK_TIER | NO_DEDICATED_SCENE / YES_RUNTIME_AVATAR_ONLY | YES | YES | YES | No dedicated Battlefield scene; storyboard art is not persistent Zone environment art. |

`js/e9/world_stage.js` maps the ten landmark WebPs and active world-map base. Storyboards/cinematic art are not silently promoted to persistent Zone environment art.

## 8. UI / VFX Board

- UI RPG: 42 raster assets under `assets/e10/ui` cover navigation icons, frames, medallions, panels, plaques, and state indicators.
- VFX/animation: Spirit animation frame families exist under `assets/pets`; Lord Trial ritual particles are presentation VFX in `index.html`. No dedicated RPG combat-VFX identity registry was found.
- Reward/loot: `rpg_item_registry.py` binds eight dedicated live item SVGs under `assets/items`; shop art is separate. Mapping A reward items are not Boss art.
- Hero/player: ten current active character concepts/assets remain in the visual bible; six Wave-2 body candidates are review material, not a new canonical selectable roster.

## 9. Orphan / Legacy / Placeholder Assets

`ORPHAN_ASSET_COUNT=47` within `assets/monsters`, using active runtime files only. Documentation, tests, review manifests, and historical references do not make an asset runtime-integrated.

| Classification | Count | Examples / meaning |
|---|---:|---|
| ORPHANED / runtime-unreferenced | 47 | 22 `generated_raw`, 6 `generated_sheets`, 18 SVG review/legacy variants, 1 redraw verification output |
| PLACEHOLDER usage | 1 | `assets/monsters/unknown_chibi.png` explicit unknown fallback |
| TEST_ONLY | included above | Raw sources, review sheets, redraw verification |
| LEGACY | separate records | Legacy blacksmith art and old display labels |
| CANDIDATE | not counted as orphan | A023 SVG prototypes and Wave-2 P1 player review material |
| OWNER_APPROVED_NOT_CANONICAL | not counted as orphan | A020-R2 source forms and Zone 1 source-only masters |
| DUPLICATE identity | 0 | Format/review variants are not competing identities |

`defeated_chibi.png` is a defeated state image, not an identity placeholder. The 20 current normal/Boss identity chibi paths are unique at the identity level. Alias reuse is explicit.

### File-quality findings

- 22 Monster chibi PNGs decode, all RGBA with alpha; dimensions vary from 331×360 through 512×508. No broken file was found.
- 14 equipment overlays decode as 1056×1408 RGBA PNG with alpha.
- Nine new Spirit forms are 512×512 RGBA lossless WebP; existing shared animation forms include 1920×1920 RGBA WebP.
- Ten Zone landmarks are 320×320 RGBA WebP.
- The world-map v2 base is 2048×1152 RGB with no alpha expected.
- Representative `origin/master` byte samples: `slime_chibi.png` 376×389 RGBA PNG, 241262 bytes; `wooden_sword.png` 1056×1408 RGBA PNG, 72321 bytes; `pet_starpath_antlerling_stage1.webp` 512×512 RGBA WebP, 69146 bytes; Zone 1 landmark 320×320 RGBA WebP, 118210 bytes; world-map v2 2048×1152 RGB WebP, 754206 bytes. The full sampled record set is in the JSON board.
- No asset was rewritten, optimized, renamed, moved, deleted, or staged.

## 10. Production Backlog

| Priority | Work | Evidence-based reason | Status |
|---|---|---|---|
| P0 | `ART002_120_MONSTER_ROSTER_AND_ZONE_DISTRIBUTION_LOCK` | No authoritative 120 roster or distribution | RECOMMENDED_NOT_STARTED |
| P0 | Per-identity Monster brief and Owner acceptance matrix | No per-identity Monster briefs or explicit approvals | BLOCKED_ON_ART002 |
| P1 | Monster canonical/visual-QA closure | Runtime art is not approval or QA evidence | NOT_STARTED |
| P1 | Dedicated Battlefield scene art wave | 0/10 dedicated Battlefield scenes | NOT_STARTED |
| P1 | Lord art wave for Zones 3–10 | Dedicated Lord packages found only for Zones 1–2 | NOT_STARTED |
| P1 | Reconcile stale `go_stone_black` wearable registry record | Conflicting registry vs icon-only contract | RECONCILIATION_ONLY |
| P2 | Governed orphan/legacy disposition | 47 assets preserved; no delete/move/rename authority | NOT_STARTED |

## 11. Recommended Production Sequence

1. Recommend `ART002_120_MONSTER_ROSTER_AND_ZONE_DISTRIBUTION_LOCK`; do not start it in ART001.
2. Derive per-identity briefs and Owner gates from the locked roster.
3. Choose the first Monster batch only after identity/Zone/brief evidence exists; batch size is `UNDETERMINED` at ART001.
4. Canonicalize/runtime-map accepted art, then run per-surface visual QA separately.

## 12. Evidence / Provenance Notes

- `app.py`: Battlefield roster/avatar map, Lord meta, Spirit catalog, and functional equipment registries.
- `monster_identity.py`, `monster_profiles.py`, `tests/test_monster_identity.py`: current canonical Battlefield identity count is 20, not 120.
- A021A Spirit manifest/package and A020-R2 review: six Spirits, 18 stages, Owner-approved clean-form source, presentation boundary.
- World NPC registry: seven frozen World NPCs and exact runtime paths.
- Zone 1/2 Lord Trial package manifests, Zone 2 canonical art manifest, and `index.html`: Owner-provided/runtime-bound Lord art for Zones 1–2.
- `js/e9/world_stage.js` and canonical image manifest: ten concrete landmark references.
- `rpg_item_registry.py`, equipment wiring test, and P3 manifest: exact 15 equipment boundary, 14 overlays, icon-only `go_stone_black`.
- Origin asset tree/raster decode audit: scope counts, dimensions, alpha, sizes, and broken-file checks.

Runtime surface evidence is repository/package evidence only: Desktop, iPad landscape, iPad portrait, and Mobile are `EMULATED` where relevant; no physical-device or full ART001 browser visual QA was performed.

## Final Report

```
TASK=ART001_GO_ODYSSEY_ART_PRODUCTION_CURRENT_STATE_RECON_AND_MASTER_BOARD_001
CURRENT_ORIGIN_MASTER=4585bd1a12d179d0810300f047357f2e36c3e851
BASE_SHA=4585bd1a12d179d0810300f047357f2e36c3e851
BRANCH=master
LOCAL_HEAD=6decd4ccfd65e69117023db0cf2b22fc830768f1
TRACKING_HEAD=4585bd1a12d179d0810300f047357f2e36c3e851
REMOTE_HEAD=4585bd1a12d179d0810300f047357f2e36c3e851
REMOTE_HEAD_EXACT=YES

CURRENT_ART_SCOPE_AUDITED=YES
AUTHORITATIVE_120_MONSTER_ROSTER_EXISTS=NO
ZONE_MONSTER_DISTRIBUTION_AUTHORITY_EXISTS=NO

NORMAL_MONSTER_TARGET=120
MONSTER_ROSTER_DEFINED_COUNT=10
MONSTER_ART_BRIEF_COUNT=0
MONSTER_DRAFT_COUNT=10
MONSTER_OWNER_APPROVED_COUNT=0
MONSTER_CANONICAL_ASSET_COUNT=10
MONSTER_RUNTIME_MAPPED_COUNT=10
MONSTER_VISUAL_QA_PASSED_COUNT=0
MONSTER_COMPLETELY_UNDEFINED_COUNT=110

MONSTER_ROSTER_PERCENT=8.33%
MONSTER_ART_APPROVAL_PERCENT=0.00%
MONSTER_CANONICAL_PERCENT=8.33%
MONSTER_RUNTIME_PERCENT=8.33%
MONSTER_VISUAL_QA_PERCENT=0.00%

BATTLEFIELD_BOSS_COUNT=10
BOSS_ART_OWNER_APPROVED_COUNT=0
BOSS_CANONICAL_ASSET_COUNT=10
BOSS_RUNTIME_MAPPED_COUNT=10
LORD_ART_COUNT=2

SPIRIT_TARGET=6
SPIRIT_ART_EXISTS_COUNT=6
SPIRIT_OWNER_APPROVED_COUNT=6
SPIRIT_CANONICAL_COUNT=6
SPIRIT_RUNTIME_MAPPED_COUNT=6

EQUIPMENT_TARGET=15
EQUIPMENT_ART_EXISTS_COUNT=15
EQUIPMENT_CANONICAL_COUNT=15
EQUIPMENT_RUNTIME_PROJECTION_COUNT=15

ZONE_TARGET=10
ZONE_WORLD_MAP_READY_COUNT=10
ZONE_ENVIRONMENT_READY_COUNT=10
ZONE_BATTLEFIELD_READY_COUNT=0

DUPLICATE_VISUAL_IDENTITY_COUNT=0
MULTIPLE_CANDIDATE_IDENTITY_COUNT=0
ORPHAN_ASSET_COUNT=47
PLACEHOLDER_USAGE_COUNT=1

ART_MASTER_BOARD_PATH=docs/planning/art_production_master_board.md
ART_MASTER_BOARD_JSON_PATH=docs/planning/art_production_master_board.json
RECON_DETERMINISTIC=PASS

ART_ASSETS_MUTATED=0
NO_NEW_ART_GENERATED=YES
APP_PY_CHANGED=NO
RUNTIME_CHANGED=NO
STATIC_RUNTIME_CHANGED=NO
TASK_INTRODUCED_FAILURES=0
UNEXPECTED_FILES=0

MASTER_MERGE=NO
DEPLOY=NO
PRODUCTION_QUERY=NO
PRODUCTION_MUTATION=NO
FEATURE_ENABLE=NO

RESULT=PASS — ART001 recon and both master-board artifacts are ready for coordinator review.
READY_FOR_COORDINATOR_ART001_REVIEW=YES
```
