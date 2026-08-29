# E045 Canonical Monster Catalog and Versioned Combat Profile Foundation

## Status

| Field | Value |
|---|---|
| Task | `E045_CANONICAL_MONSTER_CATALOG_AND_VERSIONED_COMBAT_PROFILE_FOUNDATION_001` |
| Lane | `E` |
| Fresh base | `origin/master` = `6829c4c528adf4800326e90534585a32e390ebec` |
| E044 accepted contract | `40ee6e0553f1a463758fcda2e74dbdfb81ab457a` |
| Branch | `codex/e045-canonical-monster-catalog-versioned-profile-foundation` |
| Runtime wiring | None |
| `app.py` | Unchanged |
| Database/schema | Unchanged |
| F009 activation | Unchanged and off |
| ART002 | Not promoted |
| Production | Not queried or mutated |

E045 creates a candidate-only, deterministic foundation for a shared Monster
catalog and explicit versioned combat-profile references. It does not replace
the current runtime source, alter a stat, select a new encounter, or add a
database table.

## 1. Implemented foundation

| Module | Role | Live runtime status |
|---|---|---|
| `monster_catalog_foundation.py` | Stable catalog entries, context references, exact reads, current Battlefield snapshot, E044 boundaries | Candidate-only; not imported by `app.py` |
| `tests/test_e045_monster_catalog_foundation.py` | Deterministic identity/profile/context/authority tests | Test-only |
| This document | Contract, evidence, adoption map, and Owner boundary | Planning/architecture |

The module derives current Battlefield data from the existing F003/F004
registries. It does not copy the current roster into a second active runtime
source:

```text
existing F003 identity registry
  + existing F004 profile registry
  -> E045 explicit candidate catalog/profile references
  -> no application consumer in E045
```

### Catalog entry contract

Every entry has an explicit:

```text
monster_id                 stable exact identity
display_name_key           existing canonical presentation label
family_id                  taxonomy family, not localized text authority
zone_eligibility            explicit machine Zone IDs
encounter_class             NORMAL or BATTLEFIELD_BOSS
context_eligibility         proven context memberships only
context_profile_refs        ADVENTURE_NORMAL / BATTLEFIELD_NORMAL /
                            BATTLEFIELD_BOSS / LORD, each explicit or None
catalog_version             e045.catalog.v1
status                     CANDIDATE_NOT_LIVE
gameplay_variant_ref        None without an approved gameplay mapping
art_content_ref             None; ART002 is not auto-promoted
```

The current entries use `zone_01` through `zone_10`, the existing F003/F004
Battlefield identity IDs. E045 does not guess a conversion to Adventure keys
such as `k26_30`.

### Versioned profile contract

Each current Battlefield profile is represented by an explicit key:

```text
(profile_id, version) -> (max_hp, attack, source_authority)
```

The wrapper version is `e045.profile.v1`; source authority remains
`F004_MONSTER_PROFILE_REGISTRY`. No profile accepts ELO, roster count, Zone
formula, display-name fallback, or “latest profile” resolution.

The exact reads are:

```python
get_monster(monster_id)
get_profile(profile_id, version)
resolve_context_profile(monster_id, context)
list_monsters_for_zone(zone, context)
```

The first two return no result for an exact miss. The context resolver raises a
typed failure for unknown Monster, unknown context, missing context profile,
or missing referenced profile. Zone listing is exact, deterministic, and
never performs random selection.

## 2. Context boundary

| Context | Current catalog membership | Profile behavior |
|---|---|---|
| `ADVENTURE_NORMAL` | Not proven | Explicitly `None`; never inherits Battlefield Normal |
| `BATTLEFIELD_NORMAL` | One current Normal entry per Battlefield Zone | Exact versioned F004 value |
| `BATTLEFIELD_BOSS` | One current Battlefield Boss entry per Battlefield Zone | Exact versioned F004 value |
| `LORD` | No Monster catalog membership proven | Explicitly `None`; no numeric Lord profile |

```text
CONTEXT_PROFILE_REFERENCE_EXPLICIT=YES
PROFILE_REFERENCE_VERSIONED=YES
MISSING_PROFILE_FAIL_CLOSED=YES
UNKNOWN_MONSTER_FAIL_CLOSED=YES
UNKNOWN_PROFILE_FAIL_CLOSED=YES
ADVENTURE_PROFILE_AUTO_INHERITS_BATTLEFIELD=NO
ENCOUNTER_CLASS_EXPLICIT=YES
NORMAL_BOSS_LORD_COLLAPSED=NO
FABRICATED_LORD_NUMERIC_PROFILE=NO
```

The absence of an Adventure or Lord profile is a deliberate guard, not a
placeholder numeric value.

## 3. Exact current Battlefield profile snapshot

The following values are checked against the current server-owned
`origin/master:app.py:_BATTLEFIELD_ROSTER` and F004 registry. E045 introduces
no new balance numbers.

| Zone | Identity | Class | HP | ATK | Profile reference |
|---|---|---|---:|---:|---|
| Z1 | `legacy_bf_01_normal` | Normal | 80 | 2 | `stat_legacy_bf_01_normal@e045.profile.v1` |
| Z1 | `legacy_bf_01_boss` | Battlefield Boss | 100 | 2 | `stat_legacy_bf_01_boss@e045.profile.v1` |
| Z2 | `legacy_bf_02_normal` | Normal | 130 | 3 | `stat_legacy_bf_02_normal@e045.profile.v1` |
| Z2 | `legacy_bf_02_boss` | Battlefield Boss | 160 | 4 | `stat_legacy_bf_02_boss@e045.profile.v1` |
| Z3 | `legacy_bf_03_normal` | Normal | 200 | 4 | `stat_legacy_bf_03_normal@e045.profile.v1` |
| Z3 | `legacy_bf_03_boss` | Battlefield Boss | 240 | 5 | `stat_legacy_bf_03_boss@e045.profile.v1` |
| Z4 | `legacy_bf_04_normal` | Normal | 220 | 5 | `stat_legacy_bf_04_normal@e045.profile.v1` |
| Z4 | `legacy_bf_04_boss` | Battlefield Boss | 260 | 6 | `stat_legacy_bf_04_boss@e045.profile.v1` |
| Z5 | `legacy_bf_05_normal` | Normal | 260 | 6 | `stat_legacy_bf_05_normal@e045.profile.v1` |
| Z5 | `legacy_bf_05_boss` | Battlefield Boss | 290 | 7 | `stat_legacy_bf_05_boss@e045.profile.v1` |
| Z6 | `legacy_bf_06_normal` | Normal | 520 | 12 | `stat_legacy_bf_06_normal@e045.profile.v1` |
| Z6 | `legacy_bf_06_boss` | Battlefield Boss | 700 | 14 | `stat_legacy_bf_06_boss@e045.profile.v1` |
| Z7 | `legacy_bf_07_normal` | Normal | 760 | 16 | `stat_legacy_bf_07_normal@e045.profile.v1` |
| Z7 | `legacy_bf_07_boss` | Battlefield Boss | 920 | 18 | `stat_legacy_bf_07_boss@e045.profile.v1` |
| Z8 | `legacy_bf_08_normal` | Normal | 1100 | 20 | `stat_legacy_bf_08_normal@e045.profile.v1` |
| Z8 | `legacy_bf_08_boss` | Battlefield Boss | 1350 | 22 | `stat_legacy_bf_08_boss@e045.profile.v1` |
| Z9 | `legacy_bf_09_normal` | Normal | 1700 | 28 | `stat_legacy_bf_09_normal@e045.profile.v1` |
| Z9 | `legacy_bf_09_boss` | Battlefield Boss | 2000 | 32 | `stat_legacy_bf_09_boss@e045.profile.v1` |
| Z10 | `legacy_bf_10_normal` | Normal | 2400 | 36 | `stat_legacy_bf_10_normal@e045.profile.v1` |
| Z10 | `legacy_bf_10_boss` | Battlefield Boss | 2800 | 40 | `stat_legacy_bf_10_boss@e045.profile.v1` |

```text
BATTLEFIELD_PROFILE_VALUE_DRIFT=0
CURRENT_BATTLEFIELD_PROFILE_SNAPSHOT=20 exact entries
```

Normal and Battlefield Boss series are each strictly increasing by Zone. The
mixed alternating HP sequence is not strictly non-decreasing at Z3 Boss `240`
to Z4 Normal `220`; E045 preserves that existing fact.

## 4. Preserved E044 boundaries

### Zone/question-stage mapping

E045 records the accepted mapping as evidence-only metadata and does not use it
for Monster identity or stats:

```text
Z1 k26_30  Zone LV1  / question LV1
Z2 k21_25  Zone LV2  / question LV1
Z3 k16_20  Zone LV3  / question LV2
Z4 k11_15  Zone LV4  / question LV3
Z5 k6_10   Zone LV5  / question LV4
Z6 k1_5    Zone LV6  / question LV5
Z7 d1_2    Zone LV7  / question LV7
Z8 d3_4    Zone LV8  / question LV8
Z9 d5_6    Zone LV9  / question LV9
Z10 d7+    Zone LV10 / question LV10
```

```text
ZONE_QUESTION_STAGE_MAPPING_CHANGED=NO
ZONE_QUESTION_STAGE_MAPPING_RUNTIME_CONSUMED=NO
```

### ELO, quantity, F009, and ART002

```text
ELO_MONSTER_STAT_AUTHORITY=NO
ROSTER_COUNT_USED_FOR_HP_ATK=NO
COMMON_RARE_ELITE_ENABLED=NO
COMBAT_CLASS_FREQUENCY_COUPLED=NO
ART002_GAMEPLAY_AUTHORITY=NO
ART002_AUTOPROMOTED_COUNT=0
```

Placement remains limited to start Zone and initial unlock scope. Quantity,
frequency, difficulty, and reward remain separate dimensions. No M001-M120
identifier, artwork path, display name, or array position creates gameplay
identity.

## 5. Future authority migration map

| Current source | Current responsibility | Future adoption action |
|---|---|---|
| `app.py:_BATTLEFIELD_ROSTER` | Current Battlefield sequence and exact legacy values | Keep as source until reviewed cutover; parity tests remain required |
| `monster_identity.py` | Stable Battlefield identity and legacy aliases | Reuse stable IDs; do not infer new IDs from art/text |
| `monster_profiles.py` | F004 Battlefield profile registry and HP/ATK | Become explicit source behind versioned profile refs during later cutover |
| `monster_combat_profiles.py` | Current stat resolution and compatibility | Future consumers adopt profile refs through a reviewed adapter |
| `monster_encounter_selector.py` | F009 candidate identity selection | Consume approved catalog only when separately activated; remains stat/progression agnostic |
| `app.py:_questions_for_adventure_zone` | Books-driven Adventure curriculum selection | Remains curriculum authority, not Monster profile resolution |
| `monster_taxonomy.py` | Question-stage family and encounter labels | Remains taxonomy/presentation metadata, not numeric combat authority |
| `app.py:_adventure_state` | World unlock, clear, stars, progression, Boss readiness | Remains sole World progression authority |
| Adventure Lord routes | Lord identity and Lord Trial behavior | Remains separate from generic catalog/Battlefield Boss |
| ART002 M001-M120 | Art/content baseline | Requires explicit gameplay promotion contract |

No current source is retired by E045. This map is adoption guidance, not a
runtime switch.

## 6. Test contract

The E045 suite covers:

- explicit stable IDs and no ART002 auto-promotion;
- explicit context references and versioned profile identity;
- exact parity with all 20 current Battlefield rows;
- Normal/Battlefield Boss separation;
- Adventure/Lord missing-profile fail-closed behavior;
- unknown Monster/profile and broken reference rejection;
- no generated Zone/ELO/roster-count formula path;
- F009 remains off and frequency is separate;
- exact Z2-Z6 mismatch evidence remains unchanged.

The existing RPG regression suite required alongside it is:

```text
tests/test_monster_identity.py
tests/test_monster_profiles.py
tests/test_monster_encounter_selector.py
tests/test_f008_monster_stat_authority.py
tests/test_f012_world_monster_boundary_contract.py
tests/test_f014_world_battlefield_boss_thin_adapter.py
tests/test_e10_map_authority_and_marker.py
tests/test_adventure_zone_encounter_context.py
```

## 7. Non-goals and result

E045 does not import the catalog from `app.py`, activate F009, map Adventure
Normal to Battlefield Normal, invent Lord stats, create a 120-entry gameplay
roster, consume F032 distribution, change World progression, change question
stage mapping, or change reward/Spirit/Boss/Lord/client/schema/release
behavior.

```text
MONSTER_ID_IS_EXPLICIT=YES
CONTEXT_PROFILE_REFERENCE_EXPLICIT=YES
PROFILE_REFERENCE_VERSIONED=YES
MISSING_PROFILE_FAIL_CLOSED=YES
BATTLEFIELD_PROFILE_VALUE_DRIFT=0
FABRICATED_LORD_NUMERIC_PROFILE=NO
ADVENTURE_PROFILE_AUTO_INHERITS_BATTLEFIELD=NO
ENCOUNTER_CLASS_EXPLICIT=YES
NORMAL_BOSS_LORD_COLLAPSED=NO
COMMON_RARE_ELITE_ENABLED=NO
COMBAT_CLASS_FREQUENCY_COUPLED=NO
ZONE_QUESTION_STAGE_MAPPING_CHANGED=NO
ELO_MONSTER_STAT_AUTHORITY=NO
ROSTER_COUNT_USED_FOR_HP_ATK=NO
ART002_GAMEPLAY_AUTHORITY=NO
ART002_AUTOPROMOTED_COUNT=0
UNKNOWN_MONSTER_FAIL_CLOSED=YES
UNKNOWN_PROFILE_FAIL_CLOSED=YES
NEW_FOUNDATION_RUNTIME_ACTIVE=NO
CURRENT_RUNTIME_AUTHORITY_PRESERVED=YES
APP_PY_CHANGED=NO
RUNTIME_WIRING_CHANGED=NO
SCHEMA_CHANGED=NO
MIGRATION_CHANGED=NO
```

`RESULT=PASS_CANONICAL_MONSTER_CATALOG_AND_VERSIONED_COMBAT_PROFILE_FOUNDATION`

Git publication identity is recorded in the final delivery report because a
commit hash cannot self-reference the commit that contains this document.
