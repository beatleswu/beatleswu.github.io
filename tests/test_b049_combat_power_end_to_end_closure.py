"""B049 proof that authoritative equipment changes the real battle outcome."""

from __future__ import annotations

import hashlib
import sqlite3

import pytest

import app as app_module
from map_battle_persistence import create_map_battle, ensure_map_battle_tables
from map_battle_runtime import (
    ensure_submission_lifecycle_schema,
    issue_attempt_for_context,
    issue_submission_nonce_for_attempt,
    judge_map_battle_answer_v1,
    settle_answer,
)


QUESTION = {
    "id": 7049,
    "source": "b049/authoritative-combat.sgf",
    "content": "(;SZ[19];B[dd];W[ee])",
    "monster_atk": 20,
}
QUESTION_REVISION = hashlib.sha256(QUESTION["content"].encode("utf-8")).hexdigest()


def _new_battle(*, equipment=None, equipped=1, appearance_weapon=None, monster_hp=1000):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO users(id) VALUES (7049)")
    conn.execute(
        """CREATE TABLE player_inventory(
             id INTEGER PRIMARY KEY,
             user_id INTEGER NOT NULL,
             equip_id TEXT NOT NULL,
             equipped INTEGER NOT NULL DEFAULT 0,
             obtained_at TEXT,
             source TEXT
        )"""
    )
    if appearance_weapon is not None:
        conn.execute(
            "CREATE TABLE player_appearance(user_id INTEGER PRIMARY KEY, combat_weapon TEXT)"
        )
        conn.execute(
            "INSERT INTO player_appearance(user_id,combat_weapon) VALUES(7049,?)",
            (appearance_weapon,),
        )
    if equipment is not None:
        conn.execute(
            """INSERT INTO player_inventory(
                 id,user_id,equip_id,equipped,obtained_at,source
               ) VALUES(1,7049,?,?,?,?)""",
            (equipment, equipped, "2026-08-28", "b049-test"),
        )

    ensure_map_battle_tables(conn)
    ensure_submission_lifecycle_schema(conn)
    create_map_battle(
        conn,
        battle_id="b049-same-encounter",
        user_id=7049,
        zone_key="legacy::b049",
        player_hp=100,
        player_hp_max=100,
        monster_hp=monster_hp,
        monster_hp_max=1000,
        now="2026-08-28T00:00:00+00:00",
    )
    attempt_id = "b049-attempt"
    issue_attempt_for_context(
        conn,
        user_id=7049,
        battle_id="b049-same-encounter",
        question=QUESTION,
        initial_position_identity=QUESTION_REVISION,
        board_size=19,
        player_color="B",
        transform_version="transform-v1",
        transform_id="identity",
        attempt_id=attempt_id,
        issued_at="2026-08-28T00:00:00+00:00",
        expires_at="2026-08-29T00:00:00+00:00",
    )
    issued = issue_submission_nonce_for_attempt(
        conn,
        user_id=7049,
        attempt_id=attempt_id,
        now="2026-08-28T00:01:00+00:00",
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
    )
    attempt = conn.execute(
        "SELECT * FROM map_battle_attempts WHERE id=?", (attempt_id,)
    ).fetchone()
    return conn, {
        "battle_id": attempt["battle_id"],
        "attempt_id": attempt["id"],
        "submission_nonce": issued["submission_nonce"],
        "battle_revision": 0,
        "question_revision": attempt["question_revision"],
        "player_color": "black",
        "transform_id": attempt["transform_id"],
        "transform_version": attempt["transform_version"],
        "moves": [{"x": 3, "y": 3}],
    }


def _settle_variant(
    *,
    equipment=None,
    equipped=1,
    appearance_weapon=None,
    monster_hp=1000,
    moves=None,
    judge=None,
):
    conn, payload = _new_battle(
        equipment=equipment,
        equipped=equipped,
        appearance_weapon=appearance_weapon,
        monster_hp=monster_hp,
    )
    result = settle_answer(
        conn,
        user_id=7049,
        payload={**payload, "moves": moves if moves is not None else payload["moves"]},
        question_loader=lambda question_id: QUESTION if question_id == QUESTION["id"] else None,
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
        now="2026-08-28T00:02:00+00:00",
        judge=judge,
        combat_stats_resolver=app_module._get_authoritative_combat_stats,
    )
    conn.commit()
    return conn, payload, result


def test_same_encounter_same_authoritative_answer_different_legitimate_weapon_changes_hp():
    variants = {
        "unequipped_baseline": _settle_variant(),
        "wooden_sword": _settle_variant(equipment="wooden_sword"),
        "iron_sword": _settle_variant(equipment="iron_sword"),
        "unequipped_iron_sword": _settle_variant(
            equipment="iron_sword", equipped=0
        ),
    }
    try:
        results = {name: value[2] for name, value in variants.items()}
        assert {result["result"] for result in results.values()} == {"CORRECT"}
        assert {result["authoritative_grade"] for result in results.values()} == {5}
        assert {result["submission_id"] is not None for result in results.values()} == {True}
        assert {value[1]["battle_id"] for value in variants.values()} == {
            "b049-same-encounter"
        }
        assert results["unequipped_baseline"]["damage_to_monster"] == 80
        assert results["wooden_sword"]["damage_to_monster"] == 84
        assert results["iron_sword"]["damage_to_monster"] == 90
        assert results["unequipped_iron_sword"]["damage_to_monster"] == 80
        assert (
            results["iron_sword"]["monster_hp_after"]
            < results["unequipped_baseline"]["monster_hp_after"]
        )
    finally:
        for conn, _payload, _result in variants.values():
            conn.close()


def test_map_battle_http_route_persists_equipment_adjusted_damage(monkeypatch):
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "global")
    monkeypatch.setattr(
        app_module,
        "_map_battle_question_by_id",
        lambda question_id: QUESTION if question_id == QUESTION["id"] else None,
    )
    monkeypatch.setattr(
        app_module,
        "_run_map_battle_progression",
        lambda user_id, settlement: ({"status": "applied"}, 200),
    )
    app_module.app.config["TESTING"] = True

    for equipment, expected_damage in ((None, 80), ("iron_sword", 90)):
        conn, payload = _new_battle(equipment=equipment)

        class _Db:
            def __enter__(self):
                return conn

            def __exit__(self, exc_type, exc, tb):
                if exc_type:
                    conn.rollback()
                else:
                    conn.commit()

        monkeypatch.setattr(app_module, "get_db", lambda _db=_Db(): _db)
        client = app_module.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 7049
        response = client.post(
            "/api/adventure/map-battles/v1/answers",
            headers={"X-Map-Battle-Client-Protocol": "v1"},
            json=payload,
        )
        try:
            assert response.status_code == 200
            body = response.get_json()
            assert body["result"] == "CORRECT"
            assert body["authoritative_grade"] == 5
            assert body["damage_to_monster"] == expected_damage
            assert body["monster_hp_after"] == 1000 - expected_damage
        finally:
            conn.close()


@pytest.mark.parametrize(
    "equipment,appearance_weapon",
    [
        ("unknown-equipment", None),
        ("go_stone_black", None),
        (None, "forged-client-weapon"),
    ],
)
def test_invalid_inventory_and_cosmetic_projection_fail_closed_without_combat_power(
    equipment, appearance_weapon
):
    conn, _payload, result = _settle_variant(
        equipment=equipment,
        appearance_weapon=appearance_weapon,
    )
    try:
        assert result["result"] == "CORRECT"
        assert result["damage_to_monster"] == 80
        assert result["monster_hp_before"] == 1000
        assert result["monster_hp_after"] == 920
    finally:
        conn.close()


def test_failed_authoritative_answer_damages_player_without_damaging_monster():
    conn, _payload, result = _settle_variant(moves=[{"x": 0, "y": 0}])
    try:
        assert result["result"] == "INCORRECT"
        assert result["authoritative_grade"] == 0
        assert result["damage_to_monster"] == 0
        assert result["damage_to_player"] >= 1
        assert result["monster_hp_before"] == result["monster_hp_after"] == 1000
        assert result["player_hp_after"] < result["player_hp_before"]
        assert result["heal_to_player"] == 0
    finally:
        conn.close()


def test_successful_answer_is_persisted_and_monster_hp_is_bounded_at_zero():
    conn, _payload, result = _settle_variant(
        equipment="iron_sword",
        monster_hp=3,
    )
    try:
        assert result["result"] == "CORRECT"
        assert result["damage_to_monster"] == 90
        assert result["monster_hp_after"] == 0
        assert result["monster_defeated"] is True
        persisted = conn.execute(
            "SELECT monster_hp, battle_revision FROM map_battles WHERE id=?",
            ("b049-same-encounter",),
        ).fetchone()
        assert tuple(persisted) == (0, 1)
    finally:
        conn.close()


def test_settled_retry_replays_damage_without_rerunning_authoritative_judge():
    judge_calls = []

    def counting_judge(*args):
        judge_calls.append(args)
        return judge_map_battle_answer_v1(*args)

    conn, payload, first = _settle_variant(
        equipment="iron_sword",
        judge=counting_judge,
    )
    try:
        def judge_must_not_run(*_args):
            raise AssertionError("settled retry reran the authoritative judge")

        retry = settle_answer(
            conn,
            user_id=7049,
            payload={**payload, "battle_revision": first["battle_revision"]},
            question_loader=lambda question_id: QUESTION,
            mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
            now="2026-08-28T00:03:00+00:00",
            judge=judge_must_not_run,
            combat_stats_resolver=app_module._get_authoritative_combat_stats,
        )
        assert len(judge_calls) == 1
        assert retry["duplicate"] is True
        assert retry["submission_id"] == first["submission_id"]
        assert retry["damage_to_monster"] == first["damage_to_monster"] == 90
        assert tuple(
            conn.execute(
                "SELECT monster_hp, battle_revision FROM map_battles WHERE id=?",
                ("b049-same-encounter",),
            ).fetchone()
        ) == (910, 1)
    finally:
        conn.close()
