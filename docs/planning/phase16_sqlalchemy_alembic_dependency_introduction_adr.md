# Phase 16: SQLAlchemy / Alembic Dependency Introduction ADR

## Status

Accepted as Phase 16 planning / contract baseline.

## Context

Phase 15A established a test-local persistence boundary using Python stdlib `sqlite3` with in-memory execution only. Phase 16 records the owner decision that persistence dependency introduction remains out of scope for this phase and must not be implied by docs, tests, or local spikes.

## Decision

Phase 16 does not introduce SQLAlchemy.
Phase 16 does not introduce Alembic.
Phase 16 does not add production DB models.
Phase 16 does not add production migrations.
Phase 16 does not add DB/API/backend/frontend UI.
Phase 16 preserves the Phase 15A stdlib `sqlite3` in-memory persistence contract as the current test-local boundary.

## Decision Details

Phase 16 is limited to docs/tests-only contract work.
No production persistence runtime is added.
No production dependency stack decision is made.
No physical `.db` file is introduced.

## Dependency Introduction Policy

SQLAlchemy and Alembic may be introduced only in a future owner-authorized C-level phase.
Dependency introduction requires explicit owner authorization.
Dependency introduction must include a separate implementation plan, migration plan, rollback plan, test plan, and safety audit.
Until then, persistence contracts remain docs/tests-only or test-local `sqlite3` contracts.

## Migration Strategy

No Alembic migration is created in Phase 16.
Future migrations must be reviewed as C-level production persistence changes.
Future migrations must preserve `canonical_puzzle_id` stability.
Future migrations must not infer canonical identity from `source_path`, `fixture_path`, `gold_fixture_id`, frontend temporary ID, runtime state, content hash, or autoincrement integer.
Future production migration should prefer additive schema evolution first.
Backfill and identity-binding behavior must be explicit and test-covered.
Rollback or downgrade expectations must be documented before production migration.

## Canonical Puzzle Identity Boundary

`canonical_puzzle_id` is an ingestion-generated stable UUID v4.
`canonical_puzzle_id` is generated at corpus ingestion / import time.
`canonical_puzzle_id` remains stable after assignment.
`canonical_puzzle_id` must not depend on `source_path`.
`canonical_puzzle_id` must not depend on `fixture_path`.
`canonical_puzzle_id` must not depend on `gold_fixture_id`.
`canonical_puzzle_id` must not depend on frontend temporary ID.
`canonical_puzzle_id` must not depend on runtime state.
`canonical_puzzle_id` must not use content hash as primary identity.
`canonical_puzzle_id` must not use autoincrement integer as primary identity.

## Review Queue Deletion Policy

Review queue operational records should use soft-delete / archived / closed status semantics by default.
Teacher-facing removal should hide or close queue items, not destroy owner decision trace.
Hard deletion is not part of Phase 16.
Hard deletion, if ever needed for production maintenance, requires a future C-level guarded flow.

## Owner Decision Trace / Audit History Policy

Owner decision trace and audit history are append-only by default.
Owner decision trace must not be silently deleted by teacher-facing queue actions.
Audit history must preserve who/what/when/why style information once production identity and auth exist.
Phase 16 does not implement auth, audit tables, DB schema, or UI.

## Safety Guardrails

No SGF bytes changed.
No READY_IDS changed.
No `puzzle_variation_overrides.json` changed.
No GF-003 enablement.
`B[sd] / T16` remains candidate-only.
No runtime override added.
No production override added.
No judging semantics changed.
No production `sgf_engine` code changed.
No SQLAlchemy dependency added.
No Alembic dependency added.
No Alembic migration added.
No production DB model added.
No physical `.db` file added.
No DB/API/backend/frontend UI added.
No fake `app.py` added.

## Rejected Alternatives

Introduce SQLAlchemy immediately in Phase 16.
Introduce Alembic immediately in Phase 16.
Create production DB models before backend architecture is settled.
Use `source_path` as canonical puzzle identity.
Use `fixture_path` as canonical puzzle identity.
Use `gold_fixture_id` as canonical puzzle identity.
Use content hash as primary identity.
Use autoincrement integer as primary identity.
Hard-delete review queue records by default.
Allow teacher-facing UI to directly promote candidate-only / disabled items to READY.

## Future C-Level Triggers

Adding SQLAlchemy dependency.
Adding Alembic dependency.
Creating production DB models.
Creating migrations.
Adding production persistence runtime.
Adding DB/API/backend/frontend UI.
Changing review queue runtime behavior.
Activating production overrides.
Promoting READY_IDS.
Enabling GF-003.
Allowing `B[sd] / T16` as active.
Changing `sgf_engine` judging semantics.
Changing SGF bytes.

## Test Contract

Phase 16 enforces a docs/tests-only dependency gate.
The gate preserves the Phase 15A stdlib `sqlite3` in-memory persistence boundary.
The gate rejects Phase 16 introduction of SQLAlchemy, Alembic, production DB models, production migrations, and physical `.db` files.
The gate preserves the canonical puzzle identity boundary, review queue deletion contract, and GF-003 safety boundary until a future owner-authorized C-level task changes them.
