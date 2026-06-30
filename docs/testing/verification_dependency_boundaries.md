# Independent Dependency Boundary Verification

## Scope

Verification-only review of dependency boundaries for:

- `sgf_engine/`
- `tests/sgf_engine/`

No production logic was changed. Files outside the allowed read scope were not opened. The only written file is this report.

## Files Reviewed

### `sgf_engine/`

- `sgf_engine/__init__.py`
- `sgf_engine/core/__init__.py`
- `sgf_engine/core/autoreply.py`
- `sgf_engine/core/coord_utils.py`
- `sgf_engine/core/matcher.py`
- `sgf_engine/core/tree.py`
- `sgf_engine/engine/__init__.py`
- `sgf_engine/engine/engine.py`
- `sgf_engine/override/__init__.py`
- `sgf_engine/override/override_loader.py`
- `sgf_engine/parser/__init__.py`
- `sgf_engine/parser/sgf_parser.py`

### `tests/sgf_engine/`

- `tests/sgf_engine/test_autoreply.py`
- `tests/sgf_engine/test_coord_utils.py`
- `tests/sgf_engine/test_engine.py`
- `tests/sgf_engine/test_integration_fixtures.py`
- `tests/sgf_engine/test_matcher.py`
- `tests/sgf_engine/test_override_loader.py`
- `tests/sgf_engine/test_parser_errors.py`
- `tests/sgf_engine/test_tree.py`

## Import Inventory

### `sgf_engine/__init__.py`

| Import statement | Classification |
|---|---|
| `from sgf_engine.engine.engine import EngineResult, apply_move` | sgf_engine internal |

### `sgf_engine/core/__init__.py`

No import statements.

### `sgf_engine/core/autoreply.py`

| Import statement | Classification |
|---|---|
| `from __future__ import annotations` | standard library |
| `from sgf_engine.core.coord_utils import opponent_of` | sgf_engine internal |
| `from sgf_engine.core.tree import Move, SGFNode` | sgf_engine internal |

### `sgf_engine/core/coord_utils.py`

| Import statement | Classification |
|---|---|
| `from __future__ import annotations` | standard library |

### `sgf_engine/core/matcher.py`

| Import statement | Classification |
|---|---|
| `from __future__ import annotations` | standard library |
| `from enum import Enum` | standard library |
| `from sgf_engine.core.coord_utils import sgf_to_xy` | sgf_engine internal |
| `from sgf_engine.core.tree import SGFNode, find_child_by_move` | sgf_engine internal |

### `sgf_engine/core/tree.py`

| Import statement | Classification |
|---|---|
| `from __future__ import annotations` | standard library |
| `from dataclasses import dataclass, field` | standard library |
| `from sgf_engine.core.coord_utils import opponent_of, sgf_to_xy` | sgf_engine internal |

### `sgf_engine/engine/__init__.py`

No import statements.

### `sgf_engine/engine/engine.py`

| Import statement | Classification |
|---|---|
| `from __future__ import annotations` | standard library |
| `from dataclasses import dataclass` | standard library |
| `from sgf_engine.core import autoreply, matcher, tree` | sgf_engine internal |
| `from sgf_engine.core.tree import Move, SGFNode` | sgf_engine internal |
| `from sgf_engine.override import override_loader` | sgf_engine internal |
| `from db import get_db` inside `log_off_tree` | production application dependency |

### `sgf_engine/override/__init__.py`

No import statements.

### `sgf_engine/override/override_loader.py`

| Import statement | Classification |
|---|---|
| `from __future__ import annotations` | standard library |
| `import copy` | standard library |
| `import json` | standard library |
| `from pathlib import Path` | standard library |

### `sgf_engine/parser/__init__.py`

No import statements.

### `sgf_engine/parser/sgf_parser.py`

| Import statement | Classification |
|---|---|
| `from __future__ import annotations` | standard library |
| `from dataclasses import dataclass` | standard library |
| `from sgf_engine.core.tree import Move, SGFNode` | sgf_engine internal |

## Production Dependency Findings

| Classification | File path | Function or class | Exact import/call/access pattern | Evidence |
|---|---|---|---|---|
| Needs owner decision | `sgf_engine/engine/engine.py` | `log_off_tree` | Lazy import: `from db import get_db`; DB access: `with get_db() as connection:`; DB writes: `connection.execute(...)`, `connection.commit()` | This is a direct dependency from `sgf_engine` into production application DB helper code. It is lazy, but still creates a runtime dependency on `db.py` when OFF_TREE handling executes. The function docstring says database persistence is intentional, so owner decision is needed on whether this belongs inside `sgf_engine`. |
| OK | `sgf_engine/engine/engine.py` | `apply_move` | Calls `log_off_tree(source, move_coord, player_color)` in the OFF_TREE branch | The production DB dependency is indirect through `log_off_tree`; no direct `db`, Flask, Socket.IO, Redis, PostgreSQL, route, model, config, or app access was found in `apply_move`. |
| OK | All other reviewed `sgf_engine/` modules | N/A | No imports or calls to `app.py`, `db.py`, `routes/`, models, Flask, Socket.IO, Redis, PostgreSQL helpers, application config, or production database helpers were found. | Import inventory above lists only standard library and `sgf_engine` internal imports outside `engine.py`. |

## Orchestration Boundary Findings

SGF Engine rule checked: only `sgf_engine/engine/engine.py` may orchestrate matcher + tree + override_loader + autoreply together.

| Classification | File path | Exact imports or calls | Actual orchestration or harmless usage |
|---|---|---|---|
| OK | `sgf_engine/engine/engine.py` | Imports `from sgf_engine.core import autoreply, matcher, tree`; imports `from sgf_engine.override import override_loader`; calls `override_loader.load_override`, `matcher.match_move`, `tree.find_child_by_move`, `override_loader.canonical_coord_for`, `autoreply.get_auto_reply` | Actual orchestration, allowed by rule. |
| OK | `sgf_engine/core/matcher.py` | Imports `from sgf_engine.core.tree import SGFNode, find_child_by_move`; calls `find_child_by_move(...)` | Uses only tree helper plus coordinate validation. Does not import or call more than one of matcher/tree/override_loader/autoreply. |
| OK | `sgf_engine/core/autoreply.py` | Imports `from sgf_engine.core.tree import Move, SGFNode` | Uses tree data types only. Does not import or call matcher or override_loader. |
| OK | `sgf_engine/parser/sgf_parser.py` | Imports `from sgf_engine.core.tree import Move, SGFNode` | Parser constructs tree nodes. Does not import or call matcher, override_loader, or autoreply. |
| OK | `sgf_engine/__init__.py` | Imports `EngineResult, apply_move` from `sgf_engine.engine.engine` | Package export only; no matcher/tree/override_loader/autoreply orchestration found. |
| OK | `tests/sgf_engine/test_engine.py` | Imports `from sgf_engine.engine import engine`; monkeypatches `engine.override_loader.load_override`; monkeypatches `engine.log_off_tree`; calls `engine.apply_move` | Test usage of the orchestration module. This is harmless test/helper usage, not production orchestration outside `engine.py`. |

## engine.py Child Access Findings

Expected rule checked: `sgf_engine/engine/engine.py` should use tree helper functions and should not directly traverse `SGFNode.children`.

| Classification | File path | Function name | Exact access pattern | Evidence |
|---|---|---|---|---|
| OK | `sgf_engine/engine/engine.py` | `apply_move` | Uses `tree.find_child_by_move(current_node, move_coord)`, `tree.find_child_by_move(current_node, canonical_coord)`, and `tree.find_child_by_move(current_node, reply.coord)` | No `.children`, `SGFNode.children`, `current_node.children`, or `node.children` access was found in `engine.py`. |
| OK | `sgf_engine/engine/engine.py` | `log_off_tree` | No child access | No `.children` access found. |

## Off-Tree Logging Findings

| Classification | File path | Function name | Exact import/call/access pattern | Whether unit tests mock or hide this dependency | Evidence |
|---|---|---|---|---|---|
| Needs owner decision | `sgf_engine/engine/engine.py` | `log_off_tree` | `from db import get_db`; `with get_db() as connection:`; `connection.execute("CREATE TABLE IF NOT EXISTS puzzle_unmatched_moves ...")`; `connection.execute("INSERT INTO puzzle_unmatched_moves...")`; `connection.commit()` | Yes. `tests/sgf_engine/test_engine.py::test_off_tree_logs_and_returns_without_validity_judgment` monkeypatches `engine.log_off_tree`, so the lazy `db` import and DB writes do not execute in that unit test. | OFF_TREE handling touches production DB helper code through `db.get_db`. This may be intentional persistence behavior, but it is a production dependency inside `sgf_engine`. |
| OK | `sgf_engine/engine/engine.py` | `apply_move` | OFF_TREE branch calls `log_off_tree(source, move_coord, player_color)` before returning `EngineResult(status="off_tree", ...)` | The unit test replaces `log_off_tree` with a lambda that records arguments. | The branch is explicit and test-covered for call shape, but the test does not exercise real DB integration. |

## Test Masking Findings

| Classification | Test file path | Test or fixture name | Mocked/hidden dependency | Whether the mock is appropriate for unit isolation |
|---|---|---|---|---|
| Warning | `tests/sgf_engine/test_engine.py` | `test_off_tree_logs_and_returns_without_validity_judgment` | `monkeypatch.setattr(engine, "log_off_tree", lambda source, move, color: calls.append(...))` hides `log_off_tree`'s lazy `from db import get_db` production dependency and real DB writes. | Appropriate for pure unit isolation of `apply_move` return behavior, but it masks the production DB boundary and should not be treated as evidence that OFF_TREE logging is dependency-free. |
| OK | `tests/sgf_engine/test_engine.py` | `test_apply_move_branch_then_auto_reply_then_result`, `test_apply_move_equivalent_resolves_canonical_branch`, `test_equivalent_missing_from_tree_raises_specific_error`, `test_same_color_single_child_is_not_auto_replied`, `test_identical_inputs_produce_identical_result_values` | `monkeypatch.setattr(engine.override_loader, "load_override", ...)` hides real override file loading. | Appropriate for unit isolation; this masks file I/O, not production application dependency. |
| OK | `tests/sgf_engine/test_override_loader.py` | `test_load_override_normalizes_source_and_returns_copy`, `test_missing_source_returns_none`, `test_malformed_json_raises`, `test_ambiguous_equivalent_raises` | `monkeypatch.setattr(override_loader, "OVERRIDES_FILE", path)` redirects override JSON path to `tmp_path`. | Appropriate for unit isolation of override parsing and validation; no production application dependency is hidden. |
| OK | `tests/sgf_engine/test_integration_fixtures.py` | `@pytest.mark.skipif(len(GOLD_FIXTURES) < 10, ...)` | Skips fixture integration test when fewer than 10 gold SGFs exist under `sgf_engine/data/fixtures`. | This can hide missing fixture coverage, but it does not hide a production application dependency from `sgf_engine`. |

## Additional Files That May Require Owner-Approved Review

- `db.py` - referenced by `sgf_engine/engine/engine.py::log_off_tree` via `from db import get_db`; not opened due to read-scope restriction.
- `puzzle_variation_overrides.json` - referenced by `sgf_engine/override/override_loader.py::OVERRIDES_FILE`; not opened because the allowed read scope was limited to `sgf_engine/` and `tests/sgf_engine/`.

## Final Classification

NEEDS OWNER DECISION
