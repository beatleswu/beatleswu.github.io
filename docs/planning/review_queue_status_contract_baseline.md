# Review Queue Status Contract Baseline

## Status

Planning / contract baseline only.

## Purpose

This document defines a future teacher/admin-facing review queue status contract.

## Status model

A future review queue item may expose teacher-facing status values such as:

- `needs_review`
- `owner_decision_pending`
- `feedback_reported`
- `visual_validation_needed`
- `candidate_only_disabled`
- `ready_readonly`
- `blocked_high_risk_change`
- `resolved_no_action`
- `resolved_owner_approved`

## Identity binding

Every future review queue item must bind to `canonical_puzzle_id`.

`review_queue_item_id` identifies the workflow item only.
It does not replace `canonical_puzzle_id`.

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
