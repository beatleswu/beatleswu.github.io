# Phase 17A-D: Teacher Admin Domain Contract Pack

## Status

Accepted as Phase 17A-D planning / contract baseline.

## Scope

Phase 17A-D is docs/tests-only.
Phase 17A-D does not add DB/API/backend/frontend UI.
Phase 17A-D does not add production persistence.
Phase 17A-D does not add SQLAlchemy or Alembic.
Phase 17A-D does not modify SGF engine judging semantics.
Phase 17A-D defines teacher admin domain contracts before implementation.

## Non-Goals

No production DB schema.
No migration.
No SQLAlchemy dependency.
No Alembic dependency.
No API endpoint.
No backend runtime service.
No frontend UI.
No WGo.js implementation change.
No SGF byte change.
No READY_IDS change.
No override activation.
No GF-003 activation.
No production review queue storage.

## Phase 17A: Review Queue Domain Model Contract

Phase 17A defines conceptual teacher review queue states:

- `ready_readonly`
- `needs_review`
- `pending_owner_decision`
- `candidate_only_disabled`
- `feedback_reported`
- `visual_validation_needed`
- `archived`
- `closed`

Required meanings:

- `ready_readonly` means current production-ready puzzle truth is read-only from normal teacher UI.
- `needs_review` means the item needs teacher or owner review but has not changed production truth.
- `pending_owner_decision` means an owner decision is required before truth-changing action.
- `candidate_only_disabled` means candidate evidence exists but must remain inactive.
- `feedback_reported` means a teacher/admin/user report exists.
- `visual_validation_needed` means visual board/context review is needed.
- `archived` means removed from active queue without deleting audit history.
- `closed` means no active queue work remains, without deleting audit history.

Required blocked transitions:

- `candidate_only_disabled -> ready_readonly` direct transition is blocked.
- `pending_owner_decision -> ready_readonly` direct transition is blocked unless future C-level guarded flow exists.
- `feedback_reported -> ready_readonly` direct transition is blocked if it changes production truth.
- `archived` / `closed` must not delete owner decision trace.

## Phase 17B: Teacher Action Permission Matrix

Low-risk teacher/admin actions are allowed only when they do not change production truth:

- `add_review_note`
- `add_teacher_tag`
- `set_needs_review`
- `set_visual_validation_needed`
- `escalate_to_owner_decision`
- `archive_without_truth_change`
- `close_without_truth_change`
- `mark_false_positive_without_truth_change`
- `link_feedback_report`

Low-risk actions may update review metadata only.
Low-risk actions must not modify SGF bytes.
Low-risk actions must not modify READY_IDS.
Low-risk actions must not modify `puzzle_variation_overrides.json`.
Low-risk actions must not activate runtime or production overrides.
Low-risk actions must not change judging semantics.
Low-risk actions must not promote candidate-only items to READY.

Guarded / future C-level actions:

- `promote_to_ready`
- `activate_candidate_solution`
- `enable_GF003`
- `allow_B_sd_T16_active`
- `modify_SGF_bytes`
- `modify_READY_IDS`
- `modify_puzzle_variation_overrides_json`
- `add_runtime_override`
- `add_production_override`
- `change_judging_semantics`
- `create_production_DB_schema`
- `add_API_or_UI_runtime`

These actions require future owner-authorized C-level guarded flow.
They are not implemented in Phase 17A-D.
They cannot be triggered by normal teacher UI.

## Phase 17C: Owner Decision Trace / Audit Event Contract

Owner decision trace is append-only by default.
Audit event history is append-only by default.
Teacher-facing queue actions must not silently delete audit history.
Archive and close actions hide queue work from active views but preserve trace.
Future production audit events should record who, what, when, why, previous status, next status, entry point, and affected `canonical_puzzle_id`.
Phase 17A-D does not implement auth, audit tables, persistence, API, or UI.

Suggested future event fields:

- `event_id`
- `canonical_puzzle_id`
- `actor_id`
- `actor_role`
- `action`
- `previous_status`
- `next_status`
- `reason`
- `entry_point`
- `created_at`
- `related_feedback_id`
- `related_owner_decision_id`

These fields are conceptual contract fields only.
No production schema is created in Phase 17A-D.

## Phase 17D: Active Frontend Admin Triage Contract

Active frontend admin triage is an entry point from the answer page.
It may create feedback reports.
It may add review notes.
It may mark a puzzle as `needs_review`.
It may mark `visual_validation_needed`.
It may escalate to `pending_owner_decision`.
It may archive or close only when no production truth changes.
It must preserve `canonical_puzzle_id`.
It must preserve owner decision trace.

It must not directly promote to READY.
It must not directly activate candidate-only solutions.
It must not enable GF-003.
It must not allow `B[sd]` / `T16` as active.
It must not write `puzzle_variation_overrides.json`.
It must not modify SGF bytes.
It must not change READY_IDS.
It must not change judging semantics.
It must not add runtime or production overrides.

Future visual review UI should prefer existing WGo.js board foundations.
Phase 17A-D does not implement or modify WGo.js.

## Canonical Puzzle Identity Boundary

`canonical_puzzle_id` is an ingestion-generated stable UUID v4.
`canonical_puzzle_id` is generated at corpus ingestion / import time.
`canonical_puzzle_id` remains stable after assignment.
Review queue items must refer to `canonical_puzzle_id`.
Active frontend triage must preserve `canonical_puzzle_id`.
`canonical_puzzle_id` must not depend on `source_path`.
`canonical_puzzle_id` must not depend on `fixture_path`.
`canonical_puzzle_id` must not depend on `gold_fixture_id`.
`canonical_puzzle_id` must not depend on frontend temporary ID.
`canonical_puzzle_id` must not depend on runtime state.
`canonical_puzzle_id` must not use content hash as primary identity.
`canonical_puzzle_id` must not use autoincrement integer as primary identity.

## GF-003 / Override Safety Boundary

GF-003 remains disabled.
`B[sd]` / `T16` remains candidate-only.
`B[sf]` / `T14` remains the canonical SGF answer for GF-003.
No runtime override is added.
No production override is added.
`puzzle_variation_overrides.json` remains unchanged.
READY_IDS remains unchanged.
No SGF bytes are changed.
No judging semantics are changed.

## Future C-Level Triggers

Any of the following must be future owner-authorized C-level tasks:

- Production review queue persistence.
- Production DB schema.
- SQLAlchemy introduction.
- Alembic introduction.
- Migration creation.
- API implementation.
- Frontend UI implementation.
- WGo.js review UI implementation.
- Runtime review queue behavior.
- READY promotion.
- GF-003 enablement.
- `B[sd]` / `T16` activation.
- Production override activation.
- Runtime override activation.
- SGF byte modification.
- Judging semantics change.

## Test Contract

Phase 17A-D tests use a test-local contract/tripwire.
Tests must not parse ADR prose.
Tests must not import SQLAlchemy.
Tests must not import Alembic.
Tests must not connect to a DB.
Tests must not create a physical `.db` file.
Tests must not import or modify production `sgf_engine` code.
Future C-level work must intentionally update these contract constants if it changes the boundary.
