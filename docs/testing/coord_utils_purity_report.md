# Coord Utils Purity Follow-up Review

## Scope

Verification-only follow-up review of whether `sgf_engine/core/coord_utils.py` is pure, deterministic, and safe for parser-side `Move` validation.

No production code was modified. Review was limited to the files explicitly allowed by the mission.

## Files Reviewed

- `sgf_engine/core/coord_utils.py`
- `sgf_engine/core/tree.py`
- `tests/sgf_engine/test_coord_utils.py`
- `tests/sgf_engine/test_tree.py`
- `docs/testing/parser_purity_report.md`
- `docs/testing/modification_log.md`

## Import Inventory

| File | Exact import statement | Classification |
|---|---|---|
| `sgf_engine/core/coord_utils.py` | `from __future__ import annotations` | standard library |

No `sgf_engine` internal import, production application dependency import, or other third-party import appears in `sgf_engine/core/coord_utils.py`.

## Production Dependency Findings

| File | Function name | Exact import/call/access pattern | Classification |
|---|---|---|---|
| `sgf_engine/core/coord_utils.py` | module scope | No import or call to `app.py`, `db.py`, Flask, `routes/`, `models/`, Redis, Socket.IO, PostgreSQL helpers, application config, or production database helpers appears in the file. | OK |
| `sgf_engine/core/coord_utils.py` | `sgf_to_xy` | Uses only `isinstance`, `len`, `any`, string comparisons, `ord`, `_MIN_COORD`, and the input argument `sgf`. | OK |
| `sgf_engine/core/coord_utils.py` | `xy_to_sgf` | Uses only exact `int` type checks, numeric range checks, `chr`, `_MIN_COORD`, and the input arguments `x` and `y`. | OK |
| `sgf_engine/core/coord_utils.py` | `opponent_of` | Uses only equality checks against literal SGF colors `"B"` and `"W"`. | OK |

## Side-Effect Findings

| File | Function name | Exact call/access pattern | Classification |
|---|---|---|---|
| `sgf_engine/core/coord_utils.py` | module scope | Defines immutable integer constants `_MIN_COORD = ord("a")` and `_MAX_COORD = ord("s")`; `_MAX_COORD` is not read by the functions. No external/global state is mutated. | OK |
| `sgf_engine/core/coord_utils.py` | `sgf_to_xy` | Raises `ValueError` for invalid input or returns a tuple derived from input characters; no file I/O, DB access, network access, environment read, production logging, cache write, database write, or external service write appears. | OK |
| `sgf_engine/core/coord_utils.py` | `xy_to_sgf` | Raises `ValueError` for invalid input or returns a string derived from input integers; no file I/O, DB access, network access, environment read, production logging, cache write, database write, or external service write appears. | OK |
| `sgf_engine/core/coord_utils.py` | `opponent_of` | Raises `ValueError` for invalid input or returns the opposite color literal; no file I/O, DB access, network access, environment read, production logging, cache write, database write, or external service write appears. | OK |

## Determinism Findings

| File | Function name | Exact behavior | Classification |
|---|---|---|---|
| `sgf_engine/core/coord_utils.py` | `sgf_to_xy` | Depends only on `sgf`, literal bounds `"a"` and `"s"`, and `_MIN_COORD`. It has no randomness, time behavior, filesystem behavior, environment behavior, cache behavior, or mutable global state dependency. | OK |
| `sgf_engine/core/coord_utils.py` | `xy_to_sgf` | Depends only on `x`, `y`, numeric range `0-18`, and `_MIN_COORD`. It has no randomness, time behavior, filesystem behavior, environment behavior, cache behavior, or mutable global state dependency. | OK |
| `sgf_engine/core/coord_utils.py` | `opponent_of` | Depends only on `color` and literal values `"B"` and `"W"`. It has no randomness, time behavior, filesystem behavior, environment behavior, cache behavior, or mutable global state dependency. | OK |

## Validation Behavior Findings

| File | Function name | Validation rule | Evidence from code and/or test | Classification |
|---|---|---|---|---|
| `sgf_engine/core/coord_utils.py` | `sgf_to_xy` | Rejects uppercase coordinates. | Code rejects any character where `char < "a" or char > "s"`; `tests/sgf_engine/test_coord_utils.py::test_invalid_sgf_coordinate_raises` covers `"QD"`. | OK |
| `sgf_engine/core/coord_utils.py` | `sgf_to_xy` | Rejects length not equal to 2. | Code checks `len(sgf) != 2`; `tests/sgf_engine/test_coord_utils.py::test_invalid_sgf_coordinate_raises` covers `"a"`, `"aaa"`, and `""`. | OK |
| `sgf_engine/core/coord_utils.py` | `sgf_to_xy` | Rejects letters outside `a-s`. | Code rejects any character outside `"a"` through `"s"`; `tests/sgf_engine/test_coord_utils.py::test_invalid_sgf_coordinate_raises` covers `"az"`, and `tests/sgf_engine/test_tree.py::test_move_rejects_invalid_data` covers `Move("W", "tt")`. | OK |
| `sgf_engine/core/coord_utils.py` | `sgf_to_xy` | Rejects non-string input. | Code checks `not isinstance(sgf, str)` before `len`; `tests/sgf_engine/test_coord_utils.py::test_invalid_sgf_coordinate_raises` covers `1` and `None`. | OK |
| `sgf_engine/core/coord_utils.py` | `xy_to_sgf` | Rejects coordinates outside `0-18`. | Code checks `not (0 <= x <= 18 and 0 <= y <= 18)`; `tests/sgf_engine/test_coord_utils.py::test_invalid_xy_raises` covers `(-1, 0)`, `(19, 0)`, `(0, -1)`, and `(0, 19)`. | OK |
| `sgf_engine/core/coord_utils.py` | `xy_to_sgf` | Rejects non-exact integers, including bool. | Code checks `type(x) is not int or type(y) is not int`; `tests/sgf_engine/test_coord_utils.py::test_invalid_xy_raises` covers `(True, 0)`. | OK |
| `sgf_engine/core/coord_utils.py` | `opponent_of` | Accepts only `"B"` or `"W"`. | Code returns only for `color == "B"` and `color == "W"`, then raises `ValueError`; `tests/sgf_engine/test_coord_utils.py::test_opponent` covers both valid values. | OK |
| `sgf_engine/core/coord_utils.py` | `opponent_of` | Rejects `"black"`, `"white"`, `1`, `0`, and other invalid input. | Code raises `ValueError` after the two exact literal matches; `tests/sgf_engine/test_coord_utils.py::test_invalid_opponent_color_raises` covers `"black"`, `"white"`, `1`, `0`, and `None`. | OK |

## Tree Validation Impact

| File | Function name | Exact call/access pattern | Classification |
|---|---|---|---|
| `sgf_engine/core/tree.py` | `Move.__post_init__` | Calls `opponent_of(self.color)` and discards the result, using it only to raise `ValueError` for invalid colors. | OK |
| `sgf_engine/core/tree.py` | `Move.__post_init__` | Calls `sgf_to_xy(self.coord)` and discards the result, using it only to raise `ValueError` for invalid coordinates. | OK |
| `sgf_engine/core/tree.py` | `Move` | `@dataclass(frozen=True, slots=True)` prevents post-init field mutation by this class; `__post_init__` contains no file I/O, DB access, network access, environment read, logging, or external/global write. | OK |

## Test Coverage Findings

| Test file path | Test name | Covered or missing behavior | Classification |
|---|---|---|---|
| `tests/sgf_engine/test_coord_utils.py` | `test_sgf_to_xy_required_coordinates` | Covers valid lowercase SGF coordinate conversion at corners and representative interior points: `"aa"`, `"sa"`, `"as"`, `"ss"`, `"dd"`, and `"pp"`. | OK |
| `tests/sgf_engine/test_coord_utils.py` | `test_coordinate_round_trip` | Covers `xy_to_sgf(*sgf_to_xy("qd")) == "qd"`. | OK |
| `tests/sgf_engine/test_coord_utils.py` | `test_opponent` | Covers valid `"B" -> "W"` and `"W" -> "B"`. | OK |
| `tests/sgf_engine/test_coord_utils.py` | `test_invalid_sgf_coordinate_raises` | Covers uppercase, length too short, length too long, outside `a-s`, empty string, integer input, and `None`. | OK |
| `tests/sgf_engine/test_coord_utils.py` | `test_invalid_xy_raises` | Covers negative x, x greater than 18, negative y, y greater than 18, and bool rejection for x. | OK |
| `tests/sgf_engine/test_coord_utils.py` | `test_invalid_xy_raises` | Missing direct coverage for non-int `y`, bool `y`, and non-int values other than bool. Code evidence still shows both `x` and `y` use the same exact `int` type check. | Warning |
| `tests/sgf_engine/test_coord_utils.py` | `test_invalid_opponent_color_raises` | Covers `"black"`, `"white"`, `1`, `0`, and `None`. | OK |
| `tests/sgf_engine/test_tree.py` | `test_move_rejects_invalid_data` | Covers `Move` rejecting invalid color, uppercase coordinate, and coordinate outside `a-s`. | OK |

## Additional Files That May Require Owner-Approved Review

None.

## Final Classification

PASS WITH WARNINGS
