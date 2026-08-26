# F018 Battlefield Boss Reward Milestone Result Contract v1

Status: candidate for Owner review

## Scope

F018 is a route-independent, detached result layer after the accepted F017
Battlefield Boss milestone orchestration. It consumes the typed F017 result,
which has already reused F014 validation/binding and the F015 idempotent
milestone projection. F018 does not call storage and does not mutate runtime
state.

The flow is:

```text
F017 result (F014 validated, F015-backed)
    -> BattlefieldBossMilestoneRewardResult
```

The result preserves the F017 outcome (`RECORDED`, `REPLAYED`, `CONFLICT`, or
`REJECTED`) and the stable milestone identifiers needed by a future caller.
It does not manufacture a reward grant.

## Reward authority finding

`F018_REWARD_CONTENT_AUTHORITY_MISSING=YES`.

The current repository contains `reward_battlefield_legacy` in the shared
Monster reward profile registry, but that profile is marked fragmented legacy
compatibility and is not a dedicated, authorized Battlefield Boss reward
result authority. Existing reward writers remain outside this layer. F018
therefore emits no Coins, XP, item, drop, quantity, or reward-profile values.

The result reports:

```text
reward_status=REWARD_CONTENT_AUTHORITY_MISSING
reward_content_authority_missing=true
```

This is an explicit safe shell, not a zero-value reward decision. A future
Owner-approved reward authority may add a separate projection layer without
changing the F017 milestone contract.

## Result contract

Module: `world_battlefield_boss_reward_result.py`

API: `build_battlefield_boss_milestone_reward_result(milestone)`

Contract version: `F018_BATTLEFIELD_BOSS_MILESTONE_REWARD_RESULT_V1`

`milestone` must be the exact typed
`BattlefieldBossMilestoneOrchestrationResult` returned by F017. Raw mappings
and arbitrary objects are rejected. F017 `RECORDED` and `REPLAYED` results
remain backed by the F015 table `world_battlefield_boss_milestones`; F017
`CONFLICT` and `REJECTED` outcomes are propagated without reward mutation.

The detached result contains only:

- milestone status and reward-authority status;
- user, settlement, Zone, Monster, and encounter-operation identifiers;
- recorded/replayed markers and a validation/conflict error code.

It contains no World progression decisions and no reward content values.

## Preserved authority boundaries

- `BATTLEFIELD_BOSS != LORD`; invalid Lord input is rejected by the accepted
  F014/F017 boundary.
- F017 remains the only composed milestone mutation path; F018 creates no
  second milestone or reward storage authority.
- F015 retains the `(user_id, settlement_id)` dedupe contract and caller-owned
  transaction boundary.
- F018 never commits, rolls back, writes SQL, emits Quest events, or applies
  World policy.
- Recording a milestone never implies Zone clear, Star grant, World unlock, or
  Lord readiness.
- No app.py, route, feature flag, schema, migration, Production, combat,
  drop, or reward runtime changes are included.

## Tests

The focused suite covers recorded/replayed/conflict results, cross-user
settlement isolation, invalid World/Lord input, typed-boundary rejection,
absence of reward values and World policy fields, immutability, and the
absence of runtime/storage wiring. It uses disposable SQLite only to exercise
the already accepted F017/F015 path; no F018 schema or PostgreSQL behavior is
introduced.
