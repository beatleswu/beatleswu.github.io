"""Bounded Admin Workbench V2-A review-core API.

The API exposes one question context at a time and persists only human
classification/progress state.  It deliberately has no repair or apply route.
Corpus review indexing is bulk/cached so a 40K-question review session does
not issue one database query per record.
"""

from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, session

from sgf_workbench_v2a import (
    HUMAN_REVIEW_CLASSIFICATIONS,
    build_question_context,
    ensure_human_review_table,
    load_human_review_index,
    record_hash,
    review_state_from_index,
    save_human_review_state,
)


_CACHE_LOCK = threading.RLock()
_RECORD_HASH_CACHE: dict[tuple, list[str]] = {}
_MATCH_CACHE: dict[tuple, list[tuple[int, dict, dict]]] = {}


def _json_no_store(payload, status=200):
    response = jsonify(payload)
    response.status_code = status
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def create_sgf_workbench_v2a_blueprint(*, admin_required, get_db_provider,
                                       load_questions, questions_snapshot_sha,
                                       csrf_failure, csrf_header, csrf_token,
                                       origin_failure=None):
    blueprint = Blueprint("sgf_workbench_v2a", __name__)

    def records():
        values = load_questions() or []
        if not isinstance(values, list):
            raise ValueError("question corpus must be a list")
        return values

    def snapshot_sha():
        value = questions_snapshot_sha()
        return str(value) if value else hashlib.sha256(b"sgf-workbench-v2a-empty-snapshot").hexdigest()

    def _record_cache_key(values, snapshot):
        # Object identities detect corpus reorder/re-ingestion without reading
        # or hashing every JSON byte on each request.
        return (str(snapshot), tuple(id(record) for record in values))

    def _record_hashes(values, snapshot):
        key = _record_cache_key(values, snapshot)
        with _CACHE_LOCK:
            cached = _RECORD_HASH_CACHE.get(key)
            if cached is not None:
                return cached
        hashes = [record_hash(record) if isinstance(record, dict) else "" for record in values]
        with _CACHE_LOCK:
            _RECORD_HASH_CACHE[key] = hashes
            if len(_RECORD_HASH_CACHE) > 8:
                _RECORD_HASH_CACHE.pop(next(iter(_RECORD_HASH_CACHE)))
        return hashes

    def _summary(record, index, review, digest):
        return {
            "record_index": int(index),
            "legacy_question_id": record.get("id", record.get("question_id")),
            "source": record.get("source") or record.get("source_path"),
            "source_question_number": next((record.get(key) for key in
                ("source_question_number", "question_number", "problem_number", "number")
                if record.get(key) not in (None, "")), None),
            "reviewed_record_sha256": digest,
            "review_state": review.get("state", "UNREVIEWED"),
            "classification": review.get("classification"),
            "reviewed_at": review.get("updated_at") or review.get("reviewed_at"),
        }

    def _review(review_index, reviewer_id, index, record, digest):
        return review_state_from_index(
            review_index, reviewer_id=reviewer_id, record_index=index,
            legacy_question_id=record.get("id", record.get("question_id")),
            current_record_sha256=digest,
        )

    def _matches(record, review, search, filter_name, source):
        if source and str(record.get("source") or record.get("source_path") or "") != source:
            return False
        needle = str(search or "").strip().lower()
        if needle:
            values = [str(record.get(key) or "") for key in
                      ("id", "question_id", "source", "source_path", "source_question_number",
                       "question_number", "problem_number", "number")]
            if not any(needle in value.lower() for value in values):
                return False
        filter_name = str(filter_name or "ALL").upper()
        if filter_name in ("ALL", ""):
            return True
        if filter_name == "UNREVIEWED":
            return review.get("state") == "UNREVIEWED"
        if filter_name == "CONTENT_CHANGED":
            return review.get("state") == "CONTENT_CHANGED"
        return review.get("state") == "CURRENT" and review.get("classification") == filter_name

    def _progress(conn, reviewer_id, snapshot):
        row = conn.execute(
            """SELECT record_index, legacy_question_id, record_sha256, revision, updated_at
                 FROM sgf_human_review_progress
                WHERE reviewer_id=? AND snapshot_sha256=?""",
            (reviewer_id, snapshot),
        ).fetchone()
        snapshot_changed = False
        if not row:
            row = conn.execute(
                """SELECT record_index, legacy_question_id, record_sha256, revision, updated_at
                     FROM sgf_human_review_progress
                    WHERE reviewer_id=? ORDER BY updated_at DESC, id DESC LIMIT 1""",
                (reviewer_id,),
            ).fetchone()
            snapshot_changed = row is not None
        if not row:
            return {"record_index": None, "legacy_question_id": None,
                    "record_sha256": None, "revision": 0, "updated_at": None,
                    "state": "NONE", "snapshot_changed": False}
        get = row.__getitem__ if hasattr(row, "keys") else lambda key: row[key]
        return {
            "record_index": get("record_index"),
            "legacy_question_id": get("legacy_question_id"),
            "record_sha256": get("record_sha256"),
            "revision": get("revision"),
            "updated_at": get("updated_at"),
            "state": "SAVED",
            "snapshot_changed": snapshot_changed,
        }

    def _write_progress(conn, reviewer_id, snapshot, locator):
        timestamp = datetime.now(timezone.utc).isoformat()
        row = conn.execute(
            "SELECT revision FROM sgf_human_review_progress WHERE reviewer_id=? AND snapshot_sha256=?",
            (reviewer_id, snapshot),
        ).fetchone()
        get = row.__getitem__ if row is not None and hasattr(row, "keys") else (lambda key: row[0])
        revision = (int(get("revision")) + 1) if row else 1
        conn.execute(
            """INSERT INTO sgf_human_review_progress
               (reviewer_id, snapshot_sha256, record_index, legacy_question_id,
                record_sha256, revision, updated_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(reviewer_id, snapshot_sha256)
               DO UPDATE SET record_index=excluded.record_index,
                             legacy_question_id=excluded.legacy_question_id,
                             record_sha256=excluded.record_sha256,
                             revision=excluded.revision,
                             updated_at=excluded.updated_at""",
            (reviewer_id, snapshot, int(locator["record_index"]),
             str(locator["legacy_question_id"]), str(locator["record_sha256"]),
             revision, timestamp),
        )
        return _progress(conn, reviewer_id, snapshot)

    def _filtered(values, snapshot, reviewer_id, search, filter_name, source,
                  review_index, hashes):
        identity = _record_cache_key(values, snapshot)
        key = (identity, int(reviewer_id), str(search or ""), str(filter_name or "ALL").upper(), str(source or ""))
        with _CACHE_LOCK:
            cached = _MATCH_CACHE.get(key)
            if cached is not None:
                return cached
        output = []
        for index, record in enumerate(values):
            if not isinstance(record, dict) or record.get("id", record.get("question_id")) in (None, ""):
                continue
            digest = hashes[index]
            review = _review(review_index, reviewer_id, index, record, digest)
            if _matches(record, review, search, filter_name, source):
                output.append((index, record, review))
        with _CACHE_LOCK:
            _MATCH_CACHE[key] = output
            if len(_MATCH_CACHE) > 24:
                _MATCH_CACHE.pop(next(iter(_MATCH_CACHE)))
        return output

    def _clear_match_cache():
        with _CACHE_LOCK:
            _MATCH_CACHE.clear()

    def _position(matches, current_index):
        indexes = [index for index, _record, _review in matches]
        if current_index not in indexes:
            return 0, indexes
        return indexes.index(current_index) + 1, indexes

    def _navigation(matches, current_index):
        position, indexes = _position(matches, current_index)
        zero = position - 1
        return position, {
            "previous_record_index": indexes[zero - 1] if zero > 0 else None,
            "next_record_index": indexes[zero + 1] if zero + 1 < len(indexes) else None,
        }

    def _security():
        return {"csrf_header": csrf_header, "csrf_token": csrf_token()}

    @blueprint.route("/api/admin/sgf-workbench-v2a/bootstrap")
    @blueprint.route("/api/admin/sgf-answer-review/v2a/bootstrap")
    @admin_required
    def bootstrap():
        try:
            reviewer_id = int(session["user_id"])
            search = request.args.get("search", "")
            filter_name = request.args.get("filter", "ALL")
            source = request.args.get("source", "")
            requested = request.args.get("record_index")
            limit = max(1, min(int(request.args.get("limit", 100)), 200))
            values = records()
            snapshot = snapshot_sha()
            hashes = _record_hashes(values, snapshot)
            with get_db_provider() as conn:
                review_index = load_human_review_index(conn, reviewer_id)
                matches = _filtered(values, snapshot, reviewer_id, search, filter_name, source,
                                    review_index, hashes)
                progress = _progress(conn, reviewer_id, snapshot)
                current_index = None
                resume_state = "NONE"
                if requested not in (None, ""):
                    try:
                        candidate = int(requested)
                    except (TypeError, ValueError):
                        candidate = -1
                    if any(index == candidate for index, _record, review_item in matches):
                        current_index = candidate
                if current_index is None and progress.get("record_index") is not None:
                    candidate = int(progress["record_index"])
                    for index, record, review_item in matches:
                        if (index == candidate and
                                str(record.get("id", record.get("question_id"))) == str(progress.get("legacy_question_id")) and
                                hashes[index] == progress.get("record_sha256")):
                            current_index = index
                            resume_state = "CURRENT"
                            break
                if current_index is None and progress.get("record_index") is not None:
                    resume_state = "RESUME_LOCATOR_STALE"
                    old_index = int(progress.get("record_index"))
                    stale_candidates = [(index, record, review_item) for index, record, review_item in matches
                                        if index > old_index and review_item.get("state") == "UNREVIEWED"]
                    if not stale_candidates:
                        stale_candidates = [(index, record, review_item) for index, record, review_item in matches
                                            if review_item.get("state") == "UNREVIEWED"]
                    if stale_candidates:
                        current_index = stale_candidates[0][0]
                if current_index is None and matches:
                    current_index = matches[0][0]
                    if resume_state == "NONE":
                        resume_state = "FIRST_MATCH"
                current_position, navigation = _navigation(matches, current_index)
                current = None
                if current_index is not None:
                    record = next(record for index, record, review_item in matches if index == current_index)
                    review = _review(review_index, reviewer_id, current_index, record, hashes[current_index])
                    current = build_question_context(record, record_index=current_index,
                                                     reviewer_id=reviewer_id, review_state=review)
            return _json_no_store({
                "ok": True, "current": current,
                "items": [_summary(record, index, review_item, hashes[index]) for index, record, review_item in matches[:limit]],
                "current_position": current_position, "total": len(matches),
                "navigation": navigation, "progress": progress, "resume_state": resume_state,
                "snapshot_sha256": snapshot, "classifications": list(HUMAN_REVIEW_CLASSIFICATIONS),
                "security": _security(),
                "safety": {"canonical_questions_mutated": False, "direct_apply_used": False},
            })
        except (ValueError, KeyError) as error:
            return _json_no_store({"ok": False, "error": "invalid_request", "detail": str(error)}, 400)

    @blueprint.route("/api/admin/sgf-workbench-v2a/questions/<int:record_index>")
    @blueprint.route("/api/admin/sgf-answer-review/v2a/questions/<int:record_index>")
    @admin_required
    def question(record_index):
        reviewer_id = int(session["user_id"])
        values = records()
        if record_index < 0 or record_index >= len(values) or not isinstance(values[record_index], dict):
            return _json_no_store({"ok": False, "error": "question_not_found"}, 404)
        snapshot = snapshot_sha()
        hashes = _record_hashes(values, snapshot)
        search, filter_name, source = request.args.get("search", ""), request.args.get("filter", "ALL"), request.args.get("source", "")
        with get_db_provider() as conn:
            review_index = load_human_review_index(conn, reviewer_id)
            matches = _filtered(values, snapshot, reviewer_id, search, filter_name, source,
                                review_index, hashes)
            record = values[record_index]
            review = _review(review_index, reviewer_id, record_index, record, hashes[record_index])
            context = build_question_context(record, record_index=record_index,
                                             reviewer_id=reviewer_id, review_state=review)
        position, navigation = _navigation(matches, record_index)
        return _json_no_store({"ok": True, "question": context,
                               "current_position": position, "total": len(matches),
                               "navigation": navigation, "snapshot_sha256": snapshot,
                               "security": _security()})

    def _mutation_guard():
        if origin_failure is not None:
            failure = origin_failure()
            if failure is not None:
                return failure
        if not request.is_json:
            return _json_no_store({"ok": False, "error": "json_required",
                                   "detail": "JSON request body required"}, 415)
        return csrf_failure()

    @blueprint.route("/api/admin/sgf-workbench-v2a/reviews", methods=["POST"])
    @blueprint.route("/api/admin/sgf-answer-review/v2a/reviews", methods=["POST"])
    @admin_required
    def review():
        failure = _mutation_guard()
        if failure is not None:
            return failure
        data = request.get_json(silent=True) or {}
        classification = str(data.get("classification") or "").upper()
        if classification not in HUMAN_REVIEW_CLASSIFICATIONS:
            return _json_no_store({"ok": False, "error": "invalid_classification"}, 400)
        try:
            index = int(data.get("record_index"))
        except (TypeError, ValueError):
            return _json_no_store({"ok": False, "error": "invalid_record_index"}, 400)
        values = records()
        if index < 0 or index >= len(values) or not isinstance(values[index], dict):
            return _json_no_store({"ok": False, "error": "question_not_found"}, 404)
        record = values[index]
        legacy_id = record.get("id", record.get("question_id"))
        expected_hash = record_hash(record)
        if (str(data.get("legacy_question_id")) != str(legacy_id) or
                str(data.get("reviewed_record_sha256") or "").lower() != expected_hash):
            return _json_no_store({"ok": False, "error": "stale_review_locator", "state": "CONTENT_CHANGED"}, 409)
        with get_db_provider() as conn:
            ensure_human_review_table(conn)
            result = save_human_review_state(
                conn, reviewer_id=int(session["user_id"]), record_index=index,
                legacy_question_id=legacy_id, reviewed_record_sha256=expected_hash,
                classification=classification, schema_ready=True,
            )
        _clear_match_cache()
        return _json_no_store({"ok": True, "review": result, "canonical_questions_mutated": False})

    @blueprint.route("/api/admin/sgf-workbench-v2a/progress", methods=["POST"])
    @blueprint.route("/api/admin/sgf-answer-review/v2a/progress", methods=["POST"])
    @admin_required
    def progress():
        failure = _mutation_guard()
        if failure is not None:
            return failure
        data = request.get_json(silent=True) or {}
        try:
            index = int(data.get("record_index"))
        except (TypeError, ValueError):
            return _json_no_store({"ok": False, "error": "invalid_record_index"}, 400)
        values = records()
        if index < 0 or index >= len(values) or not isinstance(values[index], dict):
            return _json_no_store({"ok": False, "error": "question_not_found"}, 404)
        record = values[index]
        locator = {"record_index": index,
                   "legacy_question_id": record.get("id", record.get("question_id")),
                   "record_sha256": record_hash(record)}
        snap = snapshot_sha()
        with get_db_provider() as conn:
            ensure_human_review_table(conn)
            result = _write_progress(conn, int(session["user_id"]), snap, locator)
        return _json_no_store({"ok": True, "progress": result, "resume_locator": locator})

    return blueprint
