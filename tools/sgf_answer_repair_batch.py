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


SCHEMA_VERSION = "1.0"
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

CLASS_AUTO = "AUTO_APPLYABLE"
CLASS_MANUAL = "MANUAL_RECONSTRUCTION_REQUIRED"
CLASS_STALE = "STALE_OR_CONFLICTED"
CLASS_UNRESOLVED = "UNRESOLVED"
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
    if fallback_replacement_conflict:
        raise ValueError(
            "UNREJECTED_PRECOMPUTED_FALLBACK_OUTSIDE_REPLACEMENT_SET"
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
    }
    validation["passed"] = bool(
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
            if not record_plan["validation"]["passed"]:
                raise ValueError("isolated repair validation failed")
            simulated.append(record_plan)
            simulated_contents.append(simulated_content)
    except (ValueError, TypeError) as error:
        result["classification"] = CLASS_STALE
        result["reason_codes"] = [
            "SIMULATION_VALIDATION_FAILED",
            str(error),
        ]
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
            "classification": CLASS_AUTO,
            "reason_codes": [
                "ISOLATED_REPAIR_VALIDATION_PASSED"
            ],
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
            CLASS_AUTO,
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
    auto_duplicate_groups = [
        plan
        for plan in plans
        if plan["classification"] == CLASS_AUTO
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
        if plan["classification"] == CLASS_AUTO
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
                "plan": ([
                    operation
                    for record in plan.get("records") or []
                    for operation in record.get(
                        "planned_operations"
                    )
                    or []
                ] or list(plan.get("intended_operations") or [])),
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
        "auto_applyable": counts[CLASS_AUTO],
        "manual_reconstruction_required": counts[CLASS_MANUAL],
        "stale_or_conflicted": counts[CLASS_STALE],
        "unresolved": counts[CLASS_UNRESOLVED],
        "no_op": counts[CLASS_NO_OP],
        "duplicate_groups": len(active_duplicate_groups),
        "multi_record_repair_groups": len(auto_duplicate_groups),
        "duplicate_fanout_records": sum(
            int(plan["group_size"]) - 1
            for plan in auto_duplicate_groups
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


def render_report(manifest: Mapping[str, Any]) -> str:
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


def run(
    *,
    proposal_snapshot_path: Path,
    reviewed_questions_path: Path,
    current_targets_path: Path,
    manifest_path: Path,
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
    for output in (manifest_path.resolve(), report_path.resolve()):
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
    report_text = render_report(manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(manifest_bytes)
    report_path.write_text(
        report_text, encoding="utf-8", newline="\n"
    )
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
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--simulation-dir", type=Path)
    args = parser.parse_args(argv)
    manifest = run(
        proposal_snapshot_path=args.proposal_snapshot,
        reviewed_questions_path=args.reviewed_questions,
        current_targets_path=args.current_targets,
        manifest_path=args.manifest,
        report_path=args.report,
        simulation_dir=args.simulation_dir,
    )
    print(
        json.dumps(
            {
                "status": "READY_FOR_OWNER_DRY_RUN_REVIEW",
                "repair_plan_sha256": manifest[
                    "repair_plan_sha256"
                ],
                "summary": manifest["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
