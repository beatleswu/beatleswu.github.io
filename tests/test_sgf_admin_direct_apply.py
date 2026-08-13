import json
import sqlite3

import pytest

from sgf_admin_workbench import (
    apply_direct_question_edit,
    canonical_file_sha256,
    direct_record_hash,
    ensure_sgf_workbench_tables,
    list_direct_versions,
    rollback_direct_question_edit,
    validate_direct_record,
)


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_sgf_workbench_tables(conn)
    return conn


def _record():
    return {
        "id": 900001,
        "content": "(;GM[1]FF[4]SZ[19];B[aa])",
        "accepted_moves": [{"x": 3, "y": 3}],
        "enabled": True,
        "solution_state": "open",
    }


def _path(tmp_path):
    path = tmp_path / "questions.json"
    path.write_text(json.dumps([_record()], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def test_direct_apply_snapshots_version_and_is_idempotent(tmp_path):
    path = _path(tmp_path)
    conn = _db()
    old = _record()
    proposed = json.loads(json.dumps(old))
    proposed["accepted_moves"].append({"x": 15, "y": 3})
    old_hash = direct_record_hash(old)
    first = apply_direct_question_edit(
        conn, questions_path=str(path), actor_id=7, question_id=900001,
        record_index=0, expected_predecessor_hash=old_hash,
        expected_canonical_sha256=canonical_file_sha256(str(path)),
        action_type="ADD_ALTERNATIVE_CORRECT_MOVE", proposed_record=proposed,
        operation_id="op-1", retest_fn=lambda record: True,
        now="2026-08-12T00:00:00+00:00",
    )
    assert first["predecessor_hash"] == old_hash
    assert first["new_hash"] == direct_record_hash(proposed)
    assert json.loads(path.read_text(encoding="utf-8"))[0]["accepted_moves"][-1] == {"x": 15, "y": 3}
    duplicate = apply_direct_question_edit(
        conn, questions_path=str(path), actor_id=7, question_id=900001,
        record_index=0, expected_predecessor_hash=old_hash,
        expected_canonical_sha256=canonical_file_sha256(str(path)),
        action_type="ADD_ALTERNATIVE_CORRECT_MOVE", proposed_record=proposed,
        operation_id="op-1", retest_fn=lambda record: True,
    )
    assert duplicate["duplicate"] is True
    assert len(list_direct_versions(conn, question_id=900001)) == 1


def test_direct_apply_rejects_stale_or_invalid_without_mutating(tmp_path):
    path = _path(tmp_path)
    conn = _db()
    proposed = _record()
    proposed["accepted_moves"].append({"x": 15, "y": 3})
    before = path.read_bytes()
    with pytest.raises(ValueError, match="stale_predecessor"):
        apply_direct_question_edit(
            conn, questions_path=str(path), actor_id=7, question_id=900001,
            record_index=0, expected_predecessor_hash="0" * 64,
            expected_canonical_sha256=canonical_file_sha256(str(path)),
            action_type="ADD_ALTERNATIVE_CORRECT_MOVE", proposed_record=proposed,
            operation_id="stale", retest_fn=lambda record: True,
        )
    assert path.read_bytes() == before
    invalid = json.loads(json.dumps(proposed))
    invalid["accepted_moves"] = []
    assert validate_direct_record(invalid)["ok"] is False


def test_rollback_creates_new_version_and_restores_exact_predecessor(tmp_path):
    path = _path(tmp_path)
    conn = _db()
    old = _record()
    proposed = json.loads(json.dumps(old))
    proposed["accepted_moves"].append({"x": 14, "y": 3})
    version = apply_direct_question_edit(
        conn, questions_path=str(path), actor_id=7, question_id=900001,
        record_index=0, expected_predecessor_hash=direct_record_hash(old),
        expected_canonical_sha256=canonical_file_sha256(str(path)),
        action_type="ADD_ALTERNATIVE_CORRECT_MOVE", proposed_record=proposed,
        operation_id="op-rollback", retest_fn=lambda record: True,
    )
    restored = rollback_direct_question_edit(
        conn, questions_path=str(path), actor_id=7, version_id=version["id"],
        operation_id="rollback-op-1",
    )
    assert restored["action_type"] == "ROLLBACK"
    assert restored["new_hash"] == version["predecessor_hash"]
    assert json.loads(path.read_text(encoding="utf-8"))[0] == old
    assert len(list_direct_versions(conn, question_id=900001)) == 2


@pytest.mark.parametrize(
    ("action", "accepted_moves"),
    [
        ("REPLACE_ANSWER", [{"x": 15, "y": 3}]),
        ("REMOVE_INCORRECT_ACCEPTED_MOVE", [{"x": 15, "y": 3}]),
        ("DISABLE_BROKEN_QUESTION", [{"x": 3, "y": 3}]),
    ],
)
def test_direct_action_versions_preserve_identity(tmp_path, action, accepted_moves):
    path = _path(tmp_path)
    conn = _db()
    old = _record()
    proposed = json.loads(json.dumps(old))
    proposed["accepted_moves"] = accepted_moves
    if action == "DISABLE_BROKEN_QUESTION":
        proposed["enabled"] = False
    result = apply_direct_question_edit(
        conn, questions_path=str(path), actor_id=7, question_id=900001,
        record_index=0, expected_predecessor_hash=direct_record_hash(old),
        expected_canonical_sha256=canonical_file_sha256(str(path)),
        action_type=action, proposed_record=proposed,
        operation_id=f"op-{action}", retest_fn=lambda record: True,
    )
    assert result["action_type"] == action
    assert result["new_record"]["id"] == old["id"]


def test_normal_player_cannot_direct_apply(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "direct-apply-test")
    import app as application

    client = application.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 123
        session["is_admin"] = False
    response = client.post("/api/admin/sgf-workbench/direct-apply", json={})
    assert response.status_code == 403
