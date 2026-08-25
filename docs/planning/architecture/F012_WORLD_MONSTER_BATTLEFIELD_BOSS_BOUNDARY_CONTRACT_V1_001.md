# F012 World / Monster Battlefield Boss Boundary Contract V1

Status: pure contract implementation, focused tests, and documentation.

## 1. Scope and provenance

| Field | Value |
|---|---|
| Task | `F012_WORLD_MONSTER_BATTLEFIELD_BOSS_BOUNDARY_CONTRACT_V1_001` |
| Parent reference | F011 accepted exact SHA `4ed81b717f751f899410a44871f5126c352b0127` |
| Current origin/master | `58d9b7047f285751a048fc551c955909c87984ac` |
| Branch | `codex/f012-world-monster-battlefield-boss-boundary-v1` |
| Contract module | `world_monster_boundary_contract.py` |
| Runtime wiring | `NO` |
| F007 activation | `NO` |
| Schema / migration | `NO` |

F012 does not import or assume that F009/F010/F011 are merged into
`origin/master`. The module is intentionally independent of the application
runtime and is suitable for a later adapter at the World and Monster seams.

## 2. Boundary purpose

F012 transports exactly two meanings:

```text
World/Progression
  -> BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1

committed Monster settlement
  -> BATTLEFIELD_BOSS_DEFEATED_FACT_V1
```

The contract does not decide World policy, select a Monster, calculate combat,
grant rewards, or mutate persistence.

The locked boundaries remain:

```text
BATTLEFIELD_BOSS != LORD
Monster defeated != Zone clear
Quest complete != World unlock
selectedZone != progressionZone
```

## 3. Contract A: World encounter intent

Contract version:

```text
BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1
```

### Required fields

| Field | Contract rule |
|---|---|
| `contract_version` | Exact `BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1`. |
| `user_id` | Positive server user identifier. |
| `zone_key` | Non-empty Zone machine key. The intent does not unlock or choose the Zone. |
| `intent_operation_id` | Non-empty server-owned logical intent operation ID. |
| `encounter_class` | Exactly `BATTLEFIELD_BOSS`. `LORD` and regular classes are rejected. |
| `eligibility_authority` | Exactly `WORLD_PROGRESSION`. |
| `eligibility_reference` | Non-empty World-side reference to the authorization decision. |
| `requested_at` | Non-empty event timestamp/string; delivery metadata, not policy. |
| `replayed` | Boolean delivery marker. It does not change intent meaning. |
| `metadata` | Bounded JSON-safe object with no authoritative stat/reward/World-policy keys. |

The intent means only:

> World has authorized creation/resolution of one Battlefield Boss milestone
> encounter.

It does not mean that the Monster has been selected or defeated, that Lord
readiness is true, or that any World progression has occurred.

### Intent replay

The logical key is:

```text
(user_id, intent_operation_id)
```

`assert_intent_replay_compatible(original, replay)` allows delivery metadata
(`requested_at`, `replayed`) to differ, but compares the contract version,
user, Zone, operation ID, class, World authority, eligibility reference, and
metadata. A changed authoritative payload raises
`BoundaryReplayMismatchError`; it is never silently accepted.

F012 does not create an operation table. A future adapter may persist the
intent using its existing server-owned operation/idempotency authority.

## 4. Contract B: Monster defeated fact

Contract version:

```text
BATTLEFIELD_BOSS_DEFEATED_FACT_V1
```

### Required fields

| Field | Contract rule |
|---|---|
| `contract_version` | Exact `BATTLEFIELD_BOSS_DEFEATED_FACT_V1`. |
| `user_id` | Positive server user identifier. |
| `zone_key` | Non-empty server-bound Zone key. |
| `monster_id` | Non-empty canonical Monster identity. |
| `encounter_class` | Exactly `BATTLEFIELD_BOSS`. Lord is rejected. |
| `encounter_operation_id` | Non-empty server encounter operation ID. |
| `settlement_id` | Non-empty stable server settlement identifier. Future World dedupe should use this identity. |
| `defeated` | Exactly boolean `true`. |
| `source_authority` | Exactly `SERVER_MONSTER_SETTLEMENT`. |
| `occurred_at` | Non-empty committed-event timestamp/string. |
| `replayed` | Boolean delivery marker. It does not create another defeat. |
| `metadata` | Bounded JSON-safe object with no authoritative stat/reward/World-policy keys. |

The fact means only:

> A server-authoritative Battlefield Boss encounter was committed as defeated.

It is emitted by a future Monster adapter only after the authoritative
settlement and HP transition are committed. It must not be emitted from a UI
animation, response text, client `monster_defeated` claim, or Quest state.

## 5. Forbidden World decisions

Both top-level payloads are strict: unknown top-level fields fail closed.
Metadata is bounded and rejects authoritative-looking fields as well.

The following are not contract fields or valid metadata keys:

```text
boss_ready
lord_ready
lord_unlocked
zone_clear
zone_cleared
star_granted
stars
next_zone
next_zone_unlock
next_zone_unlocked
world_progressed
quest_completed
correct_answer
mastery_pct
```

The contract also rejects Monster stat/drop/reward authority in metadata,
including `monster_attack`, `monster_hp_max`, `stats`, `drop`, and `reward`.
World policy therefore cannot be smuggled through an opaque metadata object.

F012 does not encode the current Adventure `30%` rule, `60%`/`100%` Star
milestones, cooldown duration, question counts, Zone clear, or next-zone
logic. Those remain future World/Product decisions.

## 6. Replay and exactly-once boundary

The contract does not persist state and does not itself grant anything.

For an intent, the same `(user_id, intent_operation_id)` must have the same
authoritative replay fingerprint. A changed payload fails closed.

For a defeated fact, `settlement_id` is the canonical future dedupe key:

```text
defeated_fact_dedupe_key(fact) == fact.settlement_id
```

`assert_defeated_fact_replay_compatible` allows delivery timestamp and replay
marker changes, but rejects a changed settlement identity or changed
authoritative fact payload. A future World consumer must treat a replay of the
same settlement as the same defeat, not a second milestone.

## 7. Authority ownership

| Responsibility | Owner | F012 behavior |
|---|---|---|
| Battlefield Boss eligibility | World/Progression | Carries `WORLD_PROGRESSION` intent authority only. |
| Monster identity/profile | Monster/Encounter | Not selected or resolved by this module. |
| Monster HP/combat | Monster settlement / canonical combat | No stats or combat fields accepted. |
| Defeat fact | Server Monster settlement | Requires exact source authority and `defeated=true`. |
| Lord readiness policy | World/Adventure | Not encoded. Current `_adventure_state` rule is unchanged. |
| Lord Trial | Lord Trial server routes | Not modeled as a Monster fact. |
| Zone clear / Star / next Zone | World/Adventure | Rejected as payload fields. |
| Quest progress | Quest authority | Not emitted or mutated. |
| Persistence | Future adapter/consumer | No database access or migration in F012. |

## 8. F010 relationship

The accepted F009/F010 architecture separates regular selection from
Battlefield Boss intent. A future adapter may consume this intent as:

```text
World intent (BATTLEFIELD_BOSS)
  -> F010 durable encounter binding with encounter_intent=BATTLEFIELD_BOSS
  -> canonical Monster identity/profile resolver
```

F010 must not decide whether the user earned the milestone. Regular selector
behavior remains Common/Rare/Elite, excludes Battlefield Boss and Lord, and
F012 does not edit or activate F010.

The reverse adapter is:

```text
committed F010/F006-compatible Monster settlement
  -> BATTLEFIELD_BOSS_DEFEATED_FACT_V1
  -> future World policy consumer
```

The fact does not directly set `boss_ready`, clear a Zone, grant Stars, or
unlock the next Zone.

## 9. Storage answer

```text
CAN_EXISTING_DURABLE_SETTLEMENT_ID_SUPPORT_WORLD_DEDUPE=UNKNOWN
```

The current `origin/master` baseline contains durable settlement IDs in the
XP settlement lineage, but the current baseline does not contain the accepted
F006 Monster settlement module proving that every Monster defeat path exposes
the same stable `settlement_id`. F012 therefore carries the required field
without claiming an existing Monster storage guarantee.

```text
FUTURE_WORLD_MILESTONE_STORAGE_REQUIRED=OWNER_DECISION_REQUIRED
```

F012 does not create storage. A later runtime task must either prove that the
approved Monster settlement/idempotency record is sufficient for World
consumption or propose an additive World milestone projection. That decision
must not be hidden inside this contract.

## 10. Validation and tests

The focused suite is:

```text
tests/test_f012_world_monster_boundary_contract.py
32 passed
```

It covers:

- valid intent/fact construction and deterministic JSON round-trip;
- dataclass and nested metadata immutability;
- Battlefield Boss class and exact source-authority requirements;
- Lord/regular/`defeated=false` rejection;
- missing operation, settlement, and Monster IDs;
- strict unknown top-level fields;
- World-policy and Monster-stat field rejection;
- same-operation replay and changed-payload fail-closed behavior;
- settlement-ID fact dedupe and changed-fact rejection;
- no World decision fields in serialized payloads;
- no `app.py`, Flask, DB, Quest, Shop, or storage dependency;
- no F007 activation marker.

`python -m py_compile world_monster_boundary_contract.py` also passes.

## 11. Change boundary

```text
APP_PY_CHANGED=NO
SCHEMA_CHANGED=NO
PRODUCTION_MUTATION=NO
FEATURE_ENABLE=NO
DEPLOY=NO
MASTER_MERGE=NO
F007_RUNTIME_ACTIVATION=NO
```
