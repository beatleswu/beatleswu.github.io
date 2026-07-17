# Canonical Puzzle Identity Owner Decision

Status: **OWNER_DECISION_REQUIRED**

Scope: SGF Engine V1 closure, identity work item only

Date: 2026-07-17

No identity migration, backfill, resolver, or request-time write is included
until the alias key is owner-resolved. Legacy judging and all legacy data
remain unchanged.

## Conflict found during canonical preflight

The dispatched task contract asks for one immutable mapping:

```text
legacy question_id <-> canonical UUID v4 (1:1)
```

The current canonical branch does not contain the referenced ADR-021. A
preservation-only historical artifact at commit
`4839a065759420c18a0da1140cf5c4c6747ad3bb` records a different accepted
contract: legacy IDs were known to be duplicated, so aliases must be keyed by
`(record_index, legacy_question_id)`, with one UUID per corpus record.

Current application behavior reinforces that conflict:

- several runtime lookups construct dictionaries keyed only by `q['id']`, so
  duplicate legacy IDs do not retain record identity at answer time;
- corpus-review helpers explicitly use `record_index` together with
  `legacy_question_id` to disambiguate records;
- question creation allocates `max(existing id) + 1`; deleting the highest ID
  can therefore allow that numeric value to be reused later.

These observations were made from tracked code and the historical ADR only.
No `questions.json`, database, SGF bytes, or protected artifact was inspected.

## Owner decision A: supersede the historical composite key

Approve a globally unique, permanently non-reusable numeric `question_id` as
the sole alias key. This also requires owner-approved ingestion governance:

1. prove or remediate every duplicate before backfill;
2. introduce a durable allocator/tombstone rule so a deleted ID is never
   reused;
3. define how historical events distinguish records that previously shared an
   ID; and
4. explicitly supersede the historical ADR-021 decision.

Only after those prerequisites can a database uniqueness constraint safely
enforce `question_id <-> UUIDv4` one-to-one.

## Owner decision B: preserve the historical composite key

Approve `(record_index, legacy_question_id)` as the alias key. This requires
each covered answer route to obtain an immutable ingestion record identifier;
the legacy numeric ID alone is insufficient. The route adapter may perform a
bounded, read-only lookup, but must never infer record identity from SGF bytes
or lazily create an alias.

This preserves the historical decision, but the owner must define how
`record_index` survives corpus reorder/re-ingestion or replace it with another
immutable ingestion key before schema approval.

## Invariants under either decision

- UUIDs are generated once by an offline, idempotent backfill.
- The alias table is the only canonical identity source.
- Answer paths perform bounded, read-only lookups with fail-safe null fallback.
- Missing, ambiguous, or failed lookups emit
  `canonical_puzzle_id=null`, `invalid_identity=true`, and
  `gf003_related=false` while returning the unchanged Legacy result.
- No request-time alias creation and no legacy-table writes are permitted.
- Ordinary application rollback preserves the additive alias table.
- Production migration/backfill remains `PENDING OWNER-GATED DEPLOYMENT`.

## Decision requested

The owner must select A or B and approve the corresponding stable alias key
before identity implementation resumes. This is a data-identity semantic
choice; selecting it in implementation code would risk binding one UUID to
multiple puzzles or splitting one puzzle's history.
