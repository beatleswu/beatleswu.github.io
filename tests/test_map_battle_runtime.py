"""Sprint 2A runtime protocol, authority, and settlement coverage."""

import ast
import hashlib
import json
import sqlite3
import threading
from pathlib import Path

import pytest

from map_battle_persistence import ensure_map_battle_tables
from map_battle_runtime import (
    AttemptExpired,
    FEATURE_DISABLED_HTTP_STATUS,
    ForbiddenClientAuthority,
    JudgeOutcome,
    RequestRejected,
    SubmissionNonceAlreadyIssued,
    SubmissionNonceInvalid,
    SubmissionNonceNotIssued,
    SubmissionRequestHashMismatch,
    canonicalize_answer,
    calculate_damage,
    ensure_submission_lifecycle_schema,
    issue_submission_nonce_for_attempt,
    issue_attempt_for_context,
    judge_map_battle_answer_v1,
    request_hash_for,
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
_ISSUED_NONCES = {}


@pytest.fixture()
def battle_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO users(id) VALUES (?)", [(101,), (202,)])
    ensure_map_battle_tables(conn)
    ensure_submission_lifecycle_schema(conn)
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
    issued = issue_submission_nonce_for_attempt(
        conn,
        user_id=101,
        attempt_id="attempt-s2",
        now="2026-08-02T00:00:00+00:00",
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
    )
    _ISSUED_NONCES[id(conn)] = issued["submission_nonce"]
    conn.commit()
    try:
        yield conn
    finally:
        _ISSUED_NONCES.pop(id(conn), None)
        conn.close()


def _payload(conn, *, moves, nonce=None, battle_revision=0, attempt_id="attempt-s2"):
    attempt = conn.execute(
        "SELECT * FROM map_battle_attempts WHERE id=?", (attempt_id,)
    ).fetchone()
    if nonce is None:
        nonce = _ISSUED_NONCES[id(conn)]
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


def test_submission_nonce_is_server_issued_hashed_and_returned_once(battle_db):
    attempt = battle_db.execute(
        "SELECT * FROM map_battle_attempts WHERE id='attempt-s2'"
    ).fetchone()
    raw_nonce = _ISSUED_NONCES[id(battle_db)]
    assert attempt["submission_nonce_hash"]
    assert raw_nonce not in str(dict(attempt))
    assert len(raw_nonce) >= 32
    with pytest.raises(SubmissionNonceAlreadyIssued):
        issue_submission_nonce_for_attempt(
            battle_db,
            user_id=101,
            attempt_id="attempt-s2",
            now="2026-08-02T00:00:00+00:00",
            mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
        )


def test_feature_off_or_dark_does_not_issue_submission_nonce(battle_db):
    attempt = battle_db.execute(
        "SELECT submission_nonce_hash FROM map_battle_attempts WHERE id='attempt-s2'"
    ).fetchone()
    assert attempt["submission_nonce_hash"]
    with pytest.raises(Exception) as error:
        issue_submission_nonce_for_attempt(
            battle_db,
            user_id=101,
            attempt_id="attempt-s2",
            now="2026-08-02T00:00:00+00:00",
            mode_environ={"E10_MAP_BATTLE_V1_MODE": "off"},
        )
    assert error.value.code == "map_battle_v1_disabled"


def test_attempt_without_server_nonce_cannot_enter_submission_lifecycle(battle_db):
    issue_attempt_for_context(
        battle_db,
        user_id=101,
        battle_id="battle-s2",
        question=QUESTION,
        initial_position_identity="position-without-nonce",
        board_size=19,
        player_color="B",
        transform_version="transform-v1",
        transform_id="identity",
        attempt_id="attempt-no-nonce",
        issued_at="2026-08-02T00:00:00+00:00",
        expires_at="2026-08-03T00:00:00+00:00",
    )
    with pytest.raises(SubmissionNonceNotIssued):
        _settle(
            battle_db,
            _payload(
                battle_db,
                attempt_id="attempt-no-nonce",
                nonce="client-supplied-only",
                moves=[{"x": 3, "y": 3}],
            ),
        )
    assert battle_db.execute("SELECT COUNT(*) FROM map_battle_submissions").fetchone()[0] == 0


def test_submission_aggregate_contains_lifecycle_identity_and_hashes(battle_db):
    payload = _payload(battle_db, moves=[{"x": 3, "y": 3}])
    attempt = dict(
        battle_db.execute("SELECT * FROM map_battle_attempts WHERE id='attempt-s2'").fetchone()
    )
    payload["request_hash"] = request_hash_for(canonicalize_answer(payload, attempt))
    response = _settle(battle_db, payload)
    battle_db.commit()
    row = battle_db.execute(
        "SELECT * FROM map_battle_submissions WHERE id=?", (response["submission_id"],)
    ).fetchone()
    assert row["battle_id"] == "battle-s2"
    assert row["attempt_id"] == "attempt-s2"
    assert row["user_id"] == 101
    assert row["submission_nonce_hash"]
    assert row["request_hash"] == response["request_hash"]
    assert row["issued_at"] == "2026-08-02T00:00:00+00:00"
    assert row["received_at"] == "2026-08-02T00:01:00+00:00"
    assert row["settled_at"] == "2026-08-02T00:01:00+00:00"
    assert row["settlement_state"] == "SETTLED"


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
    assert correct["heal_to_player"] == 1
    assert correct["player_heal_applied"] == 0
    assert correct["monster_hp_after"] == 15
    assert correct["player_hp_after"] == 20
    assert correct["battle_revision"] == 1


def test_wrong_answer_is_server_incorrect_and_player_damage(battle_db):
    wrong = _settle(battle_db, _payload(battle_db, moves=[{"x": 0, "y": 0}]))
    battle_db.commit()
    assert wrong["result"] == "INCORRECT"
    assert wrong["damage_to_monster"] == 0
    assert wrong["damage_to_player"] == 6
    assert wrong["heal_to_player"] == 0
    assert wrong["player_heal_applied"] == 0
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
    assert duplicate["heal_to_player"] == first["heal_to_player"] == 1
    assert duplicate["player_heal_applied"] == first["player_heal_applied"]
    with pytest.raises(RequestRejected):
        _settle(battle_db, {**payload, "moves": [{"x": 0, "y": 0}]})
    assert battle_db.execute("SELECT COUNT(*) FROM map_battle_submissions").fetchone()[0] == 1


def test_settled_duplicate_with_stale_client_revision_replays_without_mutation_or_judge(battle_db):
    payload = _payload(battle_db, moves=[{"x": 3, "y": 3}], battle_revision=0)
    judge_calls = []

    def counting_judge(*args):
        judge_calls.append(args)
        return judge_map_battle_answer_v1(*args)

    first = settle_answer(
        battle_db,
        user_id=101,
        payload=payload,
        question_loader=lambda question_id: QUESTION,
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
        now="2026-08-02T00:01:00+00:00",
        judge=counting_judge,
    )
    battle_db.commit()
    before_retry = tuple(
        battle_db.execute(
            "SELECT monster_hp, player_hp, battle_revision FROM map_battles WHERE id=?",
            (payload["battle_id"],),
        ).fetchone()
    )

    def judge_must_not_run(*_args):
        raise AssertionError("settled duplicate must not rerun the judge")

    retry_payload = {**payload, "battle_revision": first["battle_revision"]}
    assert request_hash_for(canonicalize_answer(payload, dict(battle_db.execute(
        "SELECT * FROM map_battle_attempts WHERE id=?", (payload["attempt_id"],)
    ).fetchone()))) == request_hash_for(canonicalize_answer(
        retry_payload, dict(battle_db.execute(
            "SELECT * FROM map_battle_attempts WHERE id=?", (payload["attempt_id"],)
        ).fetchone())
    ))
    duplicate = settle_answer(
        battle_db,
        user_id=101,
        payload=retry_payload,
        question_loader=lambda question_id: QUESTION,
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
        now="2026-08-02T00:02:00+00:00",
        judge=judge_must_not_run,
    )
    after_retry = tuple(
        battle_db.execute(
            "SELECT monster_hp, player_hp, battle_revision FROM map_battles WHERE id=?",
            (payload["battle_id"],),
        ).fetchone()
    )

    assert duplicate["duplicate"] is True
    assert duplicate["submission_id"] == first["submission_id"]
    assert duplicate["monster_hp_after"] == first["monster_hp_after"]
    assert duplicate["player_hp_after"] == first["player_hp_after"]
    assert after_retry == before_retry == (15, 20, 1)
    assert len(judge_calls) == 1


def test_correct_answer_heals_one_below_max_and_duplicate_does_not_repeat(battle_db):
    battle_db.execute("UPDATE map_battles SET player_hp=19 WHERE id='battle-s2'")
    payload = _payload(battle_db, moves=[{"x": 3, "y": 3}])
    first = _settle(battle_db, payload)
    battle_db.commit()
    duplicate = _settle(battle_db, payload)

    assert first["player_hp_before"] == 19
    assert first["player_hp_after"] == 20
    assert first["heal_to_player"] == 1
    assert first["player_heal_applied"] == 1
    assert duplicate["duplicate"] is True
    assert duplicate["player_hp_after"] == 20
    assert duplicate["player_heal_applied"] == 1
    assert battle_db.execute(
        "SELECT player_hp FROM map_battles WHERE id='battle-s2'"
    ).fetchone()[0] == 20


def test_correct_monster_ko_keeps_authoritative_heal_and_transition(battle_db):
    battle_db.execute(
        "UPDATE map_battles SET player_hp=19, monster_hp=5, monster_hp_max=5 WHERE id='battle-s2'"
    )
    result = _settle(battle_db, _payload(battle_db, moves=[{"x": 3, "y": 3}]))
    assert result["monster_hp_after"] == 0
    assert result["player_hp_after"] == 20
    assert result["player_heal_applied"] == 1
    assert result["monster_defeated"] is True
    assert result["player_defeated"] is False
    assert result["next_action"] == "monster_defeated"


def test_wrong_player_ko_does_not_damage_monster_or_heal(battle_db):
    battle_db.execute("UPDATE map_battles SET player_hp=6 WHERE id='battle-s2'")
    result = _settle(battle_db, _payload(battle_db, moves=[{"x": 0, "y": 0}]))
    assert result["player_hp_after"] == 0
    assert result["monster_hp_after"] == 20
    assert result["player_heal_applied"] == result["heal_to_player"] == 0
    assert result["player_defeated"] is True
    assert result["monster_defeated"] is False
    assert result["next_action"] == "player_defeated"


def test_new_submission_with_stale_revision_still_rejects_without_persisting(battle_db):
    first = _settle(battle_db, _payload(battle_db, moves=[{"x": 3, "y": 3}]))
    battle_db.commit()
    issue_attempt_for_context(
        battle_db,
        user_id=101,
        battle_id="battle-s2",
        question=QUESTION,
        initial_position_identity="position-new-stale",
        board_size=19,
        player_color="B",
        transform_version="transform-v1",
        transform_id="identity",
        attempt_id="attempt-new-stale",
        issued_at="2026-08-02T00:02:00+00:00",
        expires_at="2026-08-03T00:00:00+00:00",
    )
    issued = issue_submission_nonce_for_attempt(
        battle_db,
        user_id=101,
        attempt_id="attempt-new-stale",
        now="2026-08-02T00:02:00+00:00",
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
    )
    attempt = dict(battle_db.execute(
        "SELECT * FROM map_battle_attempts WHERE id=?", ("attempt-new-stale",)
    ).fetchone())
    stale_payload = {
        "battle_id": attempt["battle_id"],
        "attempt_id": attempt["id"],
        "submission_nonce": issued["submission_nonce"],
        "battle_revision": first["battle_revision"] - 1,
        "question_revision": attempt["question_revision"],
        "player_color": "black",
        "transform_id": attempt["transform_id"],
        "transform_version": attempt["transform_version"],
        "moves": [{"x": 3, "y": 3}],
    }
    with pytest.raises(RequestRejected, match="stale"):
        _settle(battle_db, stale_payload)
    battle_db.rollback()
    assert battle_db.execute(
        "SELECT COUNT(*) FROM map_battle_submissions WHERE attempt_id=?",
        ("attempt-new-stale",),
    ).fetchone()[0] == 0


def test_forged_fields_cross_account_and_revision_mismatch_are_rejected(battle_db):
    payload = _payload(battle_db, moves=[{"x": 3, "y": 3}])
    with pytest.raises(ForbiddenClientAuthority):
        _settle(battle_db, {**payload, "damage_to_monster": 999})
    with pytest.raises(ForbiddenClientAuthority):
        _settle(battle_db, {**payload, "heal_to_player": 999})
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


def test_forged_nonce_request_hash_battle_and_attempt_are_rejected_before_reservation(battle_db):
    payload = _payload(battle_db, moves=[{"x": 3, "y": 3}])
    with pytest.raises(SubmissionNonceInvalid):
        _settle(battle_db, {**payload, "submission_nonce": "forged-client-nonce"})
    with pytest.raises(SubmissionRequestHashMismatch):
        _settle(battle_db, {**payload, "request_hash": "f" * 64})
    with pytest.raises(RequestRejected):
        _settle(battle_db, {**payload, "battle_id": "forged-battle"})
    with pytest.raises(RequestRejected):
        _settle(battle_db, {**payload, "attempt_id": "forged-attempt"})
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


def test_rollback_does_not_consume_nonce_and_retry_can_settle(battle_db):
    payload = _payload(battle_db, moves=[{"x": 3, "y": 3}])

    def failing_judge(*_args):
        raise RuntimeError("synthetic judge interruption")

    with pytest.raises(RuntimeError):
        settle_answer(
            battle_db,
            user_id=101,
            payload=payload,
            question_loader=lambda _: QUESTION,
            mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
            now="2026-08-02T00:01:00+00:00",
            judge=failing_judge,
        )
    battle_db.rollback()
    assert battle_db.execute("SELECT COUNT(*) FROM map_battle_submissions").fetchone()[0] == 0
    retry = _settle(battle_db, payload)
    battle_db.commit()
    assert retry["duplicate"] is False
    assert retry["result"] == "CORRECT"


def test_submission_lifecycle_postgres_validation_rollback_retry_and_nonce_race():
    import importlib.util

    helper_path = Path(__file__).with_name("test_map_battle_persistence.py")
    spec = importlib.util.spec_from_file_location("map_battle_pg_helpers", helper_path)
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)

    with helpers._postgres_container() as database_url:
        import psycopg2

        seed = psycopg2.connect(database_url)
        seed.autocommit = True
        seed_cursor = seed.cursor()
        seed_cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        seed_cursor.execute("INSERT INTO users(id) VALUES (101), (202)")
        seed_cursor.close()
        seed.close()

        schema = helpers._postgres_wrapper(database_url)
        ensure_map_battle_tables(schema)
        ensure_submission_lifecycle_schema(schema)
        schema.commit()
        schema.close()

        def make_attempt(battle_id, attempt_id, expires_at="2026-08-03T00:00:00+00:00"):
            conn = helpers._postgres_wrapper(database_url)
            create_map_battle(
                conn,
                battle_id=battle_id,
                user_id=101,
                zone_key="pg::submission-lifecycle",
                player_hp=20,
                player_hp_max=20,
                monster_hp=20,
                monster_hp_max=20,
                now="2026-08-02T00:00:00+00:00",
            )
            issue_attempt_for_context(
                conn,
                user_id=101,
                battle_id=battle_id,
                question=QUESTION,
                initial_position_identity=attempt_id + "-position",
                board_size=19,
                player_color="B",
                transform_version="transform-v1",
                transform_id="identity",
                attempt_id=attempt_id,
                issued_at="2026-08-02T00:00:00+00:00",
                expires_at=expires_at,
            )
            issued = issue_submission_nonce_for_attempt(
                conn,
                user_id=101,
                attempt_id=attempt_id,
                now="2026-08-02T00:00:00+00:00",
                mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
            )
            attempt = conn.execute(
                "SELECT * FROM map_battle_attempts WHERE id=?", (attempt_id,)
            ).fetchone()
            payload = {
                "battle_id": attempt["battle_id"],
                "attempt_id": attempt["id"],
                "submission_nonce": issued["submission_nonce"],
                "battle_revision": attempt["battle_revision_at_issue"],
                "question_revision": attempt["question_revision"],
                "player_color": "black",
                "transform_id": attempt["transform_id"],
                "transform_version": attempt["transform_version"],
                "moves": [{"x": 3, "y": 3}],
            }
            conn.commit()
            conn.close()
            return payload

        forged_payload = make_attempt("pg-forged", "pg-attempt-forged")
        conn = helpers._postgres_wrapper(database_url)
        with pytest.raises(SubmissionNonceInvalid):
            settle_answer(
                conn,
                user_id=101,
                payload={**forged_payload, "submission_nonce": "forged"},
                question_loader=lambda _: QUESTION,
                mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
                now="2026-08-02T00:01:00+00:00",
            )
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) AS n FROM map_battle_submissions").fetchone()["n"] == 0
        conn.close()

        expired_payload = make_attempt("pg-expired", "pg-attempt-expired")
        conn = helpers._postgres_wrapper(database_url)
        conn.execute(
            "UPDATE map_battle_attempts SET expires_at=? WHERE id=?",
            ("2026-08-02T00:01:00+00:00", "pg-attempt-expired"),
        )
        conn.commit()
        with pytest.raises(AttemptExpired):
            settle_answer(
                conn,
                user_id=101,
                payload=expired_payload,
                question_loader=lambda _: QUESTION,
                mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
                now="2026-08-02T00:01:00+00:00",
            )
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) AS n FROM map_battle_submissions").fetchone()["n"] == 0
        conn.close()

        stale_payload = make_attempt("pg-stale", "pg-attempt-stale")
        conn = helpers._postgres_wrapper(database_url)
        with pytest.raises(RequestRejected):
            settle_answer(
                conn,
                user_id=101,
                payload={**stale_payload, "battle_revision": 1},
                question_loader=lambda _: QUESTION,
                mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
                now="2026-08-02T00:01:00+00:00",
            )
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) AS n FROM map_battle_submissions").fetchone()["n"] == 0
        conn.close()

        rollback_payload = make_attempt("pg-rollback", "pg-attempt-rollback")
        conn = helpers._postgres_wrapper(database_url)

        def failing_judge(*_args):
            raise RuntimeError("postgres rollback interruption")

        with pytest.raises(RuntimeError):
            settle_answer(
                conn,
                user_id=101,
                payload=rollback_payload,
                question_loader=lambda _: QUESTION,
                mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
                now="2026-08-02T00:01:00+00:00",
                judge=failing_judge,
            )
        conn.rollback()
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM map_battle_submissions WHERE attempt_id=?",
            ("pg-attempt-rollback",),
        ).fetchone()["n"] == 0
        conn.close()

        retry_conn = helpers._postgres_wrapper(database_url)
        retry = settle_answer(
            retry_conn,
            user_id=101,
            payload=rollback_payload,
            question_loader=lambda _: QUESTION,
            mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
            now="2026-08-02T00:01:00+00:00",
        )
        retry_conn.commit()
        assert retry["duplicate"] is False
        retry_conn.close()

        race_payload = make_attempt("pg-race", "pg-attempt-race")
        barrier = threading.Barrier(2)
        results = []

        def race_worker():
            conn = helpers._postgres_wrapper(database_url)
            try:
                barrier.wait(timeout=15)
                result = settle_answer(
                    conn,
                    user_id=101,
                    payload=race_payload,
                    question_loader=lambda _: QUESTION,
                    mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
                    now="2026-08-02T00:01:00+00:00",
                )
                conn.commit()
                results.append(result)
            except Exception as error:  # pragma: no cover - assertion reports it
                conn.rollback()
                results.append(error)
            finally:
                conn.close()

        threads = [threading.Thread(target=race_worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            assert not thread.is_alive()
        assert not any(isinstance(result, Exception) for result in results)
        assert sorted(result["duplicate"] for result in results) == [False, True]
        assert len({result["submission_id"] for result in results}) == 1

        final = helpers._postgres_wrapper(database_url)
        assert final.execute(
            "SELECT COUNT(*) AS n FROM map_battle_submissions WHERE attempt_id=?",
            ("pg-attempt-race",),
        ).fetchone()["n"] == 1
        assert final.execute(
            "SELECT battle_revision FROM map_battles WHERE id=?", ("pg-race",)
        ).fetchone()["battle_revision"] == 1
        final.close()

        settled_retry_payload = make_attempt(
            "pg-duplicate-retry", "pg-attempt-duplicate-retry"
        )
        first_retry_conn = helpers._postgres_wrapper(database_url)
        first_retry = settle_answer(
            first_retry_conn,
            user_id=101,
            payload=settled_retry_payload,
            question_loader=lambda _: QUESTION,
            mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
            now="2026-08-02T00:01:00+00:00",
        )
        first_retry_conn.commit()
        first_retry_conn.close()
        stale_retry_payload = {
            **settled_retry_payload,
            "battle_revision": first_retry["battle_revision"],
        }
        retry_barrier = threading.Barrier(2)
        retry_results = []

        def retry_worker():
            conn = helpers._postgres_wrapper(database_url)
            try:
                retry_barrier.wait(timeout=15)
                result = settle_answer(
                    conn,
                    user_id=101,
                    payload=stale_retry_payload,
                    question_loader=lambda _: QUESTION,
                    mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
                    now="2026-08-02T00:02:00+00:00",
                    judge=lambda *_args: (_ for _ in ()).throw(
                        AssertionError("settled duplicate retry must not rerun judge")
                    ),
                )
                conn.commit()
                retry_results.append(result)
            except Exception as error:  # pragma: no cover - assertion reports it
                conn.rollback()
                retry_results.append(error)
            finally:
                conn.close()

        retry_threads = [threading.Thread(target=retry_worker) for _ in range(2)]
        for thread in retry_threads:
            thread.start()
        for thread in retry_threads:
            thread.join(timeout=30)
            assert not thread.is_alive()
        assert not any(isinstance(result, Exception) for result in retry_results)
        assert [result["duplicate"] for result in retry_results] == [True, True]
        assert len({result["submission_id"] for result in retry_results}) == 1

        retry_final = helpers._postgres_wrapper(database_url)
        retry_state = retry_final.execute(
            "SELECT monster_hp, player_hp, battle_revision FROM map_battles WHERE id=?",
            ("pg-duplicate-retry",),
        ).fetchone()
        assert tuple(retry_state) == (
            first_retry["monster_hp_after"],
            first_retry["player_hp_after"],
            first_retry["battle_revision"],
        )
        assert retry_final.execute(
            "SELECT COUNT(*) AS n FROM map_battle_submissions WHERE attempt_id=?",
            ("pg-attempt-duplicate-retry",),
        ).fetchone()["n"] == 1
        retry_final.close()


def test_runtime_module_has_no_application_frontend_or_feature_domain_imports():
    runtime_path = Path(__file__).parents[1] / "map_battle_runtime.py"
    tree = ast.parse(runtime_path.read_text(encoding="utf-8"), filename=str(runtime_path))
    forbidden = {"app", "browser", "e10", "frontend", "guild", "index", "legacy", "js"}
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    violations = sorted(
        module for module in imported
        if module.split(".", 1)[0].lower() in forbidden
    )
    assert violations == []
