# C039 - Option C End-to-End Migration Rehearsal

## Scope and result

This document records a disposable PostgreSQL rehearsal of the governed
Option C maintenance sequence. It composes the accepted C038 quiescence
decision with the accepted C036 migration runner. It does not connect to
Production, change application source, run a Production migration, enable a
feature, or request an Owner gate.

~~~text
TASK=C039_OPTION_C_END_TO_END_MIGRATION_REHEARSAL_001
CURRENT_CANONICAL_MASTER=c2a1dab3125cdef0cff381815d3d995bdd340538
C038_HEAD=998df665306c2943f7b252db66035456f2013b19
REHEARSAL_ENVIRONMENT=DISPOSABLE_POSTGRESQL_16.14
FULL_OPERATIONAL_SEQUENCE=PASS
~~~

The test driver uses only a Docker-published loopback connection to an
ephemeral postgres:16.14-alpine container. Its URL is constructed inside
the test fixture and is never a CLI input, evidence artifact, or Production
configuration source. The fixture uses an isolated database and synthetic
rows, then removes its container in fixture cleanup.

## Accepted components and exact sequence

The rehearsal reuses these existing components without replacing or
generalizing them:

~~~text
C038:
  scripts/release/option_c_inventory_quiescence_precheck.py

C036:
  scripts/release/option_c_production_migration.py

MIGRATION_ORDER:
  1. migrations/equipment_canonical_slot_v1.py
  2. migrations/coin_purchase_operations_v1.py
~~~

The operational handoff is:

1. Use a runtime known to be B033-compatible for this rehearsal.
2. Keep CANONICAL_COIN_SHOP_PURCHASE_ENABLED=OFF.
3. Keep EQUIPMENT_CANONICAL_LOADOUT_ENABLED=OFF.
4. Stop new ingress for all eight C038 live player_inventory writer
   classes: Monster settlement, Admin grant/remove, canonical equip/unequip,
   legacy equip/unequip, and canonical Shop functional acquisition.
5. Drain requests and worker work at their existing service/process
   boundaries. C038 does not invent an application-wide freeze.
6. Require every known writer to be explicitly DRAINED.
7. Take a PostgreSQL activity observation and wait for a second stable
   observation. Require zero active writers, open conflicting transactions,
   relevant relation/advisory lock waits, long-running inventory
   transactions, and prepared transactions.
8. Hand only a QUIESCENCE_READY result to C036.
9. Run B033 through the existing C036 -Execute path with the exact
   GO_PRODUCTION_DB_MIGRATION value. In this rehearsal the target is
   asserted disposable, so this is a gate-path simulation and not Owner
   authorization.
10. B033 runs in its own transaction. Its schema and equipped-state
    postchecks must pass before commit.
11. Only after B033 commits, run C019 in its own transaction. Its schema,
    key, check, index, and JSON payload postchecks must pass before commit.
12. Run final schema/data/runtime acceptance, including a migrated C026
    purchase and D024 result adaptation.
13. Resume only compatible drained writers after acceptance. Keep both
    canonical feature gates OFF; writer resume is not feature enablement.

The external writer drain must remain held from the final C038 observation
through both C036 transactions and post-migration acceptance. C038's
observation helper is read-only and does not itself stop traffic, acquire a
migration lock, or run either migration.

## Disposable fixture

The fixture starts PostgreSQL 16.14 Alpine with:

~~~text
--shm-size 128m
--tmpfs /var/lib/postgresql/data:rw,exec,size=512m
~~~

The synthetic legacy schema has:

~~~text
user_stats
currency_log
player_inventory              canonical_slot absent
shop_inventory
player_wardrobe
domain_event_outbox           pre-existing and validated by C036
coin_purchase_operations      absent before the sequence
~~~

It seeds two users and valid legacy ownership rows representing:

~~~text
iron_sword   equipped=1   source=drop       weapon slot
cloth_robe   equipped=1   source=admin      armor slot
lucky_stone  equipped=0   source=drop       accessory slot
~~~

The rows have no duplicate equipped slots, no malformed equipped values, and
no locked xp_amulet or go_stone_black state. The fixture is therefore
representative of a safe pre-B033 handoff while still proving that B033
backfills multiple functional slots and preserves existing rows.

## Evidence covered

The focused C039 suite contains twelve collected tests, including the
following evidence:

| Evidence | Result |
| --- | --- |
| C038 clean two-sample handoff to C036 | PASS |
| exact disposable -Execute plus GO_PRODUCTION_DB_MIGRATION gate path | PASS |
| wrong gate and dry-run remain fail-closed | PASS |
| active writer blocks handoff before either migration starts | PASS |
| unknown writer state blocks handoff | PASS |
| in-flight writer commits, drains, and is preserved before handoff | PASS |
| B033 postcheck failure rolls back and skips C019 | PASS |
| C019 failure rolls back only its second transaction and preserves B033 | PASS |
| B033 and C019 postcheck failures block writer resume | PASS |
| migrated C019 purchase replay performs no second debit/event/row | PASS |
| full migration rerun returns ALREADY_VALID without migration execution | PASS |
| B040/B041 supported writers work after B033; unsafe legacy insert is rejected | PASS |

The successful path also proves a functional player_inventory purchase
through C026, captures the exact inserted ownership reference, persists the
committed result, and adapts it through D024 without a read-side
player_inventory identity lookup.

## Failure and recovery semantics

### Quiescence failure

An active, unknown, missing, extra, or unregistered writer state is not
interpreted as drained. Any nonzero observation or missing observation is not
interpreted as zero. The sequence remains stopped and neither B033 nor C019
starts.

### B033 failure

B033 is rolled back as one transaction. C019 is not attempted. The schema
must remain the legacy pre-B033 shape. Writers remain quiesced until the
rollback and runtime state are explicitly accepted. The old C32 runtime is
permitted only after a confirmed pre-B033 rollback.

### B033 postcheck failure

B033 is rolled back and the sequence stops. No C019 transaction starts and
writers are not resumed.

### C019 failure or postcheck failure

B033 remains committed. Only the C019 transaction is rolled back. The safe
state is B033_COMMITTED_COIN_PURCHASE_FAILED, with C019 absent or
unverified, both gates OFF, and writers still quiesced. There is no automatic
retry. Rolling back to the old C32 runtime after B033 commit is forbidden.

### Post-migration acceptance failure

Features remain OFF and writers remain quiesced. No blind resume or feature
enablement is allowed. The Coordinator must reconcile the committed schema
and runtime state.

### Commit outcome unknown

Do not retry or resume. Treat the schema state as unknown and require manual
reconciliation.

## Writer compatibility and resume

After B033, the rehearsal proves:

- B040 grant_equipment_ownership writes server-derived canonical slots for
  Monster/Admin source semantics.
- B041 equip_owned_item and unequip_owned_item operate on the exact
  server-owned row.
- A server-owned Admin removal predicate can remove the intended row.
- A legacy equipped insert that omits canonical_slot is rejected by the
  B033 check constraint rather than creating unsafe state.
- C026 can acquire a functional Equipment row with the exact
  player_inventory:{row_id} reference, and D024 consumes the committed
  reference.

precheck.writers_may_resume_after_acceptance() returns true only when B033
postchecks, C019 postchecks, runtime acceptance, and schema acceptance all
pass. Resuming compatible inventory traffic does not turn on Shop or
canonical loadout and does not authorize Revenue or payment enablement.

## Governance boundary

The test calls the C036 core with:

~~~text
target_environment=disposable
execute=True
owner_gate=GO_PRODUCTION_DB_MIGRATION
~~~

The value is exercised only as a synthetic disposable gate-path input.
REAL_OWNER_GATE_CONSUMED=NO; no Production target is possible through this
test driver. C039 does not request GO_PRODUCTION_DB_MIGRATION, does not
implement a maintenance mode, and does not provide a global traffic freeze.

~~~text
PRODUCTION_QUERY=NO
PRODUCTION_MUTATION=NO
PRODUCTION_SCHEMA_MIGRATION=NO
DEPLOY=NO
FEATURE_ENABLE=NO
GO_PRODUCTION_DB_MIGRATION_GRANTED=NO
~~~
