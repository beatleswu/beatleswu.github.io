# C036 Canonical Option C Production Migration Runner

## Scope and provenance

This candidate is based on c2a1dab3125cdef0cff381815d3d995bdd340538
(origin/master at implementation start). It adds one release-tooling runner
and a disposable PostgreSQL acceptance suite. It does not change app.py,
application runtime behavior, either accepted migration, the database,
Production, deployment, or feature-gate state.

The runner is:

scripts/release/option_c_production_migration.py

It is intentionally a narrow Option C tool. It knows exactly these two
migrations, in this order:

1. migrations/equipment_canonical_slot_v1.py
2. migrations/coin_purchase_operations_v1.py

migrations/domain_event_outbox_v1.py is validation-only. It is not run by
C036 because the Production contract already treats the outbox as present
and compatible.

## Execution governance

The default mode is a read-only preflight. It opens a read-only PostgreSQL
session and never calls a migration. Mutation requires both:

    -Execute
    -OwnerGate GO_PRODUCTION_DB_MIGRATION

The exact gate is case-sensitive. GO_DEPLOY, GO_ENABLE, arbitrary gate
strings, and an omitted gate fail closed before a database connection is
opened for execution. The CLI has no database-URL argument. Future
Production execution reads the protected runtime DATABASE_URL through the
repository db.get_db() / PostgresConnectionWrapper path. A direct URL is
available only as an in-process disposable-test seam and is never printed.

Before any preflight or mutation, the runner binds the result to:

- exact checked-out -ExpectedGitSha;
- the working-tree bytes and Git blob bytes of all three governed migration
  files;
- the fixed C035-approved SHA-256 values;
- the explicit migration order;
- the canonical server registry app.EQUIPMENT_DEFS.

The runner does not copy Equipment definitions and does not discover or run
unapproved migrations.

## Preflight contract

Preflight is sanitized and aggregate-only. It verifies:

- exact Git identity and the three migration hashes;
- PostgreSQL version;
- base schemas required by the current C026/C019 path;
- both canonical feature gates are effectively OFF;
- canonical_slot, the B033 constraint/index, and
  coin_purchase_operations are either absent in the approved legacy state
  or already valid;
- the existing D5A outbox is present and compatible;
- unknown equipped IDs, malformed equipped values, null/duplicate equipped
  slots, equipped xp_amulet, and equipped go_stone_black are zero.

Any failed or ambiguous precondition produces no migration attempt. A
partial or incompatible schema is never repaired automatically.

The runner records that no application-wide inventory mutation-freeze
mechanism exists in the repository. Future Production execution therefore
requires separately verified external traffic-freeze evidence; the runner
does not pretend to provide that freeze.

## Transaction and failure contract

Each migration has its own explicit caller-owned transaction with
autocommit disabled.

### B033

    BEGIN
    equipment_canonical_slot_v1.upgrade(
        conn,
        equipment_defs=app.EQUIPMENT_DEFS,
        dry_run=False,
    )
    validate_schema(conn)
    validate aggregate equipped-state invariants
    COMMIT

Any exception or failed postcheck rolls the B033 transaction back and stops
the sequence. The C019 migration is not attempted. A commit exception is
reported as B033_COMMIT_UNKNOWN without automatic retry.

### C019

This phase starts only after B033 has committed (or was already proven
valid):

    BEGIN
    coin_purchase_operations_v1.upgrade(conn, dry_run=False)
    validate_schema(conn)
    validate expected columns, constraints, indexes, and JSONB result payload
    COMMIT

An exception or failed postcheck rolls back only this second transaction.
B033 remains committed. The result is the explicit fail-closed state:

B033_COMMITTED_COIN_PURCHASE_FAILED

In that state, coin_purchase_operations is absent or unverified, both
canonical feature gates remain OFF, a B033-compatible runtime is required,
and rollback to the old C32 runtime is forbidden. No automatic second-phase
retry is performed.

The runner reports sanitized error class/SQLSTATE only. It never emits
credentials, URLs, player rows, or unrelated environment values.

## Disposable PostgreSQL acceptance

tests/test_c036_option_c_production_migration_runner.py uses only an
ephemeral PostgreSQL 16.14-alpine container and synthetic tables/data. The
fixture preserves the legacy Production shape:

- player_inventory.canonical_slot absent;
- B033 validity constraint/index absent;
- coin_purchase_operations absent;
- a compatible domain_event_outbox present;
- representative clean inventory state.

The focused suite covers:

- dry-run and wrong-gate no-mutation behavior;
- full ordered execution;
- second invocation / both migrations already valid;
- B033 already valid with only C019 missing;
- malformed equipped=2 preflight fail-closed behavior;
- direct B033 malformed-data rollback;
- B033 postcheck rollback;
- C019 failure/postcheck rollback preserving committed B033;
- partial-schema refusal;
- the external Production inventory-freeze requirement;
- source/hash binding and absence of a CLI database URL.

The existing focused B034, B041, C026, C029, and D024 suites remain the
post-migration downstream acceptance evidence. C036 does not alter those
authorities.

Local validation completed on the isolated candidate:

- C036 disposable PostgreSQL runner suite: 14 passed;
- B033/B034/B041/C026/C029/D024 focused regressions: 112 passed, 8 skipped;
- C030 legacy TEXT timestamp proof: 3 passed;
- C031 release-preflight suite: 22 passed;
- B040/C025/E030 runtime-contract regressions: 88 passed.

The PostgreSQL fixture uses `postgres:16.14-alpine`. The `equipped=2`
adversarial case is fail-closed: the runner's direct B033 path reports a
postcheck failure and rolls the transaction back, while normal execution
preflight rejects it before any migration attempt. No Production database
was queried or mutated.

## Future execution packet

The future operator must first obtain fresh, read-only Production evidence
that the compatible runtime is deployed, application and scheduler health
are passing, both gates are OFF, the approved legacy schema is still present,
the outbox is compatible, and the external inventory mutation freeze is
confirmed. Only then may an Owner separately grant
GO_PRODUCTION_DB_MIGRATION for the exact expected Git SHA.

That grant does not authorize deployment or feature enablement. C036 itself
performs no Production query or mutation.
