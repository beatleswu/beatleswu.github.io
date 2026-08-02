"""Sprint 2 protocol, authority, adapter, and settlement coverage."""

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from map_battle_persistence import ensure_map_battle_tables
from map_battle_runtime import (
    AttemptExpired,
    FEATURE_DISABLED_HTTP_STATUS,
    ForbiddenClientAuthority,
    JudgeOutcome,
    RequestRejected,
    canonicalize_answer,
    calculate_damage,
    issue_attempt_for_context,
    judge_map_battle_answer_v1,
    settle_answer,
)
from map_battle_persistence import create_map_battle


QUESTION = {
    "id": 7001,
    "source": "sprint2/fixture.sgf",
    "content": "(;SZ[19];B[dd];W[ee])",
    "monster_atk": 6,
}
QUESTION_REVISION = hashlib.sha256(QUESTION["content"].encode("utf-8")).hexdigest()


@pytest.fixture()
def battle_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO users(id) VALUES (?)", [(101,), (202,)])
    ensure_map_battle_tables(conn)
    create_map_battle(
        conn,
        battle_id="battle-s2",
        user_id=101,
        zone_key="legacy::forest",
        player_hp=20,
        player_hp_max=20,
        monster_hp=20,
        monster_hp_max=20,
        now="2026-08-02T00:00:00+00:00",
    )
    issue_attempt_for_context(
        conn,
        user_id=101,
        battle_id="battle-s2",
        question=QUESTION,
        initial_position_identity="position-s2",
        board_size=19,
        player_color="B",
        transform_version="transform-v1",
        transform_id="identity",
        attempt_id="attempt-s2",
        issued_at="2026-08-02T00:00:00+00:00",
        expires_at="2026-08-03T00:00:00+00:00",
    )
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()


def _payload(conn, *, moves, nonce="nonce-s2", battle_revision=0):
    attempt = conn.execute(
        "SELECT * FROM map_battle_attempts WHERE id=?", ("attempt-s2",)
    ).fetchone()
    return {
        "battle_id": attempt["battle_id"],
        "attempt_id": attempt["id"],
        "submission_nonce": nonce,
        "battle_revision": battle_revision,
        "question_revision": attempt["question_revision"],
        "player_color": "black",
        "transform_id": attempt["transform_id"],
        "transform_version": attempt["transform_version"],
        "moves": moves,
    }


def _settle(conn, payload):
    return settle_answer(
        conn,
        user_id=101,
        payload=payload,
        question_loader=lambda question_id: QUESTION if question_id == QUESTION["id"] else None,
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
        now="2026-08-02T00:01:00+00:00",
    )


def test_canonicalization_is_deterministic_and_excludes_authority_fields(battle_db):
    payload = _payload(battle_db, moves=[{"x": 3, "y": 3}])
    attempt = dict(battle_db.execute("SELECT * FROM map_battle_attempts WHERE id='attempt-s2'").fetchone())
    first = canonicalize_answer(payload, attempt)
    second = canonicalize_answer(json.loads(json.dumps(payload)), attempt)
    assert first.payload == second.payload
    assert first.payload["moves"] == [{"action": "play", "color": "B", "x": 3, "y": 3}]
    with pytest.raises(ForbiddenClientAuthority):
        canonicalize_answer({**payload, "grade": 5}, attempt)


@pytest.mark.parametrize(
    "moves,reason",
    [([], "empty_sequence"), ([{"action": "pass"}], "pass_not_allowed"),
     ([{"x": 99, "y": 3}], "coordinate_out_of_bounds"),
     ([{"x": 3, "y": 3}, {"x": 3, "y": 3}], "duplicate_move")],
)
def test_invalid_sequences_are_invalid_without_damage(battle_db, moves, reason):
    payload = _payload(battle_db, moves=moves)
    response = _settle(battle_db, payload)
    battle_db.commit()
    assert response["accepted"] is False
    assert response["result"] == "INVALID"
    assert response["damage_to_monster"] == 0
    assert response["damage_to_player"] == 0
    assert response["battle_revision"] == 0
    assert tuple(battle_db.execute("SELECT monster_hp, player_hp FROM map_battles").fetchone()) == (20, 20)
    assert battle_db.execute("SELECT settlement_state FROM map_battle_submissions").fetchone()[0] == "REJECTED"


def test_server_judge_and_damage_matrix(battle_db):
    correct = _settle(battle_db, _payload(battle_db, moves=[{"x": 3, "y": 3}]))
    battle_db.commit()
    assert correct["result"] == "CORRECT"
    assert correct["authoritative_grade"] == 5
    assert correct["damage_to_monster"] == 5
    assert correct["damage_to_player"] == 0
    assert correct["monster_hp_after"] == 15
    assert correct["player_hp_after"] == 20
    assert correct["battle_revision"] == 1


def test_wrong_answer_is_server_incorrect_and_player_damage(battle_db):
    wrong = _settle(battle_db, _payload(battle_db, moves=[{"x": 0, "y": 0}]))
    battle_db.commit()
    assert wrong["result"] == "INCORRECT"
    assert wrong["damage_to_monster"] == 0
    assert wrong["damage_to_player"] == 6
    assert wrong["monster_hp_after"] == 20
    assert wrong["player_hp_after"] == 14


def test_duplicate_same_request_is_exactly_once_and_conflict_is_rejected(battle_db):
    payload = _payload(battle_db, moves=[{"x": 3, "y": 3}])
    first = _settle(battle_db, payload)
    battle_db.commit()
    duplicate = _settle(battle_db, payload)
    assert duplicate["duplicate"] is True
    assert duplicate["battle_revision"] == first["battle_revision"] == 1
    assert duplicate["damage_to_monster"] == first["damage_to_monster"]
    with pytest.raises(RequestRejected):
        _settle(battle_db, {**payload, "moves": [{"x": 0, "y": 0}]})
    assert battle_db.execute("SELECT COUNT(*) FROM map_battle_submissions").fetchone()[0] == 1


def test_forged_fields_cross_account_and_revision_mismatch_are_rejected(battle_db):
    payload = _payload(battle_db, moves=[{"x": 3, "y": 3}])
    with pytest.raises(ForbiddenClientAuthority):
        _settle(battle_db, {**payload, "damage_to_monster": 999})
    with pytest.raises(RequestRejected):
        settle_answer(
            battle_db,
            user_id=202,
            payload=payload,
            question_loader=lambda _: QUESTION,
            mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
        )
    with pytest.raises(RequestRejected):
        _settle(battle_db, {**payload, "battle_revision": 1})
    assert battle_db.execute("SELECT COUNT(*) FROM map_battle_submissions").fetchone()[0] == 0


def test_judge_never_uses_client_grade_and_unavailable_judge_is_retryable(battle_db):
    attempt = dict(battle_db.execute("SELECT * FROM map_battle_attempts WHERE id='attempt-s2'").fetchone())
    canonical = canonicalize_answer(_payload(battle_db, moves=[{"x": 3, "y": 3}]), attempt)
    outcome = judge_map_battle_answer_v1(QUESTION, attempt, canonical)
    assert outcome == JudgeOutcome("CORRECT", 5, "map-battle-judge-v1", "answer_tree_reply_leaf")
    assert calculate_damage("INVALID", None, 20, QUESTION) == (0, 0)


def test_feature_off_and_dark_never_create_settlement(battle_db):
    payload = _payload(battle_db, moves=[{"x": 3, "y": 3}])
    with pytest.raises(Exception) as error:
        settle_answer(
            battle_db, user_id=101, payload=payload,
            question_loader=lambda _: QUESTION,
            mode_environ={"E10_MAP_BATTLE_V1_MODE": "off"},
        )
    assert error.value.code == "map_battle_v1_disabled"
    dark = settle_answer(
        battle_db, user_id=101, payload=payload,
        question_loader=lambda _: QUESTION,
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "dark"},
    )
    assert dark["settlement"] is False
    assert battle_db.execute("SELECT COUNT(*) FROM map_battle_submissions").fetchone()[0] == 0


def test_expired_attempt_is_rejected_before_reservation(battle_db):
    battle_db.execute(
        "UPDATE map_battle_attempts SET expires_at=? WHERE id=?",
        ("2026-08-02T00:01:00+00:00", "attempt-s2"),
    )
    with pytest.raises(AttemptExpired):
        settle_answer(
            battle_db,
            user_id=101,
            payload=_payload(battle_db, moves=[{"x": 3, "y": 3}]),
            question_loader=lambda _: QUESTION,
            mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
            now="2026-08-02T00:02:00+00:00",
        )
    assert battle_db.execute("SELECT COUNT(*) FROM map_battle_submissions").fetchone()[0] == 0


def test_shared_frontend_adapter_has_one_endpoint_and_no_srs_fallback():
    adapter = Path(__file__).parents[1] / "js" / "map_battle_v1_adapter.js"
    content = adapter.read_text(encoding="utf-8")
    assert "POST" in content
    assert "/api/adventure/map-battles/v1/answers" in content
    assert "api/srs/review" not in content
    assert "legacy: makeAdapter('legacy-adventure-map')" in content
    assert "e10: makeAdapter('e10-world-map')" in content


def test_legacy_question_runtime_uses_the_shared_adapter_without_an_active_state():
    index = Path(__file__).parents[1] / "index.html"
    content = index.read_text(encoding="utf-8")
    assert "async function _submitMapBattleV1IfActive" in content
    assert "if (!_mapBattleV1IsActive()) return null;" in content
    assert "_mapBattleMoves.push({ action: 'play', x, y });" in content
    assert "if (_mapBattleV1IsActive())" in content
    assert "_setMapBattleV1QuestionState(q);" in content
    assert "if (mapBattleResponse.ok !== false) SRS.markSeen(currentQ.id);" in content
