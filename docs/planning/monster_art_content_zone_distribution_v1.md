# Monster Art/Content Zone Distribution V1

TASK=F033_OWNER_APPROVED_MONSTER_ART_CONTENT_ZONE_DISTRIBUTION_LOCK_001  
CONTRACT=MONSTER_ART_CONTENT_ZONE_COUNTS_V1  
LANE=F  
STATUS=OWNER_APPROVED_CANONICAL_ART_CONTENT_PLANNING  
APP_PY_WRITER=NO

## Owner decision

F032 Model C was explicitly approved by the Owner as the canonical
Art/content planning distribution for the 120 normal-Monster art/content
slots. This approval does not authorize gameplay, combat, encounter, reward,
rarity, or runtime-catalog changes.

```text
OWNER_APPROVED_ART_CONTENT_DISTRIBUTION=YES
APPROVED_MODEL=MODEL_C
OWNER_APPROVED_SCOPE=ART_CONTENT_PLANNING_ONLY
```

## Canonical planning counts

| Zone | Count |
|---|---:|
| Z1 | 14 |
| Z2 | 14 |
| Z3 | 13 |
| Z4 | 12 |
| Z5 | 12 |
| Z6 | 12 |
| Z7 | 12 |
| Z8 | 11 |
| Z9 | 10 |
| Z10 | 10 |
| **Total** | **120** |

```text
MONSTER_ART_CONTENT_ZONE_COUNTS_V1=14,14,13,12,12,12,12,11,10,10
ZONE_COUNT_SUM=120
ZONE_COUNT_NONZERO_ALL=YES
```

No alternative distribution is canonical for Art/content planning after this
approval. The counts are an allocation target for content production; they do
not select encounters or alter the runtime Monster roster.

## Authority boundary

```text
ART_CONTENT_COUNT_USED_FOR_COMBAT=NO
GAMEPLAY_AUTHORITY_CHANGED=NO
GAMEPLAY_AUTHORITY=false
COMBAT_AUTHORITY=false
MONSTER_QUANTITY != MONSTER_DIFFICULTY
```

The count contract must not determine HP, ATK, TTK, question difficulty, Boss
power, Lord power, reward amount, rarity, or encounter frequency. E045 remains
the owner of the MonsterCatalog/profile architecture. F009 remains off for
this planning contract; Common/Rare/Elite assumptions are not used to assign
Zone counts.

```text
F009_ENABLED=NO
RARITY_USED_TO_ASSIGN_ZONE_COUNTS=NO
```

Normal Monster, Battlefield Boss, and Lord remain separate categories. ART002
explicitly records that Boss and Lord are not counted in the 120 normal-Monster
candidate, so this contract carries the same boundary:

```text
BOSS_INCLUDED_IN_120_COUNT=NO
LORD_INCLUDED_IN_120_COUNT=NO
ROSTER_CLASSIFICATION_RECONCILIATION_REQUIRED=NO
```

## ART002 reconciliation

The ART002 candidate remains preserved at remote commit
`3e7034ef71c27ca00acf456d03f95301f30b8c64`. Its prior planning distribution
was:

```text
OLD_ART002_DISTRIBUTION=10,11,12,12,12,13,13,14,14,9
ART002_OLD_DISTRIBUTION_STATUS=SUPERSEDED_FOR_ART_CONTENT_PLANNING
```

The old candidate is historical planning evidence, not a second canonical
distribution. ART002's `M001–M120` identity baseline, existing artwork,
existing runtime references, Zone themes, and historical documentation are
not deleted or rewritten by F033.

```text
ART002_ROSTER_IDS_PRESERVED=YES
ART002_ART_ASSETS_PRESERVED=YES
ART002_EXISTING_RUNTIME_MAPPINGS_PRESERVED=YES
ART002_CHANGED=NO
```

The exact count delta is:

| Zone | Old | New | Delta |
|---|---:|---:|---:|
| Z1 | 10 | 14 | +4 |
| Z2 | 11 | 14 | +3 |
| Z3 | 12 | 13 | +1 |
| Z4 | 12 | 12 | 0 |
| Z5 | 12 | 12 | 0 |
| Z6 | 13 | 12 | -1 |
| Z7 | 13 | 12 | -1 |
| Z8 | 14 | 11 | -3 |
| Z9 | 14 | 10 | -4 |
| Z10 | 9 | 10 | +1 |
| **Net** | **120** | **120** | **0** |

```text
ZONE_COUNT_DELTA=+4,+3,+1,0,0,-1,-1,-3,-4,+1
NET_DELTA=0
```

## M-ID identity and assignment boundary

The ART002 candidate contains exactly 120 unique IDs, `M001–M120`, with no
missing or duplicate ID. Counts approved by the Owner do not silently approve
exact ID-to-Zone reassignment. ART002's candidate Zone fields are retained as
historical candidate metadata, not promoted here to an Owner-locked exact
assignment.

```text
M_ID_COUNT=120
M_ID_UNIQUE=120
M_ID_DUPLICATES=0
M_ID_MISSING=0
OWNER_APPROVED_EXACT_M_ID_REASSIGNMENT=NO
EXACT_M_ID_ZONE_ASSIGNMENT_STATUS=PENDING_CONTENT_RECONCILIATION
M_ID_ZONE_MOVES_PERFORMED=0
```

No IDs are renumbered, deleted, merged, split, or extended beyond M120.

## ART003 consumption contract

ART003 may use this contract to plan production batches and count targets.
Until a separate content reconciliation assigns exact IDs to exact Zones,
ART003 must not infer gameplay Zone membership from count, batch placement, or
ID numbering.

```text
ART003_MAY_USE_COUNT_TARGETS=YES
ART003_MAY_INFER_GAMEPLAY_ZONE_FROM_COUNT=NO
ART003_MAY_RENUMBER_IDS=NO
ART003_B01_ART_INVALIDATED_BY_DISTRIBUTION=NO
ART003_ASSET_SCOPE_TOUCHED=NO
```

The existing ART003 B01 content (`M002–M010`, `M012`) remains valid artwork
work and is not redrawn or rejected solely because the planning counts changed.
Future allocation should prefer visual ecology, Zone identity, content
variety, and narrative fit; it must not use numeric combat difficulty as a
substitute for content assignment.

## Machine-readable contract

The companion JSON file is the deterministic representation of this contract:

`docs/planning/monster_art_content_zone_distribution_v1.json`

It records the Owner-approved status, exact counts, total, authority flags,
superseded ART002 distribution, exact-ID status, and ART003 restrictions.

## Required next decisions

1. A future content-reconciliation task may decide exact `M001–M120` Zone
   placement while preserving the counts above.
2. E045 must decide whether runtime combat profiles are unique or shared
   archetypes; F033 does not preempt that decision.
3. ART003 may continue production under the count target, but no artwork
   becomes gameplay/runtime authority until separately reviewed and mapped.

## Validation and scope

```text
CURRENT_ORIGIN_MASTER=6829c4c528adf4800326e90534585a32e390ebec
BASE_SHA=6829c4c528adf4800326e90534585a32e390ebec
F032_HEAD=57aedb47be360798648753b214e6dcb0314a3980
ART002_REFERENCE_HEAD=3e7034ef71c27ca00acf456d03f95301f30b8c64
FRESH_MASTER_RECONCILIATION=PASS

CANONICAL_PLANNING_ARTIFACT_CREATED=YES
DISTRIBUTION_CONTRACT_DETERMINISTIC=PASS
DISTRIBUTION_CONTRACT_TESTS=PASS
ROSTER_IDENTITY_TESTS=PASS
AUTHORITY_BOUNDARY_TESTS=PASS
TASK_INTRODUCED_FAILURES=0

APP_PY_CHANGED=NO
RUNTIME_SOURCE_CHANGED=NO
RUNTIME_MAPPING_CHANGED=NO
MONSTER_STATS_CHANGED=NO
ART_ASSETS_CHANGED=NO
SCHEMA_CHANGED=NO
MIGRATION_CHANGED=NO

B056_SCOPE_TOUCHED=NO
C049_SCOPE_TOUCHED=NO
A040_SCOPE_TOUCHED=NO
D041_SCOPE_TOUCHED=NO
E045_SCOPE_TOUCHED=NO
ART003_ASSET_SCOPE_TOUCHED=NO
SECRET_KEY_TOUCHED=NO

MASTER_MERGE=NO
PRODUCTION_QUERY=NO
PRODUCTION_MUTATION=NO
DEPLOY=NO
```

## Final report

```text
TASK=F033_OWNER_APPROVED_MONSTER_ART_CONTENT_ZONE_DISTRIBUTION_LOCK_001

CURRENT_ORIGIN_MASTER=6829c4c528adf4800326e90534585a32e390ebec
BASE_SHA=6829c4c528adf4800326e90534585a32e390ebec
F032_HEAD=57aedb47be360798648753b214e6dcb0314a3980
ART002_REFERENCE_HEAD=3e7034ef71c27ca00acf456d03f95301f30b8c64
FRESH_MASTER_RECONCILIATION=PASS

BRANCH=codex/f033-owner-approved-monster-art-content-zone-distribution-lock
LOCAL_HEAD=POST_COMMIT_VERIFIED_IN_HANDOFF
REMOTE_HEAD=POST_PUSH_VERIFIED_IN_HANDOFF
REMOTE_HEAD_EXACT=YES

OWNER_APPROVED_ART_CONTENT_DISTRIBUTION=YES
ZONE_COUNTS=14,14,13,12,12,12,12,11,10,10
ZONE_COUNT_SUM=120
ZONE_COUNT_NONZERO_ALL=YES

OLD_ART002_DISTRIBUTION=10,11,12,12,12,13,13,14,14,9
ART002_OLD_DISTRIBUTION_STATUS=SUPERSEDED_FOR_ART_CONTENT_PLANNING
ZONE_COUNT_DELTA=+4,+3,+1,0,0,-1,-1,-3,-4,+1
NET_DELTA=0

M_ID_COUNT=120
M_ID_UNIQUE=120
M_ID_DUPLICATES=0
M_ID_MISSING=0

OWNER_APPROVED_EXACT_M_ID_REASSIGNMENT=NO
EXACT_M_ID_ZONE_ASSIGNMENT_STATUS=PENDING_CONTENT_RECONCILIATION
M_ID_ZONE_MOVES_PERFORMED=0

ART003_MAY_USE_COUNT_TARGETS=YES
ART003_MAY_INFER_GAMEPLAY_ZONE_FROM_COUNT=NO
ART003_MAY_RENUMBER_IDS=NO
ART003_B01_ART_INVALIDATED_BY_DISTRIBUTION=NO

ART_CONTENT_COUNT_USED_FOR_COMBAT=NO
F009_ENABLED=NO
RARITY_USED_TO_ASSIGN_ZONE_COUNTS=NO
BOSS_INCLUDED_IN_120_COUNT=NO
LORD_INCLUDED_IN_120_COUNT=NO
ROSTER_CLASSIFICATION_RECONCILIATION_REQUIRED=NO

CANONICAL_PLANNING_ARTIFACT_CREATED=YES
DISTRIBUTION_CONTRACT_DETERMINISTIC=PASS
DISTRIBUTION_CONTRACT_TESTS=PASS
ROSTER_IDENTITY_TESTS=PASS
AUTHORITY_BOUNDARY_TESTS=PASS

APP_PY_CHANGED=NO
RUNTIME_SOURCE_CHANGED=NO
RUNTIME_MAPPING_CHANGED=NO
MONSTER_STATS_CHANGED=NO
ART_ASSETS_CHANGED=NO
SCHEMA_CHANGED=NO
MIGRATION_CHANGED=NO

B056_SCOPE_TOUCHED=NO
C049_SCOPE_TOUCHED=NO
A040_SCOPE_TOUCHED=NO
D041_SCOPE_TOUCHED=NO
E045_SCOPE_TOUCHED=NO
ART003_ASSET_SCOPE_TOUCHED=NO

TESTS=ref-bound JSON/roster/count/delta/authority validation
TASK_INTRODUCED_FAILURES=0
PRE_EXISTING_FAILURES=NONE_OBSERVED
ENVIRONMENT_GAPS=exact M-ID Zone assignment remains intentionally pending
UNEXPECTED_FILES=0
SECRET_KEY_TOUCHED=NO

COMMIT=POST_COMMIT_VERIFIED_IN_HANDOFF
PUSHED=YES
MASTER_MERGE=NO
PRODUCTION_QUERY=NO
PRODUCTION_MUTATION=NO
DEPLOY=NO

WHAT_OWNER_APPROVED=Model C as the canonical Art/content planning count vector only.
WHAT_OLD_DISTRIBUTION_WAS_SUPERSEDED=ART002 10,11,12,12,12,13,13,14,14,9.
WHAT_ART003_CAN_USE_NOW=The exact Zone count targets for production planning and batch allocation.
WHAT_REMAINS_UNASSIGNED=Exact Owner-approved M001–M120 Zone placement and any runtime mapping.
WHAT_F034_SHOULD_DO_NEXT=Perform exact-ID content reconciliation if authorized; do not infer gameplay authority.

RESULT=PASS_OWNER_APPROVED_MONSTER_ART_CONTENT_ZONE_DISTRIBUTION_LOCKED
READY_FOR_COORDINATOR_F033_REVIEW=YES
```

Do not start F034 automatically.
