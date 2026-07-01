# Canonical Puzzle Identity Contract Baseline

## Status

Planning / contract baseline only.

This document defines a future contract baseline for canonical puzzle identity. It does not implement runtime behavior, database schema, API routes, frontend UI, production identity migration, READY promotion, SGF byte changes, production overrides, or SGF engine judging semantics.

## Purpose

Future teacher admin workflows need a stable canonical puzzle identity so that review queue items, feedback reports, visual SGF validation cards, and owner decision traces can all refer to the same durable puzzle record.

This baseline is not the final implementation. The final canonical puzzle identity remains a future C-level owner decision.

## Core contract

A future `canonical_puzzle_id` must identify one durable puzzle record.

It must remain stable across:

- source file moves
- source file renames
- fixture path changes
- gold fixture metadata changes
- frontend sessions
- runtime answer attempts
- review queue item lifecycle
- feedback report lifecycle
- owner decision trace lifecycle
- visual SGF validation lifecycle

A future `canonical_puzzle_id` must not encode answer correctness, runtime status, review queue status, or teacher decision status directly in the ID.

## Non-canonical identifiers

The following identifiers must not be treated as canonical puzzle identity:

- `source_path`
- `fixture_path`
- `gold_fixture_id`
- frontend temporary ID
- runtime state
- answer attempt ID
- `review_queue_item_id`
- `feedback_report_id`
- owner decision note ID

Reasons:

- `source_path` can change when corpus files are reorganized.
- `fixture_path` is a test fixture reference, not a production puzzle identity.
- `gold_fixture_id` is gold fixture / test metadata, not the production DB identity.
- frontend temporary ID is not stable across sessions.
- runtime state is not a long-term review anchor.
- answer attempt ID identifies one attempt, not the puzzle itself.
- `review_queue_item_id` identifies a review workflow item, not the puzzle itself.
- `feedback_report_id` identifies a report event, not the puzzle itself.
- owner decision note ID identifies one decision note, not the puzzle itself.

## Future identity components

The future contract should keep these concepts separate:

### `canonical_puzzle_id`

Durable puzzle identity.

It is not a file path, not a fixture ID, not a runtime attempt ID, not a review queue item ID, and not a feedback report ID.

### `content_revision_id`

Future identity for SGF/content version.

It may change when puzzle content changes. It should not replace `canonical_puzzle_id`.

### `source_locator`

Current or historical source location, such as source path or manifest location.

It may be useful for debugging, migration, and traceability. It must not be the primary identity.

### `fixture_reference`

Test-only reference for gold fixtures or fixture files.

It must not be treated as production identity.

### `review_queue_item_id`

Workflow item identity.

It should point to `canonical_puzzle_id`. It does not replace `canonical_puzzle_id`.

### `feedback_report_id`

Feedback event identity.

It should point to `canonical_puzzle_id`. It does not replace `canonical_puzzle_id`.

### `owner_decision_id`

Owner decision trace identity.

It should point to `canonical_puzzle_id`. It does not replace `canonical_puzzle_id`.

## Future candidate directions

The final identity design is not decided in this baseline.

Future owner decisions may consider:

- production puzzle UUID
- stable imported puzzle ID generated during corpus ingestion
- versioned puzzle identity with separate content revision
- durable puzzle record ID plus separate SGF/content revision ID

## Explicit non-goals

This baseline does not:

- implement final canonical puzzle identity
- implement DB schema
- implement API routes
- implement frontend UI
- modify SGF bytes
- modify READY_IDS
- modify `puzzle_variation_overrides.json`
- modify SGF engine production code
- promote GF-003
- activate B[sd] / T16
- activate production overrides
