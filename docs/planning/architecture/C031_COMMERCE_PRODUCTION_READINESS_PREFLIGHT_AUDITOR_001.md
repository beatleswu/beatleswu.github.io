# C031 Commerce Production Readiness Preflight Auditor

Task: `C031_COMMERCE_PRODUCTION_READINESS_PREFLIGHT_AUDITOR_001`

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
accidentally inspect a configured environment. C031 validation used only a
local disposable PostgreSQL 16.14 container and synthetic data.

## Inputs

The source contract requires:

* `expected_application_source_sha` and
  `observed_application_source_sha`; they must be valid commit SHAs and equal.
* `current_master_sha`; the three canonical migration files are read from
  that Git object and compared byte-for-byte with the local checkout.
* `canonical_shop` and `canonical_equipment_loadout` gate facts. A supplied
  `OFF`/`False` passes; a supplied `ON`/`True` fails; an absent or malformed
  fact is `BLOCKED`.
* `legacy_writer_compatibility=PASS`. The tool verifies source markers in
  `coin_purchase_authority.py` for timezone-aware timestamp handling,
  `currency_log`, `player_inventory`, and `player_wardrobe` writes. It does
  not rewrite timestamp types.

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
  --canonical-shop-gate OFF `
  --canonical-equipment-loadout-gate OFF `
  --legacy-writer-compatibility PASS `
  --expected-postgres-version "PostgreSQL 16.14" `
  > c031-preflight.json
```

The JSON result includes a human summary, machine-readable check records,
source provenance, and a mutation guard with zero writes, commits, rollbacks,
and migration executions. A database target is represented only as
`caller_supplied; not serialized`; credentials and URLs are not emitted.

## Status semantics

* `READY_FOR_OPTION_C_MAINTENANCE`: all supplied source, gate, and database
  checks pass.
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
* the supplied legacy-writer compatibility status plus current writer source
  markers;
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

## No migration decision

Presence of `coin_purchase_operations` or B033 state is reported as a fact.
The tool does not run `upgrade`, `ALTER`, `CREATE`, `DROP`, `INSERT`,
`UPDATE`, `DELETE`, `TRUNCATE`, `COMMIT`, or `ROLLBACK`. It does not decide
whether the schema is authorized for Production installation. The Owner and
Master Coordinator retain the separate database-migration gate.

## Test evidence

`tests/test_c031_commerce_production_readiness_preflight.py` covers:

1. source contract and current-master migration SHA checks;
2. application identity mismatch fail-closed behavior;
3. missing connection blocked behavior with no database query;
4. AST-only Equipment definition loading without executing `app.py`;
5. a disposable PostgreSQL 16.14 ready fixture with all accepted migrations,
   legacy `TEXT` timestamp columns, B033 constraints/indexes, and an explicit
   SELECT-only connection probe;
6. an incompatible empty-schema fixture classified as `NOT_READY`.

The disposable fixture is synthetic and is removed in fixture teardown. No
Production hostname, database, credentials, or user data is used.

## Future release interpretation

`READY_FOR_OPTION_C_MAINTENANCE` means that the inspected state and supplied
evidence satisfy this auditor's read-only contract. It does not mean:

* the Shop route is wired;
* the canonical Coin purchase feature is enabled;
* a database migration is approved or executed;
* Revenue is live;
* deployment is approved or performed.
