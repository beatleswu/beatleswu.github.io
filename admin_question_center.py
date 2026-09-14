"""Owner-facing question-management presentation adapter.

This module deliberately owns no question-correction authority.  It reads the
existing review/report stores, normalises them for the single Owner page, and
leaves all correction writes on the established System C/D/E routes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
from pathlib import Path
import re
from typing import Any

from flask import Blueprint, jsonify, request, send_from_directory, session

from sgf_admin_workbench import (
    direct_record_hash,
    ensure_sgf_workbench_tables,
    list_workbench_items,
    list_direct_versions_for_questions,
)
from sgf_answer_review_queue import load_review_source
from sgf_workbench_v2a import load_human_review_index, record_hash, review_state_from_index


HUMAN_SECTIONS = (
    ("pending", "待處理"),
    ("reports", "玩家回報"),
    ("duplicates", "重複題"),
    ("browse", "題庫瀏覽"),
    ("modified", "已修改"),
    ("history", "歷史紀錄"),
)

REASON_LABELS = {
    "ALTERNATIVE_CORRECT_MOVE": "可能還有其他正解",
    "ALTERNATIVE_ANSWER": "可能還有其他正解",
    "SYSTEM_ANSWER_INCORRECT": "答案有問題",
    "ANSWER_SEEMS_WRONG": "答案有問題",
    "QUESTION_CONTENT_PROBLEM": "題目有問題",
    "UNCLEAR": "題目有問題",
    "BROKEN_UNANSWERABLE": "題目有問題",
    "OTHER": "其他",
    "OTHER_PROBLEM": "其他",
}

STATUS_LABELS = {
    "OPEN": "待確認",
    "STAGED": "已儲存修正版",
    "NEEDS_RESEARCH": "稍後處理",
    "PUBLISHED": "已套用",
    "APPLIED": "已套用",
    "ROLLED_BACK": "已復原",
    "REJECTED": "已確認不用修改",
    "pending": "待處理",
    "in_review": "處理中",
    "resolved": "已處理",
    "wont_fix": "先不修改",
    "open": "待確認",
    "confirmed": "已確認",
    "dismissed": "先不修改",
    "duplicate": "重複回報",
    "accepted": "已納入候選",
    "CURRENT": "已查看",
    "CONTENT_CHANGED": "需要重新確認",
    "UNREVIEWED": "可查看",
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SIZE_RE = re.compile(r"(?:^|;)SZ\[(\d+)\]", re.IGNORECASE)
_SIDE_RE = re.compile(r"(?:^|;)PL\[([BW])\]", re.IGNORECASE)


def _row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)
    except (TypeError, ValueError):
        keys = getattr(row, "keys", lambda: [])()
        return {key: row[key] for key in keys}


def _content(record: Mapping[str, Any]) -> str:
    value = record.get("content")
    if not isinstance(value, str):
        value = record.get("sgf")
    return value if isinstance(value, str) else ""


def _content_sha256(record: Mapping[str, Any]) -> str | None:
    value = _content(record)
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else None


def _record_id(record: Mapping[str, Any]) -> Any:
    return record.get("id", record.get("question_id"))


def _same_question_id(value: Any, question_id: int) -> bool:
    try:
        return int(value) == question_id
    except (TypeError, ValueError):
        return False


def _accepted_moves(record: Mapping[str, Any]) -> list[dict[str, int]]:
    raw = record.get("accepted_moves") or record.get("accepted_answers") or []
    if isinstance(raw, Mapping):
        raw = [raw]
    result: list[dict[str, int]] = []
    seen: set[tuple[int, int]] = set()
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return result
    for move in raw:
        if not isinstance(move, Mapping):
            continue
        try:
            x, y = int(move.get("x")), int(move.get("y"))
        except (TypeError, ValueError):
            continue
        if not (0 <= x < 19 and 0 <= y < 19) or (x, y) in seen:
            continue
        seen.add((x, y))
        result.append({"x": x, "y": y})
    return result


def _initial_stones(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = _content(record)
    stones: list[dict[str, Any]] = []
    for property_name, color in (("AB", "B"), ("AW", "W")):
        match = re.search(rf"{property_name}((?:\[[a-s]{{2}}\])+)", source, re.IGNORECASE)
        if not match:
            continue
        for token in re.findall(r"\[([a-s]{2})\]", match.group(1), re.IGNORECASE):
            stones.append({"color": color, "x": ord(token[0].lower()) - 97, "y": ord(token[1].lower()) - 97})
    return [stone for stone in stones if 0 <= stone["x"] < 19 and 0 <= stone["y"] < 19]


def _question_brief(record: Mapping[str, Any], *, record_index: int) -> dict[str, Any]:
    content = _content(record)
    size_match = _SIZE_RE.search(content)
    side_match = _SIDE_RE.search(content)
    return {
        "question_id": _record_id(record),
        "record_index": int(record_index),
        "topic": record.get("topic") or "",
        "level": record.get("level") or record.get("difficulty") or "",
        "source": record.get("source") or "",
        "enabled": bool(record.get("enabled", True)),
        "solution_state": record.get("solution_state") or "",
        "board_size": int(size_match.group(1)) if size_match else 19,
        "side_to_move": side_match.group(1).upper() if side_match else None,
        "board_preview": {
            "initial_stones": _initial_stones(record),
            "accepted_moves": _accepted_moves(record),
        },
    }


def _identity(
    records: Sequence[Mapping[str, Any]],
    question_id: Any,
    *,
    record_index: Any = None,
    expected_content_sha256: Any = None,
) -> dict[str, Any]:
    try:
        qid = int(question_id)
    except (TypeError, ValueError):
        return {"status": "MISSING", "message": "這題目前無法安全修改"}

    selected: tuple[int, Mapping[str, Any]] | None = None
    if record_index not in (None, ""):
        try:
            index = int(record_index)
        except (TypeError, ValueError):
            return {"status": "MISSING", "message": "這題目前無法安全修改"}
        # Callers with a record index already hold the version-scoped locator.
        # Validate that slot directly; scanning the full corpus here made the
        # 200-row browse projection O(records * browse_rows).
        if not (0 <= index < len(records)) or not _same_question_id(_record_id(records[index]), qid):
            return {"status": "STALE", "message": "題目已被更新，請重新確認"}
        selected = (index, records[index])
    else:
        matches = [(index, record) for index, record in enumerate(records) if _same_question_id(_record_id(record), qid)]
        if len(matches) == 1:
            selected = matches[0]
        elif len(matches) > 1:
            return {
                "status": "AMBIGUOUS",
                "message": "這題目前無法安全修改",
                "question_id": qid,
                "candidate_count": len(matches),
            }
        else:
            return {"status": "MISSING", "message": "這題目前無法安全修改", "question_id": qid}

    index, record = selected
    digest = _content_sha256(record)
    expected = str(expected_content_sha256 or "").lower()
    if expected and (not _SHA256_RE.fullmatch(expected) or expected != str(digest or "").lower()):
        return {
            "status": "STALE",
            "message": "題目已被更新，請重新確認",
            "question_id": qid,
            "record_index": index,
        }
    return {
        "status": "EXACT",
        "question_id": qid,
        "record_index": index,
        "content_sha256": digest,
        "record_hash": direct_record_hash(dict(record)),
        "question": _question_brief(record, record_index=index),
    }


def _human_reason(value: Any) -> str:
    raw = str(value or "OTHER").strip().upper()
    if str(value or "").strip() in {"題目有問題", "可能還有其他正解", "答案有問題", "其他"}:
        return str(value).strip()
    return REASON_LABELS.get(raw, "其他")


def _human_status(value: Any) -> str:
    raw = str(value or "").strip()
    return STATUS_LABELS.get(raw, raw or "待確認")


def _item(
    *,
    system: str,
    item_id: Any,
    source_label: str,
    reason: Any,
    status: Any,
    updated_at: Any,
    records: Sequence[Mapping[str, Any]],
    question_id: Any,
    record_index: Any = None,
    expected_content_sha256: Any = None,
    note: Any = "",
    technical: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    identity = _identity(
        records,
        question_id,
        record_index=record_index,
        expected_content_sha256=expected_content_sha256,
    )
    item = {
        "id": f"{system}:{item_id}",
        "source": source_label,
        "reason": _human_reason(reason),
        "status": _human_status(status),
        "updated_at": updated_at or "",
        "note": str(note or "")[:500],
        "identity": identity,
        "can_edit": identity.get("status") == "EXACT",
        "actions": ["CORRECT", "REPLACE_ANSWER", "ADD_ALTERNATIVE_CORRECT_MOVE", "EDIT_QUESTION", "UNSURE"],
        "technical": {"system": system, **dict(technical or {})},
    }
    if identity.get("status") == "EXACT":
        item["deep_link"] = (
            "/admin/questions?question_id="
            f"{identity['question_id']}&record_index={identity['record_index']}"
        )
    return item


def _report_rows(conn, table_name: str, *, limit: int = 200) -> list[dict[str, Any]]:
    if table_name == "question_problem_reports":
        sql = """
            SELECT id, question_id, reason_code, note, status, created_at,
                   reviewed_at, admin_note, reviewed_by
            FROM question_problem_reports
            ORDER BY CASE WHEN status='open' THEN 0 ELSE 1 END,
                     created_at DESC, id DESC LIMIT ?
        """
    else:
        sql = """
            SELECT id, question_id, wrong_move_x, wrong_move_y, note, status,
                   created_at, reviewed_at, admin_note, reviewed_by
            FROM question_alternative_reports
            ORDER BY CASE WHEN status='open' THEN 0 ELSE 1 END,
                     created_at DESC, id DESC LIMIT ?
        """
    return [_row_dict(row) for row in conn.execute(sql, (int(limit),)).fetchall()]


def _queue_rows(conn, *, limit: int = 200) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, source_type, source_ref, record_index, legacy_question_id,
               content_sha256, reason, status, resolution_action, admin_note,
               created_at, reviewed_at
        FROM corpus_review_queue
        ORDER BY CASE WHEN status IN ('pending','in_review') THEN 0 ELSE 1 END,
                 created_at DESC, id DESC LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    return [_row_dict(row) for row in rows]


def _duplicate_items(source: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for group in source.get("groups") or []:
        if not isinstance(group, Mapping) or int(group.get("group_size") or 0) < 2:
            continue
        linked = group.get("linked_records") or []
        first = linked[0] if linked and isinstance(linked[0], Mapping) else {}
        locator = first.get("audit_locator") if isinstance(first, Mapping) else {}
        result.append(
            _item(
                system="A",
                item_id=group.get("review_group_key"),
                source_label="相同題面群組",
                reason="ALTERNATIVE_CORRECT_MOVE",
                status="待確認",
                updated_at="",
                records=records,
                question_id=first.get("legacy_question_id"),
                record_index=locator.get("record_index"),
                expected_content_sha256=locator.get("content_sha256"),
                note=f"這組有 {int(group.get('group_size') or 0)} 個相同題面。",
                technical={
                    "review_group_key": group.get("review_group_key"),
                    "group_size": group.get("group_size"),
                    "priority": group.get("priority_tier"),
                },
            )
        )
    return result


def _history_items(conn: Any, records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Project System C's existing version ledger without creating a ledger."""
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    question_ids: list[int] = []
    for record in records:
        try:
            question_id = int(_record_id(record))
        except (TypeError, ValueError):
            continue
        if question_id in seen:
            continue
        seen.add(question_id)
        question_ids.append(question_id)

    versions_by_question = list_direct_versions_for_questions(
        conn, question_ids=question_ids, limit=50,
    )
    for question_id in question_ids:
        for version in versions_by_question.get(question_id, []):
            validation = version.get("validation_result") or {}
            validation_status = validation.get("status") if isinstance(validation, Mapping) else None
            result.append(
                _item(
                    system="C",
                    item_id=f"version:{version.get('id')}",
                    source_label="歷史紀錄",
                    reason=version.get("action_type") or "EDIT_QUESTION",
                    status=version.get("status") or "PUBLISHED",
                    updated_at=version.get("created_at"),
                    records=records,
                    question_id=version.get("question_id"),
                    record_index=version.get("record_index"),
                    note=(f"驗證：{validation_status or '已記錄'}；修改者：{version.get('actor_id') or '—'}"),
                    technical={
                        "version_id": version.get("id"),
                        "actor_id": version.get("actor_id"),
                        "action_type": version.get("action_type"),
                        "validation_status": validation_status,
                        "rollback_reference": version.get("rollback_reference"),
                        "was_reverted": bool(version.get("rollback_reference")),
                    },
                )
            )
    return result


def build_center_bootstrap(
    *,
    conn: Any,
    records: Sequence[Mapping[str, Any]],
    review_source_loader=load_review_source,
    direct_apply_enabled: Any = False,
    reviewer_id: int | None = None,
) -> dict[str, Any]:
    """Build a read-only projection of the existing review authorities."""

    ensure_sgf_workbench_tables(conn)
    workbench = list_workbench_items(conn, limit=200)
    queue_rows = _queue_rows(conn)
    problem_rows = _report_rows(conn, "question_problem_reports")
    alternative_rows = _report_rows(conn, "question_alternative_reports")

    pending = []
    for row in queue_rows:
        pending.append(
            _item(
                system="F",
                item_id=row.get("id"),
                source_label="待處理",
                reason=row.get("reason"),
                status=row.get("status"),
                updated_at=row.get("reviewed_at") or row.get("created_at"),
                records=records,
                question_id=row.get("legacy_question_id"),
                record_index=row.get("record_index"),
                expected_content_sha256=row.get("content_sha256"),
                note=row.get("admin_note") or row.get("reason"),
                technical={
                    "queue_id": row.get("id"),
                    "source_type": row.get("source_type"),
                    "resolution_action": row.get("resolution_action"),
                },
            )
        )
    for row in workbench:
        status = str(row.get("status") or "OPEN").upper()
        if status not in {"OPEN", "NEEDS_RESEARCH", "STAGED"}:
            continue
        pending.append(
            _item(
                system="C",
                item_id=row.get("id"),
                source_label="需要確認",
                reason=row.get("issue_type"),
                status=status,
                updated_at=row.get("updated_at") or row.get("created_at"),
                records=records,
                question_id=row.get("question_id"),
                record_index=row.get("record_index"),
                expected_content_sha256=row.get("question_content_sha256"),
                note=row.get("comment"),
                technical={"workbench_item_id": row.get("id"), "source_types": row.get("source_types")},
            )
        )

    reports = []
    for row in problem_rows:
        reports.append(
            _item(
                system="D",
                item_id=row.get("id"),
                source_label="玩家回報",
                reason=row.get("reason_code"),
                status=row.get("status"),
                updated_at=row.get("reviewed_at") or row.get("created_at"),
                records=records,
                question_id=row.get("question_id"),
                note=row.get("note") or row.get("admin_note"),
                technical={"report_id": row.get("id"), "report_type": "problem"},
            )
        )
    for row in alternative_rows:
        reports.append(
            _item(
                system="E",
                item_id=row.get("id"),
                source_label="玩家回報",
                reason="ALTERNATIVE_CORRECT_MOVE",
                status=row.get("status"),
                updated_at=row.get("reviewed_at") or row.get("created_at"),
                records=records,
                question_id=row.get("question_id"),
                note=row.get("note") or row.get("admin_note"),
                technical={
                    "report_id": row.get("id"),
                    "report_type": "alternative",
                    "reported_move": {"x": row.get("wrong_move_x"), "y": row.get("wrong_move_y")},
                },
            )
        )

    modified = []
    for row in workbench:
        status = str(row.get("status") or "").upper()
        if status not in {"STAGED", "PUBLISHED", "REJECTED"}:
            continue
        modified.append(
            _item(
                system="C",
                item_id=row.get("id"),
                source_label="已修改",
                reason=row.get("issue_type"),
                status=status,
                updated_at=row.get("updated_at") or row.get("created_at"),
                records=records,
                question_id=row.get("question_id"),
                record_index=row.get("record_index"),
                expected_content_sha256=row.get("question_content_sha256"),
                note=row.get("comment"),
                technical={"workbench_item_id": row.get("id")},
            )
        )

    try:
        review_source, evidence = review_source_loader()
        duplicates = _duplicate_items(review_source, records)
        duplicate_meta = {
            "available": True,
            "group_count": int(review_source.get("duplicate_group_count") or 0),
            "source_record_count": int(review_source.get("source_record_count") or 0),
            "artifact_sha256": evidence.get("sha256") if isinstance(evidence, Mapping) else None,
        }
    except Exception:  # read-only evidence can be unavailable without blocking C
        duplicates = []
        duplicate_meta = {"available": False, "reason": "review_source_unavailable"}

    review_index: Mapping[str, Any] = {}
    if reviewer_id is not None:
        try:
            review_index = load_human_review_index(conn, int(reviewer_id), schema_ready=False)
        except Exception:
            # B remains readable even when its optional personal verdict index
            # is unavailable; the exact question locator still fails closed.
            review_index = {}

    browse = []
    for index, record in enumerate(records[:200]):
        identity = _identity(records, _record_id(record), record_index=index)
        review = {}
        try:
            review = review_state_from_index(
                review_index,
                reviewer_id=int(reviewer_id or 0),
                record_index=index,
                legacy_question_id=_record_id(record),
                current_record_sha256=record_hash(record),
            )
        except (TypeError, ValueError, KeyError):
            review = {}
        browse.append(
            {
                "id": f"B:{index}",
                "source": "題庫",
                "reason": "",
                "status": STATUS_LABELS.get(str(review.get("state") or ""), "可查看"),
                "review_state": review.get("state", "UNREVIEWED"),
                "classification": review.get("classification"),
                "reviewed_at": review.get("updated_at") or review.get("reviewed_at"),
                "updated_at": "",
                "note": "",
                "identity": identity,
                "can_edit": identity.get("status") == "EXACT",
                "actions": ["CORRECT", "REPLACE_ANSWER", "ADD_ALTERNATIVE_CORRECT_MOVE", "EDIT_QUESTION", "UNSURE"],
                "technical": {
                    "system": "B",
                    "record_index": index,
                    "review_state": review.get("state", "UNREVIEWED"),
                    "classification": review.get("classification"),
                },
                "deep_link": (
                    f"/admin/questions?question_id={identity['question_id']}&record_index={index}"
                    if identity.get("status") == "EXACT" else None
                ),
            }
        )

    history = modified[:] + _history_items(conn, records)
    return {
        "ok": True,
        "route": "/admin/questions",
        "sections": {
            "pending": pending,
            "reports": reports,
            "duplicates": duplicates,
            "browse": browse,
            "modified": modified,
            "history": history,
        },
        "counts": {key: len(value) for key, value in {
            "pending": pending,
            "reports": reports,
            "duplicates": duplicates,
            "browse": browse,
            "modified": modified,
            "history": history,
        }.items()},
        "metadata": {
            "real_question_surfaces": 7,
            "duplicate_groups": duplicate_meta,
            "direct_apply_enabled": bool(direct_apply_enabled() if callable(direct_apply_enabled) else direct_apply_enabled),
            "production_mutation": False,
            "canonical_question_mutation": False,
            "system_f_new_writes": False,
            "system_c_correction_routes": [
                "/api/admin/sgf-workbench/flag",
                "/api/admin/sgf-workbench/items/<id>/stage",
                "/api/admin/sgf-workbench/items/<id>/validate",
            ],
            "legacy_compatibility_routes": {
                "problem_reports": "/api/admin/question-problem-reports",
                "alternative_reports": "/api/admin/question-alternative-reports",
                "review_queue": "/api/admin/review-queue",
                "v2a": "/api/admin/sgf-answer-review/v2a",
            },
        },
    }


def create_question_management_blueprint(*, admin_required, get_db_provider, load_questions, direct_apply_enabled=lambda: False):
    blueprint = Blueprint("question_management_center", __name__)
    root = Path(__file__).resolve().parent

    @blueprint.route("/admin/questions")
    @admin_required
    def question_management_page():
        response = send_from_directory(root, "admin_questions.html")
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @blueprint.route("/admin/questions.js")
    @admin_required
    def question_management_script():
        response = send_from_directory(root, "admin_questions.js", mimetype="application/javascript")
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @blueprint.route("/api/admin/questions/bootstrap")
    @admin_required
    def question_management_bootstrap():
        try:
            records = load_questions()
            if not isinstance(records, list):
                return jsonify({"ok": False, "error": "question_source_unavailable"}), 503
            with get_db_provider() as conn:
                payload = build_center_bootstrap(
                    conn=conn,
                    records=records,
                    direct_apply_enabled=direct_apply_enabled,
                    reviewer_id=int(session["user_id"]),
                )
            response = jsonify(payload)
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response
        except Exception:
            # Do not leak database/source details into the Owner UI.
            return jsonify({"ok": False, "error": "question_center_unavailable"}), 503

    return blueprint
