"""D030-R1 tests for Adventure-owned Spirit milestone acquisition."""

from __future__ import annotations

import sqlite3

import pytest

import app as app_module
from migrations.companion_operations_v1 import upgrade as upgrade_companion_schema
from spirit_adventure_milestone import (
    ADVENTURE_SPIRIT_MILESTONES,
    AdventureSpiritAcquisitionError,
    catch_up_adventure_spirit_unlocks,
    inspect_adventure_spirit_eligibility,
    resolve_milestone_for_number,
    resolve_milestone_for_zone,
    unlock_spirit_from_adventure_milestone,
    validate_executable_zone_order,
)


USER_ID = 7301


def _database() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE adventure_boss_progress(
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            cleared INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, zone_key)
        );
        CREATE TABLE pet_collection(
            user_id INTEGER NOT NULL,
            pet_key TEXT NOT NULL,
            PRIMARY KEY(user_id, pet_key)
        );
        """
    )
    upgrade_companion_schema(conn)
    conn.commit()
    return conn


def _seed_clear(conn: sqlite3.Connection, user_id: int, zone_key: str, cleared: int = 1):
    conn.execute(
        "INSERT INTO adventure_boss_progress(user_id,zone_key,cleared) VALUES(?,?,?)",
        (user_id, zone_key, cleared),
    )


def _server_owned_unlock_mutation(conn, user_id, spirit_id, zone_key, operation_id):
    conn.execute(
        "INSERT INTO pet_collection(user_id,pet_key) VALUES(?,?)",
        (user_id, spirit_id),
    )
    return {
        "ok": True,
        "status": "SUCCESS",
        "ownership_mutation_count": 1,
        "source_authority": "ADVENTURE_ZONE_MILESTONE",
        "zone_key": zone_key,
        "spirit_id": spirit_id,
        "operation_id": operation_id,
    }, 200


def _no_writer(conn, user_id, spirit_id, zone_key, operation_id):
    raise AssertionError("already-owned/replay path must not call the sink")


def test_owner_mapping_resolves_exact_executable_stable_keys():
    zone_keys = tuple(zone["key"] for zone in app_module.ADVENTURE_ZONES)

    assert validate_executable_zone_order(zone_keys) is True
    assert resolve_milestone_for_number(4).zone_key == "k11_15"
    assert resolve_milestone_for_number(6).zone_key == "k1_5"
    assert resolve_milestone_for_number(8).zone_key == "d3_4"
    assert tuple(item.zone_key for item in ADVENTURE_SPIRIT_MILESTONES) == (
        zone_keys[3],
        zone_keys[5],
        zone_keys[7],
    )
    assert app_module._adventure_zone_index("k11_15") == 3
    assert app_module._adventure_zone_index("k1_5") == 5
    assert app_module._adventure_zone_index("d3_4") == 7


@pytest.mark.parametrize(
    ("milestone", "expected_spirit"),
    [
        (ADVENTURE_SPIRIT_MILESTONES[0], "starpath_antlerling"),
        (ADVENTURE_SPIRIT_MILESTONES[1], "fatty"),
        (ADVENTURE_SPIRIT_MILESTONES[2], "obsidian_bastion"),
    ],
)
def test_each_cleared_owner_milestone_unlocks_its_mapped_spirit(milestone, expected_spirit):
    conn = _database()
    try:
        _seed_clear(conn, USER_ID, milestone.zone_key)
        result = unlock_spirit_from_adventure_milestone(
            conn,
            user_id=USER_ID,
            zone_key=milestone.zone_key,
            mutation=_server_owned_unlock_mutation,
        )

        assert result["status"] == "UNLOCKED"
        assert result["spirit_id"] == expected_spirit
        assert result["zone_key"] == milestone.zone_key
        assert result["new_unlock_count"] == 1
        assert result["ownership_mutation_count"] == 1
        assert result["compensation_count"] == 0
        assert result["replacement_count"] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM pet_collection WHERE user_id=? AND pet_key=?",
            (USER_ID, expected_spirit),
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT operation_type FROM companion_operations WHERE user_id=?",
            (USER_ID,),
        ).fetchone()[0] == "SPIRIT_UNLOCK"
    finally:
        conn.close()


def test_unreached_milestone_and_client_only_fake_completion_do_not_unlock():
    conn = _database()
    try:
        _seed_clear(conn, USER_ID, "k11_15", cleared=0)
        result = unlock_spirit_from_adventure_milestone(
            conn,
            user_id=USER_ID,
            zone_key="k11_15",
            mutation=_no_writer,
        )
        assert result["status"] == "NOT_ELIGIBLE"
        assert result["new_unlock_count"] == 0

        # There is no client-cleared/client-current-zone input in the API;
        # without the persisted World fact the same request remains ineligible.
        assert conn.execute("SELECT COUNT(*) FROM pet_collection").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM companion_operations").fetchone()[0] == 0
    finally:
        conn.close()


def test_wrong_zone_selected_zone_and_non_world_facts_fail_closed():
    conn = _database()
    try:
        _seed_clear(conn, USER_ID, "k21_25")
        with pytest.raises(AdventureSpiritAcquisitionError) as exc_info:
            unlock_spirit_from_adventure_milestone(
                conn,
                user_id=USER_ID,
                zone_key="k21_25",
                mutation=_server_owned_unlock_mutation,
            )
        assert exc_info.value.code == "UNMAPPED_ADVENTURE_SPIRIT_MILESTONE"

        # A selected/recommended UI zone is not an argument and cannot replace
        # the exact persisted progression row used below.
        _seed_clear(conn, USER_ID, "k11_15")
        eligibility = inspect_adventure_spirit_eligibility(
            conn, user_id=USER_ID, zone_key="k11_15"
        )
        assert eligibility.zone_key == "k11_15"
        assert eligibility.spirit_id == "starpath_antlerling"
        assert eligibility.cleared is True
    finally:
        conn.close()


def test_non_adventure_monster_boss_and_quest_facts_do_not_unlock():
    conn = _database()
    try:
        conn.execute("CREATE TABLE monster_defeats(user_id INTEGER, defeated INTEGER)")
        conn.execute("INSERT INTO monster_defeats VALUES(?,1)", (USER_ID,))
        conn.execute("CREATE TABLE battlefield_bosses(user_id INTEGER, defeated INTEGER)")
        conn.execute("INSERT INTO battlefield_bosses VALUES(?,1)", (USER_ID,))
        conn.execute("CREATE TABLE quest_completions(user_id INTEGER, completed INTEGER)")
        conn.execute("INSERT INTO quest_completions VALUES(?,1)", (USER_ID,))

        result = unlock_spirit_from_adventure_milestone(
            conn,
            user_id=USER_ID,
            zone_key="d3_4",
            mutation=_no_writer,
        )
        assert result["status"] == "NOT_ELIGIBLE"
        assert conn.execute(
            "SELECT COUNT(*) FROM pet_collection WHERE user_id=?",
            (USER_ID,),
        ).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM companion_operations").fetchone()[0] == 0
    finally:
        conn.close()


def test_exact_operation_replay_has_no_new_unlock_and_does_not_call_sink():
    conn = _database()
    try:
        _seed_clear(conn, USER_ID, "k11_15")
        first = unlock_spirit_from_adventure_milestone(
            conn,
            user_id=USER_ID,
            zone_key="k11_15",
            mutation=_server_owned_unlock_mutation,
        )
        conn.commit()
        replay = unlock_spirit_from_adventure_milestone(
            conn,
            user_id=USER_ID,
            zone_key="k11_15",
            mutation=_no_writer,
        )

        assert first["operation_id"] == replay["operation_id"]
        assert replay["status"] == "REPLAY"
        assert replay["replayed"] is True
        assert replay["new_unlock_count"] == 0
        assert replay["ownership_mutation_count"] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM pet_collection WHERE user_id=? AND pet_key=?",
            (USER_ID, "starpath_antlerling"),
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM companion_operations WHERE user_id=?",
            (USER_ID,),
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_already_owned_is_a_durable_no_op_with_no_compensation_or_replacement():
    conn = _database()
    try:
        _seed_clear(conn, USER_ID, "k1_5")
        conn.execute(
            "INSERT INTO pet_collection(user_id,pet_key) VALUES(?,?)",
            (USER_ID, "fatty"),
        )
        result = unlock_spirit_from_adventure_milestone(
            conn,
            user_id=USER_ID,
            zone_key="k1_5",
            mutation=_no_writer,
        )
        assert result["status"] == "NO_OP"
        assert result["new_unlock_count"] == 0
        assert result["ownership_mutation_count"] == 0
        assert result["compensation_count"] == 0
        assert result["replacement_count"] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM pet_collection WHERE user_id=? AND pet_key='fatty'",
            (USER_ID,),
        ).fetchone()[0] == 1
        replay = unlock_spirit_from_adventure_milestone(
            conn,
            user_id=USER_ID,
            zone_key="k1_5",
            mutation=_no_writer,
        )
        assert replay["status"] == "REPLAY"
        assert replay["new_unlock_count"] == 0
    finally:
        conn.close()


def test_historical_catch_up_consumes_only_persisted_cleared_rows():
    conn = _database()
    try:
        _seed_clear(conn, USER_ID, "k11_15")
        _seed_clear(conn, USER_ID, "k1_5")
        _seed_clear(conn, USER_ID, "d3_4")

        first = catch_up_adventure_spirit_unlocks(
            conn, user_id=USER_ID, mutation=_server_owned_unlock_mutation
        )
        assert [result["status"] for result in first] == [
            "UNLOCKED",
            "UNLOCKED",
            "UNLOCKED",
        ]
        assert [result["new_unlock_count"] for result in first] == [1, 1, 1]
        assert conn.execute(
            "SELECT COUNT(*) FROM pet_collection WHERE user_id=?",
            (USER_ID,),
        ).fetchone()[0] == 3

        second = catch_up_adventure_spirit_unlocks(
            conn, user_id=USER_ID, mutation=_no_writer
        )
        assert [result["status"] for result in second] == ["REPLAY", "REPLAY", "REPLAY"]
        assert sum(result["new_unlock_count"] for result in second) == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM companion_operations WHERE user_id=?",
            (USER_ID,),
        ).fetchone()[0] == 3
    finally:
        conn.close()


def test_different_users_have_independent_milestone_operations_and_ownership():
    conn = _database()
    try:
        _seed_clear(conn, USER_ID, "d3_4")
        _seed_clear(conn, USER_ID + 1, "d3_4")
        first = unlock_spirit_from_adventure_milestone(
            conn,
            user_id=USER_ID,
            zone_key="d3_4",
            mutation=_server_owned_unlock_mutation,
        )
        second = unlock_spirit_from_adventure_milestone(
            conn,
            user_id=USER_ID + 1,
            zone_key="d3_4",
            mutation=_server_owned_unlock_mutation,
        )
        assert first["new_unlock_count"] == second["new_unlock_count"] == 1
        assert first["operation_id"] != second["operation_id"]
        assert conn.execute(
            "SELECT COUNT(*) FROM pet_collection WHERE pet_key='obsidian_bastion'"
        ).fetchone()[0] == 2
    finally:
        conn.close()


def test_unlock_sink_completion_without_ownership_fails_closed():
    conn = _database()
    try:
        _seed_clear(conn, USER_ID, "k11_15")

        def missing_writer(_conn, _user_id, _spirit_id, _zone_key, operation_id):
            return {"ok": True, "status": "SUCCESS", "operation_id": operation_id}, 200

        with pytest.raises(AdventureSpiritAcquisitionError) as exc_info:
            unlock_spirit_from_adventure_milestone(
                conn,
                user_id=USER_ID,
                zone_key="k11_15",
                mutation=missing_writer,
            )
        assert exc_info.value.code == "SPIRIT_UNLOCK_OWNERSHIP_NOT_PERSISTED"
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM pet_collection").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM companion_operations").fetchone()[0] == 0
    finally:
        conn.close()


def test_caller_rollback_removes_ownership_and_b023_operation():
    conn = _database()
    try:
        _seed_clear(conn, USER_ID, "k1_5")
        conn.commit()
        result = unlock_spirit_from_adventure_milestone(
            conn,
            user_id=USER_ID,
            zone_key="k1_5",
            mutation=_server_owned_unlock_mutation,
        )
        assert result["new_unlock_count"] == 1
        assert conn.execute("SELECT COUNT(*) FROM pet_collection").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM companion_operations").fetchone()[0] == 1

        # The service never commits; the authoritative Adventure caller owns
        # the transaction boundary and can roll back both effects together.
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM pet_collection").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM companion_operations").fetchone()[0] == 0
        assert conn.execute(
            "SELECT cleared FROM adventure_boss_progress WHERE user_id=? AND zone_key=?",
            (USER_ID, "k1_5"),
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_invalid_mapping_inputs_fail_closed():
    with pytest.raises(AdventureSpiritAcquisitionError):
        resolve_milestone_for_zone("d3_4x")
    with pytest.raises(AdventureSpiritAcquisitionError):
        resolve_milestone_for_number(5)
    with pytest.raises(AdventureSpiritAcquisitionError):
        validate_executable_zone_order(("k26_30",))
