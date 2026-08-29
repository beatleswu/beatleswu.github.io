# F032 Monster 120-Roster Zone Distribution Owner Decision Closure

TASK=F032_MONSTER_120_ROSTER_ZONE_DISTRIBUTION_OWNER_DECISION_CLOSURE_001  
MODE=RESEARCH_MODEL_COMPARE_SPEC_TEST_COMMIT_PUSH  
LANE=F  
APP_PY_WRITER=NO

## Decision summary

This packet reconciles the ART002 candidate against the fresh canonical
`origin/master` snapshot. ART002 remains an art/content planning candidate;
it is not gameplay, combat-profile, Zone-difficulty, runtime-distribution, or
reward authority.

The recommendation is Model C, `14,14,13,12,12,12,12,11,10,10`, exactly
120 identities. It is a recommendation only and is **not Owner approved**.
No ART002 roster, runtime source, gameplay authority, or asset was changed.

```text
CURRENT_ORIGIN_MASTER=6829c4c528adf4800326e90534585a32e390ebec
BASE_SHA=6829c4c528adf4800326e90534585a32e390ebec
FRESH_MASTER_RECONCILIATION=PASS
ART002_SOURCE_REF=origin/codex/art002-120-monster-roster-candidate-001
ART002_SOURCE_SHA=3e7034ef71c27ca00acf456d03f95301f30b8c64
ART002_REMOTE_HEAD_EXACT=YES
ART002_EMBEDDED_PROVENANCE_RECONCILED=YES
ART002_EMBEDDED_PROVENANCE_NOTE=artifact metadata names older 92127b25; this packet binds analysis to fresh 6829c4c5
```

## Current ART002 candidate

The remote ART002 candidate is `3e7034ef71c27ca00acf456d03f95301f30b8c64`.
Its `candidate_status` is `READY_FOR_OWNER_120_MONSTER_ROSTER_REVIEW`, and its
`zone_distribution.authority_status` is `CANDIDATE_PENDING_OWNER_LOCK`.
Therefore its current authority classification is `ART_ONLY`.

| Zone | ART002 count |
|---|---:|
| Z1 | 10 |
| Z2 | 11 |
| Z3 | 12 |
| Z4 | 12 |
| Z5 | 12 |
| Z6 | 13 |
| Z7 | 13 |
| Z8 | 14 |
| Z9 | 14 |
| Z10 | 9 |
| **Total** | **120** |

The roster JSON contains `M001` through `M120` exactly once. The deterministic
check found:

```text
ART002_M_ID_COUNT=120
ART002_M_ID_UNIQUE=120
ART002_DUPLICATE_IDS=0
ART002_MISSING_IDS=0
ALL_ZONES_NONZERO=YES
```

The ten existing runtime identities and 110 proposed art identities remain
separate layers in ART002. The candidate explicitly keeps Boss, Lord, and
Spirit outside the 120 normal-Monster roster.

## Runtime and difficulty boundary

F031's prior runtime findings are preserved as input, not silently promoted
into this content decision:

```text
EXPLICIT_NUMERIC_MONSTER_LEVEL_FIELD=NO
NORMAL_HP_MONOTONIC=YES
NORMAL_ATTACK_MONOTONIC=YES
BOSS_HP_MONOTONIC=YES
BOSS_ATTACK_MONOTONIC=YES
MAJOR_DIFFICULTY_JUMPS=Z5->Z6 largest; Z8->Z9 and Z9->Z10 secondary
LATE_MONSTERS_REQUIRE_MORE_COMBAT_ACTIONS=YES
```

The current fresh-master profile authority uses `max_hp`, `attack`, Zone,
encounter class, and profile/identity references. `monster_profiles.py` has no
formal numeric Monster-level field. `monster_identity.py` has Zone and roster
identity fields; `LV1`-style values are compatibility aliases, not a gameplay
level authority. The profile registry is not changed by F032.

The current combat path also contains percentage-based successful-hit damage,
so higher HP does not imply a linearly higher successful-answer TTK. The exact
F031 conclusion is therefore retained:

```text
MONSTER_QUANTITY_DIFFICULTY_SEPARATION=YES
F031_RUNTIME_EVIDENCE_PRESERVED=YES
```

More unique art may improve visual variety, but a Zone count must not infer HP,
ATK, tier, question difficulty, Boss power, Lord power, or reward. A normal
Monster remains distinct from a Battlefield Boss and Lord, and defeating a
normal Monster does not mean a Zone is cleared.

There is no telemetry in the reviewed evidence:

```text
PLAYER_TELEMETRY_EVIDENCE=NONE
```

The player-experience rationale is content-facing only: early Zones benefit
from additional visual variety during onboarding; middle Zones cover the
largest progression span and need breadth; late Zones can use a curated,
iconic set without assuming that mechanical difficulty requires more species.

## Model comparison

All models below satisfy ten nonzero Zone counts and total exactly 120. None
assigns gameplay stats or changes runtime mapping.

| Model | Counts Z1→Z10 | Early variety | Late repetition risk | Art burden | Discoverability | Zone identity | Difficulty misconception | Finale pacing | Future variant flexibility | Curriculum compatibility | Runtime complexity |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A Current ART002 | 10,11,12,12,12,13,13,14,14,9 | Low-to-medium | Concentrated in Z10 | Back-loaded | Early narrow, late broad | Strong escalation | Medium-high if counts are read as difficulty | Compact but risks sparse finale | Less late room for variants | Acceptable | Same; art-only |
| B Aggressive front-load | 16,15,14,13,12,11,11,10,9,9 | High | High in Z8–Z10 | Front-loaded | Strong early discovery | Strong opening, declining breadth | High reverse-count signal | Finale may feel under-stocked | Reduced late flexibility | Good onboarding, potentially taxonomy-heavy | Same; art-only |
| C Moderate front-load | 14,14,13,12,12,12,12,11,10,10 | High without overload | Low-to-medium | Smoothly distributed | Good across the full arc | Early welcome, stable middle, curated finale | Low-to-medium | Curated without a 9-count tail | Preserves late variants | Best fit absent telemetry | Same; art-only |
| D Balanced | 12,12,12,12,12,12,12,12,12,12 | Medium | Medium | Even | Predictable | Weakest differentiation by quantity | Lowest | Neutral/generic | Equal everywhere | Simple | Same; art-only |

### Model A — preserve current ART002

This is valid arithmetic and the strongest current artifact continuity. It
places the largest art pool in Z8/Z9 while giving Z10 only nine identities.
That can work if the finale is intentionally compact, but it creates the
highest late-finale sparsity risk and has no runtime evidence requiring that
back-loading.

### Model B — aggressive front-load

This best maximizes early visual variety, but its 16-to-9 decline makes the
late roster look intentionally thin. It over-corrects a hypothesis that F031
did not prove: difficulty and unique identity count are separate. It is not
recommended without Owner product evidence or telemetry.

### Model C — moderate front-load

This adds early variety, keeps the middle broad and stable, and retains at
least ten identities in every late Zone. It reduces the chance that the
content plan is mistaken for a difficulty curve while keeping Z10 curated.
It is the best planning default under the current evidence, not a gameplay
rule and not an Owner lock.

### Model D — balanced

Twelve per Zone is easiest to explain and audit. It gives up some early
onboarding variety and some late-finale curation in exchange for symmetry.
It remains a reasonable fallback if the Owner values uniform production more
than Zone-specific identity.

### Model E — Owner custom

No count is assigned until the Owner supplies an explicit ten-number vector.
It must still total 120, keep every Zone nonzero, preserve M001–M120 exactly,
and remain art/content planning only.

## Owner decision packet

### OD-ROSTER-01

```text
QUESTION=What Zone distribution should become the canonical Art/content planning distribution for M001–M120?
OPTION_A=Preserve current ART002: 10,11,12,12,12,13,13,14,14,9
OPTION_B=Aggressive front-load: 16,15,14,13,12,11,11,10,9,9
OPTION_C=Moderate front-load: 14,14,13,12,12,12,12,11,10,10
OPTION_D=Balanced: 12,12,12,12,12,12,12,12,12,12
OPTION_E=Owner custom: pending explicit Owner vector
RECOMMENDATION=OPTION_C
RECOMMENDATION_STATUS=RECOMMENDATION_ONLY; NOT_OWNER_APPROVED
```

### OD-ROSTER-02

```text
QUESTION=Should the chosen Art/content distribution automatically become gameplay Zone pool authority?
RECOMMENDATION=NO
RECOMMENDATION_ART_TO_GAMEPLAY_AUTOPROMOTION=NO
RATIONALE=Art allocation and gameplay encounter/profile authority are separate contracts owned by different lanes.
```

### OD-ROSTER-03

```text
QUESTION=Should every one of M001–M120 ultimately require a unique combat profile?
OPTION_A=YES
OPTION_B=Shared archetype profiles allowed
OPTION_C=Decide later after E044 architecture
RECOMMENDATION=OPTION_C; defer to E044
IMPLEMENTATION=NONE
```

## Scope and validation

```text
ART002_CHANGED=NO
ART003_CHANGED=NO
GAMEPLAY_AUTHORITY_CHANGED=NO
E044_SCOPE_TOUCHED=NO
APP_PY_CHANGED=NO
RUNTIME_SOURCE_CHANGED=NO
MONSTER_STATS_CHANGED=NO
MONSTER_MAPPING_CHANGED=NO
SCHEMA_CHANGED=NO
MIGRATION_CHANGED=NO
```

The deterministic read-only validation used the remote ART002 JSON and tested:

```text
ROSTER_INTEGRITY=PASS
DISTRIBUTION_ARITHMETIC=PASS
TASK_INTRODUCED_FAILURES=0
```

The F031 report itself was not present in reachable Git history at this
reconciliation point, so its findings above are explicitly labeled as
task-provided prior evidence. Fresh-master source inspection confirmed the
separate identity/profile architecture and no F032 source mutation.

No Production query or mutation was performed. No merge, deploy, feature
enablement, ART003 work, image generation, M-ID renumbering, or runtime
distribution change was performed.

## Final report

```text
TASK=F032_MONSTER_120_ROSTER_ZONE_DISTRIBUTION_OWNER_DECISION_CLOSURE_001

CURRENT_ORIGIN_MASTER=6829c4c528adf4800326e90534585a32e390ebec
BASE_SHA=6829c4c528adf4800326e90534585a32e390ebec
FRESH_MASTER_RECONCILIATION=PASS

BRANCH=codex/f032-monster-roster-owner-decision-doc
LOCAL_HEAD=POST_COMMIT_VERIFIED_IN_HANDOFF
REMOTE_HEAD=POST_PUSH_VERIFIED_IN_HANDOFF
REMOTE_HEAD_EXACT=YES

ART002_Z1_COUNT=10
ART002_Z2_COUNT=11
ART002_Z3_COUNT=12
ART002_Z4_COUNT=12
ART002_Z5_COUNT=12
ART002_Z6_COUNT=13
ART002_Z7_COUNT=13
ART002_Z8_COUNT=14
ART002_Z9_COUNT=14
ART002_Z10_COUNT=9
ART002_TOTAL=120

ART002_M_ID_COUNT=120
ART002_M_ID_UNIQUE=120
ART002_DUPLICATE_IDS=0

MODEL_A_CURRENT_ART002=10,11,12,12,12,13,13,14,14,9
MODEL_B_AGGRESSIVE_FRONT_LOAD=16,15,14,13,12,11,11,10,9,9
MODEL_C_MODERATE_FRONT_LOAD=14,14,13,12,12,12,12,11,10,10
MODEL_D_BALANCED=12,12,12,12,12,12,12,12,12,12

RECOMMENDED_DISTRIBUTION=14,14,13,12,12,12,12,11,10,10
RECOMMENDATION_STATUS=RECOMMENDATION_ONLY; NOT_OWNER_APPROVED

MONSTER_QUANTITY_DIFFICULTY_SEPARATION=YES
F031_RUNTIME_EVIDENCE_PRESERVED=YES
PLAYER_TELEMETRY_EVIDENCE=NONE

OD_ROSTER_01=Recommend C; Owner decision pending
OD_ROSTER_02=NO art-to-gameplay autopromotion
OD_ROSTER_03=Defer unique-profile policy to E044
RECOMMENDED_ART_TO_GAMEPLAY_AUTOPROMOTION=NO

ART002_CHANGED=NO
ART003_CHANGED=NO
E044_SCOPE_TOUCHED=NO
APP_PY_CHANGED=NO
RUNTIME_SOURCE_CHANGED=NO
MONSTER_STATS_CHANGED=NO
MONSTER_MAPPING_CHANGED=NO
SCHEMA_CHANGED=NO
MIGRATION_CHANGED=NO

TESTS=deterministic PowerShell ref-based roster/count/arithmetic check
ROSTER_INTEGRITY=PASS
DISTRIBUTION_ARITHMETIC=PASS
TASK_INTRODUCED_FAILURES=0
PRE_EXISTING_FAILURES=NONE_OBSERVED
ENVIRONMENT_GAPS=F031 report absent from reachable Git history; prior findings retained as task input

COMMIT=POST_COMMIT_VERIFIED_IN_HANDOFF
PUSHED=YES
MASTER_MERGE=NO
PRODUCTION_QUERY=NO
PRODUCTION_MUTATION=NO
DEPLOY=NO

WHAT_CURRENT_ART002_DOES=Provides 120 art/content candidate identities, briefs, and a pending Zone allocation; it is not gameplay authority.
WHY_QUANTITY_AND_DIFFICULTY_ARE_SEPARATE=Current difficulty is represented by runtime profile/encounter data; F031 found monotonic HP/ATK but non-linear successful-hit TTK.
WHY_THE_RECOMMENDED_MODEL_WAS_CHOSEN=It improves early variety, stabilizes the middle, keeps late Zones curated but non-sparse, and does not overclaim unsupported telemetry.
WHAT_OWNER_MUST_DECIDE=Choose OD-ROSTER-01 distribution, reject/accept art-to-gameplay autopromotion in OD-ROSTER-02, and set OD-ROSTER-03 policy after E044.
WHAT_MUST_NOT_BE_IMPLEMENTED_YET=Do not lock ART002, map it into gameplay, generate ART003, assign combat profiles, or change runtime authority.

RESULT=PASS_MONSTER_120_ROSTER_DISTRIBUTION_READY_FOR_OWNER_DECISION
READY_FOR_COORDINATOR_F032_REVIEW=YES
```

Do not start F033 automatically.
