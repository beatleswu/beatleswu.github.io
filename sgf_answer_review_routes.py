"""Authenticated Flask routes for SGF answer review and repair staging."""

from __future__ import annotations

import hashlib
import json
from flask import Blueprint, Response, jsonify, request, send_from_directory, session
from datetime import datetime, timezone
import os
from pathlib import Path
import secrets
import threading
from urllib.parse import urlsplit

from sgf_answer_review_queue import (
    ReviewQueueError,
    get_owner_progress,
    list_owner_review_states,
    load_review_source,
    owner_review_summary,
    save_group_review,
    save_owner_progress,
    undo_group_review,
)
from sgf_admin_workbench import (
    ShadowReviewIdentityError,
    ShadowReviewStaleError,
    capture_workbench_report,
    direct_record_hash,
    ensure_sgf_workbench_tables,
    get_workbench_item,
    resolve_source_record_identity,
    stage_shadow_reviewed_authority,
)
from sgf_workbench_v2a import build_question_context


_SOURCE_CACHE = {}
_SOURCE_CACHE_LOCK = threading.Lock()
_REVIEW_CSRF_SESSION_KEY = "sgf_answer_review_csrf"
_REVIEW_CSRF_HEADER = "X-SGF-Answer-Review-CSRF"


def reset_review_source_cache():
    with _SOURCE_CACHE_LOCK:
        _SOURCE_CACHE.clear()


def _load_source_cached():
    configured = os.environ.get("SGF_ANSWER_REVIEW_QUEUE_SOURCE_PATH")
    default = Path(__file__).with_name("review_data") / "sgf_answer_review_queue_v1.json"
    path = Path(configured) if configured else default
    resolved = path.resolve()
    try:
        stamp = (resolved.stat().st_mtime_ns, resolved.stat().st_size)
    except OSError:
        stamp = None
    cache_key = str(resolved)
    with _SOURCE_CACHE_LOCK:
        cached = _SOURCE_CACHE.get(cache_key)
        if cached and cached[0] == stamp:
            return cached[1], cached[2]
        source, evidence = load_review_source(resolved)
        _SOURCE_CACHE.clear()
        _SOURCE_CACHE[cache_key] = (stamp, source, evidence)
        return source, evidence


def _json_no_store(payload, status=200):
    response = jsonify(payload)
    response.status_code = status
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _error_response(error):
    if isinstance(error, ReviewQueueError):
        detail = "review source is not safely available" if error.code == "review_source_unavailable" else str(error)
        return _json_no_store({"ok": False, "error": error.code, "detail": detail}, error.http_status)
    raise error


def _review_csrf_token():
    token = session.get(_REVIEW_CSRF_SESSION_KEY)
    if not isinstance(token, str) or len(token) < 32:
        token = secrets.token_urlsafe(32)
        session[_REVIEW_CSRF_SESSION_KEY] = token
    return token


def _normalized_origin(value):
    try:
        parsed = urlsplit(value or "")
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _review_origin_failure():
    supplied = request.headers.get("Origin")
    if not supplied:
        return None
    allowed = {_normalized_origin(request.host_url)}
    configured = _normalized_origin(os.environ.get("SITE_URL"))
    if configured:
        allowed.add(configured)
    if _normalized_origin(supplied) not in allowed:
        return _json_no_store(
            {
                "ok": False,
                "error": "review_origin_denied",
                "detail": "same-origin review request required",
            },
            403,
        )
    return None


def _review_csrf_failure():
    expected = session.get(_REVIEW_CSRF_SESSION_KEY)
    supplied = request.headers.get(_REVIEW_CSRF_HEADER, "")
    if (
        not isinstance(expected, str)
        or not isinstance(supplied, str)
        or not expected
        or not supplied
        or not secrets.compare_digest(expected, supplied)
    ):
        return _json_no_store(
            {
                "ok": False,
                "error": "review_csrf_failed",
                "detail": "same-session review CSRF token required",
            },
            403,
        )
    return None


def _shadow_source_path() -> Path:
    configured = os.environ.get("QUESTIONS_JSON_PATH", "questions.json").strip()
    return Path(configured or "questions.json")


def _load_shadow_records() -> list[dict]:
    """Read the current question source without creating a second source/cache."""
    path = _shadow_source_path()
    with path.open("r", encoding="utf-8") as handle:
        values = json.load(handle)
    if not isinstance(values, list):
        raise ValueError("question corpus must be a list")
    return values


def _shadow_content_sha256(record: dict) -> str:
    content = record.get("content")
    if not isinstance(content, str):
        content = record.get("sgf")
    if not isinstance(content, str):
        raise ValueError("question_content_unavailable")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _shadow_moves(record: dict) -> list[dict]:
    raw_moves = record.get("accepted_moves") or record.get("accepted_answers") or []
    if isinstance(raw_moves, dict):
        raw_moves = [raw_moves]
    if not isinstance(raw_moves, list):
        return []
    result = []
    seen = set()
    for raw in raw_moves:
        if isinstance(raw, dict):
            x, y = raw.get("x"), raw.get("y")
        elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
            x, y = raw[0], raw[1]
        else:
            continue
        try:
            move = {"x": int(x), "y": int(y)}
        except (TypeError, ValueError):
            continue
        if not (0 <= move["x"] < 19 and 0 <= move["y"] < 19):
            continue
        key = (move["x"], move["y"])
        if key not in seen:
            seen.add(key)
            result.append(move)
    return result


def _shadow_move(value: object, *, board_size: int = 19) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        x, y = int(value.get("x")), int(value.get("y"))
    except (TypeError, ValueError):
        return None
    if not (0 <= x < int(board_size) and 0 <= y < int(board_size)):
        return None
    return {"x": x, "y": y}


def _shadow_question_context(payload: dict, *, reviewer_id: int) -> dict:
    try:
        record_index = int(payload.get("record_index"))
    except (TypeError, ValueError) as error:
        raise ValueError("invalid_record_index") from error
    if record_index < 0:
        raise ValueError("invalid_record_index")
    records = _load_shadow_records()
    if record_index >= len(records) or not isinstance(records[record_index], dict):
        raise LookupError("question_not_found")
    record = records[record_index]
    legacy_id = record.get("id", record.get("question_id"))
    if legacy_id in (None, ""):
        raise ValueError("legacy_question_id_missing")
    if payload.get("legacy_question_id") not in (None, "") and str(payload.get("legacy_question_id")) != str(legacy_id):
        raise ShadowReviewStaleError("stale_shadow_locator")
    try:
        question_id = int(legacy_id)
    except (TypeError, ValueError) as error:
        raise ValueError("invalid_question_id") from error
    content_sha256 = _shadow_content_sha256(record)
    record_hash = direct_record_hash(record)
    expected_hash = payload.get("reviewed_record_sha256")
    if expected_hash not in (None, "") and str(expected_hash).lower() != record_hash:
        raise ShadowReviewStaleError("stale_shadow_review_locator")
    context = build_question_context(
        record, record_index=record_index, reviewer_id=int(reviewer_id), review_state=None
    )
    return {
        "question_id": question_id,
        "record_index": record_index,
        "legacy_question_id": legacy_id,
        "record": record,
        "record_hash": record_hash,
        "content_sha256": content_sha256,
        "accepted_moves": _shadow_moves(record),
        "context": context,
        "state": {
            "question_id": question_id,
            "record_index": record_index,
            "content_sha256": content_sha256,
            "record_hash": record_hash,
            "enabled": bool(record.get("enabled", True)),
            "solution_state": record.get("solution_state"),
            "accepted_moves": _shadow_moves(record),
            "native_sgf": record.get("native_answer") or record.get("solution"),
            "historical_katago_best_move": record.get("katago_best_move"),
        },
    }


def _latest_shadow_review(conn, *, question_id: int, record_index: int,
                          record_hash: str) -> dict | None:
    ensure_sgf_workbench_tables(conn)
    rows = conn.execute(
        "SELECT id FROM sgf_workbench_review_items "
        "WHERE question_id=? AND record_index=? ORDER BY updated_at DESC, id DESC",
        (int(question_id), int(record_index)),
    ).fetchall()
    for row in rows:
        item = get_workbench_item(conn, int(row["id"] if hasattr(row, "keys") else row[0]))
        if not item:
            continue
        for repair in reversed(item.get("staged_repairs") or []):
            provenance = repair.get("source_provenance")
            shadow = provenance.get("shadow_reviewed_authority") if isinstance(provenance, dict) else None
            if not isinstance(shadow, dict):
                continue
            if str((shadow.get("basis") or {}).get("record_hash") or "") != str(record_hash):
                continue
            return {
                "workbench_item_id": int(item["id"]),
                "workbench_item_status": item.get("status"),
                "item_updated_at": item.get("updated_at"),
                "repair_id": int(repair["id"]),
                "repair_status": repair.get("status"),
                "shadow_reviewed_authority": shadow,
            }
    return None


def _shadow_issue_type(operation: str) -> str:
    if operation == "ADD_ALTERNATIVE_CORRECT_MOVE":
        return "ALTERNATIVE_CORRECT_MOVE"
    if operation in {"REPLACE_CORRECT_ANSWER", "REMOVE_INCORRECT_ACCEPTED_MOVE"}:
        return "SYSTEM_ANSWER_INCORRECT"
    if operation in {"MARK_NEEDS_RESEARCH", "DISABLE_BROKEN_QUESTION"}:
        return "QUESTION_CONTENT_PROBLEM"
    return "OTHER"


def create_sgf_answer_review_blueprint(
    *, admin_required, get_db_provider, mutation_throttle_failure=None
):
    blueprint = Blueprint("sgf_answer_review_queue", __name__)
    root = Path(__file__).resolve().parent

    def _mutation_throttle_failure():
        if mutation_throttle_failure is None:
            return None
        return mutation_throttle_failure()

    def _legacy_page_response():
        html = (root / "sgf_answer_review.html").read_text(encoding="utf-8")
        html = html.replace(
            '<script src=' + chr(34) + '/admin/sgf-answer-review-ux-v2.js?v=2' + chr(34) + '></script>',
            "<script src='/admin/sgf-answer-review.js'></script>"
            "<script src='/admin/sgf-answer-review-legacy-ux-v2.js?v=1'></script>",
        )
        response = Response(html, mimetype="text/html")
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @blueprint.route("/admin/sgf-answer-review")
    @admin_required
    def review_page():
        if request.args.get("mode", "").lower() == "legacy":
            return _legacy_page_response()
        else:
            response = send_from_directory(root, "sgf_answer_review.html")
        response.headers["Cache-Control"] = "private, no-store"
        return response

    def review_legacy_page():
        return _legacy_page_response()
    blueprint.add_url_rule(
        "/admin/sgf-answer-review/legacy",
        endpoint="review_legacy_page_admin",
        view_func=admin_required(review_legacy_page),
    )

    @blueprint.route("/admin/sgf-answer-review.js")
    @admin_required
    def review_script():
        response = send_from_directory(root, "sgf_answer_review.js", mimetype="application/javascript")
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @blueprint.route("/admin/sgf-answer-review-ux-v2.js")
    @admin_required
    def review_ux_v2_script():
        response = send_from_directory(root, "sgf_workbench_v2a.js", mimetype="application/javascript")
        response.headers["Cache-Control"] = "private, no-store"
        return response

    def review_legacy_ux_v2_script():
        response = send_from_directory(root, "sgf_admin_workbench_ux_v2.js", mimetype="application/javascript")
        response.headers["Cache-Control"] = "private, no-store"
        return response
    blueprint.add_url_rule(
        "/admin/sgf-answer-review-legacy-ux-v2.js",
        endpoint="review_legacy_ux_v2_script_admin",
        view_func=admin_required(review_legacy_ux_v2_script),
    )

    @blueprint.route("/api/admin/sgf-answer-review/bootstrap")
    @admin_required
    def review_bootstrap():
        origin_failure = _review_origin_failure()
        if origin_failure is not None:
            return origin_failure
        try:
            source, evidence = _load_source_cached()
            owner_user_id = int(session["user_id"])
            snapshot_sha = source["source_snapshot"]["sha256"]
            with get_db_provider() as conn:
                states = list_owner_review_states(conn, owner_user_id, snapshot_sha)
                progress = get_owner_progress(conn, owner_user_id, snapshot_sha)
            return _json_no_store(
                {
                    "ok": True,
                    "owner": {
                        "user_id": owner_user_id,
                        "username": session.get("username") or "",
                        "account_scoped": True,
                    },
                    "queue_source": {
                        "schema_version": source["schema_version"],
                        "authority": source["authority"],
                        "canonicality": source["canonicality"],
                        "identity_boundary": source["identity_boundary"],
                        "review_source_id": source["review_source_id"],
                        "source_snapshot": source["source_snapshot"],
                        "validation_pack_id": source["validation_pack_id"],
                        "detector_signatures": source["detector_signatures"],
                        "source_record_count": source["source_record_count"],
                        "review_group_count": source["review_group_count"],
                        "duplicate_group_count": source["duplicate_group_count"],
                        "records_in_duplicate_groups": source["records_in_duplicate_groups"],
                        "artifact_sha256": evidence["sha256"],
                        "artifact_size_bytes": evidence["size_bytes"],
                    },
                    "groups": source["groups"],
                    "states": states,
                    "progress": progress,
                    "summary": owner_review_summary(source, states),
                    "security": {
                        "csrf_header": _REVIEW_CSRF_HEADER,
                        "csrf_token": _review_csrf_token(),
                        "same_session_required": True,
                        "same_origin_required": True,
                    },
                    "safety": {
                        "canonical_sgf_mutated": False,
                        "questions_json_mutated": False,
                        "accepted_moves_mutated": False,
                        "player_verdict_mutated": False,
                        "identity_implemented": False,
                    },
                }
            )
        except ReviewQueueError as error:
            return _error_response(error)

    @blueprint.route("/api/admin/sgf-answer-review/groups/<group_key>", methods=["POST"])
    @admin_required
    def review_save(group_key):
        origin_failure = _review_origin_failure()
        if origin_failure is not None:
            return origin_failure
        csrf_failure = _review_csrf_failure()
        if csrf_failure is not None:
            return csrf_failure
        throttle_failure = _mutation_throttle_failure()
        if throttle_failure is not None:
            return throttle_failure
        if not request.is_json:
            return _json_no_store({"ok": False, "error": "json_required"}, 415)
        try:
            source, _evidence = _load_source_cached()
            payload = request.get_json(silent=True) or {}
            with get_db_provider() as conn:
                result = save_group_review(
                    conn,
                    source,
                    owner_user_id=int(session["user_id"]),
                    group_key=group_key,
                    payload=payload,
                )
            return _json_no_store(result)
        except ReviewQueueError as error:
            return _error_response(error)

    @blueprint.route(
        "/api/admin/sgf-answer-review/groups/<group_key>/undo", methods=["POST"]
    )
    @admin_required
    def review_undo(group_key):
        origin_failure = _review_origin_failure()
        if origin_failure is not None:
            return origin_failure
        csrf_failure = _review_csrf_failure()
        if csrf_failure is not None:
            return csrf_failure
        throttle_failure = _mutation_throttle_failure()
        if throttle_failure is not None:
            return throttle_failure
        if not request.is_json:
            return _json_no_store({"ok": False, "error": "json_required"}, 415)
        try:
            source, _evidence = _load_source_cached()
            payload = request.get_json(silent=True) or {}
            with get_db_provider() as conn:
                result = undo_group_review(
                    conn,
                    source,
                    owner_user_id=int(session["user_id"]),
                    group_key=group_key,
                    payload=payload,
                )
            return _json_no_store(result)
        except ReviewQueueError as error:
            return _error_response(error)

    @blueprint.route("/api/admin/sgf-answer-review/progress", methods=["POST"])
    @admin_required
    def review_progress():
        origin_failure = _review_origin_failure()
        if origin_failure is not None:
            return origin_failure
        csrf_failure = _review_csrf_failure()
        if csrf_failure is not None:
            return csrf_failure
        throttle_failure = _mutation_throttle_failure()
        if throttle_failure is not None:
            return throttle_failure
        if not request.is_json:
            return _json_no_store({"ok": False, "error": "json_required"}, 415)
        try:
            source, _evidence = _load_source_cached()
            payload = request.get_json(silent=True) or {}
            with get_db_provider() as conn:
                result = save_owner_progress(
                    conn,
                    source,
                    owner_user_id=int(session["user_id"]),
                    payload=payload,
                )
            return _json_no_store(result)
        except ReviewQueueError as error:
            return _error_response(error)

    def shadow_context():
        origin_failure = _review_origin_failure()
        if origin_failure is not None:
            return origin_failure
        try:
            reviewer_id = int(session["user_id"])
            context = _shadow_question_context(request.args.to_dict(), reviewer_id=reviewer_id)
            with get_db_provider() as conn:
                identity = resolve_source_record_identity(conn, context["question_id"])
                latest = _latest_shadow_review(
                    conn,
                    question_id=context["question_id"],
                    record_index=context["record_index"],
                    record_hash=context["record_hash"],
                )
            return _json_no_store({
                "ok": True,
                "question_id": context["question_id"],
                "record_index": context["record_index"],
                "legacy_question_id": context["legacy_question_id"],
                "reviewed_record_sha256": context["record_hash"],
                "content_sha256": context["content_sha256"],
                "identity": identity,
                "authority": {
                    "current_accepted_moves": context["accepted_moves"],
                    "accepted_moves_classification": "HELPFUL_BUT_NOT_AUTHORITATIVE",
                    "reviewed_authority": (latest or {}).get("shadow_reviewed_authority"),
                    "runtime_authority": False,
                    "affects_progression": False,
                },
                "workbench": latest,
                "security": {
                    "csrf_header": _REVIEW_CSRF_HEADER,
                    "csrf_token": _review_csrf_token(),
                },
                "safety": {
                    "canonical_questions_mutated": False,
                    "map_battle_runtime_changed": False,
                    "progression_changed": False,
                    "direct_apply_enabled": False,
                },
            })
        except ShadowReviewStaleError as error:
            return _json_no_store({"ok": False, "error": "stale_shadow_review", "detail": str(error)}, 409)
        except LookupError as error:
            return _json_no_store({"ok": False, "error": str(error)}, 404)
        except (OSError, TypeError, ValueError) as error:
            return _json_no_store({"ok": False, "error": "shadow_context_unavailable", "detail": str(error)}, 400)

    def shadow_review():
        origin_failure = _review_origin_failure()
        if origin_failure is not None:
            return origin_failure
        csrf_failure = _review_csrf_failure()
        if csrf_failure is not None:
            return csrf_failure
        throttle_failure = _mutation_throttle_failure()
        if throttle_failure is not None:
            return throttle_failure
        if not request.is_json:
            return _json_no_store({"ok": False, "error": "json_required"}, 415)
        payload = request.get_json(silent=True) or {}
        operation = str(payload.get("operation") or "").strip().upper()
        verdict_by_operation = {
            "ADD_ALTERNATIVE_CORRECT_MOVE": "APPROVED_CORRECT_MOVE_SET",
            "REPLACE_CORRECT_ANSWER": "APPROVED_CORRECT_MOVE_SET",
            "REMOVE_INCORRECT_ACCEPTED_MOVE": "APPROVED_CORRECT_MOVE_SET",
            "MARK_NEEDS_RESEARCH": "NEEDS_RESEARCH",
            "DISABLE_BROKEN_QUESTION": "BROKEN_OR_DISABLE",
            "REJECT_NO_CHANGE": "REJECTED_NO_CHANGE",
        }
        if operation not in verdict_by_operation:
            return _json_no_store({"ok": False, "error": "invalid_shadow_operation"}, 400)
        try:
            reviewer_id = int(session["user_id"])
            context = _shadow_question_context(payload, reviewer_id=reviewer_id)
            board_size = int((context["context"].get("tree") or {}).get("board_size") or 19)
            candidate = None
            if operation in {
                "ADD_ALTERNATIVE_CORRECT_MOVE",
                "REPLACE_CORRECT_ANSWER",
                "REMOVE_INCORRECT_ACCEPTED_MOVE",
            }:
                candidate = _shadow_move(
                    payload.get("candidate_move") or payload.get("selected_move"),
                    board_size=board_size,
                )
                if candidate is None:
                    return _json_no_store({"ok": False, "error": "candidate_move_required"}, 400)
            current_moves = list(context["accepted_moves"])
            current_keys = {(move["x"], move["y"]) for move in current_moves}
            candidate_key = (candidate["x"], candidate["y"]) if candidate else None
            if operation == "ADD_ALTERNATIVE_CORRECT_MOVE":
                if candidate_key in current_keys:
                    return _json_no_store({"ok": False, "error": "candidate_already_accepted"}, 409)
                reviewed_moves = [*current_moves, candidate]
            elif operation == "REPLACE_CORRECT_ANSWER":
                reviewed_moves = [candidate]
            elif operation == "REMOVE_INCORRECT_ACCEPTED_MOVE":
                if candidate_key not in current_keys:
                    return _json_no_store({"ok": False, "error": "candidate_not_currently_accepted"}, 409)
                reviewed_moves = [move for move in current_moves if (move["x"], move["y"]) != candidate_key]
                if not reviewed_moves:
                    return _json_no_store({"ok": False, "error": "empty_reviewed_move_set"}, 409)
            else:
                reviewed_moves = current_moves

            with get_db_provider() as conn:
                identity = resolve_source_record_identity(conn, context["question_id"])
                if not identity.get("authority_review_can_be_admitted"):
                    return _json_no_store({
                        "ok": False,
                        "error": "identity_unresolved",
                        "identity": identity,
                        "source_record_uuid_attached": False,
                        "authority_review_can_be_admitted": False,
                        "runtime_authority_changed": False,
                    }, 409)
                timestamp = datetime.now(timezone.utc).isoformat()
                authority_snapshot = {
                    "current_accepted_moves": current_moves,
                    "accepted_moves_classification": "HELPFUL_BUT_NOT_AUTHORITATIVE",
                    "source_record_uuid": identity.get("source_record_uuid"),
                    "source_record_uuid_status": identity.get("status"),
                    "source_record_uuid_attached": True,
                    "runtime_authority": False,
                    "affects_progression": False,
                }
                source_provenance = {
                    "source": "MAP_BATTLE_SHADOW_REVIEW",
                    "map_battle_shadow_review": True,
                    "operation": operation,
                    "identity": identity,
                    "canonical_record_hash": context["record_hash"],
                    "reviewed_record_sha256": context["record_hash"],
                }
                material = {
                    "question_id": context["question_id"],
                    "record_index": context["record_index"],
                    "record_hash": context["record_hash"],
                    "operation": operation,
                    "reviewed_moves": reviewed_moves,
                }
                digest = hashlib.sha256(
                    json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                capture = capture_workbench_report(
                    conn,
                    source="ADMIN_PLAY",
                    reporter_id=reviewer_id,
                    question_id=context["question_id"],
                    record_index=context["record_index"],
                    issue_type=_shadow_issue_type(operation),
                    candidate_move=candidate,
                    observed_system_verdict="UNDETERMINED",
                    gameplay_surface="map_battle_shadow_review",
                    sgf_identity=context["content_sha256"],
                    node_identity=str(payload.get("selected_node_id") or "shadow-review")[:120],
                    board_state={"review_surface": "map_battle", "shadow": True},
                    question_content_sha256=context["content_sha256"],
                    authority=authority_snapshot,
                    comment=str(payload.get("note") or "")[:1000],
                    source_provenance=source_provenance,
                    external_key=f"map-battle-shadow-report:{digest}",
                    now=timestamp,
                )
                source_provenance["review_report_id"] = capture["report"].get("id")
                repair = stage_shadow_reviewed_authority(
                    conn,
                    item_id=int(capture["review_item_id"]),
                    reviewer_id=reviewer_id,
                    identity=identity,
                    reviewed_moves=reviewed_moves,
                    verdict=verdict_by_operation[operation],
                    original_state=context["state"],
                    current_content_sha256=context["content_sha256"],
                    current_record_hash=context["record_hash"],
                    reason=str(payload.get("note") or operation)[:1000],
                    source_provenance=source_provenance,
                    mutation_key=f"map-battle-shadow-repair:{reviewer_id}:{digest}",
                    expected_item_updated_at=payload.get("expected_item_updated_at"),
                    now=timestamp,
                )
                item = get_workbench_item(conn, int(capture["review_item_id"]))
            return _json_no_store({
                "ok": True,
                "shadow_reviewed_authority": repair.get("shadow_reviewed_authority"),
                "repair": repair,
                "item": item,
                "review_item_id": capture["review_item_id"],
                "runtime_authority_changed": False,
                "progression_changed": False,
                "canonical_questions_mutated": False,
                "direct_apply_enabled": False,
                "security": {
                    "csrf_header": _REVIEW_CSRF_HEADER,
                    "csrf_token": _review_csrf_token(),
                },
            })
        except ShadowReviewIdentityError as error:
            return _json_no_store({"ok": False, "error": "identity_unresolved", "detail": str(error)}, 409)
        except ShadowReviewStaleError as error:
            return _json_no_store({"ok": False, "error": "stale_shadow_review", "detail": str(error)}, 409)
        except LookupError as error:
            return _json_no_store({"ok": False, "error": str(error)}, 404)
        except (TypeError, ValueError, OSError) as error:
            return _json_no_store({"ok": False, "error": "shadow_review_rejected", "detail": str(error)}, 400)

    blueprint.add_url_rule(
        "/api/admin/sgf-answer-review/shadow/context",
        endpoint="shadow_context_admin",
        view_func=admin_required(shadow_context),
    )
    blueprint.add_url_rule(
        "/api/admin/sgf-answer-review/shadow/review",
        endpoint="shadow_review_admin",
        view_func=admin_required(shadow_review),
        methods=["POST"],
    )

    return blueprint
