# Phase 13A Teacher Admin Review Queue Implementation Readiness Map

Phase: 13A  
Status: Readiness contract baseline  
Scope: Planning / contract baseline only  
Runtime impact: None  
Database impact: None  
API impact: None  
Frontend impact: None  
SGF corpus impact: None  

## Purpose

This readiness map defines the checkpoints that must be satisfied before any future C-level implementation of the teacher admin review queue, canonical puzzle identity persistence, DB migration, API exposure, or frontend review UI begins.

Phase 13A is not an implementation phase.

It is an execution-oriented guardrail that turns future implementation readiness into explicit, reviewable, and testable contract markers.

## Current Baseline

Phase 12A accepted the owner decision:

```text
canonical_puzzle_id = ingestion-generated stable UUID v4
```

Phase 12B established the review queue state transition contract, including the blocked direct transition:

```text
candidate_only_disabled -> ready_readonly = blocked direct transition
```

Phase 13A builds on those contracts without implementing runtime, database, API, or frontend behavior.

## Required Readiness Checkpoints Before C-Level Implementation

Before starting any future C-level implementation, all of the following checkpoints MUST be satisfied:

```text
owner_approval_gate
db_schema_design_gate
uuid_backfill_plan_gate
uniqueness_constraint_plan_gate
foreign_key_reference_plan_gate
rollback_plan_gate
post_migration_verification_gate
api_contract_review_gate
frontend_review_flow_safety_gate
sgf_engine_non_regression_gate
gf003_candidate_only_safety_gate
```

## Checkpoint Definitions

### owner_approval_gate

The owner must explicitly authorize the implementation phase in the same work cycle.

Planning documents and contract tests are not enough to begin runtime, DB, API, or frontend implementation.

### db_schema_design_gate

A future DB schema design must be reviewed before migration.

The design must identify where `canonical_puzzle_id` is persisted, how it is indexed, and how it relates to review queue records.

This phase does not create the DB schema.

### uuid_backfill_plan_gate

Any existing puzzle records must have a deterministic operational plan for assigning new UUID v4 values during migration.

The plan must avoid duplicate IDs and must preserve puzzle record identity once generated.

This phase does not perform backfill.

### uniqueness_constraint_plan_gate

A future implementation must define how uniqueness of `canonical_puzzle_id` will be enforced and verified.

This phase does not add a unique constraint.

### foreign_key_reference_plan_gate

A future implementation must define how review queue records, feedback reports, owner decision traces, and future frontend references will point to canonical puzzle identity.

This phase does not create foreign keys.

### rollback_plan_gate

A future implementation must define rollback or recovery steps before migration begins.

Rollback planning must include what can be safely reverted and what requires forward-fix strategy.

This phase does not write rollback scripts.

### post_migration_verification_gate

A future implementation must define post-migration checks, including record count checks, UUID uniqueness checks, orphan reference checks, and GF-003 safety checks.

This phase does not run migration verification.

### api_contract_review_gate

A future API contract must be reviewed before exposing `canonical_puzzle_id` or review queue state through backend endpoints.

This phase does not add API endpoints.

### frontend_review_flow_safety_gate

A future frontend or active answer-page admin triage flow must be reviewed against the Phase 12B state transition contract.

Teacher-facing flows must not allow unsafe one-click activation of candidate-only disabled items.

This phase does not add frontend UI.

### sgf_engine_non_regression_gate

A future implementation must prove that SGF engine judging semantics are unchanged unless separately authorized.

This phase does not change SGF engine behavior.

### gf003_candidate_only_safety_gate

GF-003 / `431.sgf` must remain disabled and candidate-only unless a future C-level implementation is explicitly authorized by the owner.

B[sd] / T16 must not become active through teacher review queue implementation, active frontend triage, migration, or READY promotion.

## Review Queue Entry Point Readiness

Future review queue implementation may support two entry points:

```text
passive_backend_review_queue
active_frontend_answer_page_admin_triage
```

Both entry points must respect the same state transition contract.

Allowed teacher/admin actions may include:

```text
report_issue
mark_visual_validation_needed
send_to_review
close_as_resolved_no_action
add_review_note
route_high_risk_request_to_owner_decision
```

Blocked teacher/admin direct actions must include:

```text
directly_activate_candidate_only_variation
directly_promote_disabled_item_to_READY
directly_modify_SGF_bytes
directly_create_runtime_override
directly_create_production_override
directly_change_SGF_engine_judging_semantics
```

## Future Data Shape Readiness

A future review queue item is expected to reference a stable `canonical_puzzle_id`.

The future data shape must preserve these contract expectations:

```text
canonical_puzzle_id is UUID
review queue status is explicit
state transitions follow Phase 12B
high-risk changes require owner decision
candidate_only_disabled cannot directly become ready_readonly
owner decision trace is preserved
```

This readiness map does not create a production model, DB schema, migration, API field, or frontend component.

## Current Phase Non-Goals

Phase 13A does not implement:

```text
runtime behavior
DB schema
DB migration
SQLAlchemy model
Alembic migration
API endpoint
backend queue model
frontend component
WGo.js review UI
production model
teacher_admin runtime package
production override activation
runtime override activation
READY promotion
SGF byte editing
SGF engine judging semantic changes
```

## Merge Policy

This phase is docs + tests only, but it prepares future C-level implementation.

PR may be created after tests and safety audit pass.

Do not auto-merge.

Owner review is required before merge.
