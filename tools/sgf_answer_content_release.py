"""Build and locally verify an immutable SGF answer content release package.

This module is intentionally filesystem-local.  It does not know how to SSH,
address Production, restart services, or deploy application code.  The build
path creates a candidate from an exact questions.json baseline without
reserializing the corpus.  The publish and rollback primitives are guarded,
hash-preconditioned atomic file replacements for a later Owner-authorized
content gate; Phase 2E exercises them only inside temporary local directories.
"""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
from typing import Any, Callable, Iterable, Mapping, Sequence


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from map_battle_runtime import CanonicalAnswer, judge_map_battle_answer_v1
from sgf_engine.core.coord_utils import xy_to_sgf
from sgf_engine.core.matcher import BRANCH, match_move
from sgf_engine.parser.sgf_parser import parse_sgf
from tools import sgf_answer_repair_batch as repair


SCHEMA_VERSION = "1.0"
AUTHORITY = "SGF_ANSWER_REPAIR_BATCH_001_PHASE_2E_LOCAL_OFFLINE"
PRODUCTION_DESTINATION = "/app/data/questions.json"

BASELINE_RECORDS = 41_591
BASELINE_SIZE_BYTES = 71_534_726
BASELINE_SHA256 = (
    "4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28"
)
SAFE_NATIVE_BATCH_SHA256 = (
    "6fd56597f599ce1be117ac2558aaa6a2e19ffb2531d802278cedc3d97f1d1b0a"
)
SAFE_NATIVE_BATCH_FILE_SHA256 = (
    "47d08829116ffb60bd5e29062c228c394cc81ee6a0758dc9e4a1394cd5c3a69a"
)
FALLBACK_BATCH_SHA256 = (
    "8f86e709306d5f6c0e46d6cad9b5094bebb9eaf618bf0c0d16ab12c237e2d422"
)
FALLBACK_BATCH_FILE_SHA256 = (
    "8db0585194e7b8f33f012a5e8f091e0090d3cfbaae1b0c5116fbfeead866a0f8"
)
SAFE_NATIVE_IDS = frozenset({7998, 8057, 8092, 8100})
KNOWN_FALLBACK_CONFLICT_IDS = frozenset({15436, 15388, 65095})
MAX_CORPUS_BYTES = 128 * 1024 * 1024


class ContentReleaseError(RuntimeError):
    """A fail-closed content release precondition or validation error."""


@dataclass(frozen=True)
class ArtifactIdentity:
    filename: str
    size_bytes: int
    record_count: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "record_count": self.record_count,
            "sha256": self.sha256,
        }


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _load_json(path: Path, *, maximum_bytes: int = MAX_CORPUS_BYTES) -> Any:
    raw = path.read_bytes()
    if len(raw) > maximum_bytes:
        raise ContentReleaseError(f"{path} exceeds the bounded input size")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContentReleaseError(f"{path} is not valid UTF-8 JSON") from error


def _load_corpus_bytes(raw: bytes) -> list[dict[str, Any]]:
    if len(raw) > MAX_CORPUS_BYTES:
        raise ContentReleaseError("questions corpus exceeds the bounded size")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContentReleaseError("questions corpus is not valid UTF-8 JSON") from error
    if not isinstance(value, list) or not all(
        isinstance(item, dict) for item in value
    ):
        raise ContentReleaseError("questions corpus must be a list of objects")
    return value


def artifact_identity(path: Path) -> ArtifactIdentity:
    raw = path.read_bytes()
    records = _load_corpus_bytes(raw)
    return ArtifactIdentity(
        filename=path.name,
        size_bytes=len(raw),
        record_count=len(records),
        sha256=_sha256_bytes(raw),
    )


def verify_baseline(
    path: Path,
    *,
    expected_sha256: str = BASELINE_SHA256,
    expected_size_bytes: int = BASELINE_SIZE_BYTES,
    expected_records: int = BASELINE_RECORDS,
) -> tuple[bytes, list[dict[str, Any]], ArtifactIdentity]:
    raw = path.read_bytes()
    records = _load_corpus_bytes(raw)
    identity = ArtifactIdentity(
        filename=path.name,
        size_bytes=len(raw),
        record_count=len(records),
        sha256=_sha256_bytes(raw),
    )
    if identity.sha256 != expected_sha256:
        raise ContentReleaseError("FAIL_CLOSED: baseline SHA-256 mismatch")
    if identity.size_bytes != expected_size_bytes:
        raise ContentReleaseError("FAIL_CLOSED: baseline byte-size mismatch")
    if identity.record_count != expected_records:
        raise ContentReleaseError("FAIL_CLOSED: baseline record-count mismatch")
    return raw, records, identity


def _load_locked_batch(
    path: Path, *, expected_file_sha256: str, expected_batch_sha256: str
) -> dict[str, Any]:
    if _sha256_file(path) != expected_file_sha256:
        raise ContentReleaseError(f"FAIL_CLOSED: locked batch file hash mismatch: {path}")
    value = _load_json(path, maximum_bytes=16 * 1024 * 1024)
    if not isinstance(value, dict):
        raise ContentReleaseError(f"locked batch must be an object: {path}")
    if value.get("batch_sha256") != expected_batch_sha256:
        raise ContentReleaseError(f"FAIL_CLOSED: locked batch hash mismatch: {path}")
    return value


def _flatten_records(batch: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    groups = batch.get("groups")
    if not isinstance(groups, list):
        raise ContentReleaseError("locked batch groups must be a list")
    for group in groups:
        if not isinstance(group, Mapping) or not isinstance(
            group.get("records"), list
        ):
            raise ContentReleaseError("locked batch group is malformed")
        for record in group["records"]:
            if not isinstance(record, dict):
                raise ContentReleaseError("locked batch record is malformed")
            result.append(record)
    return result


def _record_indexes(
    records: Sequence[Mapping[str, Any]],
) -> dict[int, list[int]]:
    result: dict[int, list[int]] = {}
    for index, record in enumerate(records):
        question_id = record.get("id")
        if not isinstance(question_id, int) or isinstance(question_id, bool):
            raise ContentReleaseError(f"record {index} has no integer id")
        result.setdefault(question_id, []).append(index)
    return result


def _skip_ws(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    return index


def _string_end(text: str, start: int) -> int:
    if start >= len(text) or text[start] != '"':
        raise ContentReleaseError("expected JSON string")
    escaped = False
    for index in range(start + 1, len(text)):
        char = text[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            return index + 1
    raise ContentReleaseError("unterminated JSON string")


def _composite_end(text: str, start: int) -> int:
    pairs = {"{": "}", "[": "]"}
    opening = text[start]
    if opening not in pairs:
        raise ContentReleaseError("expected JSON composite")
    stack = [pairs[opening]]
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == '"':
            index = _string_end(text, index)
            continue
        if char in pairs:
            stack.append(pairs[char])
        elif char in ("}", "]"):
            if not stack or char != stack.pop():
                raise ContentReleaseError("malformed JSON composite")
            if not stack:
                return index + 1
        index += 1
    raise ContentReleaseError("unterminated JSON composite")


def _value_end(text: str, start: int) -> int:
    if text[start] == '"':
        return _string_end(text, start)
    if text[start] in "[{":
        return _composite_end(text, start)
    index = start
    while index < len(text) and text[index] not in ",}":
        index += 1
    end = index
    while end > start and text[end - 1] in " \t\r\n":
        end -= 1
    if end == start:
        raise ContentReleaseError("empty JSON value")
    return end


def _object_value_spans(text: str) -> dict[str, tuple[int, int]]:
    if not text.startswith("{") or not text.endswith("}"):
        raise ContentReleaseError("record span is not a JSON object")
    result: dict[str, tuple[int, int]] = {}
    index = _skip_ws(text, 1)
    while index < len(text) and text[index] != "}":
        key_end = _string_end(text, index)
        key = json.loads(text[index:key_end])
        if not isinstance(key, str) or key in result:
            raise ContentReleaseError("duplicate or invalid top-level record key")
        index = _skip_ws(text, key_end)
        if index >= len(text) or text[index] != ":":
            raise ContentReleaseError("missing JSON object colon")
        value_start = _skip_ws(text, index + 1)
        value_end = _value_end(text, value_start)
        result[key] = (value_start, value_end)
        index = _skip_ws(text, value_end)
        if text[index] == ",":
            index = _skip_ws(text, index + 1)
        elif text[index] != "}":
            raise ContentReleaseError("missing JSON object delimiter")
    return result


def _array_object_spans(text: str) -> list[tuple[int, int]]:
    index = _skip_ws(text, 0)
    if index >= len(text) or text[index] != "[":
        raise ContentReleaseError("questions corpus is not a JSON array")
    index = _skip_ws(text, index + 1)
    result: list[tuple[int, int]] = []
    while index < len(text) and text[index] != "]":
        if text[index] != "{":
            raise ContentReleaseError("questions array contains a non-object")
        end = _composite_end(text, index)
        result.append((index, end))
        index = _skip_ws(text, end)
        if text[index] == ",":
            index = _skip_ws(text, index + 1)
        elif text[index] != "]":
            raise ContentReleaseError("missing questions array delimiter")
    if index >= len(text) or text[index] != "]":
        raise ContentReleaseError("unterminated questions array")
    if _skip_ws(text, index + 1) != len(text):
        raise ContentReleaseError("unexpected data after questions array")
    return result


def _replace_object_string_values(
    object_text: str, replacements: Mapping[str, str]
) -> tuple[str, dict[str, str]]:
    spans = _object_value_spans(object_text)
    edits: list[tuple[int, int, str]] = []
    before: dict[str, str] = {}
    for key, replacement in replacements.items():
        if key not in spans:
            raise ContentReleaseError(f"target record is missing {key}")
        start, end = spans[key]
        try:
            current = json.loads(object_text[start:end])
        except json.JSONDecodeError as error:
            raise ContentReleaseError(f"target field {key} is invalid JSON") from error
        if not isinstance(current, str):
            raise ContentReleaseError(f"target field {key} is not a string")
        before[key] = current
        encoded = json.dumps(replacement, ensure_ascii=False)
        edits.append((start, end, encoded))
    result = object_text
    for start, end, encoded in sorted(edits, reverse=True):
        result = result[:start] + encoded + result[end:]
    return result, before


def patch_corpus_string_fields(
    baseline_raw: bytes,
    baseline_records: Sequence[Mapping[str, Any]],
    replacements_by_index: Mapping[int, Mapping[str, str]],
) -> tuple[bytes, dict[int, dict[str, str]]]:
    try:
        text = baseline_raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContentReleaseError("baseline is not UTF-8") from error
    spans = _array_object_spans(text)
    if len(spans) != len(baseline_records):
        raise ContentReleaseError("record span count does not match parsed corpus")
    edits: list[tuple[int, int, str]] = []
    before: dict[int, dict[str, str]] = {}
    for index, replacements in replacements_by_index.items():
        if not 0 <= index < len(spans):
            raise ContentReleaseError(f"target record index is invalid: {index}")
        start, end = spans[index]
        object_text = text[start:end]
        parsed_object = json.loads(object_text)
        if parsed_object != baseline_records[index]:
            raise ContentReleaseError(f"record span mismatch at index {index}")
        patched, old_values = _replace_object_string_values(
            object_text, replacements
        )
        edits.append((start, end, patched))
        before[index] = old_values
    candidate = text
    for start, end, patched in sorted(edits, reverse=True):
        candidate = candidate[:start] + patched + candidate[end:]
    return candidate.encode("utf-8"), before


def _changed_fields(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> list[str]:
    keys = set(before) | set(after)
    return sorted(key for key in keys if before.get(key) != after.get(key))


def semantic_diff(
    baseline: Sequence[Mapping[str, Any]],
    candidate: Sequence[Mapping[str, Any]],
    *,
    native_ids: set[int],
    fallback_ids: set[int],
) -> dict[str, Any]:
    if len(baseline) != len(candidate):
        raise ContentReleaseError("candidate record count changed")
    target_ids = native_ids | fallback_ids
    changed: list[dict[str, Any]] = []
    non_target_changed: list[int] = []
    accepted_moves_changed: list[int] = []
    for index, (before, after) in enumerate(zip(baseline, candidate)):
        if before.get("id") != after.get("id"):
            raise ContentReleaseError(f"record identity/order changed at {index}")
        question_id = int(before["id"])
        fields = _changed_fields(before, after)
        if before.get("accepted_moves") != after.get("accepted_moves"):
            accepted_moves_changed.append(question_id)
        if not fields:
            continue
        if question_id not in target_ids:
            non_target_changed.append(question_id)
        expected = ["content"] if question_id in native_ids else ["katago_best_move"]
        if fields != expected:
            raise ContentReleaseError(
                f"question {question_id} changed fields {fields}, expected {expected}"
            )
        changed.append(
            {
                "question_id": question_id,
                "record_index": index,
                "changed_fields": fields,
            }
        )
    changed_ids = {item["question_id"] for item in changed}
    if changed_ids != target_ids:
        missing = sorted(target_ids - changed_ids)
        extra = sorted(changed_ids - target_ids)
        raise ContentReleaseError(
            f"target mutation mismatch; missing={missing}, extra={extra}"
        )
    if non_target_changed or accepted_moves_changed:
        raise ContentReleaseError("non-target or accepted_moves mutation detected")
    return {
        "target_records_changed": len(changed),
        "non_target_records_changed": 0,
        "accepted_moves_changed": 0,
        "native_repair_records": len(native_ids),
        "fallback_fields_cleared": len(fallback_ids),
        "records": sorted(changed, key=lambda item: item["question_id"]),
    }


def _board_size(content: str) -> int:
    structure = repair._answer_structure(content)
    values = structure["root"].values("SZ")
    if values:
        try:
            size = int(values[0])
        except (TypeError, ValueError) as error:
            raise ContentReleaseError("SGF board size is invalid") from error
    else:
        size = 19
    if not 1 <= size <= 25:
        raise ContentReleaseError("SGF board size is out of bounds")
    return size


def _accepted_points(record: Mapping[str, Any], board_size: int) -> set[tuple[int, int]]:
    raw = record.get("accepted_moves") or record.get("accepted_answers") or []
    if isinstance(raw, Mapping):
        raw = [raw]
    result: set[tuple[int, int]] = set()
    for move in raw if isinstance(raw, list) else []:
        if not isinstance(move, Mapping):
            continue
        x, y = move.get("x"), move.get("y")
        if isinstance(x, int) and isinstance(y, int) and 0 <= x < board_size and 0 <= y < board_size:
            result.add((x, y))
    return result


def _labels(points: Iterable[tuple[int, int]], board_size: int) -> list[str]:
    return sorted(repair._point_label(point, board_size) for point in set(points))


def _identity_sid(app_module: Any, question_id: int) -> str:
    for suffix in range(4096):
        sid = f"phase2e-{question_id}-{suffix}"
        if app_module._rt_transform_idx(sid, question_id) == 0:
            return sid
    raise ContentReleaseError("could not obtain identity Rating Test transform")


def _rating_witness(
    tree_root: Mapping[str, Any], first_point: tuple[int, int]
) -> list[dict[str, int]]:
    """Choose one complete player sequence using Rating Test replay semantics."""

    current = tree_root
    moves: list[dict[str, int]] = []
    first = True
    for _ in range(512):
        children = list(current.get("children") or [])
        if not children:
            return moves
        if first:
            player = next(
                (
                    child
                    for child in children
                    if child.get("move")
                    and tuple(child["move"]) == first_point
                ),
                None,
            )
            first = False
        else:
            player = children[0]
        if player is None or not player.get("move"):
            raise ContentReleaseError("cannot construct Rating Test answer witness")
        x, y = player["move"]
        moves.append({"x": int(x), "y": int(y)})
        current = player
        replies = list(current.get("children") or [])
        if not replies:
            return moves
        reply = replies[0]
        if not reply.get("move"):
            return moves
        current = reply
        if not current.get("children"):
            return moves
    raise ContentReleaseError("Rating Test witness exceeds bounded depth")


def validate_player_verdicts(
    candidate_records: Sequence[Mapping[str, Any]],
    expected_by_id: Mapping[int, Sequence[str]],
    *,
    fail_on_map_battle_mismatch: bool = True,
) -> dict[str, Any]:
    os.environ.setdefault("SECRET_KEY", "synthetic-phase2e-local-validation-only")
    os.environ.setdefault("SITE_URL", "http://localhost")
    import app as app_module

    indexes = _record_indexes(candidate_records)
    evidence: list[dict[str, Any]] = []
    map_battle_mismatch_ids: list[int] = []
    for question_id in sorted(expected_by_id):
        occurrences = indexes.get(question_id) or []
        if len(occurrences) != 1:
            raise ContentReleaseError(
                f"question {question_id} is not uniquely locatable in candidate"
            )
        record = candidate_records[occurrences[0]]
        content = record.get("content")
        if not isinstance(content, str) or not content:
            raise ContentReleaseError(f"question {question_id} has no SGF content")
        structure = repair._answer_structure(content)
        size = _board_size(content)
        native = set(structure["ordered_points"])
        accepted = _accepted_points(record, size)
        fallback_text = str(record.get("katago_best_move") or "").strip()
        fallback = repair._gtp_to_xy(fallback_text, size) if fallback_text else None
        if fallback_text and fallback is None:
            raise ContentReleaseError(f"question {question_id} has invalid fallback")
        expected_labels = sorted(set(expected_by_id[question_id]))
        expected_points = {
            point
            for label in expected_labels
            for point in [repair._gtp_to_xy(label, size)]
            if point is not None
        }
        if len(expected_points) != len(expected_labels):
            raise ContentReleaseError(f"question {question_id} has invalid desired move")

        parsed = parse_sgf(content, strict=True)
        engine = {
            (x, y)
            for y in range(size)
            for x in range(size)
            if match_move(parsed, xy_to_sgf(x, y), None) == BRANCH
        }
        if engine != native:
            raise ContentReleaseError(f"question {question_id} engine/tree mismatch")

        sid = _identity_sid(app_module, question_id)
        legacy_tree = app_module._rt_parse_answer_tree(content)
        if legacy_tree is None:
            raise ContentReleaseError(
                f"question {question_id} is unavailable to Rating Test parser"
            )
        witnesses: dict[tuple[int, int], list[dict[str, int]]] = {}
        for point in sorted(expected_points):
            witness = _rating_witness(legacy_tree, point)
            if not witness or tuple((witness[0]["x"], witness[0]["y"])) != point:
                raise ContentReleaseError(
                    f"question {question_id} witness has the wrong first move"
                )
            if app_module._rt_server_verify(dict(record), sid, witness) is not True:
                raise ContentReleaseError(
                    f"question {question_id} Rating Test rejects a desired variation"
                )
            witnesses[point] = witness
        for y in range(size):
            for x in range(size):
                if (x, y) in expected_points:
                    continue
                if app_module._rt_server_verify(
                    dict(record), sid, [{"x": x, "y": y}]
                ) is True:
                    raise ContentReleaseError(
                        f"question {question_id} Rating Test accepts unexpected first move"
                    )
        rating = set(witnesses)

        side = structure["side_to_move"]
        if side not in ("B", "W"):
            raise ContentReleaseError(f"question {question_id} side to move unknown")
        attempt = {"board_size": size, "transform_id": "identity"}
        map_battle = set()
        map_battle_failures: list[dict[str, Any]] = []
        for point, witness in witnesses.items():
            canonical = CanonicalAnswer(
                {
                    "moves": [
                        {"action": "play", "x": move["x"], "y": move["y"]}
                        for move in witness
                    ],
                    "player_color": side,
                }
            )
            outcome = judge_map_battle_answer_v1(record, attempt, canonical)
            if outcome.result != "CORRECT":
                map_battle_failures.append(
                    {
                        "first_move": repair._point_label(point, size),
                        "reason_code": outcome.reason_code,
                        "witness_player_move_count": len(witness),
                    }
                )
            else:
                map_battle.add(point)
        for y in range(size):
            for x in range(size):
                if (x, y) in expected_points:
                    continue
                canonical = CanonicalAnswer(
                    {
                        "moves": [{"action": "play", "x": x, "y": y}],
                        "player_color": side,
                    }
                )
                outcome = judge_map_battle_answer_v1(record, attempt, canonical)
                if outcome.result == "CORRECT":
                    raise ContentReleaseError(
                        f"question {question_id} Map Battle accepts unexpected first move"
                    )

        main_practice = native | accepted
        final_effective = native | accepted
        if fallback is not None:
            final_effective.add(fallback)
        surfaces = {
            "sgf_engine_native": engine,
            "main_practice_client": main_practice,
            "daily_challenge_client": main_practice,
            "friend_challenge_client_then_server_trust": main_practice,
            "map_battle_server": map_battle,
            "rating_test_server": rating,
            "final_effective_player_verdict": final_effective,
        }
        non_map_surfaces = {
            name: points
            for name, points in surfaces.items()
            if name != "map_battle_server"
        }
        if any(points != expected_points for points in non_map_surfaces.values()):
            rendered = {
                name: _labels(points, size) for name, points in surfaces.items()
            }
            raise ContentReleaseError(
                f"question {question_id} verdict mismatch: {rendered} != {expected_labels}"
            )
        map_battle_match = map_battle == expected_points
        if not map_battle_match:
            map_battle_mismatch_ids.append(question_id)
        evidence.append(
            {
                "question_id": question_id,
                "board_size": size,
                "owner_desired_verdict": expected_labels,
                "final_effective_player_verdict": expected_labels,
                "accepted_moves": _labels(accepted, size),
                "native_accepted_set": _labels(native, size),
                "katago_best_move": fallback_text,
                "runtime_witness_lengths": {
                    repair._point_label(point, size): len(witness)
                    for point, witness in sorted(witnesses.items())
                },
                "map_battle_matches_owner": map_battle_match,
                "map_battle_failures": map_battle_failures,
                "surfaces": {
                    name: _labels(points, size) for name, points in surfaces.items()
                },
                "match": "YES" if map_battle_match else "NO",
            }
        )
    if map_battle_mismatch_ids and fail_on_map_battle_mismatch:
        raise ContentReleaseError(
            "strict Map Battle verdict mismatch for questions: "
            + ",".join(str(value) for value in map_battle_mismatch_ids)
        )
    return {
        "records_validated": len(evidence),
        "all_final_effective_match": not map_battle_mismatch_ids,
        "map_battle_mismatch_count": len(map_battle_mismatch_ids),
        "map_battle_mismatch_ids": map_battle_mismatch_ids,
        "records": evidence,
    }


def _write_or_verify(path: Path, raw: bytes) -> None:
    if path.exists():
        if path.read_bytes() != raw:
            raise ContentReleaseError(f"refusing to overwrite different artifact: {path}")
        return
    path.write_bytes(raw)


def _manifest_record_map(
    native_records: Sequence[Mapping[str, Any]],
    fallback_records: Sequence[Mapping[str, Any]],
) -> tuple[dict[int, Sequence[str]], dict[int, dict[str, Any]]]:
    expected: dict[int, Sequence[str]] = {}
    source: dict[int, dict[str, Any]] = {}
    for lane, rows in (("NATIVE_SGF_REPAIR", native_records), ("FALLBACK_CLEAR", fallback_records)):
        for record in rows:
            question_id = int(record["legacy_question_id"])
            if question_id in expected:
                raise ContentReleaseError(f"question {question_id} appears in both lanes")
            desired = record.get("owner_desired_verdict")
            if not isinstance(desired, list) or not all(isinstance(x, str) for x in desired):
                raise ContentReleaseError(f"question {question_id} has invalid desired verdict")
            expected[question_id] = desired
            source[question_id] = {"lane": lane, "record": dict(record)}
    return expected, source


def _prepare_replacements(
    baseline_records: Sequence[Mapping[str, Any]],
    native_records: Sequence[Mapping[str, Any]],
    fallback_records: Sequence[Mapping[str, Any]],
) -> tuple[dict[int, dict[str, str]], dict[int, Sequence[str]], list[dict[str, Any]]]:
    indexes = _record_indexes(baseline_records)
    expected_by_id, source = _manifest_record_map(native_records, fallback_records)
    replacements: dict[int, dict[str, str]] = {}
    audit: list[dict[str, Any]] = []
    for question_id in sorted(source):
        occurrences = indexes.get(question_id) or []
        if len(occurrences) != 1:
            raise ContentReleaseError(
                f"question {question_id} is not uniquely locatable in baseline"
            )
        index = occurrences[0]
        baseline = baseline_records[index]
        locked = source[question_id]["record"]
        if index != int(locked["current_record_index"]):
            raise ContentReleaseError(f"question {question_id} record index drift")
        content = baseline.get("content")
        if not isinstance(content, str):
            raise ContentReleaseError(f"question {question_id} content is not a string")
        before_content_sha = _sha256_bytes(content.encode("utf-8"))
        if before_content_sha != locked.get("source_content_sha256_before"):
            raise ContentReleaseError(f"question {question_id} content precondition drift")
        current_fallback = str(baseline.get("katago_best_move") or "")
        if current_fallback != str(locked.get("current_fallback_move") or ""):
            raise ContentReleaseError(f"question {question_id} fallback precondition drift")

        if source[question_id]["lane"] == "NATIVE_SGF_REPAIR":
            desired_labels = list(locked["desired_native_accepted_set"])
            rewrite_operations = [
                operation
                for operation in (locked.get("planned_operations") or [])
                if operation.get("type") == "REWRITE_NATIVE_ROOT_ANSWER_SET"
            ]
            if rewrite_operations:
                if len(rewrite_operations) != 1 or not isinstance(
                    rewrite_operations[0].get("after"), list
                ):
                    raise ContentReleaseError(
                        f"question {question_id} has ambiguous rewrite ordering"
                    )
                ordered_labels = list(rewrite_operations[0]["after"])
                if sorted(ordered_labels) != sorted(desired_labels):
                    raise ContentReleaseError(
                        f"question {question_id} ordered rewrite differs from desired set"
                    )
                desired_labels = ordered_labels
            size = _board_size(content)
            desired_points = [repair._gtp_to_xy(label, size) for label in desired_labels]
            if any(point is None for point in desired_points):
                raise ContentReleaseError(f"question {question_id} has invalid native desired move")
            repaired, _ = repair._rewrite_answer_set(content, desired_points)
            after_content_sha = _sha256_bytes(repaired.encode("utf-8"))
            if after_content_sha != locked.get("source_content_sha256_after"):
                raise ContentReleaseError(f"question {question_id} repair output drift")
            replacements[index] = {"content": repaired}
            changed_fields = ["content"]
        else:
            if locked.get("desired_fallback_move") != "":
                raise ContentReleaseError(f"question {question_id} fallback target is not empty")
            if locked.get("source_content_sha256_after") != before_content_sha:
                raise ContentReleaseError(f"question {question_id} unexpectedly requests SGF rewrite")
            replacements[index] = {"katago_best_move": ""}
            after_content_sha = before_content_sha
            changed_fields = ["katago_best_move"]
        audit.append(
            {
                "question_id": question_id,
                "record_index": index,
                "lane": source[question_id]["lane"],
                "changed_fields": changed_fields,
                "content_sha256_before": before_content_sha,
                "content_sha256_after": after_content_sha,
                "katago_best_move_before": current_fallback,
                "katago_best_move_after": (
                    "" if source[question_id]["lane"] == "FALLBACK_CLEAR" else current_fallback
                ),
                "owner_desired_verdict": sorted(expected_by_id[question_id]),
            }
        )
    return replacements, expected_by_id, audit


def _copy_exact(source: Path, destination: Path) -> None:
    if destination.exists():
        if _sha256_file(destination) != _sha256_file(source):
            raise ContentReleaseError(f"different artifact already exists: {destination}")
        return
    shutil.copyfile(source, destination)


def build_release_package(
    *,
    baseline_path: Path,
    native_batch_path: Path,
    fallback_batch_path: Path,
    output_dir: Path,
    created_at: str,
    expected_baseline_sha256: str = BASELINE_SHA256,
    expected_baseline_size: int = BASELINE_SIZE_BYTES,
    expected_baseline_records: int = BASELINE_RECORDS,
    expected_native_batch_sha256: str = SAFE_NATIVE_BATCH_SHA256,
    expected_native_batch_file_sha256: str = SAFE_NATIVE_BATCH_FILE_SHA256,
    expected_fallback_batch_sha256: str = FALLBACK_BATCH_SHA256,
    expected_fallback_batch_file_sha256: str = FALLBACK_BATCH_FILE_SHA256,
    expected_native_ids: frozenset[int] = SAFE_NATIVE_IDS,
    expected_excluded_ids: frozenset[int] = KNOWN_FALLBACK_CONFLICT_IDS,
    expected_fallback_records: int = 61,
    expected_fallback_groups: int = 50,
    validate_runtime: bool = True,
) -> dict[str, Any]:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", created_at):
        raise ContentReleaseError("created_at must be fixed UTC seconds in YYYY-MM-DDTHH:MM:SSZ")
    baseline_raw, baseline_records, baseline_identity = verify_baseline(
        baseline_path,
        expected_sha256=expected_baseline_sha256,
        expected_size_bytes=expected_baseline_size,
        expected_records=expected_baseline_records,
    )
    native_batch = _load_locked_batch(
        native_batch_path,
        expected_file_sha256=expected_native_batch_file_sha256,
        expected_batch_sha256=expected_native_batch_sha256,
    )
    fallback_batch = _load_locked_batch(
        fallback_batch_path,
        expected_file_sha256=expected_fallback_batch_file_sha256,
        expected_batch_sha256=expected_fallback_batch_sha256,
    )
    native_records = _flatten_records(native_batch)
    fallback_records = _flatten_records(fallback_batch)
    native_ids = {int(row["legacy_question_id"]) for row in native_records}
    fallback_ids = {int(row["legacy_question_id"]) for row in fallback_records}
    if native_ids != set(expected_native_ids) or len(native_records) != len(expected_native_ids):
        raise ContentReleaseError("FAIL_CLOSED: native batch membership drift")
    if (
        len(fallback_batch.get("groups") or []) != expected_fallback_groups
        or len(fallback_records) != expected_fallback_records
        or len(fallback_ids) != expected_fallback_records
    ):
        raise ContentReleaseError("FAIL_CLOSED: fallback batch membership drift")
    if native_ids & fallback_ids:
        raise ContentReleaseError("repair lanes overlap")
    if expected_excluded_ids & (native_ids | fallback_ids):
        raise ContentReleaseError("known fallback conflict entered candidate")

    replacements, expected_by_id, mutation_records = _prepare_replacements(
        baseline_records, native_records, fallback_records
    )
    candidate_raw, raw_before = patch_corpus_string_fields(
        baseline_raw, baseline_records, replacements
    )
    candidate_records = _load_corpus_bytes(candidate_raw)
    diff = semantic_diff(
        baseline_records,
        candidate_records,
        native_ids=native_ids,
        fallback_ids=fallback_ids,
    )
    for index, old_values in raw_before.items():
        for field, old_value in old_values.items():
            if baseline_records[index].get(field) != old_value:
                raise ContentReleaseError("raw-field patch precondition mismatch")

    baseline_indexes = _record_indexes(baseline_records)
    candidate_indexes = _record_indexes(candidate_records)
    missing_exclusions = sorted(
        expected_excluded_ids - set(baseline_indexes)
    )
    if missing_exclusions:
        raise ContentReleaseError(
            f"known fallback conflicts missing from baseline: {missing_exclusions}"
        )
    excluded = {
        question_id: (
            len(baseline_indexes[question_id]) == 1
            and baseline_indexes[question_id] == candidate_indexes[question_id]
            and baseline_records[baseline_indexes[question_id][0]]
            == candidate_records[candidate_indexes[question_id][0]]
        )
        for question_id in sorted(expected_excluded_ids)
    }
    if not all(excluded.values()):
        raise ContentReleaseError("known fallback conflict changed")

    if validate_runtime:
        verdict = validate_player_verdicts(candidate_records, expected_by_id)
    else:
        verdict = {
            "records_validated": 0,
            "all_final_effective_match": None,
            "records": [],
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        allowed_existing = {path.name for path in output_dir.iterdir() if path.is_file()}
        if not all(
            name.startswith(("questions.", "content-release-", "content-rollback-", "local-publish-"))
            for name in allowed_existing
        ):
            raise ContentReleaseError("output directory contains unrelated artifacts")

    baseline_name = f"questions.pre-mutation.{baseline_identity.sha256[:12]}.json"
    candidate_sha256 = _sha256_bytes(candidate_raw)
    candidate_name = f"questions.repaired-candidate.{candidate_sha256[:12]}.json"
    baseline_copy = output_dir / baseline_name
    candidate_path = output_dir / candidate_name
    _copy_exact(baseline_path, baseline_copy)
    _write_or_verify(candidate_path, candidate_raw)
    baseline_artifact = artifact_identity(baseline_copy)
    candidate_artifact = artifact_identity(candidate_path)
    if baseline_artifact.sha256 != expected_baseline_sha256:
        raise ContentReleaseError("pre-mutation artifact is not byte exact")

    verdict_by_id = {
        int(row["question_id"]): row for row in verdict.get("records") or []
    }
    for row in mutation_records:
        runtime_row = verdict_by_id.get(int(row["question_id"]))
        row["post_mutation_final_effective_verdict"] = (
            runtime_row.get("final_effective_player_verdict") if runtime_row else None
        )
        row["match"] = runtime_row.get("match") if runtime_row else "NOT_RUN"

    release_manifest = {
        "schema_version": SCHEMA_VERSION,
        "authority": AUTHORITY,
        "created_at": created_at,
        "source_baseline_sha256": expected_baseline_sha256,
        "intended_production_destination": PRODUCTION_DESTINATION,
        "publisher_precondition_hash_lock": expected_baseline_sha256,
        "repair_batch_locks": {
            "safe_native_sgf_batch_sha256": expected_native_batch_sha256,
            "safe_native_sgf_batch_file_sha256": expected_native_batch_file_sha256,
            "fallback_candidate_batch_sha256": expected_fallback_batch_sha256,
            "fallback_candidate_batch_file_sha256": expected_fallback_batch_file_sha256,
        },
        "pre_mutation_artifact": baseline_artifact.as_dict(),
        "repaired_candidate_artifact": candidate_artifact.as_dict(),
        "mutation_audit": diff,
        "repair_records": mutation_records,
        "verdict_validation": verdict,
        "excluded_questions_unchanged": excluded,
        "excluded_populations": {
            "stale_groups": "UNCHANGED_BY_NON_TARGET_SEMANTIC_IDENTITY",
            "manual_reconstruction": "UNCHANGED_BY_NON_TARGET_SEMANTIC_IDENTITY",
            "unresolved_older_corpus_records": "NO_MAPPING_OR_MUTATION_ATTEMPTED",
        },
        "impact": {
            "informational_best_move_outputs_removed": len(fallback_ids),
            "shadow_observational_candidate_values_removed": len(fallback_ids),
            "replacement_fallback_data_generated": False,
            "katago_run": "NONE",
        },
        "safety": {
            "production_contact": "NONE",
            "production_mutation": "NO",
            "baseline_modified_in_place": False,
            "questions_json_full_reserialization": False,
            "accepted_moves_mutated": False,
            "merge": "NO",
            "deploy": "NO",
        },
    }
    release_bytes = _json_bytes(release_manifest)
    release_name = f"content-release-manifest.{candidate_sha256[:12]}.json"
    release_path = output_dir / release_name
    _write_or_verify(release_path, release_bytes)
    release_sha256 = _sha256_bytes(release_bytes)

    rollback_manifest = {
        "schema_version": SCHEMA_VERSION,
        "authority": AUTHORITY,
        "created_at": created_at,
        "intended_production_destination": PRODUCTION_DESTINATION,
        "rollback_precondition_candidate_sha256": candidate_sha256,
        "rollback_expected_final_sha256": expected_baseline_sha256,
        "source_release_manifest": {
            "filename": release_name,
            "sha256": release_sha256,
        },
        "pre_mutation_artifact": baseline_artifact.as_dict(),
        "repaired_candidate_artifact": candidate_artifact.as_dict(),
        "repair_batch_locks": release_manifest["repair_batch_locks"],
        "rollback_operation": (
            "VERIFY_CANDIDATE_PRECONDITION_THEN_ATOMICALLY_REPLACE_WITH_BYTE_EXACT_PRE_MUTATION_ARTIFACT"
        ),
        "safety": {
            "destructive_schema_rollback": False,
            "application_image_rollback": False,
            "content_only": True,
            "production_execution_authorized": False,
        },
    }
    rollback_bytes = _json_bytes(rollback_manifest)
    rollback_name = f"content-rollback-manifest.{candidate_sha256[:12]}.json"
    rollback_path = output_dir / rollback_name
    _write_or_verify(rollback_path, rollback_bytes)
    rollback_sha256 = _sha256_bytes(rollback_bytes)

    return {
        "baseline_artifact": baseline_artifact.as_dict(),
        "candidate_artifact": candidate_artifact.as_dict(),
        "release_manifest": release_name,
        "release_manifest_sha256": release_sha256,
        "rollback_manifest": rollback_name,
        "rollback_manifest_sha256": rollback_sha256,
        "target_records_changed": diff["target_records_changed"],
        "non_target_records_changed": diff["non_target_records_changed"],
        "fallback_fields_cleared": diff["fallback_fields_cleared"],
        "native_repair_records": diff["native_repair_records"],
        "all_65_final_effective_match": verdict["all_final_effective_match"],
        "publisher_precondition_hash_lock": expected_baseline_sha256,
    }


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_replace_from_artifact(
    *,
    target: Path,
    artifact: Path,
    expected_current_sha256: str,
    expected_artifact_sha256: str,
    expected_record_count: int,
    before_replace: Callable[[Path, Path], None] | None = None,
) -> dict[str, Any]:
    if not target.is_file() or not artifact.is_file():
        raise ContentReleaseError("target and artifact must be existing files")
    if target.resolve() == artifact.resolve():
        raise ContentReleaseError("target and artifact must be different files")
    current_sha = _sha256_file(target)
    if current_sha != expected_current_sha256:
        raise ContentReleaseError("FAIL_CLOSED: current content precondition hash mismatch")
    artifact_identity_value = artifact_identity(artifact)
    if artifact_identity_value.sha256 != expected_artifact_sha256:
        raise ContentReleaseError("FAIL_CLOSED: artifact hash mismatch")
    if artifact_identity_value.record_count != expected_record_count:
        raise ContentReleaseError("FAIL_CLOSED: artifact record count mismatch")

    target_stat = target.stat()
    descriptor, stage_name = tempfile.mkstemp(
        prefix=f".{target.name}.stage-", dir=target.parent
    )
    stage = Path(stage_name)
    try:
        with os.fdopen(descriptor, "wb") as handle, artifact.open("rb") as source:
            shutil.copyfileobj(source, handle, length=1024 * 1024)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(stage, stat.S_IMODE(target_stat.st_mode))
        if hasattr(os, "chown"):
            try:
                os.chown(stage, target_stat.st_uid, target_stat.st_gid)
            except PermissionError as error:
                raise ContentReleaseError("cannot preserve target ownership") from error
        staged_identity = artifact_identity(stage)
        if staged_identity.sha256 != expected_artifact_sha256:
            raise ContentReleaseError("staged artifact hash mismatch")
        if staged_identity.record_count != expected_record_count:
            raise ContentReleaseError("staged artifact record count mismatch")
        if before_replace is not None:
            before_replace(target, stage)
        os.replace(stage, target)
        _fsync_directory(target.parent)
        final_identity = artifact_identity(target)
        if final_identity.sha256 != expected_artifact_sha256:
            raise ContentReleaseError("post-replacement hash mismatch")
        if final_identity.record_count != expected_record_count:
            raise ContentReleaseError("post-replacement record count mismatch")
        return {
            "precondition_sha256": expected_current_sha256,
            "result_sha256": final_identity.sha256,
            "result_record_count": final_identity.record_count,
            "atomic_replace": "PASS",
        }
    finally:
        if stage.exists():
            stage.unlink()


def simulate_publish_and_rollback(
    *,
    baseline_artifact: Path,
    candidate_artifact: Path,
    baseline_sha256: str,
    candidate_sha256: str,
    expected_record_count: int,
    output_path: Path,
    created_at: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="sgf-content-release-phase2e-") as raw_dir:
        root = Path(raw_dir)
        live = root / "questions.json"
        shutil.copyfile(baseline_artifact, live)

        wrong_hash_refused = False
        try:
            atomic_replace_from_artifact(
                target=live,
                artifact=candidate_artifact,
                expected_current_sha256="0" * 64,
                expected_artifact_sha256=candidate_sha256,
                expected_record_count=expected_record_count,
            )
        except ContentReleaseError:
            wrong_hash_refused = True
        if not wrong_hash_refused or _sha256_file(live) != baseline_sha256:
            raise ContentReleaseError("wrong-hash simulation did not fail closed")

        interrupted = root / ".questions.json.stage-interrupted"
        shutil.copyfile(candidate_artifact, interrupted)
        if _sha256_file(live) != baseline_sha256:
            raise ContentReleaseError("staged interruption changed live content")
        interrupted.unlink()

        publish = atomic_replace_from_artifact(
            target=live,
            artifact=candidate_artifact,
            expected_current_sha256=baseline_sha256,
            expected_artifact_sha256=candidate_sha256,
            expected_record_count=expected_record_count,
        )
        if _sha256_file(live) != candidate_sha256:
            raise ContentReleaseError("local publish did not produce candidate")

        rollback = atomic_replace_from_artifact(
            target=live,
            artifact=baseline_artifact,
            expected_current_sha256=candidate_sha256,
            expected_artifact_sha256=baseline_sha256,
            expected_record_count=expected_record_count,
        )
        final_sha = _sha256_file(live)
        if final_sha != baseline_sha256:
            raise ContentReleaseError("local rollback was not byte exact")

    result = {
        "schema_version": SCHEMA_VERSION,
        "authority": AUTHORITY,
        "created_at": created_at,
        "wrong_hash_fail_closed_test": "PASS",
        "interrupted_stage_original_recoverable": "PASS",
        "publisher_local_simulation": "PASS",
        "published_sha256": publish["result_sha256"],
        "rollback_local_simulation": "PASS",
        "rollback_byte_exact": "YES",
        "rollback_final_sha256": final_sha,
        "publish": publish,
        "rollback": rollback,
        "production_contact": "NONE",
        "production_mutation": "NO",
    }
    _write_or_verify(output_path, _json_bytes(result))
    result["simulation_artifact"] = output_path.name
    result["simulation_artifact_sha256"] = _sha256_file(output_path)
    return result


def _guard_execute(owner_gate: str, execute: bool, expected_gate: str) -> None:
    if not execute or owner_gate != expected_gate:
        raise ContentReleaseError(
            f"execution requires --execute and --owner-gate {expected_gate}"
        )


def _build_command(args: argparse.Namespace) -> dict[str, Any]:
    return build_release_package(
        baseline_path=args.baseline,
        native_batch_path=args.native_batch,
        fallback_batch_path=args.fallback_batch,
        output_dir=args.output_dir,
        created_at=args.created_at,
        validate_runtime=not args.skip_runtime_validation,
    )


def _simulate_command(args: argparse.Namespace) -> dict[str, Any]:
    return simulate_publish_and_rollback(
        baseline_artifact=args.baseline_artifact,
        candidate_artifact=args.candidate_artifact,
        baseline_sha256=args.baseline_sha256,
        candidate_sha256=args.candidate_sha256,
        expected_record_count=args.record_count,
        output_path=args.output,
        created_at=args.created_at,
    )


def _replace_command(args: argparse.Namespace, *, rollback: bool) -> dict[str, Any]:
    gate = "GO_CONTENT_ROLLBACK" if rollback else "GO_CONTENT_PUBLISH"
    _guard_execute(args.owner_gate, args.execute, gate)
    return atomic_replace_from_artifact(
        target=args.target,
        artifact=args.artifact,
        expected_current_sha256=args.expected_current_sha256,
        expected_artifact_sha256=args.expected_artifact_sha256,
        expected_record_count=args.record_count,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build")
    build.add_argument("--baseline", required=True, type=Path)
    build.add_argument("--native-batch", required=True, type=Path)
    build.add_argument("--fallback-batch", required=True, type=Path)
    build.add_argument("--output-dir", required=True, type=Path)
    build.add_argument("--created-at", required=True)
    build.add_argument("--skip-runtime-validation", action="store_true")

    simulate = subparsers.add_parser("simulate")
    simulate.add_argument("--baseline-artifact", required=True, type=Path)
    simulate.add_argument("--candidate-artifact", required=True, type=Path)
    simulate.add_argument("--baseline-sha256", required=True)
    simulate.add_argument("--candidate-sha256", required=True)
    simulate.add_argument("--record-count", required=True, type=int)
    simulate.add_argument("--output", required=True, type=Path)
    simulate.add_argument("--created-at", required=True)

    for name in ("publish", "rollback"):
        command = subparsers.add_parser(name)
        command.add_argument("--target", required=True, type=Path)
        command.add_argument("--artifact", required=True, type=Path)
        command.add_argument("--expected-current-sha256", required=True)
        command.add_argument("--expected-artifact-sha256", required=True)
        command.add_argument("--record-count", required=True, type=int)
        command.add_argument("--owner-gate", default="")
        command.add_argument("--execute", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = _build_command(args)
        elif args.command == "simulate":
            result = _simulate_command(args)
        else:
            result = _replace_command(args, rollback=args.command == "rollback")
    except (ContentReleaseError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
