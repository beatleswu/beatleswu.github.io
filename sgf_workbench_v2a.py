"""SGF Workbench V2-A review-core primitives.

This module deliberately stops at human review.  It serializes the existing
canonical SGF parser tree for display, persists a version-scoped review
locator, and never writes canonical question content.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from sgf_admin_workbench import direct_record_hash
from sgf_engine.core.coord_utils import sgf_to_xy
from sgf_engine.parser.sgf_parser import parse_sgf


HUMAN_REVIEW_CLASSIFICATIONS = (
    "CORRECT",
    "WRONG_ROOT",
    "MISSING_ANSWER",
    "MISSING_VARIATION",
    "SPECIAL",
    "UNSURE",
)
HUMAN_REVIEW_STATES = ("CURRENT", "CONTENT_CHANGED", "UNREVIEWED")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_hash(record: Mapping[str, Any]) -> str:
    """Use the Direct Apply full-record hashing contract, not SGF-only bytes."""
    return direct_record_hash(dict(record))


# Explicit names used by review/test callers; both resolve to the existing
# Direct Apply full-record hash contract.
canonical_record_hash = record_hash


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _row_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)
    except (TypeError, ValueError):
        keys = getattr(row, "keys", lambda: [])()
        return {key: row[key] for key in keys}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def ensure_human_review_table(conn) -> None:
    """Install the local/isolated table; PostgreSQL is migration-governed."""
    if not _is_sqlite(conn):
        from migrations.sgf_human_review_v2a import SchemaMismatch, validate_schema

        status = validate_schema(conn)
        if status.get("missing"):
            raise SchemaMismatch("human review schema missing: " + ",".join(status["missing"]))
        return
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sgf_human_review_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reviewer_id BIGINT NOT NULL,
            record_index BIGINT NOT NULL,
            legacy_question_id TEXT NOT NULL,
            reviewed_record_sha256 TEXT NOT NULL,
            classification TEXT NOT NULL CHECK (classification IN
                ('CORRECT','WRONG_ROOT','MISSING_ANSWER','MISSING_VARIATION','SPECIAL','UNSURE')),
            reviewed_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(reviewer_id, record_index, legacy_question_id, reviewed_record_sha256)
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sgfh_current_locator "
        "ON sgf_human_review_state(reviewer_id, record_index, legacy_question_id, updated_at DESC)"
    )


def _validate_locator(*, reviewer_id: int, record_index: int,
                      legacy_question_id: Any, reviewed_record_sha256: str) -> tuple[int, int, str, str]:
    try:
        reviewer_id = int(reviewer_id)
        record_index = int(record_index)
    except (TypeError, ValueError) as exc:
        raise ValueError("review locator ids must be integers") from exc
    if reviewer_id <= 0 or record_index < 0:
        raise ValueError("review locator ids are out of range")
    if legacy_question_id in (None, ""):
        raise ValueError("legacy_question_id is required")
    value = str(legacy_question_id)
    digest = str(reviewed_record_sha256 or "").lower()
    if not _SHA256.fullmatch(digest):
        raise ValueError("reviewed_record_sha256 must be a SHA-256 hex digest")
    return reviewer_id, record_index, value, digest


def get_human_review_state(conn, *, reviewer_id: int, record_index: int,
                           legacy_question_id: Any, current_record_sha256: str) -> dict[str, Any]:
    """Resolve only the exact version-scoped locator; never rebind by id alone."""
    reviewer_id, record_index, legacy_id, current_hash = _validate_locator(
        reviewer_id=reviewer_id, record_index=record_index,
        legacy_question_id=legacy_question_id, reviewed_record_sha256=current_record_sha256,
    )
    ensure_human_review_table(conn)
    row = conn.execute(
        """SELECT * FROM sgf_human_review_state
           WHERE reviewer_id=? AND record_index=? AND legacy_question_id=?
             AND reviewed_record_sha256=?""",
        (reviewer_id, record_index, legacy_id, current_hash),
    ).fetchone()
    exact = _row_dict(row)
    if exact:
        exact["state"] = "CURRENT"
        exact["reviewed_record_sha256"] = exact.get("reviewed_record_sha256") or current_hash
        return exact
    previous = conn.execute(
        """SELECT * FROM sgf_human_review_state
           WHERE reviewer_id=? AND record_index=? AND legacy_question_id=?
           ORDER BY updated_at DESC, id DESC LIMIT 1""",
        (reviewer_id, record_index, legacy_id),
    ).fetchone()
    prior = _row_dict(previous)
    if prior:
        return {
            "state": "CONTENT_CHANGED",
            "classification": None,
            "previous_classification": prior.get("classification"),
            "previous_reviewed_record_sha256": prior.get("reviewed_record_sha256"),
            "record_index": record_index,
            "legacy_question_id": legacy_id,
        }
    return {
        "state": "UNREVIEWED",
        "classification": None,
        "record_index": record_index,
        "legacy_question_id": legacy_id,
    }


def save_human_review_state(conn, *, reviewer_id: int, record_index: int,
                            legacy_question_id: Any, reviewed_record_sha256: str,
                            classification: str, now: str | None = None) -> dict[str, Any]:
    """Persist one lazy human classification and append a bounded audit row."""
    reviewer_id, record_index, legacy_id, digest = _validate_locator(
        reviewer_id=reviewer_id, record_index=record_index,
        legacy_question_id=legacy_question_id, reviewed_record_sha256=reviewed_record_sha256,
    )
    classification = str(classification or "").upper()
    if classification not in HUMAN_REVIEW_CLASSIFICATIONS:
        raise ValueError("invalid human review classification")
    ensure_human_review_table(conn)
    timestamp = now or utc_now()
    conn.execute(
        """INSERT INTO sgf_human_review_state
           (reviewer_id, record_index, legacy_question_id, reviewed_record_sha256,
            classification, reviewed_at, updated_at)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(reviewer_id, record_index, legacy_question_id, reviewed_record_sha256)
           DO UPDATE SET classification=excluded.classification, updated_at=excluded.updated_at""",
        (reviewer_id, record_index, legacy_id, digest, classification, timestamp, timestamp),
    )
    # The seven-table audit is intentionally a separate lifecycle from the
    # legacy OPEN/STAGED/PUBLISHED review-item status dimension.
    try:
        from sgf_admin_workbench import ensure_sgf_workbench_tables

        ensure_sgf_workbench_tables(conn)
        conn.execute(
            """INSERT INTO sgf_workbench_audit
               (target_type, target_id, actor_id, action, detail, created_at)
               VALUES(?,?,?,?,?,?)""",
            ("human_review", None, reviewer_id, "CLASSIFICATION_SET",
             _json({"record_index": record_index, "legacy_question_id": legacy_id,
                    "reviewed_record_sha256": digest, "classification": classification}), timestamp),
        )
    except Exception:
        # Audit is required for a governed mutation.  Let the transaction
        # caller roll back rather than returning an apparently saved state.
        raise
    result = get_human_review_state(
        conn, reviewer_id=reviewer_id, record_index=record_index,
        legacy_question_id=legacy_id, current_record_sha256=digest,
    )
    result["idempotent_replay"] = result.get("updated_at") == timestamp
    return result


def serialize_sgf_tree(sgf: str) -> dict[str, Any]:
    """Serialize the existing SGFNode tree with deterministic path identities."""
    root = parse_sgf(sgf)
    root_props = root.metadata.get("properties") if isinstance(root.metadata, dict) else {}
    root_props = root_props if isinstance(root_props, dict) else {}
    try:
        board_size = int((root_props.get("SZ") or [root.metadata.get("size", 19)])[0])
    except (TypeError, ValueError, IndexError):
        board_size = 19
    board_size = max(2, min(board_size, 19))
    initial_stones: list[dict[str, Any]] = []
    setup_errors: list[str] = []
    for color, prop in (("B", "AB"), ("W", "AW")):
        for coord in root_props.get(prop, []) or []:
            try:
                x, y = sgf_to_xy(coord)
                if x >= board_size or y >= board_size:
                    raise ValueError("outside board")
                initial_stones.append({"color": color, "x": x, "y": y})
            except (TypeError, ValueError):
                setup_errors.append(f"invalid_setup:{prop}:{coord}")
    for coord in root_props.get("AE", []) or []:
        try:
            x, y = sgf_to_xy(coord)
            initial_stones.append({"color": "E", "x": x, "y": y})
        except (TypeError, ValueError):
            setup_errors.append(f"invalid_setup:AE:{coord}")
    nodes: list[dict[str, Any]] = [{"id": "0", "parent_id": None, "move": None, "children": []}]
    by_id: dict[str, dict[str, Any]] = {"0": nodes[0]}

    def visit(parent, parent_id: str) -> None:
        for position, child in enumerate(parent.children):
            node_id = f"{parent_id}.{position}"
            move = None
            if child.move is not None:
                if child.move.is_pass:
                    move = {"color": child.move.color, "pass": True, "x": None, "y": None}
                else:
                    try:
                        x, y = sgf_to_xy(child.move.coord or "")
                        move = {"color": child.move.color, "x": x, "y": y, "pass": False}
                    except (TypeError, ValueError):
                        move = {"color": child.move.color, "pass": False, "invalid": True}
            item = {"id": node_id, "parent_id": parent_id, "move": move, "children": []}
            by_id[node_id] = item
            nodes.append(item)
            by_id[parent_id]["children"].append(node_id)
            visit(child, node_id)

    visit(root, "0")
    side = root.metadata.get("player_to_move") if isinstance(root.metadata, dict) else None
    if side not in ("B", "W"):
        first = next((node for node in nodes[1:] if node.get("move") and node["move"].get("color")), None)
        side = first["move"]["color"] if first else "B"
    return {
        "root_id": "0",
        "nodes": nodes,
        "board_size": board_size,
        "initial_stones": initial_stones,
        "side_to_play": side,
        "errors": setup_errors,
    }


serialize_answer_tree = serialize_sgf_tree


def _group_liberties(board: dict[tuple[int, int], str], start: tuple[int, int], size: int = 19) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    color = board[start]
    stones: set[tuple[int, int]] = set()
    liberties: set[tuple[int, int]] = set()
    stack = [start]
    while stack:
        point = stack.pop()
        if point in stones:
            continue
        stones.add(point)
        x, y = point
        for neighbour in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if not (0 <= neighbour[0] < size and 0 <= neighbour[1] < size):
                continue
            if neighbour not in board:
                liberties.add(neighbour)
            elif board[neighbour] == color and neighbour not in stones:
                stack.append(neighbour)
    return stones, liberties


def replay_sgf_tree(tree: Mapping[str, Any], node_id: str = "0") -> dict[str, Any]:
    """Replay a selected path for display; failures are explicit and non-mutating."""
    nodes = {str(node["id"]): node for node in tree.get("nodes", []) if isinstance(node, Mapping)}
    if "0" not in nodes or str(node_id) not in nodes:
        return {"status": "FAIL", "error": "node_not_found", "node_id": str(node_id)}
    selected = str(node_id)
    path: list[str] = []
    while selected != "0":
        path.append(selected)
        parent = nodes[selected].get("parent_id")
        if parent is None or str(parent) not in nodes:
            return {"status": "FAIL", "error": "broken_parent_link", "node_id": str(node_id)}
        selected = str(parent)
    path.reverse()
    board: dict[tuple[int, int], str] = {}
    size = int(tree.get("board_size") or 19)
    for stone in tree.get("initial_stones", []) or []:
        try:
            x, y, color = int(stone["x"]), int(stone["y"]), str(stone["color"])
        except (KeyError, TypeError, ValueError):
            return {"status": "FAIL", "error": "invalid_setup", "node_id": str(node_id)}
        if color == "E":
            board.pop((x, y), None)
        elif color in ("B", "W") and 0 <= x < size and 0 <= y < size:
            board[(x, y)] = color
        else:
            return {"status": "FAIL", "error": "invalid_setup", "node_id": str(node_id)}
    replay_errors: list[str] = []
    for current_id in path:
        move = nodes[current_id].get("move") or {}
        if move.get("pass"):
            continue
        if move.get("invalid") or move.get("color") not in ("B", "W"):
            replay_errors.append(f"invalid_move:{current_id}")
            continue
        x, y = move.get("x"), move.get("y")
        if not isinstance(x, int) or not isinstance(y, int) or not (0 <= x < size and 0 <= y < size):
            replay_errors.append(f"invalid_coordinate:{current_id}")
            continue
        if (x, y) in board:
            replay_errors.append(f"occupied_point:{current_id}")
            continue
        board[(x, y)] = move["color"]
        opponent = "W" if move["color"] == "B" else "B"
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if board.get((nx, ny)) != opponent:
                continue
            stones, liberties = _group_liberties(board, (nx, ny), size)
            if not liberties:
                for point in stones:
                    board.pop(point, None)
        stones, liberties = _group_liberties(board, (x, y), size)
        if not liberties:
            replay_errors.append(f"suicide_or_illegal:{current_id}")
            for point in stones:
                board.pop(point, None)
    return {
        "status": "FAIL" if replay_errors or tree.get("errors") else "PASS",
        "error": replay_errors[0] if replay_errors else (tree.get("errors") or [None])[0],
        "node_id": str(node_id),
        "path": ["0", *path],
        "stones": [{"x": x, "y": y, "color": color} for (x, y), color in sorted(board.items())],
        "side_to_play": nodes[str(node_id)].get("move", {}).get("color") if nodes[str(node_id)].get("move") else tree.get("side_to_play"),
    }


replay_answer_tree = replay_sgf_tree


def compute_local_viewport(tree: Mapping[str, Any], record: Mapping[str, Any] | None = None,
                           *, full_board: bool = False, margin: int = 2) -> dict[str, Any]:
    size = int(tree.get("board_size") or 19)
    whole = bool(full_board or (record or {}).get("whole_board") or
                (record or {}).get("discipline") == "whole_board" or
                (record or {}).get("encounter_type") in ("chapter_boss", "book_boss") or
                "whole_board" in ((record or {}).get("tags") or []))
    points: list[tuple[int, int]] = []
    for stone in tree.get("initial_stones", []) or []:
        if stone.get("color") in ("B", "W"):
            points.append((int(stone["x"]), int(stone["y"])))
    for node in tree.get("nodes", []) or []:
        move = node.get("move") or {}
        if not move.get("pass") and isinstance(move.get("x"), int) and isinstance(move.get("y"), int):
            points.append((move["x"], move["y"]))
    if whole or not points:
        return {"mode": "FULL", "x0": 0, "y0": 0, "x1": size - 1, "y1": size - 1,
                "touch_top": True, "touch_bottom": True, "touch_left": True, "touch_right": True}
    min_x, max_x = min(p[0] for p in points), max(p[0] for p in points)
    min_y, max_y = min(p[1] for p in points), max(p[1] for p in points)
    x0, x1 = max(0, min_x - margin), min(size - 1, max_x + margin)
    y0, y1 = max(0, min_y - margin), min(size - 1, max_y + margin)
    return {"mode": "LOCAL", "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "touch_top": y0 == 0, "touch_bottom": y1 == size - 1,
            "touch_left": x0 == 0, "touch_right": x1 == size - 1}


def build_question_context(record: Mapping[str, Any], *, record_index: int,
                           reviewer_id: int, review_state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    legacy_id = record.get("id", record.get("question_id"))
    digest = record_hash(record)
    content = record.get("content") or record.get("sgf") or ""
    try:
        tree = serialize_sgf_tree(str(content))
        playback = replay_sgf_tree(tree)
        viewport = compute_local_viewport(tree, record)
    except (TypeError, ValueError, KeyError) as error:
        tree = {"root_id": "0", "nodes": [], "board_size": 19, "initial_stones": [], "errors": [str(error)]}
        playback = {"status": "FAIL", "error": str(error), "node_id": "0", "path": [], "stones": []}
        viewport = compute_local_viewport(tree, record)
    source_number = next((record.get(key) for key in
                          ("source_question_number", "question_number", "problem_number", "number")
                          if record.get(key) not in (None, "")), None)
    return {
        "record_index": int(record_index),
        "legacy_question_id": legacy_id,
        "reviewed_record_sha256": digest,
        "source": record.get("source") or record.get("source_path"),
        "source_question_number": source_number,
        "side_to_play": tree.get("side_to_play"),
        "tree": tree,
        "playback": playback,
        "viewport": viewport,
        "classification": (review_state or {}).get("classification"),
        "review_state": (review_state or {}).get("state", "UNREVIEWED"),
        "reviewed_at": (review_state or {}).get("updated_at") or (review_state or {}).get("reviewed_at"),
        "enabled": bool(record.get("enabled", True)),
        "metadata": {
            "discipline": record.get("discipline"),
            "tags": record.get("tags") if isinstance(record.get("tags"), list) else [],
        },
    }


__all__ = [
    "HUMAN_REVIEW_CLASSIFICATIONS", "HUMAN_REVIEW_STATES", "record_hash", "canonical_record_hash",
    "ensure_human_review_table", "get_human_review_state", "save_human_review_state",
    "serialize_sgf_tree", "serialize_answer_tree", "replay_sgf_tree", "replay_answer_tree",
    "compute_local_viewport", "build_question_context",
]
