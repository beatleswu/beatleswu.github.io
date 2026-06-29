# Independent Parser Purity Review

## Scope

Verification-only review of whether `sgf_engine/parser/sgf_parser.py` is pure, deterministic, and limited to parsing SGF strings into `SGFNode` trees.

No production code was modified. Review was limited to the files explicitly allowed by the mission.

## Files Reviewed

- `sgf_engine/parser/sgf_parser.py`
- `sgf_engine/core/tree.py`
- `sgf_engine/core/coord_utils.py`
- `tests/sgf_engine/test_parser_errors.py`
- `tests/sgf_engine/test_coord_utils.py`
- `tests/sgf_engine/test_tree.py`
- `docs/testing/modification_log.md`

## Import Inventory

| File | Exact import statement | Classification |
|---|---|---|
| `sgf_engine/parser/sgf_parser.py` | `from __future__ import annotations` | standard library |
| `sgf_engine/parser/sgf_parser.py` | `from dataclasses import dataclass` | standard library |
| `sgf_engine/parser/sgf_parser.py` | `from sgf_engine.core.tree import Move, SGFNode` | sgf_engine internal |
| `sgf_engine/core/tree.py` | `from __future__ import annotations` | standard library |
| `sgf_engine/core/tree.py` | `from dataclasses import dataclass, field` | standard library |
| `sgf_engine/core/tree.py` | `from sgf_engine.core.coord_utils import opponent_of, sgf_to_xy` | sgf_engine internal |

No production application dependency import was found in the reviewed parser or tree files.

## Mutable State Findings

| File | Name | Exact pattern | Classification |
|---|---|---|---|
| `sgf_engine/parser/sgf_parser.py` | `_SGFParser.__init__` | Instance fields `self.source = source` and `self.index = 0` are created per `parse_sgf` call. | OK |
| `sgf_engine/parser/sgf_parser.py` | `_SGFParser.index` | Parse cursor is instance-local and advances during one parse only. `parse_sgf` constructs `_SGFParser(sgf_string)` for each call. | OK |
| `sgf_engine/parser/sgf_parser.py` | `_ParsedNode.properties` | Per-node dictionary returned from `_parse_node`; not module-level or shared across parses. | OK |
| `sgf_engine/parser/sgf_parser.py` | `_build_node.metadata` | New local dictionary per node, including copied property value lists via `{key: list(values) ...}`. | OK |
| `sgf_engine/core/tree.py` | `SGFNode.children` | `field(default_factory=list)` creates a per-instance mutable list. | OK |
| `sgf_engine/core/tree.py` | `SGFNode.metadata` | `field(default_factory=dict)` creates a per-instance mutable dictionary. | OK |

No module-level mutable state, class-level mutable state, cache, singleton, persistent global parse cursor, or shared mutable parse object was found in the reviewed parser file.

## Side-Effect Findings

| File | Function or class | Exact call/access pattern | Classification |
|---|---|---|---|
| `sgf_engine/parser/sgf_parser.py` | `parse_sgf` | Constructs `_SGFParser(sgf_string).parse()` and returns an `SGFNode`; no I/O, DB, network, environment, logging, or external write call appears in the reviewed file. | OK |
| `sgf_engine/parser/sgf_parser.py` | `_parse_game_tree` | Mutates only newly constructed/local `SGFNode` objects by assigning `node.parent`, appending to `current.children`, and updating `parent.metadata`. | OK |
| `sgf_engine/parser/sgf_parser.py` | `_parse_property_value` | Builds a local `result` list and returns `"".join(result)`; no external mutation. | OK |
| `sgf_engine/parser/sgf_parser.py` | `_build_node` | Constructs `Move` and `SGFNode` instances; no external write call appears in the reviewed file. | OK |
| `sgf_engine/core/tree.py` | `Move.__post_init__` | Calls `opponent_of(self.color)` and `sgf_to_xy(self.coord)` for validation. Follow-up review of `sgf_engine/core/coord_utils.py` found no production dependency, side effect, mutable global state, hidden fallback behavior, or nondeterminism. | OK |

No file I/O, DB access, network access, environment variable read, production logging call, external/global state mutation, input argument mutation, or writes to files/cache/database/external services were found in the reviewed parser file.

## Parser Responsibility Findings

| File | Function or class | Exact behavior | Classification |
|---|---|---|---|
| `sgf_engine/parser/sgf_parser.py` | `parse_sgf` | Rejects non-string or blank input with `ValueError`, then parses exactly one game tree. | OK |
| `sgf_engine/parser/sgf_parser.py` | `_parse_game_tree` | Consumes `(`, parses one or more `;` nodes, recurses into `(` variations, and consumes `)`. | OK |
| `sgf_engine/parser/sgf_parser.py` | `_parse_node` | Parses uppercase SGF property identifiers and bracketed values; rejects invalid identifiers and missing values. | OK |
| `sgf_engine/parser/sgf_parser.py` | `_parse_property_value` | Parses SGF property values and escape/newline handling; rejects unterminated or incomplete escapes. | OK |
| `sgf_engine/parser/sgf_parser.py` | `_build_node` | Stores all parsed properties under `metadata["properties"]`, copies comment/result metadata, converts `SZ` to integer, validates `PL`, and constructs `Move` for `B`/`W`. | OK |
| `sgf_engine/parser/sgf_parser.py` | `_build_node` | Rejects a node containing both `B` and `W` moves and rejects move properties with multiple values. | OK |
| `sgf_engine/parser/sgf_parser.py` | `_build_node` | Delegates non-pass move validation to `Move(color=color, coord=coord)`. Follow-up review found `Move.__post_init__` relies on pure `coord_utils` validation only. | OK |

No game outcome inference, answer success/fail inference, override handling, auto-reply behavior, matcher behavior, engine orchestration, DB behavior, Flask/app behavior, or production application behavior was found in the reviewed parser file.

## Malformed SGF Behavior

Code evidence:

- `parse_sgf` raises `ValueError` for non-string or blank input.
- `_consume` raises `ValueError` when expected SGF delimiters are missing.
- `_parse_game_tree` raises `ValueError` for empty game trees with no node.
- `_parse_node` raises `ValueError` for non-uppercase property identifiers and properties without values.
- `_parse_property_value` raises `ValueError` for incomplete escapes and unterminated values.
- `parse` raises `ValueError` for trailing content after one complete tree.
- `_build_node` raises `ValueError` for both `B` and `W` in one node, multiple values on a move property, invalid `SZ`, invalid `PL`, and invalid `Move`.

Malformed cases covered by tests:

| Test file | Test name | Malformed input pattern | Expected behavior |
|---|---|---|---|
| `tests/sgf_engine/test_parser_errors.py` | `test_structurally_invalid_sgf_raises_without_partial_tree` | `""` | `parse_sgf` raises `ValueError` |
| `tests/sgf_engine/test_parser_errors.py` | `test_structurally_invalid_sgf_raises_without_partial_tree` | `"not sgf"` | `parse_sgf` raises `ValueError` |
| `tests/sgf_engine/test_parser_errors.py` | `test_structurally_invalid_sgf_raises_without_partial_tree` | `"()"` | `parse_sgf` raises `ValueError` |
| `tests/sgf_engine/test_parser_errors.py` | `test_structurally_invalid_sgf_raises_without_partial_tree` | `"(;B[dd]"` | `parse_sgf` raises `ValueError` |
| `tests/sgf_engine/test_parser_errors.py` | `test_structurally_invalid_sgf_raises_without_partial_tree` | `"(;B[DD])"` | `parse_sgf` raises `ValueError` |
| `tests/sgf_engine/test_parser_errors.py` | `test_structurally_invalid_sgf_raises_without_partial_tree` | `"(;B[dd]W[pp])"` | `parse_sgf` raises `ValueError` |
| `tests/sgf_engine/test_parser_errors.py` | `test_structurally_invalid_sgf_raises_without_partial_tree` | `"(;PL[black])"` | `parse_sgf` raises `ValueError` |
| `tests/sgf_engine/test_parser_errors.py` | `test_structurally_invalid_sgf_raises_without_partial_tree` | `"(;SZ[nineteen])"` | `parse_sgf` raises `ValueError` |
| `tests/sgf_engine/test_parser_errors.py` | `test_structurally_invalid_sgf_raises_without_partial_tree` | `"(;C[unterminated)"` | `parse_sgf` raises `ValueError` |
| `tests/sgf_engine/test_parser_errors.py` | `test_structurally_invalid_sgf_raises_without_partial_tree` | `"(;B[dd]) trailing"` | `parse_sgf` raises `ValueError` |
| `tests/sgf_engine/test_tree.py` | `test_move_rejects_invalid_data` | `Move("black", "dd")` | `Move` raises `ValueError` |
| `tests/sgf_engine/test_tree.py` | `test_move_rejects_invalid_data` | `Move("B", "DD")` | `Move` raises `ValueError` |
| `tests/sgf_engine/test_tree.py` | `test_move_rejects_invalid_data` | `Move("W", "tt")` | `Move` raises `ValueError` |

Coverage Gap:

- No parser test directly covers lowercase or mixed-case SGF property identifiers such as `(;b[dd])`.
- No parser test directly covers a property identifier with no value such as `(;B)`.
- No parser test directly covers an empty nested variation such as `(;B[dd]())`.
- No parser test directly covers broken variation structure after a valid prefix, such as `(;B[dd](;W[pp])`.
- No parser test directly covers a move property with multiple values such as `(;B[dd][pp])`.
- No parser test directly covers an incomplete trailing escape in a property value such as `(;C[abc\`.
- No parser test directly covers whether a failed parse mutates any persistent state, though reviewed code shows no persistent parser state.

These gaps are test coverage warnings only. Within the reviewed parser code, the corresponding paths appear to raise `ValueError` rather than return partial trees. Follow-up review of `sgf_engine.core.coord_utils` confirms direct coordinate/color validation evidence.

## Tree Coupling Findings

| File | Exact import/call/access pattern | Classification |
|---|---|---|
| `sgf_engine/parser/sgf_parser.py` | `from sgf_engine.core.tree import Move, SGFNode` | OK |
| `sgf_engine/parser/sgf_parser.py` | `move = Move(color=color, coord=coord)` | OK |
| `sgf_engine/parser/sgf_parser.py` | `return SGFNode(move=move, metadata=metadata)` | OK |
| `sgf_engine/core/tree.py` | `from sgf_engine.core.coord_utils import opponent_of, sgf_to_xy` | OK |
| `sgf_engine/core/tree.py` | `Move.__post_init__` calls `opponent_of(self.color)` and `sgf_to_xy(self.coord)` | OK |

No parser dependency on matcher, override loader, autoreply, engine, `db.py`, `app.py`, Flask, Redis, Socket.IO, routes, models, or production modules was found in the reviewed files.

## Determinism Findings

| File | Function or class | Exact behavior | Classification |
|---|---|---|---|
| `sgf_engine/parser/sgf_parser.py` | `parse_sgf` | Creates a fresh `_SGFParser` for each input string. | OK |
| `sgf_engine/parser/sgf_parser.py` | `_SGFParser` | Uses only `self.source`, `self.index`, local dictionaries/lists, and recursive descent over the input string. | OK |
| `sgf_engine/parser/sgf_parser.py` | `_build_node` | Property metadata order follows parsed dictionary insertion order from the input; no randomness, time, filesystem, environment, or cache is used. | OK |
| `sgf_engine/core/tree.py` | `Move.__post_init__` | Calls deterministic `opponent_of` and `sgf_to_xy`; follow-up review found both functions depend only on input arguments and literal/module constant coordinate bounds. | OK |

No randomness, time-based behavior, environment-based behavior, filesystem-based behavior, global state affecting parse output, or cache state affecting parse output was found in the reviewed parser file.

## Test Masking Findings

| Test file path | Test or fixture name | Mocked/skipped/hidden behavior | Appropriate? | Classification |
|---|---|---|---|---|
| `tests/sgf_engine/test_parser_errors.py` | `test_structurally_invalid_sgf_raises_without_partial_tree` | No monkeypatch, no skip, no hidden side-effect suppression. | Yes | OK |
| `tests/sgf_engine/test_tree.py` | `test_find_child_by_move_returns_first_match` | No monkeypatch, no skip, no hidden side-effect suppression. | Yes | OK |
| `tests/sgf_engine/test_tree.py` | `test_find_child_by_move_ignores_metadata_node_and_missing_coord` | No monkeypatch, no skip, no hidden side-effect suppression. | Yes | OK |
| `tests/sgf_engine/test_tree.py` | `test_move_rejects_invalid_data` | No monkeypatch, no skip, no hidden side-effect suppression. Covers invalid color and invalid coordinates at `Move` level, not direct `parse_sgf` invalid color. | Partly | Warning |

No test monkeypatches parser internals or explicitly hides parser side effects in the reviewed tests.

## Coordinate Utility Follow-up

`docs/testing/coord_utils_purity_report.md` reviewed `sgf_engine/core/coord_utils.py`, `sgf_engine/core/tree.py`, `tests/sgf_engine/test_coord_utils.py`, and `tests/sgf_engine/test_tree.py`.

Findings:

- Import inventory found only `from __future__ import annotations` in `coord_utils.py`, classified as standard library.
- Production dependency audit found no import or call to `app.py`, `db.py`, Flask, routes, models, Redis, Socket.IO, PostgreSQL helpers, application config, or production database helpers.
- Side-effect audit found no file I/O, DB access, network access, environment variable read, production logging, external/global state mutation, or write to files/cache/database/external services.
- Determinism audit found `sgf_to_xy`, `xy_to_sgf`, and `opponent_of` depend only on their input arguments plus literal/module constant bounds.
- Validation audit found code and tests cover uppercase SGF rejection, invalid SGF length rejection, letters outside `a-s`, coordinates outside `0-18`, and invalid opponent colors including `"black"`, `"white"`, `1`, and `0`.
- Tree impact audit found `Move.__post_init__` calls `opponent_of(self.color)` and `sgf_to_xy(self.coord)` only for validation and introduces no side effects.

The prior `Needs owner decision` classification for tree coupling through `coord_utils.py` is resolved. Parser malformed-SGF coverage gaps remain as warnings.

## Additional Files That May Require Owner-Approved Review

None.

## Final Classification

PASS WITH WARNINGS
