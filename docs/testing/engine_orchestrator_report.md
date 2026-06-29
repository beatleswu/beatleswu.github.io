# Independent Engine Orchestrator Final Review

## Scope

Verification-only audit of `sgf_engine/engine/engine.py` as the SGF Engine orchestrator.

No production code was modified. Review was limited to the mission-approved files. Files outside that scope were not opened automatically.

## Files Reviewed

- `sgf_engine/engine/engine.py`
- `tests/sgf_engine/test_engine.py`
- `sgf_engine/core/tree.py`
- `sgf_engine/core/matcher.py`
- `sgf_engine/core/autoreply.py`
- `sgf_engine/override/override_loader.py`
- `docs/testing/sgf_engine_owner_decisions.md`
- `docs/testing/verification_dependency_boundaries.md`
- `docs/testing/matcher_autoreply_responsibility_report.md`
- `docs/testing/override_purity_report.md`
- `docs/testing/modification_log.md`

## Import Inventory

| File path | Exact import statement | Classification |
|---|---|---|
| `sgf_engine/engine/engine.py:3` | `from __future__ import annotations` | standard library |
| `sgf_engine/engine/engine.py:5` | `from dataclasses import dataclass` | standard library |
| `sgf_engine/engine/engine.py:7` | `from sgf_engine.core import autoreply, matcher, tree` | sgf_engine internal |
| `sgf_engine/engine/engine.py:8` | `from sgf_engine.core.tree import Move, SGFNode` | sgf_engine internal |
| `sgf_engine/engine/engine.py:9` | `from sgf_engine.override import override_loader` | sgf_engine internal |
| `sgf_engine/engine/engine.py:22` | `from db import get_db` | documented boundary exception |

## Production Dependency Findings

| File path | Function name | Exact import/call/access pattern | Covered by owner decision | Classification |
|---|---|---|---|---|
| `sgf_engine/engine/engine.py:20-42` | `log_off_tree` | Lazy import `from db import get_db`; call `with get_db() as connection:`; writes unmatched move table/row with `connection.execute(...)`; commits with `connection.commit()`. | Yes. `docs/testing/sgf_engine_owner_decisions.md:9-15` records OFF_TREE logging as required product behavior, accepts `log_off_tree` direct `db.get_db` dependency temporarily, and forbids any further production application dependencies. | Documented Boundary Exception |
| `sgf_engine/engine/engine.py:75` | `apply_move` | Calls `log_off_tree(source, move_coord, player_color)` only in the OFF_TREE branch. | Yes, because the call is the current OFF_TREE logging path covered by the owner decision. | Documented Boundary Exception |
| `sgf_engine/engine/engine.py` | module scope / `apply_move` | No import or direct call to `app.py`, Flask, routes, models, Redis, Socket.IO, PostgreSQL helpers, application config, or production database helpers other than `log_off_tree -> db.get_db`. | Not needed; no additional production dependency found in reviewed code. | OK |

## Orchestration Sequence Findings

| File path | Function name | Exact behavior/sequence | Code evidence | Test evidence | Classification |
|---|---|---|---|---|---|
| `sgf_engine/engine/engine.py` | `apply_move` | Step 1 loads override before matching. | `override = override_loader.load_override(source)` at line 53. | Tests monkeypatch `engine.override_loader.load_override` before calling `apply_move` at `tests/sgf_engine/test_engine.py:20`, `37-39`, `52-54`, `69`, `92`, and `110`. | OK |
| `sgf_engine/engine/engine.py` | `apply_move` | Step 2 delegates move classification to matcher. | `matched = matcher.match_move(current_node, move_coord, override)` at line 56. | Branch, equivalent, and off-tree paths are asserted in `test_apply_move_branch_then_auto_reply_then_result`, `test_apply_move_equivalent_resolves_canonical_branch`, and `test_off_tree_logs_and_returns_without_validity_judgment`. | OK |
| `sgf_engine/engine/engine.py` | `apply_move` | Step 3 advances BRANCH via `tree.find_child_by_move`, advances EQUIVALENT through canonical coordinate lookup then `tree.find_child_by_move`, or logs/returns OFF_TREE. | Lines 59-81. | Tests cover branch advancement at lines 22-27, equivalent canonical advancement at lines 41-46, missing canonical error at lines 56-63, and OFF_TREE result at lines 76-82. | OK |
| `sgf_engine/engine/engine.py` | `apply_move` | Step 4 delegates auto-reply decision to `autoreply.get_auto_reply`; if a reply exists, advances with `tree.find_child_by_move(reply.coord)`. | Lines 83-89. | `test_apply_move_branch_then_auto_reply_then_result` asserts the final node is the reply node and `auto_reply == Move("W", "pp")`; `test_same_color_single_child_is_not_auto_replied` asserts no auto-reply. | OK |
| `sgf_engine/engine/engine.py` | `apply_move` | Step 5 reads result metadata after traversal and optional auto-reply, defaulting to `"continue"`. | `result = current_node.metadata.get("result", "continue")` at line 92, then returned at lines 93-98. | Branch plus auto-reply result is asserted as `"success"` at `tests/sgf_engine/test_engine.py:24`; equivalent/no explicit reply result is asserted as `"continue"` at line 43; same-color no auto-reply result is asserted at line 97. | OK |

## Delegation and Encapsulation Findings

| File path | Function name | Exact call/access pattern | Classification |
|---|---|---|---|
| `sgf_engine/engine/engine.py:53` | `apply_move` | Delegates override loading to `override_loader.load_override(source)`. | OK |
| `sgf_engine/engine/engine.py:56` | `apply_move` | Delegates matching to `matcher.match_move(current_node, move_coord, override)`. | OK |
| `sgf_engine/engine/engine.py:60,68,86` | `apply_move` | Delegates tree lookup/traversal to `tree.find_child_by_move(...)`. No direct `.children` access appears in `engine.py`. | OK |
| `sgf_engine/engine/engine.py:67` | `apply_move` | Delegates canonical equivalent resolution to `override_loader.canonical_coord_for(override, move_coord)`. | OK |
| `sgf_engine/engine/engine.py:84` | `apply_move` | Delegates auto-reply decision to `autoreply.get_auto_reply(current_node, player_color)`. | OK |
| `sgf_engine/engine/engine.py` | `apply_move` / `log_off_tree` | No SGF parsing, override JSON reading, player-color validation reimplementation, BRANCH-vs-EQUIVALENT priority reimplementation, or auto-reply logic reimplementation appears. | OK |
| `sgf_engine/core/matcher.py:30-39` | `match_move` | BRANCH priority over EQUIVALENT lives in matcher, not engine; engine consumes `matched`. | OK |
| `sgf_engine/core/autoreply.py:11-23` | `get_auto_reply` | Player-color validation and sole-opponent-child decision live in autoreply, not engine. | OK |

## EngineResult Contract Findings

| File path | Function or test name | Exact behavior | Classification |
|---|---|---|---|
| `sgf_engine/engine/engine.py:12-17` | `EngineResult` | Dataclass includes `status`, `node`, `matched_type`, and `auto_reply`. | OK |
| `sgf_engine/engine/engine.py:59-63,93-98` | BRANCH path | Advances to branch node, then returns `status=current_node.metadata.get(...)`, `node=current_node`, `matched_type=matched.value`, and `auto_reply=reply`. | OK |
| `tests/sgf_engine/test_engine.py:13-27` | `test_apply_move_branch_then_auto_reply_then_result` | Covers BRANCH plus auto-reply fields: `status == "success"`, `node is reply_node`, `matched_type == "branch"`, and `auto_reply == Move("W", "pp")`. | OK |
| `sgf_engine/engine/engine.py:64-73,93-98` | EQUIVALENT path | Resolves canonical coord, advances to canonical SGF node, and returns `matched_type=matched.value`. | OK |
| `tests/sgf_engine/test_engine.py:30-46` | `test_apply_move_equivalent_resolves_canonical_branch` | Covers EQUIVALENT fields: `status == "continue"`, `node is canonical`, `matched_type == "equivalent"`, and `auto_reply is None`. | OK |
| `sgf_engine/engine/engine.py:74-81` | OFF_TREE path | Logs OFF_TREE and returns `EngineResult(status="off_tree", node=None, matched_type=matcher.OFF_TREE.value, auto_reply=None)`. | OK |
| `tests/sgf_engine/test_engine.py:66-82` | `test_off_tree_logs_and_returns_without_validity_judgment` | Covers log call shape and OFF_TREE result fields. | OK |
| `sgf_engine/engine/engine.py:69-73` | equivalent canonical missing from SGF tree | Raises `ValueError`; no `EngineResult` is returned and there is no OFF_TREE fallback. | OK |
| `tests/sgf_engine/test_engine.py:49-63` | `test_equivalent_missing_from_tree_raises_specific_error` | Covers the specific missing-canonical error message. | OK |

## Edge Case Handling Findings

| File path | Function name | Exact behavior | Code evidence | Test evidence | Classification |
|---|---|---|---|---|---|
| `sgf_engine/engine/engine.py` | `apply_move` | Raises `ValueError` when `matcher.EQUIVALENT` occurs but canonical coordinate cannot be found in the SGF tree. | Lines 67-73. | `tests/sgf_engine/test_engine.py:49-63`. | OK |
| `sgf_engine/engine/engine.py` | `apply_move` | Does not silently fall through from EQUIVALENT failure to OFF_TREE; the EQUIVALENT branch raises before the `else` OFF_TREE branch can run. | EQUIVALENT handling is an `elif` at lines 64-73; OFF_TREE is the separate `else` at lines 74-81. | Missing-canonical test expects `ValueError`, not OFF_TREE. | OK |
| `sgf_engine/engine/engine.py` | `apply_move` | OFF_TREE returns `status="off_tree"`, `node=None`, `matched_type="off_tree"`, and `auto_reply=None`. It does not classify the move as success/fail or reason about validity. | Lines 74-81. | `tests/sgf_engine/test_engine.py:66-82`. | OK |
| `sgf_engine/engine/engine.py` | `apply_move` | Reads node metadata only after traversal and optional auto-reply. | Metadata access appears only at line 92 after tree advancement and auto-reply block. | `test_apply_move_branch_then_auto_reply_then_result` proves reply metadata drives status after auto-reply. | OK |
| `sgf_engine/engine/engine.py` | `apply_move` | Defaults missing metadata result to `"continue"`. | `current_node.metadata.get("result", "continue")` at line 92. | Equivalent path with metadata `"continue"` and same-color path with `"continue"` are covered, but no test uses an empty metadata dict after successful traversal. | Warning |

## Side-Effect Findings

| File path | Function name | Exact call/access pattern | Classification |
|---|---|---|---|
| `sgf_engine/engine/engine.py:20-42` | `log_off_tree` | Imports `db.get_db`, creates `puzzle_unmatched_moves` if needed, inserts one unmatched move row, and commits. | Documented Boundary Exception |
| `sgf_engine/engine/engine.py:53` | `apply_move` | Calls `override_loader.load_override(source)`, which reads `puzzle_variation_overrides.json` through `override_loader.py`; this is delegated override loading, not direct JSON access in engine. | OK |
| `sgf_engine/engine/engine.py:45-98` | `apply_move` | Reassigns the local `current_node` variable to existing nodes returned by tree helper; no assignments to `children`, `parent`, `metadata`, module globals, environment variables, files, network, logging, or caches appear. | OK |
| `sgf_engine/engine/engine.py` | module scope / functions | No file writes, network access, environment variable reads, production logging, unexpected external/global state accumulation, or SGF tree structure mutation found outside the documented OFF_TREE DB write. | OK |

## Test Masking Findings

| Test file path | Test name | Mocked/skipped/hidden behavior | Whether appropriate for unit isolation | Classification |
|---|---|---|---|---|
| `tests/sgf_engine/test_engine.py:13-27` | `test_apply_move_branch_then_auto_reply_then_result` | Monkeypatches `override_loader.load_override` to return `None`, so real JSON override loading is not exercised. | Appropriate for unit isolation of branch/auto-reply/result order, but not evidence of real override-file integration. | Warning |
| `tests/sgf_engine/test_engine.py:30-46` | `test_apply_move_equivalent_resolves_canonical_branch` | Monkeypatches `override_loader.load_override` to return an in-memory override. | Appropriate for unit isolation of canonical equivalent traversal, but it does not cover real JSON loading through `engine.apply_move`. | Warning |
| `tests/sgf_engine/test_engine.py:49-63` | `test_equivalent_missing_from_tree_raises_specific_error` | Monkeypatches `override_loader.load_override` to return an in-memory override. | Appropriate for the edge case, but still masks real JSON loading. | Warning |
| `tests/sgf_engine/test_engine.py:66-82` | `test_off_tree_logs_and_returns_without_validity_judgment` | Monkeypatches `engine.log_off_tree`, hiding the lazy `from db import get_db` import and real DB writes. | Appropriate for unit isolation of `apply_move`, but persistence behavior still requires separate integration coverage per owner decision. | Warning |
| `tests/sgf_engine/test_engine.py` | all tests | No test exercises real JSON override loading through `engine.apply_move`. | Unit isolation is reasonable, but this is an engine-level integration coverage gap. | Warning |
| `tests/sgf_engine/test_engine.py` | all tests | No test records or asserts the full Step 1-5 call order with spies. | Existing tests cover outcomes of the sequence, but not exact call order mechanically. | Warning |
| `tests/sgf_engine/test_engine.py:49-63` | `test_equivalent_missing_from_tree_raises_specific_error` | Covers EQUIVALENT canonical missing error. | Appropriate and directly covers required edge case. | OK |
| `tests/sgf_engine/test_engine.py:66-82` | `test_off_tree_logs_and_returns_without_validity_judgment` | Covers OFF_TREE result fields, including `matched_type` and `auto_reply`. | Appropriate for unit isolation. | OK |
| `tests/sgf_engine/test_engine.py:13-27,30-46` | branch/equivalent tests | Cover `matched_type` and `auto_reply` for branch-with-auto-reply and equivalent-without-auto-reply. | Appropriate. | OK |
| `tests/sgf_engine/test_engine.py` | all tests | No successful path uses a node with missing `metadata["result"]` to assert default `"continue"`. | Coverage gap; code evidence still shows the default at `engine.py:92`. | Warning |
| `tests/sgf_engine/test_engine.py` | all tests | No engine-level test covers branch priority under an active override. | Coverage gap; matcher-level responsibility report records matcher-level branch priority coverage, and engine delegates to matcher. | Warning |

## Cross-Report Consistency Findings

| Report file | engine.py behavior | Consistency result | Classification |
|---|---|---|---|
| `docs/testing/sgf_engine_owner_decisions.md:9-15` | `log_off_tree` directly imports `db.get_db`; `apply_move` reaches it only in OFF_TREE handling. | Consistent. The owner decision accepts this exact dependency temporarily and forbids additional production dependencies. | Documented Boundary Exception |
| `docs/testing/verification_dependency_boundaries.md:87-97,123-129,153-158` | Earlier dependency report found the same `from db import get_db` in `log_off_tree` and no other direct production dependency in `apply_move`. | Consistent, with classification updated from pre-decision "Needs owner decision" to current "Documented Boundary Exception" because the owner decision now exists. | OK |
| `docs/testing/matcher_autoreply_responsibility_report.md:43-53,59-66,73-78,111-117` | Engine delegates matching and auto-reply; matcher owns BRANCH/EQUIVALENT/OFF_TREE classification and autoreply owns sole-opponent-child decision. | Consistent. No engine contradiction found. Test coverage warnings also align with existing responsibility report warnings. | OK |
| `docs/testing/override_purity_report.md:81-90,105-110` | Engine uses `override_loader.load_override` and `canonical_coord_for`; tests monkeypatch `load_override` and do not cover real JSON loading through engine. | Consistent. Engine behavior matches override semantics; the same engine-level real-JSON and active-override branch-priority test gaps remain warnings. | OK |

## Additional Files That May Require Owner-Approved Review

- `db.py` - referenced by `sgf_engine/engine/engine.py::log_off_tree` via `from db import get_db`; not opened because it is outside this mission's read scope.
- `puzzle_variation_overrides.json` - read by `override_loader.load_override`; not opened because it is outside this mission's read scope.
- `tests/sgf_engine/test_matcher.py` - cited only through existing reports for matcher branch-priority coverage; not opened because it is outside this mission's read scope.
- `tests/sgf_engine/test_override_loader.py` - cited only through existing reports for override loader coverage; not opened because it is outside this mission's read scope.

## Final Classification

PASS WITH WARNINGS
