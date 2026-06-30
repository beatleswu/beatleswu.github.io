# Puzzle Corpus And Teacher Admin Baseline

## Scope

This planning note records the current corpus-management baseline and the owner-defined
teacher-admin backlog without changing production behavior.

This document is docs-only groundwork.

This document does not:

- implement teacher admin
- add DB, API, backend, or frontend UI
- change SGF bytes
- promote any fixture into READY
- activate GF-003
- activate production overrides
- change runtime behavior
- change SGF engine judging semantics

## Current Corpus States

The current repository already distinguishes several corpus states, but the distinction
is spread across manifest fields rather than a dedicated teacher-admin model.

Current observed states:

- READY active
- candidate-only
- disabled
- needs review
- owner decision pending
- production override inactive

Observed repository evidence:

- READY active records live in `tests/sgf_engine/data/gold_fixtures/fixtures.json` under
  `fixtures` with `owner_status: READY` and `ready_for_next_test_commit: true`.
- Candidate-only records currently live under `excluded_fixtures`.
- `GF-003` is the only excluded record with disabled override metadata and a proposed
  equivalent-answer override.
- `GF-004`, `GF-006`, and `GF-007` remain `PENDING` review items, not READY fixtures.
- `puzzle_variation_overrides.json` remains `{}`, so production override behavior is inactive.

## Taxonomy Baseline

Teacher-facing language should describe metadata state and runtime state separately.

Recommended teacher-facing buckets:

- `READY`
- `EXCLUDED`
- `CANDIDATE_ONLY`
- `DISABLED`
- `NEEDS_REVIEW`
- `OWNER_DECISION_PENDING`
- `PRODUCTION_OVERRIDE_INACTIVE`
- `PRODUCTION_OVERRIDE_ACTIVE`

Current mapping guidance:

- `owner_status: READY` maps to `READY`.
- `status: CANDIDATE_REQUIRES_OVERRIDE` maps to `CANDIDATE_ONLY`.
- `status: PENDING` maps to `NEEDS_REVIEW` and `OWNER_DECISION_PENDING`.
- `runtime_status: disabled` plus `apply_automatically: false` maps to `DISABLED`.
- Empty `puzzle_variation_overrides.json` maps to `PRODUCTION_OVERRIDE_INACTIVE`.

Important boundary: metadata state is not the same thing as runtime activation.

## Safety Boundary

The current baseline must preserve these safety rules:

- Candidate metadata does not make a fixture READY.
- Disabled metadata does not make a runtime override active.
- Proposed override metadata does not modify production override config.
- `puzzle_variation_overrides.json` remains the only active production override source.
- `GF-003` remains disabled and candidate-only.
- `B[sd] / T16` remains a candidate equivalent only.

Concretely, today:

- `GF-003` is still outside the READY active set.
- `GF-003` has `runtime_status: disabled`.
- `GF-003` has `apply_automatically: false`.
- `GF-003` has `runtime_override_active: false`.
- repository override config remains `{}`.

## Teacher Admin Product Principle

Teacher-admin work should improve reviewability and auditability without coupling the
product surface to SGF engine internals.

Guiding principles:

- preserve owner-approved corpus truth
- separate review metadata from runtime activation
- keep teacher workflows auditable
- avoid coupling teacher workflows directly to SGF engine or override schema details

## Owner-Defined Teacher Admin Backlog

The following items are explicitly future backlog, not part of this PR's implementation.

### Status Review

Needed future capabilities:

- browse active, excluded, candidate-only, disabled, and pending records
- inspect canonical answer versus proposed candidate answer
- inspect whether a production override is inactive or active
- trace owner decision history

### Visual SGF Validation

Needed future capabilities:

- visual review for board-crop and coordinate-quality issues
- side-by-side inspection of SGF variations
- comparison of canonical answer and candidate answer
- explicit confirmation of issue, false alarm, or owner decision needed

This planning note does not implement WGo.js or any other teacher review UI.

### Domain Taxonomy

Possible future taxonomy directions include:

- life and death
- tesuji
- ladder
- endgame
- opening
- joseki
- shape and reading categories
- rank and difficulty categories

This planning note does not define a production tag schema.

### Feedback Loop

Possible future workflow directions include:

- teacher review queue
- confirmed issue versus false alarm triage
- owner decision queue
- student issue reporting intake
- before/after review evidence

This planning note does not implement a queue, report button, or backend workflow.

## Recommended Next Engineering Batches

Low-risk docs-and-tests batches:

- metadata quality checks
- status taxonomy tests
- teacher-facing status language docs
- owner decision queue docs
- visual SGF validation requirements doc
- domain taxonomy requirements doc
- feedback loop requirements doc

Needs owner decision before implementation:

- teacher admin UX flow
- status transition rules
- review queue behavior
- batch operation rules
- permission model
- initial domain taxonomy
- student report workflow
- WGo.js integration details

Higher-risk future implementation:

- backend and API
- DB schema
- frontend UI
- runtime override activation
- READY promotion workflow
- production override management
- student report ingestion
- teacher review queue implementation

## Explicit Non-Actions

This baseline does not:

- implement teacher admin
- add DB, API, backend, or UI
- change SGF bytes
- change `READY_IDS`
- change `puzzle_variation_overrides.json`
- change SGF engine production code
- activate GF-003
- make `B[sd] / T16` active
- activate runtime overrides
- activate production overrides
- implement WGo.js teacher review UI
- implement domain taxonomy schema
- implement student feedback or report queue
