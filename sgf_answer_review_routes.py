"""Authenticated Flask routes for SGF answer review and repair staging."""

from __future__ import annotations

from flask import Blueprint, jsonify, request, send_from_directory, session
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


def create_sgf_answer_review_blueprint(*, admin_required, get_db_provider):
    blueprint = Blueprint("sgf_answer_review_queue", __name__)
    root = Path(__file__).resolve().parent

    @blueprint.route("/admin/sgf-answer-review")
    @admin_required
    def review_page():
        response = send_from_directory(root, "sgf_answer_review.html")
        response.headers["Cache-Control"] = "private, no-store"
        return response

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

    return blueprint
