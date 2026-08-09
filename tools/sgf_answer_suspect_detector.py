#!/usr/bin/env python3
"""Deterministic, read-only SGF answer suspect detector.

The detector ranks records for human inspection. It never declares an answer
wrong and never writes to the source corpus. Generated evidence contains only
snapshot-bound audit locators, coordinates, structural metrics, and reason
codes needed for Owner validation.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import html
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sgf_engine.core.coord_utils import sgf_to_xy
from sgf_engine.parser.sgf_parser import parse_sgf


DETECTOR_VERSION = "1.0.0"
OUTPUT_CLASSIFICATION = "OWNER_REVIEW_RECOMMENDED"
IDENTITY_TYPE = "AUDIT_LOCATOR_ONLY"
PLAYER_SIGNAL_UNAVAILABLE = "UNAVAILABLE_LOCAL"
PLAYER_SIGNAL_AVAILABLE = "AVAILABLE_AGGREGATE_INPUT"
SIDE_TO_MOVE_UNKNOWN_REASON = "SIDE_TO_MOVE_UNKNOWN"
SIDE_TO_MOVE_LABELS = {
    "B": "黑先 / Black to play",
    "W": "白先 / White to play",
    None: "先手不明 / Side to move unknown",
}

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
CONFIDENCE_BY_TIER = {"P0": "HIGH", "P1": "HIGH", "P2": "MEDIUM", "P3": "LOW"}

REASON_ORDER = (
    "PARSER_FAILURE",
    "EMPTY_SOLUTION_TREE",
    "NO_VALID_ROOT_ANSWER",
    "STRUCTURAL_SGF_ISSUE",
    "DUPLICATE_ROOT_MOVE_BRANCH",
    "NON_MOVE_ROOT_BRANCH",
    "AMBIGUOUS_OPPONENT_REPLY",
    "INVALID_PRECOMPUTED_MOVE",
    "HISTORICAL_ANSWER_CONFLICT",
    "HIGH_CONFIDENCE_GLOBAL_TENUKI_SUSPECT",
    "PLAYER_REPORTED",
    "REPEATED_REJECTED_MOVE",
    "REPEATED_SAME_ALTERNATIVE",
    "MULTIPLE_SOLUTION_REVIEW",
    "ABNORMAL_WRONG_RATE",
    "SHADOW_DISAGREEMENT",
    "PRECOMPUTED_KATAGO_ONLY_FALLBACK",
    "KATAGO_NATIVE_TREE_DISAGREEMENT",
    "HISTORICAL_KATAGO_NEEDS_REVIEW",
    "POSSIBLE_GLOBAL_TENUKI_SUSPECT",
    "ANSWER_PROVENANCE_UNKNOWN",
    "CALIBRATION_DEPENDENT",
)
REASON_RANK = {reason: index for index, reason in enumerate(REASON_ORDER)}

P0_REASONS = {
    "PARSER_FAILURE",
    "EMPTY_SOLUTION_TREE",
    "NO_VALID_ROOT_ANSWER",
    "INVALID_PRECOMPUTED_MOVE",
}

FALSE_POSITIVE_GUARDS = (
    "ko threats",
    "ladders",
    "outside liberties",
    "outside support",
    "long-range connections",
    "escape routes",
    "sente",
    "intentional tenuki",
    "whole-board tesuji",
    "positions that are not local tsumego",
)

GEOMETRY_THRESHOLDS = {
    "minimum_setup_stones": 4,
    "maximum_local_bbox_width": 10,
    "maximum_local_bbox_height": 10,
    "maximum_local_bbox_area_ratio": 0.30,
    "minimum_dominant_cluster_ratio": 0.80,
    "maximum_local_quadrant_count": 2,
    "minimum_dominant_quadrant_ratio": 0.70,
    "broad_bbox_area_ratio": 0.45,
    "broad_dimension_ratio": 0.75,
    "active_region_margin": 3,
    "possible_tenuki_minimum_distance": 6,
    "high_tenuki_minimum_distance": 8,
    "cluster_link_chebyshev_distance": 4,
    "continuation_depth_limit": 12,
}

_GTP_COLUMNS = "ABCDEFGHJKLMNOPQRST"
_SAFE_PLAYER_TOP_LEVEL_KEYS = {"schema_version", "snapshot_sha256", "records"}
_SAFE_PLAYER_RECORD_KEYS = {
    "record_index",
    "legacy_question_id",
    "content_sha256",
    "player_report_count",
    "distinct_reporter_count",
    "report_reason_counts",
    "rejected_moves",
    "attempt_count",
    "wrong_count",
    "wrong_rate",
    "shadow_disagreement_count",
    "high_skill_rejected_move_count",
    "calibration_dependent",
}
_SAFE_REJECTED_MOVE_KEYS = {"x", "y", "count"}


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(raw)


def _safe_short_text(value: Any, *, limit: int = 80) -> str | None:
    text = " ".join(str(value or "").split())
    if not text:
        return None
    return text[:limit]


def _side_to_move_evidence(root: Any, first_move_colors: set[str]) -> dict[str, Any]:
    """Return SGF-derived side-to-move evidence without board-shape inference.

    An explicit root PL property is authoritative. Without PL, a uniform color
    across the first solution branches is safe SGF evidence. Anything else is
    kept unknown rather than guessed.
    """

    explicit = root.metadata.get("player_to_move") if root is not None else None
    if explicit in {"B", "W"}:
        return {
            "side_to_move": explicit,
            "side_to_move_source": "SGF_ROOT_PL",
            "side_to_move_display": SIDE_TO_MOVE_LABELS[explicit],
            "side_to_move_reason_codes": [],
        }
    if len(first_move_colors) == 1:
        side = next(iter(first_move_colors))
        return {
            "side_to_move": side,
            "side_to_move_source": "SGF_FIRST_SOLUTION_COLOR",
            "side_to_move_display": SIDE_TO_MOVE_LABELS[side],
            "side_to_move_reason_codes": [],
        }
    return {
        "side_to_move": None,
        "side_to_move_source": None,
        "side_to_move_display": SIDE_TO_MOVE_LABELS[None],
        "side_to_move_reason_codes": [SIDE_TO_MOVE_UNKNOWN_REASON],
    }


def _read_questions_snapshot(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw = path.read_bytes()
    if len(raw) > 128 * 1024 * 1024:
        raise ValueError("questions snapshot exceeds the 128 MiB read-only detector bound")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("questions snapshot is not valid UTF-8 JSON") from error
    if not isinstance(value, list):
        raise ValueError("questions snapshot must contain a JSON list")
    if not (0 < len(value) <= 200_000):
        raise ValueError("questions snapshot record count is outside the detector bound")
    if any(not isinstance(record, dict) for record in value):
        raise ValueError("every questions snapshot record must be a JSON object")
    return value, {
        "sha256": _sha256_bytes(raw),
        "size_bytes": len(raw),
        "question_count": len(value),
    }


def _strict_nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"player evidence {field} must be a non-negative integer")
    return value


def _optional_rate(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("player evidence wrong_rate must be numeric")
    rate = float(value)
    if not (0.0 <= rate <= 1.0):
        raise ValueError("player evidence wrong_rate must be between 0 and 1")
    return rate


def load_player_evidence(
    path: Path | None,
    *,
    snapshot_sha256: str,
) -> tuple[dict[tuple[int, int, str], dict[str, Any]], dict[str, Any]]:
    """Load an optional PII-free aggregate evidence file.

    Exact record index, legacy ID, content hash, and snapshot hash are required.
    Unknown fields are rejected so raw notes, usernames, and reporter IDs cannot
    accidentally enter the detector evidence pack.
    """
    if path is None:
        return {}, {
            "status": PLAYER_SIGNAL_UNAVAILABLE,
            "record_count": 0,
            "input_sha256": None,
        }

    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("player evidence must be valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError("player evidence must be a JSON object")
    unknown_top = set(value) - _SAFE_PLAYER_TOP_LEVEL_KEYS
    if unknown_top:
        raise ValueError(f"player evidence contains unsupported top-level fields: {sorted(unknown_top)}")
    if value.get("snapshot_sha256") != snapshot_sha256:
        raise ValueError("player evidence snapshot_sha256 does not match the questions snapshot")
    records = value.get("records")
    if not isinstance(records, list):
        raise ValueError("player evidence records must be a JSON list")

    result: dict[tuple[int, int, str], dict[str, Any]] = {}
    for raw_record in records:
        if not isinstance(raw_record, dict):
            raise ValueError("player evidence record must be a JSON object")
        unknown = set(raw_record) - _SAFE_PLAYER_RECORD_KEYS
        if unknown:
            raise ValueError(f"player evidence contains unsupported record fields: {sorted(unknown)}")
        record_index = _strict_nonnegative_int(raw_record.get("record_index"), "record_index")
        legacy_id = raw_record.get("legacy_question_id")
        if isinstance(legacy_id, bool) or not isinstance(legacy_id, int):
            raise ValueError("player evidence legacy_question_id must be an integer")
        content_sha = str(raw_record.get("content_sha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", content_sha):
            raise ValueError("player evidence content_sha256 must be lowercase SHA-256")
        report_count = _strict_nonnegative_int(
            raw_record.get("player_report_count", 0), "player_report_count"
        )
        distinct_count = _strict_nonnegative_int(
            raw_record.get("distinct_reporter_count", 0), "distinct_reporter_count"
        )
        attempt_count = _strict_nonnegative_int(raw_record.get("attempt_count", 0), "attempt_count")
        wrong_count = _strict_nonnegative_int(raw_record.get("wrong_count", 0), "wrong_count")
        shadow_count = _strict_nonnegative_int(
            raw_record.get("shadow_disagreement_count", 0), "shadow_disagreement_count"
        )
        high_skill_count = _strict_nonnegative_int(
            raw_record.get("high_skill_rejected_move_count", 0),
            "high_skill_rejected_move_count",
        )
        reason_counts = raw_record.get("report_reason_counts") or {}
        if not isinstance(reason_counts, dict):
            raise ValueError("player evidence report_reason_counts must be an object")
        normalized_reasons: dict[str, int] = {}
        for reason, count in sorted(reason_counts.items()):
            if not re.fullmatch(r"[A-Z0-9_]{1,64}", str(reason)):
                raise ValueError("player evidence reason codes must be machine-readable uppercase tokens")
            normalized_reasons[str(reason)] = _strict_nonnegative_int(count, "report reason count")

        rejected_moves = raw_record.get("rejected_moves") or []
        if not isinstance(rejected_moves, list):
            raise ValueError("player evidence rejected_moves must be a list")
        normalized_moves = []
        for move in rejected_moves:
            if not isinstance(move, dict) or set(move) - _SAFE_REJECTED_MOVE_KEYS:
                raise ValueError("player evidence rejected move has unsupported fields")
            x = _strict_nonnegative_int(move.get("x"), "rejected move x")
            y = _strict_nonnegative_int(move.get("y"), "rejected move y")
            count = _strict_nonnegative_int(move.get("count"), "rejected move count")
            normalized_moves.append({"x": x, "y": y, "count": count})
        normalized_moves.sort(key=lambda item: (-item["count"], item["x"], item["y"]))

        key = (record_index, legacy_id, content_sha)
        if key in result:
            raise ValueError("player evidence contains a duplicate audit locator")
        result[key] = {
            "status": PLAYER_SIGNAL_AVAILABLE,
            "player_report_count": report_count,
            "distinct_reporter_count": distinct_count,
            "report_reason_counts": normalized_reasons,
            "rejected_moves": normalized_moves,
            "attempt_count": attempt_count,
            "wrong_count": wrong_count,
            "wrong_rate": _optional_rate(raw_record.get("wrong_rate")),
            "shadow_disagreement_count": shadow_count,
            "high_skill_rejected_move_count": high_skill_count,
            "calibration_dependent": bool(raw_record.get("calibration_dependent", False)),
        }

    return result, {
        "status": PLAYER_SIGNAL_AVAILABLE,
        "record_count": len(result),
        "input_sha256": _sha256_bytes(raw),
        "schema_version": str(value.get("schema_version") or "unspecified"),
    }


def gtp_to_xy(value: Any, board_size: int) -> tuple[int, int] | None:
    text = str(value or "").upper().strip()
    match = re.fullmatch(r"([A-HJ-T])(\d{1,2})", text)
    if not match or not (1 <= board_size <= len(_GTP_COLUMNS)):
        return None
    x = _GTP_COLUMNS.find(match.group(1))
    row = int(match.group(2))
    if not (0 <= x < board_size and 1 <= row <= board_size):
        return None
    return x, board_size - row


def xy_to_gtp(x: int, y: int, board_size: int) -> str | None:
    if not (1 <= board_size <= len(_GTP_COLUMNS) and 0 <= x < board_size and 0 <= y < board_size):
        return None
    return f"{_GTP_COLUMNS[x]}{board_size - y}"


def _move_packet(
    x: int,
    y: int,
    board_size: int,
    *,
    color: str | None = None,
    sgf: str | None = None,
) -> dict[str, Any]:
    packet: dict[str, Any] = {"x": x, "y": y, "gtp": xy_to_gtp(x, y, board_size)}
    if color:
        packet["color"] = color
    if sgf:
        packet["sgf"] = sgf
    return packet


def _board_size_hint(content: str) -> int:
    match = re.search(r"SZ\[(\d+)\]", content or "")
    if match:
        try:
            size = int(match.group(1))
            if 1 <= size <= 19:
                return size
        except ValueError:
            pass
    return 19


def _expand_sgf_points(values: Iterable[str], board_size: int) -> tuple[list[tuple[int, int]], int]:
    points: set[tuple[int, int]] = set()
    invalid = 0
    for value in values:
        try:
            if ":" in value:
                first, last = value.split(":", 1)
                x1, y1 = sgf_to_xy(first)
                x2, y2 = sgf_to_xy(last)
                if not all(0 <= coordinate < board_size for coordinate in (x1, y1, x2, y2)):
                    raise ValueError
                for x in range(min(x1, x2), max(x1, x2) + 1):
                    for y in range(min(y1, y2), max(y1, y2) + 1):
                        points.add((x, y))
            else:
                x, y = sgf_to_xy(value)
                if not (0 <= x < board_size and 0 <= y < board_size):
                    raise ValueError
                points.add((x, y))
        except (TypeError, ValueError):
            invalid += 1
    return sorted(points), invalid


def _initial_stones(root: Any, board_size: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    properties = root.metadata.get("properties") or {}
    black, invalid_black = _expand_sgf_points(properties.get("AB") or [], board_size)
    white, invalid_white = _expand_sgf_points(properties.get("AW") or [], board_size)
    empty, invalid_empty = _expand_sgf_points(properties.get("AE") or [], board_size)
    empty_set = set(empty)
    black_set = set(black) - empty_set
    white_set = set(white) - empty_set
    overlap = black_set & white_set
    stones = [
        {"x": x, "y": y, "color": color}
        for color, values in (("B", sorted(black_set)), ("W", sorted(white_set)))
        for x, y in values
    ]
    return stones, {
        "invalid_setup_coordinate_count": invalid_black + invalid_white + invalid_empty,
        "overlapping_setup_coordinate_count": len(overlap),
    }


def _quadrant(x: int, y: int, board_size: int) -> str:
    horizontal = "L" if x < board_size / 2 else "R"
    vertical = "T" if y < board_size / 2 else "B"
    return vertical + horizontal


def _largest_component_ratio(points: Sequence[tuple[int, int]]) -> float:
    if not points:
        return 0.0
    remaining = set(points)
    largest = 0
    max_link = GEOMETRY_THRESHOLDS["cluster_link_chebyshev_distance"]
    while remaining:
        seed = remaining.pop()
        component = {seed}
        stack = [seed]
        while stack:
            current = stack.pop()
            linked = {
                point
                for point in remaining
                if max(abs(point[0] - current[0]), abs(point[1] - current[1])) <= max_link
            }
            remaining.difference_update(linked)
            component.update(linked)
            stack.extend(linked)
        largest = max(largest, len(component))
    return largest / len(points)


def _within_region(point: tuple[int, int], region: Sequence[int] | None) -> bool:
    if region is None:
        return False
    x, y = point
    return region[0] <= x <= region[2] and region[1] <= y <= region[3]


def _continuation_points(node: Any, *, depth_limit: int) -> list[tuple[int, int]]:
    points: set[tuple[int, int]] = set()
    queue = [(child, 1) for child in node.children]
    while queue:
        current, depth = queue.pop(0)
        if current.move is not None and not current.move.is_pass and current.move.coord:
            try:
                points.add(sgf_to_xy(current.move.coord))
            except ValueError:
                pass
        if depth < depth_limit:
            queue.extend((child, depth + 1) for child in current.children)
    return sorted(points)


def _geometry_base(stones: Sequence[dict[str, Any]], board_size: int) -> dict[str, Any]:
    points = sorted({(stone["x"], stone["y"]) for stone in stones})
    metrics: dict[str, Any] = {
        "setup_stone_count": len(points),
        "appears_strongly_local": False,
        "broad_position_guard": True,
        "bbox": None,
        "expanded_active_region": None,
        "bbox_area_ratio": None,
        "dominant_cluster_ratio": None,
        "occupied_quadrant_count": 0,
        "dominant_quadrant": None,
        "dominant_quadrant_ratio": None,
    }
    if not points:
        return metrics
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    bbox = [min(xs), min(ys), max(xs), max(ys)]
    width = bbox[2] - bbox[0] + 1
    height = bbox[3] - bbox[1] + 1
    area_ratio = (width * height) / float(board_size * board_size)
    quadrants = collections.Counter(_quadrant(x, y, board_size) for x, y in points)
    dominant_quadrant, dominant_count = sorted(
        quadrants.items(), key=lambda item: (-item[1], item[0])
    )[0]
    dominant_ratio = dominant_count / len(points)
    cluster_ratio = _largest_component_ratio(points)
    broad = (
        area_ratio >= GEOMETRY_THRESHOLDS["broad_bbox_area_ratio"]
        or width / board_size >= GEOMETRY_THRESHOLDS["broad_dimension_ratio"]
        or height / board_size >= GEOMETRY_THRESHOLDS["broad_dimension_ratio"]
        or len(quadrants) >= 3
    )
    local = (
        len(points) >= GEOMETRY_THRESHOLDS["minimum_setup_stones"]
        and not broad
        and width <= GEOMETRY_THRESHOLDS["maximum_local_bbox_width"]
        and height <= GEOMETRY_THRESHOLDS["maximum_local_bbox_height"]
        and area_ratio <= GEOMETRY_THRESHOLDS["maximum_local_bbox_area_ratio"]
        and cluster_ratio >= GEOMETRY_THRESHOLDS["minimum_dominant_cluster_ratio"]
        and len(quadrants) <= GEOMETRY_THRESHOLDS["maximum_local_quadrant_count"]
        and dominant_ratio >= GEOMETRY_THRESHOLDS["minimum_dominant_quadrant_ratio"]
    )
    margin = GEOMETRY_THRESHOLDS["active_region_margin"]
    active = [
        max(0, bbox[0] - margin),
        max(0, bbox[1] - margin),
        min(board_size - 1, bbox[2] + margin),
        min(board_size - 1, bbox[3] + margin),
    ]
    metrics.update(
        {
            "appears_strongly_local": local,
            "broad_position_guard": broad,
            "bbox": bbox,
            "bbox_width": width,
            "bbox_height": height,
            "expanded_active_region": active,
            "bbox_area_ratio": round(area_ratio, 6),
            "dominant_cluster_ratio": round(cluster_ratio, 6),
            "occupied_quadrant_count": len(quadrants),
            "dominant_quadrant": dominant_quadrant,
            "dominant_quadrant_ratio": round(dominant_ratio, 6),
            "quadrant_setup_counts": dict(sorted(quadrants.items())),
        }
    )
    return metrics


def _candidate_geometry(
    point: tuple[int, int] | None,
    *,
    setup_points: Sequence[tuple[int, int]],
    board_size: int,
    base: Mapping[str, Any],
    continuation_points: Sequence[tuple[int, int]] = (),
) -> dict[str, Any] | None:
    if point is None:
        return None
    minimum_distance = (
        min(max(abs(point[0] - x), abs(point[1] - y)) for x, y in setup_points)
        if setup_points
        else None
    )
    region = base.get("expanded_active_region")
    candidate_quadrant = _quadrant(point[0], point[1], board_size)
    quadrant_counts = base.get("quadrant_setup_counts") or {}
    unrelated_sparse_quadrant = bool(
        base.get("dominant_quadrant")
        and candidate_quadrant != base.get("dominant_quadrant")
        and int(quadrant_counts.get(candidate_quadrant, 0)) == 0
    )
    continuation_interacts = any(_within_region(item, region) for item in continuation_points)
    outside = not _within_region(point, region)
    possible_far = bool(
        base.get("appears_strongly_local")
        and outside
        and minimum_distance is not None
        and minimum_distance >= GEOMETRY_THRESHOLDS["possible_tenuki_minimum_distance"]
    )
    high_far = bool(
        possible_far
        and minimum_distance >= GEOMETRY_THRESHOLDS["high_tenuki_minimum_distance"]
        and unrelated_sparse_quadrant
        and not continuation_interacts
    )
    return {
        "point": _move_packet(point[0], point[1], board_size),
        "outside_expanded_active_region": outside,
        "minimum_chebyshev_distance_to_setup": minimum_distance,
        "candidate_quadrant": candidate_quadrant,
        "unrelated_sparse_quadrant": unrelated_sparse_quadrant,
        "continuation_point_count": len(continuation_points),
        "continuation_interacts_with_active_region": continuation_interacts,
        "possible_far_signal": possible_far,
        "high_far_signal": high_far,
    }


def _normalized_accepted_moves(record: Mapping[str, Any], board_size: int) -> tuple[list[dict[str, Any]], int]:
    raw_moves = record.get("accepted_moves") or record.get("accepted_answers") or []
    if isinstance(raw_moves, dict):
        raw_moves = [raw_moves]
    if not isinstance(raw_moves, list):
        return [], 1
    result: list[dict[str, Any]] = []
    invalid = 0
    seen: set[tuple[int, int]] = set()
    for raw in raw_moves:
        if isinstance(raw, dict):
            x, y = raw.get("x"), raw.get("y")
        elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
            x, y = raw[0], raw[1]
        else:
            invalid += 1
            continue
        if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, int) or not isinstance(y, int):
            invalid += 1
            continue
        if not (0 <= x < board_size and 0 <= y < board_size):
            invalid += 1
            continue
        if (x, y) not in seen:
            result.append(_move_packet(x, y, board_size))
            seen.add((x, y))
    return result, invalid


def _historical_katago_metadata(record: Mapping[str, Any]) -> dict[str, Any]:
    status = _safe_short_text(record.get("katago_full_report_status"), limit=32)
    answer_source = _safe_short_text(record.get("answer_source"), limit=64)
    return {
        "present": any(
            record.get(key) not in (None, "", [], {})
            for key in (
                "katago_best_move",
                "katago_full_applied_at",
                "katago_auto_applied_at",
                "katago_full_report_status",
                "katago_auto_source",
            )
        ),
        "answer_source": answer_source,
        "report_status": status,
        "answer_conflict": bool(record.get("answer_conflict")) or status == "CONFLICT",
        "manual_verified": answer_source == "manual_verified",
    }


def _player_reasons(
    metrics: Mapping[str, Any],
    *,
    board_size: int,
    native_points: set[tuple[int, int]],
    native_root_count: int,
) -> list[str]:
    if metrics.get("status") != PLAYER_SIGNAL_AVAILABLE:
        return []
    reasons: list[str] = []
    if metrics.get("player_report_count", 0) > 0:
        reasons.append("PLAYER_REPORTED")
    repeated = [
        move
        for move in metrics.get("rejected_moves", [])
        if move.get("count", 0) >= 2
        and 0 <= move.get("x", -1) < board_size
        and 0 <= move.get("y", -1) < board_size
    ]
    if repeated:
        reasons.extend(("REPEATED_REJECTED_MOVE", "REPEATED_SAME_ALTERNATIVE"))
        if native_root_count == 1 and any((move["x"], move["y"]) not in native_points for move in repeated):
            reasons.append("MULTIPLE_SOLUTION_REVIEW")
    if (
        metrics.get("wrong_rate") is not None
        and metrics.get("attempt_count", 0) >= 20
        and metrics["wrong_rate"] >= 0.70
    ):
        reasons.append("ABNORMAL_WRONG_RATE")
    if metrics.get("shadow_disagreement_count", 0) > 0:
        reasons.append("SHADOW_DISAGREEMENT")
    if metrics.get("calibration_dependent") or metrics.get("high_skill_rejected_move_count", 0) > 0:
        reasons.append("CALIBRATION_DEPENDENT")
    return reasons


def _priority_tier(reasons: set[str]) -> str:
    if reasons & P0_REASONS:
        return "P0"
    katago_disagreement = bool(
        reasons & {"PRECOMPUTED_KATAGO_ONLY_FALLBACK", "KATAGO_NATIVE_TREE_DISAGREEMENT"}
    )
    player_cluster = "REPEATED_REJECTED_MOVE" in reasons
    high_tenuki = "HIGH_CONFIDENCE_GLOBAL_TENUKI_SUSPECT" in reasons
    historical_conflict = "HISTORICAL_ANSWER_CONFLICT" in reasons
    strong_groups = sum((katago_disagreement, player_cluster, high_tenuki, historical_conflict))
    if (
        ("MULTIPLE_SOLUTION_REVIEW" in reasons and player_cluster)
        or strong_groups >= 2
        or ("PLAYER_REPORTED" in reasons and (katago_disagreement or high_tenuki))
    ):
        return "P1"
    if (
        katago_disagreement
        or player_cluster
        or high_tenuki
        or historical_conflict
        or "HISTORICAL_KATAGO_NEEDS_REVIEW" in reasons
        or "ABNORMAL_WRONG_RATE" in reasons
        or "SHADOW_DISAGREEMENT" in reasons
        or "STRUCTURAL_SGF_ISSUE" in reasons
        or "AMBIGUOUS_OPPONENT_REPLY" in reasons
        or "DUPLICATE_ROOT_MOVE_BRANCH" in reasons
        or "NON_MOVE_ROOT_BRANCH" in reasons
    ):
        return "P2"
    return "P3"


def _sort_key(record: Mapping[str, Any]) -> tuple[Any, ...]:
    reasons = set(record["reason_codes"])
    structural_rank = min((REASON_RANK.get(reason, 999) for reason in reasons), default=999)
    strong_count = sum(
        (
            "HIGH_CONFIDENCE_GLOBAL_TENUKI_SUSPECT" in reasons,
            bool(reasons & {"PRECOMPUTED_KATAGO_ONLY_FALLBACK", "KATAGO_NATIVE_TREE_DISAGREEMENT"}),
            "HISTORICAL_ANSWER_CONFLICT" in reasons,
            "REPEATED_REJECTED_MOVE" in reasons,
            "PLAYER_REPORTED" in reasons,
            "SHADOW_DISAGREEMENT" in reasons,
        )
    )
    distance = 0
    spatial = record.get("spatial_metrics") or {}
    for key in ("native_first_solution", "stored_precomputed_move"):
        candidate = spatial.get(key) or {}
        distance = max(distance, candidate.get("minimum_chebyshev_distance_to_setup") or 0)
    return (
        PRIORITY_ORDER[record["priority_tier"]],
        structural_rank,
        -strong_count,
        -distance,
        record["audit_locator"]["record_index"],
        record["audit_locator"]["content_sha256"],
    )


def analyze_record(
    record: Mapping[str, Any],
    *,
    record_index: int,
    snapshot_sha256: str,
    player_metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    content = record.get("content")
    if not isinstance(content, str):
        content = ""
    content_sha = _sha256_bytes(content.encode("utf-8"))
    legacy_id = record.get("id")
    legacy_id_value = legacy_id if isinstance(legacy_id, int) and not isinstance(legacy_id, bool) else None
    locator = {
        "type": IDENTITY_TYPE,
        "snapshot_sha256": snapshot_sha256,
        "record_index": record_index,
        "legacy_question_id": legacy_id_value,
        "content_sha256": content_sha,
    }
    source_family = _safe_short_text(record.get("discipline") or record.get("topic_en"))
    board_size = _board_size_hint(content)
    reasons: set[str] = set()
    notes: list[str] = []
    structural_metrics: dict[str, Any] = {
        "parse_status": "failure",
        "parse_error_class": None,
        "parser_diagnostic_codes": [],
        "root_child_count": 0,
        "native_root_solution_count": 0,
        "root_pass_count": 0,
        "non_move_root_child_count": 0,
        "duplicate_root_coordinate_count": 0,
        "ambiguous_opponent_reply_count": 0,
        "invalid_setup_coordinate_count": 0,
        "overlapping_setup_coordinate_count": 0,
        "accepted_move_count": 0,
        "invalid_accepted_move_count": 0,
    }
    initial_stones: list[dict[str, Any]] = []
    native_packets: list[dict[str, Any]] = []
    native_nodes: list[Any] = []
    root = None
    side_to_move_evidence = _side_to_move_evidence(None, set())
    try:
        root = parse_sgf(content, strict=True)
        structural_metrics["parse_status"] = "success"
        diagnostics = root.metadata.get("diagnostics") or []
        structural_metrics["parser_diagnostic_codes"] = sorted(
            {str(item.get("code")) for item in diagnostics if isinstance(item, dict) and item.get("code")}
        )
        properties = root.metadata.get("properties") or {}
        try:
            board_size = int((properties.get("SZ") or [root.metadata.get("size") or 19])[0])
        except (TypeError, ValueError, IndexError):
            board_size = 19
        if not (1 <= board_size <= 19):
            raise ValueError("unsupported board size")
        initial_stones, setup_issues = _initial_stones(root, board_size)
        structural_metrics.update(setup_issues)
        if any(setup_issues.values()):
            reasons.add("STRUCTURAL_SGF_ISSUE")
        structural_metrics["root_child_count"] = len(root.children)
        seen_coords: set[tuple[int, int]] = set()
        root_colors: set[str] = set()
        first_move_colors: set[str] = set()
        for child in root.children:
            move = child.move
            if move is None:
                structural_metrics["non_move_root_child_count"] += 1
                continue
            first_move_colors.add(move.color)
            if move.is_pass or not move.coord:
                structural_metrics["root_pass_count"] += 1
                continue
            try:
                x, y = sgf_to_xy(move.coord)
            except ValueError:
                continue
            if not (0 <= x < board_size and 0 <= y < board_size):
                continue
            if (x, y) in seen_coords:
                structural_metrics["duplicate_root_coordinate_count"] += 1
            else:
                seen_coords.add((x, y))
                native_packets.append(
                    _move_packet(x, y, board_size, color=move.color, sgf=move.coord)
                )
                native_nodes.append(child)
            root_colors.add(move.color)
            opponent_children = [
                reply
                for reply in child.children
                if reply.move is not None and reply.move.color != move.color
            ]
            if len(opponent_children) > 1:
                structural_metrics["ambiguous_opponent_reply_count"] += 1
        side_to_move_evidence = _side_to_move_evidence(root, first_move_colors)
        structural_metrics["native_root_solution_count"] = len(native_packets)
        if not root.children:
            reasons.update(("EMPTY_SOLUTION_TREE", "NO_VALID_ROOT_ANSWER", "STRUCTURAL_SGF_ISSUE"))
        elif not native_packets:
            reasons.update(("NO_VALID_ROOT_ANSWER", "STRUCTURAL_SGF_ISSUE"))
        if (
            structural_metrics["non_move_root_child_count"]
            or structural_metrics["root_pass_count"]
            or structural_metrics["duplicate_root_coordinate_count"]
            or len(root_colors) > 1
        ):
            reasons.add("STRUCTURAL_SGF_ISSUE")
        if structural_metrics["non_move_root_child_count"]:
            reasons.add("NON_MOVE_ROOT_BRANCH")
        if structural_metrics["duplicate_root_coordinate_count"]:
            reasons.add("DUPLICATE_ROOT_MOVE_BRANCH")
        if structural_metrics["ambiguous_opponent_reply_count"]:
            reasons.update(("AMBIGUOUS_OPPONENT_REPLY", "STRUCTURAL_SGF_ISSUE"))
    except Exception as error:  # parser errors are normalized; raw SGF/error text is never emitted
        structural_metrics["parse_error_class"] = error.__class__.__name__
        reasons.update(("PARSER_FAILURE", "STRUCTURAL_SGF_ISSUE"))

    accepted_moves, invalid_accepted = _normalized_accepted_moves(record, board_size)
    structural_metrics["accepted_move_count"] = len(accepted_moves)
    structural_metrics["invalid_accepted_move_count"] = invalid_accepted
    if invalid_accepted:
        reasons.add("STRUCTURAL_SGF_ISSUE")

    native_points = {(move["x"], move["y"]) for move in native_packets}
    raw_katago = record.get("katago_best_move")
    katago_text = _safe_short_text(raw_katago, limit=16)
    katago_xy = gtp_to_xy(raw_katago, board_size) if katago_text else None
    katago_packet = (
        {"label": katago_text, **_move_packet(katago_xy[0], katago_xy[1], board_size)}
        if katago_xy is not None
        else ({"label": katago_text, "valid_coordinate": False} if katago_text else None)
    )
    historical = _historical_katago_metadata(record)
    if katago_text and katago_xy is None:
        reasons.update(("INVALID_PRECOMPUTED_MOVE", "STRUCTURAL_SGF_ISSUE"))
    if katago_xy is not None and katago_xy not in native_points:
        reasons.add("PRECOMPUTED_KATAGO_ONLY_FALLBACK")
        if native_points:
            reasons.add("KATAGO_NATIVE_TREE_DISAGREEMENT")
    if katago_text and not historical.get("answer_source"):
        reasons.add("ANSWER_PROVENANCE_UNKNOWN")
    if historical["answer_conflict"]:
        reasons.add("HISTORICAL_ANSWER_CONFLICT")
    if historical.get("report_status") == "NEEDS_REVIEW":
        reasons.add("HISTORICAL_KATAGO_NEEDS_REVIEW")

    setup_points = sorted({(stone["x"], stone["y"]) for stone in initial_stones})
    spatial = _geometry_base(initial_stones, board_size)
    native_first_xy = None
    native_continuation: list[tuple[int, int]] = []
    if native_packets:
        native_first_xy = (native_packets[0]["x"], native_packets[0]["y"])
        native_continuation = _continuation_points(
            native_nodes[0], depth_limit=GEOMETRY_THRESHOLDS["continuation_depth_limit"]
        )
    native_geometry = _candidate_geometry(
        native_first_xy,
        setup_points=setup_points,
        board_size=board_size,
        base=spatial,
        continuation_points=native_continuation,
    )
    katago_geometry = _candidate_geometry(
        katago_xy,
        setup_points=setup_points,
        board_size=board_size,
        base=spatial,
    )
    spatial["native_first_solution"] = native_geometry
    spatial["stored_precomputed_move"] = katago_geometry
    possible_geometry = bool(
        (native_geometry and native_geometry["possible_far_signal"])
        or (katago_geometry and katago_geometry["possible_far_signal"])
    )
    high_geometry = bool(
        (native_geometry and native_geometry["high_far_signal"] and historical["present"])
        or (
            katago_geometry
            and katago_geometry["high_far_signal"]
            and katago_xy not in native_points
        )
    )
    if high_geometry:
        reasons.add("HIGH_CONFIDENCE_GLOBAL_TENUKI_SUSPECT")
        notes.append("GEOMETRY_IS_SUSPECT_ONLY")
    elif possible_geometry:
        reasons.add("POSSIBLE_GLOBAL_TENUKI_SUSPECT")
        notes.append("GEOMETRY_IS_SUSPECT_ONLY")

    player = dict(player_metrics or {"status": PLAYER_SIGNAL_UNAVAILABLE})
    reasons.update(
        _player_reasons(
            player,
            board_size=board_size,
            native_points=native_points,
            native_root_count=len(native_packets),
        )
    )
    if "CALIBRATION_DEPENDENT" in reasons:
        notes.append("CALIBRATION_DEPENDENT_EVIDENCE_DOES_NOT_INCREASE_PRIORITY")

    ordered_reasons = sorted(reasons, key=lambda item: (REASON_RANK.get(item, 999), item))
    priority_tier = _priority_tier(reasons) if reasons else None
    return {
        "audit_locator": locator,
        "legacy_question_id": legacy_id_value,
        "source_family_if_known": source_family,
        "board_size": board_size,
        **side_to_move_evidence,
        "classification": OUTPUT_CLASSIFICATION if reasons else "NO_OBVIOUS_ISSUE",
        "priority_tier": priority_tier,
        "confidence": CONFIDENCE_BY_TIER.get(priority_tier),
        "reason_codes": ordered_reasons,
        "native_root_solution_count": len(native_packets),
        "current_first_solution_moves": native_packets,
        "stored_precomputed_move_if_any": katago_packet,
        "historical_katago_metadata": historical,
        "accepted_move_metadata": accepted_moves,
        "structural_metrics": structural_metrics,
        "spatial_metrics": spatial,
        "player_report_metrics_if_available": player,
        "shadow_candidate_evidence_if_available": {
            "status": player.get("status", PLAYER_SIGNAL_UNAVAILABLE),
            "shadow_disagreement_count": player.get("shadow_disagreement_count"),
        },
        "board_preview": {"initial_stones": initial_stones},
        "notes": sorted(set(notes)),
    }


def analyze_corpus(
    records: Sequence[Mapping[str, Any]],
    *,
    snapshot_sha256: str,
    player_evidence: Mapping[tuple[int, int, str], Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    evidence = player_evidence or {}
    analyzed = []
    for index, record in enumerate(records):
        content = record.get("content") if isinstance(record.get("content"), str) else ""
        content_sha = _sha256_bytes(content.encode("utf-8"))
        legacy_id = record.get("id")
        key = (index, legacy_id, content_sha)
        analyzed.append(
            analyze_record(
                record,
                record_index=index,
                snapshot_sha256=snapshot_sha256,
                player_metrics=evidence.get(key),
            )
        )
    return analyzed


def _reason_pair_counts(suspects: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: collections.Counter[str] = collections.Counter()
    for record in suspects:
        reasons = sorted(set(record["reason_codes"]))
        for first_index, first in enumerate(reasons):
            for second in reasons[first_index + 1 :]:
                counts[f"{first}+{second}"] += 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:30])


def build_summary(
    analyzed: Sequence[Mapping[str, Any]],
    *,
    snapshot: Mapping[str, Any],
    player_status: Mapping[str, Any],
    top_limit: int,
    selected_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    suspects = [record for record in analyzed if record["reason_codes"]]
    parse_success = sum(
        record["structural_metrics"]["parse_status"] == "success" for record in analyzed
    )
    root_distribution = collections.Counter()
    for record in analyzed:
        if record["structural_metrics"]["parse_status"] != "success":
            root_distribution["parser_failure"] += 1
        else:
            count = record["native_root_solution_count"]
            root_distribution["zero"] += count == 0
            root_distribution["one"] += count == 1
            root_distribution["multiple"] += count > 1
    reason_counts = collections.Counter(
        reason for record in suspects for reason in record["reason_codes"]
    )
    tier_counts = collections.Counter(record["priority_tier"] for record in suspects)
    selected_tiers = collections.Counter(record["priority_tier"] for record in selected_records)
    selected_reasons = collections.Counter(
        reason for record in selected_records for reason in record["reason_codes"]
    )
    structural_metric_counts = collections.Counter()
    for record in analyzed:
        metrics = record["structural_metrics"]
        for key in (
            "root_pass_count",
            "non_move_root_child_count",
            "duplicate_root_coordinate_count",
            "ambiguous_opponent_reply_count",
            "invalid_setup_coordinate_count",
            "overlapping_setup_coordinate_count",
            "invalid_accepted_move_count",
        ):
            if metrics.get(key, 0):
                structural_metric_counts[key] += 1
    historical_present = sum(record["historical_katago_metadata"]["present"] for record in analyzed)
    katago_move_present = sum(record["stored_precomputed_move_if_any"] is not None for record in analyzed)
    katago_valid = sum(
        bool(record["stored_precomputed_move_if_any"])
        and record["stored_precomputed_move_if_any"].get("valid_coordinate", True)
        for record in analyzed
    )
    accepted_present = sum(bool(record["accepted_move_metadata"]) for record in analyzed)
    side_to_move_counts = collections.Counter(
        record["side_to_move"] or "UNKNOWN" for record in analyzed
    )
    side_to_move_source_counts = collections.Counter(
        record["side_to_move_source"] or "UNKNOWN" for record in analyzed
    )
    return {
        "detector_version": DETECTOR_VERSION,
        "classification_boundary": "SUSPECT_NOT_WRONG",
        "source_snapshot": dict(snapshot),
        "player_signal_data": dict(player_status),
        "corpus": {
            "question_count": len(analyzed),
            "parse_success_count": parse_success,
            "parse_failure_count": len(analyzed) - parse_success,
            "answer_structure_distribution": dict(sorted(root_distribution.items())),
            "native_multi_root_answer_count": root_distribution["multiple"],
            "accepted_move_metadata_record_count": accepted_present,
            "historical_katago_metadata_record_count": historical_present,
            "stored_katago_move_record_count": katago_move_present,
            "valid_stored_katago_move_record_count": katago_valid,
            "structural_metric_record_counts": dict(sorted(structural_metric_counts.items())),
            "side_to_move_counts": {
                side: side_to_move_counts.get(side, 0) for side in ("B", "W", "UNKNOWN")
            },
            "side_to_move_source_counts": dict(sorted(side_to_move_source_counts.items())),
        },
        "suspects": {
            "total": len(suspects),
            "priority_tier_counts": {tier: tier_counts.get(tier, 0) for tier in PRIORITY_ORDER},
            "reason_code_counts": dict(sorted(reason_counts.items())),
            "top_validation_set_size": len(selected_records),
            "validation_set_priority_tier_counts": {
                tier: selected_tiers.get(tier, 0) for tier in PRIORITY_ORDER
            },
            "validation_set_reason_code_counts": dict(sorted(selected_reasons.items())),
            "validation_selection_policy": {
                "global_rank_prefix_ratio": 0.60,
                "minimum_tier_representation_ratios": {
                    "P1": 0.20,
                    "P2": 0.15,
                    "P3": 0.05,
                },
                "rule": "highest global ranks first, then highest not-yet-selected ranks from underrepresented tiers, then global-rank fill",
            },
            "top_reason_overlaps": _reason_pair_counts(suspects),
        },
        "geometry_thresholds": dict(GEOMETRY_THRESHOLDS),
        "geometry_false_positive_guards": list(FALSE_POSITIVE_GUARDS),
        "assertions": {
            "KATAGO_RUNTIME_IN_PRODUCTION": "NO",
            "PRECOMPUTED_KATAGO_DATA_AFFECTS_CURRENT_VERDICT": "YES",
            "OUTPUT_MEANS": OUTPUT_CLASSIFICATION,
            "CANONICAL_IDENTITY": "DEFERRED",
        },
    }


def rank_suspects(analyzed: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    suspects = [dict(record) for record in analyzed if record["reason_codes"]]
    suspects.sort(key=_sort_key)
    for rank, record in enumerate(suspects, 1):
        record["deterministic_rank"] = rank
    return suspects


def select_validation_set(
    ranked: Sequence[Mapping[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Preserve a global-rank prefix, then add deterministic tier coverage.

    Owner validation must test detector precision across structural, combined,
    single-strong, and exploratory categories. A pure prefix can be monopolized
    by one large tier, so 40% of the pack is reserved for minimum P1/P2/P3
    representation. Every selection remains the highest available global rank
    within its tier.
    """
    limit = min(limit, len(ranked))
    prefix_count = min(limit, math.floor(limit * 0.60))
    selected = [dict(record) for record in ranked[:prefix_count]]
    selected_keys = {
        (
            record["audit_locator"]["record_index"],
            record["audit_locator"]["content_sha256"],
        )
        for record in selected
    }
    targets = {
        "P1": math.floor(limit * 0.20),
        "P2": math.floor(limit * 0.15),
        "P3": math.floor(limit * 0.05),
    }
    counts = collections.Counter(record["priority_tier"] for record in selected)
    for tier in ("P1", "P2", "P3"):
        needed = max(0, targets[tier] - counts[tier])
        if not needed:
            continue
        for record in ranked:
            key = (
                record["audit_locator"]["record_index"],
                record["audit_locator"]["content_sha256"],
            )
            if record["priority_tier"] != tier or key in selected_keys:
                continue
            selected.append(dict(record))
            selected_keys.add(key)
            counts[tier] += 1
            needed -= 1
            if needed == 0 or len(selected) == limit:
                break
    if len(selected) < limit:
        for record in ranked:
            key = (
                record["audit_locator"]["record_index"],
                record["audit_locator"]["content_sha256"],
            )
            if key in selected_keys:
                continue
            selected.append(dict(record))
            selected_keys.add(key)
            if len(selected) == limit:
                break
    selected.sort(key=lambda record: record["deterministic_rank"])
    return selected


def _annotation_template(
    top_records: Sequence[Mapping[str, Any]],
    snapshot: Mapping[str, Any],
    validation_pack_id: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "authority": "OWNER_VALIDATION_ANNOTATION",
        "canonicality": "NON_AUTHORITATIVE",
        "snapshot_sha256": snapshot["sha256"],
        "validation_pack_id": validation_pack_id,
        "allowed_review_statuses": [
            "NO_ISSUE",
            "CONFIRMED_ISSUE",
            "POSSIBLE_MULTIPLE_SOLUTION",
            "UNCERTAIN",
        ],
        "confirmed_issue_reason_codes": [
            "GLOBAL_TENUKI",
            "WRONG_PRIMARY_ANSWER",
            "WRONG_CONTINUATION",
            "MISSING_EQUIVALENT_SOLUTION",
            "SIDE_TO_MOVE_OR_METADATA_ERROR",
            "SGF_OR_BOARD_STRUCTURE_ERROR",
            "OTHER",
        ],
        "instructions": "Edit a copy only. This file never changes canonical answers or verdicts.",
        "records": [
            {
                "audit_locator": record["audit_locator"],
                "legacy_question_id": record["legacy_question_id"],
                "side_to_move": record["side_to_move"],
                "priority_tier": record["priority_tier"],
                "detector_reason_codes": record["reason_codes"],
                "review_status": None,
                "issue_reason": None,
                "owner_note": "",
                "reviewed_at": None,
            }
            for record in top_records
        ],
    }


def _validation_pack_id(top_records: Sequence[Mapping[str, Any]]) -> str:
    identity = [
        {
            "deterministic_rank": record["deterministic_rank"],
            "record_index": record["audit_locator"]["record_index"],
            "content_sha256": record["audit_locator"]["content_sha256"],
        }
        for record in top_records
    ]
    return _sha256_bytes(_json_bytes(identity))


def _render_html(top_manifest: Mapping[str, Any]) -> bytes:
    payload = json.dumps(top_manifest, ensure_ascii=False, sort_keys=True).replace("<", "\\u003c")
    title = "SGF Answer Suspect Detector — Owner Validation Pack"
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, system-ui, sans-serif; background:#10141b; color:#e8edf5; }}
body {{ margin:0; }} header {{ position:sticky; top:0; z-index:2; background:#151b24ee; border-bottom:1px solid #334155; padding:14px 20px; }}
h1 {{ margin:0 0 6px; font-size:20px; }} .sub {{ color:#9fb0c5; font-size:13px; }}
.controls {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }} input,select {{ background:#0b1017; color:#e8edf5; border:1px solid #3b485a; border-radius:7px; padding:7px 9px; }}
main {{ padding:18px; display:grid; grid-template-columns:repeat(auto-fit,minmax(390px,1fr)); gap:14px; }}
.card {{ background:#171e29; border:1px solid #334155; border-radius:12px; padding:13px; scroll-margin-top:210px; }} .card h2 {{ margin:0 0 8px; font-size:16px; }}
 .meta {{ font-size:12px; color:#aebbd0; line-height:1.5; overflow-wrap:anywhere; }} .side-to-move {{ display:inline-block; margin-top:8px; border:1px solid #64748b; border-radius:999px; padding:5px 9px; font-size:12px; font-weight:800; letter-spacing:.01em; }} .side-B {{ background:#050505; color:#fff; }} .side-W {{ background:#f8fafc; color:#0f172a; }} .side-UNKNOWN {{ background:#513b12; color:#fde68a; border-color:#a16207; }} .reasons {{ display:flex; flex-wrap:wrap; gap:5px; margin:8px 0; }}
.reason {{ font:11px ui-monospace,monospace; background:#253248; border-radius:999px; padding:3px 7px; }} .P0 {{ border-left:5px solid #ef4444; }} .P1 {{ border-left:5px solid #f97316; }} .P2 {{ border-left:5px solid #eab308; }} .P3 {{ border-left:5px solid #38bdf8; }}
.board-row {{ display:flex; gap:12px; align-items:flex-start; flex-wrap:wrap; }} canvas {{ width:270px; height:270px; background:#d6a95f; border-radius:5px; }}
pre {{ margin:7px 0 0; white-space:pre-wrap; font:11px ui-monospace,monospace; color:#cbd5e1; max-width:330px; }}
.evidence {{ min-width:220px; max-width:330px; font-size:12px; line-height:1.55; color:#cbd5e1; }} .evidence b {{ color:#f8fafc; }} details {{ margin-top:9px; }} summary {{ cursor:pointer; color:#93c5fd; }}
.warning {{ color:#f8c879; }} .empty {{ padding:30px; color:#94a3b8; }}
.review-toolbar {{ position:sticky; top:108px; z-index:2; display:flex; align-items:center; gap:9px; flex-wrap:wrap; padding:10px 18px; background:#111827f2; border-bottom:1px solid #334155; }}
button {{ border:1px solid #475569; border-radius:8px; background:#1e293b; color:#f8fafc; padding:8px 11px; cursor:pointer; font-weight:700; }} button:hover {{ border-color:#93c5fd; }} button:focus-visible {{ outline:3px solid #38bdf8; outline-offset:2px; }}
.progress-count {{ font-weight:800; }} .review-toolbar .spacer {{ flex:1; }} .review-toolbar label {{ display:flex; gap:6px; align-items:center; font-size:13px; color:#cbd5e1; }}
.card.active-card {{ outline:3px solid #38bdf8; outline-offset:2px; }} .review-panel {{ margin-top:12px; padding-top:12px; border-top:1px solid #334155; }}
.review-statuses {{ display:grid; grid-template-columns:repeat(2,minmax(150px,1fr)); gap:8px; }} .review-status {{ min-height:54px; font-size:13px; line-height:1.25; }} .review-status.selected {{ background:#075985; border-color:#7dd3fc; box-shadow:0 0 0 2px #38bdf855 inset; }}
.issue-panel {{ margin-top:10px; padding:10px; border:1px solid #92400e; border-radius:9px; background:#2b1b0d; }} .issue-heading {{ margin-bottom:8px; color:#fed7aa; font-weight:800; }}
.issue-reasons {{ display:grid; grid-template-columns:repeat(2,minmax(160px,1fr)); gap:7px; }} .issue-reason {{ min-height:46px; font-size:12px; }} .issue-reason.selected {{ background:#9a3412; border-color:#fdba74; }}
.other-note {{ display:block; width:100%; box-sizing:border-box; min-height:62px; margin-top:9px; resize:vertical; background:#0b1017; color:#e8edf5; border:1px solid #64748b; border-radius:7px; padding:8px; }} .review-state {{ margin-top:8px; min-height:18px; font-size:12px; color:#93c5fd; }}
@media (max-width:620px) {{ .review-statuses,.issue-reasons {{ grid-template-columns:1fr; }} .review-toolbar {{ top:135px; }} }}
</style>
</head>
<body>
<header><h1>{html.escape(title)}</h1><div class="sub" id="summary"></div>
<div class="controls"><select id="tier"><option value="">All tiers</option><option>P0</option><option>P1</option><option>P2</option><option>P3</option></select>
<input id="search" size="38" placeholder="reason, legacy ID, record index"><span class="sub warning">Suspect only — never proof of a wrong answer. Canonical data remains read-only.</span></div></header>
<section class="review-toolbar" aria-label="Owner review navigation">
<button type="button" id="previous-record">← 上一題 / Previous</button><button type="button" id="next-record">下一題 / Next →</button>
<span class="progress-count" id="reviewed-count">Reviewed 0</span><span class="progress-count" id="unreviewed-count">Unreviewed 0</span>
<select id="review-filter" aria-label="Filter by review status"><option value="ALL">All review states</option><option value="UNREVIEWED">Unreviewed</option><option value="NO_ISSUE">NO_ISSUE</option><option value="CONFIRMED_ISSUE">CONFIRMED_ISSUE</option><option value="POSSIBLE_MULTIPLE_SOLUTION">POSSIBLE_MULTIPLE_SOLUTION</option><option value="UNCERTAIN">UNCERTAIN</option></select>
<label><input type="checkbox" id="auto-advance"> 完成後自動下一題 / Auto-advance</label><span class="spacer"></span>
<span class="sub">OWNER_VALIDATION_ANNOTATION · NON_AUTHORITATIVE · browser-local only</span><button type="button" id="export-reviews">匯出審查結果 / Export Review Results</button><span class="sub" id="export-status" aria-live="polite"></span>
</section>
<main id="cards"></main>
<script id="pack-data" type="application/json">{payload}</script>
<script>
const pack=JSON.parse(document.getElementById('pack-data').textContent), cards=document.getElementById('cards');
const tier=document.getElementById('tier'), search=document.getElementById('search');
const reviewFilter=document.getElementById('review-filter'),reviewedCount=document.getElementById('reviewed-count'),unreviewedCount=document.getElementById('unreviewed-count'),autoAdvance=document.getElementById('auto-advance');
const REVIEW_STATUS_DEFS=[
  {{code:'NO_ISSUE',label:'沒有問題 / No issue'}},
  {{code:'CONFIRMED_ISSUE',label:'確認有問題 / Confirmed issue'}},
  {{code:'POSSIBLE_MULTIPLE_SOLUTION',label:'可能有多個有效解 / Possible multiple solution'}},
  {{code:'UNCERTAIN',label:'不確定 / Uncertain'}}
];
const ISSUE_REASON_DEFS=[
  {{code:'GLOBAL_TENUKI',label:'全局脫先 / Global tenuki'}},
  {{code:'WRONG_PRIMARY_ANSWER',label:'主要答案錯誤 / Wrong primary answer'}},
  {{code:'WRONG_CONTINUATION',label:'後續變化錯誤 / Wrong continuation'}},
  {{code:'MISSING_EQUIVALENT_SOLUTION',label:'缺少等價解 / Missing equivalent solution'}},
  {{code:'SIDE_TO_MOVE_OR_METADATA_ERROR',label:'先手或 metadata 錯誤 / Side-to-move or metadata error'}},
  {{code:'SGF_OR_BOARD_STRUCTURE_ERROR',label:'SGF 或棋盤結構錯誤 / SGF or board structure error'}},
  {{code:'OTHER',label:'其他 / Other'}}
];
const storageKey=`sgf-answer-suspect-detector:owner-validation:${{pack.source_snapshot.sha256}}:${{pack.validation_pack_id}}`;
let reviewState=loadReviewState(),visibleRecords=[],activeRecordKey=null;
function recordKey(rec){{return `${{rec.audit_locator.record_index}}:${{rec.audit_locator.content_sha256}}`;}}
function freshReviewState(){{return {{schema_version:'1.0',authority:'OWNER_VALIDATION_ANNOTATION',canonicality:'NON_AUTHORITATIVE',snapshot_sha256:pack.source_snapshot.sha256,validation_pack_id:pack.validation_pack_id,records:{{}}}};}}
function loadReviewState(){{
  try{{
    const value=JSON.parse(localStorage.getItem(storageKey)||'null');
    if(value&&value.authority==='OWNER_VALIDATION_ANNOTATION'&&value.canonicality==='NON_AUTHORITATIVE'&&value.snapshot_sha256===pack.source_snapshot.sha256&&value.validation_pack_id===pack.validation_pack_id&&value.records&&typeof value.records==='object')return value;
  }}catch{{}}
  return freshReviewState();
}}
function saveReviewState(){{reviewState.updated_at=new Date().toISOString();localStorage.setItem(storageKey,JSON.stringify(reviewState));}}
function reviewComplete(entry){{return Boolean(entry&&entry.review_status&&(entry.review_status!=='CONFIRMED_ISSUE'||ISSUE_REASON_DEFS.some(def=>def.code===entry.issue_reason)));}}
function progressSnapshot(){{
  const complete=pack.records.map(rec=>reviewState.records[recordKey(rec)]).filter(reviewComplete);
  return {{reviewed:complete.length,unreviewed:pack.records.length-complete.length}};
}}
function updateProgress(){{const progress=progressSnapshot();reviewedCount.textContent=`Reviewed ${{progress.reviewed}}`;unreviewedCount.textContent=`Unreviewed ${{progress.unreviewed}}`;}}
function syncActiveCard(scroll=false){{
  for(const card of cards.querySelectorAll('.card'))card.classList.toggle('active-card',card.dataset.recordKey===activeRecordKey);
  const active=cards.querySelector(`.card[data-record-key="${{CSS.escape(activeRecordKey||'')}}"]`);if(scroll&&active)active.scrollIntoView({{behavior:'smooth',block:'start'}});
}}
function navigateRelative(delta){{
  if(!visibleRecords.length)return;
  let index=visibleRecords.findIndex(rec=>recordKey(rec)===activeRecordKey);if(index<0)index=0;
  index=Math.max(0,Math.min(visibleRecords.length-1,index+delta));activeRecordKey=recordKey(visibleRecords[index]);syncActiveCard(true);
}}
function finishAndMaybeAdvance(key){{
  render();
  const stillVisible=visibleRecords.some(rec=>recordKey(rec)===key);
  if(autoAdvance.checked&&stillVisible)navigateRelative(1);
}}
function setReviewStatus(rec,status){{
  if(!REVIEW_STATUS_DEFS.some(def=>def.code===status))return;
  const key=recordKey(rec),previous=reviewState.records[key]||{{}},same=previous.review_status===status;
  const entry={{review_status:status,issue_reason:null,owner_note:'',reviewed_at:null}};
  if(status==='CONFIRMED_ISSUE'&&same){{entry.issue_reason=previous.issue_reason||null;entry.owner_note=entry.issue_reason==='OTHER'?(previous.owner_note||''):'';}}
  if(status!=='CONFIRMED_ISSUE'||entry.issue_reason)entry.reviewed_at=new Date().toISOString();
  reviewState.records[key]=entry;activeRecordKey=key;saveReviewState();
  if(reviewComplete(entry))finishAndMaybeAdvance(key);else render();
}}
function setIssueReason(rec,reason){{
  if(!ISSUE_REASON_DEFS.some(def=>def.code===reason))return;
  const key=recordKey(rec),entry=reviewState.records[key];if(!entry||entry.review_status!=='CONFIRMED_ISSUE')return;
  entry.issue_reason=reason;entry.owner_note=reason==='OTHER'?(entry.owner_note||''):'';entry.reviewed_at=new Date().toISOString();activeRecordKey=key;saveReviewState();finishAndMaybeAdvance(key);
}}
function setOwnerNote(rec,note){{
  const entry=reviewState.records[recordKey(rec)];if(!entry||entry.review_status!=='CONFIRMED_ISSUE'||entry.issue_reason!=='OTHER')return;
  entry.owner_note=String(note).slice(0,500);entry.reviewed_at=new Date().toISOString();saveReviewState();updateProgress();
}}
function buildExportPayload(){{
  const reviewed=[];for(const rec of pack.records){{const entry=reviewState.records[recordKey(rec)];if(!reviewComplete(entry))continue;reviewed.push({{audit_locator:rec.audit_locator,legacy_question_id:rec.legacy_question_id,side_to_move:rec.side_to_move,priority_tier:rec.priority_tier,detector_reason_codes:rec.reason_codes,review_status:entry.review_status,issue_reason:entry.review_status==='CONFIRMED_ISSUE'?entry.issue_reason:null,owner_note:entry.issue_reason==='OTHER'?(entry.owner_note||''):'',reviewed_at:entry.reviewed_at}});}}
  const issueReasonCounts={{}};for(const row of reviewed)if(row.issue_reason)issueReasonCounts[row.issue_reason]=(issueReasonCounts[row.issue_reason]||0)+1;
  const count=status=>reviewed.filter(row=>row.review_status===status).length;
  return {{schema_version:'1.0',authority:'OWNER_VALIDATION_ANNOTATION',canonicality:'NON_AUTHORITATIVE',snapshot_sha256:pack.source_snapshot.sha256,validation_pack_id:pack.validation_pack_id,exported_at:new Date().toISOString(),summary:{{reviewed_total:reviewed.length,no_issue:count('NO_ISSUE'),confirmed_issue:count('CONFIRMED_ISSUE'),possible_multiple_solution:count('POSSIBLE_MULTIPLE_SOLUTION'),uncertain:count('UNCERTAIN'),issue_reason_counts:issueReasonCounts}},records:reviewed}};
}}
function downloadExport(){{const payload=buildExportPayload(),raw=JSON.stringify(payload,null,2)+'\\n',status=document.getElementById('export-status'),blob=new Blob([raw],{{type:'application/json'}}),url=URL.createObjectURL(blob),link=document.createElement('a');status.textContent=`Exported ${{payload.summary.reviewed_total}} reviewed record(s) as JSON`;status.dataset.lastExportSummary=JSON.stringify(payload.summary);status.dataset.lastExportFirstRecord=JSON.stringify(payload.records[0]||null);link.href=url;link.download=`sgf-owner-validation-${{pack.source_snapshot.sha256.slice(0,12)}}-${{pack.validation_pack_id.slice(0,12)}}.json`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),0);}}
document.getElementById('summary').textContent=`snapshot ${{pack.source_snapshot.sha256}} · ${{pack.records.length}} ranked suspects · detector ${{pack.detector_version}}`;
function el(tag,cls,text){{const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node;}}
function draw(canvas,rec){{const n=rec.board_size||19,ctx=canvas.getContext('2d'),s=540,p=26,step=(s-2*p)/(n-1);canvas.width=s;canvas.height=s;ctx.fillStyle='#d6a95f';ctx.fillRect(0,0,s,s);ctx.strokeStyle='#352915';ctx.lineWidth=1.3;for(let i=0;i<n;i++){{const q=p+i*step;ctx.beginPath();ctx.moveTo(p,q);ctx.lineTo(s-p,q);ctx.stroke();ctx.beginPath();ctx.moveTo(q,p);ctx.lineTo(q,s-p);ctx.stroke();}}for(const st of rec.board_preview.initial_stones||[]){{const x=p+st.x*step,y=p+st.y*step;ctx.beginPath();ctx.arc(x,y,step*.43,0,Math.PI*2);ctx.fillStyle=st.color==='B'?'#101010':'#f5f5f2';ctx.fill();ctx.strokeStyle='#111';ctx.stroke();}}(rec.current_first_solution_moves||[]).forEach((mv,i)=>{{const x=p+mv.x*step,y=p+mv.y*step;ctx.beginPath();ctx.arc(x,y,step*.28,0,Math.PI*2);ctx.strokeStyle='#16a34a';ctx.lineWidth=5;ctx.stroke();ctx.fillStyle='#052e16';ctx.font='bold 22px sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(String.fromCharCode(65+i),x,y);}});const k=rec.stored_precomputed_move_if_any;if(k&&Number.isInteger(k.x)){{const x=p+k.x*step,y=p+k.y*step;ctx.strokeStyle='#f97316';ctx.lineWidth=5;ctx.beginPath();ctx.moveTo(x-9,y-9);ctx.lineTo(x+9,y+9);ctx.moveTo(x+9,y-9);ctx.lineTo(x-9,y+9);ctx.stroke();}}}}
function makeReviewPanel(rec,entry){{
  const panel=el('div','review-panel'),heading=el('div','issue-heading','Owner validation · choose exactly one status');panel.append(heading);
  const statuses=el('div','review-statuses');for(const def of REVIEW_STATUS_DEFS){{const button=el('button','review-status'+(entry?.review_status===def.code?' selected':''),`${{def.label}}\n${{def.code}}`);button.type='button';button.dataset.reviewStatus=def.code;button.setAttribute('aria-pressed',String(entry?.review_status===def.code));button.addEventListener('click',event=>{{event.stopPropagation();setReviewStatus(rec,def.code);}});statuses.append(button);}}panel.append(statuses);
  if(entry?.review_status==='CONFIRMED_ISSUE'){{
    const issue=el('div','issue-panel'),issueHeading=el('div','issue-heading','確認問題原因 / Select one required issue reason');issue.append(issueHeading);
    const reasons=el('div','issue-reasons');for(const def of ISSUE_REASON_DEFS){{const button=el('button','issue-reason'+(entry.issue_reason===def.code?' selected':''),`${{def.label}}\n${{def.code}}`);button.type='button';button.dataset.issueReason=def.code;button.setAttribute('aria-pressed',String(entry.issue_reason===def.code));button.addEventListener('click',event=>{{event.stopPropagation();setIssueReason(rec,def.code);}});reasons.append(button);}}issue.append(reasons);
    if(entry.issue_reason==='OTHER'){{const note=document.createElement('textarea');note.className='other-note';note.placeholder='Optional note for OTHER only';note.value=entry.owner_note||'';note.maxLength=500;note.addEventListener('click',event=>event.stopPropagation());note.addEventListener('input',event=>setOwnerNote(rec,event.target.value));issue.append(note);}}
    panel.append(issue);
  }}
  const state=el('div','review-state');state.textContent=reviewComplete(entry)?`Complete · ${{entry.review_status}}${{entry.issue_reason?' · '+entry.issue_reason:''}}`:(entry?.review_status==='CONFIRMED_ISSUE'?'Reason required before this review is complete.':'Unreviewed');panel.append(state);return panel;
}}
function render(){{
  const needle=search.value.trim().toLowerCase(),wanted=tier.value,reviewWanted=reviewFilter.value;cards.replaceChildren();visibleRecords=[];let shown=0;
  for(const rec of pack.records){{
    const hay=(JSON.stringify(rec.reason_codes)+' '+rec.legacy_question_id+' '+rec.audit_locator.record_index).toLowerCase();
    const entry=reviewState.records[recordKey(rec)],complete=reviewComplete(entry);
    if(wanted&&rec.priority_tier!==wanted)continue;if(needle&&!hay.includes(needle))continue;if(reviewWanted==='UNREVIEWED'&&complete)continue;if(REVIEW_STATUS_DEFS.some(def=>def.code===reviewWanted)&&entry?.review_status!==reviewWanted)continue;shown++;visibleRecords.push(rec);
    const card=el('section','card '+rec.priority_tier),head=el('h2','',`#${{rec.deterministic_rank}} · ${{rec.priority_tier}} · legacy ${{rec.legacy_question_id??'null'}}`);card.append(head);
    card.dataset.recordKey=recordKey(rec);card.tabIndex=0;card.setAttribute('aria-label',`Suspect rank ${{rec.deterministic_rank}} review card`);card.addEventListener('click',()=>{{activeRecordKey=recordKey(rec);card.focus({{preventScroll:true}});syncActiveCard(false);}});
    card.append(el('div','meta',`record_index=${{rec.audit_locator.record_index}} · confidence=${{rec.confidence}} · roots=${{rec.native_root_solution_count}} · board=${{rec.board_size}}`));
     const sideState=rec.side_to_move||'UNKNOWN',sideText=rec.side_to_move_display||'先手不明 / Side to move unknown',side=el('div','side-to-move side-'+sideState,sideText);side.dataset.sideToMove=sideState;side.dataset.reasonCodes=(rec.side_to_move_reason_codes||[]).join(',');card.append(side);
     const reasons=el('div','reasons');for(const r of rec.reason_codes)reasons.append(el('span','reason',r));card.append(reasons);
    const row=el('div','board-row'),canvas=el('canvas');canvas.setAttribute('aria-label','Read-only Go board preview');row.append(canvas);
    const evidence=el('div','evidence'),answerLabels=(rec.current_first_solution_moves||[]).map(m=>m.gtp||`${{m.x}},${{m.y}}`).join(', ')||'none';
    const fallback=rec.stored_precomputed_move_if_any,spatial=rec.spatial_metrics||{{}},native=spatial.native_first_solution||{{}},stored=spatial.stored_precomputed_move||{{}};
    evidence.append(el('div','',`Root answer(s): ${{answerLabels}}`));
    evidence.append(el('div','',`Stored precomputed: ${{fallback?(fallback.label||fallback.gtp||'invalid'):'none'}}`));
    evidence.append(el('div','',`Local geometry: ${{spatial.appears_strongly_local?'yes':'no'}} · native distance=${{native.minimum_chebyshev_distance_to_setup??'n/a'}} · stored distance=${{stored.minimum_chebyshev_distance_to_setup??'n/a'}}`));
    evidence.append(el('div','',`Player evidence: ${{rec.player_report_metrics_if_available.status}}`));
    const disclosure=document.createElement('details'),label=document.createElement('summary');label.textContent='Evidence metrics';disclosure.append(label);
    disclosure.append(el('pre','',JSON.stringify({{structural:rec.structural_metrics,spatial:rec.spatial_metrics,historical:rec.historical_katago_metadata,player:rec.player_report_metrics_if_available}},null,2)));evidence.append(disclosure);
    row.append(evidence);card.append(row);card.append(makeReviewPanel(rec,entry));cards.append(card);draw(canvas,rec);
  }}
  if(!shown)cards.append(el('div','empty','No suspects match this filter.'));
  if(!visibleRecords.some(rec=>recordKey(rec)===activeRecordKey))activeRecordKey=visibleRecords.length?recordKey(visibleRecords[0]):null;syncActiveCard(false);updateProgress();
}}
function applyFilters(){{activeRecordKey=null;render();syncActiveCard(true);}}
tier.addEventListener('change',applyFilters);search.addEventListener('input',applyFilters);reviewFilter.addEventListener('change',applyFilters);
document.getElementById('previous-record').addEventListener('click',()=>navigateRelative(-1));document.getElementById('next-record').addEventListener('click',()=>navigateRelative(1));document.getElementById('export-reviews').addEventListener('click',downloadExport);
document.addEventListener('keydown',event=>{{
  if(['INPUT','TEXTAREA','SELECT','BUTTON'].includes(event.target.tagName)||event.target.isContentEditable)return;
  if(event.key==='ArrowLeft'){{event.preventDefault();navigateRelative(-1);return;}}if(event.key==='ArrowRight'){{event.preventDefault();navigateRelative(1);return;}}
  const status=REVIEW_STATUS_DEFS[Number(event.key)-1]?.code,rec=visibleRecords.find(item=>recordKey(item)===activeRecordKey);if(status&&rec){{event.preventDefault();setReviewStatus(rec,status);}}
}});
window.ownerReviewApi={{storageKey,getState:()=>JSON.parse(JSON.stringify(reviewState)),progress:progressSnapshot,exportPayload:buildExportPayload,getActiveKey:()=>activeRecordKey,getVisibleKeys:()=>visibleRecords.map(recordKey),setStatus:(key,status)=>{{const rec=pack.records.find(item=>recordKey(item)===key);if(rec)setReviewStatus(rec,status);}},setIssueReason:(key,reason)=>{{const rec=pack.records.find(item=>recordKey(item)===key);if(rec)setIssueReason(rec,reason);}}}};
render();
</script>
</body></html>"""
    return document.encode("utf-8")


def generate_outputs(
    *,
    questions_path: Path,
    output_dir: Path,
    top_limit: int = 300,
    player_evidence_path: Path | None = None,
) -> dict[str, Any]:
    if not (100 <= top_limit <= 500):
        raise ValueError("top validation set limit must be between 100 and 500")
    questions_path = questions_path.resolve()
    output_dir = output_dir.resolve()
    output_files = {
        "summary": output_dir / "corpus_summary.json",
        "manifest": output_dir / "top_suspects.json",
        "html": output_dir / "owner_validation_pack.html",
        "annotations": output_dir / "owner_review_annotations.template.json",
        "artifacts": output_dir / "artifact_manifest.json",
    }
    if questions_path in {path.resolve() for path in output_files.values()}:
        raise ValueError("output path must not overwrite the questions snapshot")

    records, snapshot = _read_questions_snapshot(questions_path)
    player_evidence, player_status = load_player_evidence(
        player_evidence_path.resolve() if player_evidence_path else None,
        snapshot_sha256=snapshot["sha256"],
    )
    analyzed = analyze_corpus(
        records,
        snapshot_sha256=snapshot["sha256"],
        player_evidence=player_evidence,
    )
    ranked = rank_suspects(analyzed)
    top = select_validation_set(ranked, limit=top_limit)
    summary = build_summary(
        analyzed,
        snapshot=snapshot,
        player_status=player_status,
        top_limit=top_limit,
        selected_records=top,
    )
    validation_pack_id = _validation_pack_id(top)
    top_manifest = {
        "detector_version": DETECTOR_VERSION,
        "validation_pack_id": validation_pack_id,
        "classification_boundary": "SUSPECT_NOT_WRONG",
        "output_classification": OUTPUT_CLASSIFICATION,
        "identity_boundary": IDENTITY_TYPE,
        "source_snapshot": snapshot,
        "player_signal_data": player_status,
        "geometry_false_positive_guards": list(FALSE_POSITIVE_GUARDS),
        "validation_selection_policy": summary["suspects"]["validation_selection_policy"],
        "records": top,
    }
    annotations = _annotation_template(top, snapshot, validation_pack_id)
    payloads = {
        output_files["summary"]: _json_bytes(summary),
        output_files["manifest"]: _json_bytes(top_manifest),
        output_files["html"]: _render_html(top_manifest),
        output_files["annotations"]: _json_bytes(annotations),
    }
    for path, raw in payloads.items():
        _write_bytes(path, raw)
    artifact_manifest = {
        "detector_version": DETECTOR_VERSION,
        "source_snapshot_sha256": snapshot["sha256"],
        "artifacts": {
            path.name: {"sha256": _sha256_bytes(raw), "size_bytes": len(raw)}
            for path, raw in sorted(payloads.items(), key=lambda item: item[0].name)
        },
    }
    _write_bytes(output_files["artifacts"], _json_bytes(artifact_manifest))

    # Re-hash after all writes. A changed source aborts instead of reporting success.
    final_raw = questions_path.read_bytes()
    if _sha256_bytes(final_raw) != snapshot["sha256"] or len(final_raw) != snapshot["size_bytes"]:
        raise RuntimeError("questions snapshot changed during detector execution")
    return {
        "summary": summary,
        "artifact_manifest": artifact_manifest,
        "output_dir": str(output_dir),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic read-only SGF answer suspect validation pack."
    )
    parser.add_argument("--questions", required=True, type=Path, help="Explicit questions.json snapshot")
    parser.add_argument("--output-dir", required=True, type=Path, help="Artifact output directory")
    parser.add_argument(
        "--top-limit",
        type=int,
        default=300,
        help="Owner validation set size, inclusive range 100-500 (default: 300)",
    )
    parser.add_argument(
        "--player-evidence",
        type=Path,
        help="Optional PII-free aggregate player evidence JSON bound to the same snapshot",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = generate_outputs(
        questions_path=args.questions,
        output_dir=args.output_dir,
        top_limit=args.top_limit,
        player_evidence_path=args.player_evidence,
    )
    summary = result["summary"]
    concise = {
        "detector_version": DETECTOR_VERSION,
        "source_snapshot_sha256": summary["source_snapshot"]["sha256"],
        "question_count": summary["corpus"]["question_count"],
        "suspect_count": summary["suspects"]["total"],
        "priority_tier_counts": summary["suspects"]["priority_tier_counts"],
        "top_validation_set_size": summary["suspects"]["top_validation_set_size"],
        "player_signal_data": summary["player_signal_data"]["status"],
        "output_dir": result["output_dir"],
    }
    print(json.dumps(concise, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
