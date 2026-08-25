# F017 Battlefield Boss Milestone Orchestrator V1

## Scope

F017 provides one route-independent service for the already merged F012,
F014, and F015 foundation.  It validates a trusted World intent, binds the
server-selected Battlefield Boss and committed Monster settlement through
F014, then delegates the only projection write to F015.

Runtime route wiring remains out of scope.  The service does not select a
Monster, settle combat, authenticate a request, emit Quest events, or apply
World progression policy.

## API

Implementation:

`world_battlefield_boss_orchestrator.orchestrate_battlefield_boss_milestone`

Inputs:

- caller-owned database connection
- authenticated server user ID
- validated `BattlefieldBossEncounterIntent`
- server-bound `ServerBattlefieldBossSelection`
- typed `ServerMonsterSettlementEvidence`
- optional delivery replay marker and storage timestamp

The authenticated user ID must match the user in all three trusted handoffs.
Raw mappings and client defeat claims are rejected by the F014 type boundary.

## Authority flow

```text
authenticated server identity
        +
F012 BattlefieldBossEncounterIntent
        +
F014 server Monster selection
        +
F014 committed settlement evidence
        |
        v
F014 selector-call validation
        -> F014 operation / Zone / Monster binding
        -> F014 defeated-fact builder
        v
F015 record_battlefield_boss_defeated_fact
        v
detached F017 result
```

F014 remains the authority for:

- World-authorized Battlefield Boss intent
- server-selected Monster identity
- Zone and operation continuity
- committed defeat transition (`hp_before > 0`, `hp_after == 0`)
- Battlefield Boss versus non-Boss rejection

F015 remains the authority for:

- `world_battlefield_boss_milestones`
- composite dedupe `(user_id, settlement_id)`
- idempotent replay
- changed authoritative payload conflict

F017 does not issue direct SQL and does not create a second milestone store.

## Result contract

`BattlefieldBossMilestoneOrchestrationResult.status` is one of:

- `RECORDED` — one new F015 projection row was recorded.
- `REPLAYED` — the same composite identity replayed the original row.
- `CONFLICT` — the same `(user_id, settlement_id)` carried changed
  authoritative evidence; no replacement is accepted.
- `REJECTED` — F014 validation/binding or typed evidence validation failed.

The result exposes only user, settlement, Zone, Monster, and encounter
operation identifiers plus delivery status.  It has no World progression
decision fields.

## Transaction contract

The caller owns `BEGIN`, `COMMIT`, and `ROLLBACK`.  F017 performs none of
these operations.  A schema/database failure is propagated to the caller;
expected validation and F015 evidence conflicts are represented in the
typed result.

## Explicit non-goals

Recording a milestone does not itself alter Zone state, Stars, World unlock,
Lord readiness, Lord Trial state, Quest state, selected Zone, or progression
Zone.  Battlefield Boss remains distinct from Lord.  No `app.py` route,
feature flag, migration, Production operation, or runtime cutover is part of
F017.

## Verification

`tests/test_f017_world_battlefield_boss_orchestrator.py` covers recorded
facts, replay, changed-payload conflict, cross-user settlement isolation,
F014 validation failures, raw defeat rejection, transaction ownership, and
the absence of World policy/runtime wiring.
