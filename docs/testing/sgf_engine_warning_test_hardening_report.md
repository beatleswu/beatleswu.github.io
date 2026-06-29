# SGF Engine Warning Test Hardening Report

## Scope

Focused test coverage hardening for SGF Engine PASS WITH WARNINGS findings only.

This task added unit tests for parser malformed-input handling, coordinate utility negative validation, override loader defensive copying, matcher immutability/determinism, autoreply empty-node and immutability behavior, and engine orchestration warnings.

No production implementation changes, refactors, Gold SGF fixtures, API wiring, or DB integration tests were added.

## Files Modified

- `tests/sgf_engine/test_parser_errors.py`
- `tests/sgf_engine/test_coord_utils.py`
- `tests/sgf_engine/test_override_loader.py`
- `tests/sgf_engine/test_matcher.py`
- `tests/sgf_engine/test_autoreply.py`
- `tests/sgf_engine/test_engine.py`
- `docs/testing/sgf_engine_warning_test_hardening_report.md`
- `docs/testing/modification_log.md`

## Tests Added

| File path | Test name | Warning addressed | Passed |
|---|---|---|---|
| `tests/sgf_engine/test_parser_errors.py` | `test_structurally_invalid_sgf_raises_without_partial_tree[(;b[dd])]` | Lowercase move property must raise `ValueError`. | Yes |
| `tests/sgf_engine/test_parser_errors.py` | `test_structurally_invalid_sgf_raises_without_partial_tree[(;Ab[dd])]` | Mixed-case property identifier must raise `ValueError`. | Yes |
| `tests/sgf_engine/test_parser_errors.py` | `test_structurally_invalid_sgf_raises_without_partial_tree[(;B)]` | Property identifier with no value must raise `ValueError`. | Yes |
| `tests/sgf_engine/test_parser_errors.py` | `test_structurally_invalid_sgf_raises_without_partial_tree[(;B[dd]())]` | Empty nested variation must raise `ValueError`. | Yes |
| `tests/sgf_engine/test_parser_errors.py` | `test_structurally_invalid_sgf_raises_without_partial_tree[(;B[dd](;W[pp])]` | Broken variation structure must raise `ValueError`. | Yes |
| `tests/sgf_engine/test_parser_errors.py` | `test_structurally_invalid_sgf_raises_without_partial_tree[(;B[dd][pp])]` | Move property with multiple values must raise `ValueError`. | Yes |
| `tests/sgf_engine/test_parser_errors.py` | `test_structurally_invalid_sgf_raises_without_partial_tree[(;C[abc\\]` | Incomplete trailing escape in a comment must raise `ValueError`. | Yes |
| `tests/sgf_engine/test_parser_errors.py` | `test_failed_parse_does_not_poison_later_valid_parse` | Failed parse must not poison a later valid parse through the public API. | Yes |
| `tests/sgf_engine/test_coord_utils.py` | `test_invalid_xy_raises[coords5]` | `bool` y coordinate must be rejected. | Yes |
| `tests/sgf_engine/test_coord_utils.py` | `test_invalid_xy_raises[coords6]` | Non-int y coordinate must be rejected. | Yes |
| `tests/sgf_engine/test_coord_utils.py` | `test_invalid_xy_raises[coords7]` | Non-int x coordinate beyond bool must be rejected. | Yes |
| `tests/sgf_engine/test_coord_utils.py` | `test_invalid_xy_raises[coords8]` | Non-int y coordinate beyond bool/string must be rejected. | Yes |
| `tests/sgf_engine/test_override_loader.py` | `test_load_override_returns_nested_defensive_copy` | Nested `equivalent_moves` mutation must not affect later loads. | Yes |
| `tests/sgf_engine/test_matcher.py` | `test_match_move_does_not_mutate_tree_or_override` | `match_move` must not mutate SGF tree or override dict. | Yes |
| `tests/sgf_engine/test_matcher.py` | `test_repeated_match_move_calls_return_identical_result` | Repeated `match_move` calls with identical inputs must produce identical `MatchResult`. | Yes |
| `tests/sgf_engine/test_matcher.py` | `test_missing_equivalent_moves_behaves_like_no_equivalent_override` | Missing `equivalent_moves` must behave like no equivalent override. | Yes |
| `tests/sgf_engine/test_autoreply.py` | `test_empty_node_returns_none_for_valid_player_color[B]` | `get_auto_reply(SGFNode(), "B")` must return `None`. | Yes |
| `tests/sgf_engine/test_autoreply.py` | `test_empty_node_returns_none_for_valid_player_color[W]` | `get_auto_reply(SGFNode(), "W")` must return `None`. | Yes |
| `tests/sgf_engine/test_autoreply.py` | `test_get_auto_reply_does_not_mutate_tree` | `get_auto_reply` must not mutate the SGF tree. | Yes |
| `tests/sgf_engine/test_autoreply.py` | `test_repeated_get_auto_reply_calls_return_identical_result` | Repeated `get_auto_reply` calls with identical inputs must produce identical results. | Yes |
| `tests/sgf_engine/test_engine.py` | `test_apply_move_defaults_missing_result_metadata_to_continue` | Successful traversal to a node without `metadata["result"]` must return status `"continue"`. | Yes |
| `tests/sgf_engine/test_engine.py` | `test_apply_move_uses_real_json_override_loading` | `engine.apply_move` must resolve equivalents through real JSON override loading. | Yes |
| `tests/sgf_engine/test_engine.py` | `test_active_override_does_not_override_direct_branch_priority` | Engine-level active override must not override direct branch priority. | Yes |
| `tests/sgf_engine/test_engine.py` | `test_apply_move_step_order_with_lightweight_spies` | Step 1-5 orchestration order must load override, match, traverse player branch, auto-reply, then traverse reply branch. | Yes |

## Warnings Resolved

- Parser malformed SGF coverage now directly covers lowercase identifiers, mixed-case identifiers, missing property values, empty nested variations, broken variation structure, multiple move values, incomplete trailing escapes, and parser state isolation.
- `xy_to_sgf` negative coverage now directly covers non-int `y`, bool `y`, and additional non-int coordinate values.
- Override loader defensive-copy coverage now includes nested `equivalent_moves` mutation.
- Matcher hardening now covers non-mutation, repeated-call determinism, and missing `equivalent_moves`.
- Autoreply hardening now covers empty valid-color nodes, non-mutation, and repeated-call determinism.
- Engine hardening now covers metadata default `"continue"`, real JSON override loading through `apply_move`, active override branch priority, and a lightweight step-order spy.
- OFF_TREE result fields were already fully covered by `test_off_tree_logs_and_returns_without_validity_judgment`; no duplicate test was added.

## Warnings Deferred

- Real DB persistence for `log_off_tree` remains deferred and out of scope. OFF_TREE unit coverage continues to monkeypatch `log_off_tree`.
- Real owner-provided Gold SGF fixture integration remains deferred. Existing integration fixture coverage still skips until owner-provided Gold SGFs exist.
- Malformed `equivalent_moves` matcher behavior remains deferred because malformed override behavior belongs to loader validation and no matcher contract for malformed in-memory override structures was specified.
- Metadata-read observation inside the step-order test remains limited. The test verifies the observable order through auto-reply traversal and final status, but it does not instrument direct dictionary `.get` access because doing so would require invasive production changes or artificial metadata objects.

## Validation Result

Command:

```powershell
python -m pytest tests/sgf_engine -v
```

Result:

```text
86 passed, 1 skipped in 0.34s
```

The skipped test is the existing owner-provided Gold SGF fixture gate:

```text
PENDING: requires 10 manually verified real gold SGFs; found 0. Synthetic SGFs are forbidden.
```

## Production Code Status

- No production code modified.
- No files under `sgf_engine/` were modified.
- No Gold Fixtures created.
- No DB integration added.
