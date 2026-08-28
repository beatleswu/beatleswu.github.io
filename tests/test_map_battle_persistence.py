"""Sprint 1 tests for additive Map Battle schema and persistence primitives.

SQLite is used for deterministic constraint and transaction coverage only.
The PostgreSQL-only row-lock/concurrency contract is covered by the optional
disposable-PostgreSQL test below; SQLite is never treated as equivalent.
"""

import contextlib
import json
import sqlite3
import threading

import pytest

from tests.postgres_test_harness import (
    disposable_postgres as _disposable_postgres,
)

from map_battle_persistence import (
    LEGACY_ALREADY_V1,
    LEGACY_INVALID_STATE,
    LEGACY_READ_ONLY_REQUIRES_FRESH_BATTLE,
    LEGACY_SAFE_TO_MIGRATE,
    InvalidSettlement,
    StaleBattleRevision,
    SubmissionConflict,
    classify_legacy_battle_for_migration,
    create_map_battle,
    ensure_map_battle_tables,
    get_map_battle_v1_mode,
    hash_submission_nonce,
    issue_map_battle_attempt,
    load_authoritative_battle_state,
    lookup_attempt_for_owner,
    reserve_submission_nonce,
    settle_map_battle_submission,
)


_POSTGRES_CONNECT_TIMEOUT = 3


@pytest.fixture()
def sqlite_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO users(id) VALUES (?)", [(101,), (202,)])
    ensure_map_battle_tables(conn)
    try:
        yield conn
    finally:
        conn.close()


def _battle(conn, battle_id="battle-1", user_id=101):
    return create_map_battle(
        conn,
        battle_id=battle_id,
        user_id=user_id,
        zone_key="forest::encounter-1",
        player_hp=20,
        player_hp_max=20,
        monster_hp=30,
        monster_hp_max=30,
        now="2026-08-02T00:00:00+00:00",
    )


def _attempt(conn, battle_id="battle-1", attempt_id="attempt-1", user_id=101, question_id=9001):
    return issue_map_battle_attempt(
        conn,
        attempt_id=attempt_id,
        battle_id=battle_id,
        user_id=user_id,
        question_id=question_id,
        question_revision="question-rev-1",
        initial_position_identity="position-1",
        board_size=19,
        player_color="B",
        transform_version="transform-v1",
        transform_id="transform-1",
        battle_revision_at_issue=0,
        issued_at="2026-08-02T00:00:00+00:00",
        expires_at="2026-08-03T00:00:00+00:00",
    )


def _reserve(conn, attempt_id="attempt-1", nonce="nonce-1", request_hash="request-hash-1"):
    return reserve_submission_nonce(
        conn,
        user_id=101,
        battle_id="battle-1",
        attempt_id=attempt_id,
        submission_nonce=nonce,
        request_hash=request_hash,
        canonical_move_json={"moves": [{"x": 3, "y": 3}]},
        received_at="2026-08-02T00:01:00+00:00",
    )


def test_mode_is_server_controlled_and_fails_closed(monkeypatch):
    assert get_map_battle_v1_mode({}) == "off"
    assert get_map_battle_v1_mode({"E10_MAP_BATTLE_V1_MODE": "admin"}) == "admin"
    assert get_map_battle_v1_mode({"E10_MAP_BATTLE_V1_MODE": "GLOBAL"}) == "global"
    assert get_map_battle_v1_mode({"E10_MAP_BATTLE_V1_MODE": "not-a-mode"}) == "off"
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "invalid")
    assert get_map_battle_v1_mode() == "off"


def test_schema_inventory_constraints_and_indexes(sqlite_db):
    tables = {
        row["name"]
        for row in sqlite_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'map_battle%'"
        ).fetchall()
    }
    assert tables == {"map_battles", "map_battle_attempts", "map_battle_submissions"}

    expected_columns = {
        "map_battles": {
            "id", "user_id", "zone_key", "state", "player_hp", "player_hp_max",
            "monster_hp", "monster_hp_max", "battle_revision", "migration_source",
            "migration_version", "created_at", "updated_at", "completed_at",
        },
        "map_battle_attempts": {
            "id", "battle_id", "user_id", "question_id", "question_revision",
            "initial_position_identity", "board_size", "player_color",
            "transform_version", "transform_id", "judge_version", "state",
            "issued_at", "expires_at", "settled_at", "battle_revision_at_issue",
            "created_at", "updated_at",
        },
        "map_battle_submissions": {
            "id", "battle_id", "attempt_id", "user_id", "submission_nonce_hash",
            "request_hash", "canonical_move_json", "settlement_state", "judge_result",
            "authoritative_grade", "damage_to_monster", "damage_to_player",
            "monster_hp_before", "monster_hp_after", "player_hp_before",
            "player_hp_after", "battle_revision_before", "battle_revision_after",
            "received_at", "settled_at", "created_at", "updated_at",
        },
    }
    for table, columns in expected_columns.items():
        actual = {row["name"] for row in sqlite_db.execute(f"PRAGMA table_info({table})")}
        assert columns <= actual

    indexes = {
        row["name"]
        for row in sqlite_db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_map_%'"
        )
    }
    assert {
        "idx_map_battles_user_active",
        "idx_map_battles_revision",
        "idx_map_battles_migration",
        "idx_map_battle_attempts_battle",
        "idx_map_battle_attempts_expiry",
        "idx_map_battle_submissions_nonce",
        "idx_map_battle_submissions_processing",
    } <= indexes


def test_schema_rejects_invalid_hp_revision_color_and_expiry(sqlite_db):
    with pytest.raises(ValueError):
        create_map_battle(
            sqlite_db,
            battle_id="bad-hp",
            user_id=101,
            zone_key="zone",
            player_hp=21,
            player_hp_max=20,
            monster_hp=1,
            monster_hp_max=2,
        )
    _battle(sqlite_db)
    with pytest.raises(ValueError):
        issue_map_battle_attempt(
            sqlite_db,
            battle_id="battle-1",
            user_id=101,
            question_id=1,
            question_revision="rev",
            initial_position_identity="position",
            board_size=19,
            player_color="X",
            transform_version="v1",
            transform_id="id",
            battle_revision_at_issue=0,
            issued_at="2026-08-02T00:00:00+00:00",
            expires_at="2026-08-01T00:00:00+00:00",
        )
    with pytest.raises(sqlite3.IntegrityError):
        sqlite_db.execute(
            "INSERT INTO map_battles(id,user_id,zone_key,player_hp,player_hp_max,monster_hp,monster_hp_max,created_at,updated_at) "
            "VALUES ('db-bad',101,'zone',1,0,1,2,'2026-08-02','2026-08-02')"
        )


def test_owner_lookup_and_composite_ownership_constraint(sqlite_db):
    _battle(sqlite_db)
    _attempt(sqlite_db)
    assert lookup_attempt_for_owner(sqlite_db, user_id=101, attempt_id="attempt-1")["battle_id"] == "battle-1"
    assert lookup_attempt_for_owner(sqlite_db, user_id=202, attempt_id="attempt-1") is None
    with pytest.raises(sqlite3.IntegrityError):
        _attempt(sqlite_db, attempt_id="attempt-cross-owner", user_id=202)


def test_nonce_is_hashed_and_duplicate_same_hash_returns_existing(sqlite_db):
    _battle(sqlite_db)
    _attempt(sqlite_db)
    first = _reserve(sqlite_db)
    second = _reserve(sqlite_db)
    assert first["created"] is True
    assert second["created"] is False
    assert second["duplicate"] is True
    assert second["submission_id"] == first["submission_id"]
    assert first["submission_nonce_hash"] == hash_submission_nonce("nonce-1")
    assert sqlite_db.execute(
        "SELECT submission_nonce_hash, canonical_move_json FROM map_battle_submissions"
    ).fetchone()["submission_nonce_hash"] != "nonce-1"
    assert json.loads(
        sqlite_db.execute("SELECT canonical_move_json FROM map_battle_submissions").fetchone()[0]
    ) == {"moves": [{"x": 3, "y": 3}]}
    with pytest.raises(SubmissionConflict):
        _reserve(sqlite_db, nonce="nonce-1", request_hash="different-request")
    with pytest.raises(SubmissionConflict):
        _reserve(sqlite_db, nonce="nonce-2", request_hash="request-hash-2")


def test_settlement_is_exactly_once_and_invalid_does_not_damage(sqlite_db):
    _battle(sqlite_db)
    _attempt(sqlite_db)
    reserved = _reserve(sqlite_db)
    sqlite_db.commit()
    result = settle_map_battle_submission(
        sqlite_db,
        user_id=101,
        battle_id="battle-1",
        attempt_id="attempt-1",
        submission_id=reserved["submission_id"],
        expected_revision=0,
        judge_result="CORRECT",
        authoritative_grade=5,
        damage_to_monster=7,
        damage_to_player=0,
        settled_at="2026-08-02T00:02:00+00:00",
    )
    sqlite_db.commit()
    assert result["duplicate"] is False
    assert result["battle"]["monster_hp"] == 23
    assert result["battle"]["battle_revision"] == 1
    replay = settle_map_battle_submission(
        sqlite_db,
        user_id=101,
        battle_id="battle-1",
        attempt_id="attempt-1",
        submission_id=reserved["submission_id"],
        expected_revision=1,
        judge_result="CORRECT",
        damage_to_monster=7,
        settled_at="2026-08-02T00:03:00+00:00",
    )
    assert replay["duplicate"] is True
    assert load_authoritative_battle_state(sqlite_db, user_id=101, battle_id="battle-1")["battle_revision"] == 1

    _attempt(sqlite_db, attempt_id="attempt-invalid", question_id=9002)
    invalid = _reserve(sqlite_db, attempt_id="attempt-invalid", nonce="nonce-invalid", request_hash="request-invalid")
    sqlite_db.commit()
    invalid_result = settle_map_battle_submission(
        sqlite_db,
        user_id=101,
        battle_id="battle-1",
        attempt_id="attempt-invalid",
        submission_id=invalid["submission_id"],
        expected_revision=1,
        judge_result="INVALID",
        damage_to_monster=0,
        damage_to_player=0,
        settled_at="2026-08-02T00:04:00+00:00",
    )
    sqlite_db.commit()
    assert invalid_result["submission"]["settlement_state"] == "REJECTED"
    assert invalid_result["battle"]["battle_revision"] == 1
    assert invalid_result["battle"]["monster_hp"] == 23


def test_stale_revision_and_transaction_failure_do_not_partially_settle(sqlite_db):
    _battle(sqlite_db)
    _attempt(sqlite_db)
    _attempt(sqlite_db, attempt_id="attempt-2", question_id=9002)
    first = _reserve(sqlite_db)
    second = _reserve(sqlite_db, attempt_id="attempt-2", nonce="nonce-2", request_hash="request-hash-2")
    sqlite_db.commit()
    settle_map_battle_submission(
        sqlite_db,
        user_id=101,
        battle_id="battle-1",
        attempt_id="attempt-1",
        submission_id=first["submission_id"],
        expected_revision=0,
        judge_result="INCORRECT",
        damage_to_player=4,
        settled_at="2026-08-02T00:05:00+00:00",
    )
    sqlite_db.commit()
    with pytest.raises(StaleBattleRevision):
        settle_map_battle_submission(
            sqlite_db,
            user_id=101,
            battle_id="battle-1",
            attempt_id="attempt-2",
            submission_id=second["submission_id"],
            expected_revision=0,
            judge_result="CORRECT",
            damage_to_monster=5,
            settled_at="2026-08-02T00:06:00+00:00",
        )
    assert sqlite_db.execute(
        "SELECT settlement_state FROM map_battle_submissions WHERE id=?", (second["submission_id"],)
    ).fetchone()[0] == "RESERVED"

    _attempt(sqlite_db, attempt_id="attempt-rollback", question_id=9003)
    rollback_reservation = _reserve(sqlite_db, attempt_id="attempt-rollback", nonce="nonce-rollback", request_hash="request-rollback")
    sqlite_db.commit()
    sqlite_db.execute("BEGIN")
    settle_map_battle_submission(
        sqlite_db,
        user_id=101,
        battle_id="battle-1",
        attempt_id="attempt-rollback",
        submission_id=rollback_reservation["submission_id"],
        expected_revision=1,
        judge_result="CORRECT",
        damage_to_monster=5,
        settled_at="2026-08-02T00:07:00+00:00",
    )
    sqlite_db.rollback()
    assert sqlite_db.execute(
        "SELECT settlement_state FROM map_battle_submissions WHERE id=?", (rollback_reservation["submission_id"],)
    ).fetchone()[0] == "RESERVED"
    assert load_authoritative_battle_state(sqlite_db, user_id=101, battle_id="battle-1")["battle_revision"] == 1


def test_migration_classification_fails_closed():
    base = {
        "user_id": 101,
        "battle_id": "legacy-1",
        "zone_key": "forest::encounter-1",
        "player_hp": 20,
        "player_hp_max": 20,
        "monster_hp": 30,
        "monster_hp_max": 30,
    }
    assert classify_legacy_battle_for_migration(base) == LEGACY_READ_ONLY_REQUIRES_FRESH_BATTLE
    assert classify_legacy_battle_for_migration({**base, "attempt_id": "a", "question_revision": "q", "player_color": "B", "transform_version": "v", "transform_id": "t"}) == LEGACY_SAFE_TO_MIGRATE
    assert classify_legacy_battle_for_migration({**base, "schema_version": "map-battle-v1"}) == LEGACY_ALREADY_V1
    assert classify_legacy_battle_for_migration({"user_id": 101}) == LEGACY_INVALID_STATE
    assert classify_legacy_battle_for_migration({**base, "player_hp": 99}) == LEGACY_INVALID_STATE


def test_invalid_settlement_payload_never_writes_damage(sqlite_db):
    _battle(sqlite_db)
    _attempt(sqlite_db)
    reserved = _reserve(sqlite_db)
    sqlite_db.commit()
    with pytest.raises(InvalidSettlement):
        settle_map_battle_submission(
            sqlite_db,
            user_id=101,
            battle_id="battle-1",
            attempt_id="attempt-1",
            submission_id=reserved["submission_id"],
            expected_revision=0,
            judge_result="INVALID",
            damage_to_monster=1,
            settled_at="2026-08-02T00:08:00+00:00",
        )
    assert sqlite_db.execute(
        "SELECT settlement_state, damage_to_monster, damage_to_player FROM map_battle_submissions WHERE id=?",
        (reserved["submission_id"],),
    ).fetchone()[0:3] == ("RESERVED", 0, 0)


@contextlib.contextmanager
def _postgres_container():
    with _disposable_postgres(name_prefix="go-odyssey-map-battle-test") as record:
        yield record["database_url"]


def _postgres_wrapper(database_url):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(database_url, connect_timeout=_POSTGRES_CONNECT_TIMEOUT)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


def test_disposable_postgres_concurrency_lock_cas_and_duplicate_winner():
    """Exercise the real PostgreSQL row lock and unique constraints.

    This is intentionally separate from the SQLite tests: a skipped Docker
    test is not represented as a SQLite-equivalent concurrency pass.
    """

    with _postgres_container() as database_url:
        import psycopg2

        seed = psycopg2.connect(database_url, connect_timeout=_POSTGRES_CONNECT_TIMEOUT)
        seed.autocommit = True
        seed_cursor = seed.cursor()
        seed_cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        seed_cursor.execute("INSERT INTO users(id) VALUES (101), (202)")
        seed_cursor.close()
        seed.close()

        schema = _postgres_wrapper(database_url)
        ensure_map_battle_tables(schema)
        schema.close()

        setup = _postgres_wrapper(database_url)
        _battle(setup)
        _attempt(setup)
        _attempt(setup, attempt_id="attempt-2", question_id=9002)
        _attempt(setup, attempt_id="attempt-3", question_id=9003)
        setup.commit()
        setup.close()

        reserve_barrier = threading.Barrier(2)
        reserve_results = []

        def reserve_worker():
            conn = _postgres_wrapper(database_url)
            try:
                reserve_barrier.wait(timeout=10)
                reserve_results.append(_reserve(conn))
                conn.commit()
            except Exception as exc:  # pragma: no cover - assertion below reports it
                conn.rollback()
                reserve_results.append(exc)
            finally:
                conn.close()

        threads = [threading.Thread(target=reserve_worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            assert not thread.is_alive()
        assert not any(isinstance(result, Exception) for result in reserve_results)
        assert sorted(result["created"] for result in reserve_results) == [False, True]
        assert len({result["submission_id"] for result in reserve_results}) == 1

        setup = _postgres_wrapper(database_url)
        _reserve(setup, attempt_id="attempt-2", nonce="nonce-2", request_hash="request-hash-2")
        _reserve(setup, attempt_id="attempt-3", nonce="nonce-3", request_hash="request-hash-3")
        setup.commit()
        setup.close()

        settle_barrier = threading.Barrier(2)
        settle_results = []

        def settle_worker(attempt_id, submission_id, damage):
            conn = _postgres_wrapper(database_url)
            try:
                settle_barrier.wait(timeout=10)
                settle_results.append(
                    settle_map_battle_submission(
                        conn,
                        user_id=101,
                        battle_id="battle-1",
                        attempt_id=attempt_id,
                        submission_id=submission_id,
                        expected_revision=0,
                        judge_result="CORRECT",
                        damage_to_monster=damage,
                        settled_at="2026-08-02T00:09:00+00:00",
                    )
                )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                settle_results.append(exc)
            finally:
                conn.close()

        # Use the two distinct reservations that were committed above.  The
        # first duplicate-reservation result identifies the same row and is
        # not reused for this race.
        reservation_rows = []
        inspect = _postgres_wrapper(database_url)
        for attempt_id in ("attempt-2", "attempt-3"):
            row = inspect.execute(
                "SELECT id FROM map_battle_submissions WHERE user_id=? AND battle_id=? AND attempt_id=?",
                (101, "battle-1", attempt_id),
            ).fetchone()
            reservation_rows.append(row["id"])
        inspect.close()
        threads = [
            threading.Thread(target=settle_worker, args=("attempt-2", reservation_rows[0], 2)),
            threading.Thread(target=settle_worker, args=("attempt-3", reservation_rows[1], 3)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            assert not thread.is_alive()
        assert sum(not isinstance(result, Exception) for result in settle_results) == 1
        assert sum(isinstance(result, StaleBattleRevision) for result in settle_results) == 1

        final = _postgres_wrapper(database_url)
        state = load_authoritative_battle_state(final, user_id=101, battle_id="battle-1")
        assert state["battle_revision"] == 1
        assert state["monster_hp"] in (28, 27)
        final.close()
