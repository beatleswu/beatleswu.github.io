# Teacher Admin MVP Readiness Baseline

## Scope

This planning note records a product and technical readiness baseline for a future
teacher-admin MVP built on the Phase 9A, 9B, and 9C groundwork.

This is not an implementation spec.

This document is docs-only groundwork.

This document does not:

- implement teacher admin MVP
- add DB, API, backend, or frontend UI
- add formal schemas
- define or implement final canonical puzzle identity
- implement a feedback queue
- change runtime behavior
- activate overrides
- promote READY
- change SGF bytes

## MVP Purpose

The future teacher-admin MVP should make review and triage safer, more auditable, and
easier to operate without hiding risky state transitions behind implicit runtime
behavior.

The MVP should help a teacher understand what is under review, what remains inactive,
what still needs owner decisions, and what would require a later high-risk workflow.

## MVP Must Eventually Include

The future MVP should eventually include:

- Review Queue
- Visual SGF Validation
- issue triage state visibility
- Domain Taxonomy filters
- Difficulty filters
- Teacher custom tags
- Feedback or issue-report queue
- owner decision trace
- low-risk batch operations
- high-risk confirmation flow

These remain future owner backlog items.

## MVP Must Not Hide

The future MVP must not hide:

- candidate-only
- disabled
- excluded
- needs review
- owner decision pending
- production override inactive or active
- canonical answer
- proposed candidate answer
- source traceability metadata

## Low, Medium, And High-Risk Operations

### Low-Risk Future Operations

Examples:

- add a review note
- mark false alarm
- mark needs review
- add a teacher-facing tag
- record a teacher-facing decision without changing runtime behavior

### Medium-Risk Future Operations

Examples:

- mark an item as review-ready in planning
- edit candidate-answer metadata
- revise teacher-facing issue grouping
- revise domain-tag metadata

### High-Risk Or C-Level Future Operations

Examples:

- READY promotion
- production override activation
- runtime override behavior
- SGF bytes modification
- engine judging semantic changes
- DB, API, backend, or frontend UI implementation
- canonical puzzle identity contract implementation
- feedback queue implementation

This PR does not authorize medium-risk or high-risk runtime operations.

This PR is limited to docs and tests baseline groundwork.

## Engineering Readiness Gates

The following still need explicit owner decisions before any C-level implementation:

- teacher admin UX flow
- permission model
- status transition rules
- review queue behavior
- domain taxonomy initial tag list
- difficulty-level final grouping
- feedback issue reason list
- WGo.js review UI integration details
- API payload shape
- DB schema
- canonical puzzle identity contract
- feedback-to-puzzle binding model
- audit and owner-decision trace model

## Future TDD Acceptance Criteria

This PR adds `pytest.mark.skip` skeleton tests as placeholders for future C-level
acceptance criteria.

These skipped tests exist to document the expected shape of future implementation.

They do not create shadow APIs, shadow workflows, or shadow schemas.

When a future C-level implementation exists, those tests can be un-skipped and turned
into active acceptance tests.

## Explicit Non-Actions

This PR does not implement teacher admin MVP.

This PR does not add DB, API, backend, or frontend UI.

This PR does not add formal schemas.

This PR does not define or implement final canonical puzzle identity.

This PR does not implement feedback queue.

This PR does not change runtime behavior.

This PR does not activate overrides.

This PR does not promote READY.

This PR does not change SGF bytes.
