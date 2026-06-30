# Gold Fixtures Selection Spec

## Scope

This is a selection specification only.

- No SGF files were created.
- No SGF content was fabricated.
- No `puzzle_variation_overrides.json` edits were made.
- No integration tests were written.
- No production code was modified.
- No files under `sgf_engine/` were modified.

This document defines the real SGF fixture coverage required before the next integration phase can begin. It does not authorize fixture creation or test implementation.

## Source Rules

- Gold Fixtures must use real SGF only.
- SGF files must be owner-provided or come from owner-approved existing real puzzle sources.
- AI-generated SGF is not allowed.
- Synthetic SGF is not allowed.
- Invented puzzle sequences are not allowed.
- Simplified SGF strings created only to satisfy a test case are not allowed.
- Every fixture must record provenance before it can be accepted.

## Fixture Acceptance Criteria

A real SGF file can become a Gold Fixture only when all of the following are true:

- The SGF is parseable by the current parser.
- The expected path is deterministic under the current SGF Engine.
- The expected `player_color` is known.
- The expected player move is known.
- The expected engine result is known.
- The expected metadata result behavior is clear.
- The override requirement is explicitly marked `yes` or `no`.
- Any planned override is based on owner-approved real puzzle intent.
- There is no ambiguous owner intent about the correct move, equivalent move, expected continuation, or expected result.
- The fixture proves one primary engine behavior without bundling unrelated assertions.

## Fixture Metadata Template

Each future fixture must record:

```text
fixture_id:
fixture_file_name:
source/provenance:
source owner:
reason selected:
primary behavior under test:
player_color:
player_move:
initial node assumption:
expected matched_type:
expected status:
expected auto_reply:
expected final node description:
override required: yes/no
planned override key, if applicable:
planned equivalent_moves entry, if applicable:
OFF_TREE logging expected: yes/no
notes:
```

## Ten Required Fixture Slots

### GF-001

- Fixture goal: Direct branch success.
- Required SGF characteristics: The selected current node has a child whose move directly matches the player's move.
- Expected engine behavior: The engine advances to the matching child branch and returns `matched_type: branch`.
- Override requirement: No override required.
- Later integration test intent: Verify direct SGF tree branch matching without consulting equivalent move data.
- Owner input needed: Provide a real SGF, the intended starting node, `player_color`, player move, and expected result metadata for the reached node.

### GF-002

- Fixture goal: Branch with auto-reply success.
- Required SGF characteristics: The player move directly matches an SGF child branch, and the reached node has exactly one child whose move color is the opponent color.
- Expected engine behavior: The engine advances to the player branch, auto-plays exactly one opponent reply, and reads final result metadata from the auto-reply node.
- Override requirement: No override required unless owner provenance proves an unrelated equivalent case is also needed elsewhere; this slot should not depend on it.
- Later integration test intent: Verify the locked order of branch traversal, single auto-reply, and result propagation from the reply node.
- Owner input needed: Provide a real SGF with a one-reply continuation and identify the expected opponent reply and final metadata result.

### GF-003

- Fixture goal: Equivalent move success.
- Required SGF characteristics: The player move is not a direct child of the current node, but the owner confirms it is equivalent to a real canonical child branch in the SGF tree.
- Expected engine behavior: The matcher returns `matched_type: equivalent`, the engine resolves the canonical coordinate, and traversal advances to the canonical SGF child branch.
- Override requirement: Yes.
- Later integration test intent: Verify equivalent move resolution through owner-approved override data and canonical tree traversal.
- Owner input needed: Provide the real SGF, the canonical SGF branch coordinate, the player alternative coordinate, and the owner-approved equivalence rationale.

### GF-004

- Fixture goal: Active override but direct branch priority.
- Required SGF characteristics: The player move directly matches an SGF child branch, and active override data also contains that same player move as an equivalent alternative.
- Expected engine behavior: Direct branch matching wins and returns `matched_type: branch`.
- Override requirement: Yes, for the active override condition; the expected outcome must still be direct branch.
- Later integration test intent: Verify branch priority when override data exists.
- Owner input needed: Provide a real SGF and owner-approved override scenario where the submitted move is both a direct branch and present in equivalent move data.

### GF-005

- Fixture goal: OFF_TREE unmatched move.
- Required SGF characteristics: From the selected current node, the player move is neither a direct child branch nor an owner-approved equivalent alternative.
- Expected engine behavior: The engine returns `status: off_tree`, `node: None`, `matched_type: off_tree`, and `auto_reply: None`.
- Override requirement: No override required for the unmatched move.
- Later integration test intent: Verify OFF_TREE classification and logging intent without treating DB persistence as part of this fixture test.
- Owner input needed: Provide a real SGF, intended starting node, and an owner-approved unmatched player move to test.

### GF-006

- Fixture goal: Metadata result success.
- Required SGF characteristics: Successful traversal reaches a node whose metadata result indicates success.
- Expected engine behavior: The final returned status is `success`.
- Override requirement: No override preferred unless the owner-approved real case requires equivalent traversal; the primary purpose is result propagation.
- Later integration test intent: Verify result metadata propagation for success without matcher or autoreply deciding success.
- Owner input needed: Provide a real SGF and identify the successful terminal or continuation node with its expected metadata result.

### GF-007

- Fixture goal: Metadata result fail.
- Required SGF characteristics: Successful traversal reaches a node whose metadata result indicates fail.
- Expected engine behavior: The final returned status is `fail`.
- Override requirement: No override preferred unless the owner-approved real case requires equivalent traversal; the primary purpose is fail propagation.
- Later integration test intent: Verify result metadata propagation for fail without matcher or autoreply deciding fail.
- Owner input needed: Provide a real SGF and identify the failed terminal or continuation node with its expected metadata result.

### GF-008

- Fixture goal: Missing result metadata defaults to continue.
- Required SGF characteristics: Successful traversal reaches a real SGF node that lacks result metadata.
- Expected engine behavior: The final returned status defaults to `continue`.
- Override requirement: No override preferred; this slot should isolate missing metadata behavior.
- Later integration test intent: Verify the engine default when `metadata["result"]` is absent.
- Owner input needed: Provide a real SGF, intended starting node, and player move that reaches a node with no result metadata.

### GF-009

- Fixture goal: Multi-branch no auto-reply.
- Required SGF characteristics: After the player move, the reached node has multiple opponent candidate child branches.
- Expected engine behavior: The engine does not auto-reply and returns `auto_reply: None`.
- Override requirement: No override preferred; this slot should isolate auto-reply blocking by multiple candidates.
- Later integration test intent: Verify that auto-reply only occurs for exactly one immediate opponent child.
- Owner input needed: Provide a real SGF where the post-player node has multiple opponent continuations and identify the expected final node before any reply.

### GF-010

- Fixture goal: Same-color or non-opponent child no auto-reply.
- Required SGF characteristics: After the player move, the reached node has exactly one child, but that child is not an opponent-color move.
- Expected engine behavior: The engine does not auto-reply and returns `auto_reply: None`.
- Override requirement: No override preferred; this slot should isolate auto-reply blocking by child color or non-move child.
- Later integration test intent: Verify that a single child is not enough for auto-reply unless it is exactly the opponent color.
- Owner input needed: Provide a real SGF with a single same-color or non-opponent child after the player move and identify the expected final node.

## Override Planning Notes

- `puzzle_variation_overrides.json` must not be edited until real fixture files are selected.
- `equivalent_moves` must use the canonical SGF tree coordinate as the key and player alternative coordinates as values.
- Overrides must remain exception data, not a truth source replacement.
- Equivalent move entries must be traceable to owner-approved real puzzle intent.
- Direct branch priority must be preserved even when active override data exists.

## Deferred Until Real Fixtures Exist

- Actual SGF files.
- Actual override JSON entries.
- Gold Fixtures integration tests.
- Real DB persistence test for `log_off_tree`.
- API/app.py integration.

## Additional Files That May Require Owner-Approved Review

None identified for this documentation-only selection spec.

## Stop Conditions

- This spec does not authorize Codex to create SGF files.
- This spec does not authorize Codex to fabricate puzzle data.
- This spec does not authorize production code changes.
- This spec does not authorize integration test creation.
- The next step requires owner-provided real SGF files or owner-approved existing real puzzle sources.
