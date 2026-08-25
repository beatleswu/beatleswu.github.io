# F013 — Battlefield Boss Runtime Adapter and Settlement Lineage Recon

## Status and scope

This is a read-only current-master reconciliation. It does not implement the
World-to-Monster flow, import the accepted F012 module, enable F010, activate
F007, change combat, add schema, or mutate Production.

| Field | Result |
|---|---|
| Repository | `D:\go-website` |
| Recon worktree | `D:\go-website-f013-battlefield-boss-recon` |
| Branch | `codex/f013-battlefield-boss-runtime-recon` |
| Current `origin/master` | `b75308d44806bb7c2e2b131a73ba06a71c188b3c` |
| Accepted F012-R1 reference | `91701324d57649c1f1376f09fbb8c44114b96a73` |
| F012-R1 merged into current master | No |
| F007 runtime activation | No |

The F012-R1 object was inspected as a reference only. Current master has no
`world_monster_boundary_contract.py`, F012 test, or F012 planning artifact, so
no F012 runtime code was copied into this candidate.

## A. Executive conclusion

The current master has the pieces needed for a narrow future adapter, but not
the complete Battlefield Boss milestone flow.

1. F009/F010 already expose a server-only `BATTLEFIELD_BOSS` intent at the
   pure selector and durable selector-service boundary. The live `app.py`
   Map Battle creation path currently calls the durable service with
   `encounter_intent='REGULAR'` only and supplies no World eligibility intent.
2. Therefore the F012 intent is **thin-adapter compatible**, not directly
   live-compatible. A future World adapter must validate F012, map its
   server-owned operation and canonical Zone, and set the F010
   `battlefield_boss_authorized=True` boundary marker. The selector must not
   decide eligibility.
3. Canonical Monster identity is resolved by
   `monster_identity.resolve_monster_identity`; combat definition/profile is
   then resolved by `monster_combat_profiles.resolve_monster_combat_profile`.
   The selector does not own HP/ATK.
4. A committed defeat is represented by the existing F006
   `monster_settlement.settle_monster_defeat` event/outbox path, called from
   `app._settle_monster_defeat_in_tx`, after the server-owned HP transition
   has reached `hp_before > 0` and `hp_after == 0`.
5. `settlement_id` exists, but it is caller-supplied and is not proven
   globally unique. D5A uniqueness is explicitly scoped by
   `(player_id, event_type, idempotency_key)`. For the fixed
   `MONSTER_DEFEATED` event type, the safe current scope is per user. The
   accepted F012-R1 composite `(user_id, settlement_id)` is therefore the
   correct V1 World consumer key for this current lineage.
6. The current settlement event has a trustworthy server-bound `zone_id`,
   but not the F012 field `zone_key` by that name and not a uniform
   `encounter_operation_id`. A future adapter must normalize the Zone field
   and bind the encounter operation from the authoritative encounter/battle
   record; it must never infer either from a selected UI label.
7. Current Adventure/Lord progression is independent. `_adventure_state`
   computes Lord readiness from unlocked state, distinct correct progress at
   30%, clear state, and cooldown. It does not consume `MONSTER_DEFEATED`.
   Lord Trial finish owns the conditional first-clear transition, Star 1, and
   first-clear reward; ordered Adventure state projects subsequent Zone
   unlocks. Battlefield Boss defeat currently does not make Lord ready.

## B. Answers to the required questions

| Question | Current-master answer | Evidence / boundary |
|---|---|---|
| A. F010 Boss intent seam | **Yes at service level; no live World seam** | `select_monster_encounter` accepts `BATTLEFIELD_BOSS`; `select_durable_monster_encounter` persists the intent. `app.py` creates only `REGULAR` selection. |
| B. Thinnest future World adapter | `BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1` adapter -> `monster_encounter_selector_runtime.select_durable_monster_encounter` | Map F012 `zone_key` to F010 canonical selector key, use the server intent operation ID, pass the server-only authorization marker, then resolve the selected ID through F008. |
| C. Boss identity resolver | F009 selector selects the one server catalog Boss; F004/F003 identity/profile registries validate and resolve it | `monster_encounter_selector.py` requires exactly one Boss for the authoritative Zone; `resolve_monster_combat_profile` then binds the profile. |
| D. Committed defeat representative | `monster_settlement.settle_monster_defeat` plus its durable `MONSTER_DEFEATED` outbox row | The app wrapper builds the event from the server HP boundary and delegates to F006. |
| E. Stable settlement identifier | Yes, `MonsterDefeatedEvent.settlement_id` and outbox idempotency key | It is not a server-generated globally unique settlement primitive. |
| F. Settlement ID uniqueness scope | `PER_USER` for the current `MONSTER_DEFEATED` lineage | D5A unique contract is `(player_id,event_type,idempotency_key)`; the Monster key is derived from `settlement_id`. Global uniqueness is unproven. |
| G. F012 composite dedupe | **Yes for the current fixed event type and server-bound user** | `(user_id, settlement_id)` matches the current D5A lookup/unique scope and rejects cross-user collisions. It is not a claim of global settlement-ID uniqueness. |
| H. New Monster operation table | **No** | F010 already has `monster_encounter_selection_operation`; F013 does not need another Monster table. F012 intent evidence/eligibility reference is not currently a field in that table. |
| I. New World milestone table | **Conditional, future policy/storage task** | A World projection is recommended if Boss milestone consumption becomes an owned durable World state. F013 does not create it. |
| J. No-schema history read | **Partial** | `domain_event_outbox` can retain/query `MONSTER_DEFEATED` payloads containing user, `zone_id`, Monster, class, and settlement ID. Current master has no F012 fact consumer, no uniform operation ID in the Monster event, and no World milestone projection. |

## C. Current runtime topology

### C1. Regular Map Battle path, flag off

The current default path is still the legacy compatibility path:

```text
validated Map Battle question / Zone context
  -> F008 resolver with explicit Map Battle compatibility overrides
  -> Map Battle battle state
  -> Map Battle server judge and battle-revision settlement
  -> no F010 selector-state mutation
```

`monster_selector_v1_enabled` is fail-closed and defaults to false. When the
flag is off, `app.py` calls `_map_battle_monster_hp`, which uses the F008
resolver and the governed legacy fallback rather than creating an F010
selection operation.

### C2. Regular Map Battle path, flag on in local/test only

```text
server-authenticated user + validated Map Battle Zone
  -> canonical_selector_zone_key
  -> new_server_encounter_operation_id
  -> select_durable_monster_encounter(..., encounter_intent=REGULAR)
  -> resolve_monster_combat_profile({monster_id})
  -> create_map_battle(battle_id=encounter_operation_id)
  -> map_battle_runtime.settle_answer
  -> settle_map_battle_submission
```

The F010 operation row is keyed by `(user_id, zone_key,
encounter_operation_id)`. The durable selector state row is keyed by
`(user_id, zone_key)`. A replay returns the stored identity and does not
advance the selector cursor. The feature remains default-off and F007's
100-row candidate catalog is not imported.

The current live integration supplies `REGULAR` only (`app.py:13521-13570`).
There is no World-produced F012 intent, no Boss eligibility check, and no
live call with `encounter_intent=BATTLEFIELD_BOSS` in `app.py`.

### C3. Future Boss intent adapter target

The smallest future adapter shape is conceptually:

```python
intent = validate_f012_battlefield_boss_intent(payload)

selector_zone = canonical_selector_zone_key(intent.zone_key)
selection = select_durable_monster_encounter(
    conn,
    user_id=intent.user_id,
    zone_key=selector_zone,
    encounter_operation_id=intent.intent_operation_id,
    candidates=server_owned_catalog,
    encounter_intent="BATTLEFIELD_BOSS",
    battlefield_boss_authorized=True,
)
profile = resolve_monster_combat_profile(
    selection.selection.f008_profile_input,
    context="MAP_BATTLE",
)
```

The `True` marker is not a client field and must be set only after the World
adapter has accepted `eligibility_authority=WORLD_PROGRESSION`. The adapter
must retain or forward `eligibility_reference` in its World-owned evidence;
the current F010 operation schema does not store that F012 field. `replayed`
is delivery metadata; F010 replay is determined by the same server-owned
`(user, zone, operation)` key.

| F012 intent field | Current F010 target | Compatibility |
|---|---|---|
| `user_id` | `select_durable_monster_encounter.user_id` | Direct |
| `zone_key` | `canonical_selector_zone_key` -> F010 `zone_key` | Thin vocabulary adapter |
| `intent_operation_id` | `encounter_operation_id` | Direct identity role |
| `encounter_class=BATTLEFIELD_BOSS` | `encounter_intent="BATTLEFIELD_BOSS"` | Direct enum mapping |
| `eligibility_authority` | `battlefield_boss_authorized=True` only after validation | Thin authority adapter |
| `eligibility_reference` | Not a current F010 operation field | Missing persistence field at this seam; keep World-owned |
| `requested_at` | No selector-policy meaning | Adapter audit/delivery metadata only |
| `replayed` | F010 stored-operation replay result | Adapter maps to replay response |

Result: `F010_BOSS_INTENT_SEAM=THIN_ADAPTER_REQUIRED`. This is a narrow
adapter gap, not a need for a second selector or a new combat engine.

## D. Selector authority audit

The selector source matrix is:

| Source | Current role | Relevant behavior |
|---|---|---|
| `monster_encounter_selector.select_monster_encounter` | Canonical pure selector | Zone-local catalog, explicit intent, no immediate repeat, unseen cycle, family preference, deterministic weighting. |
| `monster_encounter_selector_runtime.select_durable_monster_encounter` | Canonical durable selector service | Locks user+Zone state, replays an operation, calls the pure selector, records before/after cursor state. Caller owns the transaction. |
| `migrations/monster_encounter_selector_state_v1.py` | Additive candidate schema | State PK `(user_id,zone_key)`; operation PK `(user_id,zone_key,encounter_operation_id)`; no F012 import. |
| `app.py` F010 Map Battle branch | Default-off runtime adapter | Only `REGULAR`; creates a server operation ID and resolves F008 profile. |
| `app.py` legacy `_BATTLEFIELD_ROSTER` / `next_roster_entry` | Legacy compatibility selector | Daily `battlefield_monster` row and sequential roster rotation; not World milestone eligibility. |
| Question `monster_*` fields | Legacy identity/stat compatibility input | Server-loaded and routed through F003/F008; not a client Boss-authority path. |
| Client request fields | Non-authoritative | Map Battle runtime rejects/ignores forged identity/stat/result authority fields. |

The pure selector explicitly rejects Lord identities, excludes Battlefield Boss
from the regular pool, and requires `battlefield_boss_authorized=True` for the
Boss intent. The durable runtime preserves this policy and intentionally does
not put a Boss in the regular unseen cycle.

## E. Identity and profile resolution

The current identity chain is:

```text
server-owned roster / F010 selected monster_id
  -> monster_identity.resolve_monster_identity
  -> CanonicalMonsterIdentity
  -> monster_profiles.get_monster_profile
  -> monster_combat_profiles.resolve_monster_combat_profile
  -> immutable MonsterCombatProfile
```

`CanonicalMonsterIdentity` currently exposes `monster_id`, `zone_id`,
`roster_slot`, `encounter_class`, and family. The current legacy roster has
20 entries (`legacy_bf_01_normal` through `legacy_bf_10_boss`), with the
roster index/slot server-bound. Localized display names and art keys are not
standalone identity authority.

The F008 profile resolver is the one combat-definition boundary. It supplies
`max_hp`, `attack`, `encounter_class`, profile provenance, and compatibility
metadata. It does not mutate current HP. Current HP remains owned by the
legacy Battlefield or Map Battle settlement state.

## F. Combat and committed-defeat topology

### F1. Legacy Battlefield

The current legacy path is:

```text
server review operation
  -> _get_or_create_battlefield(user, bf_date)
  -> canonical roster-slot identity
  -> F008 Monster profile
  -> grade/correctness combat math and HP transition
  -> current_hp == 0 / monster_defeated
  -> battlefield row update and next_roster_entry compatibility rotation
  -> _settle_monster_defeat_in_tx
  -> build_monster_defeated_event
  -> settle_monster_defeat
  -> D5A MONSTER_DEFEATED outbox + supported item lineage
```

The existing roster row is stored in `battlefield_monster` with `user_id` and
`bf_date`; the `monster_idx` is the server-owned identity binding. Defeat is
not a World Zone-clear write.

### F2. Map Battle

Map Battle owns its own authoritative state transition:

```text
server SGF judge
  -> map_battle_runtime.calculate_combat_effects
  -> map_battle_persistence.settle_map_battle_submission
  -> row-locked battle revision and monster_hp_before/after
  -> battle state COMPLETED when monster HP reaches zero
  -> internal SRS/review progression handoff
  -> _settle_monster_defeat_in_tx for the shared Monster drop/lineage tail
```

`map_battle_submissions` stores the authoritative HP before/after and
settlement state. A settled submission is replayed from its stored row and
does not rerun the judge or mutate battle state.

The important F013 gap is binding continuity: when the F010 feature is on,
Map Battle combat resolves the selected F010 operation through
`_map_battle_f010_profile`, but the later shared Monster lineage call receives
server-loaded `q_info` and constructs its event from that input. The current
Monster event has no `encounter_operation_id` field that explicitly links the
F010 battle binding. For a future Boss fact, the adapter must require that the
selected operation, active Monster identity, Zone, and settlement submission
all agree before emitting F012.

### F3. Authoritative settlement function

The exact current generic Monster settlement authority is:

```text
app._settle_monster_defeat_in_tx
  -> monster_settlement.build_monster_defeated_event
  -> monster_settlement.settle_monster_defeat
```

`build_monster_defeated_event` accepts a defeat only when the server-provided
transition is `hp_before > 0` and `hp_after == 0`. It binds `user_id`,
`monster_id`, `zone_id`, roster slot, class, family, and the settlement ID.
`settle_monster_defeat` resolves F004/F005 profiles, appends one
`MONSTER_DEFEATED` event, stores the rolled result in the payload, and replays
the original event on the same idempotency key.

The caller owns the surrounding transaction. The truthful F012 emission
point is therefore **after the transaction containing the Monster outbox row
has committed**, or through a future consumer of that committed outbox row.
The pre-commit `MonsterSettlementResult` is not by itself a committed fact.

## G. Settlement identity and D5A lineage

### G1. Current fields and construction

| Field | Current evidence | Meaning |
|---|---|---|
| `MonsterDefeatedEvent.settlement_id` | `monster_settlement.py:50-60` | Required non-empty caller-supplied logical settlement identity. |
| D5A `idempotency_key` | `_event_key` -> `monster-defeated:<settlement_id>` | Lookup and unique-conflict key for `MONSTER_DEFEATED`. |
| D5A `player_id` | `event.user_id` | User scope used by `get_event_by_idempotency_key` and schema uniqueness. |
| D5A `event_id` | Server-generated UUID in `event_outbox.append_event` | Durable event row primary key; not used as the settlement ID. |
| `source_event_id` | Current settlement ID for the Monster event; D5A event ID for item acquisition | Lineage reference, not a global settlement constraint. |
| `lineage_id` | `monster-settlement:<settlement_id>` | Human/lineage grouping, not a unique global settlement primitive. |

Current callers include:

- legacy review: `review:<submission_id>`;
- Map Battle: `map-battle:<submission_id>`;
- fallback legacy review: `legacy-review:<uid>:<date>:<qid>:<kill_count>`.

These construction paths demonstrate why a global uniqueness claim would be
unsafe. The D5A schema's unique contract is exactly
`(player_id, event_type, idempotency_key)`, and current replay lookup uses all
three values. Consequently:

```text
SETTLEMENT_ID_GLOBAL_UNIQUENESS_PROVEN = NO
SETTLEMENT_ID_SCOPE = PER_USER
F012 V1 consumer dedupe = (user_id, settlement_id)
```

F012-R1's accepted replay rule correctly rejects a changed user or changed
settlement ID, while allowing delivery-only changes such as `occurred_at` and
`replayed`. A future simplification to bare `settlement_id` requires a
separate proof that every Monster settlement path generates globally unique
IDs.

### G2. Existing D5A history

`domain_event_outbox` already provides durable evidence for a committed
`MONSTER_DEFEATED` row and supported `ITEM_ACQUISITION` lineage. Its Monster
payload includes `settlement_id`, `monster_id`, `zone_id`, roster slot,
`encounter_class`, HP boundary, drop/reward profile references, and the stored
drop result. It is therefore a useful history source, but it is not yet a
World milestone projection and it does not contain a uniform
`encounter_operation_id`.

`D5C` is not involved in Monster acquisition; no D5C boundary is added here.

## H. Zone binding

`SETTLEMENT_ZONE_KEY_AVAILABLE=YES`, with an adapter caveat:

- the current Monster event field is named `zone_id`, not F012's `zone_key`;
- for legacy Battlefield it comes from the canonical server roster identity;
- for Map Battle, the authoritative battle row has its own `zone_key`, while
  the shared Monster lineage adapter currently reconstructs identity from
  server-loaded question data;
- the future adapter must normalize and cross-check these sources, not derive
  a Zone from `selected_stage_key`, display text, or the client request.

The smallest safe future change is an adapter input contract that carries the
already-authoritative encounter operation/battle binding and its Zone into the
F012 fact construction. It should fail closed on mismatch. F013 does not
change `MonsterDefeatedEvent` or any schema.

## I. Battlefield Boss, Lord, Quest, and World boundaries

### I1. Battlefield Boss eligibility

Current legacy Battlefield has a persisted daily roster cursor/row and
sequential `next_roster_entry`; this is a Monster/legacy presentation and
encounter path, not World milestone eligibility. Current master has no World
writer that authorizes a Battlefield Boss milestone encounter.

Recommended future ownership remains:

```text
World/Progression decides eligibility
  -> F012 BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1
  -> F010 resolves the explicit Boss identity
```

The F010 selector must not calculate eligibility. `BATTLEFIELD_BOSS` remains a
generic Monster encounter class and is not a Lord.

### I2. Lord readiness and Lord Trial

Current `_adventure_state` reads `review_log`, `srs_cards`,
`adventure_boss_progress`, and `adventure_zone_unlocks`. For each Zone it
computes:

```text
unlocked
+ distinct historical correct progress >= BOSS_UNLOCK_PCT (30)
+ not adventure_boss_progress.cleared
+ cooldown_left == 0
```

The current `boss_ready` value is this Lord Trial readiness projection. It
does not query Monster settlement history and does not require a Battlefield
Boss defeat.

`/api/adventure/boss/start` validates the server-derived Zone state and starts
the signed exam. `/api/adventure/boss/finish` recomputes the result from
server review evidence and calls `_adventure_boss_record_attempt`. The
conditional `cleared=0` transition in `adventure_boss_progress` is the first
clear winner; replay is derived from the already-cleared row. A first clear
sets Star 1 and grants the existing first-clear reward in the same database
transaction. Lord Trial is therefore separate from generic Monster combat.

### I3. Stars and next Zone

Current Star projection is in `_adventure_state` / `_adventure_progress_payload`:

- cleared -> at least Star 1;
- distinct correct progress >= 60% -> at least Star 2;
- all Zone questions historically defeated/correct -> Star 3;
- stored `adventure_boss_progress.stars` is retained with `max` semantics.

Next-zone availability is the ordered Adventure projection: the next Zone is
unlocked through `previous_cleared`, unless placement has already inserted an
`adventure_zone_unlocks` row. A generic Monster defeat does not write this
state, and a Battlefield Boss defeat is not currently an input.

`selected_stage_key` is presentation/action context. `_adventure_map_state_from_zones`
computes it separately from `_adventure_current_zone_key`, which derives the
server-owned progression node from placement and durable Zone clear/progress
state. The invariant remains:

```text
selectedZone != progressionZone
```

### I4. Quest and Spirit

Quest may observe the `MONSTER_DEFEATED` seam, but current Quest progress
helpers do not own `adventure_boss_progress`, Star, or Zone unlock writes.
Lord Trial review explicitly excludes the ordinary Monster Spirit adapter.
No F013 change is made to Quest, Spirit, combat, or World policy.

## J. Current versus recommended event flow

### Current flow

```text
Map Battle / legacy review
  -> server judge or server-owned grade path
  -> F008 profile / existing combat state
  -> HP transition
  -> Map Battle submission settlement or legacy battlefield update
  -> shared F006 Monster settlement
  -> committed D5A MONSTER_DEFEATED event
  -> optional Quest observation / review projection

Adventure World state
  -> reads review/SRS and adventure_boss_progress
  -> computes Lord readiness
  -> Lord Trial start/finish
  -> adventure_boss_progress.cleared / stars
  -> ordered next-zone projection
```

There is no current arrow from `MONSTER_DEFEATED` to `boss_ready`, no current
F012 fact emission, and no current Battlefield Boss milestone World consumer.

### Recommended target, pending Owner policy

```text
World/Progression eligibility policy
  -> BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1
  -> thin F010 adapter with explicit Boss intent
  -> F010 durable encounter binding
  -> F008 Monster identity/profile/stat resolution
  -> canonical combat settlement
  -> committed Monster HP defeat transition
  -> D5A MONSTER_DEFEATED lineage
  -> BATTLEFIELD_BOSS_DEFEATED_FACT_V1
  -> future World consumer evaluates (but does not blindly mutate) policy
  -> Lord Trial authority
  -> first authoritative Lord clear
  -> existing Star / next-zone World projection
```

The target flow does not decide whether a Boss defeat changes the existing
30% Lord readiness rule. That remains an Owner/Product decision.

## K. World milestone storage options

| Option | Idempotency | Auditability | Query cost | Replay/rollback | Schema | Finding |
|---|---|---|---|---|---|---|
| A. Reuse committed Monster history | Good if keyed by `(user,settlement)` and fixed event type | Good lineage, but World consumption state is implicit | Repeated filtered outbox reads | Safe read-only replay; no consumed projection | No new schema | Useful for reconciliation and bootstrap, not ideal as the long-term World state. |
| B. Add World consumed-milestone projection | Strong user+Zone+source/settlement idempotency | Explicit World decision and audit boundary | Low steady-state read cost | Conditional first-write / replay-safe projection | Additive future schema likely | **Recommended** once the Owner approves Boss defeat as a World input. |
| C. Derive dynamically on every read | Depends on event history scans | Weak policy-consumption audit | Highest and potentially unbounded | Harder to distinguish consumed versus merely observed | No new schema | Not recommended as the final World authority. |

Recommendation: `ADD_WORLD_MILESTONE_PROJECTION`, but
`NEW_WORLD_SCHEMA_REQUIRED=CONDITIONAL`. F013 does not create a table or
choose the policy. Existing D5A history can support a migration/bootstrap
read, while the projection gives World a durable, user+Zone-scoped consumed
fact once the product rule is locked.

## L. Static validation and test evidence

Focused tests were run against the unchanged current-master runtime with
`PYTHONPATH=.`:

| Suite | Result |
|---|---:|
| `tests/test_monster_encounter_selector.py` + `tests/test_f010_monster_selector_runtime.py` | 27 passed |
| `tests/test_monster_settlement.py` + `tests/test_domain_event_outbox_foundation.py` | 20 passed, 1 skipped |
| `tests/test_map_battle_runtime.py` + `tests/test_map_battle_persistence.py` | 37 passed |
| `tests/test_f008_monster_stat_authority.py` + three Adventure authority suites | 72 passed |

Static/source checks:

- regular selector excludes `BATTLEFIELD_BOSS` and rejects Lord identities;
- Boss selection requires explicit server-only authorization;
- F010 feature flag is default-off;
- current `app.py` F010 runtime branch passes `REGULAR` only;
- no current-master F012 module or F012 artifact is present;
- F010 selector/runtime has no imports or writes to Adventure World state;
- Monster settlement has no World, Lord, or Quest progression writer;
- Map Battle settlement identity is owner-bound and replay-safe;
- no F007 100-row catalog is imported or activated.

No task code was changed while running these checks. No PostgreSQL migration
or Production database was used by F013.

## M. Required future adapter invariants

Before runtime implementation, the future adapter should fail closed unless
all of the following agree:

1. F012 intent user and Zone are server-authenticated.
2. intent operation ID is stable and replayed through F010's operation key.
3. F010-selected `monster_id` resolves through F004/F008.
4. active encounter/battle Zone equals the F012 Zone after vocabulary
   normalization.
5. the settlement user equals the encounter user.
6. HP before/after proves a committed defeat.
7. the settlement is committed before F012 fact delivery.
8. the fact class is exactly `BATTLEFIELD_BOSS`, never `LORD`.
9. dedupe uses `(user_id, settlement_id)` for F012 V1.
10. fact delivery does not directly write `boss_ready`, `cleared`, `stars`, or
    next-zone state.

## N. Final classification

`F010_BOSS_INTENT_SEAM=THIN_ADAPTER_REQUIRED`

The current architecture is sufficiently composed for a narrow contract
adapter, but it is not yet a complete runtime Battlefield Boss milestone
flow. The remaining gaps are explicit encounter-operation/settlement
binding, F012 fact emission after commit, and a future World-owned milestone
consumption projection. None requires a second Monster selector, a second
combat engine, or a change to current Lord policy.
