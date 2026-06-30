# SGF Engine Specification v1.0

Status: Formal documentation specification
Date: 2026-06-29
Source basis: SGF Engine Specification v1.0 Draft v0.1, current SGF Engine documentation, owner decisions, and gold fixture draft records.

## 1. Scope

This specification defines the intended SGF Engine behavior and phase boundaries for the current repository state.

This file is documentation only. It is not runtime input, test input, fixture input, override input, or production configuration.

This specification does not authorize:

- writing tests;
- creating or copying SGF fixtures;
- modifying SGF source files;
- modifying `puzzle_variation_overrides.json`;
- modifying production code;
- treating `docs/testing/gold_fixture_owner_manifest_draft.yml` as active test input;
- activating GF-003, GF-004, GF-006, or GF-007;
- entering the integration-test phase.

## 2. Module Responsibilities

The SGF Engine is split by responsibility:

- `sgf_engine/core/coord_utils.py`: strict SGF coordinate and color helpers.
- `sgf_engine/core/tree.py`: `Move`, `SGFNode`, parent/child structure, and pure child lookup.
- `sgf_engine/core/matcher.py`: move classification only: `branch`, `equivalent`, or `off_tree`.
- `sgf_engine/core/autoreply.py`: sole auto-reply rule.
- `sgf_engine/parser/sgf_parser.py`: strict structural SGF parser with variation preservation.
- `sgf_engine/override/override_loader.py`: source-normalized JSON override loading and canonical equivalent resolution.
- `sgf_engine/engine/engine.py`: the sole orchestration layer for override loading, matching, traversal, auto-reply, result reading, and OFF_TREE logging.

No module may use AI reasoning to decide Go meaning.

## 3. Runtime Inputs

The runtime engine may use only explicit inputs:

- the current `SGFNode`;
- the submitted SGF move coordinate;
- the submitted player color;
- the source identifier used for override lookup;
- the active contents of `puzzle_variation_overrides.json`.

Owner notes, fixture selection documents, manifest drafts, and this specification are not runtime inputs.

## 4. Locked Engine Order

`engine.apply_move` must process a submitted move in this order:

1. Load the active override for the source.
2. Match the submitted move structurally.
3. Traverse the direct or canonical SGF tree branch, or log and return OFF_TREE.
4. Apply auto-reply only when exactly one immediate opponent-color child exists.
5. Read result metadata from the final node, defaulting to `continue` when missing.

Matcher classification must not read result metadata.

Auto-reply must not decide success or failure.

## 5. Match Types

The matcher vocabulary is closed:

- `branch`: the submitted move is a direct child of the current SGF node.
- `equivalent`: the submitted move is declared as an alternative in the active override data.
- `off_tree`: the submitted move is neither a direct child nor an active declared equivalent.

The matcher must not mutate the SGF tree, node metadata, child lists, parent pointers, or override data.

## 6. Override Precedence

Direct SGF tree branch matching has priority over override equivalence.

If a submitted move is both a direct child and appears in active override data, the engine must return `matched_type: branch`.

Equivalent moves are active only when they are present in the runtime override data loaded from `puzzle_variation_overrides.json`.

Owner Go judgment, owner manifest notes, and draft fixture classification are not runtime override data.

Without an active override, even an owner-approved equivalent move, such as GF-003 `B[sd] / 黑 T16`, must be classified by the Engine as `OFF_TREE`.

Override entries must use canonical SGF tree coordinates as keys and owner-approved alternative coordinates as values:

```json
{
  "equivalent_moves": {
    "sf": ["sd"]
  }
}
```

The canonical coordinate must exist as a real SGF child branch when the equivalent move is applied. If active override data declares an equivalent move whose canonical coordinate is absent from the SGF tree, the engine must raise an error rather than silently falling back to OFF_TREE.

## 7. Auto-Reply Rule

The engine may auto-reply only after a successful player branch or equivalent traversal.

Auto-reply is allowed only when the reached node has exactly one immediate child whose move color is the opponent color.

Auto-reply must not occur when:

- there are zero opponent-color child moves;
- there are multiple opponent-color child moves;
- the only child is same-color;
- the child is not a move node.

Same-color children, including source SGF color typos, must not be treated as opponent auto-replies.

## 8. Result Metadata

The engine reads result metadata only after traversal and optional auto-reply.

If the final node has `metadata["result"]`, that value is the engine status.

If result metadata is absent, the engine status defaults to `continue`.

Missing result metadata must not be interpreted by the matcher or auto-reply logic.

## 9. OFF_TREE Behavior

OFF_TREE means the submitted move is not an active engine path under the current SGF tree and active override data.

OFF_TREE does not mean the engine has judged the move's Go quality.

Current owner decision accepts `sgf_engine/engine/engine.py::log_off_tree` as a temporary documented boundary exception because it writes unmatched moves through production `db.get_db`.

No additional `sgf_engine/` code may import production application modules such as `app.py`, Flask, routes, Redis, Socket.IO, or other production infrastructure.

Future cleanup should move OFF_TREE persistence to the application integration layer or inject an OFF_TREE logger.

## 10. Gold Fixture Gate

Gold fixture integration remains gated.

The current owner manifest draft classifications are documentation only:

- READY: GF-001, GF-002, GF-005, GF-008, GF-009, GF-010.
- CANDIDATE_REQUIRES_OVERRIDE: GF-003.
- PENDING: GF-004, GF-006, GF-007.

These classifications do not activate tests, fixtures, overrides, or runtime behavior.

No integration-test phase may begin until the owner explicitly authorizes it.

## 11. Fixture and Override Constraints

Gold fixtures must use real SGF only.

Synthetic SGF, AI-generated SGF, invented sequences, or simplified SGF strings made only to satisfy tests are forbidden.

`puzzle_variation_overrides.json` must not be edited merely because a draft manifest records owner-approved Go meaning.

Candidate or pending fixture records must not be used as active test input.

GF-003 must remain inactive until an explicit active override is introduced under owner approval.

GF-004, GF-006, and GF-007 must remain inactive while their manifest status is `PENDING`.

## 12. Documentation Isolation

The following files are documentation-only unless the owner explicitly announces a new phase:

- `docs/testing/gold_fixture_owner_manifest_draft.yml`;
- `docs/testing/sgf_engine_specification_v1.0.md`;
- `docs/testing/gold_fixtures_selection_spec.md`.

Code, tests, fixture loaders, SGF engine modules, and override loaders must not consume these files as active input.

## 13. Non-Goals

This specification does not define:

- API or frontend integration;
- production route behavior;
- DB migration strategy;
- real persistence integration tests for OFF_TREE logging;
- active gold fixture file layout;
- active owner override JSON entries;
- Go correctness beyond owner-provided explicit data.

## 14. Current Phase Boundary

The current phase is documentation-only.

No tests were added by this specification.

No SGF files were modified or copied.

No override data was modified.

No production code was modified.

No fixture was activated.

The integration-test phase was not entered.
