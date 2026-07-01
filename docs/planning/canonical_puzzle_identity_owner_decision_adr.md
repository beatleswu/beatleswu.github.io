# Canonical Puzzle Identity Owner Decision ADR

## Status

Accepted owner decision.

## Decision

Future production `canonical_puzzle_id` is defined as an ingestion-generated stable UUID v4.

## Rationale

The canonical puzzle identity must be durable and must not depend on mutable file paths, fixture metadata, frontend temporary IDs, runtime state, or content hash alone.

## Stability rule

Once a future production `canonical_puzzle_id` is generated for a puzzle record, it must remain stable across:

- source file moves
- source file renames
- fixture path changes
- gold fixture metadata changes
- frontend sessions
- runtime attempts
- review queue lifecycle
- feedback lifecycle
- owner decision lifecycle

## Rejected identity sources

The following must not be used as canonical puzzle identity:

- `source_path`
- `fixture_path`
- `gold_fixture_id`
- frontend temporary ID
- runtime state
- content hash

## Notes

`content_revision_id` may exist separately in the future, but it does not replace `canonical_puzzle_id`.

## Non-goals

This Phase 12A ADR does not implement:

- runtime ingestion
- DB schema
- DB migration
- API fields
- frontend fields
- review queue storage
- production override activation
- READY promotion
- SGF byte changes
