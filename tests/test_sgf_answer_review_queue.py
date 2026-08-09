import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess

import pytest

os.environ.setdefault("SECRET_KEY", "synthetic-sgf-review-queue-test-secret")
os.environ.setdefault("SITE_URL", "http://localhost")

import app as app_module  # noqa: E402
from sgf_answer_review_queue import (  # noqa: E402
    InvalidReviewRequest,
    MutationIdConflict,
    StaleReviewRevision,
    build_review_source,
    build_review_source_bytes,
    detector_validation_pack_id,
    ensure_review_queue_tables,
    get_owner_progress,
    list_owner_review_states,
    owner_review_summary,
    save_group_review,
    save_owner_progress,
    undo_group_review,
)
from sgf_answer_review_routes import reset_review_source_cache  # noqa: E402


SNAPSHOT_SHA = "a" * 64


def _record(
    *,
    rank,
    index,
    content_sha,
    legacy_id,
    answer=(3, 3),
    historical=(15, 15),
    side="B",
    reasons=None,
    stones=None,
):
    return {
        "deterministic_rank": rank,
        "audit_locator": {
            "type": "AUDIT_LOCATOR_ONLY",
            "snapshot_sha256": SNAPSHOT_SHA,
            "record_index": index,
            "legacy_question_id": legacy_id,
            "content_sha256": content_sha,
        },
        "legacy_question_id": legacy_id,
        "source_family_if_known": "synthetic",
        "priority_tier": "P1" if rank < 3 else "P2",
        "confidence": "HIGH" if rank < 3 else "MEDIUM",
        "reason_codes": reasons or ["HIGH_CONFIDENCE_GLOBAL_TENUKI_SUSPECT"],
        "side_to_move": side,
        "side_to_move_display": (
            "黑先 / Black to play"
            if side == "B"
            else "白先 / White to play"
            if side == "W"
            else "先手不明 / Side to move unknown"
        ),
        "side_to_move_reason_codes": [] if side else ["SIDE_TO_MOVE_UNKNOWN"],
        "board_size": 19,
        "board_preview": {
            "initial_stones": stones
            or [
                {"color": "B", "x": 2, "y": 2},
                {"color": "W", "x": 2, "y": 3},
            ]
        },
        "current_first_solution_moves": (
            [{"x": answer[0], "y": answer[1], "color": side}] if answer else []
        ),
        "stored_precomputed_move_if_any": (
            {"x": historical[0], "y": historical[1]} if historical else None
        ),
    }


def _manifest():
    records = [
        _record(rank=1, index=10, content_sha="1" * 64, legacy_id=101),
        _record(
            rank=2,
            index=11,
            content_sha="1" * 64,
            legacy_id=102,
            historical=(14, 14),
        ),
        _record(
            rank=3,
            index=12,
            content_sha="2" * 64,
            legacy_id=103,
            answer=(4, 4),
            historical=None,
            side="W",
            reasons=["MULTIPLE_SOLUTION_REVIEW"],
        ),
        _record(
            rank=4,
            index=13,
            content_sha="3" * 64,
            legacy_id=104,
            answer=None,
            historical=None,
            side=None,
            reasons=["EMPTY_SOLUTION_TREE", "NO_VALID_ROOT_ANSWER"],
        ),
    ]
    return {
        "detector_version": "synthetic-v1",
        "source_snapshot": {
            "sha256": SNAPSHOT_SHA,
            "size_bytes": 999,
            "question_count": 4,
        },
        "validation_pack_id": detector_validation_pack_id(records),
        "records": records,
    }


def _connection():
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL, is_admin INTEGER NOT NULL)"
    )
    connection.executemany(
        "INSERT INTO users(id, username, is_admin) VALUES(?,?,?)",
        [(1, "owner-a", 1), (2, "owner-b", 1)],
    )
    ensure_review_queue_tables(connection)
    return connection


def _save_payload(*, mutation="save-review-0001", revision=0, resume=None, **extra):
    payload = {
        "mutation_id": mutation,
        "expected_revision": revision,
        "review_status": "NO_ISSUE",
        "issue_reason": None,
        "owner_note": "",
        "current_sgf_answer_preserved": True,
        "historical_precomputed_rejected": False,
        "proposals": [],
        "resume_group_key": resume,
    }
    payload.update(extra)
    return payload


def _source_with_native_answers(source, *moves):
    updated = copy.deepcopy(source)
    group = updated["groups"][0]
    group["current_first_solution_moves"] = [
        {"x": x, "y": y, "color": "B"} for x, y in moves
    ]
    return updated, group


class _ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        return False


@pytest.fixture()
def source():
    return build_review_source(_manifest(), detector_manifest_sha256="f" * 64)


@pytest.fixture()
def connection():
    connection = _connection()
    yield connection
    connection.close()


def test_review_source_groups_duplicate_content_without_claiming_identity(source):
    assert source["source_record_count"] == 4
    assert source["review_group_count"] == 3
    assert source["duplicate_group_count"] == 1
    assert source["records_in_duplicate_groups"] == 2
    assert [group["review_group_key"] for group in source["groups"]] == [
        "1" * 64,
        "2" * 64,
        "3" * 64,
    ]
    first = source["groups"][0]
    assert first["group_size"] == 2
    assert [item["legacy_question_id"] for item in first["linked_records"]] == [101, 102]
    assert all(
        item["audit_locator"]["type"] == "AUDIT_LOCATOR_ONLY"
        for item in first["linked_records"]
    )
    assert "NOT_CANONICAL_IDENTITY" in source["identity_boundary"]


def test_review_source_generation_is_deterministic_and_read_only():
    raw = json.dumps(_manifest(), ensure_ascii=False, sort_keys=True).encode("utf-8")
    before = bytes(raw)
    first = build_review_source_bytes(raw)
    second = build_review_source_bytes(raw)

    assert first == second
    assert raw == before
    derived = json.loads(first)
    assert derived["detector_signatures"]["detector_ranking_changed"] is False
    assert derived["detector_signatures"]["full_13085_ranking_sha256"] == (
        "e0177ab32c7c2888b51c4d0c54c7e3e58e9bd46ade1baf8504f6a3a1174eb501"
    )
    assert derived["detector_signatures"]["top_500_selection_order_sha256"] == (
        "ecd03c63d230749192fe36fb5b4aba7670d3eb07d82992428bf5aaa792aa11ed"
    )
    assert "content" not in derived["groups"][0]
    assert "sgf" not in json.dumps(derived["groups"][0]).lower()


def test_server_state_is_account_scoped_persistent_and_progress_resumable(source, connection):
    group_a, group_b = source["groups"][:2]
    response = save_group_review(
        connection,
        source,
        owner_user_id=1,
        group_key=group_a["review_group_key"],
        payload=_save_payload(resume=group_b["review_group_key"]),
    )

    assert response["state"]["review_status"] == "NO_ISSUE"
    assert response["state"]["revision"] == 1
    assert response["progress"]["current_review_group_key"] == group_b["review_group_key"]
    assert list_owner_review_states(connection, 1, SNAPSHOT_SHA)[group_a["review_group_key"]]["review_status"] == "NO_ISSUE"
    assert list_owner_review_states(connection, 2, SNAPSHOT_SHA) == {}
    assert get_owner_progress(connection, 1, SNAPSHOT_SHA)["current_review_group_key"] == group_b["review_group_key"]


def test_idempotent_retry_replays_without_duplicate_revision_or_audit(source, connection):
    group = source["groups"][0]
    payload = _save_payload(mutation="same-retry-0001")
    first = save_group_review(connection, source, owner_user_id=1, group_key=group["review_group_key"], payload=payload)
    replay = save_group_review(connection, source, owner_user_id=1, group_key=group["review_group_key"], payload=payload)

    assert first["idempotent_replay"] is False
    assert replay["idempotent_replay"] is True
    assert replay["state"]["revision"] == 1
    assert connection.execute("SELECT COUNT(*) FROM sgf_answer_review_audit").fetchone()[0] == 1


def test_mutation_id_reuse_and_stale_revision_fail_closed(source, connection):
    group = source["groups"][0]
    original = _save_payload(mutation="conflict-id-0001")
    save_group_review(connection, source, owner_user_id=1, group_key=group["review_group_key"], payload=original)

    altered = _save_payload(mutation="conflict-id-0001", review_status="UNCERTAIN", current_sgf_answer_preserved=False)
    with pytest.raises(MutationIdConflict):
        save_group_review(connection, source, owner_user_id=1, group_key=group["review_group_key"], payload=altered)

    stale = _save_payload(mutation="stale-save-0001", revision=0, review_status="UNCERTAIN", current_sgf_answer_preserved=False)
    with pytest.raises(StaleReviewRevision):
        save_group_review(connection, source, owner_user_id=1, group_key=group["review_group_key"], payload=stale)


def test_replace_add_side_source_and_reconstruction_proposals_are_structured(source, connection):
    group = source["groups"][0]
    payload = _save_payload(
        mutation="structured-proposals-0001",
        review_status="CONFIRMED_ISSUE",
        issue_reason="SOURCE_CONVERSION_OR_SIDE_TO_MOVE_ERROR",
        current_sgf_answer_preserved=False,
        proposals=[
            {"type": "REPLACE_PRIMARY_ANSWER", "proposed_move": {"x": 4, "y": 4, "color": "B"}},
            {"type": "ADD_EQUIVALENT_SOLUTION", "proposed_move": {"x": 5, "y": 5, "color": "B"}},
            {"type": "SET_SIDE_TO_MOVE", "proposed_side_to_move": "W", "source_position_includes_answer": True},
            {"type": "SOURCE_POSITION_INCLUDES_ANSWER"},
            {"type": "NEEDS_SOURCE_RECONSTRUCTION", "source_position_includes_answer": True},
        ],
    )
    response = save_group_review(connection, source, owner_user_id=1, group_key=group["review_group_key"], payload=payload)
    proposals = response["state"]["proposals"]

    assert {proposal["type"] for proposal in proposals} == {
        "REPLACE_PRIMARY_ANSWER",
        "ADD_EQUIVALENT_SOLUTION",
        "SET_SIDE_TO_MOVE",
        "SOURCE_POSITION_INCLUDES_ANSWER",
        "NEEDS_SOURCE_RECONSTRUCTION",
    }
    assert all(proposal["authority"] == "OWNER_APPROVED_REPAIR_PROPOSAL" for proposal in proposals)
    assert all(proposal["canonicality"] == "STAGED_NOT_APPLIED" for proposal in proposals)
    assert all(proposal["owner_user_id"] == 1 for proposal in proposals)
    assert all(proposal["affected_review_group"]["identity_boundary"] == "AUDIT_LOCATOR_ONLY" for proposal in proposals)


@pytest.mark.parametrize(
    ("replacement", "mutation"),
    [
        ((1, 18), "subset-keep-b1-0001"),
        ((0, 17), "subset-keep-a2-0001"),
    ],
)
def test_replace_answer_set_accepts_a_single_surviving_native_answer(
    source, connection, replacement, mutation
):
    updated, group = _source_with_native_answers(source, (0, 17), (1, 18))
    response = save_group_review(
        connection,
        updated,
        owner_user_id=1,
        group_key=group["review_group_key"],
        payload=_save_payload(
            mutation=mutation,
            review_status="CONFIRMED_ISSUE",
            issue_reason="WRONG_PRIMARY_ANSWER",
            current_sgf_answer_preserved=False,
            proposals=[
                {
                    "type": "REPLACE_PRIMARY_ANSWER",
                    "proposed_move": {"x": replacement[0], "y": replacement[1]},
                }
            ],
        ),
    )

    assert response["state"]["proposals"][0]["proposed_move"] == {
        "x": replacement[0],
        "y": replacement[1],
    }


def test_replace_answer_set_accepts_a_new_move(source, connection):
    updated, group = _source_with_native_answers(source, (0, 17), (1, 18))
    response = save_group_review(
        connection,
        updated,
        owner_user_id=1,
        group_key=group["review_group_key"],
        payload=_save_payload(
            mutation="replacement-new-b2-0001",
            review_status="CONFIRMED_ISSUE",
            issue_reason="WRONG_PRIMARY_ANSWER",
            current_sgf_answer_preserved=False,
            proposals=[
                {
                    "type": "REPLACE_PRIMARY_ANSWER",
                    "proposed_move": {"x": 1, "y": 17},
                }
            ],
        ),
    )

    assert response["state"]["proposals"][0]["proposed_move"] == {"x": 1, "y": 17}


def test_replace_answer_set_rejects_only_an_exact_native_set_no_op(source, connection):
    updated, group = _source_with_native_answers(source, (0, 17), (1, 18))
    with pytest.raises(InvalidReviewRequest, match="answer set matches current native answers"):
        save_group_review(
            connection,
            updated,
            owner_user_id=1,
            group_key=group["review_group_key"],
            payload=_save_payload(
                mutation="replacement-exact-noop-0001",
                review_status="CONFIRMED_ISSUE",
                issue_reason="WRONG_PRIMARY_ANSWER",
                current_sgf_answer_preserved=False,
                proposals=[
                    {"type": "REPLACE_PRIMARY_ANSWER", "proposed_move": {"x": 0, "y": 17}},
                    {"type": "REPLACE_PRIMARY_ANSWER", "proposed_move": {"x": 1, "y": 18}},
                ],
            ),
        )


def test_add_equivalent_solution_semantics_are_unchanged(source, connection):
    updated, group = _source_with_native_answers(source, (0, 17), (1, 18))
    accepted = save_group_review(
        connection,
        updated,
        owner_user_id=1,
        group_key=group["review_group_key"],
        payload=_save_payload(
            mutation="add-equivalent-b2-0001",
            review_status="POSSIBLE_MULTIPLE_SOLUTION",
            proposals=[
                {
                    "type": "ADD_EQUIVALENT_SOLUTION",
                    "proposed_move": {"x": 1, "y": 17},
                }
            ],
        ),
    )
    assert accepted["state"]["proposals"][0]["proposed_move"] == {"x": 1, "y": 17}

    with pytest.raises(InvalidReviewRequest, match="already exists in native answers"):
        save_group_review(
            connection,
            updated,
            owner_user_id=2,
            group_key=group["review_group_key"],
            payload=_save_payload(
                mutation="add-equivalent-b1-0001",
                review_status="POSSIBLE_MULTIPLE_SOLUTION",
                proposals=[
                    {
                        "type": "ADD_EQUIVALENT_SOLUTION",
                        "proposed_move": {"x": 1, "y": 18},
                    }
                ],
            ),
        )


def test_question_15436_can_stage_b1_only_then_reload_and_undo(connection):
    review_source = json.loads(
        (Path(__file__).resolve().parents[1] / "review_data" / "sgf_answer_review_queue_v1.json").read_text(
            encoding="utf-8"
        )
    )
    group = next(
        group
        for group in review_source["groups"]
        if any(record["legacy_question_id"] == 15436 for record in group["linked_records"])
    )
    assert [move["gtp"] for move in group["current_first_solution_moves"]] == ["A2", "B1"]

    saved = save_group_review(
        connection,
        review_source,
        owner_user_id=1,
        group_key=group["review_group_key"],
        payload=_save_payload(
            mutation="question-15436-b1-only-0001",
            review_status="CONFIRMED_ISSUE",
            issue_reason="WRONG_PRIMARY_ANSWER",
            current_sgf_answer_preserved=False,
            proposals=[
                {
                    "type": "REPLACE_PRIMARY_ANSWER",
                    "proposed_move": {"x": 1, "y": 18, "color": "W"},
                }
            ],
            resume=group["review_group_key"],
        ),
    )
    reloaded = list_owner_review_states(connection, 1, review_source["source_snapshot"]["sha256"])
    assert saved["state"]["proposals"][0]["proposed_move"] == {
        "x": 1,
        "y": 18,
        "color": "W",
    }
    assert reloaded[group["review_group_key"]]["proposals"] == saved["state"]["proposals"]

    undone = undo_group_review(
        connection,
        review_source,
        owner_user_id=1,
        group_key=group["review_group_key"],
        payload={
            "mutation_id": "question-15436-undo-0001",
            "expected_revision": saved["state"]["revision"],
            "resume_group_key": group["review_group_key"],
        },
    )
    assert undone["state"]["review_status"] is None
    assert undone["state"]["proposals"] == []



def test_owner_can_edit_a_staged_proposal_without_creating_a_duplicate(source, connection):
    group = source["groups"][0]
    first = save_group_review(
        connection,
        source,
        owner_user_id=1,
        group_key=group["review_group_key"],
        payload=_save_payload(
            mutation="proposal-edit-base-0001",
            review_status="CONFIRMED_ISSUE",
            issue_reason="WRONG_PRIMARY_ANSWER",
            current_sgf_answer_preserved=False,
            proposals=[{"type": "REPLACE_PRIMARY_ANSWER", "proposed_move": {"x": 4, "y": 4}}],
        ),
    )
    edited = save_group_review(
        connection,
        source,
        owner_user_id=1,
        group_key=group["review_group_key"],
        payload=_save_payload(
            mutation="proposal-edit-next-0001",
            revision=first["state"]["revision"],
            review_status="CONFIRMED_ISSUE",
            issue_reason="WRONG_PRIMARY_ANSWER",
            current_sgf_answer_preserved=False,
            proposals=[{"type": "REPLACE_PRIMARY_ANSWER", "proposed_move": {"x": 5, "y": 5}}],
        ),
    )
    assert edited["state"]["revision"] == 2
def test_board_proposal_coordinate_validation_rejects_occupied_and_out_of_bounds(source, connection):
    group = source["groups"][0]
    occupied = _save_payload(
        mutation="occupied-point-0001",
        review_status="CONFIRMED_ISSUE",
        issue_reason="WRONG_PRIMARY_ANSWER",
        current_sgf_answer_preserved=False,
        proposals=[{"type": "REPLACE_PRIMARY_ANSWER", "proposed_move": {"x": 2, "y": 2}}],
    )
    with pytest.raises(InvalidReviewRequest, match="occupied"):
        save_group_review(connection, source, owner_user_id=1, group_key=group["review_group_key"], payload=occupied)

    outside = copy.deepcopy(occupied)
    outside["mutation_id"] = "outside-point-0001"
    outside["proposals"][0]["proposed_move"] = {"x": 19, "y": 1}
    with pytest.raises(InvalidReviewRequest, match="maximum"):
        save_group_review(connection, source, owner_user_id=1, group_key=group["review_group_key"], payload=outside)


def test_undo_restores_previous_decision_and_preserves_audit_history(source, connection):
    group = source["groups"][0]
    saved = save_group_review(
        connection,
        source,
        owner_user_id=1,
        group_key=group["review_group_key"],
        payload=_save_payload(mutation="undo-base-0001"),
    )
    undone = undo_group_review(
        connection,
        source,
        owner_user_id=1,
        group_key=group["review_group_key"],
        payload={"mutation_id": "undo-action-0001", "expected_revision": saved["state"]["revision"], "resume_group_key": group["review_group_key"]},
    )

    assert undone["state"]["review_status"] is None
    assert undone["state"]["revision"] == 2
    assert [row[0] for row in connection.execute("SELECT action FROM sgf_answer_review_audit ORDER BY revision")] == ["SAVE_REVIEW", "UNDO_REVIEW"]


def test_progress_is_idempotent_and_summary_counts_group_once(source, connection):
    group = source["groups"][0]
    progress_payload = {"mutation_id": "progress-op-0001", "review_group_key": group["review_group_key"]}
    first = save_owner_progress(connection, source, owner_user_id=1, payload=progress_payload)
    replay = save_owner_progress(connection, source, owner_user_id=1, payload=progress_payload)
    assert first["progress"]["revision"] == replay["progress"]["revision"] == 1
    assert replay["idempotent_replay"] is True

    save_group_review(connection, source, owner_user_id=1, group_key=group["review_group_key"], payload=_save_payload(mutation="summary-save-0001"))
    summary = owner_review_summary(source, list_owner_review_states(connection, 1, SNAPSHOT_SHA))
    assert summary == {
        "total_groups": 3,
        "pending": 2,
        "reviewed": 1,
        "confirmed_issue": 0,
        "possible_multiple_solution": 0,
        "uncertain": 0,
        "no_issue": 1,
        "staged_repair_groups": 0,
        "staged_proposals": 0,
    }


@pytest.fixture()
def api_environment(tmp_path, monkeypatch):
    manifest = _manifest()
    source = build_review_source(manifest, detector_manifest_sha256="e" * 64)
    source_path = tmp_path / "review-source.json"
    source_path.write_text(json.dumps(source, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    connection = _connection()
    monkeypatch.setenv("SGF_ANSWER_REVIEW_QUEUE_SOURCE_PATH", str(source_path))
    monkeypatch.setattr(app_module, "get_db", lambda: _ConnectionContext(connection))
    reset_review_source_cache()
    yield app_module.app, connection, source
    reset_review_source_cache()
    connection.close()


def _authorize(client, user_id=1, *, admin=True):
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["username"] = f"owner-{user_id}"
        session["is_admin"] = admin


def _review_csrf_headers(client):
    response = client.get("/api/admin/sgf-answer-review/bootstrap")
    assert response.status_code == 200
    security = response.get_json()["security"]
    assert security["same_session_required"] is True
    assert security["same_origin_required"] is True
    return {security["csrf_header"]: security["csrf_token"]}


def test_real_admin_auth_protects_page_script_and_api(api_environment):
    flask_app, _connection_value, _source = api_environment
    anonymous = flask_app.test_client()
    assert anonymous.get("/admin/sgf-answer-review").status_code == 302
    assert anonymous.get("/api/admin/sgf-answer-review/bootstrap").status_code == 401

    ordinary = flask_app.test_client()
    _authorize(ordinary, admin=False)
    assert ordinary.get("/admin/sgf-answer-review").status_code == 302
    assert ordinary.get("/api/admin/sgf-answer-review/bootstrap").status_code == 403

    admin = flask_app.test_client()
    _authorize(admin)
    assert admin.get("/admin/sgf-answer-review").status_code == 200
    assert admin.get("/admin/sgf-answer-review.js").status_code == 200
    bootstrap = admin.get("/api/admin/sgf-answer-review/bootstrap")
    assert bootstrap.status_code == 200
    bootstrap_payload = bootstrap.get_json()
    assert bootstrap_payload["owner"]["account_scoped"] is True
    assert bootstrap_payload["security"]["csrf_header"] == "X-SGF-Answer-Review-CSRF"
    assert len(bootstrap_payload["security"]["csrf_token"]) >= 32


def test_review_writes_require_same_session_csrf_after_admin_auth(api_environment):
    flask_app, _connection_value, source = api_environment
    admin = flask_app.test_client()
    other_admin = flask_app.test_client()
    ordinary = flask_app.test_client()
    _authorize(admin)
    _authorize(other_admin, 2)
    _authorize(ordinary, 3, admin=False)
    group = source["groups"][0]
    url = f"/api/admin/sgf-answer-review/groups/{group['review_group_key']}"
    payload = _save_payload(mutation="csrf-save-0001")

    assert flask_app.test_client().post(url, json=payload).status_code == 401
    assert ordinary.post(url, json=payload).status_code == 403
    missing = admin.post(url, json=payload)
    assert missing.status_code == 403
    assert missing.get_json()["error"] == "review_csrf_failed"

    other_headers = _review_csrf_headers(other_admin)
    wrong_session = admin.post(url, json=payload, headers=other_headers)
    assert wrong_session.status_code == 403
    assert wrong_session.get_json()["error"] == "review_csrf_failed"

    valid = admin.post(url, json=payload, headers=_review_csrf_headers(admin))
    assert valid.status_code == 200


def test_review_api_does_not_expose_bootstrap_or_writes_cross_origin(api_environment):
    flask_app, _connection_value, source = api_environment
    admin = flask_app.test_client()
    _authorize(admin)

    denied_bootstrap = admin.get(
        "/api/admin/sgf-answer-review/bootstrap",
        headers={"Origin": "https://untrusted.example"},
    )
    assert denied_bootstrap.status_code == 403
    assert denied_bootstrap.get_json()["error"] == "review_origin_denied"

    headers = _review_csrf_headers(admin)
    headers["Origin"] = "https://untrusted.example"
    group = source["groups"][0]
    denied_write = admin.post(
        f"/api/admin/sgf-answer-review/groups/{group['review_group_key']}",
        json=_save_payload(mutation="cross-origin-save-0001"),
        headers=headers,
    )
    assert denied_write.status_code == 403
    assert denied_write.get_json()["error"] == "review_origin_denied"


def test_local_qa_bootstrap_is_absent_from_normal_application(api_environment):
    flask_app, _connection_value, _source = api_environment
    assert flask_app.test_client().get("/__local_qa__/owner-login").status_code == 404


def test_two_devices_share_server_state_but_different_owner_does_not(api_environment):
    flask_app, _connection_value, source = api_environment
    device_a = flask_app.test_client()
    device_b = flask_app.test_client()
    other_owner = flask_app.test_client()
    _authorize(device_a, 1)
    _authorize(device_b, 1)
    _authorize(other_owner, 2)
    group = source["groups"][0]

    response = device_a.post(
        f"/api/admin/sgf-answer-review/groups/{group['review_group_key']}",
        json=_save_payload(mutation="cross-device-save-0001", resume=source["groups"][1]["review_group_key"]),
        headers=_review_csrf_headers(device_a),
    )
    assert response.status_code == 200

    same_account = device_b.get("/api/admin/sgf-answer-review/bootstrap").get_json()
    isolated_account = other_owner.get("/api/admin/sgf-answer-review/bootstrap").get_json()
    assert same_account["states"][group["review_group_key"]]["review_status"] == "NO_ISSUE"
    assert same_account["progress"]["current_review_group_key"] == source["groups"][1]["review_group_key"]
    assert isolated_account["states"] == {}


def test_api_replay_and_stale_retry_are_deterministic(api_environment):
    flask_app, connection, source = api_environment
    client = flask_app.test_client()
    _authorize(client)
    group = source["groups"][0]
    payload = _save_payload(mutation="api-retry-save-0001")
    url = f"/api/admin/sgf-answer-review/groups/{group['review_group_key']}"
    headers = _review_csrf_headers(client)

    first = client.post(url, json=payload, headers=headers)
    replay = client.post(url, json=payload, headers=headers)
    stale = client.post(url, json=_save_payload(mutation="api-stale-save-0001", revision=0, review_status="UNCERTAIN", current_sgf_answer_preserved=False), headers=headers)

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.get_json()["idempotent_replay"] is True
    assert stale.status_code == 409
    assert stale.get_json()["error"] == "stale_review_revision"
    assert connection.execute("SELECT COUNT(*) FROM sgf_answer_review_states").fetchone()[0] == 1


def test_bundled_500_source_retains_detector_order_and_has_no_full_sgf_bytes():
    path = Path(__file__).resolve().parents[1] / "review_data" / "sgf_answer_review_queue_v1.json"
    raw = path.read_bytes()
    source = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == "ccfb20ca81a4daaa83b7b172426c490a7c732287810521caedc5782a8052b51e"
    assert source["source_record_count"] == 500
    assert source["review_group_count"] == 452
    assert source["duplicate_group_count"] == 29
    assert source["records_in_duplicate_groups"] == 77
    assert [group["group_order"] for group in source["groups"]] == list(range(452))
    assert all(group["first_deterministic_rank"] >= 1 for group in source["groups"])
    assert source["detector_signatures"]["detector_ranking_changed"] is False
    assert b"(;" not in raw
    assert b'"content"' not in raw


def test_worktree_scope_contains_no_canonical_question_or_sgf_mutation():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    changed_paths = {line[3:].replace("\\", "/") for line in result.stdout.splitlines() if len(line) > 3}

    assert "questions.json" not in changed_paths
    assert not any(path.lower().endswith(".sgf") for path in changed_paths)
    assert not any(path.startswith("sgf_engine/") for path in changed_paths)
    assert not any("accepted_moves" in path for path in changed_paths)
    assert "secret_key.txt" not in changed_paths
