"""Server-side staging for the SGF answer Owner Review Queue.

The queue source is derived read-only evidence from
SGF-ANSWER-SUSPECT-DETECTOR-001.  This module deliberately never opens or
writes questions.json and never mutates SGF, accepted moves, historical
KataGo metadata, or player verdicts.  Content hashes group identical review
surfaces only; they are not canonical puzzle identity.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import copy
import hashlib
import json
import os
from pathlib import Path
import re


REVIEW_SOURCE_SCHEMA_VERSION = "1.0"
REVIEW_SOURCE_AUTHORITY = "SGF_ANSWER_SUSPECT_DETECTOR_001"
REVIEW_SOURCE_CANONICALITY = "READ_ONLY_DERIVED_EVIDENCE"
REVIEW_STATE_AUTHORITY = "OWNER_REVIEW_STAGING"
REVIEW_STATE_CANONICALITY = "NON_AUTHORITATIVE_REPAIR_STAGING"
PROPOSAL_AUTHORITY = "OWNER_APPROVED_REPAIR_PROPOSAL"
PROPOSAL_CANONICALITY = "STAGED_NOT_APPLIED"

DETECTOR_FULL_RANKING_SIGNATURE = (
    "e0177ab32c7c2888b51c4d0c54c7e3e58e9bd46ade1baf8504f6a3a1174eb501"
)
DETECTOR_TOP_500_ORDER_SIGNATURE = (
    "ecd03c63d230749192fe36fb5b4aba7670d3eb07d82992428bf5aaa792aa11ed"
)

REVIEW_STATUSES = (
    "NO_ISSUE",
    "CONFIRMED_ISSUE",
    "POSSIBLE_MULTIPLE_SOLUTION",
    "UNCERTAIN",
)
ISSUE_REASONS = (
    "GLOBAL_TENUKI",
    "WRONG_PRIMARY_ANSWER",
    "WRONG_CONTINUATION",
    "MISSING_EQUIVALENT_SOLUTION",
    "SOURCE_CONVERSION_OR_SIDE_TO_MOVE_ERROR",
    "SGF_OR_BOARD_STRUCTURE_ERROR",
    "OTHER",
)
PROPOSAL_TYPES = (
    "REPLACE_PRIMARY_ANSWER",
    "ADD_EQUIVALENT_SOLUTION",
    "REJECT_HISTORICAL_PRECOMPUTED_FALLBACK",
    "SET_SIDE_TO_MOVE",
    "SOURCE_POSITION_INCLUDES_ANSWER",
    "NEEDS_SOURCE_RECONSTRUCTION",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MUTATION_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
_CONFIDENCE_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_SCHEMA_ADVISORY_LOCK_KEY = 773310019


class ReviewQueueError(RuntimeError):
    """Expected request/source rejection with a stable API error code."""

    code = "review_queue_error"
    http_status = 400


class ReviewSourceUnavailable(ReviewQueueError):
    code = "review_source_unavailable"
    http_status = 503


class InvalidReviewRequest(ReviewQueueError):
    code = "invalid_review_request"
    http_status = 400


class ReviewGroupNotFound(ReviewQueueError):
    code = "review_group_not_found"
    http_status = 404


class StaleReviewRevision(ReviewQueueError):
    code = "stale_review_revision"
    http_status = 409


class MutationIdConflict(ReviewQueueError):
    code = "mutation_id_conflict"
    http_status = 409


def _utc_now_text(now=None):
    value = now or datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _require_sha256(value, name):
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256")
    return value


def _require_int(value, name, *, minimum=None, maximum=None):
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} is below its minimum")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} is above its maximum")
    return value


def _clean_move(move, *, board_size, name):
    if not isinstance(move, Mapping):
        raise ValueError(f"{name} must be an object")
    x = _require_int(move.get("x"), f"{name}.x", minimum=0, maximum=board_size - 1)
    y = _require_int(move.get("y"), f"{name}.y", minimum=0, maximum=board_size - 1)
    result = {"x": x, "y": y}
    color = move.get("color")
    if color in ("B", "W"):
        result["color"] = color
    for key in ("gtp", "sgf"):
        value = move.get(key)
        if isinstance(value, str) and 0 < len(value) <= 16:
            result[key] = value
    return result


def _clean_board_preview(preview, *, board_size):
    if not isinstance(preview, Mapping):
        raise ValueError("board_preview must be an object")
    stones = preview.get("initial_stones")
    if not isinstance(stones, list):
        raise ValueError("board_preview.initial_stones must be a list")
    cleaned = []
    occupied = set()
    for index, stone in enumerate(stones):
        if not isinstance(stone, Mapping) or stone.get("color") not in ("B", "W"):
            raise ValueError(f"initial_stones[{index}] has invalid color")
        move = _clean_move(stone, board_size=board_size, name=f"initial_stones[{index}]")
        point = (move["x"], move["y"])
        if point in occupied:
            raise ValueError("initial board contains duplicate occupied points")
        occupied.add(point)
        cleaned.append({"color": stone["color"], "x": move["x"], "y": move["y"]})
    return {"initial_stones": cleaned}


def detector_validation_pack_id(records):
    identity = [
        {
            "deterministic_rank": record["deterministic_rank"],
            "record_index": record["audit_locator"]["record_index"],
            "content_sha256": record["audit_locator"]["content_sha256"],
        }
        for record in records
    ]
    return _sha256(_json_bytes(identity))


def _unique_moves(records, key):
    unique = OrderedDict()
    for record in records:
        value = record.get(key)
        moves = value if isinstance(value, list) else ([value] if value else [])
        for move in moves:
            marker = (move["x"], move["y"], move.get("color"))
            unique.setdefault(marker, move)
    return list(unique.values())


def _ordered_union(records, key):
    values = []
    seen = set()
    for record in records:
        for value in record.get(key) or []:
            if value not in seen:
                seen.add(value)
                values.append(value)
    return values


def build_review_source(detector_manifest, *, detector_manifest_sha256=None):
    """Transform the exact ranked detector pack into grouped runtime evidence."""

    if not isinstance(detector_manifest, Mapping):
        raise ValueError("detector manifest must be an object")
    snapshot = detector_manifest.get("source_snapshot")
    records = detector_manifest.get("records")
    if not isinstance(snapshot, Mapping) or not isinstance(records, list) or not records:
        raise ValueError("detector manifest is missing source_snapshot or records")
    snapshot_sha = _require_sha256(snapshot.get("sha256"), "source_snapshot.sha256")
    validation_pack_id = _require_sha256(
        detector_manifest.get("validation_pack_id"), "validation_pack_id"
    )
    if detector_validation_pack_id(records) != validation_pack_id:
        raise ValueError("detector records do not match validation_pack_id ordering")

    cleaned_records = []
    seen_locator = set()
    previous_rank = -1
    for source_order, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ValueError("detector record must be an object")
        rank = _require_int(record.get("deterministic_rank"), "deterministic_rank", minimum=0)
        if rank <= previous_rank:
            raise ValueError("detector records must retain strictly increasing deterministic_rank")
        previous_rank = rank
        locator = record.get("audit_locator")
        if not isinstance(locator, Mapping) or locator.get("type") != "AUDIT_LOCATOR_ONLY":
            raise ValueError("record must carry AUDIT_LOCATOR_ONLY")
        if locator.get("snapshot_sha256") != snapshot_sha:
            raise ValueError("audit locator snapshot does not match source snapshot")
        content_sha = _require_sha256(locator.get("content_sha256"), "content_sha256")
        record_index = _require_int(locator.get("record_index"), "record_index", minimum=0)
        legacy_id = record.get("legacy_question_id")
        if locator.get("legacy_question_id") != legacy_id:
            raise ValueError("locator legacy_question_id mismatch")
        locator_key = (record_index, content_sha)
        if locator_key in seen_locator:
            raise ValueError("duplicate audit locator")
        seen_locator.add(locator_key)
        board_size = _require_int(record.get("board_size"), "board_size", minimum=2, maximum=25)
        board_preview = _clean_board_preview(record.get("board_preview"), board_size=board_size)
        current_moves = [
            _clean_move(move, board_size=board_size, name="current_first_solution_moves")
            for move in (record.get("current_first_solution_moves") or [])
        ]
        historical = record.get("stored_precomputed_move_if_any")
        if historical is not None:
            historical = _clean_move(
                historical, board_size=board_size, name="stored_precomputed_move_if_any"
            )
        priority = record.get("priority_tier")
        if priority not in _PRIORITY_ORDER:
            raise ValueError("invalid priority_tier")
        confidence = str(record.get("confidence") or "LOW").upper()
        if confidence not in _CONFIDENCE_ORDER:
            confidence = "LOW"
        reasons = record.get("reason_codes") or []
        if not isinstance(reasons, list) or any(not isinstance(reason, str) for reason in reasons):
            raise ValueError("reason_codes must be strings")
        side = record.get("side_to_move")
        if side not in (None, "B", "W"):
            raise ValueError("side_to_move must be B, W, or null")
        cleaned_records.append(
            {
                "source_order": source_order,
                "deterministic_rank": rank,
                "audit_locator": {
                    "type": "AUDIT_LOCATOR_ONLY",
                    "snapshot_sha256": snapshot_sha,
                    "record_index": record_index,
                    "legacy_question_id": legacy_id,
                    "content_sha256": content_sha,
                },
                "legacy_question_id": legacy_id,
                "source_family_if_known": record.get("source_family_if_known"),
                "priority_tier": priority,
                "confidence": confidence,
                "reason_codes": list(reasons),
                "side_to_move": side,
                "side_to_move_display": record.get("side_to_move_display")
                or ("黑先 / Black to play" if side == "B" else "白先 / White to play" if side == "W" else "先手不明 / Side to move unknown"),
                "side_to_move_reason_codes": list(record.get("side_to_move_reason_codes") or []),
                "board_size": board_size,
                "board_preview": board_preview,
                "current_first_solution_moves": current_moves,
                "stored_precomputed_move_if_any": historical,
            }
        )

    grouped = OrderedDict()
    for record in cleaned_records:
        grouped.setdefault(record["audit_locator"]["content_sha256"], []).append(record)

    groups = []
    duplicate_groups = 0
    records_in_duplicate_groups = 0
    for group_order, (content_sha, members) in enumerate(grouped.items()):
        first = members[0]
        board_identity = _canonical_json(
            {"board_size": first["board_size"], "board_preview": first["board_preview"]}
        )
        for member in members[1:]:
            if _canonical_json(
                {"board_size": member["board_size"], "board_preview": member["board_preview"]}
            ) != board_identity:
                raise ValueError("same content fingerprint produced different board previews")
        if len(members) > 1:
            duplicate_groups += 1
            records_in_duplicate_groups += len(members)
        sides = {member["side_to_move"] for member in members}
        side = next(iter(sides)) if len(sides) == 1 else None
        side_reasons = _ordered_union(members, "side_to_move_reason_codes")
        if len(sides) > 1 and "GROUP_SIDE_TO_MOVE_CONFLICT" not in side_reasons:
            side_reasons.append("GROUP_SIDE_TO_MOVE_CONFLICT")
        priorities = sorted(
            {member["priority_tier"] for member in members}, key=_PRIORITY_ORDER.__getitem__
        )
        confidences = sorted(
            {member["confidence"] for member in members}, key=_CONFIDENCE_ORDER.__getitem__
        )
        native_moves = _unique_moves(members, "current_first_solution_moves")
        historical_moves = _unique_moves(members, "stored_precomputed_move_if_any")
        linked_records = [
            {
                "audit_locator": member["audit_locator"],
                "legacy_question_id": member["legacy_question_id"],
                "source_family_if_known": member["source_family_if_known"],
                "deterministic_rank": member["deterministic_rank"],
                "priority_tier": member["priority_tier"],
                "reason_codes": member["reason_codes"],
                "current_first_solution_moves": member["current_first_solution_moves"],
                "stored_precomputed_move_if_any": member["stored_precomputed_move_if_any"],
            }
            for member in members
        ]
        groups.append(
            {
                "review_group_key": content_sha,
                "group_order": group_order,
                "group_size": len(members),
                "first_deterministic_rank": first["deterministic_rank"],
                "priority_tier": priorities[0],
                "priority_tiers": priorities,
                "confidence": confidences[0],
                "reason_codes": _ordered_union(members, "reason_codes"),
                "side_to_move": side,
                "side_to_move_display": (
                    first["side_to_move_display"]
                    if len(sides) == 1
                    else "先手資料不一致 / Side to move conflict"
                ),
                "side_to_move_reason_codes": side_reasons,
                "board_size": first["board_size"],
                "board_preview": first["board_preview"],
                "current_first_solution_moves": native_moves,
                "historical_precomputed_moves": historical_moves,
                "metadata_variance": {
                    "native_answers": len(
                        {
                            _canonical_json(member["current_first_solution_moves"])
                            for member in members
                        }
                    )
                    > 1,
                    "historical_precomputed": len(
                        {
                            _canonical_json(member["stored_precomputed_move_if_any"])
                            for member in members
                        }
                    )
                    > 1,
                    "side_to_move": len(sides) > 1,
                },
                "linked_records": linked_records,
            }
        )

    source = {
        "schema_version": REVIEW_SOURCE_SCHEMA_VERSION,
        "authority": REVIEW_SOURCE_AUTHORITY,
        "canonicality": REVIEW_SOURCE_CANONICALITY,
        "identity_boundary": "AUDIT_LOCATOR_ONLY; REVIEW_DEDUPLICATION_NOT_CANONICAL_IDENTITY",
        "output_classification": "OWNER_REVIEW_RECOMMENDED",
        "source_snapshot": {
            "sha256": snapshot_sha,
            "size_bytes": snapshot.get("size_bytes"),
            "question_count": snapshot.get("question_count"),
        },
        "validation_pack_id": validation_pack_id,
        "detector_version": detector_manifest.get("detector_version"),
        "detector_signatures": {
            "full_13085_ranking_sha256": DETECTOR_FULL_RANKING_SIGNATURE,
            "top_500_selection_order_sha256": DETECTOR_TOP_500_ORDER_SIGNATURE,
            "validation_pack_id_recomputed": validation_pack_id,
            "detector_ranking_changed": False,
        },
        "source_record_count": len(cleaned_records),
        "review_group_count": len(groups),
        "duplicate_group_count": duplicate_groups,
        "records_in_duplicate_groups": records_in_duplicate_groups,
        "groups": groups,
    }
    if detector_manifest_sha256:
        source["detector_manifest_sha256"] = _require_sha256(
            detector_manifest_sha256, "detector_manifest_sha256"
        )
    source["review_source_id"] = _sha256(_json_bytes(source))
    return source


def build_review_source_bytes(detector_raw):
    manifest = json.loads(detector_raw.decode("utf-8"))
    source = build_review_source(manifest, detector_manifest_sha256=_sha256(detector_raw))
    return _json_bytes(source)


def write_review_source(detector_path, output_path):
    detector_path = Path(detector_path).resolve()
    output_path = Path(output_path).resolve()
    if detector_path == output_path:
        raise ValueError("detector input and review source output must differ")
    before = detector_path.read_bytes()
    result = build_review_source_bytes(before)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(result)
    if detector_path.read_bytes() != before:
        raise RuntimeError("detector input changed during review source generation")
    return {
        "path": str(output_path),
        "size_bytes": len(result),
        "sha256": _sha256(result),
        "source_sha256": _sha256(before),
    }


def _validate_review_source(source):
    if not isinstance(source, Mapping):
        raise ValueError("review source must be an object")
    if source.get("schema_version") != REVIEW_SOURCE_SCHEMA_VERSION:
        raise ValueError("unsupported review source schema")
    if source.get("authority") != REVIEW_SOURCE_AUTHORITY:
        raise ValueError("unexpected review source authority")
    if source.get("canonicality") != REVIEW_SOURCE_CANONICALITY:
        raise ValueError("review source canonicality mismatch")
    snapshot_sha = _require_sha256(source.get("source_snapshot", {}).get("sha256"), "snapshot")
    groups = source.get("groups")
    if not isinstance(groups, list) or len(groups) != source.get("review_group_count"):
        raise ValueError("review source group count mismatch")
    seen = set()
    for expected_order, group in enumerate(groups):
        key = _require_sha256(group.get("review_group_key"), "review_group_key")
        if key in seen or group.get("group_order") != expected_order:
            raise ValueError("review group keys/order are invalid")
        seen.add(key)
        linked = group.get("linked_records")
        if not isinstance(linked, list) or len(linked) != group.get("group_size") or not linked:
            raise ValueError("review group provenance is incomplete")
        for record in linked:
            locator = record.get("audit_locator", {})
            if (
                locator.get("type") != "AUDIT_LOCATOR_ONLY"
                or locator.get("snapshot_sha256") != snapshot_sha
                or locator.get("content_sha256") != key
            ):
                raise ValueError("review group locator boundary mismatch")
    signatures = source.get("detector_signatures", {})
    if signatures.get("detector_ranking_changed") is not False:
        raise ValueError("review source claims detector ranking changed")
    return source


def load_review_source(path=None):
    configured = path or os.environ.get("SGF_ANSWER_REVIEW_QUEUE_SOURCE_PATH")
    source_path = Path(configured) if configured else Path(__file__).with_name("review_data") / "sgf_answer_review_queue_v1.json"
    try:
        raw = source_path.read_bytes()
        source = json.loads(raw.decode("utf-8"))
        _validate_review_source(source)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ReviewSourceUnavailable(str(error)) from error
    return source, {"path": str(source_path.resolve()), "sha256": _sha256(raw), "size_bytes": len(raw)}


def review_group_by_key(source, group_key):
    if not isinstance(group_key, str) or not _SHA256_RE.fullmatch(group_key):
        raise ReviewGroupNotFound("invalid review group key")
    for group in source["groups"]:
        if group["review_group_key"] == group_key:
            return group
    raise ReviewGroupNotFound("review group is not in this detector pack")


def _raw_connection(conn):
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn):
    return _raw_connection(conn).__class__.__module__.startswith("sqlite3")


def _acquire_schema_lock(conn):
    if not _is_sqlite(conn):
        conn.execute(f"SELECT pg_advisory_xact_lock({_SCHEMA_ADVISORY_LOCK_KEY})")


def ensure_review_queue_tables(conn):
    """Install additive staging tables; no canonical puzzle table is touched."""

    _acquire_schema_lock(conn)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sgf_answer_review_states (
            owner_user_id                    INTEGER NOT NULL,
            snapshot_sha256                  TEXT NOT NULL,
            content_sha256                   TEXT NOT NULL,
            review_status                    TEXT,
            issue_reason                     TEXT,
            owner_note                       TEXT,
            current_sgf_answer_preserved     INTEGER NOT NULL DEFAULT 0,
            historical_precomputed_rejected INTEGER NOT NULL DEFAULT 0,
            proposals_json                   TEXT NOT NULL DEFAULT '[]',
            revision                         INTEGER NOT NULL DEFAULT 0,
            created_at                       TEXT NOT NULL,
            updated_at                       TEXT NOT NULL,
            PRIMARY KEY (owner_user_id, snapshot_sha256, content_sha256),
            FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE,
            CHECK (review_status IS NULL OR review_status IN
                ('NO_ISSUE','CONFIRMED_ISSUE','POSSIBLE_MULTIPLE_SOLUTION','UNCERTAIN')),
            CHECK (issue_reason IS NULL OR issue_reason IN
                ('GLOBAL_TENUKI','WRONG_PRIMARY_ANSWER','WRONG_CONTINUATION',
                 'MISSING_EQUIVALENT_SOLUTION','SOURCE_CONVERSION_OR_SIDE_TO_MOVE_ERROR',
                 'SGF_OR_BOARD_STRUCTURE_ERROR','OTHER')),
            CHECK (revision >= 0)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sgf_answer_review_progress (
            owner_user_id        INTEGER NOT NULL,
            snapshot_sha256      TEXT NOT NULL,
            current_content_sha256 TEXT,
            revision             INTEGER NOT NULL DEFAULT 0,
            updated_at           TEXT NOT NULL,
            PRIMARY KEY (owner_user_id, snapshot_sha256),
            FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE,
            CHECK (revision >= 0)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sgf_answer_review_mutations (
            owner_user_id   INTEGER NOT NULL,
            mutation_id     TEXT NOT NULL,
            request_sha256  TEXT NOT NULL,
            response_json   TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            PRIMARY KEY (owner_user_id, mutation_id),
            FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sgf_answer_review_audit (
            owner_user_id   INTEGER NOT NULL,
            snapshot_sha256 TEXT NOT NULL,
            content_sha256  TEXT NOT NULL,
            revision        INTEGER NOT NULL,
            mutation_id     TEXT NOT NULL,
            action          TEXT NOT NULL,
            before_json     TEXT NOT NULL,
            after_json      TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            PRIMARY KEY (owner_user_id, snapshot_sha256, content_sha256, revision),
            UNIQUE (owner_user_id, mutation_id),
            FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sgf_review_state_owner_status "
        "ON sgf_answer_review_states(owner_user_id, snapshot_sha256, review_status, updated_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sgf_review_audit_group "
        "ON sgf_answer_review_audit(owner_user_id, snapshot_sha256, content_sha256, revision)"
    )
    if hasattr(conn, "commit"):
        conn.commit()


def _row_dict(row):
    if row is None:
        return None
    if isinstance(row, Mapping):
        return dict(row)
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    raise TypeError("review queue queries require mapping rows")


def _blank_state(snapshot_sha, content_sha):
    return {
        "authority": REVIEW_STATE_AUTHORITY,
        "canonicality": REVIEW_STATE_CANONICALITY,
        "snapshot_sha256": snapshot_sha,
        "review_group_key": content_sha,
        "review_status": None,
        "issue_reason": None,
        "owner_note": "",
        "current_sgf_answer_preserved": False,
        "historical_precomputed_rejected": False,
        "proposals": [],
        "revision": 0,
        "created_at": None,
        "updated_at": None,
    }


def _state_from_row(row, snapshot_sha, content_sha):
    row = _row_dict(row)
    if not row:
        return _blank_state(snapshot_sha, content_sha)
    state = _blank_state(snapshot_sha, content_sha)
    state.update(
        {
            "review_status": row["review_status"],
            "issue_reason": row["issue_reason"],
            "owner_note": row["owner_note"] or "",
            "current_sgf_answer_preserved": bool(row["current_sgf_answer_preserved"]),
            "historical_precomputed_rejected": bool(row["historical_precomputed_rejected"]),
            "proposals": json.loads(row["proposals_json"] or "[]"),
            "revision": row["revision"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    )
    return state


def _state_payload_for_audit(state):
    return {
        key: copy.deepcopy(state[key])
        for key in (
            "review_status",
            "issue_reason",
            "owner_note",
            "current_sgf_answer_preserved",
            "historical_precomputed_rejected",
            "proposals",
        )
    }


def _current_state(conn, owner_user_id, snapshot_sha, content_sha):
    row = conn.execute(
        """SELECT * FROM sgf_answer_review_states
           WHERE owner_user_id=? AND snapshot_sha256=? AND content_sha256=?""",
        (owner_user_id, snapshot_sha, content_sha),
    ).fetchone()
    return _state_from_row(row, snapshot_sha, content_sha)


def list_owner_review_states(conn, owner_user_id, snapshot_sha):
    rows = conn.execute(
        """SELECT * FROM sgf_answer_review_states
           WHERE owner_user_id=? AND snapshot_sha256=?
           ORDER BY updated_at, content_sha256""",
        (owner_user_id, snapshot_sha),
    ).fetchall()
    return {
        row["content_sha256"]: _state_from_row(row, snapshot_sha, row["content_sha256"])
        for row in rows
    }


def get_owner_progress(conn, owner_user_id, snapshot_sha):
    row = conn.execute(
        """SELECT current_content_sha256, revision, updated_at
           FROM sgf_answer_review_progress
           WHERE owner_user_id=? AND snapshot_sha256=?""",
        (owner_user_id, snapshot_sha),
    ).fetchone()
    row = _row_dict(row)
    if not row:
        return {"current_review_group_key": None, "revision": 0, "updated_at": None}
    return {
        "current_review_group_key": row["current_content_sha256"],
        "revision": row["revision"],
        "updated_at": row["updated_at"],
    }


def _validate_mutation_id(value):
    if not isinstance(value, str) or not _MUTATION_ID_RE.fullmatch(value):
        raise InvalidReviewRequest("mutation_id is invalid")
    return value


def _validate_expected_revision(value):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InvalidReviewRequest("expected_revision must be a non-negative integer")
    return value


def _mutation_replay(conn, owner_user_id, mutation_id, request_sha):
    row = conn.execute(
        """SELECT request_sha256, response_json
           FROM sgf_answer_review_mutations
           WHERE owner_user_id=? AND mutation_id=?""",
        (owner_user_id, mutation_id),
    ).fetchone()
    row = _row_dict(row)
    if not row:
        return None
    if row["request_sha256"] != request_sha:
        raise MutationIdConflict("mutation_id was already used for a different request")
    response = json.loads(row["response_json"])
    response["idempotent_replay"] = True
    return response


def _store_mutation(conn, owner_user_id, mutation_id, request_sha, response, now):
    conn.execute(
        """INSERT INTO sgf_answer_review_mutations
           (owner_user_id, mutation_id, request_sha256, response_json, created_at)
           VALUES(?,?,?,?,?)""",
        (owner_user_id, mutation_id, request_sha, _canonical_json(response), now),
    )


def _point_occupied(group, point):
    return any(
        stone["x"] == point["x"] and stone["y"] == point["y"]
        for stone in group["board_preview"]["initial_stones"]
    )


def _proposal_provenance(source, group):
    return {
        "identity_boundary": "AUDIT_LOCATOR_ONLY",
        "review_deduplication_only": True,
        "snapshot_sha256": source["source_snapshot"]["sha256"],
        "validation_pack_id": source["validation_pack_id"],
        "content_sha256": group["review_group_key"],
        "legacy_question_ids": [record["legacy_question_id"] for record in group["linked_records"]],
        "audit_locators": [record["audit_locator"] for record in group["linked_records"]],
    }


def _normalize_proposals(source, group, proposals, *, owner_user_id, now):
    if not isinstance(proposals, list) or len(proposals) > 25:
        raise InvalidReviewRequest("proposals must be a list with at most 25 entries")
    normalized = OrderedDict()
    board_size = group["board_size"]
    current_points = {(move["x"], move["y"]) for move in group["current_first_solution_moves"]}
    replacement_points = set()
    provenance = _proposal_provenance(source, group)
    for raw in proposals:
        if not isinstance(raw, Mapping):
            raise InvalidReviewRequest("proposal must be an object")
        proposal_type = raw.get("type")
        if proposal_type not in PROPOSAL_TYPES:
            raise InvalidReviewRequest("unsupported proposal type")
        proposal = {
            "authority": PROPOSAL_AUTHORITY,
            "canonicality": PROPOSAL_CANONICALITY,
            "type": proposal_type,
            "owner_user_id": owner_user_id,
            "review_group_key": group["review_group_key"],
            "original_answers": copy.deepcopy(group["current_first_solution_moves"]),
            "affected_review_group": copy.deepcopy(provenance),
            "staged_at": now,
        }
        if proposal_type in ("REPLACE_PRIMARY_ANSWER", "ADD_EQUIVALENT_SOLUTION"):
            try:
                point = _clean_move(
                    raw.get("proposed_move"), board_size=board_size, name="proposed_move"
                )
            except ValueError as error:
                raise InvalidReviewRequest(str(error)) from error
            if _point_occupied(group, point):
                raise InvalidReviewRequest("proposed move is occupied in the initial position")
            if proposal_type == "REPLACE_PRIMARY_ANSWER":
                replacement_points.add((point["x"], point["y"]))
            if proposal_type == "ADD_EQUIVALENT_SOLUTION" and (point["x"], point["y"]) in current_points:
                raise InvalidReviewRequest("equivalent proposal already exists in native answers")
            proposal["proposed_move"] = point
            semantic_key = f"{proposal_type}:{point['x']}:{point['y']}"
        elif proposal_type == "SET_SIDE_TO_MOVE":
            side = raw.get("proposed_side_to_move")
            if side not in ("B", "W"):
                raise InvalidReviewRequest("proposed_side_to_move must be B or W")
            proposal["original_side_to_move"] = group["side_to_move"]
            proposal["proposed_side_to_move"] = side
            proposal["source_position_includes_answer"] = bool(
                raw.get("source_position_includes_answer")
            )
            semantic_key = proposal_type
        elif proposal_type == "SOURCE_POSITION_INCLUDES_ANSWER":
            proposal["source_position_includes_answer"] = True
            semantic_key = proposal_type
        elif proposal_type == "NEEDS_SOURCE_RECONSTRUCTION":
            proposal["needs_source_reconstruction"] = True
            proposal["source_position_includes_answer"] = bool(
                raw.get("source_position_includes_answer")
            )
            semantic_key = proposal_type
        else:
            proposal["historical_precomputed_moves"] = copy.deepcopy(
                group["historical_precomputed_moves"]
            )
            semantic_key = proposal_type
        proposal["proposal_id"] = hashlib.sha256(
            f"{group['review_group_key']}:{semantic_key}".encode("utf-8")
        ).hexdigest()[:24]
        if semantic_key in normalized:
            raise InvalidReviewRequest("duplicate proposal semantics")
        normalized[semantic_key] = proposal
    if replacement_points and replacement_points == current_points:
        raise InvalidReviewRequest("replacement answer set matches current native answers")
    return list(normalized.values())


def _normalize_review_payload(source, group, payload, *, owner_user_id, now):
    allowed = {
        "mutation_id",
        "expected_revision",
        "review_status",
        "issue_reason",
        "owner_note",
        "current_sgf_answer_preserved",
        "historical_precomputed_rejected",
        "proposals",
        "resume_group_key",
    }
    if not isinstance(payload, Mapping) or set(payload) - allowed:
        raise InvalidReviewRequest("review payload contains unsupported fields")
    status = payload.get("review_status")
    if status not in REVIEW_STATUSES:
        raise InvalidReviewRequest("invalid review_status")
    reason = payload.get("issue_reason")
    if status == "CONFIRMED_ISSUE":
        if reason not in ISSUE_REASONS:
            raise InvalidReviewRequest("confirmed issue requires a valid issue_reason")
    elif reason is not None:
        raise InvalidReviewRequest("issue_reason is only valid for confirmed issues")
    note = str(payload.get("owner_note") or "").strip()
    if len(note) > 500 or (note and reason != "OTHER"):
        raise InvalidReviewRequest("owner_note is only available for OTHER and is limited to 500")
    proposals = _normalize_proposals(
        source,
        group,
        payload.get("proposals") or [],
        owner_user_id=owner_user_id,
        now=now,
    )
    types = {proposal["type"] for proposal in proposals}
    if "REPLACE_PRIMARY_ANSWER" in types and status != "CONFIRMED_ISSUE":
        raise InvalidReviewRequest("primary answer replacement requires CONFIRMED_ISSUE")
    if "ADD_EQUIVALENT_SOLUTION" in types and status not in (
        "POSSIBLE_MULTIPLE_SOLUTION",
        "CONFIRMED_ISSUE",
    ):
        raise InvalidReviewRequest("equivalent solution proposal requires multiple/confirmed review")
    historical_rejected = bool(payload.get("historical_precomputed_rejected"))
    if historical_rejected and "REJECT_HISTORICAL_PRECOMPUTED_FALLBACK" not in types:
        raise InvalidReviewRequest("historical rejection requires a structured proposal")
    return {
        "review_status": status,
        "issue_reason": reason,
        "owner_note": note,
        "current_sgf_answer_preserved": bool(payload.get("current_sgf_answer_preserved")),
        "historical_precomputed_rejected": historical_rejected,
        "proposals": proposals,
    }


def _validate_resume_group(source, value):
    if value is None:
        return None
    return review_group_by_key(source, value)["review_group_key"]


def _write_progress(conn, owner_user_id, snapshot_sha, group_key, now):
    row = conn.execute(
        """SELECT revision FROM sgf_answer_review_progress
           WHERE owner_user_id=? AND snapshot_sha256=?""",
        (owner_user_id, snapshot_sha),
    ).fetchone()
    row = _row_dict(row)
    if row:
        conn.execute(
            """UPDATE sgf_answer_review_progress
               SET current_content_sha256=?, revision=?, updated_at=?
               WHERE owner_user_id=? AND snapshot_sha256=? AND revision=?""",
            (group_key, row["revision"] + 1, now, owner_user_id, snapshot_sha, row["revision"]),
        )
    else:
        conn.execute(
            """INSERT INTO sgf_answer_review_progress
               (owner_user_id, snapshot_sha256, current_content_sha256, revision, updated_at)
               VALUES(?,?,?,?,?)""",
            (owner_user_id, snapshot_sha, group_key, 1, now),
        )


def _write_state(conn, owner_user_id, snapshot_sha, content_sha, before, after, now):
    new_revision = before["revision"] + 1
    if before["revision"] == 0:
        conn.execute(
            """INSERT INTO sgf_answer_review_states
               (owner_user_id,snapshot_sha256,content_sha256,review_status,issue_reason,
                owner_note,current_sgf_answer_preserved,historical_precomputed_rejected,
                proposals_json,revision,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                owner_user_id,
                snapshot_sha,
                content_sha,
                after["review_status"],
                after["issue_reason"],
                after["owner_note"],
                int(after["current_sgf_answer_preserved"]),
                int(after["historical_precomputed_rejected"]),
                _canonical_json(after["proposals"]),
                new_revision,
                now,
                now,
            ),
        )
        created_at = now
    else:
        cursor = conn.execute(
            """UPDATE sgf_answer_review_states
               SET review_status=?,issue_reason=?,owner_note=?,current_sgf_answer_preserved=?,
                   historical_precomputed_rejected=?,proposals_json=?,revision=?,updated_at=?
               WHERE owner_user_id=? AND snapshot_sha256=? AND content_sha256=? AND revision=?""",
            (
                after["review_status"],
                after["issue_reason"],
                after["owner_note"],
                int(after["current_sgf_answer_preserved"]),
                int(after["historical_precomputed_rejected"]),
                _canonical_json(after["proposals"]),
                new_revision,
                now,
                owner_user_id,
                snapshot_sha,
                content_sha,
                before["revision"],
            ),
        )
        if cursor.rowcount != 1:
            raise StaleReviewRevision("review state changed concurrently")
        created_at = before["created_at"]
    result = _blank_state(snapshot_sha, content_sha)
    result.update(copy.deepcopy(after))
    result.update({"revision": new_revision, "created_at": created_at, "updated_at": now})
    return result


def save_group_review(conn, source, *, owner_user_id, group_key, payload, now=None):
    group = review_group_by_key(source, group_key)
    snapshot_sha = source["source_snapshot"]["sha256"]
    mutation_id = _validate_mutation_id(payload.get("mutation_id") if isinstance(payload, Mapping) else None)
    expected_revision = _validate_expected_revision(payload.get("expected_revision"))
    request_sha = _sha256(_canonical_json({"action": "SAVE_REVIEW", "group": group_key, "payload": payload}).encode("utf-8"))
    replay = _mutation_replay(conn, owner_user_id, mutation_id, request_sha)
    if replay:
        return replay
    timestamp = _utc_now_text(now)
    before = _current_state(conn, owner_user_id, snapshot_sha, group_key)
    if before["revision"] != expected_revision:
        raise StaleReviewRevision("expected_revision does not match server state")
    after = _normalize_review_payload(
        source, group, payload, owner_user_id=owner_user_id, now=timestamp
    )
    state = _write_state(
        conn, owner_user_id, snapshot_sha, group_key, before, after, timestamp
    )
    resume_key = _validate_resume_group(source, payload.get("resume_group_key"))
    if resume_key is not None:
        _write_progress(conn, owner_user_id, snapshot_sha, resume_key, timestamp)
    conn.execute(
        """INSERT INTO sgf_answer_review_audit
           (owner_user_id,snapshot_sha256,content_sha256,revision,mutation_id,action,
            before_json,after_json,created_at)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (
            owner_user_id,
            snapshot_sha,
            group_key,
            state["revision"],
            mutation_id,
            "SAVE_REVIEW",
            _canonical_json(_state_payload_for_audit(before)),
            _canonical_json(_state_payload_for_audit(state)),
            timestamp,
        ),
    )
    response = {
        "ok": True,
        "action": "SAVE_REVIEW",
        "state": state,
        "progress": get_owner_progress(conn, owner_user_id, snapshot_sha),
        "idempotent_replay": False,
    }
    _store_mutation(conn, owner_user_id, mutation_id, request_sha, response, timestamp)
    return response


def undo_group_review(conn, source, *, owner_user_id, group_key, payload, now=None):
    review_group_by_key(source, group_key)
    if not isinstance(payload, Mapping) or set(payload) - {
        "mutation_id",
        "expected_revision",
        "resume_group_key",
    }:
        raise InvalidReviewRequest("undo payload contains unsupported fields")
    snapshot_sha = source["source_snapshot"]["sha256"]
    mutation_id = _validate_mutation_id(payload.get("mutation_id"))
    expected_revision = _validate_expected_revision(payload.get("expected_revision"))
    request_sha = _sha256(_canonical_json({"action": "UNDO_REVIEW", "group": group_key, "payload": payload}).encode("utf-8"))
    replay = _mutation_replay(conn, owner_user_id, mutation_id, request_sha)
    if replay:
        return replay
    before = _current_state(conn, owner_user_id, snapshot_sha, group_key)
    if before["revision"] == 0 or before["revision"] != expected_revision:
        raise StaleReviewRevision("there is no matching review revision to undo")
    audit = conn.execute(
        """SELECT before_json FROM sgf_answer_review_audit
           WHERE owner_user_id=? AND snapshot_sha256=? AND content_sha256=? AND revision=?""",
        (owner_user_id, snapshot_sha, group_key, before["revision"]),
    ).fetchone()
    audit = _row_dict(audit)
    if not audit:
        raise StaleReviewRevision("audit history for current revision is unavailable")
    restored = json.loads(audit["before_json"])
    timestamp = _utc_now_text(now)
    state = _write_state(
        conn, owner_user_id, snapshot_sha, group_key, before, restored, timestamp
    )
    resume_key = _validate_resume_group(source, payload.get("resume_group_key"))
    if resume_key is not None:
        _write_progress(conn, owner_user_id, snapshot_sha, resume_key, timestamp)
    conn.execute(
        """INSERT INTO sgf_answer_review_audit
           (owner_user_id,snapshot_sha256,content_sha256,revision,mutation_id,action,
            before_json,after_json,created_at)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (
            owner_user_id,
            snapshot_sha,
            group_key,
            state["revision"],
            mutation_id,
            "UNDO_REVIEW",
            _canonical_json(_state_payload_for_audit(before)),
            _canonical_json(_state_payload_for_audit(state)),
            timestamp,
        ),
    )
    response = {
        "ok": True,
        "action": "UNDO_REVIEW",
        "state": state,
        "progress": get_owner_progress(conn, owner_user_id, snapshot_sha),
        "idempotent_replay": False,
    }
    _store_mutation(conn, owner_user_id, mutation_id, request_sha, response, timestamp)
    return response


def save_owner_progress(conn, source, *, owner_user_id, payload, now=None):
    if not isinstance(payload, Mapping) or set(payload) != {"mutation_id", "review_group_key"}:
        raise InvalidReviewRequest("progress payload fields are invalid")
    mutation_id = _validate_mutation_id(payload.get("mutation_id"))
    group_key = _validate_resume_group(source, payload.get("review_group_key"))
    snapshot_sha = source["source_snapshot"]["sha256"]
    request_sha = _sha256(_canonical_json({"action": "SET_PROGRESS", "payload": payload}).encode("utf-8"))
    replay = _mutation_replay(conn, owner_user_id, mutation_id, request_sha)
    if replay:
        return replay
    timestamp = _utc_now_text(now)
    _write_progress(conn, owner_user_id, snapshot_sha, group_key, timestamp)
    response = {
        "ok": True,
        "action": "SET_PROGRESS",
        "progress": get_owner_progress(conn, owner_user_id, snapshot_sha),
        "idempotent_replay": False,
    }
    _store_mutation(conn, owner_user_id, mutation_id, request_sha, response, timestamp)
    return response


def owner_review_summary(source, states):
    counts = {
        "total_groups": source["review_group_count"],
        "pending": source["review_group_count"],
        "reviewed": 0,
        "confirmed_issue": 0,
        "possible_multiple_solution": 0,
        "uncertain": 0,
        "no_issue": 0,
        "staged_repair_groups": 0,
        "staged_proposals": 0,
    }
    for state in states.values():
        status = state.get("review_status")
        if status:
            counts["reviewed"] += 1
            counts["pending"] -= 1
        if status == "CONFIRMED_ISSUE":
            counts["confirmed_issue"] += 1
        elif status == "POSSIBLE_MULTIPLE_SOLUTION":
            counts["possible_multiple_solution"] += 1
        elif status == "UNCERTAIN":
            counts["uncertain"] += 1
        elif status == "NO_ISSUE":
            counts["no_issue"] += 1
        proposals = state.get("proposals") or []
        if proposals:
            counts["staged_repair_groups"] += 1
            counts["staged_proposals"] += len(proposals)
    return counts
