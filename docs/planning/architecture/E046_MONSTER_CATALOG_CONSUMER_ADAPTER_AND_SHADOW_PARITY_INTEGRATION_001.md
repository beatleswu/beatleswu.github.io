# E046 Monster Catalog Consumer Adapter and Shadow Parity Integration

Status: candidate-only shadow integration.  This document records the
consumer inventory, the adapter boundary, and deterministic parity evidence;
it does not authorize a gameplay cutover.

## Provenance and scope

- Fresh base: `origin/master` at `6829c4c528adf4800326e90534585a32e390ebec`.
- E045 foundation carried into this candidate: `ceec80e2fe1793198cf04ea8f8cb781a43eeea5b`.
- E044 Owner decisions remain governance authority; E044 does not need to be
  merged for this shadow layer.
- `app.py`, routes, response payloads, selection, rewards, progression,
  question mapping, F009 activation, ART002, and F034 planning data are not
  changed or consumed as new gameplay authority.

The current active chain remains F003 identity, F004 Battlefield profiles,
F008 stat resolution, the existing Battlefield resolver/settlement paths, and
World/Adventure progression.  E046 only compares an already resolved runtime
tuple with E045.

## Current Monster consumer matrix

| Consumer | Identity source | Stat source | Encounter class source | Active runtime authority | E045 adapter target | Safe for shadow | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Battlefield normal encounter/settlement (`app.py:_BATTLEFIELD_ROSTER`, `_update_monster_and_quests`) | F003 `canonical_battlefield_identity` and server-owned roster slot | F004 through F008, with existing persisted-state compatibility | Server-owned roster kind plus F003 | Yes: existing combat/settlement path | Compare explicit `monster_id` or F003 `roster_slot`, `current_hp`, `current_atk` in `BATTLEFIELD_NORMAL` | Yes | Adapter does not select, correct, settle, or write. |
| Battlefield Boss encounter/settlement (`app.py` Battlefield branches) | F003 identity bound to the server-owned roster | F004 through F008 | Server-owned roster kind plus F003 `BATTLEFIELD_BOSS` | Yes: existing Boss combat/settlement path | Same explicit tuple in `BATTLEFIELD_BOSS` | Yes | Boss remains distinct from normal and Lord. |
| Battlefield status initialization (`app.py:/api/monster/status`) | Persisted Battlefield row validated by F003 | F008 `resolve_monster_combat_profile` with legacy persisted-HP compatibility | F008/F003 | Yes: response authority remains existing route | Observe the returned canonical ID/profile tuple only | Yes | No E046 import or response mutation. |
| Map Battle legacy/F010 (`app.py:_map_battle_monster_hp`, `map_battle_runtime.py`) | Existing server question/persisted binding; F010 selector is default-off | F008, including the existing Map Battle compatibility fallback | Existing Map Battle route/selector contract | Yes: existing Map Battle contract | Deferred context adapter; never infer a Battlefield profile from a Map Battle question | Yes, no-profile/firewall only | E046 does not add a `MAP_BATTLE` profile context. |
| F009 selector (`monster_encounter_selector.py`) | Server-owned durable selected `monster_id` when explicitly enabled | F008 after selection | Selector candidate class; Boss eligibility remains caller-owned | Default-off; not activated by E046 | Compare selected ID after server selection, without consuming rarity as stats | Yes | `MONSTER_SELECTOR_LIVE_ACTIVATED` remains false. |
| Adventure normal/question flow (`app.py:_questions_for_adventure_zone`) | Adventure curriculum/question taxonomy and World state | No E045 Adventure numeric profile | Adventure/World state | Yes: existing Adventure/question authority | Return typed `NO_EXPLICIT_ADVENTURE_PROFILE` when observed | Yes | No Battlefield stat inheritance. |
| World/Adventure progression (`app.py:_adventure_state`, `_adventure_state_cached`) | World persistence and progression state | Not a Monster stat consumer | World progression state | Yes: World authority | No progression call; adapter is read-only | Yes | E046 cannot unlock/relock or move selected/progression Zone. |
| Lord Trial (`app.py:adventure_boss_start`, `adventure_boss_finish`) | Lord/Adventure metadata and server verdict | No numeric Lord profile | Lord route | Yes: Lord/World authority | Return `EXPLICIT_LORD_NO_NUMERIC_PROFILE` | Yes | E046 creates no Lord HP, ATK, tier, or Boss-derived profile. |
| Existing identity/profile test suites | F003/F004 test fixtures | F004/F008 test fixtures | Test-owned explicit class | Tests only | Adapter contract/parity fixtures | Yes | Tests prove the firewall; they do not activate runtime wiring. |

### Authority migration map

| Current authority | E046 relationship | Future migration action |
| --- | --- | --- |
| F003 stable Battlefield identity | Read-only identity bridge | A future Battlefield consumer may adopt the explicit catalog ID after separate cutover review. |
| F004 Battlefield profile registry | Read-only versioned parity target | Keep F004 authoritative until a separately approved profile migration. |
| F008 combat resolver | Remains active resolver | A future adapter caller must preserve F008 compatibility and error boundaries. |
| World/Adventure progression and curriculum | Never replaced | No Monster-catalog migration may own Zone unlocks, selected Zone, progression Zone, or question selection. |
| F009 selector | Default-off identity candidate only | Revisit only with an explicit feature-enable and durable-authority task. |
| Lord Trial | Explicit no-profile boundary | Requires separate numeric authority decision before any numeric profile adoption. |

## Shadow adapter contract

`monster_catalog_shadow_adapter.py` exposes:

- `compare_runtime_encounter(runtime, context=...)` for one explicit runtime
  tuple;
- `compare_runtime_encounters(...)` for deterministic batches; and
- `ShadowComparison.as_contract()` with the required current/foundation
  identity, context, HP, ATK, profile version, and `PARITY` fields.

Accepted identity inputs are only an explicit E045 `monster_id` or the
server-owned F003 `roster_slot`.  `monster_idx`, display name, localized text,
art filename, image path, roster count, ELO, and array order cannot select a
catalog entry.  A mismatch is reported as `MISMATCH`; the adapter never
replaces the current value.  Unknown identity/profile and broken explicit
references fail closed.

The supported context reference is explicit:

`ADVENTURE_NORMAL`, `BATTLEFIELD_NORMAL`, `BATTLEFIELD_BOSS`, or `LORD`.

E045 profile references are versioned.  Adventure and Lord missing references
are reported as `NOT_APPLICABLE`, with no numeric fallback.  The Lord result is
specifically `EXPLICIT_LORD_NO_NUMERIC_PROFILE`.

## Parity evidence

The E045 snapshot remains sourced from the current F004 registry and is tested
against the current server-owned `_BATTLEFIELD_ROSTER`:

| Context | Zones covered | HP | ATK | Drift |
| --- | ---: | --- | --- | ---: |
| Battlefield normal | 10 | 80, 130, 200, 220, 260, 520, 760, 1100, 1700, 2400 | 2, 3, 4, 5, 6, 12, 16, 20, 28, 36 | 0 |
| Battlefield Boss | 10 | 100, 160, 240, 260, 290, 700, 920, 1350, 2000, 2800 | 2, 4, 5, 6, 7, 14, 18, 22, 32, 40 | 0 |

The tests also prove that:

- normal and Battlefield Boss references do not cross-resolve;
- Adventure does not auto-inherit Battlefield values;
- Lord has no fabricated numeric profile;
- a broken profile reference raises `UnknownProfileError`;
- a runtime mismatch stays a mismatch rather than being corrected;
- the current Z2-Z6 question-stage mismatch remains unchanged;
- F009 remains off and no rarity/frequency policy becomes stat authority; and
- `app.py` has no E046 import, so active gameplay output is unchanged.

## Shadow coverage and adoption readiness

- Shadow consumer groups invoked by the deterministic suite: 4 (normal batch,
  Boss batch, Adventure no-profile, Lord no-profile).
- Normal Zones evaluated: 10.
- Boss Zones evaluated: 10.
- Lord cases: 1 explicit no-profile case.
- Adventure cases: 2 (known identity and missing identity), both no-profile.

Readiness: `READY_FOR_LIMITED_SHADOW_CALLER_INTEGRATION`.

The next safe caller is a non-player-visible Battlefield parity diagnostic or
test harness that receives the already server-resolved F003/F004/F008 tuple.
No route or settlement caller should be migrated in E046.  Adventure and Lord
remain blocked from profile adoption until their own explicit authority is
approved; F009 remains a separate default-off enablement decision.

## Non-goals and release boundary

No app.py write, runtime wiring, schema/migration, ART002/F034 gameplay use,
B057 scope change, Production query/mutation, deploy, feature enablement, or
master merge is part of E046.  There is no player-visible output or telemetry
from the adapter.
