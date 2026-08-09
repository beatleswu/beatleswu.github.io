"""Deterministic, read-only SGF answer repair-batch planner.

The planner consumes an immutable Owner proposal snapshot, the exact historical
questions snapshot the Owner reviewed, and a minimal read-only snapshot of the
current Production target records. It only rewrites in-memory/isolated copies.
Canonical SGFs, questions.json, accepted moves, Production state, and verdicts
are never written by this module.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sgf_engine.core.coord_utils import sgf_to_xy, xy_to_sgf
from sgf_engine.core.matcher import BRANCH, OFF_TREE, match_move
from sgf_engine.parser.sgf_parser import parse_sgf


SCHEMA_VERSION = "1.1"
AUTHORITY = "SGF_ANSWER_REPAIR_BATCH_001_DRY_RUN"
OUTPUT_CLASSIFICATION = "OWNER_REPAIR_PLAN_DRY_RUN_ONLY"

AUTO_TYPES = {
    "REPLACE_PRIMARY_ANSWER",
    "ADD_EQUIVALENT_SOLUTION",
    "REJECT_HISTORICAL_PRECOMPUTED_FALLBACK",
}
MANUAL_TYPES = {
    "SET_SIDE_TO_MOVE",
    "SOURCE_POSITION_INCLUDES_ANSWER",
    "NEEDS_SOURCE_RECONSTRUCTION",
}
KNOWN_TYPES = AUTO_TYPES | MANUAL_TYPES
REPAIR_CLASS_BY_PROPOSAL_TYPE = {
    "REPLACE_PRIMARY_ANSWER": "REPLACE_ANSWER_SET",
    "ADD_EQUIVALENT_SOLUTION": "ADD_EQUIVALENT_SOLUTION",
    "REJECT_HISTORICAL_PRECOMPUTED_FALLBACK": (
        "REJECT_HISTORICAL_PRECOMPUTED_FALLBACK"
    ),
    "SET_SIDE_TO_MOVE": "SIDE_TO_MOVE_CORRECTION",
    "SOURCE_POSITION_INCLUDES_ANSWER": (
        "SOURCE_CONVERSION_OR_SIDE_TO_MOVE_ERROR"
    ),
    "NEEDS_SOURCE_RECONSTRUCTION": (
        "SOURCE_CONVERSION_OR_SIDE_TO_MOVE_ERROR"
    ),
}

CLASS_FULLY = "FULLY_APPLYABLE_END_TO_END"
CLASS_FALLBACK_CONFLICT = "NATIVE_REPAIR_VALID_BUT_FALLBACK_CONFLICT"
CLASS_MANUAL = "MANUAL_RECONSTRUCTION_REQUIRED"
CLASS_STALE = "STALE_OR_CONFLICTED"
CLASS_UNRESOLVED = "UNRESOLVED_SOURCE"
CLASS_NO_OP = "NO_OP"

_MAX_PROPOSAL_BYTES = 8 * 1024 * 1024
_MAX_TARGET_BYTES = 32 * 1024 * 1024
_MAX_QUESTIONS_BYTES = 128 * 1024 * 1024
_GTP_COLUMNS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _read_json(path: Path, *, maximum_bytes: int) -> tuple[Any, bytes]:
    raw = path.read_bytes()
    if len(raw) > maximum_bytes:
        raise ValueError(f"{path} exceeds the read-only input bound")
    try:
        return json.loads(raw.decode("utf-8")), raw
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{path} is not valid UTF-8 JSON") from error


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _move_key(move: Mapping[str, Any]) -> tuple[int, int]:
    x, y = move.get("x"), move.get("y")
    if (
        not isinstance(x, int)
        or isinstance(x, bool)
        or not isinstance(y, int)
        or isinstance(y, bool)
    ):
        raise ValueError("move coordinates must be integers")
    return x, y


def _ordered_unique_points(moves: Iterable[Mapping[str, Any]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for move in moves:
        point = _move_key(move)
        if point not in seen:
            seen.add(point)
            result.append(point)
    return result


def _point_label(point: tuple[int, int], board_size: int) -> str:
    x, y = point
    if not (0 <= x < board_size and 0 <= y < board_size):
        return f"({x},{y})"
    return f"{_GTP_COLUMNS[x]}{board_size - y}"


def _gtp_to_xy(value: Any, board_size: int) -> tuple[int, int] | None:
    text = str(value or "").strip().upper()
    if len(text) < 2 or text[0] not in _GTP_COLUMNS[:board_size]:
        return None
    try:
        row = int(text[1:])
    except ValueError:
        return None
    if not (1 <= row <= board_size):
        return None
    return _GTP_COLUMNS.index(text[0]), board_size - row


def _sorted_points(points: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    return sorted(set(points), key=lambda point: (point[0], point[1]))


def _point_labels(
    points: Iterable[tuple[int, int]], board_size: int
) -> list[str]:
    return [_point_label(point, board_size) for point in _sorted_points(points)]


def _effective_verdict_layers(
    *,
    native_points: Iterable[tuple[int, int]],
    accepted_points: Iterable[tuple[int, int]],
    fallback_point: tuple[int, int] | None,
    board_size: int,
) -> dict[str, Any]:
    """Model the current first-move verdict surfaces without changing them.

    Rating Test calls ``_rt_server_verify``. Although that verifier contains
    an accepted-moves check, ``_build_rt_pool`` currently does not project
    accepted moves into its pool records, so its effective V1 inputs are the
    legacy SGF replay tree plus the stored precomputed fallback. Main practice
    and Map Battle use accepted moves plus the native tree. Daily Challenge is
    native-tree-only; Friend Challenge records the main client's verdict.
    """

    native = set(native_points)
    accepted = set(accepted_points)
    fallback = {fallback_point} if fallback_point is not None else set()
    layers = {
        "main_practice_client": native | accepted,
        "daily_challenge_client": native,
        "friend_challenge_client_then_server_trust": native | accepted,
        "map_battle_server": native | accepted,
        "rating_test_server": native | fallback,
    }
    return {
        "accepted_first_moves_by_surface": {
            name: _point_labels(points, board_size)
            for name, points in layers.items()
        },
        "final_effective_player_verdict": _point_labels(
            set().union(*layers.values()), board_size
        ),
        "rating_test_accepted_moves_projection": "OMITTED_BY_CURRENT_POOL_BUILD",
        "stored_precomputed_fallback_used_by": ["rating_test_server"]
        if fallback
        else [],
    }


@dataclass(frozen=True)
class RawNode:
    raw: str
    properties: tuple[tuple[str, tuple[str, ...]], ...]

    def values(self, name: str) -> tuple[str, ...]:
        wanted = name.upper()
        values: list[str] = []
        for identifier, current in self.properties:
            canonical = "".join(c for c in identifier if "A" <= c <= "Z")
            if canonical == wanted:
                values.extend(current)
        return tuple(values)

    def move(self) -> tuple[str, str] | None:
        found: list[tuple[str, str]] = []
        for color in ("B", "W"):
            values = self.values(color)
            if values:
                if len(values) != 1:
                    raise ValueError(f"{color} move property must have one value")
                found.append((color, values[0]))
        if len(found) > 1:
            raise ValueError("node contains both B and W moves")
        return found[0] if found else None


@dataclass(frozen=True)
class RawTree:
    sequence: tuple[RawNode, ...]
    variations: tuple["RawTree", ...]


class _LosslessSgfParser:
    def __init__(self, source: str):
        self.source = source
        self.index = 0

    def parse(self) -> RawTree:
        self._skip_space()
        tree = self._tree()
        self._skip_space()
        if self.index != len(self.source):
            raise ValueError(f"unexpected SGF content at offset {self.index}")
        return tree

    def _tree(self) -> RawTree:
        self._consume("(")
        self._skip_space()
        nodes: list[RawNode] = []
        while self._peek() == ";":
            nodes.append(self._node())
            self._skip_space()
        if not nodes:
            raise ValueError("SGF tree has no nodes")
        variations: list[RawTree] = []
        while self._peek() == "(":
            variations.append(self._tree())
            self._skip_space()
        self._consume(")")
        return RawTree(tuple(nodes), tuple(variations))

    def _node(self) -> RawNode:
        start = self.index
        self._consume(";")
        properties: list[tuple[str, tuple[str, ...]]] = []
        self._skip_space()
        while True:
            current = self._peek()
            if not current or current in ";()":
                break
            if not current.isalpha():
                raise ValueError(f"invalid SGF property at offset {self.index}")
            identifier_start = self.index
            while self._peek().isalpha():
                self.index += 1
            identifier = self.source[identifier_start : self.index]
            self._skip_space()
            values: list[str] = []
            while self._peek() == "[":
                values.append(self._value())
                self._skip_space()
            if not values:
                raise ValueError(f"SGF property {identifier} has no value")
            properties.append((identifier, tuple(values)))
        return RawNode(self.source[start : self.index], tuple(properties))

    def _value(self) -> str:
        self._consume("[")
        result: list[str] = []
        while self.index < len(self.source):
            char = self.source[self.index]
            self.index += 1
            if char == "]":
                return "".join(result)
            if char != "\\":
                result.append(char)
                continue
            if self.index >= len(self.source):
                raise ValueError("incomplete SGF escape")
            escaped = self.source[self.index]
            self.index += 1
            if escaped == "\r":
                if self._peek() == "\n":
                    self.index += 1
                continue
            if escaped == "\n":
                continue
            result.append(escaped)
        raise ValueError("unterminated SGF value")

    def _skip_space(self) -> None:
        while self.index < len(self.source) and self.source[self.index].isspace():
            self.index += 1

    def _peek(self) -> str:
        return self.source[self.index] if self.index < len(self.source) else ""

    def _consume(self, expected: str) -> None:
        if self._peek() != expected:
            raise ValueError(
                f"expected {expected!r} at SGF offset {self.index}, got {self._peek()!r}"
            )
        self.index += 1


def _raw_node_from_move(color: str, coord: str) -> RawNode:
    if color not in ("B", "W"):
        raise ValueError("new answer branch requires B or W")
    sgf_to_xy(coord)
    return RawNode(f";{color}[{coord}]", ((color, (coord,)),))


def _serialize_tree(tree: RawTree) -> str:
    return (
        "("
        + "".join(node.raw for node in tree.sequence)
        + "".join(_serialize_tree(branch) for branch in tree.variations)
        + ")"
    )


def _root_and_branches(tree: RawTree) -> tuple[RawNode, list[RawTree]]:
    root = tree.sequence[0]
    if root.move() is not None:
        raise ValueError("SGF begins with a move and has no metadata root node")
    if len(tree.sequence) > 1:
        return root, [RawTree(tree.sequence[1:], tree.variations)]
    return root, list(tree.variations)


def _tree_with_branches(root: RawNode, branches: Sequence[RawTree]) -> RawTree:
    if len(branches) == 1:
        branch = branches[0]
        return RawTree((root, *branch.sequence), branch.variations)
    return RawTree((root,), tuple(branches))


def _branch_move(branch: RawTree) -> tuple[str, str]:
    if not branch.sequence:
        raise ValueError("root variation has no nodes")
    move = branch.sequence[0].move()
    if move is None or move[1] == "":
        raise ValueError("root variation does not begin with a non-pass move")
    sgf_to_xy(move[1])
    return move


def _answer_structure(content: str) -> dict[str, Any]:
    tree = _LosslessSgfParser(content).parse()
    root, branches = _root_and_branches(tree)
    branch_by_point: dict[tuple[int, int], list[RawTree]] = {}
    colors: set[str] = set()
    ordered_points: list[tuple[int, int]] = []
    for branch in branches:
        color, coord = _branch_move(branch)
        point = sgf_to_xy(coord)
        if point not in branch_by_point:
            branch_by_point[point] = []
            ordered_points.append(point)
        branch_by_point[point].append(branch)
        colors.add(color)
    pl = root.values("PL")
    if pl and pl[0] in ("B", "W"):
        side = pl[0]
    elif len(colors) == 1:
        side = next(iter(colors))
    else:
        side = None
    return {
        "tree": tree,
        "root": root,
        "branches": branches,
        "branch_by_point": branch_by_point,
        "ordered_points": ordered_points,
        "side_to_move": side,
        "branch_colors": colors,
    }


def _rewrite_answer_set(
    content: str, desired_points: Sequence[tuple[int, int]]
) -> tuple[str, dict[str, Any]]:
    before = _answer_structure(content)
    side = before["side_to_move"]
    if side not in ("B", "W"):
        raise ValueError("side to move cannot be determined for answer rewrite")
    branches: list[RawTree] = []
    for point in desired_points:
        existing = before["branch_by_point"].get(point)
        if existing is not None:
            # Multiple authored variations may deliberately share one first
            # move. Preserve every continuation when that move survives.
            branches.extend(existing)
        else:
            branches.append(
                RawTree((_raw_node_from_move(side, xy_to_sgf(*point)),), ())
            )
    if not branches:
        raise ValueError("answer rewrite cannot produce an empty answer set")
    after_tree = _tree_with_branches(before["root"], branches)
    after_content = _serialize_tree(after_tree)
    after = _answer_structure(after_content)
    return after_content, {"before": before, "after": after}


def _answer_packets(
    points: Sequence[tuple[int, int]], side: str | None, board_size: int
) -> list[dict[str, Any]]:
    return [
        {
            "x": x,
            "y": y,
            "color": side,
            "sgf": xy_to_sgf(x, y),
            "gtp": _point_label((x, y), board_size),
        }
        for x, y in points
    ]


def _same_point_set(
    left: Iterable[tuple[int, int]], right: Iterable[tuple[int, int]]
) -> bool:
    return set(left) == set(right)


def _initial_position_signature(root: Any) -> dict[str, Any]:
    properties = root.metadata.get("properties") or {}
    return {
        key: list(properties.get(key) or [])
        for key in ("SZ", "AB", "AW", "AE", "PL")
    }


def _native_judging_validation(
    content: str,
    *,
    desired: Sequence[tuple[int, int]],
    removed: Sequence[tuple[int, int]],
) -> dict[str, Any]:
    root = parse_sgf(content, strict=True)
    desired_results = {
        xy_to_sgf(*point): match_move(root, xy_to_sgf(*point), None).value
        for point in desired
    }
    removed_results = {
        xy_to_sgf(*point): match_move(root, xy_to_sgf(*point), None).value
        for point in removed
    }
    return {
        "desired_all_native_branches": all(
            value == BRANCH.value for value in desired_results.values()
        ),
        "removed_all_off_tree": all(
            value == OFF_TREE.value for value in removed_results.values()
        ),
        "desired_results": desired_results,
        "removed_results": removed_results,
    }


def _reviewed_record(
    reviewed_questions: Sequence[Mapping[str, Any]], locator: Mapping[str, Any]
) -> dict[str, Any]:
    index = locator.get("record_index")
    if (
        not isinstance(index, int)
        or isinstance(index, bool)
        or not (0 <= index < len(reviewed_questions))
    ):
        raise ValueError("reviewed record_index is unavailable")
    record = _require_mapping(reviewed_questions[index], "reviewed question")
    if record.get("id") != locator.get("legacy_question_id"):
        raise ValueError("reviewed record legacy ID mismatch")
    content = record.get("content")
    if not isinstance(content, str):
        raise ValueError("reviewed record has no SGF content")
    if _sha256(content.encode("utf-8")) != locator.get("content_sha256"):
        raise ValueError("reviewed record content hash mismatch")
    return {
        "record_index": index,
        "legacy_question_id": record.get("id"),
        "source_path": record.get("source"),
        "content_sha256": locator.get("content_sha256"),
    }


def _target_key(record: Mapping[str, Any]) -> tuple[Any, ...]:
    locator = _require_mapping(record.get("audit_locator"), "target audit_locator")
    return (
        locator.get("snapshot_sha256"),
        locator.get("record_index"),
        locator.get("legacy_question_id"),
        locator.get("content_sha256"),
    )


def _source_resolution(
    group: Mapping[str, Any],
    *,
    reviewed_questions: Sequence[Mapping[str, Any]],
    targets_by_key: Mapping[tuple[Any, ...], Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    resolved: list[dict[str, Any]] = []
    errors: list[str] = []
    for linked in group.get("linked_records") or []:
        locator = _require_mapping(linked.get("audit_locator"), "audit_locator")
        key = (
            locator.get("snapshot_sha256"),
            locator.get("record_index"),
            locator.get("legacy_question_id"),
            locator.get("content_sha256"),
        )
        try:
            reviewed = _reviewed_record(reviewed_questions, locator)
        except ValueError as error:
            errors.append(f"REVIEWED_SOURCE:{error}")
            continue
        target = targets_by_key.get(key)
        if target is None:
            errors.append("CURRENT_TARGET_EVIDENCE_MISSING")
            resolved.append({"reviewed": reviewed, "target": None, "linked": linked})
            continue
        status = target.get("resolution_status")
        if status != "CURRENT_CONTENT_MATCH":
            errors.append(str(status or "CURRENT_TARGET_UNRESOLVED"))
            resolved.append({"reviewed": reviewed, "target": target, "linked": linked})
            continue
        content = target.get("current_content")
        if not isinstance(content, str):
            errors.append("CURRENT_CONTENT_MISSING")
            resolved.append({"reviewed": reviewed, "target": target, "linked": linked})
            continue
        actual_hash = _sha256(content.encode("utf-8"))
        if actual_hash != target.get("current_content_sha256"):
            errors.append("CURRENT_TARGET_HASH_INVALID")
        if actual_hash != locator.get("content_sha256"):
            errors.append("CURRENT_CONTENT_CHANGED")
        if target.get("current_source_path") != reviewed.get("source_path"):
            errors.append("SOURCE_PATH_CHANGED")
        resolved.append({"reviewed": reviewed, "target": target, "linked": linked})
    return resolved, sorted(set(errors))


def _proposal_points(
    proposals: Sequence[Mapping[str, Any]], proposal_type: str
) -> list[tuple[int, int]]:
    return _ordered_unique_points(
        proposal["proposed_move"]
        for proposal in proposals
        if proposal.get("type") == proposal_type
    )


def _reviewed_historical_points(group: Mapping[str, Any]) -> set[tuple[int, int]]:
    points: set[tuple[int, int]] = set()
    for move in group.get("historical_precomputed_moves") or []:
        try:
            points.add(_move_key(move))
        except ValueError:
            continue
    return points


def _unresolved_diagnostic(resolution_errors: Sequence[str]) -> dict[str, Any]:
    errors = set(resolution_errors)
    if "MISSING_CURRENT_SOURCE" in errors:
        return {
            "primary_reason": "QUESTION_ID_NOT_IN_CURRENT_CORPUS",
            "evidence_reasons": ["REVIEW_SNAPSHOT_FROM_OLDER_CORPUS"],
            "disposition": "RE_REVIEW_REQUIRED",
        }
    if "CURRENT_TARGET_EVIDENCE_MISSING" in errors:
        return {
            "primary_reason": "PROVENANCE_MISSING",
            "evidence_reasons": [],
            "disposition": "SOURCE_RECOVERY_REQUIRED",
        }
    if "CURRENT_CONTENT_MISSING" in errors:
        return {
            "primary_reason": "SGF_SOURCE_MISSING",
            "evidence_reasons": [],
            "disposition": "SOURCE_RECOVERY_REQUIRED",
        }
    if "CURRENT_TARGET_HASH_INVALID" in errors:
        return {
            "primary_reason": "SOURCE_HASH_MISMATCH",
            "evidence_reasons": ["PROVENANCE_STALE"],
            "disposition": "RE_REVIEW_REQUIRED",
        }
    return {
        "primary_reason": "OTHER",
        "evidence_reasons": sorted(errors),
        "disposition": "OTHER",
    }


def _manual_reconstruction_preview(
    group: Mapping[str, Any],
    proposals: Sequence[Mapping[str, Any]],
    resolved: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    target = _require_mapping(resolved[0].get("target"), "manual target")
    content = str(target.get("current_content") or "")
    try:
        root = parse_sgf(content, strict=True)
        signature = _initial_position_signature(root)
        structure = _answer_structure(content)
        board_size = int((signature.get("SZ") or [19])[0])
        side_to_move = structure.get("side_to_move")
        native = _point_labels(structure.get("ordered_points") or [], board_size)
        setup = {
            "black": len(signature.get("AB") or []),
            "white": len(signature.get("AW") or []),
            "empty": len(signature.get("AE") or []),
        }
        parse_status = "PASS"
    except (ValueError, TypeError, IndexError):
        board_size = int(group.get("board_size") or 19)
        side_to_move = group.get("side_to_move")
        native = []
        setup = None
        parse_status = "FAIL"
    proposed_points = []
    for proposal in proposals:
        move = proposal.get("proposed_move")
        if isinstance(move, Mapping):
            proposed_points.append(_move_key(move))
    intended = (
        _point_labels(proposed_points, board_size)
        if proposed_points
        else ["NOT_SPECIFIED_RECONSTRUCTION_REQUIRED"]
    )
    return {
        "legacy_question_id": target.get("legacy_question_id"),
        "source_path": target.get("current_source_path"),
        "content_sha256": target.get("current_content_sha256"),
        "sgf_parse": parse_status,
        "board_size": board_size,
        "setup_stone_counts": setup,
        "side_to_move": side_to_move or "UNKNOWN",
        "current_native_answers": native,
        "historical_precomputed_fallback": str(
            target.get("current_katago_best_move") or ""
        ),
        "owner_reviewed_intended_answer": intended,
        "automatic_reconstruction_unsafe_because": [
            "OWNER_FLAGGED_SOURCE_POSITION_INCLUDES_ANSWER",
            "NO_OWNER_APPROVED_CORRECTED_INITIAL_POSITION",
            "NO_OWNER_APPROVED_NATIVE_ANSWER_SEQUENCE",
        ],
        "likely_reconstruction_options": [
            "REMOVE_THE_ALREADY_PLAYED_ANSWER_FROM_SETUP_AND_AUTHOR_A_NATIVE_TREE",
            "CORRECT_SIDE_TO_MOVE_AND_AUTHOR_A_NATIVE_TREE",
            "RECOVER_THE_PRE_CONVERSION_SOURCE_POSITION",
        ],
        "exact_owner_decision_required": (
            "Approve the corrected initial stones, side to move, and complete "
            "native answer variation; the D16 fallback is evidence only."
        ),
    }


def _review_state_evidence(
    group: Mapping[str, Any],
    proposals: Sequence[Mapping[str, Any]],
    resolved: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    board_size = int(group.get("board_size") or 19)
    reviewed_points = _ordered_unique_points(
        group.get("current_first_solution_moves") or []
    )
    replace = _proposal_points(proposals, "REPLACE_PRIMARY_ANSWER")
    additions = _proposal_points(proposals, "ADD_EQUIVALENT_SOLUTION")
    desired = list(replace if replace else reviewed_points)
    for point in additions:
        if point not in desired:
            desired.append(point)
    if set(str(p.get("type") or "") for p in proposals) & MANUAL_TYPES:
        desired_state: Any = "MANUAL_RECONSTRUCTION_OWNER_DECISION_REQUIRED"
    else:
        desired_state = _point_labels(desired, board_size)
    current_records = []
    for item in resolved:
        target = item.get("target")
        if not isinstance(target, Mapping):
            continue
        content = target.get("current_content")
        current_native: Any = "UNAVAILABLE"
        current_side: Any = "UNKNOWN"
        if isinstance(content, str):
            try:
                structure = _answer_structure(content)
                current_native = _point_labels(
                    structure["ordered_points"], board_size
                )
                current_side = structure["side_to_move"] or "UNKNOWN"
            except (ValueError, TypeError):
                current_native = "PARSE_FAILURE"
        current_records.append(
            {
                "legacy_question_id": target.get("legacy_question_id"),
                "source_path": target.get("current_source_path"),
                "content_sha256": target.get("current_content_sha256"),
                "side_to_move": current_side,
                "native_answers": current_native,
                "accepted_moves": target.get("current_accepted_moves") or [],
                "stored_precomputed_fallback": str(
                    target.get("current_katago_best_move") or ""
                ),
            }
        )
    return {
        "owner_reviewed_current_state": {
            "side_to_move": group.get("side_to_move") or "UNKNOWN",
            "native_answers": _point_labels(reviewed_points, board_size),
            "reviewed_content_sha256": group.get("review_group_key"),
        },
        "current_canonical_state": current_records,
        "owner_desired_state": desired_state,
    }


def _simulate_record(
    resolved: Mapping[str, Any],
    *,
    desired_points: Sequence[tuple[int, int]],
    replace_answer_set: bool,
    reject_fallback: bool,
    reviewed_historical_points: set[tuple[int, int]],
) -> tuple[dict[str, Any], str]:
    target = _require_mapping(resolved.get("target"), "resolved target")
    content = str(target.get("current_content") or "")
    parsed_before = parse_sgf(content, strict=True)
    try:
        board_size = int(
            (parsed_before.metadata.get("properties", {}).get("SZ") or [19])[0]
        )
    except (TypeError, ValueError, IndexError):
        board_size = 19
    structure_before = _answer_structure(content)
    current_points = list(structure_before["ordered_points"])
    removed_points = [
        point for point in current_points if point not in set(desired_points)
    ]
    content_after = content
    branch_preservation = True
    root_preserved = True
    if not _same_point_set(current_points, desired_points):
        content_after, rewrite = _rewrite_answer_set(content, desired_points)
        before_structure = rewrite["before"]
        after_structure = rewrite["after"]
        root_preserved = (
            before_structure["root"].raw == after_structure["root"].raw
        )
        for point in set(current_points) & set(desired_points):
            before_branches = before_structure["branch_by_point"][point]
            after_branches = after_structure["branch_by_point"][point]
            if [
                _serialize_tree(branch) for branch in before_branches
            ] != [
                _serialize_tree(branch) for branch in after_branches
            ]:
                branch_preservation = False

    parsed_after = parse_sgf(content_after, strict=True)
    structure_after = _answer_structure(content_after)
    actual_after_points = list(structure_after["ordered_points"])
    accepted_moves = {
        _move_key(move)
        for move in (target.get("current_accepted_moves") or [])
        if isinstance(move, Mapping)
    }
    accepted_removed_conflict = sorted(accepted_moves & set(removed_points))
    accepted_replacement_conflict = sorted(
        accepted_moves - set(desired_points)
        if replace_answer_set
        else set()
    )

    fallback_before = str(target.get("current_katago_best_move") or "").strip()
    fallback_point = (
        _gtp_to_xy(fallback_before, board_size) if fallback_before else None
    )
    if fallback_before and fallback_point is None:
        raise ValueError("HISTORICAL_FALLBACK_COORDINATE_INVALID")
    fallback_match = (
        fallback_point in reviewed_historical_points
        if fallback_point is not None
        else False
    )
    fallback_after = fallback_before
    fallback_replacement_conflict = bool(
        replace_answer_set
        and fallback_point is not None
        and fallback_point not in set(desired_points)
        and not reject_fallback
    )
    if reject_fallback:
        if not fallback_before:
            raise ValueError("historical fallback is already empty")
        if not fallback_match:
            raise ValueError(
                "current historical fallback differs from reviewed evidence"
            )
        if fallback_point in set(actual_after_points) or fallback_point in accepted_moves:
            raise ValueError(
                "rejected fallback remains accepted by another answer layer"
            )
        fallback_after = ""

    current_effective = set(current_points) | accepted_moves
    if fallback_point is not None:
        current_effective.add(fallback_point)
    if replace_answer_set:
        owner_desired_effective = set(desired_points)
    else:
        owner_desired_effective = current_effective | set(desired_points)
    if reject_fallback and fallback_point is not None:
        owner_desired_effective.discard(fallback_point)

    fallback_after_point = (
        _gtp_to_xy(fallback_after, board_size) if fallback_after else None
    )
    current_layers = _effective_verdict_layers(
        native_points=current_points,
        accepted_points=accepted_moves,
        fallback_point=fallback_point,
        board_size=board_size,
    )
    simulated_layers = _effective_verdict_layers(
        native_points=actual_after_points,
        accepted_points=accepted_moves,
        fallback_point=fallback_after_point,
        board_size=board_size,
    )
    simulated_effective = set(actual_after_points) | accepted_moves
    if fallback_after_point is not None:
        simulated_effective.add(fallback_after_point)
    simulated_surface_sets = [
        set(actual_after_points) | accepted_moves,
        set(actual_after_points),
        set(actual_after_points)
        | ({fallback_after_point} if fallback_after_point is not None else set()),
    ]
    effective_match = (
        simulated_effective == owner_desired_effective
        and all(
            surface == owner_desired_effective
            for surface in simulated_surface_sets
        )
    )

    judging = _native_judging_validation(
        content_after, desired=desired_points, removed=removed_points
    )
    validation = {
        "sgf_parse_before": True,
        "sgf_parse_after": True,
        "initial_position_preserved": _initial_position_signature(parsed_before)
        == _initial_position_signature(parsed_after),
        "root_metadata_raw_preserved": root_preserved,
        "surviving_variations_preserved": branch_preservation,
        "side_to_move_preserved": structure_before["side_to_move"]
        == structure_after["side_to_move"],
        "answer_set_exact": _same_point_set(
            actual_after_points, desired_points
        ),
        "accepted_moves_removed_conflict": [
            _point_label(point, board_size)
            for point in accepted_removed_conflict
        ],
        "accepted_moves_replacement_conflict": [
            _point_label(point, board_size)
            for point in accepted_replacement_conflict
        ],
        "native_judging": judging,
        "historical_fallback_cleared": (
            not reject_fallback or fallback_after == ""
        ),
        "fallback_replacement_conflict": fallback_replacement_conflict,
        "owner_desired_verdict_equals_simulated_final_effective_player_verdict": (
            effective_match
        ),
    }
    validation["native_repair_passed"] = bool(
        validation["initial_position_preserved"]
        and validation["root_metadata_raw_preserved"]
        and validation["surviving_variations_preserved"]
        and validation["side_to_move_preserved"]
        and validation["answer_set_exact"]
        and not accepted_removed_conflict
        and not accepted_replacement_conflict
        and judging["desired_all_native_branches"]
        and judging["removed_all_off_tree"]
        and validation["historical_fallback_cleared"]
    )
    validation["passed"] = bool(
        validation["native_repair_passed"] and effective_match
    )

    current_index = int(target["current_record_index"])
    legacy_id = target.get("legacy_question_id")
    artifact_name = f"record-{current_index:05d}-q{legacy_id}.sgf"
    simulated_record = {
        "content_sha256": _sha256(content_after.encode("utf-8")),
        "katago_best_move": fallback_after,
        "accepted_moves": list(target.get("current_accepted_moves") or []),
    }
    operations: list[dict[str, Any]] = []
    if not _same_point_set(current_points, desired_points):
        operations.append(
            {
                "type": "REWRITE_NATIVE_ROOT_ANSWER_SET",
                "before": [
                    _point_label(point, board_size) for point in current_points
                ],
                "after": [
                    _point_label(point, board_size) for point in desired_points
                ],
                "removed": [
                    _point_label(point, board_size) for point in removed_points
                ],
                "added": [
                    _point_label(point, board_size)
                    for point in desired_points
                    if point not in set(current_points)
                ],
            }
        )
    if reject_fallback:
        operations.append(
            {
                "type": "CLEAR_PRECOMPUTED_KATAGO_FALLBACK",
                "before": fallback_before,
                "after": "",
            }
        )
    return {
        "audit_locator": resolved["linked"]["audit_locator"],
        "legacy_question_id": legacy_id,
        "reviewed_record_index": resolved["reviewed"]["record_index"],
        "current_record_index": current_index,
        "source_path": target.get("current_source_path"),
        "source_content_sha256_before": target.get(
            "current_content_sha256"
        ),
        "source_content_sha256_after": simulated_record[
            "content_sha256"
        ],
        "current_side_to_move": structure_before["side_to_move"],
        "current_authoritative_native_answers": _answer_packets(
            current_points, structure_before["side_to_move"], board_size
        ),
        "desired_authoritative_native_answers": _answer_packets(
            desired_points, structure_after["side_to_move"], board_size
        ),
        "current_katago_best_move": fallback_before,
        "desired_katago_best_move": fallback_after,
        "current_effective_verdict": current_layers,
        "owner_desired_verdict": _point_labels(
            owner_desired_effective, board_size
        ),
        "simulated_final_verdict": simulated_layers,
        "match": effective_match,
        "planned_operations": operations,
        "existing_tree": {
            "native_root_solution_count": len(current_points),
            "root_variation_count": len(structure_before["branches"]),
        },
        "simulation_artifact": artifact_name,
        "simulated_record_sha256": _sha256(
            _canonical_json_bytes(simulated_record)
        ),
        "validation": validation,
    }, content_after


def _classify_group(
    group: Mapping[str, Any],
    *,
    reviewed_questions: Sequence[Mapping[str, Any]],
    targets_by_key: Mapping[tuple[Any, ...], Mapping[str, Any]],
    simulation_dir: Path | None,
) -> dict[str, Any]:
    state = _require_mapping(group.get("state"), "group state")
    proposals = [
        _require_mapping(proposal, "proposal")
        for proposal in (state.get("proposals") or [])
    ]
    proposal_types = [
        str(proposal.get("type") or "") for proposal in proposals
    ]
    reject_fallback_requested = (
        "REJECT_HISTORICAL_PRECOMPUTED_FALLBACK" in proposal_types
    )
    unknown = sorted(set(proposal_types) - KNOWN_TYPES)
    resolved, resolution_errors = _source_resolution(
        group,
        reviewed_questions=reviewed_questions,
        targets_by_key=targets_by_key,
    )
    result: dict[str, Any] = {
        "review_group_key": group.get("review_group_key"),
        "group_order": group.get("group_order"),
        "group_size": group.get("group_size"),
        "legacy_question_ids": [
            linked.get("legacy_question_id")
            for linked in (group.get("linked_records") or [])
        ],
        "state_revision": state.get("revision"),
        "state_updated_at": state.get("updated_at"),
        "proposal_types": proposal_types,
        "repair_classes": list(
            dict.fromkeys(
                REPAIR_CLASS_BY_PROPOSAL_TYPE.get(
                    proposal_type, "OTHER_MANUAL_REVIEW_REQUIRED"
                )
                for proposal_type in proposal_types
            )
        ),
        "classification": None,
        "reason_codes": [],
        "records": [],
    }
    result.update(_review_state_evidence(group, proposals, resolved))

    available_count = sum(
        1
        for item in resolved
        if (item.get("target") or {}).get("resolution_status")
        == "CURRENT_CONTENT_MATCH"
    )
    if resolution_errors:
        if available_count == 0 and all(
            code
            in {
                "MISSING_CURRENT_SOURCE",
                "CURRENT_TARGET_EVIDENCE_MISSING",
            }
            for code in resolution_errors
        ):
            result["classification"] = CLASS_UNRESOLVED
            result["unresolved"] = _unresolved_diagnostic(
                resolution_errors
            )
        else:
            result["classification"] = CLASS_STALE
        result["reason_codes"] = resolution_errors
        result["records"] = [
            {
                "audit_locator": item["linked"]["audit_locator"],
                "legacy_question_id": item["linked"].get(
                    "legacy_question_id"
                ),
                "source_path": item["reviewed"].get("source_path"),
                "current_source_path": (
                    (item.get("target") or {}).get("current_source_path")
                    if item.get("target")
                    else None
                ),
                "reviewed_content_sha256": item["reviewed"].get(
                    "content_sha256"
                ),
                "current_content_sha256": (
                    (item.get("target") or {}).get(
                        "current_content_sha256"
                    )
                    if item.get("target")
                    else None
                ),
                "current_resolution": (
                    (item.get("target") or {}).get("resolution_status")
                    if item.get("target")
                    else "CURRENT_TARGET_EVIDENCE_MISSING"
                ),
            }
            for item in resolved
        ]
        return result

    current_fallbacks = list(
        dict.fromkeys(
            str(item["target"].get("current_katago_best_move") or "").strip()
            for item in resolved
            if item.get("target") is not None
            and str(
                item["target"].get("current_katago_best_move") or ""
            ).strip()
        )
    )
    result["current_precomputed_fallbacks"] = current_fallbacks
    result["desired_precomputed_fallbacks"] = (
        [] if reject_fallback_requested else current_fallbacks
    )

    if unknown:
        result["classification"] = CLASS_MANUAL
        result["reason_codes"] = ["UNSUPPORTED_PROPOSAL_TYPE", *unknown]
        return result
    if set(proposal_types) & MANUAL_TYPES:
        result["classification"] = CLASS_MANUAL
        result["reason_codes"] = sorted(set(proposal_types) & MANUAL_TYPES)
        result["records"] = [
            {
                "audit_locator": item["linked"]["audit_locator"],
                "legacy_question_id": item["linked"].get(
                    "legacy_question_id"
                ),
                "source_path": item["reviewed"].get("source_path"),
                "current_record_index": item["target"].get(
                    "current_record_index"
                ),
                "current_content_sha256": item["target"].get(
                    "current_content_sha256"
                ),
            }
            for item in resolved
        ]
        result["manual_reconstruction_preview"] = (
            _manual_reconstruction_preview(group, proposals, resolved)
        )
        return result

    first_target = _require_mapping(
        resolved[0].get("target"), "first target"
    )
    first_content = str(first_target.get("current_content") or "")
    try:
        first_structure = _answer_structure(first_content)
    except (ValueError, TypeError) as error:
        result["classification"] = CLASS_STALE
        result["reason_codes"] = [
            "CURRENT_SGF_STRUCTURE_INVALID",
            str(error),
        ]
        return result
    current_points = list(first_structure["ordered_points"])
    board_size = int(group.get("board_size") or 19)
    reviewed_points = _ordered_unique_points(
        group.get("current_first_solution_moves") or []
    )
    if not _same_point_set(current_points, reviewed_points):
        result["classification"] = CLASS_STALE
        result["reason_codes"] = [
            "CURRENT_NATIVE_ANSWERS_DIFFER_FROM_REVIEWED_STATE"
        ]
        return result
    if group.get("side_to_move") not in (
        None,
        first_structure["side_to_move"],
    ):
        result["classification"] = CLASS_STALE
        result["reason_codes"] = [
            "CURRENT_SIDE_TO_MOVE_DIFFERS_FROM_REVIEWED_STATE"
        ]
        return result

    for proposal in proposals:
        original = _ordered_unique_points(
            proposal.get("original_answers") or []
        )
        if not _same_point_set(original, reviewed_points):
            result["classification"] = CLASS_STALE
            result["reason_codes"] = ["PROPOSAL_ORIGINAL_ANSWERS_STALE"]
            return result

    replace_points = _proposal_points(
        proposals, "REPLACE_PRIMARY_ANSWER"
    )
    add_points = _proposal_points(
        proposals, "ADD_EQUIVALENT_SOLUTION"
    )
    desired_points = list(
        replace_points if replace_points else current_points
    )
    for point in add_points:
        if point not in desired_points:
            desired_points.append(point)
    reject_fallback = reject_fallback_requested
    current_labels = [
        _point_label(point, board_size) for point in current_points
    ]
    desired_labels = [
        _point_label(point, board_size) for point in desired_points
    ]
    intended_operations: list[dict[str, Any]] = []
    if replace_points:
        intended_operations.append(
            {
                "type": "REWRITE_NATIVE_ROOT_ANSWER_SET",
                "before": current_labels,
                "after": desired_labels,
                "removed": [
                    _point_label(point, board_size)
                    for point in current_points
                    if point not in set(desired_points)
                ],
                "added": [
                    _point_label(point, board_size)
                    for point in desired_points
                    if point not in set(current_points)
                ],
            }
        )
    elif add_points:
        intended_operations.append(
            {
                "type": "REWRITE_NATIVE_ROOT_ANSWER_SET",
                "before": current_labels,
                "after": desired_labels,
                "removed": [],
                "added": [
                    _point_label(point, board_size)
                    for point in desired_points
                    if point not in set(current_points)
                ],
            }
        )
    if reject_fallback:
        intended_operations.append(
            {"type": "CLEAR_PRECOMPUTED_KATAGO_FALLBACK"}
        )
    result.update(
        {
            "current_answer_set": current_labels,
            "desired_answer_set": desired_labels,
            "intended_operations": intended_operations,
        }
    )
    if not desired_points:
        result["classification"] = CLASS_MANUAL
        result["reason_codes"] = [
            "NO_VALID_NATIVE_ANSWER_AFTER_REPAIR"
        ]
        return result
    if (
        first_structure["side_to_move"] not in ("B", "W")
        or first_structure["branch_colors"]
        != {first_structure["side_to_move"]}
    ):
        result["classification"] = CLASS_MANUAL
        result["reason_codes"] = [
            "NATIVE_ROOT_MOVE_COLOR_OR_SIDE_UNKNOWN"
        ]
        return result
    if (
        _same_point_set(current_points, desired_points)
        and not reject_fallback
    ):
        result["classification"] = CLASS_NO_OP
        result["reason_codes"] = ["EXACT_SEMANTIC_NO_OP"]
        return result

    historical_points = _reviewed_historical_points(group)
    simulated: list[dict[str, Any]] = []
    simulated_contents: list[str] = []
    try:
        for item in resolved:
            record_plan, simulated_content = _simulate_record(
                item,
                desired_points=desired_points,
                replace_answer_set=bool(replace_points),
                reject_fallback=reject_fallback,
                reviewed_historical_points=historical_points,
            )
            simulated.append(record_plan)
            simulated_contents.append(simulated_content)
    except (ValueError, TypeError) as error:
        result["classification"] = CLASS_STALE
        result["reason_codes"] = [
            "SIMULATION_VALIDATION_FAILED",
            str(error),
        ]
        return result

    native_repair_passed = all(
        record["validation"]["native_repair_passed"]
        for record in simulated
    )
    end_to_end_match = all(record["match"] for record in simulated)
    fallback_conflict = any(
        record["validation"]["fallback_replacement_conflict"]
        for record in simulated
    )
    if not native_repair_passed:
        result.update(
            {
                "classification": CLASS_STALE,
                "reason_codes": ["SIMULATION_VALIDATION_FAILED"],
                "records": simulated,
            }
        )
        return result

    if simulation_dir is not None:
        simulation_dir.mkdir(parents=True, exist_ok=True)
        for record_plan, simulated_content in zip(
            simulated, simulated_contents, strict=True
        ):
            artifact_path = simulation_dir / record_plan[
                "simulation_artifact"
            ]
            artifact_bytes = simulated_content.encode("utf-8")
            artifact_path.write_bytes(artifact_bytes)
            if _sha256(artifact_bytes) != record_plan[
                "source_content_sha256_after"
            ]:
                raise RuntimeError(
                    "isolated repair artifact hash verification failed"
                )
    result.update(
        {
            "classification": (
                CLASS_FULLY
                if end_to_end_match
                else (
                    CLASS_FALLBACK_CONFLICT
                    if fallback_conflict
                    else CLASS_STALE
                )
            ),
            "reason_codes": (
                ["END_TO_END_EFFECTIVE_VERDICT_MATCH"]
                if end_to_end_match
                else (
                    [
                        "UNREJECTED_PRECOMPUTED_FALLBACK_OUTSIDE_REPLACEMENT_SET"
                    ]
                    if fallback_conflict
                    else ["FINAL_EFFECTIVE_VERDICT_MISMATCH"]
                )
            ),
            "records": simulated,
        }
    )
    return result


def build_repair_plan(
    proposal_snapshot: Mapping[str, Any],
    reviewed_questions: Sequence[Mapping[str, Any]],
    current_targets: Mapping[str, Any],
    *,
    proposal_snapshot_sha256: str,
    reviewed_questions_sha256: str,
    current_targets_sha256: str,
    simulation_dir: Path | None = None,
) -> dict[str, Any]:
    proposal_snapshot = _require_mapping(
        proposal_snapshot, "proposal snapshot"
    )
    current_targets = _require_mapping(
        current_targets, "current targets"
    )
    if (
        proposal_snapshot.get("authority")
        != "PRODUCTION_OWNER_REVIEW_QUEUE_READ_ONLY_SNAPSHOT"
    ):
        raise ValueError("unexpected proposal snapshot authority")
    if (
        current_targets.get("authority")
        != "PRODUCTION_CANONICAL_TARGET_READ_ONLY_SNAPSHOT"
    ):
        raise ValueError("unexpected current target authority")
    queue_snapshot = _require_mapping(
        proposal_snapshot.get("queue_source", {}).get("source_snapshot"),
        "queue source snapshot",
    )
    if reviewed_questions_sha256 != queue_snapshot.get("sha256"):
        raise ValueError(
            "reviewed questions snapshot hash does not match proposal provenance"
        )
    if len(reviewed_questions) != queue_snapshot.get("question_count"):
        raise ValueError(
            "reviewed questions snapshot count does not match proposal provenance"
        )
    if (
        current_targets.get("proposal_snapshot_sha256")
        != proposal_snapshot_sha256
    ):
        raise ValueError(
            "current target evidence is not bound to this proposal snapshot"
        )

    targets = current_targets.get("records")
    if not isinstance(targets, list):
        raise ValueError("current target records are missing")
    targets_by_key = {_target_key(record): record for record in targets}
    if len(targets_by_key) != len(targets):
        raise ValueError(
            "current target evidence contains duplicate locators"
        )

    groups = proposal_snapshot.get("groups")
    if not isinstance(groups, list):
        raise ValueError("proposal snapshot groups are missing")
    plans = [
        _classify_group(
            group,
            reviewed_questions=reviewed_questions,
            targets_by_key=targets_by_key,
            simulation_dir=simulation_dir,
        )
        for group in groups
    ]
    counts = {
        classification: 0
        for classification in (
            CLASS_FULLY,
            CLASS_FALLBACK_CONFLICT,
            CLASS_MANUAL,
            CLASS_STALE,
            CLASS_UNRESOLVED,
            CLASS_NO_OP,
        )
    }
    for plan in plans:
        counts[plan["classification"]] += 1

    active_duplicate_groups = [
        group
        for group in groups
        if int(group.get("group_size") or 0) > 1
    ]
    safe_duplicate_groups = [
        plan
        for plan in plans
        if plan["classification"] == CLASS_FULLY
        and int(plan.get("group_size") or 0) > 1
    ]
    duplicate_conflicts = [
        plan
        for plan in plans
        if int(plan.get("group_size") or 0) > 1
        and plan["classification"] == CLASS_STALE
    ]
    planned_records = [
        record
        for plan in plans
        if plan["classification"] == CLASS_FULLY
        for record in plan.get("records") or []
    ]
    planned_sources = sorted(
        {
            str(record.get("source_path") or "")
            for record in planned_records
        }
    )
    replacement_fallback_conflicts = [
        plan
        for plan in plans
        if "UNREJECTED_PRECOMPUTED_FALLBACK_OUTSIDE_REPLACEMENT_SET"
        in (plan.get("reason_codes") or [])
    ]
    reason_code_counts: dict[str, int] = {}
    for plan in plans:
        for reason_code in plan.get("reason_codes") or []:
            reason_code_counts[str(reason_code)] = (
                reason_code_counts.get(str(reason_code), 0) + 1
            )
    reason_code_counts = dict(sorted(reason_code_counts.items()))

    question_15436 = None
    for plan in plans:
        if 15436 in plan.get("legacy_question_ids", []):
            question_15436 = {
                "present": True,
                "classification": plan["classification"],
                "current": plan.get("current_answer_set"),
                "desired": plan.get("desired_answer_set"),
                "current_precomputed_fallbacks": plan.get(
                    "current_precomputed_fallbacks"
                ),
                "desired_precomputed_fallbacks": plan.get(
                    "desired_precomputed_fallbacks"
                ),
                "reason_codes": plan.get("reason_codes"),
                "current_effective_verdict": (
                    (plan.get("records") or [{}])[0].get(
                        "current_effective_verdict"
                    )
                ),
                "owner_desired_verdict": (
                    (plan.get("records") or [{}])[0].get(
                        "owner_desired_verdict"
                    )
                ),
                "simulated_final_verdict": (
                    (plan.get("records") or [{}])[0].get(
                        "simulated_final_verdict"
                    )
                ),
                "plan": ([
                    operation
                    for record in plan.get("records") or []
                    for operation in record.get(
                        "planned_operations"
                    )
                    or []
                ] or list(plan.get("intended_operations") or [])),
            }
            final_labels = set(
                (
                    question_15436.get("simulated_final_verdict") or {}
                ).get("final_effective_player_verdict")
                or []
            )
            question_15436["mandatory_proof"] = {
                "B1": "ACCEPT" if "B1" in final_labels else "REJECT",
                "A2": "ACCEPT" if "A2" in final_labels else "REJECT",
                "Q4": "ACCEPT" if "Q4" in final_labels else "REJECT",
                "final_effective_verdict_safe": final_labels == {"B1"},
            }
            break
    if question_15436 is None:
        question_15436 = {
            "present": False,
            "classification": None,
            "plan": [],
        }

    summary = {
        "active_proposals": int(
            proposal_snapshot.get("counts", {}).get(
                "active_proposals"
            )
            or 0
        ),
        "active_review_groups": len(plans),
        "affected_question_records": int(
            proposal_snapshot.get("counts", {}).get(
                "affected_question_records"
            )
            or 0
        ),
        "fully_applyable_end_to_end": counts[CLASS_FULLY],
        "native_repair_valid_but_fallback_conflict": counts[
            CLASS_FALLBACK_CONFLICT
        ],
        "manual_reconstruction_required": counts[CLASS_MANUAL],
        "stale_or_conflicted": counts[CLASS_STALE],
        "unresolved": counts[CLASS_UNRESOLVED],
        "no_op": counts[CLASS_NO_OP],
        "duplicate_groups": len(active_duplicate_groups),
        "multi_record_repair_groups": len(safe_duplicate_groups),
        "duplicate_fanout_records": sum(
            int(plan["group_size"]) - 1
            for plan in safe_duplicate_groups
        ),
        "duplicate_group_conflicts": len(duplicate_conflicts),
        "planned_canonical_files_changed": len(planned_sources),
        "planned_question_records_changed": len(planned_records),
        "precomputed_fallbacks_cleared": sum(
            1
            for record in planned_records
            if record.get("current_katago_best_move")
            and not record.get("desired_katago_best_move")
        ),
        "precomputed_fallbacks_preserved": sum(
            1
            for record in planned_records
            if record.get("current_katago_best_move")
            and record.get("desired_katago_best_move")
        ),
        "replacement_fallback_conflicts": len(
            replacement_fallback_conflicts
        ),
    }
    plan_core = {
        "proposal_snapshot_sha256": proposal_snapshot_sha256,
        "reviewed_questions_sha256": reviewed_questions_sha256,
        "current_targets_sha256": current_targets_sha256,
        "current_production_questions_sha256": current_targets.get(
            "production_questions", {}
        ).get("content_sha256"),
        "groups": plans,
    }
    repair_plan_sha256 = _sha256(
        _canonical_json_bytes(plan_core)
    )
    multi_answer_records = [
        record
        for record in planned_records
        if len(record.get("desired_authoritative_native_answers") or []) > 1
    ]
    validation = {
        "isolated_repair_records": len(planned_records),
        "sgf_parse_validation": all(
            record["validation"]["sgf_parse_before"]
            and record["validation"]["sgf_parse_after"]
            for record in planned_records
        ),
        "native_judging_validation": all(
            record["validation"]["native_judging"][
                "desired_all_native_branches"
            ]
            and record["validation"]["native_judging"][
                "removed_all_off_tree"
            ]
            for record in planned_records
        ),
        "position_and_variation_preservation": all(
            record["validation"]["initial_position_preserved"]
            and record["validation"]["root_metadata_raw_preserved"]
            and record["validation"]["surviving_variations_preserved"]
            for record in planned_records
        ),
        "multi_answer_record_count": len(multi_answer_records),
        "multi_answer_validation": all(
            record["validation"]["answer_set_exact"]
            and record["validation"]["native_judging"][
                "desired_all_native_branches"
            ]
            for record in multi_answer_records
        ),
        "final_effective_judging_simulation": all(
            record.get("match") is True for record in planned_records
        ),
    }

    unresolved_groups = [
        {
            "review_group_key": plan.get("review_group_key"),
            "legacy_question_ids": plan.get("legacy_question_ids") or [],
            "primary_reason": plan["unresolved"]["primary_reason"],
            "evidence_reasons": plan["unresolved"]["evidence_reasons"],
            "disposition": plan["unresolved"]["disposition"],
        }
        for plan in plans
        if plan["classification"] == CLASS_UNRESOLVED
    ]
    unresolved_reason_breakdown: dict[str, int] = {}
    unresolved_disposition_breakdown: dict[str, int] = {}
    for item in unresolved_groups:
        for reason in [item["primary_reason"], *item["evidence_reasons"]]:
            unresolved_reason_breakdown[reason] = (
                unresolved_reason_breakdown.get(reason, 0) + 1
            )
        disposition = item["disposition"]
        unresolved_disposition_breakdown[disposition] = (
            unresolved_disposition_breakdown.get(disposition, 0) + 1
        )

    conflict_review_groups = [
        {
            "question_id_or_review_group": (
                plan.get("legacy_question_ids") or [plan["review_group_key"]]
            ),
            "review_group_key": plan.get("review_group_key"),
            "owner_reviewed_current_state": plan.get(
                "owner_reviewed_current_state"
            ),
            "current_canonical_state": plan.get("current_canonical_state"),
            "owner_desired_state": plan.get("owner_desired_state"),
            "conflict_reason": plan.get("reason_codes") or [],
            "recommended_disposition": (
                "OWNER_FALLBACK_DECISION_REQUIRED_THEN_RE_REVIEW"
                if plan["classification"] == CLASS_FALLBACK_CONFLICT
                else "RE_REVIEW_REQUIRED"
            ),
        }
        for plan in plans
        if plan["classification"] in {
            CLASS_FALLBACK_CONFLICT,
            CLASS_STALE,
        }
    ]

    safe_groups = []
    for plan in plans:
        if plan["classification"] != CLASS_FULLY:
            continue
        safe_groups.append(
            {
                "review_group_key": plan["review_group_key"],
                "legacy_question_ids": plan["legacy_question_ids"],
                "group_size": plan["group_size"],
                "classification": plan["classification"],
                "records": [
                    {
                        "audit_locator": record["audit_locator"],
                        "legacy_question_id": record["legacy_question_id"],
                        "current_record_index": record["current_record_index"],
                        "source_path": record["source_path"],
                        "source_content_sha256_before": record[
                            "source_content_sha256_before"
                        ],
                        "source_content_sha256_after": record[
                            "source_content_sha256_after"
                        ],
                        "planned_operations": record["planned_operations"],
                        "current_effective_verdict": record[
                            "current_effective_verdict"
                        ],
                        "owner_desired_verdict": record[
                            "owner_desired_verdict"
                        ],
                        "simulated_final_verdict": record[
                            "simulated_final_verdict"
                        ],
                        "match": "YES" if record["match"] else "NO",
                    }
                    for record in plan.get("records") or []
                ],
            }
        )
    safe_files = sorted(
        {
            record["source_path"]
            for group in safe_groups
            for record in group["records"]
        }
    )
    safe_batch_core = {
        "proposal_snapshot_sha256": proposal_snapshot_sha256,
        "reviewed_questions_sha256": reviewed_questions_sha256,
        "current_targets_sha256": current_targets_sha256,
        "repair_plan_sha256": repair_plan_sha256,
        "invariant": (
            "OWNER_DESIRED_VERDICT == "
            "SIMULATED_FINAL_EFFECTIVE_PLAYER_VERDICT"
        ),
        "groups": safe_groups,
        "files": safe_files,
    }
    safe_batch_sha256 = _sha256(_canonical_json_bytes(safe_batch_core))
    safe_batch = {
        "schema_version": "1.0",
        "authority": "SGF_ANSWER_REPAIR_BATCH_001_SAFE_FIRST_BATCH_DRY_RUN_ONLY",
        "classification_filter": [CLASS_FULLY],
        "excluded_classifications": [
            CLASS_FALLBACK_CONFLICT,
            CLASS_MANUAL,
            CLASS_STALE,
            CLASS_UNRESOLVED,
            CLASS_NO_OP,
        ],
        **safe_batch_core,
        "summary": {
            "safe_batch_groups": len(safe_groups),
            "safe_batch_records": sum(
                len(group["records"]) for group in safe_groups
            ),
            "safe_batch_files": len(safe_files),
            "safe_batch_sha256": safe_batch_sha256,
        },
        "safe_batch_sha256": safe_batch_sha256,
        "apply_authorized": False,
    }

    question_verdict_traces = {}
    for question_id in (15436, 15388, 65095):
        plan = next(
            (
                candidate
                for candidate in plans
                if question_id in candidate.get("legacy_question_ids", [])
            ),
            None,
        )
        if plan is None:
            continue
        record = (plan.get("records") or [None])[0]
        question_verdict_traces[str(question_id)] = {
            "fallback_source_field": "katago_best_move",
            "fallback_storage_location": (
                "per-question /app/data/questions.json katago_best_move field; "
                "copied into the in-memory Rating Test pool. The optional "
                "rating_verified_questions.json override file is absent from "
                "the canonical tree and is not copied by the Dockerfile"
            ),
            "verified_override_evidence": (
                "CANONICAL_FILE_ABSENT_AND_NOT_PACKAGED"
            ),
            "fallback_provenance": (
                "historical Owner-side offline KataGo preprocessing before upload; "
                "no Production KataGo execution is involved"
            ),
            "fallback_acceptance_condition": (
                "Rating Test only: exactly one submitted move equals the session-"
                "transformed stored fallback after accepted/native legacy replay "
                "has not returned true"
            ),
            "final_verdict_path": [
                "main practice: accepted_moves injected into native SGF client tree",
                "daily challenge: native SGF client tree; server trusts client correct",
                "friend challenge: main client verdict; server trusts client correct",
                "Map Battle V1: server accepted_moves then native SGF tree",
                "Rating Test: pool accepted_moves check (currently empty because pool projection omits it), native legacy SGF replay, stored katago_best_move fallback",
            ],
            "classification": plan["classification"],
            "current_native_answers": plan.get("current_answer_set") or [],
            "owner_desired_answers": plan.get("desired_answer_set") or [],
            "stored_fallbacks": plan.get("current_precomputed_fallbacks") or [],
            "end_to_end_record": record,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "authority": AUTHORITY,
        "output_classification": OUTPUT_CLASSIFICATION,
        "identity_boundary": (
            "AUDIT_LOCATOR_ONLY; IDENTITY_IMPLEMENTED=NO"
        ),
        "inputs": {
            "proposal_snapshot_sha256": proposal_snapshot_sha256,
            "proposal_snapshot_timestamp": proposal_snapshot.get(
                "captured_at"
            ),
            "reviewed_questions_sha256": reviewed_questions_sha256,
            "reviewed_questions_count": len(reviewed_questions),
            "current_targets_sha256": current_targets_sha256,
            "current_targets_timestamp": current_targets.get(
                "captured_at"
            ),
            "current_production_questions": current_targets.get(
                "production_questions"
            ),
            "production_app": current_targets.get("production_app"),
        },
        "summary": summary,
        "reason_code_counts": reason_code_counts,
        "validation": validation,
        "question_15436": question_15436,
        "question_verdict_traces": question_verdict_traces,
        "unresolved_reason_breakdown": dict(
            sorted(unresolved_reason_breakdown.items())
        ),
        "unresolved_disposition_breakdown": dict(
            sorted(unresolved_disposition_breakdown.items())
        ),
        "unresolved_groups": unresolved_groups,
        "conflict_review_groups": conflict_review_groups,
        "manual_reconstruction_previews": [
            plan["manual_reconstruction_preview"]
            for plan in plans
            if plan.get("manual_reconstruction_preview")
        ],
        "fallback_remediation_boundary": {
            "recommended": (
                "A_PER_RECORD_FALLBACK_REMOVAL_ONLY_AFTER_EXPLICIT_OWNER_DECISION"
            ),
            "option_a": (
                "NARROWEST; existing planner can clear the exact per-record field "
                "only when a reviewed REJECT_HISTORICAL_PRECOMPUTED_FALLBACK "
                "proposal matches current evidence"
            ),
            "option_b": (
                "NOT_IMPLEMENTED; would require governed per-record metadata and "
                "precedence semantics"
            ),
            "option_c": "NOT_AUTHORIZED_AND_NOT_PROPOSED",
            "global_fallback_impact_audit": (
                "NOT_RUN_BECAUSE_NO_GLOBAL_PRECEDENCE_CHANGE_IS_PROPOSED"
            ),
        },
        "safe_batch": safe_batch,
        "groups": plans,
        "repair_plan_sha256": repair_plan_sha256,
        "safety": {
            "dry_run_only": True,
            "canonical_sgf_mutated": False,
            "questions_json_mutated": False,
            "accepted_moves_mutated": False,
            "production_db_mutated": False,
            "player_verdict_mutated": False,
            "katago_run": "NONE",
            "identity_implemented": False,
        },
    }


def _human_action(plan: Mapping[str, Any]) -> str:
    if plan.get("classification") == CLASS_MANUAL:
        return "人工重建／題面或先後手證據審查"
    if plan.get("classification") == CLASS_UNRESOLVED:
        return "current corpus 找不到對應題目；不可套用"
    if plan.get("classification") == CLASS_STALE:
        return "stale/conflict；必須重新審題"
    if plan.get("classification") == CLASS_NO_OP:
        return "語意無變更"
    operations = {
        op.get("type")
        for record in plan.get("records") or []
        for op in record.get("planned_operations") or []
    }
    labels = []
    if "REWRITE_NATIVE_ROOT_ANSWER_SET" in operations:
        labels.append("重寫 native root answer set")
    if "CLEAR_PRECOMPUTED_KATAGO_FALLBACK" in operations:
        labels.append("清除歷史預先計算 fallback")
    return "；".join(labels) or "無"


def _fallback_summary(plan: Mapping[str, Any]) -> str:
    current = list(plan.get("current_precomputed_fallbacks") or [])
    desired = list(plan.get("desired_precomputed_fallbacks") or [])
    if not current and not desired:
        return "—"
    current_text = "、".join(current) or "—"
    desired_text = "、".join(desired) or "清除"
    if current == desired:
        return f"{current_text}（保留）"
    return f"{current_text} → {desired_text}"


def _render_phase1_report(manifest: Mapping[str, Any]) -> str:
    summary = manifest["summary"]
    q15436 = manifest["question_15436"]
    lines = [
        "# SGF-ANSWER-REPAIR-BATCH-001 — Phase 1 Dry Run",
        "",
        "Status: READY_FOR_OWNER_DRY_RUN_REVIEW",
        "",
        (
            "這是 Production staged proposals 的唯讀快照與隔離修正模擬。"
            "沒有任何 canonical SGF、questions.json、accepted moves、"
            "玩家判題或 Production DB 寫入。"
        ),
        "",
        "## Snapshot identity",
        "",
        (
            "- Proposal snapshot timestamp: "
            + str(manifest["inputs"]["proposal_snapshot_timestamp"])
        ),
        (
            "- Proposal snapshot SHA-256: "
            + str(manifest["inputs"]["proposal_snapshot_sha256"])
        ),
        (
            "- Reviewed questions snapshot SHA-256: "
            + str(manifest["inputs"]["reviewed_questions_sha256"])
        ),
        (
            "- Current target evidence SHA-256: "
            + str(manifest["inputs"]["current_targets_sha256"])
        ),
        (
            "- Current Production questions SHA-256: "
            + str(
                manifest["inputs"]["current_production_questions"][
                    "content_sha256"
                ]
            )
        ),
        (
            "- Current Production question count: "
            + str(
                manifest["inputs"]["current_production_questions"][
                    "record_count"
                ]
            )
        ),
        "- Repair plan SHA-256: "
        + str(manifest["repair_plan_sha256"]),
        "",
        "## Batch totals",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
    ]
    for label, key in (
        ("Active proposals", "active_proposals"),
        ("Active review groups", "active_review_groups"),
        ("Affected question records", "affected_question_records"),
        ("Auto applyable", "auto_applyable"),
        (
            "Manual reconstruction required",
            "manual_reconstruction_required",
        ),
        ("Stale or conflicted", "stale_or_conflicted"),
        ("Unresolved", "unresolved"),
        ("No-op", "no_op"),
        ("Duplicate groups", "duplicate_groups"),
        (
            "Multi-record repair groups",
            "multi_record_repair_groups",
        ),
        ("Duplicate fan-out records", "duplicate_fanout_records"),
        (
            "Duplicate group conflicts",
            "duplicate_group_conflicts",
        ),
        (
            "Planned canonical source references changed",
            "planned_canonical_files_changed",
        ),
        (
            "Planned question records changed",
            "planned_question_records_changed",
        ),
        (
            "Precomputed fallbacks cleared",
            "precomputed_fallbacks_cleared",
        ),
        (
            "Precomputed fallbacks preserved",
            "precomputed_fallbacks_preserved",
        ),
        (
            "Replacement/fallback conflicts",
            "replacement_fallback_conflicts",
        ),
    ):
        lines.append(f"| {label} | {summary[key]} |")
    lines.extend(
        [
            "",
            (
                "Classification totals are review-group counts. "
                "Planned question records include exact duplicate fan-out."
            ),
        ]
    )

    validation = manifest["validation"]
    lines.extend(
        [
            "",
            "## Isolated validation summary",
            "",
            "| Check | Result |",
            "| --- | --- |",
            (
                "| Isolated repaired records | "
                f"{validation['isolated_repair_records']} |"
            ),
            (
                "| SGF parse before/after | "
                f"{'PASS' if validation['sgf_parse_validation'] else 'FAIL'} |"
            ),
            (
                "| Native desired/removed move judging | "
                f"{'PASS' if validation['native_judging_validation'] else 'FAIL'} |"
            ),
            (
                "| Initial position/root/surviving variations | "
                f"{'PASS' if validation['position_and_variation_preservation'] else 'FAIL'} |"
            ),
            (
                "| Multi-answer repaired records | "
                f"{validation['multi_answer_record_count']} |"
            ),
            (
                "| Multi-answer exact-set validation | "
                f"{'PASS' if validation['multi_answer_validation'] else 'FAIL'} |"
            ),
            "",
            "### Fail-closed reason counts",
            "",
            "| Reason code | Groups |",
            "| --- | ---: |",
        ]
    )
    for reason_code, count in manifest["reason_code_counts"].items():
        lines.append(f"| `{reason_code}` | {count} |")

    lines.extend(
        [
            "",
            "## Question 15436 regression reference",
            "",
            f"- Present: {q15436['present']}",
            (
                "- Classification: "
                + str(q15436.get("classification"))
            ),
            "- Current: "
            + (", ".join(q15436.get("current") or []) or "—"),
            "- After repair: "
            + (", ".join(q15436.get("desired") or []) or "—"),
            "- Historical precomputed fallback: "
            + (
                "、".join(
                    q15436.get("current_precomputed_fallbacks") or []
                )
                or "—"
            ),
            "- Classification reasons: "
            + (
                ", ".join(q15436.get("reason_codes") or [])
                or "—"
            ),
            (
                "- Intended operation: remove A2 from the native answer set "
                "and preserve B1. This is replacement semantics, not add B1."
            ),
            "",
            "## Owner-friendly repair plan",
            "",
            (
                "| Question(s) | Current native | After native | "
                "Historical fallback | Classification | Action | Dry-run |"
            ),
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if (
        "UNREJECTED_PRECOMPUTED_FALLBACK_OUTSIDE_REPLACEMENT_SET"
        in (q15436.get("reason_codes") or [])
    ):
        insertion_index = lines.index("## Owner-friendly repair plan") - 1
        lines[insertion_index:insertion_index] = [
            "",
            (
                "Question 15436 is fail-closed: the native rewrite itself "
                "is valid, but current verdict logic would still accept Q4. "
                "A later apply batch needs an explicit Owner decision on that "
                "historical fallback; this dry run does not infer one."
            ),
        ]
    for plan in manifest["groups"]:
        ids = "、".join(
            str(value)
            for value in plan.get("legacy_question_ids") or []
        )
        current = "、".join(plan.get("current_answer_set") or []) or "—"
        desired = "、".join(plan.get("desired_answer_set") or []) or "—"
        dry_run = (
            "PASS"
            if plan["classification"] == CLASS_AUTO
            else (
                "N/A"
                if plan["classification"]
                in (CLASS_MANUAL, CLASS_UNRESOLVED)
                else "FAIL CLOSED"
            )
        )
        lines.append(
            f"| {ids} | {current} | {desired} | "
            f"{_fallback_summary(plan)} | "
            f"{plan['classification']} | {_human_action(plan)} | "
            f"{dry_run} |"
        )

    lines.extend(
        [
            "",
            "<details>",
            "<summary>Technical classification notes</summary>",
            "",
            (
                "- AUTO_APPLYABLE means only that an isolated copy parsed "
                "and matched the exact Owner-approved answer semantics. "
                "It is not permission to apply."
            ),
            (
                "- MANUAL_RECONSTRUCTION_REQUIRED covers side-to-move/"
                "source-position/reconstruction proposals where no "
                "deterministic authoring transformation is proven."
            ),
            (
                "- UNRESOLVED means the exact reviewed legacy record is "
                "absent from the current Production corpus. "
                "No ID/index guess was made."
            ),
            (
                "- Content fingerprints and legacy IDs are bounded locator "
                "evidence only; canonical identity remains deferred."
            ),
            (
                "- A replacement fails closed when a non-rejected historical "
                "precomputed fallback remains outside the desired answer set. "
                "That stored fallback still affects the current player verdict; "
                "the dry run never infers permission to clear it."
            ),
            (
                "- planned_canonical_files_changed counts unique source SGF "
                "references among applyable records; the current authoritative "
                "runtime representation remains the corresponding "
                "questions.json records."
            ),
            "",
            "</details>",
            "",
            "## Reproduction",
            "",
            "The committed proposal snapshot and the local-only current-target "
            "evidence are immutable inputs. The latter contains the minimum "
            "71 target SGFs needed for simulation and is intentionally not "
            "committed.",
            "",
            "```powershell",
            (
                "python tools\\sgf_answer_repair_batch.py "
                "--proposal-snapshot docs\\planning\\"
                "sgf_answer_repair_batch_001_proposal_snapshot.json "
                "--reviewed-questions D:\\go-website\\questions.json "
                "--current-targets D:\\go-website-sgf-answer-repair-batch-001-artifacts\\"
                "current_canonical_targets.json "
                "--manifest docs\\planning\\sgf_answer_repair_batch_001_manifest.json "
                "--report docs\\planning\\sgf_answer_repair_batch_001_dry_run.md "
                "--simulation-dir D:\\go-website-sgf-answer-repair-batch-001-artifacts\\"
                "isolated-repairs-final"
            ),
            "```",
            "",
            "Before any later apply phase, take a fresh current-source snapshot "
            "and require the same locator/content/source preconditions again. "
            "This report is not an apply authorization.",
            "",
            "## Safety assertions",
            "",
            "    CANONICAL_SGF_MUTATED=NO",
            "    QUESTIONS_JSON_MUTATED=NO",
            "    ACCEPTED_MOVES_MUTATED=NO",
            "    PRODUCTION_DB_MUTATED=NO",
            "    PLAYER_VERDICT_MUTATED=NO",
            "    KATAGO_RUN=NONE",
            "    IDENTITY_IMPLEMENTED=NO",
            "    DEPLOY=NO",
            "",
        ]
    )
    return "\n".join(lines)


def render_report(manifest: Mapping[str, Any]) -> str:
    summary = manifest["summary"]
    safe = manifest["safe_batch"]
    question = manifest["question_15436"]
    proof = question.get("mandatory_proof") or {}
    validation = manifest["validation"]
    lines = [
        "# SGF-ANSWER-REPAIR-BATCH-001 — Phase 1B End-to-End Verdict Safety",
        "",
        "Status: READY_FOR_OWNER_SAFE_BATCH_REVIEW",
        "",
        (
            "The native-only dry run was accepted as PASS_WITH_BLOCKER. This "
            "continuation checks the final effective first-move verdict across "
            "current player-facing paths. It is read-only and is not GO_APPLY."
        ),
        "",
        "## Snapshot identity",
        "",
        f"- Proposal snapshot timestamp: {manifest['inputs']['proposal_snapshot_timestamp']}",
        f"- Proposal snapshot SHA-256: `{manifest['inputs']['proposal_snapshot_sha256']}`",
        f"- Reviewed questions SHA-256: `{manifest['inputs']['reviewed_questions_sha256']}`",
        f"- Current target evidence SHA-256: `{manifest['inputs']['current_targets_sha256']}`",
        f"- Current Production questions SHA-256: `{manifest['inputs']['current_production_questions']['content_sha256']}`",
        f"- Current Production question count: {manifest['inputs']['current_production_questions']['record_count']}",
        f"- Repair plan SHA-256: `{manifest['repair_plan_sha256']}`",
        f"- Safe first batch SHA-256: `{safe['safe_batch_sha256']}`",
        "",
        "## End-to-end classification",
        "",
        "| Classification | Groups |",
        "| --- | ---: |",
        f"| `{CLASS_FULLY}` | {summary['fully_applyable_end_to_end']} |",
        f"| `{CLASS_FALLBACK_CONFLICT}` | {summary['native_repair_valid_but_fallback_conflict']} |",
        f"| `{CLASS_MANUAL}` | {summary['manual_reconstruction_required']} |",
        f"| `{CLASS_STALE}` | {summary['stale_or_conflicted']} |",
        f"| `{CLASS_UNRESOLVED}` | {summary['unresolved']} |",
        f"| `{CLASS_NO_OP}` | {summary['no_op']} |",
        "",
        (
            "Required invariant: `OWNER_DESIRED_VERDICT == "
            "SIMULATED_FINAL_EFFECTIVE_PLAYER_VERDICT`. Native SGF success "
            "alone no longer qualifies a group for the safe batch."
        ),
        "",
        "### Duplicate safety",
        "",
        f"- `DUPLICATE_GROUPS={summary['duplicate_groups']}`",
        f"- `MULTI_RECORD_REPAIR_GROUPS={summary['multi_record_repair_groups']}`",
        f"- `DUPLICATE_FANOUT_RECORDS={summary['duplicate_fanout_records']}`",
        f"- `DUPLICATE_GROUP_CONFLICTS={summary['duplicate_group_conflicts']}`",
        "",
        "## Validation",
        "",
        "| Check | Result |",
        "| --- | --- |",
        f"| SGF parse before/after | {'PASS' if validation['sgf_parse_validation'] else 'FAIL'} |",
        f"| Native judging | {'PASS' if validation['native_judging_validation'] else 'FAIL'} |",
        f"| Position/root/surviving variations | {'PASS' if validation['position_and_variation_preservation'] else 'FAIL'} |",
        f"| Multi-answer validation | {'PASS' if validation['multi_answer_validation'] else 'FAIL'} |",
        f"| Final effective judging simulation | {'PASS' if validation['final_effective_judging_simulation'] else 'FAIL'} |",
        "",
        "## Actual current verdict architecture",
        "",
        "- Main practice injects `accepted_moves` into the native SGF client tree. `/api/srs/review` records the resulting grade; it does not re-judge the move.",
        "- Daily Challenge judges in the client against the native SGF tree; the submit route trusts client `correct`.",
        "- Friend Challenge uses the main client verdict; the answer route trusts client `correct`.",
        "- Map Battle V1 checks server-side `accepted_moves`, then the native SGF tree; it does not use `katago_best_move`.",
        "- Rating Test uses `_rt_server_verify`: accepted moves, native legacy replay, then stored `katago_best_move`. Current `_build_rt_pool` omits accepted moves from pool records, so the effective current pool path is native legacy replay then stored fallback.",
        "- Shadow/candidate judging is observational and does not alter final verdicts.",
        "",
        "### Historical fallback traces",
        "",
    ]
    for question_id, trace in manifest["question_verdict_traces"].items():
        record = trace.get("end_to_end_record") or {}
        simulated = (record.get("simulated_final_verdict") or {}).get(
            "final_effective_player_verdict"
        ) or []
        lines.extend(
            [
                f"#### Question {question_id}",
                "",
                f"- `FALLBACK_SOURCE_FIELD={trace['fallback_source_field']}`",
                f"- `FALLBACK_STORAGE_LOCATION={trace['fallback_storage_location']}`",
                f"- `VERIFIED_OVERRIDE_EVIDENCE={trace['verified_override_evidence']}`",
                f"- `FALLBACK_PROVENANCE={trace['fallback_provenance']}`",
                f"- `FALLBACK_ACCEPTANCE_CONDITION={trace['fallback_acceptance_condition']}`",
                "- `FINAL_VERDICT_PATH=` " + " → ".join(trace["final_verdict_path"]),
                f"- Current native: {', '.join(trace['current_native_answers']) or '—'}",
                f"- Owner desired: {', '.join(trace['owner_desired_answers']) or '—'}",
                f"- Stored fallback: {', '.join(trace['stored_fallbacks']) or '—'}",
                f"- Simulated final effective verdict: {', '.join(simulated) or '—'}",
                f"- Classification: `{trace['classification']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Question 15436 mandatory proof",
            "",
            f"- Current native: {', '.join(question.get('current') or [])}",
            f"- Owner desired: {', '.join(question.get('desired') or [])}",
            f"- Stored fallback: {', '.join(question.get('current_precomputed_fallbacks') or [])}",
            f"- `B1={proof.get('B1')}`",
            f"- `A2={proof.get('A2')}`",
            f"- `Q4={proof.get('Q4')}`",
            "- `QUESTION_15436_FINAL_EFFECTIVE_VERDICT_SAFE="
            + ("YES" if proof.get("final_effective_verdict_safe") else "NO")
            + "`",
            f"- Classification: `{question.get('classification')}`",
            "",
            (
                "The native rewrite removes A2 and preserves B1, but Q4 remains "
                "accepted by Rating Test fallback. Question 15436 is excluded "
                "from the safe first batch."
            ),
            "",
            "## Safe first batch",
            "",
            f"- `SAFE_BATCH_GROUPS={safe['summary']['safe_batch_groups']}`",
            f"- `SAFE_BATCH_RECORDS={safe['summary']['safe_batch_records']}`",
            f"- `SAFE_BATCH_FILES={safe['summary']['safe_batch_files']}`",
            f"- `SAFE_BATCH_SHA256={safe['safe_batch_sha256']}`",
            "- Filter: `FULLY_APPLYABLE_END_TO_END` only.",
            "- Every safe record contains current effective, Owner desired, and simulated final verdict evidence with `MATCH=YES`.",
            "",
            "## Unresolved source breakdown",
            "",
            "### Reasons",
            "",
            "| Reason | Groups |",
            "| --- | ---: |",
        ]
    )
    for reason, count in manifest["unresolved_reason_breakdown"].items():
        lines.append(f"| `{reason}` | {count} |")
    lines.extend(
        [
            "",
            "### Dispositions",
            "",
            "| Disposition | Groups |",
            "| --- | ---: |",
        ]
    )
    for disposition, count in manifest[
        "unresolved_disposition_breakdown"
    ].items():
        lines.append(f"| `{disposition}` | {count} |")
    lines.extend(
        [
            "",
            "The manifest contains a machine-readable mapping for every unresolved group. All 47 reviewed IDs are absent from the exact current-corpus target inventory; the older review snapshot is retained as evidence and no mapping is guessed.",
            "",
            "## Five stale/conflict groups",
            "",
        ]
    )
    for conflict in manifest["conflict_review_groups"]:
        ids = ", ".join(
            str(value) for value in conflict["question_id_or_review_group"]
        )
        lines.extend(
            [
                f"### Question / review group {ids}",
                "",
                "- `OWNER_REVIEWED_CURRENT_STATE=` "
                + json.dumps(conflict["owner_reviewed_current_state"], ensure_ascii=False, sort_keys=True),
                "- `CURRENT_CANONICAL_STATE=` "
                + json.dumps(conflict["current_canonical_state"], ensure_ascii=False, sort_keys=True),
                "- `OWNER_DESIRED_STATE=` "
                + json.dumps(conflict["owner_desired_state"], ensure_ascii=False, sort_keys=True),
                "- `CONFLICT_REASON=` " + ", ".join(conflict["conflict_reason"]),
                "- `RECOMMENDED_DISPOSITION="
                + conflict["recommended_disposition"]
                + "`",
                "",
            ]
        )
    lines.extend(["## Manual reconstruction preview", ""])
    for preview in manifest["manual_reconstruction_previews"]:
        lines.extend(
            [
                f"### Question {preview['legacy_question_id']}",
                "",
                f"- Current source: `{preview['source_path']}`",
                f"- Current content SHA-256: `{preview['content_sha256']}`",
                f"- Board/setup: {preview['board_size']}x{preview['board_size']}; {preview['setup_stone_counts']}",
                f"- Side to move: `{preview['side_to_move']}`",
                f"- Current native answer(s): {', '.join(preview['current_native_answers']) or 'none'}",
                f"- Historical fallback evidence: `{preview['historical_precomputed_fallback'] or 'none'}`",
                "- Owner-reviewed intended answer: " + ", ".join(preview["owner_reviewed_intended_answer"]),
                "- Automatic reconstruction unsafe: " + ", ".join(preview["automatic_reconstruction_unsafe_because"]),
                "- Likely options: " + ", ".join(preview["likely_reconstruction_options"]),
                "- Exact Owner decision required: " + preview["exact_owner_decision_required"],
                "",
            ]
        )
    boundary = manifest["fallback_remediation_boundary"]
    lines.extend(
        [
            "## Fallback remediation boundary",
            "",
            f"- Recommended: `{boundary['recommended']}`",
            f"- Option A: {boundary['option_a']}",
            f"- Option B: {boundary['option_b']}",
            f"- Option C: `{boundary['option_c']}`",
            f"- Global impact audit: `{boundary['global_fallback_impact_audit']}`. No global precedence change is proposed, so corpus-wide changed-verdict counts were not inferred from the bounded 71-record target snapshot.",
            "",
            "## Reproduction",
            "",
            "```powershell",
            "python tools\\sgf_answer_repair_batch.py --proposal-snapshot docs\\planning\\sgf_answer_repair_batch_001_proposal_snapshot.json --reviewed-questions D:\\go-website\\questions.json --current-targets D:\\go-website-sgf-answer-repair-batch-001-artifacts\\current_canonical_targets.json --manifest docs\\planning\\sgf_answer_repair_batch_001_manifest.json --safe-batch docs\\planning\\sgf_answer_repair_batch_001_safe_batch.json --report docs\\planning\\sgf_answer_repair_batch_001_dry_run.md --simulation-dir D:\\go-website-sgf-answer-repair-batch-001-artifacts\\isolated-repairs-phase1b",
            "```",
            "",
            "Run the command twice against the same immutable inputs and require byte-identical manifests, reports, safe-batch artifacts, ordering, and hashes.",
            "",
            "## Safety assertions",
            "",
            "    GLOBAL_JUDGING_CHANGE_IMPLEMENTED=NO",
            "    CANONICAL_SGF_MUTATED=NO",
            "    QUESTIONS_JSON_MUTATED=NO",
            "    ACCEPTED_MOVES_MUTATED=NO",
            "    PRODUCTION_DB_MUTATED=NO",
            "    PLAYER_VERDICT_MUTATED=NO",
            "    KATAGO_RUN=NONE",
            "    IDENTITY_IMPLEMENTED=NO",
            "    MERGE=NO",
            "    DEPLOY=NO",
            "",
        ]
    )
    return "\n".join(lines)


def run(
    *,
    proposal_snapshot_path: Path,
    reviewed_questions_path: Path,
    current_targets_path: Path,
    manifest_path: Path,
    safe_batch_path: Path | None = None,
    report_path: Path,
    simulation_dir: Path | None,
) -> dict[str, Any]:
    if simulation_dir is not None:
        resolved_simulation_dir = simulation_dir.resolve()
        if (
            resolved_simulation_dir == _REPO_ROOT
            or _REPO_ROOT in resolved_simulation_dir.parents
        ):
            raise ValueError(
                "isolated SGF simulation directory must be outside the repository"
            )
    inputs = {
        proposal_snapshot_path.resolve(),
        reviewed_questions_path.resolve(),
        current_targets_path.resolve(),
    }
    output_paths = [manifest_path.resolve(), report_path.resolve()]
    if safe_batch_path is not None:
        output_paths.append(safe_batch_path.resolve())
    for output in output_paths:
        if output in inputs:
            raise ValueError(
                "output path must not overwrite an input snapshot"
            )
    proposal_snapshot, proposal_raw = _read_json(
        proposal_snapshot_path, maximum_bytes=_MAX_PROPOSAL_BYTES
    )
    reviewed_questions, questions_raw = _read_json(
        reviewed_questions_path, maximum_bytes=_MAX_QUESTIONS_BYTES
    )
    current_targets, targets_raw = _read_json(
        current_targets_path, maximum_bytes=_MAX_TARGET_BYTES
    )
    if not isinstance(reviewed_questions, list) or not all(
        isinstance(record, Mapping) for record in reviewed_questions
    ):
        raise ValueError(
            "reviewed questions snapshot must be a list of objects"
        )
    manifest = build_repair_plan(
        proposal_snapshot,
        reviewed_questions,
        current_targets,
        proposal_snapshot_sha256=_sha256(proposal_raw),
        reviewed_questions_sha256=_sha256(questions_raw),
        current_targets_sha256=_sha256(targets_raw),
        simulation_dir=simulation_dir,
    )
    manifest_bytes = _json_bytes(manifest)
    safe_batch_bytes = _json_bytes(manifest["safe_batch"])
    report_text = render_report(manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if safe_batch_path is not None:
        safe_batch_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(manifest_bytes)
    report_path.write_text(
        report_text, encoding="utf-8", newline="\n"
    )
    if safe_batch_path is not None:
        safe_batch_path.write_bytes(safe_batch_bytes)
    if proposal_snapshot_path.read_bytes() != proposal_raw:
        raise RuntimeError(
            "proposal snapshot changed during dry run"
        )
    if reviewed_questions_path.read_bytes() != questions_raw:
        raise RuntimeError(
            "reviewed questions snapshot changed during dry run"
        )
    if current_targets_path.read_bytes() != targets_raw:
        raise RuntimeError(
            "current target snapshot changed during dry run"
        )
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--proposal-snapshot", required=True, type=Path
    )
    parser.add_argument(
        "--reviewed-questions", required=True, type=Path
    )
    parser.add_argument("--current-targets", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--safe-batch", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--simulation-dir", type=Path)
    args = parser.parse_args(argv)
    manifest = run(
        proposal_snapshot_path=args.proposal_snapshot,
        reviewed_questions_path=args.reviewed_questions,
        current_targets_path=args.current_targets,
        manifest_path=args.manifest,
        safe_batch_path=args.safe_batch,
        report_path=args.report,
        simulation_dir=args.simulation_dir,
    )
    print(
        json.dumps(
            {
                "status": "READY_FOR_OWNER_SAFE_BATCH_REVIEW",
                "repair_plan_sha256": manifest[
                    "repair_plan_sha256"
                ],
                "summary": manifest["summary"],
                "safe_batch": manifest["safe_batch"]["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
