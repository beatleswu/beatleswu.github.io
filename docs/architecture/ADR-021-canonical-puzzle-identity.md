# ADR-021: Canonical Puzzle Identity

## Status

Accepted. Originally owner-confirmed 2026-07-09 and reconfirmed by the owner
on 2026-07-17 for SGF Engine V1 closure.

This document restores the accepted contract recorded at historical commit
`4839a065759420c18a0da1140cf5c4c6747ad3bb` and makes the implementation and
rollback rules explicit. The duplicate counts below are historical evidence
from that decision; they were not re-measured from protected corpus data during
the 2026-07-17 implementation.

## Context

The corpus was reported to contain 41,591 records on 2026-07-09 and to identify
puzzles with a legacy numeric question ID. That ID is not a reliable canonical
identity:

- 12 legacy IDs were reported duplicated across records. Examples recorded in
  the accepted decision include `70450`, `63382`, `71240`, `71238`, and `62011`,
  each appearing twice.
- Shadow Judging events carried `legacy_question_id` but no stable canonical
  join key.
- Teacher repair can change SGF bytes. An identity derived from content would
  therefore change during a repair and break historical joins and override
  bindings.

Content-addressed identity and legacy-ID identity were both rejected. Content
hashes describe a version or support duplicate analysis; they do not identify
the enduring puzzle.

## Decision

1. `canonical_puzzle_id` is an ingestion-generated UUID version 4. It is minted
   once and is never derived from the legacy ID, SGF bytes, a content hash, a
   route, or a gameplay mode.
2. The canonical alias key is exactly:

   ```text
   (record_index, legacy_question_id)
   ```

   `record_index` is the record position in the governed ingestion population;
   `legacy_question_id` is retained as the paired legacy alias. Neither member
   is sufficient by itself.
3. Each composite alias key maps to one canonical UUID, and each canonical UUID
   maps to one composite alias key. `canonical_puzzle_id` is therefore unique.
4. `puzzle_identity_alias` is the only canonical mapping source. Route-local
   maps, SGF hashes, and caches may not become alternative identity sources.
5. Rating Test, Daily Challenge, Friend Challenge, Adventure, and any other
   mode resolve the same source record through the same composite alias. Route
   or mode is never part of puzzle identity.
6. `legacy_question_id` may be indexed for diagnostics, but that index is
   deliberately non-unique and may not be used as proof of identity.
7. `puzzle_version_id` and `sgf_sha256` remain version/fingerprint material
   only. They must not substitute for `canonical_puzzle_id`.

## Exact lookup and fail-safe fallback

The preferred request-path input is the exact composite alias key. Where a
legacy path carries only `legacy_question_id`, the resolver may return a UUID
only when the alias table contains exactly one row with that legacy ID. Zero
rows return missing identity; two or more rows return ambiguous identity. It
must never choose the first or last duplicate or infer a record index from
route, mode, ordering, filename, or SGF content.

Missing, ambiguous, invalid, timed-out, or failed lookup resolves to:

```json
{
  "canonical_puzzle_id": null,
  "invalid_identity": true
}
```

Legacy judging continues unchanged. Request paths are read-only and never mint
or insert an alias. A cache may retain lookup results, but the alias table
remains authoritative and cache failure must fall back to the null result.

## Immutability and backfill

- UUIDs are minted only by the offline ingestion/backfill operation.
- Backfill inserts missing composite keys only. It never updates, replaces, or
  deletes an existing row, including diagnostic metadata.
- Re-running backfill against the same governed population must leave every
  existing mapping byte-for-byte unchanged.
- A changed or reordered source population requires a new ingestion review. It
  must not be treated as permission to rewrite existing aliases.
- No request-time lazy creation and no legacy-table write are permitted.

## Migration and rollback

The table is additive and has no foreign key whose cascade could remove an
alias. Migration upgrade and destructive downgrade exist as separately
reviewable operations, but neither is called by application startup.

Normal application/image rollback leaves PostgreSQL untouched and therefore
preserves `puzzle_identity_alias` and all mappings. Dropping the table is not a
normal rollback step; it requires a separate, explicit owner-approved
destructive operation. Re-deploying an older application version must not
delete or rebuild canonical identities.

No Production migration, backfill, or destructive downgrade was authorized by
the 2026-07-17 confirmation. Production state remains pending a separate owner
gate.

## Consequences

- Identity survives SGF repair and remains joinable across content versions.
- Duplicate legacy IDs become explicit ambiguous aliases rather than silent
  first/last-match choices.
- Older application versions can coexist with the additive table during a
  rollback.
- Routes without an exact, unique record identity emit invalid identity
  diagnostics while preserving the Legacy result.

## Alternatives rejected

- **SGF/content hash as canonical ID:** changes on repair.
- **Legacy question ID alone:** historically duplicated.
- **Legacy ID plus content hash:** still changes on repair.
- **Route or gameplay mode in the key:** splits one puzzle into multiple
  identities.
