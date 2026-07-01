# Teacher Review Queue Read Model Contract Baseline

## Status

Planning / contract baseline only.

This document defines a future contract baseline for a teacher/admin-facing review queue read model. It does not implement runtime behavior, database schema, API routes, frontend UI, production queue behavior, READY promotion, SGF byte changes, production overrides, or SGF engine judging semantics.

## Purpose

The review queue read model is a teacher/admin-facing projection that helps teachers find, understand, prioritize, and review puzzle issues without understanding SGF engine internals, override schema, or fixture metadata.

The read model must be simple for teachers, while keeping high-risk production actions behind guarded C-level flows.

## Entry points

The future teacher admin workflow has two review entry points.

### 1. Passive backend review queue

Teachers/admins can centrally review items such as:

- needs review
- owner decision pending
- feedback reported
- disabled candidate-only items
- visual SGF validation items
- taxonomy review items
- difficulty review items

### 2. Active frontend answer-page admin triage

Teachers/admins can flag or send a puzzle into review flow directly from the answer page when they encounter an issue during real usage.

This active entry point is for triage and review intake. It must not bypass high-risk guarded flows.

## Identity binding

Every future review queue item must point to `canonical_puzzle_id`.

The read model may include `source_locator` and `fixture_reference` for debugging and traceability, but these must not be the primary identity.

A `review_queue_item_id` identifies the workflow item. It does not replace `canonical_puzzle_id`.

A `feedback_report_id` identifies a feedback event. It does not replace `canonical_puzzle_id`.

## Proposed read model fields

Future read model fields may include:

- `review_queue_item_id`
- `canonical_puzzle_id`
- `content_revision_id`
- `source_locator`
- `fixture_reference`
- `teacher_facing_status`
- `review_reason`
- `domain_tags`
- `difficulty_band`
- `reported_by`
- `reported_from_entrypoint`
- `created_at`
- `updated_at`
- `owner_decision_status`
- `owner_decision_trace_ref`
- `risk_level`
- `allowed_low_risk_actions`
- `blocked_high_risk_actions`
- `visual_sgf_card_ref`

This list is a contract baseline, not a production schema.

## Teacher-facing status candidates

The final status taxonomy is not decided in this baseline.

Future candidates may include:

- `needs_review`
- `owner_decision_pending`
- `feedback_reported`
- `visual_validation_needed`
- `candidate_only_disabled`
- `ready_readonly`
- `blocked_high_risk_change`
- `resolved_no_action`
- `resolved_owner_approved`

## Low-risk actions

Future low-risk teacher actions may include:

- add teacher note
- add custom tag
- mark as needs review
- assign review reason
- link duplicate report
- close false-positive feedback as no action

Low-risk actions must not change SGF engine judging semantics, SGF bytes, READY status, production overrides, or canonical identity.

## High-risk guarded actions

The following actions must remain behind guarded C-level flows:

- READY promotion
- production override activation
- SGF bytes modification
- SGF engine judging semantics change
- candidate-only answer activation
- canonical identity migration

## Active frontend answer-page guardrails

Active frontend answer-page admin triage must not:

- activate candidate-only answers
- promote disabled puzzles to READY
- activate production overrides
- modify SGF bytes
- change SGF engine judging semantics
- bypass high-risk guarded flow

## Explicit non-goals

This baseline does not:

- implement review queue storage
- implement DB schema
- implement API routes
- implement frontend UI
- implement WGo.js review UI
- modify SGF bytes
- modify READY_IDS
- modify `puzzle_variation_overrides.json`
- modify SGF engine production code
- promote GF-003
- activate B[sd] / T16
- activate production overrides
