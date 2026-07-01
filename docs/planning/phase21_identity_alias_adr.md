# Phase 21: Puzzle Identity Alias ADR

## Status

Accepted as Phase 21 owner decision baseline. Production data shapes verified
2026-07-02 by read-only inspection.

## Context: Verified Facts

- Production puzzle identity today is a plain INTEGER `question_id`
  (observed values around 30000).
- `question_id` is referenced as a column in at least: `srs_cards`,
  `mistake_log`, `node_mastery`, `review_log`, `teacher_comments`,
  `question_comments`.
- `question_id` is ALSO serialized inside JSON integer arrays stored in TEXT
  columns: `challenges.question_ids` and `daily_training_queue.question_ids`.
- These tables contain live paying-user history (thousands of SRS and review
  rows). Rewriting them is high-risk surgery.
- Phase 12A decided: `canonical_puzzle_id` = ingestion-generated stable UUID v4.
- Phase 19 shadow events already carry `legacy_question_id` with
  `canonical_puzzle_id` optional, anticipating this ADR.

## Decision

1. Canonical identity is introduced as an ADDITIVE ALIAS, not a replacement.
2. Conceptual alias shape (no schema is created by this ADR):

   puzzle_identity_alias:
     question_id           integer, unique, not null
     canonical_puzzle_id   UUID v4, unique, not null
     created_at            timestamp
     note                  text (origin annotation)

3. The mapping is strictly 1:1 and IMMUTABLE once assigned.
4. UUID v4 values are generated at alias-backfill time. For the existing
   corpus, the backfill event IS the "ingestion" moment required by Phase 12A.
5. All legacy tables and JSON arrays remain UNCHANGED and continue to use
   integer `question_id`. No foreign keys are rewritten. No JSON is rewritten.
6. New systems (shadow judging events, review queue, audit events, feedback
   links) always carry `legacy_question_id`, and additionally carry
   `canonical_puzzle_id` once the alias exists.
7. `canonical_puzzle_id` must never be derived from `source_path`,
   `fixture_path`, `gold_fixture_id`, content hash, frontend temporary ID,
   runtime state, or autoincrement integer (Phase 12A / Phase 16 rules).

## What This ADR Does Not Do

- No table is created. No migration is written. No dependency is added.
- Implementation of the alias table and backfill is a future owner-authorized
  C-level task governed by the Phase 13 readiness gates (backfill plan,
  uniqueness verification, rollback plan, post-migration verification).

## Backfill Requirements (for the future C-level task)

- One row per existing production question_id; UUID generated per row.
- Uniqueness verified on both columns after backfill.
- Row count must equal the distinct question_id count.
- Rollback: the alias table is additive, so rollback = drop the table;
  nothing else references it until consumers opt in.

## Rejected Alternatives

- Replacing integer primary keys with UUIDs across all tables: touches
  paying-user SRS history and requires rewriting JSON arrays inside TEXT
  columns; highest-risk option with no near-term benefit.
- Content-hash identity: puzzle content can be repaired/edited; identity must
  survive content fixes.
- Path-based identity: files move; paths are not stable.
- Deferring identity entirely: Phase 19+ consumers need a stable target now.

## Consequences

- Phase 22 shadow hook can ship BEFORE the alias table exists
  (events carry legacy_question_id only).
- Review queue and audit records (Phase 24+) should prefer canonical_puzzle_id
  and therefore depend on the alias backfill task.
- The Phase 13 migration risk register shrinks: uuid_backfill, uniqueness,
  foreign-key, and rollback gates now apply to ONE new table instead of the
  whole schema.
