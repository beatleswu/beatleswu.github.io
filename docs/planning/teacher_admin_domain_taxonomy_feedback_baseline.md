# Teacher Admin Domain Taxonomy And Feedback Loop Baseline

## Scope

This planning note records a future-facing domain taxonomy baseline and feedback-loop
baseline for teacher admin without changing production behavior.

This document is docs-only groundwork.

This document does not:

- implement teacher admin
- add DB, API, backend, or frontend UI
- add a formal domain tag schema
- add a formal feedback or report queue
- define the final canonical puzzle identity contract
- change SGF bytes
- promote any fixture into READY
- activate GF-003
- activate production overrides
- change runtime behavior
- change SGF engine judging semantics

## Owner-Defined Purpose

This baseline exists to document the lowest-risk groundwork for teacher-admin
classification and issue review before any future product implementation.

The repository already contains enough metadata to discuss current corpus states,
traceability, canonical answer versus candidate answer review, and inactive override
boundaries.

The repository does not yet define a teacher-facing taxonomy schema, a feedback queue,
or a teacher-admin review implementation.

The intended long-term goal is to help teachers classify content, triage reported
issues, and review candidate answers without coupling metadata directly to runtime
activation.

## Domain Taxonomy Backlog

The following owner-defined domain labels are future product backlog items:

- Life and Death
- Tesuji
- Ladder
- Endgame
- Opening
- Joseki
- Capture
- Escape
- Connection
- Cutting
- Eye Shape
- Ko
- Attack / Defense
- Endgame Technique

These are future product taxonomy requirements.

This PR does not add a formal domain tag schema.

This PR does not add production data for domain taxonomy.

This PR does not attach domain tags to `fixtures.json` or any READY record.

## Difficulty And Level Backlog

The following owner-defined difficulty and level labels remain future backlog:

- 30K-26K
- 25K-21K
- 20K-16K
- 15K-11K
- 10K-6K
- 5K-1K
- 1D-2D
- 3D-4D
- 5D-6D
- 7D+
- beginner
- intermediate
- advanced
- teacher-adjusted difficulty

Corrected dan-level grouping for future planning:

- 1D-2D
- 3D-4D
- 5D-6D
- 7D+

These labels remain future product backlog.

This PR does not add a formal difficulty schema.

This PR does not add difficulty fields to production data or READY records.

## Teacher Custom Tags Backlog

Teacher custom tags are also future backlog.

Possible examples include:

- lesson-specific focus
- common mistake
- shape confusion
- reading challenge
- opening follow-up
- endgame review
- review requested
- owner follow-up needed

This PR does not add a teacher tag schema.

This PR does not add teacher custom tag fields to production data.

## Teacher-Facing Filtering Baseline

Future teacher-admin filtering may eventually support:

- status buckets such as READY, excluded, candidate-only, disabled, needs review, and
  owner decision pending
- domain taxonomy filters
- difficulty or level filters
- teacher custom tags
- source traceability references
- fixture, SGF, and review-reference context

Current repository evidence supports traceability planning through metadata such as
`source_path`, `fixture_path`, and `gold_fixture_id`.

These fields are traceability metadata only.

They are not teacher-admin schemas and they are not a canonical puzzle identity.

## Feedback Loop Backlog

### Student-Reported Issue Flow

Future student issue reporting may eventually include:

1. A student reports a puzzle issue.
2. The report enters a needs-review intake state.
3. A teacher review queue surfaces the report with traceability context.
4. A teacher reviews the canonical answer, candidate answer, and SGF reference.
5. A teacher records an outcome such as confirmed issue, false alarm, or needs owner
   decision.

This PR does not implement a report button, a report intake workflow, or a queue.

### Teacher-Reported Issue Flow

Future teacher issue reporting may eventually include:

1. A teacher flags a puzzle for review.
2. A teacher records a review note.
3. The record enters needs review or owner decision pending.
4. A later decision marks the item as confirmed issue, false alarm, or owner decision
   needed.

This PR does not implement teacher review notes, queue state transitions, or any
backend workflow.

### Review Queue Behavior

Future queue behavior may eventually include:

- review-note history
- issue triage status
- false-alarm traceability
- owner-decision traceability
- review priority
- student report context

This PR does not add a formal feedback or report queue.

## Feedback Identity Anchor

Any future student feedback, teacher feedback, issue report, review note, or review
queue item must bind strongly to a future canonical puzzle identity.

The canonical puzzle identity should be defined by a future C-level identity and API
decision.

The following are not canonical puzzle identity:

- `source_path`
- `fixture_path`
- `gold_fixture_id`
- any ad hoc review-item identifier
- transient runtime state

This PR treats `source_path`, `fixture_path`, and `gold_fixture_id` as traceability
metadata only.

Any future C-level implementation must define a canonical puzzle identity contract for
feedback binding.

## Gap Analysis

### Currently Available Metadata

The current repository already exposes a safe subset of metadata for planning:

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

The current safe subset is limited to metadata that helps teachers inspect review
context without activating runtime behavior:

- traceability references
- canonical answer reference
- proposed candidate reference
- disabled runtime state
- inactive production override state

### Future C-Level Requirements

The following are future-facing requirements, not current repository guarantees:

- `[Future C-level Requirement]` `domain_tags`
- `[Future C-level Requirement]` `difficulty_label`
- `[Future C-level Requirement]` `teacher_custom_tags`
- `[Future C-level Requirement]` `student_report_count`
- `[Future C-level Requirement]` `issue_reason`
- `[Future C-level Requirement]` `review_queue_status`
- `[Future C-level Requirement]` `teacher_review_notes`
- `[Future C-level Requirement]` confirmed issue / false alarm state
- `[Future C-level Requirement]` review priority
- `[Future C-level Requirement]` student report context
- `[Future C-level Requirement]` canonical puzzle identity for feedback binding

This PR does not add a formal domain tag schema.

This PR does not add a formal feedback or report queue.

This PR does not modify `fixtures.json`.

This PR does not add DB, API, backend, or frontend UI.

## Safety Boundary

The current baseline must preserve these boundaries:

- domain tags do not change runtime behavior
- difficulty labels do not promote READY
- student reports do not activate overrides
- teacher notes do not promote READY
- review queue status does not change SGF bytes
- candidate-only records do not become active
- disabled records do not become READY
- production override activation remains a future C-level workflow

## Connection To Visual SGF Validation

This baseline connects to the Phase 9B Visual SGF Validation groundwork.

Future domain tags and feedback-loop fields may later appear in a teacher review card.

Future teacher review should still compare canonical and candidate answers in real SGF
board context rather than inferring review outcomes from coordinate strings alone.

This PR does not add a review-card API and does not add WGo.js UI.

## Explicit Non-Actions

This PR does not implement teacher admin.

This PR does not add DB, API, backend, or frontend UI.

This PR does not add a formal domain tag schema.

This PR does not add a formal feedback or report queue.

This PR does not define the final canonical puzzle identity contract.

This PR does not change SGF bytes.

This PR does not promote READY.

This PR does not activate GF-003.

This PR does not activate production overrides.

This PR does not change runtime behavior.

This PR does not implement WGo.js teacher review UI.

This PR only documents domain taxonomy and feedback-loop baseline, plus tests metadata
boundaries and future skipped acceptance criteria.
