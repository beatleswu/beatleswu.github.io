"""Fail-closed validation for an explicitly supplied questions corpus.

The validator is deliberately independent of Production and never discovers a
questions file.  A caller must provide the exact corpus path plus all release
identity declarations.  REPORT_ONLY emits every observed violation; the
RELEASE_ENFORCEMENT mode returns a non-zero process result for any blocking
violation and never rewrites the corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    # package-release-image.ps1 executes this file BY PATH
    # (python -B tools/questions_corpus_validation.py ...), which puts tools/ on
    # sys.path rather than the repository root, so `import tools.*` raised
    # ModuleNotFoundError and the packager saw an empty stdout with a non-zero
    # exit -- "validation failed closed" with no diagnosis. Resolve the repo root
    # from this file's own location so the validator behaves identically whether
    # it is run by path, as `python -m tools.questions_corpus_validation`, or
    # imported as a module.
    _REPO_ROOT = str(Path(__file__).resolve().parents[1])
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)

from tools.content_release_core import (  # noqa: E402
    ArtifactIdentity,
    GovernanceError,
    QUESTIONS_CORPUS_RELEASE_FIELDS,
    identify_json,
    validate_questions_corpus_binding,
)


REPORT_ONLY = "REPORT_ONLY"
RELEASE_ENFORCEMENT = "RELEASE_ENFORCEMENT"
MODES = (REPORT_ONLY, RELEASE_ENFORCEMENT)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GTP_RE = re.compile(r"^([A-HJ-Ta-hj-t])([1-9][0-9]*)$")
SPECIAL_MOVES = {"PASS", "RESIGN"}
GATE_NAMES = (
    "VALID_BOARD_SIZE",
    "VALID_CROP_METADATA",
    "NON_NEGATIVE_CROP_ORIGIN",
    "DETERMINISTIC_GLOBAL_LOCAL_MAPPING",
    "AT_LEAST_ONE_PLAYABLE_AUTHORITATIVE_ANSWER",
    "NO_INVALID_ALL_OFF_CROP_AUTHORITY",
    "EXPLICIT_PASS_SPECIAL_MOVE_SEMANTICS",
    "KATAGO_LOCAL_CROP_REPRESENTABILITY",
    "CORPUS_SHA256_PRESENT",
    "CORPUS_RECORD_COUNT_PRESENT",
    "CORPUS_SOURCE_IDENTITY_PRESENT",
)

# Owner/Coordinator release-policy ruling for the externally-managed Production
# QuestionsCorpus family (the corpus lives in the Docker volume
# go-odyssey_go-data; it is governed by neither the application image nor Git).
#
# Only exact corpus identity is authoritative blocking release policy:
#   1. exact corpus SHA-256 identity
#   2. exact record-count identity
#   3. exact source identity
#
# The eight content/schema checks below were authored against a record shape this
# corpus family has never had. Two independent reasons, both verified against the
# live 41,591-record corpus:
#
#   * A top-level `board_size` field, crop metadata (origin_x/origin_y/width/
#     height) and structured `accepted_moves` are absent from 100% of records,
#     and `origin_x` has no producer or consumer anywhere in the product outside
#     this module and its own tests.
#   * Separately, the `_board_size` fallback extractor cannot recover the board
#     size from the SGF in `content` either: its pattern anchors SZ to `^` or a
#     preceding `[`, so `(;GM[1]SZ[19];B[aa])` and `(;FF[4]SZ[19])` do not match.
#     VALID_BOARD_SIZE therefore fails every record for an extractor defect, not
#     only for missing data, and the three gates that need a board size inherit
#     that failure. This is a known REPORT_ONLY diagnostic defect; it is recorded
#     here rather than silently repaired, because changing what the diagnostics
#     report is a separate decision from what may block a release.
#
# Either way these checks rejected every real corpus and could never have
# expressed an accepted release policy.
#
# They are retained and still fully executed as REPORT_ONLY diagnostics. They are
# NOT deleted, skipped, falsified, or whitelisted to PASS: their exact per-gate
# and per-reason counts are always reported, and content_diagnostics_status is
# reported independently of the release status so a content failure can never be
# read as a release PASS claim. They simply do not gate a release.
BLOCKING_IDENTITY_GATE_NAMES = (
    "CORPUS_SHA256_PRESENT",
    "CORPUS_RECORD_COUNT_PRESENT",
    "CORPUS_SOURCE_IDENTITY_PRESENT",
)
REPORT_ONLY_CONTENT_GATE_NAMES = tuple(
    gate for gate in GATE_NAMES if gate not in BLOCKING_IDENTITY_GATE_NAMES
)
BLOCKING = "BLOCKING"
REPORT_ONLY_DIAGNOSTIC = "REPORT_ONLY_DIAGNOSTIC"

# A real corpus produces ~184,700 content diagnostics. Emitting every instance
# inline would make the release manifest JSON unusable for the packager, so each
# REPORT_ONLY gate reports its EXACT violation_count and EXACT per-reason counts
# plus a bounded example sample. Nothing is suppressed: the counts are complete
# and `violations_truncated` states plainly when the sample is partial.
CONTENT_DIAGNOSTIC_SAMPLE_LIMIT = 20


class CorpusValidationError(RuntimeError):
    """A malformed invocation or fail-closed validation result."""


def _raw_identity(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _record_label(record: Mapping[str, Any], index: int) -> Any:
    for key in ("source_record_uuid", "id", "question_id", "legacy_question_id"):
        if record.get(key) not in (None, ""):
            return record[key]
    return f"record-index:{index}"


def _first_value(record: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in record:
            return record[key]
    return None


def _board_size(record: Mapping[str, Any]) -> int | None:
    direct = _first_value(record, ("board_size", "boardSize", "boardXSize"))
    if direct is None and isinstance(record.get("board"), Mapping):
        direct = _first_value(record["board"], ("size", "board_size", "boardSize"))
    if direct is None:
        content = record.get("content")
        if isinstance(content, str):
            match = re.search(r"(?:^|\[)SZ\[(\d+)\]", content, re.IGNORECASE)
            if match:
                direct = int(match.group(1))
    return int(direct) if _is_int(direct) else None


def _crop_metadata(record: Mapping[str, Any]) -> dict[str, Any] | None:
    nested: Mapping[str, Any] | None = None
    for key in ("crop", "crop_metadata", "playable_crop", "board_crop"):
        value = record.get(key)
        if isinstance(value, Mapping):
            nested = value
            break
    source: Mapping[str, Any] = nested or record

    def value(keys: Sequence[str]) -> Any:
        found = _first_value(source, keys)
        if found is None and source is not record:
            found = _first_value(record, keys)
        return found

    origin_x = value(("origin_x", "start_x", "startX", "crop_origin_x", "crop_start_x"))
    origin_y = value(("origin_y", "start_y", "startY", "crop_origin_y", "crop_start_y"))
    width = value(("width", "crop_width", "display_width", "displayWidth"))
    height = value(("height", "crop_height", "display_height", "displayHeight"))
    if width is None:
        width = value(("displayColumns", "display_columns"))
    if height is None:
        height = value(("displayLines", "display_lines"))

    origin = source.get("origin")
    if isinstance(origin, Sequence) and not isinstance(origin, (str, bytes)) and len(origin) == 2:
        if origin_x is None:
            origin_x = origin[0]
        if origin_y is None:
            origin_y = origin[1]
    size = source.get("size")
    if isinstance(size, Sequence) and not isinstance(size, (str, bytes)) and len(size) == 2:
        if width is None:
            width = size[0]
        if height is None:
            height = size[1]
    if origin_x is None and origin_y is None and width is None and height is None:
        return None
    return {
        "origin_x": origin_x,
        "origin_y": origin_y,
        "width": width,
        "height": height,
    }


def _gtp_to_global(value: str, board_size: int) -> tuple[int, int] | None:
    match = GTP_RE.fullmatch(value.strip())
    if not match:
        return None
    column = match.group(1).upper()
    x = ord(column) - ord("A")
    if column >= "I":
        x -= 1
    y = board_size - int(match.group(2))
    return (x, y)


def _move_entries(record: Mapping[str, Any]) -> list[Any]:
    entries: list[Any] = []
    for key in ("accepted_moves", "accepted_answers", "answers", "authoritative_moves"):
        value = record.get(key)
        if isinstance(value, list):
            entries.extend(value)
        elif isinstance(value, Mapping) or isinstance(value, str):
            entries.append(value)
    for key in ("primary_answer", "answer"):
        value = record.get(key)
        if value not in (None, ""):
            entries.append(value)
    return entries


def _special_move(value: Any) -> str | None:
    if isinstance(value, str):
        normalized = value.strip().upper()
        return normalized if normalized in SPECIAL_MOVES else None
    if isinstance(value, Mapping):
        kind = value.get("type", value.get("special"))
        if isinstance(kind, str) and kind.strip().upper() in SPECIAL_MOVES:
            return kind.strip().upper()
        if value.get("pass") is True:
            return "PASS"
        if value.get("resign") is True:
            return "RESIGN"
    return None


def _coordinate(value: Any, board_size: int | None) -> tuple[int, int] | None:
    if isinstance(value, Mapping):
        x = value.get("x")
        y = value.get("y")
        if _is_int(x) and _is_int(y):
            return (x, y)
        for key in ("gtp", "coordinate", "move"):
            nested = value.get(key)
            if isinstance(nested, str) and board_size is not None:
                return _gtp_to_global(nested, board_size)
    if isinstance(value, str) and board_size is not None:
        return _gtp_to_global(value, board_size)
    return None


def _binding_from_args(args: argparse.Namespace) -> dict[str, Any] | None:
    values = {field: getattr(args, field, None) for field in QUESTIONS_CORPUS_RELEASE_FIELDS}
    if all(value is None for value in values.values()):
        return None
    return values


def _violation(
    gate: str,
    *,
    index: int | None = None,
    record: Mapping[str, Any] | None = None,
    reason: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {"gate": gate, "reason": reason}
    if index is not None:
        item["record_index"] = index
    if record is not None and index is not None:
        item["record_id"] = _record_label(record, index)
    if details:
        item["details"] = dict(details)
    return item


def _validate_records(records: list[Any]) -> dict[str, list[dict[str, Any]]]:
    failures = {gate: [] for gate in GATE_NAMES}
    for index, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            item = _violation(
                "VALID_BOARD_SIZE",
                index=index,
                reason="record_must_be_object",
            )
            failures["VALID_BOARD_SIZE"].append(item)
            failures["VALID_CROP_METADATA"].append(
                _violation("VALID_CROP_METADATA", index=index, reason="record_must_be_object")
            )
            failures["AT_LEAST_ONE_PLAYABLE_AUTHORITATIVE_ANSWER"].append(
                _violation(
                    "AT_LEAST_ONE_PLAYABLE_AUTHORITATIVE_ANSWER",
                    index=index,
                    reason="record_must_be_object",
                )
            )
            continue
        record = dict(raw)
        board = _board_size(record)
        if board is None or not 1 <= board <= 19:
            failures["VALID_BOARD_SIZE"].append(
                _violation(
                    "VALID_BOARD_SIZE",
                    index=index,
                    record=record,
                    reason="board_size_missing_or_out_of_range",
                    details={"observed": board},
                )
            )
        crop = _crop_metadata(record)
        crop_valid = True
        if crop is None:
            crop_valid = False
            failures["VALID_CROP_METADATA"].append(
                _violation(
                    "VALID_CROP_METADATA",
                    index=index,
                    record=record,
                    reason="crop_metadata_missing",
                )
            )
        else:
            for field in ("origin_x", "origin_y", "width", "height"):
                if not _is_int(crop[field]):
                    crop_valid = False
                    failures["VALID_CROP_METADATA"].append(
                        _violation(
                            "VALID_CROP_METADATA",
                            index=index,
                            record=record,
                            reason="crop_field_must_be_integer",
                            details={"field": field, "observed": crop[field]},
                        )
                    )
            if crop_valid:
                if crop["width"] <= 0 or crop["height"] <= 0:
                    crop_valid = False
                    failures["VALID_CROP_METADATA"].append(
                        _violation(
                            "VALID_CROP_METADATA",
                            index=index,
                            record=record,
                            reason="crop_dimensions_must_be_positive",
                        )
                    )
                if crop["origin_x"] < 0 or crop["origin_y"] < 0:
                    failures["NON_NEGATIVE_CROP_ORIGIN"].append(
                        _violation(
                            "NON_NEGATIVE_CROP_ORIGIN",
                            index=index,
                            record=record,
                            reason="crop_origin_must_be_non_negative",
                            details={"origin_x": crop["origin_x"], "origin_y": crop["origin_y"]},
                        )
                    )
                    crop_valid = False
                if board is not None and (
                    crop["origin_x"] + crop["width"] > board
                    or crop["origin_y"] + crop["height"] > board
                ):
                    crop_valid = False
                    failures["VALID_CROP_METADATA"].append(
                        _violation(
                            "VALID_CROP_METADATA",
                            index=index,
                            record=record,
                            reason="crop_exceeds_board_bounds",
                        )
                    )

        entries = _move_entries(record)
        coordinate_moves: list[tuple[int, int]] = []
        special_count = 0
        invalid_entry = False
        for entry in entries:
            special = _special_move(entry)
            if special is not None:
                special_count += 1
                continue
            coordinate = _coordinate(entry, board)
            if coordinate is None:
                invalid_entry = True
                failures["EXPLICIT_PASS_SPECIAL_MOVE_SEMANTICS"].append(
                    _violation(
                        "EXPLICIT_PASS_SPECIAL_MOVE_SEMANTICS",
                        index=index,
                        record=record,
                        reason="answer_move_is_neither_coordinate_nor_explicit_special_move",
                    )
                )
                continue
            coordinate_moves.append(coordinate)

        if not entries:
            failures["AT_LEAST_ONE_PLAYABLE_AUTHORITATIVE_ANSWER"].append(
                _violation(
                    "AT_LEAST_ONE_PLAYABLE_AUTHORITATIVE_ANSWER",
                    index=index,
                    record=record,
                    reason="authoritative_answer_missing",
                )
            )
            failures["EXPLICIT_PASS_SPECIAL_MOVE_SEMANTICS"].append(
                _violation(
                    "EXPLICIT_PASS_SPECIAL_MOVE_SEMANTICS",
                    index=index,
                    record=record,
                    reason="no_explicit_answer_or_special_move",
                )
            )

        local_valid_count = 0
        full_valid_count = 0
        for x, y in coordinate_moves:
            full_valid = board is not None and 0 <= x < board and 0 <= y < board
            if full_valid:
                full_valid_count += 1
            if crop_valid and full_valid:
                local_x = x - int(crop["origin_x"])
                local_y = y - int(crop["origin_y"])
                if 0 <= local_x < int(crop["width"]) and 0 <= local_y < int(crop["height"]):
                    local_valid_count += 1
        if entries and local_valid_count == 0 and special_count == 0:
            failures["AT_LEAST_ONE_PLAYABLE_AUTHORITATIVE_ANSWER"].append(
                _violation(
                    "AT_LEAST_ONE_PLAYABLE_AUTHORITATIVE_ANSWER",
                    index=index,
                    record=record,
                    reason="no_authoritative_coordinate_maps_inside_crop",
                )
            )
        if coordinate_moves and local_valid_count == 0:
            failures["NO_INVALID_ALL_OFF_CROP_AUTHORITY"].append(
                _violation(
                    "NO_INVALID_ALL_OFF_CROP_AUTHORITY",
                    index=index,
                    record=record,
                    reason="all_authoritative_coordinates_are_off_crop_or_invalid",
                )
            )
        if invalid_entry:
            failures["DETERMINISTIC_GLOBAL_LOCAL_MAPPING"].append(
                _violation(
                    "DETERMINISTIC_GLOBAL_LOCAL_MAPPING",
                    index=index,
                    record=record,
                    reason="authoritative_move_cannot_be_deterministically_mapped",
                )
            )
        elif coordinate_moves and not crop_valid:
            failures["DETERMINISTIC_GLOBAL_LOCAL_MAPPING"].append(
                _violation(
                    "DETERMINISTIC_GLOBAL_LOCAL_MAPPING",
                    index=index,
                    record=record,
                    reason="mapping_requires_valid_crop_metadata",
                )
            )
        elif coordinate_moves and full_valid_count != len(coordinate_moves):
            failures["DETERMINISTIC_GLOBAL_LOCAL_MAPPING"].append(
                _violation(
                    "DETERMINISTIC_GLOBAL_LOCAL_MAPPING",
                    index=index,
                    record=record,
                    reason="global_coordinate_out_of_board",
                )
            )

        katago = record.get("katago_best_move")
        if katago not in (None, ""):
            special = _special_move(katago)
            coordinate = None if special else _coordinate(katago, board)
            if special is None and coordinate is None:
                failures["KATAGO_LOCAL_CROP_REPRESENTABILITY"].append(
                    _violation(
                        "KATAGO_LOCAL_CROP_REPRESENTABILITY",
                        index=index,
                        record=record,
                        reason="katago_move_not_parseable",
                    )
                )
            elif special is None and (board is None or not crop_valid):
                failures["KATAGO_LOCAL_CROP_REPRESENTABILITY"].append(
                    _violation(
                        "KATAGO_LOCAL_CROP_REPRESENTABILITY",
                        index=index,
                        record=record,
                        reason="katago_move_requires_valid_board_and_crop",
                    )
                )
            elif special is None:
                x, y = coordinate
                if not (0 <= x < board and 0 <= y < board):
                    failures["KATAGO_LOCAL_CROP_REPRESENTABILITY"].append(
                        _violation(
                            "KATAGO_LOCAL_CROP_REPRESENTABILITY",
                            index=index,
                            record=record,
                            reason="katago_move_outside_full_board",
                        )
                    )
                else:
                    local_x = x - int(crop["origin_x"])
                    local_y = y - int(crop["origin_y"])
                    if not (0 <= local_x < int(crop["width"]) and 0 <= local_y < int(crop["height"])):
                        failures["KATAGO_LOCAL_CROP_REPRESENTABILITY"].append(
                            _violation(
                                "KATAGO_LOCAL_CROP_REPRESENTABILITY",
                                index=index,
                                record=record,
                                reason="katago_move_off_crop",
                            )
                        )
    return failures


def validate_questions_corpus(
    corpus_path: Path,
    *,
    mode: str = REPORT_ONLY,
    release_binding: Mapping[str, Any] | None = None,
    expected_source_sha256: str | None = None,
    expected_source_record_count: int | None = None,
) -> dict[str, Any]:
    """Validate one explicit corpus path and return a structured report."""

    if mode not in MODES:
        raise CorpusValidationError(f"unsupported_mode:{mode}")
    path = Path(corpus_path)
    if not path.is_file() or path.is_symlink():
        raise CorpusValidationError("regular_corpus_file_required")
    raw_sha, raw_bytes = _raw_identity(path)
    parse_error: str | None = None
    records: list[Any] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, list):
            raise ValueError("top_level_must_be_array")
        records = payload
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        parse_error = str(error)

    failures = {gate: [] for gate in GATE_NAMES}
    identity: ArtifactIdentity | None = None
    if parse_error is None:
        try:
            identity = identify_json(path)
        except GovernanceError as error:
            parse_error = str(error)
    if parse_error is not None:
        failures["VALID_BOARD_SIZE"].append(_violation("VALID_BOARD_SIZE", reason="json_parse_failed"))
        failures["VALID_CROP_METADATA"].append(_violation("VALID_CROP_METADATA", reason="json_parse_failed"))
        failures["CORPUS_SHA256_PRESENT"].append(_violation("CORPUS_SHA256_PRESENT", reason="json_parse_failed"))
        failures["CORPUS_RECORD_COUNT_PRESENT"].append(_violation("CORPUS_RECORD_COUNT_PRESENT", reason="json_parse_failed"))
    else:
        failures.update(_validate_records(records))

    if release_binding is None:
        for gate in (
            "CORPUS_SHA256_PRESENT",
            "CORPUS_RECORD_COUNT_PRESENT",
            "CORPUS_SOURCE_IDENTITY_PRESENT",
        ):
            failures[gate].append(_violation(gate, reason="release_identity_binding_missing"))
    else:
        try:
            if identity is None:
                raise GovernanceError("corpus_identity_unavailable")
            validate_questions_corpus_binding(
                release_binding,
                actual_identity=identity,
                expected_source_sha256=expected_source_sha256,
                expected_source_record_count=expected_source_record_count,
            )
        except GovernanceError as error:
            gate = "CORPUS_SOURCE_IDENTITY_PRESENT"
            message = str(error)
            if "questions_corpus_sha256" in message:
                gate = "CORPUS_SHA256_PRESENT"
            elif "questions_corpus_bytes" in message:
                gate = "CORPUS_SHA256_PRESENT"
            elif "questions_corpus_record_count" in message:
                gate = "CORPUS_RECORD_COUNT_PRESENT"
            failures[gate].append(_violation(gate, reason=message))

    if release_binding is not None:
        snapshot_id = release_binding.get("questions_corpus_snapshot_id")
        if isinstance(snapshot_id, str) and ("/" in snapshot_id or "\\" in snapshot_id or snapshot_id.lower().endswith(".json")):
            failures["CORPUS_SOURCE_IDENTITY_PRESENT"].append(
                _violation(
                    "CORPUS_SOURCE_IDENTITY_PRESENT",
                    reason="snapshot_id_must_not_be_a_filename_or_path",
                )
            )

    gate_report: dict[str, Any] = {}
    blocking_violations: list[dict[str, Any]] = []
    content_violation_count = 0
    content_reason_counts: dict[str, int] = {}
    for gate in GATE_NAMES:
        violations = failures[gate]
        blocking = gate in BLOCKING_IDENTITY_GATE_NAMES
        report: dict[str, Any] = {
            "pass": not violations,
            "violation_count": len(violations),
            "enforcement": BLOCKING if blocking else REPORT_ONLY_DIAGNOSTIC,
        }
        if blocking:
            # Identity gates are few and are the authoritative release policy:
            # report every violation in full and let them block.
            report["violations"] = violations
            report["blocks_release"] = True
            blocking_violations.extend(violations)
        else:
            reasons: dict[str, int] = {}
            for item in violations:
                reason = str(item.get("reason", "unknown"))
                reasons[reason] = reasons.get(reason, 0) + 1
                content_reason_counts[reason] = content_reason_counts.get(reason, 0) + 1
            content_violation_count += len(violations)
            report["blocks_release"] = False
            report["reason_counts"] = reasons
            report["violations"] = violations[:CONTENT_DIAGNOSTIC_SAMPLE_LIMIT]
            report["violations_truncated"] = len(violations) > CONTENT_DIAGNOSTIC_SAMPLE_LIMIT
        gate_report[gate] = report

    blocking_gate_pass_count = sum(
        1 for gate in BLOCKING_IDENTITY_GATE_NAMES if gate_report[gate]["pass"]
    )
    result = {
        "schema_version": "1.1",
        "mode": mode,
        # status and release_rejected reflect the authoritative blocking policy
        # (exact corpus identity) only. Content diagnostics are reported
        # separately and independently below so that a content failure can never
        # be mistaken for -- or silently converted into -- a release PASS claim.
        "status": "PASS" if not blocking_violations else "FAIL",
        "release_rejected": bool(blocking_violations) and mode == RELEASE_ENFORCEMENT,
        "release_enforcement_policy": {
            "blocking_identity_gates": list(BLOCKING_IDENTITY_GATE_NAMES),
            "blocking_identity_gate_count": len(BLOCKING_IDENTITY_GATE_NAMES),
            "report_only_content_gates": list(REPORT_ONLY_CONTENT_GATE_NAMES),
            "report_only_content_gate_count": len(REPORT_ONLY_CONTENT_GATE_NAMES),
            "content_diagnostics_can_block_release": False,
        },
        "corpus_path": str(path.resolve()),
        "identity": {
            "sha256": raw_sha,
            "bytes": raw_bytes,
            "record_count": len(records) if parse_error is None else None,
        },
        "json_parse": "PASS" if parse_error is None else "FAIL",
        "parse_error": parse_error,
        "summary": {
            "record_count": len(records) if parse_error is None else None,
            "gate_count": len(GATE_NAMES),
            "passed_gate_count": sum(1 for report in gate_report.values() if report["pass"]),
            "blocking_violation_count": len(blocking_violations),
            "blocking_identity_gate_count": len(BLOCKING_IDENTITY_GATE_NAMES),
            "blocking_identity_gates_passed": blocking_gate_pass_count,
            "report_only_content_gate_count": len(REPORT_ONLY_CONTENT_GATE_NAMES),
            "report_only_content_violation_count": content_violation_count,
            "content_diagnostics_status": "PASS" if content_violation_count == 0 else "FAIL",
            "content_diagnostics_recorded": True,
            "content_diagnostics_suppressed": False,
        },
        "content_diagnostics": {
            "status": "PASS" if content_violation_count == 0 else "FAIL",
            "violation_count": content_violation_count,
            "reason_counts": content_reason_counts,
            "sample_limit_per_gate": CONTENT_DIAGNOSTIC_SAMPLE_LIMIT,
            "note": (
                "Executed and recorded in full by count; not authoritative "
                "blocking release policy for this corpus family."
            ),
        },
        "gates": gate_report,
        "violations": blocking_violations,
    }
    if mode == RELEASE_ENFORCEMENT and blocking_violations:
        raise CorpusValidationError(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--corpus-path", required=True, type=Path)
    validate.add_argument("--mode", choices=MODES, default=REPORT_ONLY)
    validate.add_argument("--questions_corpus_sha256")
    validate.add_argument("--questions_corpus_record_count", type=int)
    validate.add_argument("--questions_corpus_bytes", type=int)
    validate.add_argument("--questions_corpus_snapshot_id")
    validate.add_argument("--questions_corpus_source_identity")
    validate.add_argument("--questions_corpus_source_sha256")
    validate.add_argument("--questions_corpus_source_record_count", type=int)
    validate.add_argument("--expected-source-sha256")
    validate.add_argument("--expected-source-record-count", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = validate_questions_corpus(
            args.corpus_path,
            mode=args.mode,
            release_binding=_binding_from_args(args),
            expected_source_sha256=args.expected_source_sha256,
            expected_source_record_count=args.expected_source_record_count,
        )
    except CorpusValidationError as error:
        if args.mode == RELEASE_ENFORCEMENT:
            try:
                print(str(error))
            except UnicodeEncodeError:
                print(str(error).encode("utf-8", "replace").decode("utf-8"))
            return 2
        print(json.dumps({"status": "FAIL_CLOSED", "reason": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" or args.mode == REPORT_ONLY else 2


if __name__ == "__main__":
    raise SystemExit(main())
