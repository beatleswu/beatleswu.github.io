# C031-R1 Commerce Production Readiness Preflight Auditor

Task: `C031_R1_RUNTIME_COMPATIBILITY_AND_AUDIT_HONESTY_CLOSURE_001`

This candidate adds one repeatable, read-only auditor for the future
Option-C Equipment plus canonical Coin Shop maintenance gate. It reports
source identity, migration-file integrity, PostgreSQL schema state, B033
equipped-row safety, explicit feature-gate facts, and the legacy-writer
compatibility contract. It does not perform a migration, enable a feature,
debit Coins, grant ownership, or decide whether an Owner may authorize a
Production database operation.

## Provenance and boundaries

| Field | Value |
| --- | --- |
| Current canonical origin/master at task start | `e10735cf580fb5074e07811f76ab60445562760c` |
| C031 source head | `c71c55f4812c070d4d5dc871f367f2f33f7284b2` |
| Tool | `scripts/release/commerce_production_readiness_preflight.py` |
| Test | `tests/test_c031_commerce_production_readiness_preflight.py` |
| Output | JSON on stdout, human summary on stderr and in `human_summary` |
| Production query during C031 | No |
| Production mutation | No |
| Schema source changed | No |
| `app.py` changed | No |
| Revenue enablement implied | No |

The tool accepts an explicit caller-supplied PostgreSQL connection. It never
falls back to `DATABASE_URL`, so invoking it without `--database-url` cannot
accidentally inspect a configured environment. The CLI requires an explicit
`--target-environment disposable|production|other`; C031 never infers
Production from a hostname. C031-R1 validation uses only a local disposable
PostgreSQL 16.14 container and synthetic data.

## Inputs

The source contract requires:

* `expected_application_source_sha` and
  `observed_application_source_sha`; they must be valid commit SHAs and equal.
* `current_master_sha`; the three canonical migration files are read from
  that Git object and compared byte-for-byte with the local checkout.
* `canonical_shop` and `canonical_equipment_loadout` gate facts. A supplied
  `OFF`/`False` passes; a supplied `ON`/`True` fails; an absent or malformed
  fact is `BLOCKED`.
* `legacy_writer_compatibility=PASS`, if supplied, is secondary caller
  evidence only. It cannot make an unsafe source tree ready.
* C030's independent legacy TEXT timestamp proof is reported as
  `legacy_text_timestamp_compatibility`; it is not used as Equipment/Shop
  runtime-writer evidence.

The current application line does not expose a dedicated canonical C-lane
feature-gate constant. Requiring the gate facts as explicit inputs keeps the
auditor from inferring that a route is off merely because a symbol is absent.
The future release caller must provide the observed source/runtime gate facts.

Example shape (the URL is deliberately not recorded in output):

```powershell
$sha = git rev-parse origin/master
$env:PYTHONPATH = "."
python scripts/release/commerce_production_readiness_preflight.py `
  --database-url $DisposablePostgresUrl `
  --expected-application-source-sha $sha `
  --observed-application-source-sha $sha `
  --current-master-sha $sha `
  --target-environment disposable `
  --canonical-shop-gate OFF `
  --canonical-equipment-loadout-gate OFF `
  --legacy-writer-compatibility PASS `
  --expected-postgres-version "PostgreSQL 16.14" `
  > c031-preflight.json
```

The JSON result includes a human summary, machine-readable check records,
source provenance, truthful target/query metadata, and a mutation guard with
observed query count plus zero writes, commits, rollbacks, and migration
executions. Credentials and URLs are not emitted.

## Status semantics

* `READY_FOR_OPTION_C_MAINTENANCE`: all supplied source, runtime-seam, gate,
  and database checks pass.
* `NOT_READY`: the database is reachable but a required table, column,
  migration contract, B033 invariant, equipped-row rule, or gate is not ready.
* `BLOCKED`: an identity/evidence input is absent or contradictory, the
  source contract cannot be inspected, the migration Git object is unavailable,
  or no database connection was supplied. No release conclusion is inferred
  from missing evidence.

`GO_PRODUCTION_DB_MIGRATION` is always reported as
`DEFERRED_TO_OWNER_COORDINATOR`. The auditor does not grant that gate.

## Checks

### Source and release policy

The auditor checks:

* expected versus observed application source SHA;
* literal `app.EQUIPMENT_DEFS` source readability without importing or
  executing `app.py`;
* canonical Shop gate `OFF`;
* canonical Equipment loadout gate `OFF`;
* C030 legacy TEXT timestamp evidence separately from runtime-writer
  compatibility;
* AST/source-contract evidence for Monster -> B040, Admin -> B040,
  Equipment route -> B034/B041 exact ownership-row semantics, and canonical
  Shop -> C025/C029 -> C026 -> D024;
* default-OFF source gates for canonical Shop and canonical Equipment loadout;
* SHA-256 equality of these current-master migration files:
  `migrations/equipment_canonical_slot_v1.py`,
  `migrations/coin_purchase_operations_v1.py`, and
  `migrations/domain_event_outbox_v1.py`;
* the fact that C031 has no Revenue enablement or mutation path.

### PostgreSQL and ownership state

All database operations are metadata or `SELECT` reads. The audit covers:

* PostgreSQL version;
* `user_stats.coins`;
* required columns for `currency_log`, `player_inventory`,
  `shop_inventory`, and `player_wardrobe`;
* `player_inventory.canonical_slot` presence;
* B033 validity constraint and partial unique equipped-slot index;
* equipped `xp_amulet` count and equipped `go_stone_black` count, both expected
  to be zero;
* duplicate equipped `(user_id, canonical_slot)` groups;
* unknown, null-slot, invalid-slot, slot-mismatch, locked-item, and duplicate
  malformed equipped rows;
* compatible `coin_purchase_operations` schema;
* compatible `domain_event_outbox` schema for D5A lineage;
* `currency_log.created_at`, `player_inventory.obtained_at`, and
  `player_wardrobe.obtained_at` type observations. `TEXT` remains an accepted
  observation because C030 proved the current C026 writer against that
  legacy shape; C031 does not alter it.

## Read-only database hardening and no migration decision

Presence of `coin_purchase_operations` or B033 state is reported as a fact.
The tool does not run `upgrade`, `ALTER`, `CREATE`, `DROP`, `INSERT`,
`UPDATE`, `DELETE`, `TRUNCATE`, `COMMIT`, or `ROLLBACK`. Its source probe
rejects every SQL keyword other than `SELECT` and `WITH`. The CLI configures a
psycopg2 connection read-only when supported; a failure is reported rather
than assumed safe. The JSON reports `TARGET_ENVIRONMENT`,
`DATABASE_QUERY_PERFORMED_BY_C031`, `PRODUCTION_QUERY_PERFORMED_BY_C031`, and
`mutation_guard.database_queries` from actual execution. Connection cleanup is
not treated as an application mutation. It does not decide whether the schema
is authorized for Production installation. The Owner and Master Coordinator
retain the separate database-migration gate.

## Test evidence

`tests/test_c031_commerce_production_readiness_preflight.py` covers:

1. source contract and current-master migration SHA checks;
2. application identity mismatch fail-closed behavior;
3. missing connection blocked behavior with no database query;
4. AST-only Equipment definition loading without executing `app.py`;
5. current-master legacy routes remaining `NOT_READY` despite caller-supplied
   `legacy_writer_compatibility=PASS`;
6. a future-ready in-memory source fixture proving all four runtime seams and
   default-OFF gates without changing `app.py`;
7. a disposable PostgreSQL 16.14 schema fixture with all accepted migrations,
   legacy `TEXT` timestamp columns, B033 constraints/indexes, and an explicit
   SELECT-only connection probe;
8. truthful no-query, disposable-query, production-label-only, and `other`
   target metadata;
9. an incompatible empty-schema fixture classified as `NOT_READY`.

The disposable fixture is synthetic and is removed in fixture teardown. No
Production hostname, database, credentials, or user data is used.

## Future release interpretation

`READY_FOR_OPTION_C_MAINTENANCE` means that the inspected state and
source-verified runtime seams satisfy this auditor's read-only contract. The
pre-E030 current master is expected to be `NOT_READY` because the route seams
are not yet integrated. It does not mean:

* the Shop route is wired;
* the canonical Coin purchase feature is enabled;
* a database migration is approved or executed;
* Revenue is live;
* deployment is approved or performed.
