# Puzzle Identity Alias Migration and Rollback Contract

Status: implementation prepared for local/test verification. Production
migration and backfill are **PENDING A SEPARATE OWNER GATE**.

## Scope

The additive schema migration is implemented by
`migrations.puzzle_identity_alias_v1`:

```python
upgrade(conn)
downgrade(conn, allow_destructive=False)
```

Importing the module has no side effects. Neither function is wired into
`app.init_db()`, the scheduler, an entrypoint, a build, a deploy, or a rollback
script.

## Upgrade contract

`upgrade(conn)` creates only `puzzle_identity_alias` and its diagnostic index:

| Column | Contract |
|---|---|
| `record_index` | non-negative integer; first member of the alias key |
| `legacy_question_id` | integer; second member of the alias key; not globally unique |
| `canonical_puzzle_id` | lowercase RFC-4122 UUIDv4 text; globally unique |
| `created_at` | insertion timestamp; never refreshed by backfill |

The primary key is `(record_index, legacy_question_id)`. The unique canonical
UUID constraint enforces one canonical identity per source record. The
`legacy_question_id` index is intentionally non-unique and is diagnostic only.
There are no foreign keys and no cascade behavior.

The SQL uses portable DB-API statements supported by the repository's
PostgreSQL wrapper and disposable SQLite tests. Upgrade is additive and
idempotent at the object-creation level. It commits on success and rolls back
its transaction on failure.

## Backfill contract

Backfill is a separate offline operation:

1. Use an isolated local/test database populated only with synthetic fixtures.
2. Run `upgrade(conn)` explicitly.
3. Validate the governed input population and enumerate its exact
   `(record_index, legacy_question_id)` keys.
4. For each missing key, mint one lowercase UUIDv4 and insert it.
5. On a key conflict, keep the existing row byte-for-byte unchanged. Never use
   an upsert that updates a UUID or metadata.
6. Snapshot the mappings, run backfill again, and verify that the snapshot is
   identical and the second inserted count is zero.

The command must not default to a Production connection, copy a Production
database, print a connection string, or claim a Production row count.

## Read-only runtime contract

Runtime lookup performs an exact, bounded `SELECT` using both primary-key
columns when both key members are available. When only a legacy ID is
available, a second bounded `SELECT ... LIMIT 2` resolves it only if exactly
one alias row exists. Zero or multiple rows are not canonical evidence.
Missing, ambiguous, invalid, or failed lookup returns
`canonical_puzzle_id=null` and `invalid_identity=true`; it never inserts an
alias and never changes the Legacy answer.

## Normal application rollback

Normal image/application rollback must:

- leave PostgreSQL untouched, consistent with the canonical rollback runbook;
- leave the alias table and every mapping intact;
- avoid invoking `downgrade`;
- allow an older application version to ignore the additive table; and
- preserve the same UUIDs for a later re-deploy/backfill.

This is the rollback-survival mechanism: the schema has no dependency on an
application version and the normal rollback path performs no database action.

## Destructive downgrade

`downgrade(conn)` refuses by default. Passing `allow_destructive=True` is a
code-level guard intended for disposable local/test verification or a future,
separately owner-approved destructive procedure. The argument is not itself
owner authorization.

Dropping `puzzle_identity_alias` destroys canonical history. It is never part
of `GO_DEPLOY`, image rollback, application rollback, or ordinary incident
recovery. No Production downgrade is authorized by this change.

## Review checklist

- Migration is imported and invoked explicitly; it cannot auto-run.
- Composite primary key and canonical UUID uniqueness are present.
- UUID format, version 4, RFC variant, and lowercase canonical form are checked.
- Legacy-ID index is non-unique.
- Repeated backfill does not update existing rows.
- Resolver statements contain no insert/update/delete operation.
- Normal rollback leaves mappings queryable.
- Destructive downgrade is refused without the explicit function argument.
- Production actual migration/backfill count remains `PENDING OWNER-GATED DEPLOYMENT`.
