# C037 Option C Live-Concurrency Migration Safety Proof

## Decision

`LIVE_CONCURRENT_WRITE_SAFE_WITHOUT_FREEZE=NO`.

The PostgreSQL transactions are atomic and the database does not silently
drop a committed inventory write.  That is not sufficient to permit the
legacy application writers to remain live across the B033 commit.  Ordinary
inventory writers do not take the B033 advisory lock, and a legacy equipped
insert that omits `canonical_slot` is rejected by the B033 check constraint
after the migration commits.  The smallest safe Production procedure is an
externally governed, temporary inventory-write quiescence.

This proof uses only a synthetic disposable PostgreSQL 16.14 database.  It
does not query or mutate Production and does not change `app.py`, either
accepted migration, or product runtime behavior.

## Provenance

| Field | Value |
| --- | --- |
| C037 base / current canonical master | `c2a1dab3125cdef0cff381815d3d995bdd340538` |
| C036 parent candidate | `aa9924a933ce52a438bd7a301e64059ffecdd473` |
| migration order | `equipment_canonical_slot_v1.py` then `coin_purchase_operations_v1.py` |
| PostgreSQL image | `postgres:16.14-alpine` |
| Python driver | `psycopg2 2.9.9` |
| repository DB adapter | `db.PostgresConnectionWrapper` |
| data | synthetic only |

## Lock and transaction findings

### B033 equipment canonical-slot migration

`migrations.equipment_canonical_slot_v1.upgrade` takes transaction-scoped
advisory lock `773310034`.  This serializes B033 callers only; it is not a
lock acquired by application inventory writers.  The first
`ALTER TABLE ... ADD COLUMN canonical_slot` takes PostgreSQL
`AccessExclusiveLock`, held through the caller's transaction.  The known
functional-item backfill then runs before the check constraint and ordinary
partial unique index are created.  The index is not `CONCURRENTLY`.

Consequently, a writer holding a relation lock makes B033 wait, and a new
writer waits while B033 holds the relation lock.  A writer that committed
before B033 obtained the relation lock is visible to the backfill.  A legacy
equipped writer released after B033 commits can fail with SQLSTATE `23514`
because it did not provide a canonical slot.  This is an explicit rejected
write, not a safe transparent compatibility mode.

Any exception before B033 commit is rolled back by its caller, including the
new column, backfill, constraint, and index.  No B033 partial schema is
accepted.

### C019 purchase-operation migration

`migrations.coin_purchase_operations_v1.upgrade` takes its separate
transaction-scoped advisory lock `773310026`, creates and validates only the
purchase-operation table and its indexes, and never commits or rolls back.
The C036 runner starts it only after a committed B033 phase.  A C019 failure
rolls back only its own transaction; the safe result is
`B033_COMMITTED_COIN_PURCHASE_FAILED`, with both canonical feature gates
remaining OFF and no automatic retry.

The C019 primary key `(user_id, purchase_operation_id)` and the C019 service's
existing transaction contract preserve replay idempotency: a committed
operation replay returns its stored result without a second debit,
acquisition, or D5A event.  This does not make B033 safe with legacy writers;
the two concerns remain separate.

## Concurrent scenario matrix

The focused C037 suite runs the real migration functions and, for the replay
case, the real `coin_purchase_authority.purchase_with_coins` path.

| Scenario | Observed/required result |
| --- | --- |
| Writer committed before B033 | B033 backfills its server-derived slot; row survives |
| Writer began before B033 | B033 waits on the relation lock; writer can commit first; row is backfilled |
| Writer begins during B033 | insert waits while B033 holds `AccessExclusiveLock` |
| Legacy equipped writer releases after B033 | fails closed with the B033 check; B033 remains committed |
| Writer waits on the migration advisory lock | only another migration caller waits; ordinary writers use relation locks, not the advisory lock |
| B033 failure while a writer was active | caller rollback removes all B033 schema state; the writer's committed legacy row remains |
| writer failure while B033 is active | writer rolls back independently; B033 can commit cleanly |
| two post-B033 unequipped writers | both legitimate rows commit; no write is lost |
| two post-B033 equipped same-slot writers | the partial unique index serializes the conflict; at most one commits |
| B040 Monster/Admin writers after B033 | both server-owned writers persist exact rows and derived slots |
| B034 equip/unequip after B033 | exact ownership-row writer remains valid; state returns to unequipped |
| C019 migration with a live inventory writer | C019 does not touch `player_inventory`; the writer survives |
| C019 purchase replay | stored operation result replays once; no second debit, row, or D5A event |

## Safety result

```text
B033_TRANSACTION_ATOMICITY=PASS
C019_TRANSACTION_ATOMICITY=PASS
NO_HALF_MIGRATED_INVENTORY=PASS
NO_DUPLICATE_EQUIPPED_SLOT=PASS
NO_LOST_INVENTORY_WRITE=PASS
LIVE_CONCURRENT_WRITE_SAFE_WITHOUT_FREEZE=NO
EXISTING_INVENTORY_MUTATION_FREEZE_MECHANISM=NO
```

The `PASS` sub-results describe database transaction and invariant behavior.
The overall `NO` is an operational compatibility result: a live legacy
writer may be rejected after B033, and the current C036 runner does not
provide an application-wide mutation freeze.  Allowing that behavior during
a Production migration would make valid in-flight requests nondeterministic
and would not prove a safe release boundary.

## Smallest governed temporary write-quiescence

This is an execution precondition, not an implementation in C037:

1. Deploy and health-check the B033-compatible runtime first; do not enable
   canonical Shop or canonical Equipment loadout.
2. Use the separately governed operational control to stop and drain every
   `player_inventory` mutation writer, including Monster/B040, Admin/B040,
   B034/B041 equip/unequip, and any remaining legacy direct writer.  Confirm
   zero in-flight inventory mutations.  C036 reports no existing
   application-wide freeze mechanism, so this evidence must come from the
   release/operator control plane.
3. Begin an explicit caller-owned transaction, run B033, run its schema and
   equipped-state postchecks, and commit only if all pass.  On any exception
   or failed postcheck, roll back and stop; do not start C019.
4. Begin a separate transaction, run C019, validate its complete schema and
   idempotency constraints, and commit only if all pass.  If it fails, roll
   back only transaction two and stop in the
   `B033_COMMITTED_COIN_PURCHASE_FAILED` state.
5. Keep both canonical feature gates OFF, perform sanitized health and
   invariant checks, and resume only B033-compatible writers.  An old C32
   runtime rollback is forbidden after B033 commits.

No application maintenance mode or general migration framework is introduced
by this proof.

## Failure boundaries

| Failure | Safe action | Safe schema/runtime state |
| --- | --- | --- |
| B033 precheck or migration failure | rollback/stop; do not run C019 | legacy schema; legacy-compatible runtime may continue |
| B033 postcheck failure | rollback/stop | no half-migrated inventory schema |
| C019 migration/postcheck failure | rollback transaction two only; stop | B033 committed; C019 absent/unverified; gates OFF; B033-compatible runtime required |
| writer failure during migration | roll back that writer; inspect error; do not retry blindly | migration transaction remains authoritative |
| old runtime after B033 commit | forbidden rollback target | only B033-compatible runtime may run |

## Files and boundaries

The C037 candidate adds only the focused disposable proof and this evidence
document.  It does not modify `app.py`, runtime services, accepted migration
files, production configuration, or any database.

## Validation evidence

The focused proof was run against a disposable PostgreSQL `16.14` instance
using `psycopg2 2.9.9` and the repository's `db.PostgresConnectionWrapper`.
Each case recreated a synthetic public schema; no Production connection,
credential, or player data was used.

```text
python -m pytest -q tests/test_c037_option_c_live_concurrency_migration_safety.py
13 passed in 20.21s
```

The 13 passing cases cover the exact PostgreSQL version, writers committed
before and started before B033, a writer beginning while B033 holds its
relation lock, B033 advisory-lock serialization, B033 failure rollback with
an active writer, writer failure during B033, competing post-B033 writers and
the partial unique equipped-slot invariant, a live writer during C019,
B040 Monster/Admin writers, B034 exact-row equip/unequip, C019 failure
rollback, and a real C019 purchase replay with no second debit, ownership
grant, or D5A event.

The proof also records the six parallel review results: all reviewers agree
that the database transaction/invariant sub-results pass, while live
concurrent operation without an external write-quiescence is not safe.
