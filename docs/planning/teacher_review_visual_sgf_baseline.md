# Teacher Review Workflow And Visual SGF Validation Baseline

## Scope

This planning note records a future teacher-review workflow baseline and a Visual SGF
Validation contract baseline without changing production behavior.

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
- implement WGo.js teacher review UI

## Owner-Defined Purpose

This baseline exists to document the lowest-risk reviewability groundwork before any
future teacher-review implementation.

The current repository already contains enough metadata to discuss review traceability,
candidate answers, disabled override state, and SGF reference sanity.

The current repository does not yet define a stable teacher-review API payload or a
teacher-facing review workflow implementation.

## Review Workflow Baseline

The intended future review workflow is:

1. A teacher opens a review queue.
2. The teacher sees a teacher-facing status bucket such as READY, excluded,
   candidate-only, disabled, needs review, or owner decision pending.
3. The teacher opens the SGF reference for the record under review.
4. The teacher compares the canonical answer with any proposed candidate answer.
5. The teacher reviews traceability metadata and issue context.
6. The teacher records a review outcome such as confirmed issue, false alarm, needs
   owner decision, or candidate approved for future follow-up.
7. A later, higher-risk workflow may decide whether READY promotion or production
   override activation should happen.

This is a future workflow baseline, not an implemented workflow.

Important separation:

- teacher review metadata is not runtime activation
- proposed candidate answer is not active answer behavior
- production override activation remains a separate future decision

## Visual SGF Validation Contract Baseline

The repository already exposes a safe subset of metadata that can support future visual
review planning:

- stable puzzle identity via `gf_id`
- teacher-review traceability via `fixture_path`, `source_path`, and `gold_fixture_id`
- SGF reference via the fixture `.sgf` path
- canonical answer move via `canonical_move_sgf`
- proposed candidate move via `player_move_sgf`
- runtime inactivity via `runtime_status`
- automatic activation boundary via `apply_automatically`
- production override inactivity via empty `puzzle_variation_overrides.json`
- review context via the record `reason`

Current baseline guidance:

- `source_path`, `fixture_path`, and `gold_fixture_id` are traceability metadata
- canonical identity should remain stable even when candidate metadata exists
- proposed candidate metadata must not be treated as active runtime answer behavior
- empty production override config means proposed override metadata is still inactive

## Gap Analysis

### Currently Available Metadata

The current repository already provides:

- `gf_id`
- `fixture_path`
- `player_move_sgf`
- `canonical_move_sgf`
- `disabled_override_metadata.gold_fixture_id`
- `disabled_override_metadata.source_path`
- `disabled_override_metadata.runtime_status`
- `disabled_override_metadata.apply_automatically`
- `proposed_override`
- `reason`

### Safe Traceability Subset

This PR treats the following as the safe currently available subset for future review
planning:

- stable identity
- fixture reference
- canonical answer move
- proposed candidate move
- runtime inactive state
- production override inactive state
- source traceability metadata

Tests in this PR only verify that this safe subset exists and remains inactive where
required.

### Future C-Level Requirements

The following fields or capabilities are future-facing requirements, not current
repository guarantees:

- `[Future C-level Requirement]` teacher-facing status bucket
- `[Future C-level Requirement]` canonical answer display coordinate
- `[Future C-level Requirement]` proposed candidate display coordinate
- `[Future C-level Requirement]` review notes or issue reason workflow
- `[Future C-level Requirement]` student report context
- `[Future C-level Requirement]` front-end SGF playback payload
- `[Future C-level Requirement]` stable review-card API payload

This document does not authorize adding future review-card fields to `fixtures.json`,
modifying SGF files, changing production code, or changing runtime behavior.

## WGo.js Rendering Principle

Future visual SGF validation should render SGF references using a board viewer such as
WGo.js instead of inventing review judgments from raw coordinate strings alone.

This baseline only records the rendering principle:

- future review UI should show real SGF board context
- future review UI should let a teacher compare canonical and proposed answers visually
- future review UI should preserve traceability to the underlying SGF source

This PR does not implement WGo.js, frontend playback, or any teacher-review UI.

## Review Action Safety

Low-risk future review actions:

- add a review note
- mark needs review
- mark false alarm
- add teacher-facing tags
- record a teacher decision without changing runtime behavior

Medium-risk future actions:

- record owner-decision outcomes
- mark a candidate as READY in review planning
- edit candidate answer metadata
- edit domain tags

High-risk or C-level future actions:

- READY promotion
- production override activation
- runtime override behavior changes
- SGF byte modification
- SGF engine judging semantic changes
- DB, API, backend, or frontend implementation

This PR is limited to docs and tests groundwork and does not perform medium-risk or
high-risk actions.

## Domain Taxonomy And Feedback Loop Connection

Future teacher review may later connect to:

- domain taxonomy tags
- issue reasons
- student report context
- owner decision queues
- before/after review evidence

These remain backlog topics. This PR does not define a domain taxonomy schema, report
button, backend queue, or API contract.

## Explicit Non-Actions

This baseline does not:

- implement teacher admin
- add DB, API, backend, or frontend UI
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
