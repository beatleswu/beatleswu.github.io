# C030 — C026 PostgreSQL Legacy TEXT Timestamp Compatibility Proof

Status: `OWNER_REVIEW_CANDIDATE`

This is a disposable PostgreSQL proof of the current C026 path. It does not
query Production, change runtime source, alter timestamp types, enable
Commerce, or execute a Production migration.

## Provenance and environment

- Current implementation base: `18de673fa62b82c7be0b2c89ee80dd421148bd1d`
- Branch: `codex/c030-c026-postgres-text-timestamp-compatibility`
- Disposable image: `postgres:16.14-alpine`
- Server: `PostgreSQL 16.14 on x86_64-pc-linux-musl, compiled by gcc (Alpine
  15.2.0) 15.2.0, 64-bit`
- Driver: `psycopg2 2.9.9 (dt dec pq3 ext lo64)`
- Repository adapter: `db.PostgresConnectionWrapper` over a `psycopg2`
  `DictCursor`
- Disposable container: removed after each proof run

The test owns a local loopback connection with synthetic user IDs and does not
read `DATABASE_URL` or any Production credential. `PRODUCTION_QUERY=NO`.

## Schema under test

The disposable schema used the current C026-compatible tables and current
repository migration code for:

- `migrations/coin_purchase_operations_v1.py`
- `migrations/domain_event_outbox_v1.py`
- `migrations/equipment_canonical_slot_v1.py`

The three legacy columns were deliberately created as `TEXT NOT NULL` and
verified through `information_schema.columns` before any purchase:

| Table | Column | Observed PostgreSQL type |
| --- | --- | --- |
| `currency_log` | `created_at` | `text` |
| `player_inventory` | `obtained_at` | `text` |
| `player_wardrobe` | `obtained_at` | `text` |

No `ALTER`, type conversion, or timestamp migration was used.

## Time binding

The test passes the real C026 `purchase_with_coins` path an explicit
timezone-aware Python value:

```text
type=datetime
tzinfo=UTC
value=2026-08-26T04:00:00+00:00
```

The C026 source retains timezone-aware `datetime` binding for PostgreSQL. The
current `_timestamp(conn)` calls used by Coin audit and ownership writers pass
aware `datetime` values to `psycopg2`; the PostgreSQL text columns accepted the
driver's timestamp adaptation through the real `INSERT` statements.

## Proof results

### Stackable Shop inventory

`shop_inventory` purchase `c030-stack-a` succeeded and committed:

- Coin result: `1000 -> 970`, spend `30`
- `currency_log.delta=-30`
- `currency_log.balance_after=970`
- stored `currency_log.created_at`:
  `2026-08-25 17:11:23.986029+00`
- operation status: `COMMITTED`
- same-operation replay returned the stored result
- replay left one currency log row, one inventory quantity, and balance `970`

### Functional Equipment / player inventory

`iron_sword` purchase `c030-equipment-a` succeeded and committed:

- `player_inventory.equipped=0`
- `player_inventory.canonical_slot=weapon`
- stored `player_inventory.obtained_at`:
  `2026-08-25 17:11:24.021477+00`
- stored value was returned as a non-empty Python `str`
- exact inserted row ID was captured by the current C026 insert path
- result reference was exactly `player_inventory:{row_id}`
- same-operation replay returned the original reference
- replay left one ownership row and did not debit Coins again

### Cosmetic / player wardrobe

`robe_plain` purchase `c030-wardrobe-a` succeeded and committed:

- stored `player_wardrobe.obtained_at`:
  `2026-08-25 17:11:24.048821+00`
- stored value was returned as a non-empty Python `str`
- same-operation replay was deterministic
- a distinct duplicate operation was rejected by the existing
  `REJECT_IF_OWNED` authority
- duplicate rejection left one wardrobe row and preserved the balance

### Caller rollback

A forced D5A failure after the current C026 ownership insert caused the caller
to roll back. Verification showed:

- no Coin debit persisted;
- no `currency_log` row persisted;
- no `player_inventory` row persisted;
- no purchase operation persisted; and
- no `domain_event_outbox` row persisted.

The C026 service remained caller-transaction-owned; C030 did not add commit or
rollback behavior.

## Exact failure classification

No legacy TEXT timestamp binding failure occurred.

```text
CONFIRMED_COMPATIBILITY_DEFECT=NO
POSTGRES_SQLSTATE=NONE
FAILURE_COLUMN=NONE
FAILURE_SOURCE=NONE
SOURCE_REPAIR_REQUIRED=NO
```

The observed result is compatibility proof for the tested C026 paths, not a
reason to change Production column types.

## Regression evidence

```text
C030_POSTGRES_TESTS=3 passed
C025_REGRESSION=22 passed
C026_REGRESSION=20 passed
C029_REGRESSION=27 passed
D024_REGRESSION=16 passed
C019_EXPLICIT_OFFER_CONTRACT_CHECK=1 passed
COMMERCE_COMBINED=85 passed
```

There is no standalone C019 or C027 test file in this current master checkout;
C019 offer-contract coverage is included in the C026 suite, and this C030
run is the requested PostgreSQL compatibility proof for the accepted C026
path. No C027 runtime source was changed.

## Remaining Production gates

Legacy TEXT timestamp compatibility is now proven, but this does not make the
Production schema ready. The accepted C028 gap remains:

```text
CANONICAL_COIN_PURCHASE_PRODUCTION_SCHEMA_READY=NO
CONFIRMED_PRODUCTION_SCHEMA_GAP=coin_purchase_operations
B033_PRODUCTION_MIGRATION_READY_FROM_THIS_TASK=NO
```

The C019 purchase-operation migration and the B033 canonical-slot Production
migration remain separate Owner-authorized gates. C030 performed neither.
