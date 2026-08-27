# C038 — Governed Inventory-Write Quiescence Execution Packet

## Scope and decision

This packet is the release-control boundary for the future Option C schema
maintenance sequence. It does not stop application traffic, run a migration,
change `app.py`, or enable a feature. The companion helper is an observation
and decision tool only:

`[option_c_inventory_quiescence_precheck.py](../../../scripts/release/option_c_inventory_quiescence_precheck.py)`

The helper accepts independently collected writer/process and PostgreSQL
evidence, then fails closed unless every live writer is explicitly drained and
the relevant database observations are zero. It never connects to a database
from its CLI, stops a process, acquires a migration lock, commits, rolls back,
or executes a migration.

The C038 conclusion remains:

```text
LIVE_CONCURRENT_WRITE_SAFE_WITHOUT_FREEZE=NO
REQUIRED_WRITE_QUIESCENCE=YES
EXISTING_INVENTORY_MUTATION_FREEZE_MECHANISM=NO
```

The database transactions are atomic, but ordinary inventory writers do not
take the B033 advisory lock. B033 obtains an `AccessExclusiveLock` while its
transaction is open, and the old equipped writer contract is not semantically
compatible after B033 commits. A temporary, externally governed write drain
is therefore required.

## Provenance

```text
CURRENT_CANONICAL_MASTER=c2a1dab3125cdef0cff381815d3d995bdd340538
C037_ACCEPTED_HEAD=ff4aed3266a1aaa67755cb9e6374a1cc6e44bc92
C036_RUNNER_REFERENCE=aa9924a933ce52a438bd7a301e64059ffecdd473
MIGRATION_SEQUENCE=equipment_canonical_slot_v1.py -> coin_purchase_operations_v1.py
```

The C038 candidate is based on the accepted C037 descendant so the C036
governed runner and the C037 live-concurrency evidence remain available as
parent history. The current canonical master is an ancestor. No C036, C037,
B033, or C019 migration source is changed by C038.

## Complete current `player_inventory` mutation inventory

The following eight entries are the live traffic writer set that must be
stopped and drained. The list was bounded against the tracked current source,
`app.py`, B040, B041, C026, route callers, and tooling. The helper exposes the
same list through `writer_inventory()`.

| Writer | Classification | Caller / process | Authority | Normal production | Stop / drain / resume boundary |
| --- | --- | --- | --- | --- | --- |
| `monster_functional_equipment_acquisition` | `APP_REQUEST_WRITER` | `app._settle_monster_defeat_in_tx.grant_functional_item`; review and internal MapBattle settlement workers | B040 `grant_equipment_ownership` | Yes | Stop review/settlement ingress and worker intake; drain in-flight settlements; resume only after acceptance with B040-compatible runtime |
| `admin_equipment_grant` | `ADMIN_WRITER` | `admin_set_equipment`, `action=grant`, `/api/admin/users/<uid>/assets/equipment` | B040 equipment ownership service | Yes, admin-only | Close/hold the admin mutation boundary and drain requests; resume only after acceptance |
| `admin_equipment_remove` | `ADMIN_WRITER` | `admin_set_equipment`, `action=remove`, same route | Authenticated direct `DELETE` with `id` and `user_id` ownership predicate | Yes, admin-only | Close/hold the admin mutation boundary and drain requests; resume only after acceptance |
| `player_equipment_equip_canonical` | `APP_REQUEST_WRITER` | `equip_item`, `/api/player/inventory/equip`, canonical loadout gate ON | B041 `equip_owned_item` | Conditional; gate defaults OFF | Stop endpoint traffic and drain in-flight calls; resume only with B041-compatible runtime and acceptance |
| `player_equipment_unequip_canonical` | `APP_REQUEST_WRITER` | `equip_item`, same endpoint, canonical loadout gate ON | B041 `unequip_owned_item` | Conditional; gate defaults OFF | Stop endpoint traffic and drain in-flight calls; resume only with B041-compatible runtime and acceptance |
| `player_equipment_equip_legacy` | `LEGACY_WRITER` | `equip_item`, canonical loadout gate OFF | Direct legacy `player_inventory` `UPDATE` | Yes by default | Stop endpoint traffic; a gate-OFF state alone is not a drain; resume only after compatible runtime acceptance |
| `player_equipment_unequip_legacy` | `LEGACY_WRITER` | `equip_item`, canonical loadout gate OFF | Direct legacy `player_inventory` `UPDATE` | Yes by default | Stop endpoint traffic; a gate-OFF state alone is not a drain; resume only after compatible runtime acceptance |
| `canonical_shop_functional_equipment_acquisition` | `APP_REQUEST_WRITER` | `shop_buy` / `shop_buy_appearance` canonical dispatch → C025/C029 → C026 | C026 `SqlAcquisitionAuthority` | Conditional; Shop gate defaults OFF | Keep canonical Shop disabled, stop any canonical request intake, drain retries/requests; resume only after acceptance and a separate enable decision |

Every live entry has an explicit stop boundary, drain signal, and resume
boundary in the helper. The common drain signal is an operator acknowledgement
plus PostgreSQL evidence showing zero active inventory writers, zero open
conflicting transactions, zero relevant lock waits, zero long-running
inventory transactions, zero B033 migration-lock waits, and zero prepared
transactions.

### Controlled maintenance mutator (not a live traffic writer)

B033's `_backfill_known_functional_equipment` also mutates
`player_inventory`. It is listed separately by
`maintenance_mutator_inventory()` because it is the controlled migration step
that is allowed to start only after the live writer set is quiescent. It has no
service stop/drain/resume lifecycle and must not be treated as a writer that
can be resumed. The C038 helper therefore requires the eight live names, then
hands the controlled mutation to C036.

### Paths not found as live `player_inventory` writers

The bounded source scan found no additional production scheduler/background,
reward-result, D024, read-model, frontend, or release-tool direct DML writer.
`app.init_db` schema creation is DDL/bootstrap, not an ownership-row writer.
Tests and development fixtures may issue direct SQL, but are not production
writers and are excluded from the live set. Any later-discovered external
worker, queue, retry process, or direct SQL utility is an unregistered writer;
the packet must be treated as `WRITER_STATE_UNKNOWN` until it is inventoried
and drained. No absence claim is made for undiscovered external systems.

## Existing boundaries and how traffic is quiesced

No application-wide inventory mutation freeze exists in current source. The
two feature gates are not a substitute:

```text
CANONICAL_COIN_SHOP_PURCHASE_ENABLED=OFF
EQUIPMENT_CANONICAL_LOADOUT_ENABLED=OFF
```

They block the future canonical Shop/loadout branches, but do not stop B040
Monster drops, B040 Admin grants/removals, or legacy equip/unequip updates.

The smallest governed procedure must therefore use the existing service and
process boundaries, with an external operator controlling ingress and worker
intake:

1. Confirm a B033-compatible runtime is deployed and healthy. Do not use the
   old C32 runtime as the post-B033 rollback target.
2. Observe both canonical gates and require actual `OFF`. An `ON` or unknown
   gate is a fail-closed result.
3. At the app/service boundary, stop accepting the eight live writer classes:
   review/Monster settlement, Admin Equipment mutations, the equipment
   endpoint, and any canonical Shop request path. Pause relevant worker intake
   and retry/queue delivery. Do not claim a writer is stopped merely because a
   feature gate is OFF.
4. Drain in-flight requests and worker jobs. The operator must provide an
   explicit state for every helper writer name: `DRAINED`, `ACTIVE`, or
   `UNKNOWN`. Missing, extra, invalid, or unknown names fail closed.
5. On the same external freeze, collect a PostgreSQL observation. Repeat the
   observation after the configured settle interval; both samples must be
   clean. The helper records `observation_samples=1` for each raw observation
   and requires the caller to supply at least two clean samples before it can
   return `QUIESCENCE_READY`. It deliberately does not pretend that a single
   query prevents a new writer from starting.
6. Require `QUIESCENCE_READY`. Do not start B033 when any active writer,
   unknown writer, open conflict, lock wait, long-running transaction,
   migration lock wait, prepared transaction, runtime mismatch, gate problem,
   or schema mismatch is present.
7. Keep the external freeze continuously held through both migration phases,
   their postchecks, and the acceptance smoke checks. A later writer must not
   enter between the final observation and B033 `COMMIT`.

If an external service boundary cannot stop or drain a writer, its state is
`WRITER_STATE_UNKNOWN`, not `DRAINED`; the sequence does not begin.

## Read-only PostgreSQL drain observation

`observe_postgres_inventory_activity()` is intentionally aggregate-only and
uses four `SELECT`/`WITH` statements through the repository PostgreSQL
adapter:

1. Resolve the `public.player_inventory` relation OID.
2. Inspect `pg_stat_activity` and `pg_locks` for aggregate counts of active
   writer sessions, open idle-in-transaction writers holding relation locks,
   relevant relation lock waits, and long-running transactions whose query or
   relation lock touches `player_inventory`.
3. Inspect ungranted B033 advisory-lock waits for key `773310034`.
4. Count `pg_prepared_xacts`; any prepared transaction is a conflict for the
   quiescence handoff.

The observation excludes the observer backend and returns only counts. It
does not return PIDs, SQL text, player rows, user IDs, or credentials. The
function rejects any statement whose first keyword is not `SELECT` or `WITH`,
and reports `writes=0`, `commits=0`, `rollbacks=0`, and
`migration_execution=0`. A caller must roll back/close its own read-only
observation transaction; the helper itself never performs cleanup that could
be confused with application mutation.

The proof covers:

```text
ACTIVE_WRITER_DETECTION=PostgreSQL pg_stat_activity/pg_locks aggregate
OPEN_TRANSACTION_DETECTION=idle-in-transaction writer relation-lock aggregate
LOCK_WAIT_DETECTION=player_inventory relation waits + B033 advisory waits
```

The observer requires sufficient PostgreSQL catalog visibility. If the caller
cannot obtain complete evidence, it must supply missing/unknown evidence and
the result is not ready.

## Fail-closed decision contract

The helper returns these exact decision statuses:

| Status | Meaning | Required action |
| --- | --- | --- |
| `QUIESCENCE_READY` | All eight live writers are explicitly `DRAINED`, all required counts are observed as zero, runtime is compatible, both gates are OFF, and the exact legacy pre-migration schema is observed | A handoff to the governed C036 runner may be considered; C038 still does not execute it |
| `WRITER_ACTIVE` | A writer is explicitly active or the database shows active/locked/long-running writer activity | Stop; continue drain; do not start migration |
| `WRITER_STATE_UNKNOWN` | A writer state, database count, or runtime evidence is missing/unknown, or an unregistered writer appears | Stop; inventory and obtain evidence; do not infer zero |
| `OPEN_CONFLICTING_TRANSACTION` | An open writer relation lock, B033 migration lock wait, or prepared transaction is present | Stop and resolve the transaction/lock |
| `RUNTIME_NOT_B033_COMPATIBLE` | The deployed/runtime evidence is known incompatible | Deploy/verify compatible runtime first; do not migrate |
| `FEATURE_GATE_UNEXPECTED` | Shop or loadout is ON or unknown | Keep features OFF; return to Coordinator |
| `SCHEMA_STATE_UNEXPECTED` | The observed pre-migration schema is partial, already migrated, or otherwise not the expected state | Stop; reconcile schema; do not auto-repair |

Unknown is never converted to `DRAINED`, zero, or ready. Fewer than two stable
database samples are also insufficient evidence. A caller's
`freeze_confirmed` acknowledgement, if retained by the C036 handoff, is
secondary evidence and cannot replace the writer map plus database observation.

## Exact future migration handoff

C038 binds the following sequence and does not generalize it:

```text
1. migrations/equipment_canonical_slot_v1.py
2. migrations/coin_purchase_operations_v1.py
```

After the two-sample quiescence proof is accepted, the future operator hands
the evidence to the accepted C036 runner
`scripts/release/option_c_production_migration.py`. C036 remains the only
component that may execute these migrations, and only its exact governed
contract applies:

```text
production mutation requires -Execute
and -OwnerGate GO_PRODUCTION_DB_MIGRATION
and external inventory-mutation-freeze evidence
```

`GO_DEPLOY` and `GO_ENABLE` do not authorize schema mutation. C038 does not
invoke C036 and does not request `GO_PRODUCTION_DB_MIGRATION`.

## Failure and recovery packet

The external freeze remains in force until the state is explicitly accepted.
No automatic retry is allowed for an unknown commit outcome.

| Failure state | Transaction action | Safe runtime/schema state | Gate / writer action | Next allowed action |
| --- | --- | --- | --- | --- |
| `B033_PRECHECK_FAIL` / quiescence not reached | No migration transaction begins | Legacy schema unchanged | Gates OFF; writers remain stopped or return only after the existing legacy state is confirmed safe | Resolve the exact precondition, recollect evidence, and obtain a fresh handoff |
| `B033_MIGRATION_FAIL` | Roll back B033 transaction | Legacy schema; no partial column/constraint/index accepted | Gates OFF; keep writers quiesced until rollback/state is confirmed | Stop and investigate; do not run C019 |
| `B033_POSTCHECK_FAIL` | Roll back B033 transaction | Legacy schema; no half-migrated inventory accepted | Gates OFF; keep writers quiesced | Stop and investigate; do not run C019 |
| `B033` committed, `COIN_PURCHASE_MIGRATION_FAIL` | Roll back C019 transaction only | B033 committed; C019 absent or unverified | Gates OFF; old C32 rollback forbidden; keep writers quiesced until B033-compatible state is confirmed | Coordinator reconciliation; no automatic C019 retry |
| `COIN_PURCHASE_POSTCHECK_FAIL` | Roll back C019 transaction only | B033 committed; C019 absent or unverified | Gates OFF; old C32 rollback forbidden; keep writers quiesced | Coordinator reconciliation; do not enable Shop |
| Post-migration acceptance failure | Do not enable; do not blindly resume | Schema may be committed but unaccepted | Gates OFF; writers remain quiesced unless a compatible recovery state is explicitly proven | Manual acceptance/reconciliation |
| Commit outcome unknown | Do not retry or resume | Unknown; treat as unsafe | Gates OFF; freeze stays in force | Manual schema/state reconciliation |

The accepted C036/C037 boundary is explicit: after B033 commits, an old C32
writer that omits `canonical_slot` is not a safe rollback runtime. A B033
failure before commit leaves the legacy schema and can return to the old
runtime only after the rollback is confirmed.

## Writer resume contract

Writers may resume only after all of the following are independently PASS:

```text
B033 postchecks
C019 postchecks
runtime acceptance
schema acceptance
```

The resume action is limited to B033-compatible writers. Canonical Shop and
Equipment loadout remain OFF; resuming eligible compatible inventory traffic
does not grant `GO_ENABLE` and does not enable Revenue or payments. Feature
enablement is a separate Owner decision.

## Disposable PostgreSQL evidence

The focused C038 suite uses a synthetic PostgreSQL 16.14 Alpine container
with an isolated `player_inventory` table. It proves:

```text
FULL_QUIESCENCE_SEQUENCE=PASS
ACTIVE_WRITER_BLOCK=PASS
UNKNOWN_WRITER_BLOCK=PASS
DRAIN_BEHAVIOUR=PASS
SAFE_RESUME=PASS
ACTIVE_WRITER_DETECTION=PASS
RELATION_LOCK_WAIT_DETECTION=PASS
B033_ADVISORY_LOCK_WAIT_DETECTION=PASS
```

Observed test result:

```text
tests/test_c038_inventory_write_quiescence.py = 16 passed
PostgreSQL = 16.14 (disposable only)
Production query = 0
Production mutation = 0
```

The test does not claim that PostgreSQL DDL is safe with live legacy writers;
that conclusion remains the accepted C037 result `NO` without external
quiescence. The test proves the C038 observation and fail-closed decision
boundary, not a Production migration.

## C038 boundaries

```text
APP_PY_CHANGED=NO
SCHEMA_MIGRATION_FILES_CHANGED=NO
DOCKERFILE_CHANGED=NO
PRODUCTION_QUERY=NO
PRODUCTION_MUTATION=NO
PRODUCTION_SCHEMA_MIGRATION=NO
DEPLOY=NO
FEATURE_ENABLE=NO
GO_PRODUCTION_DB_MIGRATION_GRANTED=NO
```

No secrets, database credentials, Production rows, or player identifiers are
output by the helper or the focused tests. C038 is ready for Coordinator
review as a governed planning/proof packet, not as authorization to perform
the migration.
