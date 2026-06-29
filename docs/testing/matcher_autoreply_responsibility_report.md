# Matcher and Autoreply Responsibility Boundary Review

## Scope

Verification-only audit of `sgf_engine/core/matcher.py` and `sgf_engine/core/autoreply.py` against their declared responsibility boundaries. No production code was modified. Review was limited to the files allowed by the mission.

## Files Reviewed

- `sgf_engine/core/matcher.py`
- `sgf_engine/core/autoreply.py`
- `sgf_engine/core/tree.py`
- `sgf_engine/core/coord_utils.py`
- `tests/sgf_engine/test_matcher.py`
- `tests/sgf_engine/test_autoreply.py`
- `tests/sgf_engine/test_engine.py`
- `docs/testing/modification_log.md`

## Import Inventory

| File path | Exact import statement | Classification |
|---|---|---|
| `sgf_engine/core/matcher.py` | `from __future__ import annotations` | standard library |
| `sgf_engine/core/matcher.py` | `from enum import Enum` | standard library |
| `sgf_engine/core/matcher.py` | `from sgf_engine.core.coord_utils import sgf_to_xy` | sgf_engine internal |
| `sgf_engine/core/matcher.py` | `from sgf_engine.core.tree import SGFNode, find_child_by_move` | sgf_engine internal |
| `sgf_engine/core/autoreply.py` | `from __future__ import annotations` | standard library |
| `sgf_engine/core/autoreply.py` | `from sgf_engine.core.coord_utils import opponent_of` | sgf_engine internal |
| `sgf_engine/core/autoreply.py` | `from sgf_engine.core.tree import Move, SGFNode` | sgf_engine internal |

## Production Dependency Findings

| File path | Function name | Exact import/call/access pattern | Classification |
|---|---|---|---|
| `sgf_engine/core/matcher.py` | module scope | Imports only `__future__`, `enum.Enum`, `sgf_engine.core.coord_utils.sgf_to_xy`, and `sgf_engine.core.tree.SGFNode/find_child_by_move`; no `app.py`, `db.py`, Flask, routes, models, Redis, Socket.IO, PostgreSQL helper, application config, or production database helper import appears. | OK |
| `sgf_engine/core/matcher.py` | `match_move` | Calls only `sgf_to_xy(move_coord)` and `find_child_by_move(current_node, move_coord)` before reading the supplied `override` dict. | OK |
| `sgf_engine/core/autoreply.py` | module scope | Imports only `sgf_engine.core.coord_utils.opponent_of` and `sgf_engine.core.tree.Move/SGFNode`; no production application dependency import appears. | OK |
| `sgf_engine/core/autoreply.py` | `get_auto_reply` | Calls only `opponent_of(player_color)` and reads immediate child state from `current_node.children`. | OK |

## Matcher Responsibility Findings

| File path | Function name | Exact behavior | Evidence from code and/or tests | Classification |
|---|---|---|---|---|
| `sgf_engine/core/matcher.py` | `MatchResult` / `match_move` | Return vocabulary is limited to `BRANCH`, `EQUIVALENT`, and `OFF_TREE`. | `MatchResult` defines only those three values; `match_move` returns `BRANCH`, `EQUIVALENT`, or `OFF_TREE`. `tests/sgf_engine/test_matcher.py` asserts all three outcomes. | OK |
| `sgf_engine/core/matcher.py` | `match_move` | Returns match type only, not `SGFNode`. | Signature is `-> MatchResult`; direct branch path discards the `find_child_by_move` node and returns `BRANCH`. | OK |
| `sgf_engine/core/matcher.py` | `match_move` | Checks BRANCH before EQUIVALENT. | Calls `find_child_by_move` and returns `BRANCH` before assigning `equivalent_moves`; `test_branch_is_checked_before_equivalent` asserts this priority. | OK |
| `sgf_engine/core/matcher.py` | `match_move` | Uses tree helper lookup rather than performing advancement. | Uses `find_child_by_move(current_node, move_coord)`; no assignment to current node or returned next node appears. | OK |
| `sgf_engine/core/matcher.py` | `match_move` | Does not decide success/fail or read result metadata. | No `metadata` or `result` access appears in matcher; `test_matcher_does_not_read_result_metadata` puts `metadata={"result": "fail"}` on a matching child and still expects `BRANCH`. | OK |
| `sgf_engine/core/matcher.py` | `match_move` | Does not load overrides from file or call `override_loader.load_override`. | No override loader import/call; override is received as the `override` argument and read with `(override or {}).get("equivalent_moves")`. | OK |
| `sgf_engine/core/matcher.py` | `match_move` | Does not call `canonical_coord_for`. | No import or call appears. Equivalent detection only checks whether `move_coord` appears in provided alternatives. | OK |
| `sgf_engine/core/matcher.py` | `match_move` | Does not mutate SGFNode, Move, children, parent, metadata, or override. | Function contains validation, helper lookup, local `equivalent_moves` assignment, iteration over `.values()`, membership checks, and returns; no assignment to object attributes or container mutation appears. | OK |
| `sgf_engine/core/matcher.py` | `match_move` | Treats override as optional. | Uses `(override or {})`; `test_unknown_move_is_off_tree` passes `None`. | OK |
| `sgf_engine/core/matcher.py` | `match_move` | Does not perform logging or DB writes. | No logging, database, filesystem, service, or app dependency call appears. | OK |
| `sgf_engine/core/matcher.py` | `match_move` | Validates coordinate by calling `sgf_to_xy` before classification. | `sgf_to_xy(move_coord)` appears before branch lookup; `test_matcher_rejects_invalid_coordinate` expects `ValueError` for `"DD"`. This is validation, not canonical resolution. | OK |

## Autoreply Responsibility Findings

| File path | Function name | Exact behavior | Evidence from code and/or tests | Classification |
|---|---|---|---|---|
| `sgf_engine/core/autoreply.py` | `get_auto_reply` | Validates `player_color` through `opponent_of`. | First executable line is `opponent = opponent_of(player_color)`; `test_invalid_player_color_raises_even_without_children` expects `ValueError`. | OK |
| `sgf_engine/core/autoreply.py` | `get_auto_reply` | Returns `Move | None`, not `SGFNode`. | Signature is `-> Move | None`; only object return is `child.move`. | OK |
| `sgf_engine/core/autoreply.py` | `get_auto_reply` | Returns a move only when the current node has exactly one child and that child's move color equals `opponent_of(player_color)`. | Checks `len(current_node.children) != 1`, then `child.move is None`, then `child.move.color == opponent`; `test_single_opponent_child_returns_move` covers the positive path. | OK |
| `sgf_engine/core/autoreply.py` | `get_auto_reply` | Returns `None` for multiple children. | `len(current_node.children) != 1` returns `None`; `test_multiple_children_return_none` covers this. | OK |
| `sgf_engine/core/autoreply.py` | `get_auto_reply` | Returns `None` when the single child has no move. | Checks `if child.move is None: return None`; `test_metadata_child_returns_none` covers this. | OK |
| `sgf_engine/core/autoreply.py` | `get_auto_reply` | Returns `None` when the single child move color equals `player_color`. | Only returns when color equals `opponent`; `test_single_same_color_child_returns_none` covers same-color child. | OK |
| `sgf_engine/core/autoreply.py` | `get_auto_reply` | Does not mutate SGFNode, Move, children, parent, or metadata. | Function only reads child count, first child, and child move fields; no assignment or mutating method call appears. | OK |
| `sgf_engine/core/autoreply.py` | `get_auto_reply` | Does not call matcher, override loader, parser, logging, DB writes, success/fail evaluation, or metadata result reads. | Imports and body contain only `opponent_of`, `Move`, `SGFNode`, child inspection, and returns. | OK |
| `tests/sgf_engine/test_autoreply.py` | test coverage | Zero-child `None` behavior is covered only indirectly by invalid-color ordering, not as a valid-color zero-child case. | `test_invalid_player_color_raises_even_without_children` uses `SGFNode()` but expects `ValueError`; no test asserts `get_auto_reply(SGFNode(), "B") is None`. | Warning |

## Branch Priority and Equivalent Semantics

| File path | Function or test name | Exact behavior | Classification |
|---|---|---|---|
| `sgf_engine/core/matcher.py` | `match_move` | If a move matches both a direct child and an override alternative, direct child wins because `find_child_by_move` is checked before `equivalent_moves`. | OK |
| `tests/sgf_engine/test_matcher.py` | `test_branch_is_checked_before_equivalent` | Creates child `B[dd]` and override `{"equivalent_moves": {"pp": ["dd"]}}`; asserts `match_move(root, "dd", override) == BRANCH`. | OK |
| `sgf_engine/core/matcher.py` | `match_move` | Treats `override["equivalent_moves"]` as canonical coordinate keys with alternatives as values; matcher checks only whether the played move appears in alternatives. | OK |
| `sgf_engine/core/matcher.py` | `match_move` | Only classifies `EQUIVALENT`; it does not resolve the canonical coordinate or advance to a canonical node. | OK |
| `tests/sgf_engine/test_engine.py` | `test_apply_move_equivalent_resolves_canonical_branch` | Engine-level test shows canonical branch resolution happens in `engine.apply_move`, not in matcher. | OK |
| `tests/sgf_engine/test_matcher.py` | matcher tests | Explicitly covers BRANCH, EQUIVALENT, OFF_TREE, BRANCH over EQUIVALENT, `None` override, and result metadata not affecting matching. | OK |
| `tests/sgf_engine/test_matcher.py` | matcher tests | Missing explicit coverage for override dict with missing `equivalent_moves`, malformed `equivalent_moves`, and non-list alternatives. Code handles missing key via default `{}`, but malformed types are unspecified. | Warning |

## Tree Access and Mutation Findings

| File path | Function name | Exact access or mutation pattern | Classification |
|---|---|---|---|
| `sgf_engine/core/matcher.py` | `match_move` | Reads through `find_child_by_move(current_node, move_coord)` and never assigns to `children`, `parent`, `metadata`, `Move.color`, or `Move.coord`. | OK |
| `sgf_engine/core/tree.py` | `find_child_by_move` | Helper iterates `node.children` and reads `child.move.coord`; returns the child node to caller. Matcher uses this only for existence testing. | OK |
| `sgf_engine/core/autoreply.py` | `get_auto_reply` | Reads `len(current_node.children)`, `current_node.children[0]`, `child.move`, and `child.move.color`; returns `child.move`. No mutation appears. | OK |
| `tests/sgf_engine/test_engine.py` | `_attach` | Test helper mutates `child.parent` and `parent.children`, but this is test setup, not matcher/autoreply behavior. | OK |

## Override Boundary Findings

| File path | Function name | Exact behavior | Classification |
|---|---|---|---|
| `sgf_engine/core/matcher.py` | `match_move` | Receives `override` as `dict | None` argument and reads `(override or {}).get("equivalent_moves") or {}`. | OK |
| `sgf_engine/core/matcher.py` | `match_move` | Does not load `puzzle_variation_overrides.json`, does not call `override_loader.load_override`, and does not call `canonical_coord_for`. | OK |
| `sgf_engine/core/matcher.py` | `match_move` | Does not mutate override, infer canonical moves, or generate equivalent moves; it only checks membership in provided alternatives. | OK |
| `sgf_engine/core/autoreply.py` | `get_auto_reply` | Has no override parameter, import, lookup, or dependency. | OK |

## Determinism Findings

| File path | Function name | Exact behavior | Classification |
|---|---|---|---|
| `sgf_engine/core/matcher.py` | `match_move` | Uses no randomness, time, filesystem state, environment variables, cache/global state mutation, previous-call state, logging, or production I/O. Result depends on `current_node`, `move_coord`, and supplied `override`. | OK |
| `sgf_engine/core/autoreply.py` | `get_auto_reply` | Uses no randomness, time, filesystem state, environment variables, cache/global state mutation, previous-call state, logging, or production I/O. Result depends on `current_node` and `player_color`. | OK |
| `tests/sgf_engine/test_engine.py` | `test_identical_inputs_produce_identical_result_values` | Engine-level determinism test covers identical `apply_move` inputs producing identical result values, but there is no separate matcher/autoreply immutability or repeat-call assertion. | Warning |

## Test Masking Findings

| Test file path | Test name | Mocked/skipped/hidden behavior | Whether appropriate | Classification |
|---|---|---|---|---|
| `tests/sgf_engine/test_matcher.py` | all tests | No mocking of matcher internals appears. Tests instantiate `SGFNode`/`Move` directly and call `match_move`. | Appropriate. | OK |
| `tests/sgf_engine/test_autoreply.py` | all tests | No mocking of autoreply internals appears. Tests instantiate `SGFNode`/`Move` directly and call `get_auto_reply`. | Appropriate. | OK |
| `tests/sgf_engine/test_engine.py` | engine tests | Monkeypatches `engine.override_loader.load_override` and `engine.log_off_tree`, but does not mock matcher or autoreply logic. | Appropriate for isolating engine orchestration from file loading/logging while preserving matcher/autoreply behavior through engine calls. | OK |
| `tests/sgf_engine/test_matcher.py` | matcher tests | Does not assert tree immutability before/after `match_move`. Code review found no mutation, but the test suite would not catch a future accidental mutation. | Coverage gap. | Warning |
| `tests/sgf_engine/test_autoreply.py` | autoreply tests | Does not assert tree immutability before/after `get_auto_reply`. Code review found no mutation, but the test suite would not catch a future accidental mutation. | Coverage gap. | Warning |
| `tests/sgf_engine/test_matcher.py` | matcher tests | Covers BRANCH over EQUIVALENT, invalid coordinate, and result metadata non-read; does not cover missing `equivalent_moves` separately from `None` override, nor malformed alternative structures. | Partial gap; behavior for malformed structures is not specified in the mission beyond asking to inspect coverage. | Warning |
| `tests/sgf_engine/test_autoreply.py` | autoreply tests | Covers invalid `player_color`, same-color child, child move `None`, and multiple children; lacks valid-color zero-child assertion. | Minor coverage gap. | Warning |

## Cross-Module Orchestration Findings

| File path | Exact import/call/access pattern | Classification |
|---|---|---|
| `sgf_engine/core/matcher.py` | Imports `sgf_to_xy`, `SGFNode`, and `find_child_by_move`; body performs coordinate validation, direct child existence check, supplied override membership check, and returns a match type. It does not combine override loading, autoreply, traversal advancement, result reading, parsing, DB logging, or engine-like sequencing. | OK |
| `sgf_engine/core/autoreply.py` | Imports `opponent_of`, `Move`, and `SGFNode`; body validates color and inspects only immediate child conditions. It does not call matcher, override loading, parser, DB logging, result reading, or engine-like sequencing. | OK |

## Additional Files That May Require Owner-Approved Review

- `sgf_engine/engine/engine.py` may require owner-approved review if the next audit needs to verify that traversal, canonical equivalent resolution, result evaluation, override loading, and off-tree logging remain exclusively in the engine layer.
- `sgf_engine/override/*` may require owner-approved review if the next audit needs to verify the canonical-coordinate override boundary from the loader side.

## Final Classification

PASS WITH WARNINGS
