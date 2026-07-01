# Review Queue State Transition Contract

## Status

Planning / contract baseline only.

## Purpose

This document defines a future teacher/admin-facing review queue state transition contract.

## State model

A future review queue item may expose teacher-facing states such as:

- `needs_review`
- `feedback_reported`
- `visual_validation_needed`
- `candidate_only_disabled`
- `owner_decision_pending`
- `blocked_high_risk_change`
- `resolved_no_action`
- `resolved_owner_approved`
- `resolved_rejected`
- `ready_readonly`

## Identity binding

Every future review queue item must bind to `canonical_puzzle_id`.

`review_queue_item_id` identifies the workflow item only.
It does not replace `canonical_puzzle_id`.

## Allowed low-risk transitions

The following teacher-facing low-risk transitions may be allowed in the future:

- `feedback_reported` -> `needs_review`
- `feedback_reported` -> `resolved_no_action`
- `visual_validation_needed` -> `needs_review`
- `needs_review` -> `owner_decision_pending`
- `needs_review` -> `resolved_no_action`

## Guarded high-risk transitions

The following transitions remain guarded C-level flows:

- `owner_decision_pending` -> `resolved_owner_approved`
- `owner_decision_pending` -> `resolved_rejected`
- `blocked_high_risk_change` -> `owner_decision_pending`

## Blocked direct transitions

The following direct transitions must remain blocked:

- `candidate_only_disabled` -> `ready_readonly` = blocked direct transition
- `feedback_reported` -> `ready_readonly` = blocked direct transition
- `needs_review` -> `ready_readonly` = blocked direct transition
- `visual_validation_needed` -> `ready_readonly` = blocked direct transition

A candidate-only disabled item MUST NOT be promoted directly to `ready_readonly`.

B[sd] / T16 remains candidate-only.

## Guardrails

Teacher-facing low-risk status operations must not:

- activate production overrides
- promote READY
- modify SGF bytes
- change SGF engine judging semantics
- migrate canonical identity

## High-risk flows

The following remain guarded C-level flows:

- READY promotion
- production override activation
- canonical identity migration
- SGF byte modification
- SGF engine semantics change

## Non-goals

This baseline does not implement:

- DB schema
- DB migration
- API routes
- frontend UI
- queue storage
- runtime status mutation
- production override activation
- READY promotion
