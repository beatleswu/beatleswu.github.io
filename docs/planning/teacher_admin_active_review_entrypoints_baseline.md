# Teacher Admin Active Review Entry Points Baseline

## Scope

This planning note records future entry points for teacher-admin review work.

This is docs-only groundwork.

This PR does not implement frontend answer-page admin triage.

This PR does not add UI buttons.

This PR does not add API routes.

This PR does not add DB tables.

This PR does not add fake app.py.

This PR does not implement review queue.

This PR does not define final canonical puzzle identity.

This PR does not change runtime behavior.

## Two Review Entry Points

Future teacher-admin review should support two complementary entry points.

### Passive backend review queue

- issue enters a passive backend review queue
- queue surfaces needs review items
- queue surfaces owner decision pending items
- queue surfaces feedback reported items
- teacher reviews the item from a backend review surface

### Active frontend answer-page admin triage

- admin or teacher account is on the frontend answer page
- account notices a puzzle issue in context
- account opens admin triage directly from the answer page
- account can mark review status, add a review note, or propose a candidate-only
  follow-up
- account should not need to leave the answer page to start review flow

These remain future product backlog entry points only.

## Active Answer-Page Admin Actions Backlog

The following are future owner backlog items only:

- mark needs review
- add teacher review note
- mark false alarm
- mark candidate issue
- propose canonical answer correction
- propose candidate answer
- view owner decision queue linkage
- view canonical answer
- view proposed candidate answer
- view current production override status
- view source traceability metadata

This PR does not implement any action.

## Safety Boundary For Active Entry Point

Future active frontend answer-page admin triage must remain safety-bounded:

- candidate-only actions may be active
- disabled metadata may be visible
- READY promotion requires a future C-level guarded flow
- production override activation requires a future C-level guarded flow
- SGF bytes changes require a future C-level guarded flow

Active answer-page admin triage must not directly activate READY, production overrides,
or SGF byte changes.

## Visual SGF Tie-In

Future active frontend answer-page admin triage should stay connected to visual SGF
review.

The answer page should let a teacher inspect:

- the current board context
- canonical answer
- proposed candidate answer
- puzzle status and review note context

Future implementation should likely reuse the existing WGo.js basis.

This PR does not implement WGo.js UI.

This PR does not add frontend.

## Canonical Identity Requirement

Any future active review action or passive review queue item must bind strongly to a
stable canonical puzzle identity.

The formal canonical puzzle identity definition remains a future C-level identity and
API decision.

The following are not canonical puzzle identity:

- `source_path`
- `fixture_path`
- `gold_fixture_id`
- temporary review item ID
- transient runtime state

This PR only allows `source_path`, `fixture_path`, and `gold_fixture_id` to appear as
traceability metadata.

No future active review or feedback flow should bind to mutable file paths or
temporary runtime state.

## Explicit Non-Actions

This PR does not implement frontend answer-page admin triage.

This PR does not add UI buttons.

This PR does not add API routes.

This PR does not add DB tables.

This PR does not add fake app.py.

This PR does not implement review queue.

This PR does not define final canonical puzzle identity.

This PR does not change runtime behavior.

This PR only documents active review entry point requirements and tests future
boundaries.
