# E048 Battlefield Monster Catalog Explicit Consumer Migration Decision Packet

Status: owner decision packet only.  This document compares the accepted
E045/E046/E047 MonsterCatalog foundation with the current Battlefield runtime;
it does not activate the catalog, change a consumer, or authorize a cutover.

## Provenance and lineage

```text
TASK=E048_BATTLEFIELD_MONSTER_CATALOG_EXPLICIT_CONSUMER_MIGRATION_DECISION_PACKET_001
CURRENT_ORIGIN_MASTER=3f98c204a2b249763ad3d8d0730e5d3a0764622b
BASE_SHA=3f98c204a2b249763ad3d8d0730e5d3a0764622b
FRESH_MASTER_RECONCILIATION=PASS
FRESH_MASTER_IS_ANCESTOR=YES

E045_ACCEPTED_HEAD=ceec80e2fe1793198cf04ea8f8cb781a43eeea5b
E046_ACCEPTED_HEAD=70c41bd2639837556779af63be3632ee5e4d0eac
E047_ACCEPTED_HEAD=5c20e0294f6dc2b3b0a67c387b2266d836fbd54f
```

The accepted E-line commits were not assumed to be merged into the fresh
master.  Their equivalent patches were replayed in this isolated decision
packet worktree so the comparison uses one reproducible source tree:

| Accepted layer | Accepted source head | Fresh-base materialization | Evidence |
| --- | --- | --- | --- |
| E045 foundation | `ceec80e2fe1793198cf04ea8f8cb781a43eeea5b` | `77851edd1` | `monster_catalog_foundation.py`, E045 contract tests |
| E046 adapter | `70c41bd2639837556779af63be3632ee5e4d0eac` | `fd62f39a4`, `82e5b9b26` | shadow adapter and accepted consumer matrix |
| E047 shadow caller | `5c20e0294f6dc2b3b0a67c387b2266d836fbd54f` | `934d59da6` | Battlefield shadow caller and drift tests |

Therefore:

```text
E045_FOUNDATION_PRESENT=YES
E046_ADAPTER_PRESENT=YES
E047_SHADOW_CALLER_PRESENT=YES
E044_OWNER_DECISIONS_PRESERVED=YES
```

The original E045/E046/E047 SHAs are retained as accepted lineage references;
the fresh-base materializations are the immutable evidence inputs for this
packet.  No unrelated lane was merged.

## Decision in one sentence

The 20 Battlefield Normal/Boss entries are decision-ready for an explicit
catalog migration because identity, context, profile reference, HP, and ATK
are all parity-zero, but the current safest choice is a time-boxed read-only
shadow window (Option B) followed by an Owner-approved fail-closed cutover
(Option D).  Permanent dual authority is not recommended.

```text
RECOMMENDED_MIGRATION_OPTION=OPTION_B_TRANSITION_TO_OPTION_D
PERMANENT_DUAL_AUTHORITY_RECOMMENDED=NO
```

## Current Battlefield authority inventory

The source inventory covered the F003 identity module, F004 profile registry,
F008 resolver, Battlefield initialization/status paths, combat settlement
paths, and adjacent selector/Adventure/World callers.  The active Battlefield
authority remains the following:

| Caller | Current source | Current authority | Mutation role | Proposed catalog source | Migration scope |
| --- | --- | --- | --- | --- | --- |
| Battlefield roster and initialization (`app.py:_BATTLEFIELD_ROSTER`, `_get_or_create_battlefield`) | Server-owned roster tuple; F003 `build_battlefield_identity_registry` binds stable identity to roster slot | F003 identity plus the existing server-owned roster | Creates/repairs the persisted Battlefield row and selects the initial/next roster slot | `get_monster(monster_id)` plus explicit `BATTLEFIELD_NORMAL`/`BATTLEFIELD_BOSS` reference | Battlefield only; shadow first |
| Battlefield identity response (`app.py:_battlefield_identity_payload`) | F003 `canonical_battlefield_identity` from server-owned `monster_idx`/roster slot; legacy type/name are compatibility fields | F003 identity | Projects identity fields into the existing response; unresolved identity fails closed | E045 explicit `monster_id` and catalog entry | Convert only after identity parity gate |
| Battlefield combat/settlement (`app.py:_update_monster_and_quests`, `_lane_b_monster_update_with_authoritative_profile`) | F008 `resolve_monster_combat_profile`; F004 values plus explicitly scoped persisted-HP compatibility | F008 active combat profile; existing settlement remains authoritative for HP, defeat, drops, rewards, and persistence | Calculates damage/retaliation, writes HP/defeat/kill state, and invokes existing settlement | `resolve_context_profile(monster_id, context)` with the E045 versioned reference | Last Battlefield consumer to convert |
| Battlefield status route (`app.py:/api/monster/status`) | Persisted Battlefield row, F003 identity, F008 resolver, and server-owned equipment effects | Existing route response and F008 stat projection | May initialize/repair state through `_get_or_create_battlefield`; response itself does not grant progression | Catalog identity/profile projection after status parity proof | First read-only migration candidate; no route change in E048 |
| Battlefield next-monster projection (`_update_monster_and_quests` next-monster branch) | Server-owned roster order and F008 profile for the next slot | Existing Battlefield transition/settlement path | Persists the next roster state after a defeat | Explicit catalog identity/profile lookup for the already selected slot | Convert with combat/settlement, not independently |

`UNKNOWN_ACTIVE_CONSUMERS=0`.  There is no separate active admin/debug Monster
authority in the inspected source; `/api/monster/status` is player
initialization.  The E047 caller is diagnostic/test-only and is not counted as
an active gameplay consumer.

### Adjacent consumers explicitly excluded

| Area | Current authority | E048 treatment |
| --- | --- | --- |
| Map Battle (`map_battle_runtime.py`, `_map_battle_monster_hp`) | Existing Map Battle state/question contract through F008, including its explicit legacy compatibility fallback | Not a Battlefield migration target; no catalog profile inheritance |
| F009 selector (`monster_encounter_selector.py`) | Default-off selector contract; it does not own stat authority | `F009_ENABLED=NO`; not included in the migration |
| Adventure question/boss flow | Adventure curriculum, server review evidence, and World/Lord contracts | Not included; no Battlefield profile inheritance |
| World/progression | World persistence and progression authority | Never replaced by MonsterCatalog |
| Rewards/settlement | Existing server-owned settlement and reward writers | Not migrated by a catalog decision packet |
| Lord | Lord route and server verdict; no numeric Lord profile | No numeric catalog migration |
| ART002/ART003/F035 | Content/art/planning metadata | Never used as gameplay identity, profile, or Zone authority |

## Migration options

### Option A — keep current F003/F004/F008 authority and shadow only

```text
OPTION_A=KEEP_CURRENT_F003_F004_F008_AUTHORITY_AND_SHADOW_ONLY
BENEFITS=Zero gameplay cutover risk; preserves all current contracts; simple rollback.
RISKS=Catalog remains non-authoritative indefinitely; two representations can drift unless shadowing remains maintained; migration benefit is deferred.
ROLLBACK_COMPLEXITY=LOW; no active authority change to undo.
AUTHORITY_AMBIGUITY=LOW_NOW_HIGH_IF_PERMANENT; current authority is clear but the long-term duplicate source remains.
RECOMMENDATION=Accept only as a short hold state, not as the target architecture.
```

### Option B — catalog read-only runtime shadow before authority migration

```text
OPTION_B=CATALOG_READONLY_RUNTIME_SHADOW_BEFORE_AUTHORITY_MIGRATION
BENEFITS=Detects identity/context/profile/HP/ATK drift continuously without changing player output; validates real caller inputs before cutover.
RISKS=Temporary dual evaluation and bounded overhead; a shadow path must remain non-player-visible and non-mutating; it can become permanent without an exit gate.
ROLLBACK_COMPLEXITY=LOW; disable the shadow caller and retain current runtime.
AUTHORITY_AMBIGUITY=LOW_IF_EXPLICIT; current F003/F004/F008 result remains the only result and shadow output is diagnostic only.
RECOMMENDATION=RECOMMENDED_NEXT DECISION; use only with a fixed exit window and zero-drift exit criteria.
```

### Option C — migrate Battlefield consumers with legacy fallback

```text
OPTION_C=MIGRATE_BATTLEFIELD_CONSUMERS_TO_CATALOG_AUTHORITY_WITH_FALLBACK
BENEFITS=Incremental caller conversion; legacy path can keep an encounter available during a data gap; operational rollback is comparatively easy.
RISKS=Fallback can hide catalog defects, create two authorities, and silently reintroduce F004/F008 as an unreviewed decision path; it can become permanent.
ROLLBACK_COMPLEXITY=MEDIUM; caller routing and fallback state must both be reverted and re-proven.
AUTHORITY_AMBIGUITY=HIGH unless the fallback is explicit, bounded, observable, and never silent.
RECOMMENDATION=NOT RECOMMENDED as a steady state; permit only as a separately approved, time-boxed compatibility bridge.
```

### Option D — migrate Battlefield consumers fail-closed without legacy fallback

```text
OPTION_D=MIGRATE_BATTLEFIELD_CONSUMERS_TO_CATALOG_AUTHORITY_FAIL_CLOSED_NO_LEGACY_FALLBACK
BENEFITS=One clear authority; unknown/missing/mismatched data cannot silently choose a different Monster or stat; defects surface immediately.
RISKS=An incomplete catalog or bad reference can block an encounter; requires full caller coverage, a tested rollback artifact, and the app.py writer for route conversion.
ROLLBACK_COMPLEXITY=HIGHER; the authority switch and legacy retirement must be reversed as one controlled operation.
AUTHORITY_AMBIGUITY=LOWEST; catalog is the sole Battlefield identity/profile authority after cutover.
RECOMMENDATION=RECOMMENDED TARGET after Option B exit criteria and explicit Owner approval.
```

```text
TRANSITION_WINDOW=One bounded Owner-approved shadow/validation window; no open-ended dual-authority period.
EXIT_CRITERIA=20/20 Battlefield entries match identity, context, explicit versioned profile reference, HP, and ATK; fail-closed cases pass; no active-output drift; all intended callers are enumerated; rollback artifact is ready.
```

## Fail-closed policy matrix

| Condition | Shadow/decision-packet behavior | Future Option D cutover behavior | Forbidden behavior |
| --- | --- | --- | --- |
| Unknown Monster ID | Emit typed diagnostic failure; current F003/F008 result remains untouched | Reject the catalog resolution and stop the affected operation | First Monster, Zone default, display-name guess, art index, or array-index fallback |
| Unknown profile ID/version | Emit `UNKNOWN_PROFILE`; do not compare as a match | Reject the affected encounter and raise an operational/data defect | Latest-version substitution or generated profile |
| Missing context profile | Emit `MISSING_PROFILE`/not-applicable where the context contract says no profile exists | Reject the affected Battlefield operation; do not cross-context inherit | Adventure or Lord inheriting Battlefield stats |
| Context mismatch | Emit `CONTEXT_MISMATCH` | Reject; require explicit caller context correction | Treating Normal, Battlefield Boss, and Lord as equivalent |
| HP/ATK mismatch | Emit explicit `HP_DRIFT` or `ATK_DRIFT`; never replace current values | Block cutover or roll back the affected authority change | Formula correction, tolerance masking, or silent legacy fallback |

```text
GENERATED_PROFILE_FALLBACK=NO
UNKNOWN_MONSTER_FAIL_CLOSED=YES
UNKNOWN_PROFILE_FAIL_CLOSED=YES
MISSING_PROFILE_FAIL_CLOSED=YES
```

## Battlefield Normal migration readiness

`CURRENT_PROFILE` is the active F008 view of the F004 stat profile.  The
catalog reference is the same explicit profile ID under the E045 versioned
registry.  `READY=YES_FOR_EXPLICIT_MIGRATION_DECISION` means the row is
parity-ready for a future approved cutover; it does not authorize runtime
mutation in E048.

| ZONE | CURRENT_MONSTER_ID | CATALOG_MONSTER_ID | CURRENT_PROFILE (HP/ATK) | CATALOG_PROFILE (HP/ATK) | PARITY | READY |
| --- | --- | --- | --- | --- | --- | --- |
| zone_01 | `legacy_bf_01_normal` | `legacy_bf_01_normal` | `stat_legacy_bf_01_normal@f008.v1` (80/2) | `stat_legacy_bf_01_normal@e045.profile.v1` (80/2) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |
| zone_02 | `legacy_bf_02_normal` | `legacy_bf_02_normal` | `stat_legacy_bf_02_normal@f008.v1` (130/3) | `stat_legacy_bf_02_normal@e045.profile.v1` (130/3) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |
| zone_03 | `legacy_bf_03_normal` | `legacy_bf_03_normal` | `stat_legacy_bf_03_normal@f008.v1` (200/4) | `stat_legacy_bf_03_normal@e045.profile.v1` (200/4) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |
| zone_04 | `legacy_bf_04_normal` | `legacy_bf_04_normal` | `stat_legacy_bf_04_normal@f008.v1` (220/5) | `stat_legacy_bf_04_normal@e045.profile.v1` (220/5) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |
| zone_05 | `legacy_bf_05_normal` | `legacy_bf_05_normal` | `stat_legacy_bf_05_normal@f008.v1` (260/6) | `stat_legacy_bf_05_normal@e045.profile.v1` (260/6) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |
| zone_06 | `legacy_bf_06_normal` | `legacy_bf_06_normal` | `stat_legacy_bf_06_normal@f008.v1` (520/12) | `stat_legacy_bf_06_normal@e045.profile.v1` (520/12) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |
| zone_07 | `legacy_bf_07_normal` | `legacy_bf_07_normal` | `stat_legacy_bf_07_normal@f008.v1` (760/16) | `stat_legacy_bf_07_normal@e045.profile.v1` (760/16) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |
| zone_08 | `legacy_bf_08_normal` | `legacy_bf_08_normal` | `stat_legacy_bf_08_normal@f008.v1` (1100/20) | `stat_legacy_bf_08_normal@e045.profile.v1` (1100/20) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |
| zone_09 | `legacy_bf_09_normal` | `legacy_bf_09_normal` | `stat_legacy_bf_09_normal@f008.v1` (1700/28) | `stat_legacy_bf_09_normal@e045.profile.v1` (1700/28) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |
| zone_10 | `legacy_bf_10_normal` | `legacy_bf_10_normal` | `stat_legacy_bf_10_normal@f008.v1` (2400/36) | `stat_legacy_bf_10_normal@e045.profile.v1` (2400/36) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |

```text
NORMAL_SHADOW_PARITY=PASS
NORMAL_DRIFT_COUNT=0
```

## Battlefield Boss migration readiness

Boss remains an explicit `BATTLEFIELD_BOSS` encounter class.  It is not a
Lord, and its profile is not derived from a Normal profile formula.

| ZONE | CURRENT_BOSS_ID | CATALOG_BOSS_ID | CURRENT_PROFILE (HP/ATK) | CATALOG_PROFILE (HP/ATK) | PARITY | READY |
| --- | --- | --- | --- | --- | --- | --- |
| zone_01 | `legacy_bf_01_boss` | `legacy_bf_01_boss` | `stat_legacy_bf_01_boss@f008.v1` (100/2) | `stat_legacy_bf_01_boss@e045.profile.v1` (100/2) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |
| zone_02 | `legacy_bf_02_boss` | `legacy_bf_02_boss` | `stat_legacy_bf_02_boss@f008.v1` (160/4) | `stat_legacy_bf_02_boss@e045.profile.v1` (160/4) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |
| zone_03 | `legacy_bf_03_boss` | `legacy_bf_03_boss` | `stat_legacy_bf_03_boss@f008.v1` (240/5) | `stat_legacy_bf_03_boss@e045.profile.v1` (240/5) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |
| zone_04 | `legacy_bf_04_boss` | `legacy_bf_04_boss` | `stat_legacy_bf_04_boss@f008.v1` (260/6) | `stat_legacy_bf_04_boss@e045.profile.v1` (260/6) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |
| zone_05 | `legacy_bf_05_boss` | `legacy_bf_05_boss` | `stat_legacy_bf_05_boss@f008.v1` (290/7) | `stat_legacy_bf_05_boss@e045.profile.v1` (290/7) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |
| zone_06 | `legacy_bf_06_boss` | `legacy_bf_06_boss` | `stat_legacy_bf_06_boss@f008.v1` (700/14) | `stat_legacy_bf_06_boss@e045.profile.v1` (700/14) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |
| zone_07 | `legacy_bf_07_boss` | `legacy_bf_07_boss` | `stat_legacy_bf_07_boss@f008.v1` (920/18) | `stat_legacy_bf_07_boss@e045.profile.v1` (920/18) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |
| zone_08 | `legacy_bf_08_boss` | `legacy_bf_08_boss` | `stat_legacy_bf_08_boss@f008.v1` (1350/22) | `stat_legacy_bf_08_boss@e045.profile.v1` (1350/22) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |
| zone_09 | `legacy_bf_09_boss` | `legacy_bf_09_boss` | `stat_legacy_bf_09_boss@f008.v1` (2000/32) | `stat_legacy_bf_09_boss@e045.profile.v1` (2000/32) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |
| zone_10 | `legacy_bf_10_boss` | `legacy_bf_10_boss` | `stat_legacy_bf_10_boss@f008.v1` (2800/40) | `stat_legacy_bf_10_boss@e045.profile.v1` (2800/40) | MATCH | YES_FOR_EXPLICIT_MIGRATION_DECISION |

```text
BOSS_SHADOW_PARITY=PASS
BOSS_DRIFT_COUNT=0
BATTLEFIELD_BOSS_IS_LORD=NO
```

## Authority firewalls

```text
LORD_ACTIVE_CALLER_INTEGRATED=NO
LORD_NUMERIC_PROFILE_CREATED=NO
ADVENTURE_INCLUDED_IN_MIGRATION_DECISION=NO
ADVENTURE_PROFILE_AUTO_INHERITS_BATTLEFIELD=NO
F009_ENABLED=NO
F009_INCLUDED_IN_MIGRATION=NO
COMBAT_CLASS_FREQUENCY_COUPLED=NO
F035_PLANNING_ZONE_USED_FOR_GAMEPLAY=NO
ART002_GAMEPLAY_AUTHORITY=NO
ART003_GAMEPLAY_AUTHORITY=NO
ZONE_QUESTION_STAGE_MAPPING_CHANGED=NO
```

The E045/E046 catalog remains a candidate representation.  It has no
authority over selected Zone, progression Zone, Zone unlocks, question
mapping, reward settlement, Boss reward ownership, Spirit grants, or Lord
correctness.  Common/Rare/Elite remains disabled; any future combat class
field remains independent of encounter frequency.

## Proposed cutover sequence (future task; not executed here)

1. **Preconditions and Owner gate.** Re-fetch the exact target master, bind the
   conversion to an explicit catalog/profile version, confirm 20/20 current
   Battlefield rows and all intended callers, confirm no profile drift, and
   reserve the separately owned `app.py` writer.  Keep Adventure, Lord, F009,
   World, rewards, and Map Battle outside the change.
2. **Read-only status projection.** Convert or shadow the status/diagnostic
   projection first.  Compare explicit Monster ID, context, profile ID/version,
   HP, and ATK at the same boundary as the existing F008 result.  Do not write
   catalog output into persistence yet.
3. **Normal caller.** Convert Battlefield Normal profile reads and response
   projections, preserving the current F003 roster-slot selection and F008
   compatibility/error boundary while the cutover is staged.
4. **Boss caller.** Convert Battlefield Boss reads with a separate explicit
   `BATTLEFIELD_BOSS` reference.  Do not share a Normal profile or route Boss
   into Lord.
5. **Mutation/settlement last.** Only after the read-only and response callers
   pass should the combat/settlement path consume the catalog profile.  HP
   transition, defeat, rewards, persistence, and progression remain owned by
   their existing server contracts.
6. **Authority switch.** Under a separate Owner-approved implementation task,
   make the catalog resolver the single Battlefield identity/profile authority.
   Do not keep an implicit F004/F008 fallback in the authority path.
7. **Rollback gate.** On any identity/context/profile/HP/ATK drift, missing
   profile, response change, settlement change, reward change, or progression
   change, stop and restore the last known F003/F004/F008 path using the
   prepared rollback artifact. Preserve diagnostic evidence.
8. **Legacy retirement.** Retire the old Battlefield authority only after the
   full shadow window is clean, fail-closed cases are exercised, active output
   is unchanged through the approved cutover, and the Owner signs off. F008
   may remain as a deliberately documented compatibility implementation only
   if it is no longer a competing Battlefield authority.

```text
PROPOSED_CUTOVER_SEQUENCE=READ_ONLY_STATUS -> NORMAL_READS -> BOSS_READS -> MUTATION/SETTLEMENT -> SINGLE_AUTHORITY_SWITCH -> LEGACY_RETIREMENT
LEGACY_FALLBACK_POLICY=NONE_AFTER_OPTION_D_CUTOVER; any Option C bridge must be explicit, time-boxed, and separately approved.
```

## Rollback decision matrix

| Observation | Classification | Decision | Evidence to retain |
| --- | --- | --- | --- |
| Shadow-only mismatch before cutover, no active output change | Safe rollback/hold | Disable the shadow caller or keep current authority; do not alter data | Deterministic record, caller, zone, context, profile IDs, values |
| Unknown Monster or missing catalog entry | Catalog defect | Block migration; do not choose a default or fallback silently | Exact input, catalog version, current F003 identity |
| Unknown/missing profile or context mismatch | Profile/data defect | Fail closed and stop the affected caller; do not inherit another context | Profile ID/version, context, exception category |
| Any identity/profile/HP/ATK mismatch | Data/profile mismatch | Do not cut over; if already switched, roll back the affected caller | Before/after tuple and drift type |
| Player-visible response, combat, reward, progression, or Boss behavior changes | Unexpected gameplay drift | Immediate authority rollback and Owner review | API response, settlement/progression evidence, regression output |
| Correct parity and all fail-closed tests pass | Safe progression | Continue only to the next explicitly approved caller conversion | Full matrix, test commit, cutover gate |

Rollback is a source/authority routing decision only.  E048 performs no
rollback, data repair, schema change, production query, production mutation, or
deployment.

## Owner decision packet

`OWNER_DECISION_ITEM_COUNT=4`

### E048-D1 — Battlefield adoption strategy

**QUESTION:** Which adoption strategy should the Owner authorize?

**OPTIONS:**

- A: Keep F003/F004/F008 authoritative and retain shadow/test evidence only.
- B: Add a bounded, read-only catalog shadow window before migration.
- C: Migrate with a legacy fallback.
- D: Migrate to catalog authority fail-closed without legacy fallback.

**RECOMMENDED_OPTION:** B now, with D as the target after the exit criteria.

**WHY:** All 20 rows are parity-ready, but E048 is a decision packet and has
not converted a real route.  B supplies caller-bound evidence without changing
player output; D provides the intended single authority once coverage and
rollback are approved.

**RISK_IF_WRONG:** Premature D can block a player on an incomplete reference;
permanent A/B leaves duplicate representations and future drift unresolved;
C can hide defects behind an ambiguous fallback.

### E048-D2 — Legacy fallback policy during transition

**QUESTION:** May a converted Battlefield consumer silently fall back to the
legacy F003/F004/F008 authority when catalog resolution fails?

**OPTIONS:**

- No silent fallback; fail closed and stop the affected operation.
- A separately approved, explicit, time-boxed compatibility bridge with a
  visible diagnostic outcome and an expiry/retirement gate.
- Permanent fallback for operational availability.

**RECOMMENDED_OPTION:** No fallback after the authority switch.  Before the
switch, use the current runtime as the unchanged authority while shadow output
is diagnostic; do not treat that as a hidden catalog fallback.

**WHY:** The current runtime can remain the authority during Option B without
creating a second decision path.  Option D must make unknown/missing data
observable rather than silently restoring a competing authority.

**RISK_IF_WRONG:** A permissive fallback can mask catalog defects and make
rollback/retirement impossible to reason about; a strict policy can temporarily
block an encounter if catalog coverage regresses.

### E048-D3 — Cutover and rollback threshold

**QUESTION:** What evidence is sufficient to switch Battlefield authority and
when must the change roll back?

**OPTIONS:**

- Any identity, context, profile ID/version, HP, or ATK mismatch blocks/rolls
  back.
- Permit bounded numeric or profile drift while the player result remains
  available.
- Allow a manual exception per incident.

**RECOMMENDED_OPTION:** Any mismatch blocks; require zero drift across all 10
Normal and 10 Boss rows, typed fail-closed cases, unchanged active output, and
the full caller inventory before switching.  Any post-switch gameplay,
response, reward, or progression drift triggers rollback.

**WHY:** The E045 contract is explicit and versioned; tolerance would turn an
authority mismatch into silent balance or identity change.

**RISK_IF_WRONG:** A tolerance policy can ship an incorrect profile; an overly
strict policy delays migration but preserves player safety and auditability.

### E048-D4 — Migration scope and caller order

**QUESTION:** Which consumers belong in the first implementation task?

**OPTIONS:**

- Battlefield status/read-only projection, then Normal, Boss, and finally
  combat/settlement.
- Convert all Battlefield, Adventure, Lord, F009, World, and reward callers in
  one change.
- Convert only the combat mutation path first.

**RECOMMENDED_OPTION:** Battlefield-only order: status/read-only -> Normal ->
Boss -> mutation/settlement.  Adventure, Lord, F009, World, rewards, and Map
Battle remain separate decisions.

**WHY:** It reduces the authority surface and preserves the already approved
cross-lane ownership boundaries.  The read-only stage makes response and
profile errors visible before combat mutation is exposed.

**RISK_IF_WRONG:** A broad conversion can mix independent authorities and make
rollback ambiguous; mutation-first can change player outcomes before parity is
proven at the route boundary.

## Validation evidence

The following bounded suites were run from the fresh-base reconciled worktree:

```text
E045_E046_E047_CONTRACTS=28 passed in 2.09s
CURRENT_AUTHORITY_REGRESSION=154 passed in 8.70s
```

The 28-test suite covers the E045 foundation, E046 adapter, E047 caller,
Normal/Boss parity and fail-closed cases.  The 154-test suite additionally
covers F003 identity, F004 profiles, F008 resolver, F009 default-off behavior,
World/Monster boundary, Adventure context, and related current runtime
contracts.

The existing `tests/test_map_battle_runtime.py` was also bounded.  It emitted
25 completed cases and then stalled for approximately 120 seconds before it
was interrupted.  E047's prior evidence recorded 27/27 for that unchanged
suite; this E048 run does not claim a fresh Map Battle pass and does not
attribute the harness stall to E048, which changes no runtime file.

```text
FAIL_CLOSED_REGRESSION=PASS
TASK_INTRODUCED_FAILURES=0
PRE_EXISTING_FAILURES=Map Battle harness stall in bounded run; no E048 runtime delta
ENVIRONMENT_GAPS=Map Battle suite did not complete within the bounded window
```

## Scope and non-mutation record

```text
APP_PY_CHANGED=NO
RUNTIME_WIRING_CHANGED=NO
ACTIVE_GAMEPLAY_OUTPUT_CHANGED=NO
SCHEMA_CHANGED=NO
MIGRATION_CHANGED=NO
DATA_CHANGED=NO
B060_SCOPE_TOUCHED=NO
PRODUCTION_QUERY=NO
PRODUCTION_MUTATION=NO
DEPLOY=NO
SECRET_KEY_TOUCHED=NO
```

No catalog authority was activated.  No E048 code path selects a Monster,
sets HP/ATK, changes Boss classification, settles rewards, changes
progression, or calls Adventure/Lord/F009/World authority.

## Next task

```text
NEXT_E_TASK=E049_BATTLEFIELD_MONSTER_CATALOG_OWNER_APPROVED_CONSUMER_MIGRATION_IMPLEMENTATION_001
NEXT_E_TASK_REQUIRES_OWNER_DECISION=YES
```

E049 should implement only the Owner-approved Battlefield caller sequence,
starting with a read-only status/diagnostic projection, and must reserve the
`app.py` writer before changing route consumers.  It should carry this exact
20-row matrix, the fail-closed policy, and the rollback artifact into its
implementation tests.  It must not broaden into Adventure, Lord, F009, World,
reward, Map Battle, ART, or planning-zone authority.

## Final report

```text
TASK=E048_BATTLEFIELD_MONSTER_CATALOG_EXPLICIT_CONSUMER_MIGRATION_DECISION_PACKET_001
CURRENT_ORIGIN_MASTER=3f98c204a2b249763ad3d8d0730e5d3a0764622b
BASE_SHA=3f98c204a2b249763ad3d8d0730e5d3a0764622b
FRESH_MASTER_RECONCILIATION=PASS

E045_HEAD=ceec80e2fe1793198cf04ea8f8cb781a43eeea5b
E046_HEAD=70c41bd2639837556779af63be3632ee5e4d0eac
E047_HEAD=5c20e0294f6dc2b3b0a67c387b2266d836fbd54f
E045_FOUNDATION_PRESENT=YES
E046_ADAPTER_PRESENT=YES
E047_SHADOW_CALLER_PRESENT=YES

CURRENT_BATTLEFIELD_AUTHORITY_MATRIX=DOCUMENTED; F003 identity, F004 profiles, F008 resolver, existing Battlefield runtime/settlement
UNKNOWN_ACTIVE_CONSUMERS=0

MIGRATION_OPTION_MATRIX=OPTIONS_A_B_C_D_COMPARED
RECOMMENDED_MIGRATION_OPTION=OPTION_B_TRANSITION_TO_OPTION_D
PERMANENT_DUAL_AUTHORITY_RECOMMENDED=NO
TRANSITION_WINDOW=ONE_BOUNDED_OWNER_APPROVED_SHADOW/VALIDATION_WINDOW
EXIT_CRITERIA=20/20_ZERO_DRIFT_PLUS_FAIL_CLOSED_AND_ACTIVE_OUTPUT_PROOF

FAIL_CLOSED_POLICY_MATRIX=DOCUMENTED
GENERATED_PROFILE_FALLBACK=NO

NORMAL_ZONE_MIGRATION_MATRIX=10_ENTRIES
NORMAL_SHADOW_PARITY=PASS
NORMAL_DRIFT_COUNT=0
BOSS_ZONE_MIGRATION_MATRIX=10_ENTRIES
BOSS_SHADOW_PARITY=PASS
BOSS_DRIFT_COUNT=0

BATTLEFIELD_BOSS_IS_LORD=NO
LORD_ACTIVE_CALLER_INTEGRATED=NO
LORD_NUMERIC_PROFILE_CREATED=NO
ADVENTURE_INCLUDED_IN_MIGRATION_DECISION=NO
ADVENTURE_PROFILE_AUTO_INHERITS_BATTLEFIELD=NO
F009_ENABLED=NO
F009_INCLUDED_IN_MIGRATION=NO
COMBAT_CLASS_FREQUENCY_COUPLED=NO
F035_PLANNING_ZONE_USED_FOR_GAMEPLAY=NO
ART002_GAMEPLAY_AUTHORITY=NO
ART003_GAMEPLAY_AUTHORITY=NO

PROPOSED_CUTOVER_SEQUENCE=DOCUMENTED_NOT_EXECUTED
ROLLBACK_DECISION_MATRIX=DOCUMENTED_NOT_EXECUTED
OWNER_DECISION_ITEM_COUNT=4
OWNER_DECISION_PACKET=E048-D1_THROUGH_E048-D4
NEXT_E_TASK=E049_BATTLEFIELD_MONSTER_CATALOG_OWNER_APPROVED_CONSUMER_MIGRATION_IMPLEMENTATION_001
NEXT_E_TASK_REQUIRES_OWNER_DECISION=YES

APP_PY_CHANGED=NO
RUNTIME_WIRING_CHANGED=NO
ACTIVE_GAMEPLAY_OUTPUT_CHANGED=NO
SCHEMA_CHANGED=NO
MIGRATION_CHANGED=NO
DATA_CHANGED=NO
B060_SCOPE_TOUCHED=NO
TESTS=28_E045-E047_CONTRACTS_PLUS_154_CURRENT_AUTHORITY_REGRESSION_PASSED
TASK_INTRODUCED_FAILURES=0
PRE_EXISTING_FAILURES=BOUNDED_MAP_BATTLE_HARNESS_STALL_ONLY
ENVIRONMENT_GAPS=MAP_BATTLE_SUITE_DID_NOT_COMPLETE_WITHIN_BOUNDED_WINDOW
UNEXPECTED_FILES=0_BEYOND_ACCEPTED_E045-E047_LINEAGE_AND_THIS_PACKET
SECRET_KEY_TOUCHED=NO

MASTER_MERGE=NO
PRODUCTION_QUERY=NO
PRODUCTION_MUTATION=NO
DEPLOY=NO

RESULT=PASS_BATTLEFIELD_MONSTER_CATALOG_EXPLICIT_CONSUMER_MIGRATION_DECISION_PACKET
READY_FOR_COORDINATOR_E048_REVIEW=YES
```
