# Independent Override Purity Review

## Scope

Verification-only review of `sgf_engine/override/override_loader.py` for purity, determinism, production-boundary isolation, JSON behavior, defensive-copy behavior, and `equivalent_moves` semantics.

No production code was modified. Review was limited to the files allowed by the mission request.

## Files Reviewed

- `sgf_engine/override/override_loader.py`
- `puzzle_variation_overrides.json`
- `tests/sgf_engine/test_override_loader.py`
- `tests/sgf_engine/test_engine.py`
- `docs/testing/modification_log.md`

## Import Inventory

| File path | Exact import statement | Classification |
|---|---|---|
| `sgf_engine/override/override_loader.py` | `from __future__ import annotations` | standard library |
| `sgf_engine/override/override_loader.py` | `import copy` | standard library |
| `sgf_engine/override/override_loader.py` | `import json` | standard library |
| `sgf_engine/override/override_loader.py` | `from pathlib import Path` | standard library |

Finding: OK. `override_loader.py` imports only standard-library modules.

## Production Dependency Findings

| File path | Function name | Exact import/call/access pattern | Classification |
|---|---|---|---|
| `sgf_engine/override/override_loader.py:3-7` | module scope | Imports are limited to `__future__`, `copy`, `json`, and `Path`. No `app.py`, `db.py`, Flask, routes, models, Redis, Socket.IO, PostgreSQL helpers, application config, production DB helpers, or `question_overrides` import appears. | OK |
| `sgf_engine/override/override_loader.py:10-12` | module scope | `OVERRIDES_FILE = Path(__file__).resolve().parents[2] / "puzzle_variation_overrides.json"` resolves the JSON override file path only. | OK |
| `sgf_engine/override/override_loader.py:52-73` | `load_override` | Opens only `OVERRIDES_FILE` with UTF-8 and parses it with `json.load`. | OK |

No production application dependency was found in the reviewed loader.

## Side-Effect Findings

| File path | Function name | Exact call/access pattern | Classification |
|---|---|---|---|
| `sgf_engine/override/override_loader.py:55-56` | `load_override` | `with OVERRIDES_FILE.open("r", encoding="utf-8") as handle:` followed by `document = json.load(handle)`. This is a read-only file access to the allowed override JSON. | OK |
| `sgf_engine/override/override_loader.py:61-68` | `load_override` | Builds local `normalized_document` from parsed JSON; no writeback to file, cache, DB, or global state. | OK |
| `sgf_engine/override/override_loader.py:31-47` | `_validate_entry` | Builds local `seen_alternatives`; reads `entry` and nested values without assigning into them. | OK |
| `sgf_engine/override/override_loader.py:76-88` | `canonical_coord_for` | Reads the passed `override` dictionary and returns the matched canonical key; no mutation is performed. | OK |

No file writes, DB access, network access, environment-variable reads, production logging, SGF tree mutation, input-argument mutation, global override mutation, cache writes, database writes, or external-service writes were found.

## JSON Loading Behavior

| File path | Function name | Exact behavior | Evidence | Classification |
|---|---|---|---|---|
| `sgf_engine/override/override_loader.py:55-59` | `load_override` | Malformed JSON raises from `json.load`; no `try/except` hides parse errors. Non-object JSON raises `ValueError`. | Code calls `json.load(handle)` directly, then checks `isinstance(document, dict)`. | OK |
| `tests/sgf_engine/test_override_loader.py:43-49` | `test_malformed_json_raises` | Test writes `{malformed` and expects `json.JSONDecodeError`. | `with pytest.raises(json.JSONDecodeError): override_loader.load_override(...)`. | OK |

Malformed JSON does not silently return `None`, `{}`, default data, or a fallback object.

## Missing Source Behavior

| File path | Function name | Exact behavior | Evidence | Classification |
|---|---|---|---|---|
| `sgf_engine/override/override_loader.py:54,70-72` | `load_override` | Normalizes the requested source with slash replacement and whitespace trimming, performs exact dictionary lookup, and returns `None` when absent. | `entry = normalized_document.get(normalized_source)` followed by `if entry is None: return None`. | OK |
| `tests/sgf_engine/test_override_loader.py:36-40` | `test_missing_source_returns_none` | Empty override document returns `None` for missing source. | Assertion is `override_loader.load_override("SGF/path/missing.sgf") is None`. | OK |

No fuzzy matching, fallback to another source, or nearby-source inference was found.

## Defensive Copy and Mutation Safety

| File path | Function name | Exact copy or mutation behavior | Evidence | Classification |
|---|---|---|---|---|
| `sgf_engine/override/override_loader.py:73` | `load_override` | Returns `copy.deepcopy(_validate_entry(normalized_source, entry))`. | The returned object is a deep copy of the validated parsed entry. | OK |
| `sgf_engine/override/override_loader.py:55-56` | `load_override` | Reloads JSON from disk for each call; no module-level parsed override dictionary is cached. | `json.load` occurs inside `load_override`. | OK |
| `tests/sgf_engine/test_override_loader.py:14-33` | `test_load_override_normalizes_source_and_returns_copy` | Test mutates the returned dictionary's top-level `quality` value, then reloads and expects original `gold`. | `loaded["quality"] = "mutated"` followed by second `load_override` assertion. | OK |

Returned override data is mutable by callers, but the reviewed implementation returns a deep copy and does not expose module-global override data. The existing mutation test covers top-level mutation; nested mutation is protected by the same `deepcopy` implementation but is not separately asserted.

## equivalent_moves Semantics

| File path | Function or test name | Exact behavior | Classification |
|---|---|---|---|
| `sgf_engine/override/override_loader.py:25-49` | `_validate_entry` | Reads `equivalent_moves` as a dictionary where each canonical coordinate key maps to a list of alternative coordinates. Rejects non-dict `equivalent_moves`, non-string canonical keys, non-list alternatives, non-string alternatives, and alternatives that map to multiple canonical moves. | OK |
| `sgf_engine/override/override_loader.py:76-88` | `canonical_coord_for` | Resolves `equivalent_coord` by scanning alternatives and returning the single matching canonical coordinate. Raises `ValueError` unless exactly one canonical match exists. | OK |
| `puzzle_variation_overrides.json:1` | JSON data | Current authoritative override file is `{}`. It contains no live `equivalent_moves` entries to contradict loader/test semantics. | OK |
| `tests/sgf_engine/test_override_loader.py:52-64` | `test_ambiguous_equivalent_raises` | Confirms one alternative declared under two canonical coordinates raises `ValueError`. | OK |
| `tests/sgf_engine/test_override_loader.py:67-70` | `test_canonical_coord_for_resolves_declared_alternative` | Confirms alternative `pp` resolves to canonical `dd` when override is `{"equivalent_moves": {"dd": ["pp", "qq"]}}`. | OK |
| `tests/sgf_engine/test_engine.py:30-46` | `test_apply_move_equivalent_resolves_canonical_branch` | Engine test models player alternative `pp` resolving to canonical SGF tree branch `dd`; expected `matched_type` is `equivalent`. | OK |
| `tests/sgf_engine/test_engine.py:49-63` | `test_equivalent_missing_from_tree_raises_specific_error` | Engine test expects an error when the declared canonical coordinate `cc` is not present in the SGF tree. | OK |
| `tests/sgf_engine/test_engine.py:13-27` | `test_apply_move_branch_then_auto_reply_then_result` | Confirms normal branch matching takes place when `load_override` returns `None`. It does not test branch priority when an override is present and the submitted move could also be involved in `equivalent_moves`. | Warning |

Semantics are consistent in the reviewed loader and tests: keys are canonical SGF tree moves, values are player alternative moves, `canonical_coord_for` resolves alternative move to canonical move, and ambiguous alternatives are rejected. The remaining warning is test coverage only: branch-priority behavior with an active override is not directly asserted in the reviewed tests.

## SGF Tree Isolation

| File path | Exact import/call/access pattern | Classification |
|---|---|---|
| `sgf_engine/override/override_loader.py:3-7` | Imports only `__future__`, `copy`, `json`, and `Path`; no `SGFNode`, `Move`, `tree.py`, `matcher.py`, `autoreply.py`, or `engine.py` import appears. | OK |
| `sgf_engine/override/override_loader.py:15-88` | Functions operate on strings, dictionaries, lists, and JSON file data only. No SGF tree object is accessed or mutated. | OK |

No SGF tree mutation or engine orchestration was found in `override_loader.py`.

## Test Masking Findings

| Test file path | Test name | Mocked/skipped/hidden behavior | Whether appropriate | Classification |
|---|---|---|---|---|
| `tests/sgf_engine/test_override_loader.py:14-33` | `test_load_override_normalizes_source_and_returns_copy` | Monkeypatches `override_loader.OVERRIDES_FILE` to a temp JSON file. | Appropriate; isolates file content while exercising real loader logic. | OK |
| `tests/sgf_engine/test_override_loader.py:36-40` | `test_missing_source_returns_none` | Monkeypatches `OVERRIDES_FILE` to an empty temp JSON file. | Appropriate; exercises missing-source behavior directly. | OK |
| `tests/sgf_engine/test_override_loader.py:43-49` | `test_malformed_json_raises` | Monkeypatches `OVERRIDES_FILE` to malformed temp JSON. | Appropriate; directly verifies malformed JSON raises. | OK |
| `tests/sgf_engine/test_override_loader.py:52-64` | `test_ambiguous_equivalent_raises` | Monkeypatches `OVERRIDES_FILE` to an ambiguous temp JSON document. | Appropriate; directly verifies duplicate-alternative validation. | OK |
| `tests/sgf_engine/test_engine.py:13-115` | all listed engine tests | Monkeypatches `engine.override_loader.load_override` rather than reading `puzzle_variation_overrides.json`. | Appropriate for unit isolation of engine behavior, but it masks integration with real JSON loading and cannot detect real override-file parse or validation failures in engine flows. | Warning |
| `tests/sgf_engine/test_engine.py:13-46` | branch and equivalent tests | Branch behavior is tested with no override, and equivalent behavior is tested with an override. The reviewed tests do not cover a case where a direct branch move and an equivalent override could both affect matching priority. | Coverage gap; no purity violation in loader. | Warning |
| `tests/sgf_engine/test_override_loader.py:14-33` | defensive-copy test | Mutates only a top-level returned field. | Acceptable because loader uses `copy.deepcopy`, but a nested mutation assertion would make the guarantee explicit. | Warning |

No test was found that hides malformed JSON behavior in `override_loader.py`; the malformed JSON case is explicitly covered.

## Additional Files That May Require Owner-Approved Review

- `sgf_engine/engine/engine.py`: may be needed only if an owner wants independent code-level verification of engine branch-priority orchestration beyond the reviewed `tests/sgf_engine/test_engine.py` evidence. This file was not opened because it is outside the allowed read scope for this mission.

## Final Classification

PASS WITH WARNINGS
