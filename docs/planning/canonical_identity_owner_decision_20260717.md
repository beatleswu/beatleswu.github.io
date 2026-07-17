# Canonical Puzzle Identity Owner Decision

Status: **RESOLVED — ADR-021 COMPOSITE ALIAS CONFIRMED**

Scope: SGF Engine V1 closure, identity work item only

Owner-confirmed date: 2026-07-17

Historical source: commit
`4839a065759420c18a0da1140cf5c4c6747ad3bb`,
`docs/planning/ADR-021-canonical-puzzle-identity.md`

The canonical copy is restored at
`docs/architecture/ADR-021-canonical-puzzle-identity.md`.

## Binding decision

Each immutable ingested puzzle record receives one ingestion-generated UUID
version 4. The canonical alias key is exactly:

```text
(record_index, legacy_question_id)
```

`legacy_question_id` is not globally unique. The historical audit recorded 12
duplicated IDs, including `70450`, `63382`, `71240`, `71238`, and `62011`.
The interim proposal to use `(source_namespace,
immutable_source_record_key)` was withdrawn before implementation and is not
part of the schema, resolver, or backfill.

## Runtime resolution

- When both key members are available, resolve only the exact composite key.
- When only `legacy_question_id` is available, resolve only if the alias table
  contains exactly one row for that ID.
- Zero rows are missing identity; multiple rows are ambiguous identity.
- Route, gameplay mode, corpus ordering, filename, SGF bytes, and content hash
  must never break an ambiguity or mint identity.
- Missing, ambiguous, invalid, or failed lookup emits
  `canonical_puzzle_id=null`, `invalid_identity=true`, and
  `gf003_related=false`.
- Player request paths perform SELECT-only lookups and never create aliases.

The current Rating Test, Daily Challenge, and Friend Challenge answer-session
contracts persist only the legacy ID. Their Shadow diagnostics therefore use
the unique-only fallback. A duplicated legacy ID fails closed rather than
borrowing a record index from a reconstructed pool or using the first or last
record in current corpus order. Exact composite lookup remains available only
to callers that carry both immutable key members as verified source context.

## Immutability and rollback

- `puzzle_identity_alias` is the only canonical mapping source.
- Offline backfill inserts missing mappings only and never updates or replaces
  an existing UUID.
- Repeated backfill over the same governed ingestion population must preserve
  mapping snapshots byte-for-byte.
- Normal application rollback leaves the additive table and mappings intact.
- A guarded destructive down migration exists only for review completeness;
  it is never an automatic or normal rollback step.

## Production boundary

No Production migration, backfill, database access, destructive downgrade,
GF-003 activation, SGF modification, or authoritative judging change is
authorized. Production migration and actual row count remain:

```text
PENDING OWNER-GATED DEPLOYMENT
```
