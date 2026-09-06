from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

import pytest

import sgf_admin_workbench as wb


EXACT_UUID = "00000000-0000-0000-0000-000000000431"
CONTENT_SHA = "a" * 64


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    wb.ensure_sgf_workbench_tables(conn)
    return conn


def _record():
    return {
        "id": 431,
        "source": "fixture",
        "content": "(;GM[1]FF[4]SZ[19]PL[B];B[dd])",
        "accepted_moves": [{"x": 3, "y": 3}],
        "enabled": True,
    }


def _identity(status="EXACT"):
    values = {
        "status": status,
        "legacy_question_id": "431",
        "reason": "fixture",
        "candidates": [],
    }
    if status == "EXACT":
        values.update({
            "source_record_uuid": EXACT_UUID,
            "source_record_uuid_attached": True,
            "authority_review_can_be_admitted": True,
        })
    return values


def _capture(conn, *, key="shadow-report"):
    return wb.capture_workbench_report(
        conn,
        source="ADMIN_PLAY",
        reporter_id=7,
        question_id=431,
        record_index=0,
        issue_type="SYSTEM_ANSWER_INCORRECT",
        candidate_move={"x": 4, "y": 4},
        gameplay_surface="map_battle_shadow_review",
        question_content_sha256=CONTENT_SHA,
        source_provenance={"fixture": True},
        external_key=key,
        now="2026-01-01T00:00:00+00:00",
    )


def _stage(conn, *, identity=None, key="shadow-repair"):
    record = _record()
    capture = _capture(conn, key=f"report-{key}")
    repair = wb.stage_shadow_reviewed_authority(
        conn,
        item_id=capture["review_item_id"],
        reviewer_id=7,
        identity=identity or _identity(),
        reviewed_moves=[{"x": 4, "y": 4}],
        verdict="APPROVED_CORRECT_MOVE_SET",
        original_state={
            "question_id": 431,
            "record_index": 0,
            "accepted_moves": record["accepted_moves"],
            "enabled": True,
        },
        current_content_sha256=CONTENT_SHA,
        current_record_hash=wb.direct_record_hash(record),
        source_provenance={"fixture": True},
        mutation_key=key,
        now="2026-01-01T00:00:01+00:00",
    )
    return capture, repair


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("AMBIGUOUS", "AMBIGUOUS"),
        ("MISSING", "MISSING"),
        ("UNAVAILABLE", "UNAVAILABLE"),
        ("RETIRED", "RETIRED_NON_ATTACHABLE"),
    ],
)
def test_identity_non_exact_results_fail_closed(status, expected):
    conn = _db()
    raw = {"status": status}
    if status == "RETIRED":
        raw.update({"source_record_uuid": "retired-but-not-attachable", "attachable": False})
    if status == "AMBIGUOUS":
        raw["candidates"] = ["candidate-a", "candidate-b"]
    identity = wb.resolve_source_record_identity(conn, 431, resolver=lambda _qid: raw)
    assert identity["status"] == expected
    assert identity["source_record_uuid"] is None
    assert identity["source_record_uuid_attached"] is False
    assert identity["authority_review_can_be_admitted"] is False
    with pytest.raises(wb.ShadowReviewIdentityError):
        _stage(conn, identity=identity, key=f"closed-{status.lower()}")


def test_exact_identity_binding_is_attached_without_minting():
    conn = _db()
    identity = wb.resolve_source_record_identity(
        conn, 431,
        resolver=lambda _qid: {
            "status": "EXACT",
            "source_record_uuid": EXACT_UUID,
            "attachable": True,
        },
    )
    assert identity["status"] == "EXACT"
    assert identity["source_record_uuid"] == EXACT_UUID
    assert identity["source_record_uuid_attached"] is True
    assert "uuid.uuid4" not in Path("sgf_admin_workbench.py").read_text(encoding="utf-8")


def test_record_index_alone_and_accepted_moves_alone_cannot_create_authority():
    conn = _db()
    report = _capture(conn, key="legacy-only-report")
    with pytest.raises(wb.ShadowReviewIdentityError):
        wb.stage_shadow_reviewed_authority(
            conn,
            item_id=report["review_item_id"],
            reviewer_id=7,
            identity=wb.resolve_source_record_identity(
                conn, 431, resolver=lambda _qid: {"status": "MISSING"}
            ),
            reviewed_moves=[{"x": 4, "y": 4}],
            verdict="APPROVED_CORRECT_MOVE_SET",
            original_state={"record_index": 0, "accepted_moves": [{"x": 3, "y": 3}]},
            current_content_sha256=CONTENT_SHA,
            current_record_hash=wb.direct_record_hash(_record()),
            mutation_key="legacy-only-repair",
        )
    assert conn.execute("SELECT COUNT(*) FROM sgf_workbench_staged_repairs").fetchone()[0] == 0


def test_explicit_human_review_creates_shadow_state_in_existing_stage_and_audit():
    conn = _db()
    capture, repair = _stage(conn)
    item = wb.get_workbench_item(conn, capture["review_item_id"])
    assert repair["status"] == "STAGED"
    assert repair["runtime_authority"] is False
    shadow = repair["shadow_reviewed_authority"]
    assert shadow["mode"] == "SHADOW"
    assert shadow["review_verdict"] == "APPROVED_CORRECT_MOVE_SET"
    assert shadow["source_record_uuid"] == EXACT_UUID
    assert shadow["source_record_uuid_attached"] is True
    assert shadow["runtime_authority"] is False
    assert item["status"] == "STAGED"
    assert item["authority"]["shadow_reviewed_authority"]["source_record_uuid"] == EXACT_UUID
    audit_actions = [row[0] for row in conn.execute("SELECT action FROM sgf_workbench_audit ORDER BY id")]
    assert "STAGED_REPAIR" in audit_actions
    assert "SHADOW_AUTHORITY_REVIEWED" in audit_actions


def test_shadow_validation_records_retest_and_stale_basis_fails_closed():
    conn = _db()
    capture, repair = _stage(conn)
    record = _record()
    validated = wb.validate_staged_repair(
        conn,
        repair_id=repair["id"],
        actor_id=7,
        current_record=record,
        current_content_sha256=CONTENT_SHA,
        current_record_hash=wb.direct_record_hash(record),
        verdict_fn=lambda _record, _move: True,
        now="2026-01-01T00:00:02+00:00",
    )
    assert validated["status"] == "PASS"
    shadow = validated["repair"]["source_provenance"]["shadow_reviewed_authority"]
    assert shadow["validation_status"] == "PASS"
    assert shadow["retest_result"]["status"] == "PASS"

    stale = wb.validate_staged_repair(
        conn,
        repair_id=repair["id"],
        actor_id=7,
        current_record=record,
        current_content_sha256="b" * 64,
        current_record_hash=wb.direct_record_hash(record),
        now="2026-01-01T00:00:03+00:00",
    )
    assert stale["status"] == "STALE"
    assert "canonical_content_basis_changed" in stale["errors"]
    assert stale["repair"]["source_provenance"]["shadow_reviewed_authority"]["stale"] is True
    assert stale["repair"]["source_provenance"]["shadow_reviewed_authority"]["authority_review_can_be_admitted"] is False
    assert wb.get_workbench_item(conn, capture["review_item_id"])["status"] == "STALE"


def test_ready_for_apply_remains_non_applied_and_direct_apply_stays_off():
    conn = _db()
    capture, repair = _stage(conn, key="ready-shadow")
    record = _record()
    assert wb.validate_staged_repair(
        conn,
        repair_id=repair["id"],
        actor_id=7,
        current_record=record,
        current_content_sha256=CONTENT_SHA,
        current_record_hash=wb.direct_record_hash(record),
        verdict_fn=lambda _record, _move: True,
        now="2026-01-01T00:00:02+00:00",
    )["status"] == "PASS"
    batch = wb.create_workbench_batch(
        conn, created_by=7, require_validation=True, idempotency_key="ready-shadow-batch"
    )
    ready = wb.mark_batch_ready_for_apply(
        conn,
        batch_id=batch["id"],
        actor_id=7,
        current_bases={capture["review_item_id"]: {
            "content_sha256": CONTENT_SHA,
            "record_hash": wb.direct_record_hash(record),
        }},
    )
    assert ready["status"] == "READY_FOR_APPLY"
    assert ready["canonical_mutation"] is False
    assert ready["apply_enabled"] is False
    assert wb.workbench_constants()["apply_enabled"] is False
    assert wb.SHADOW_REVIEWED_AUTHORITY_ACTION not in wb.WORKBENCH_ACTIONS
    assert conn.execute("SELECT COUNT(*) FROM sgf_workbench_direct_versions").fetchone()[0] == 0


def test_shadow_route_reuses_existing_workbench_and_fail_closes_identity(tmp_path, monkeypatch):
    from flask import Flask
    import sgf_answer_review_routes as routes

    records_path = tmp_path / "questions.json"
    records_path.write_text(json.dumps([_record()]), encoding="utf-8")
    monkeypatch.setenv("QUESTIONS_JSON_PATH", str(records_path))
    conn = _db()

    @contextmanager
    def provider():
        yield conn

    def admin_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            return view(*args, **kwargs)
        return wrapped

    app = Flask(__name__)
    app.secret_key = "shadow-route-test"
    app.register_blueprint(routes.create_sgf_answer_review_blueprint(
        admin_required=admin_required, get_db_provider=provider
    ))
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
        session["is_admin"] = True
    monkeypatch.setattr(routes, "resolve_source_record_identity", lambda _conn, _qid: _identity())
    context = client.get(
        "/api/admin/sgf-answer-review/shadow/context?record_index=0&legacy_question_id=431"
    )
    assert context.status_code == 200
    payload = context.get_json()
    headers = {payload["security"]["csrf_header"]: payload["security"]["csrf_token"]}
    response = client.post(
        "/api/admin/sgf-answer-review/shadow/review",
        json={
            "operation": "ADD_ALTERNATIVE_CORRECT_MOVE",
            "record_index": 0,
            "legacy_question_id": 431,
            "reviewed_record_sha256": wb.direct_record_hash(_record()),
            "candidate_move": {"x": 4, "y": 4},
            "selected_node_id": "0",
        },
        headers=headers,
    )
    assert response.status_code == 200
    result = response.get_json()
    assert result["shadow_reviewed_authority"]["source_record_uuid"] == EXACT_UUID
    assert result["runtime_authority_changed"] is False
    assert conn.execute("SELECT COUNT(*) FROM sgf_workbench_staged_repairs").fetchone()[0] == 1

    monkeypatch.setattr(routes, "resolve_source_record_identity", lambda _conn, _qid: _identity("AMBIGUOUS"))
    blocked = client.post(
        "/api/admin/sgf-answer-review/shadow/review",
        json={
            "operation": "REPLACE_CORRECT_ANSWER",
            "record_index": 0,
            "legacy_question_id": 431,
            "reviewed_record_sha256": wb.direct_record_hash(_record()),
            "candidate_move": {"x": 5, "y": 5},
        },
        headers=headers,
    )
    assert blocked.status_code == 409
    assert blocked.get_json()["source_record_uuid_attached"] is False
