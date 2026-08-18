"""Bounded Admin Workbench V2-A review-core API.

The endpoints expose one question context at a time.  They persist only human
classification/progress state and deliberately have no repair or apply route.
"""

from __future__ import annotations

import hashlib
import json
from flask import Blueprint, jsonify, request, session

from sgf_answer_review_queue import ensure_review_queue_tables
from sgf_workbench_v2a import (
    HUMAN_REVIEW_CLASSIFICATIONS,
    build_question_context,
    get_human_review_state,
    record_hash,
    save_human_review_state,
    ensure_human_review_table,
)


def _json_no_store(payload, status=200):
    response = jsonify(payload)
    response.status_code = status
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def create_sgf_workbench_v2a_blueprint(*, admin_required, get_db_provider,
                                       load_questions, questions_snapshot_sha,
                                       csrf_failure, csrf_header, csrf_token):
    blueprint = Blueprint("sgf_workbench_v2a", __name__)

    def records():
        values = load_questions() or []
        if not isinstance(values, list):
            raise ValueError("question corpus must be a list")
        return values

    def snapshot_sha():
        value = questions_snapshot_sha()
        if value:
            return str(value)
        return hashlib.sha256(b"sgf-workbench-v2a-empty-snapshot").hexdigest()

    def _summary(record, index, review):
        return {
            "record_index": int(index),
            "legacy_question_id": record.get("id", record.get("question_id")),
            "source": record.get("source") or record.get("source_path"),
            "source_question_number": next((record.get(key) for key in
                ("source_question_number", "question_number", "problem_number", "number")
                if record.get(key) not in (None, "")), None),
            "reviewed_record_sha256": record_hash(record),
            "review_state": review.get("state", "UNREVIEWED"),
            "classification": review.get("classification"),
            "reviewed_at": review.get("updated_at") or review.get("reviewed_at"),
        }

    def _review(conn, reviewer_id, index, record):
        return get_human_review_state(
            conn, reviewer_id=reviewer_id, record_index=index,
            legacy_question_id=record.get("id", record.get("question_id")),
            current_record_sha256=record_hash(record),
        )

    def _matches(record, index, review, search, filter_name, source):
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
        ensure_review_queue_tables(conn)
        row = conn.execute(
            """SELECT current_content_sha256, revision, updated_at
               FROM sgf_answer_review_progress
              WHERE owner_user_id=? AND snapshot_sha256=?""",
            (reviewer_id, snapshot),
        ).fetchone()
        snapshot_changed = False
        if not row:
            # Keep resume safe across a corpus snapshot change.  The locator
            # itself is still verified below; this is not an id-only rebind.
            row = conn.execute(
                """SELECT current_content_sha256, revision, updated_at
                   FROM sgf_answer_review_progress
                  WHERE owner_user_id=? ORDER BY updated_at DESC LIMIT 1""",
                (reviewer_id,),
            ).fetchone()
            snapshot_changed = row is not None
        if not row:
            return {"record_index": None, "legacy_question_id": None,
                    "record_sha256": None, "revision": 0, "updated_at": None,
                    "state": "NONE"}
        raw = row["current_content_sha256"] if hasattr(row, "keys") else row[0]
        try:
            locator = json.loads(raw or "{}")
        except (TypeError, ValueError):
            locator = {}
        return {
            "record_index": locator.get("record_index"),
            "legacy_question_id": locator.get("legacy_question_id"),
            "record_sha256": locator.get("record_sha256"),
            "revision": row["revision"] if hasattr(row, "keys") else row[1],
            "updated_at": row["updated_at"] if hasattr(row, "keys") else row[2],
            "state": "SAVED",
            "snapshot_changed": snapshot_changed,
        }

    def _write_progress(conn, reviewer_id, snapshot, locator):
        ensure_review_queue_tables(conn)
        timestamp = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        encoded = json.dumps(locator, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        row = conn.execute(
            "SELECT revision FROM sgf_answer_review_progress WHERE owner_user_id=? AND snapshot_sha256=?",
            (reviewer_id, snapshot),
        ).fetchone()
        revision = (int(row["revision"] if hasattr(row, "keys") else row[0]) + 1) if row else 1
        if row:
            conn.execute(
                "UPDATE sgf_answer_review_progress SET current_content_sha256=?, revision=?, updated_at=? "
                "WHERE owner_user_id=? AND snapshot_sha256=?",
                (encoded, revision, timestamp, reviewer_id, snapshot),
            )
        else:
            conn.execute(
                "INSERT INTO sgf_answer_review_progress "
                "(owner_user_id, snapshot_sha256, current_content_sha256, revision, updated_at) "
                "VALUES(?,?,?,?,?)",
                (reviewer_id, snapshot, encoded, revision, timestamp),
            )
        return _progress(conn, reviewer_id, snapshot)

    def _filtered(conn, reviewer_id, search, filter_name, source):
        output = []
        for index, record in enumerate(records()):
            if not isinstance(record, dict) or record.get("id", record.get("question_id")) in (None, ""):
                continue
            review = _review(conn, reviewer_id, index, record)
            if _matches(record, index, review, search, filter_name, source):
                output.append((index, record, review))
        return output

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
            with get_db_provider() as conn:
                ensure_human_review_table(conn)
                matches = _filtered(conn, reviewer_id, search, filter_name, source)
                progress = _progress(conn, reviewer_id, snapshot_sha())
                current_index = None
                resume_state = "NONE"
                if requested not in (None, ""):
                    try:
                        candidate = int(requested)
                    except (TypeError, ValueError):
                        candidate = -1
                    if any(index == candidate for index, _record, _review in matches):
                        current_index = candidate
                if current_index is None and progress.get("record_index") is not None:
                    candidate = int(progress["record_index"])
                    # Resume only on exact locator.  Reorder/hash drift is stale.
                    for index, record, review in matches:
                        if index == candidate and record.get("id", record.get("question_id")) == progress.get("legacy_question_id") and record_hash(record) == progress.get("record_sha256"):
                            current_index = index
                            resume_state = "CURRENT"
                            break
                if current_index is None and progress.get("record_index") is not None:
                    # Reorder/content drift makes the saved locator stale.
                    # Continue at a deterministic unreviewed record only;
                    # never infer identity from legacy_question_id alone.
                    resume_state = "RESUME_LOCATOR_STALE"
                    old_index = int(progress.get("record_index"))
                    stale_candidates = [
                        (index, record, review) for index, record, review in matches
                        if index > old_index and review.get("state") == "UNREVIEWED"
                    ]
                    if not stale_candidates:
                        stale_candidates = [
                            (index, record, review) for index, record, review in matches
                            if review.get("state") == "UNREVIEWED"
                        ]
                    if stale_candidates:
                        current_index = stale_candidates[0][0]
                if current_index is None and matches:
                    current_index = matches[0][0]
                    if resume_state == "NONE":
                        resume_state = "FIRST_MATCH"
                match_indexes = [index for index, _record, _review in matches]
                current_position = match_indexes.index(current_index) if current_index in match_indexes else 0
                current = None
                if current_index is not None:
                    record = next(record for index, record, _review in matches if index == current_index)
                    review = _review(conn, reviewer_id, current_index, record)
                    current = build_question_context(record, record_index=current_index,
                                                     reviewer_id=reviewer_id, review_state=review)
                return _json_no_store({
                    "ok": True,
                    "current": current,
                    "items": [_summary(record, index, review) for index, record, review in matches[:limit]],
                    "total": len(matches),
                    "navigation": {
                        "previous_record_index": match_indexes[current_position - 1] if current_position > 0 else None,
                        "next_record_index": match_indexes[current_position + 1] if current_position + 1 < len(match_indexes) else None,
                    },
                    "progress": progress,
                    "resume_state": resume_state,
                    "snapshot_sha256": snapshot_sha(),
                    "classifications": list(HUMAN_REVIEW_CLASSIFICATIONS),
                    "security": {"csrf_header": csrf_header, "csrf_token": csrf_token()},
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
        record = values[record_index]
        with get_db_provider() as conn:
            ensure_human_review_table(conn)
            review = _review(conn, reviewer_id, record_index, record)
            context = build_question_context(record, record_index=record_index,
                                             reviewer_id=reviewer_id, review_state=review)
        return _json_no_store({"ok": True, "question": context})

    @blueprint.route("/api/admin/sgf-workbench-v2a/reviews", methods=["POST"])
    @blueprint.route("/api/admin/sgf-answer-review/v2a/reviews", methods=["POST"])
    @admin_required
    def review():
        failure = csrf_failure()
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
            result = save_human_review_state(
                conn, reviewer_id=int(session["user_id"]), record_index=index,
                legacy_question_id=legacy_id, reviewed_record_sha256=expected_hash,
                classification=classification,
            )
        return _json_no_store({"ok": True, "review": result, "canonical_questions_mutated": False})

    @blueprint.route("/api/admin/sgf-workbench-v2a/progress", methods=["POST"])
    @blueprint.route("/api/admin/sgf-answer-review/v2a/progress", methods=["POST"])
    @admin_required
    def progress():
        failure = csrf_failure()
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
        locator = {
            "record_index": index,
            "legacy_question_id": record.get("id", record.get("question_id")),
            "record_sha256": record_hash(record),
        }
        with get_db_provider() as conn:
            result = _write_progress(conn, int(session["user_id"]), snapshot_sha(), locator)
        return _json_no_store({"ok": True, "progress": result, "resume_locator": locator})

    return blueprint
