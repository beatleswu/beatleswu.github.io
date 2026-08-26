"""B027-R2 integration proof for the single Spirit combat adapter."""

import sqlite3
import os

import pytest

os.environ.setdefault("SECRET_KEY", "b027-r2-spirit-runtime-test-secret")

import app as app_module  # noqa: E402

from map_battle_persistence import create_map_battle, ensure_map_battle_tables
from map_battle_runtime import (
    ensure_submission_lifecycle_schema,
    issue_attempt_for_context,
    issue_submission_nonce_for_attempt,
    settle_answer,
)
from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from spirit_combat_runtime import apply_spirit_combat_effect


QUESTION = {
    "id": 7027,
    "source": "b027/r2.sgf",
    "content": "(;SZ[19];B[dd];W[ee])",
    "monster_atk": 6,
}


def _projection(spirit_id, stage="STAGE_III"):
    return {
        "active_spirit_id": spirit_id,
        "ownership_validated": True,
        "evolution_stage": stage,
        "progression_level": 25 if stage == "STAGE_III" else 10,
        "effect_profile_id": None,
        "effect_policy_version": None,
        "enabled": True,
        "single_active_spirit": True,
        "source": "SERVER_B022_D008_PROJECTION",
    }


def _battle_db(*, monster_hp=1000, player_hp=100):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO users(id) VALUES(101)")
    conn.execute(
        """CREATE TABLE player_inventory(
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               user_id INTEGER NOT NULL,
               equip_id TEXT NOT NULL,
               equipped INTEGER NOT NULL DEFAULT 0
           )"""
    )
    conn.execute(
        """CREATE TABLE player_skills(
               user_id INTEGER NOT NULL,
               skill_id TEXT NOT NULL,
               equipped INTEGER NOT NULL DEFAULT 0,
               PRIMARY KEY(user_id, skill_id)
           )"""
    )
    # B021's server-owned weapon contribution is deliberately in the real
    # combat-stats resolver, not in the Spirit adapter.
    conn.execute(
        "INSERT INTO player_inventory(user_id,equip_id,equipped) VALUES(101,'iron_sword',1)"
    )
    ensure_map_battle_tables(conn)
    ensure_submission_lifecycle_schema(conn)
    upgrade_outbox(conn)
    create_map_battle(
        conn,
        battle_id="b027-battle",
        user_id=101,
        zone_key="b027::integration",
        player_hp=player_hp,
        player_hp_max=100,
        monster_hp=monster_hp,
        monster_hp_max=monster_hp,
        now="2026-08-24T00:00:00+00:00",
    )
    issue_attempt_for_context(
        conn,
        user_id=101,
        battle_id="b027-battle",
        question=QUESTION,
        initial_position_identity="b027-position",
        board_size=19,
        player_color="B",
        transform_version="transform-v1",
        transform_id="identity",
        attempt_id="b027-attempt",
        issued_at="2026-08-24T00:00:00+00:00",
        expires_at="2026-08-25T00:00:00+00:00",
    )
    issued = issue_submission_nonce_for_attempt(
        conn,
        user_id=101,
        attempt_id="b027-attempt",
        now="2026-08-24T00:01:00+00:00",
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
    )
    conn.commit()
    return conn, issued["submission_nonce"]


def _payload(conn, nonce, moves):
    attempt = conn.execute(
        "SELECT * FROM map_battle_attempts WHERE id='b027-attempt'"
    ).fetchone()
    return {
        "battle_id": attempt["battle_id"],
        "attempt_id": attempt["id"],
        "submission_nonce": nonce,
        "battle_revision": 0,
        "question_revision": attempt["question_revision"],
        "player_color": "black",
        "transform_id": attempt["transform_id"],
        "transform_version": attempt["transform_version"],
        "moves": moves,
    }


def _settle(conn, nonce, moves, projection, *, battle_revision=0):
    payload = _payload(conn, nonce, moves)
    payload["battle_revision"] = battle_revision
    return settle_answer(
        conn,
        user_id=101,
        payload=payload,
        question_loader=lambda question_id: QUESTION,
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
        now="2026-08-24T00:02:00+00:00",
        combat_stats_resolver=app_module._get_authoritative_combat_stats,
        monster_profile_resolver=app_module._map_battle_f010_profile,
        spirit_projection_resolver=lambda _conn, _uid: projection,
    )


def test_map_battle_real_settlement_applies_kelpie_after_equipment_once():
    conn, nonce = _battle_db()
    try:
        first = _settle(conn, nonce, [{"x": 3, "y": 3}], _projection("ink_drop_kelpie"))
        conn.commit()
        assert first["result"] == "CORRECT"
        # B021 iron_sword first produces ceil(1000 * 8% * 1.12) = 90;
        # Stage III Kelpie then adds floor(90 * 9%) = 8 before the one
        # canonical Map Battle settlement.
        assert first["damage_to_monster"] == 98
        assert first["monster_hp_after"] == 902

        retry = _settle(
            conn,
            nonce,
            [{"x": 3, "y": 3}],
            _projection("ink_drop_kelpie"),
            battle_revision=1,
        )
        assert retry["duplicate"] is True
        assert retry["damage_to_monster"] == first["damage_to_monster"]
        assert tuple(conn.execute(
            "SELECT monster_hp, battle_revision FROM map_battles WHERE id='b027-battle'"
        ).fetchone()) == (902, 1)
    finally:
        conn.close()


def test_map_battle_wrong_answer_uses_server_result_not_client_claim_for_spirit():
    conn, nonce = _battle_db(monster_hp=100)
    try:
        result = _settle(
            conn,
            nonce,
            [{"x": 0, "y": 0}],
            _projection("ink_drop_kelpie"),
        )
        assert result["result"] == "INCORRECT"
        assert result["damage_to_monster"] == 0
        assert result["damage_to_player"] == 6
    finally:
        conn.close()


def test_map_battle_bastion_uses_pre_damage_player_hp_after_armor():
    conn, nonce = _battle_db(monster_hp=100, player_hp=35)
    try:
        result = _settle(
            conn,
            nonce,
            [{"x": 0, "y": 0}],
            _projection("obsidian_bastion", "STAGE_II"),
        )
        assert result["result"] == "INCORRECT"
        # Monster attack 6, no B021 armor in this isolated settlement, then
        # Stage II Bastion: floor(6 * 30%) = 1, so 5 damage is settled.
        assert result["damage_to_player"] == 5
        assert result["player_hp_after"] == 30
    finally:
        conn.close()


def test_adapter_fails_closed_when_legacy_has_no_server_answer_evidence():
    conn = sqlite3.connect(":memory:")
    try:
        result = apply_spirit_combat_effect(
            conn,
            101,
            answer_correct=None,
            encounter_class="COMMON",
            monster_hp_before=100,
            monster_max_hp=100,
            incoming_damage_after_armor=0,
            outgoing_damage_after_equipment=80,
            player_hp_before=100,
            player_max_hp=100,
            projection_resolver=lambda _conn, _uid: _projection("ink_drop_kelpie"),
        )
        assert result["triggered"] is False
        assert result["reason"] == "INVALID_ANSWER_CORRECT"
    finally:
        conn.close()


def _legacy_spirit_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE user_stats(
            user_id INTEGER PRIMARY KEY,
            total_correct INTEGER NOT NULL DEFAULT 0,
            current_streak INTEGER NOT NULL DEFAULT 0,
            max_streak INTEGER NOT NULL DEFAULT 0,
            mistake_corrected INTEGER NOT NULL DEFAULT 0,
            xp INTEGER NOT NULL DEFAULT 0,
            rank_level TEXT NOT NULL DEFAULT 'LV1',
            rank_xp INTEGER NOT NULL DEFAULT 0,
            player_hp INTEGER NOT NULL DEFAULT 100,
            player_max_hp INTEGER NOT NULL DEFAULT 100
        );
        CREATE TABLE player_inventory(
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            equip_id TEXT NOT NULL,
            equipped INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE player_skills(
            user_id INTEGER NOT NULL,
            skill_id TEXT NOT NULL,
            equipped INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, skill_id)
        );
        CREATE TABLE battlefield_monster(
            user_id INTEGER NOT NULL,
            bf_date TEXT NOT NULL,
            monster_idx INTEGER NOT NULL DEFAULT 0,
            monster_type TEXT NOT NULL,
            monster_name TEXT NOT NULL,
            monster_avatar TEXT,
            max_hp INTEGER NOT NULL,
            current_hp INTEGER NOT NULL,
            defeated INTEGER NOT NULL DEFAULT 0,
            kill_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, bf_date)
        );
        CREATE TABLE monster_kill_log(
            user_id INTEGER NOT NULL,
            monster_type TEXT NOT NULL,
            kill_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, monster_type)
        );
        CREATE TABLE monster_kill_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            monster_type TEXT NOT NULL,
            monster_name TEXT NOT NULL,
            killed_at TEXT NOT NULL,
            bf_date TEXT NOT NULL
        );
        CREATE TABLE user_pets(
            user_id INTEGER PRIMARY KEY,
            pet_key TEXT NOT NULL,
            nickname TEXT,
            level INTEGER NOT NULL DEFAULT 1,
            xp INTEGER NOT NULL DEFAULT 0,
            fullness INTEGER NOT NULL DEFAULT 60,
            affection INTEGER NOT NULL DEFAULT 10,
            selected_at TEXT NOT NULL,
            last_fed_at TEXT,
            last_interacted_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE pet_collection(
            user_id INTEGER NOT NULL,
            pet_key TEXT NOT NULL,
            nickname TEXT,
            selected_at TEXT,
            level INTEGER NOT NULL DEFAULT 1,
            xp INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    conn.execute("INSERT INTO user_stats(user_id) VALUES(1)")
    conn.execute(
        """INSERT INTO battlefield_monster(
            user_id,bf_date,monster_idx,monster_type,monster_name,
             max_hp,current_hp
           ) VALUES(1,'2026-08-24',14,'golem','LV8 騎士 / 混沌領主',1100,1100)"""
    )
    conn.execute(
        "INSERT INTO user_pets(user_id,pet_key,selected_at,level) VALUES(1,?,?,25)",
        ("ink_drop_kelpie", "2026-08-24"),
    )
    conn.execute(
        "INSERT INTO pet_collection(user_id,pet_key,selected_at,level,xp) VALUES(1,?,?,25,0)",
        ("ink_drop_kelpie", "2026-08-24"),
    )
    conn.commit()
    return conn


def test_legacy_battlefield_uses_same_policy_only_with_server_answer_fact(monkeypatch):
    conn = _legacy_spirit_db()
    monkeypatch.setattr(app_module, "_update_daily_quests", lambda *args, **kwargs: [])
    monkeypatch.setattr(app_module, "_gain_sp", lambda _conn, _uid, amount: amount)
    try:
        authoritative = app_module._update_monster_and_quests(
            conn,
            1,
            9001,
            5,
            {"_server_authoritative_answer_correct": True},
            0,
            "2026-08-24",
        )
        # Same base B021 damage (88) plus Stage III Kelpie's locked 9% floor.
        assert authoritative["monster"]["dmg"] == 95

        conn.execute(
            "UPDATE battlefield_monster SET current_hp=1000 WHERE user_id=1"
        )
        legacy_grade_only = app_module._update_monster_and_quests(
            conn,
            1,
            9002,
            5,
            {},
            0,
            "2026-08-24",
        )
        # A public SRS grade is not an authoritative correctness fact, so a
        # correctness-dependent Spirit effect must not be activated by it.
        assert legacy_grade_only["monster"]["dmg"] == 88
    finally:
        conn.close()


def test_legacy_lord_context_excludes_spirit_policy(monkeypatch):
    conn = _legacy_spirit_db()
    monkeypatch.setattr(app_module, "_update_daily_quests", lambda *args, **kwargs: [])
    monkeypatch.setattr(app_module, "_gain_sp", lambda _conn, _uid, amount: amount)
    try:
        result = app_module._update_monster_and_quests(
            conn,
            1,
            9003,
            5,
            {
                "_server_authoritative_answer_correct": True,
                "_spirit_effects_excluded": True,
            },
            0,
            "2026-08-24",
        )
        # Lord Trial is outside Combat V1 even when a private server answer
        # fact is available; the legacy B021 damage remains unchanged.
        assert result["monster"]["dmg"] == 88
    finally:
        conn.close()


def test_postgres_map_battle_spirit_effect_and_committed_retry():
    """Exercise the actual PG wrapper, projection read, settlement, and replay."""

    import importlib.util
    from pathlib import Path

    helper_path = Path(__file__).with_name("test_map_battle_persistence.py")
    spec = importlib.util.spec_from_file_location("b027_pg_helpers", helper_path)
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)

    with helpers._postgres_container() as database_url:
        from spirit_runtime import build_b022_active_spirit_projection

        seed = helpers._postgres_wrapper(database_url)
        seed.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        seed.execute("INSERT INTO users(id) VALUES (?)", (101,))
        seed.execute(
            """CREATE TABLE player_inventory(
                   id SERIAL PRIMARY KEY,
                   user_id INTEGER NOT NULL,
                   equip_id TEXT NOT NULL,
                   equipped INTEGER NOT NULL DEFAULT 0
               )"""
        )
        seed.execute(
            """CREATE TABLE player_skills(
                   user_id INTEGER NOT NULL,
                   skill_id TEXT NOT NULL,
                   equipped INTEGER NOT NULL DEFAULT 0,
                   PRIMARY KEY(user_id, skill_id)
               )"""
        )
        seed.execute(
            "INSERT INTO player_inventory(user_id,equip_id,equipped) VALUES (?,?,1)",
            (101, "iron_sword"),
        )
        seed.execute(
            """CREATE TABLE pet_collection(
                   user_id INTEGER NOT NULL,
                   pet_key TEXT NOT NULL,
                   level INTEGER NOT NULL DEFAULT 1,
                   xp INTEGER NOT NULL DEFAULT 0
               )"""
        )
        seed.execute(
            """CREATE TABLE user_pets(
                   user_id INTEGER PRIMARY KEY,
                   pet_key TEXT NOT NULL,
                   level INTEGER NOT NULL DEFAULT 1,
                   xp INTEGER NOT NULL DEFAULT 0
               )"""
        )
        seed.execute(
            "INSERT INTO pet_collection(user_id,pet_key,level,xp) VALUES (?,?,25,0)",
            (101, "ink_drop_kelpie"),
        )
        seed.execute(
            "INSERT INTO user_pets(user_id,pet_key,level,xp) VALUES (?,?,25,0)",
            (101, "ink_drop_kelpie"),
        )
        ensure_map_battle_tables(seed)
        ensure_submission_lifecycle_schema(seed)
        upgrade_outbox(seed)
        create_map_battle(
            seed,
            battle_id="b027-pg-battle",
            user_id=101,
            zone_key="b027::pg",
            player_hp=100,
            player_hp_max=100,
            monster_hp=1000,
            monster_hp_max=1000,
            now="2026-08-24T00:00:00+00:00",
        )
        issue_attempt_for_context(
            seed,
            user_id=101,
            battle_id="b027-pg-battle",
            question=QUESTION,
            initial_position_identity="b027-pg-position",
            board_size=19,
            player_color="B",
            transform_version="transform-v1",
            transform_id="identity",
            attempt_id="b027-pg-attempt",
            issued_at="2026-08-24T00:00:00+00:00",
            expires_at="2026-08-25T00:00:00+00:00",
        )
        issued = issue_submission_nonce_for_attempt(
            seed,
            user_id=101,
            attempt_id="b027-pg-attempt",
            now="2026-08-24T00:01:00+00:00",
            mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
        )
        attempt = seed.execute(
            "SELECT * FROM map_battle_attempts WHERE id=?", ("b027-pg-attempt",)
        ).fetchone()
        payload = {
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
        seed.commit()

        first = settle_answer(
            seed,
            user_id=101,
            payload=payload,
            question_loader=lambda _question_id: QUESTION,
            mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
            now="2026-08-24T00:02:00+00:00",
            combat_stats_resolver=app_module._get_authoritative_combat_stats,
            spirit_projection_resolver=build_b022_active_spirit_projection,
        )
        seed.commit()
        assert first["damage_to_monster"] == 98
        assert first["monster_hp_after"] == 902

        def must_not_re_evaluate(*_args):
            raise AssertionError("committed retry re-evaluated Spirit")

        retry = settle_answer(
            seed,
            user_id=101,
            payload={**payload, "battle_revision": 1},
            question_loader=lambda _question_id: QUESTION,
            mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
            now="2026-08-24T00:03:00+00:00",
            combat_stats_resolver=app_module._get_authoritative_combat_stats,
            spirit_projection_resolver=must_not_re_evaluate,
        )
        assert retry["duplicate"] is True
        assert retry["damage_to_monster"] == 98
        assert tuple(seed.execute(
            "SELECT monster_hp,battle_revision FROM map_battles WHERE id=?",
            ("b027-pg-battle",),
        ).fetchone()) == (902, 1)
        assert seed.execute(
            "SELECT COUNT(*) FROM map_battle_submissions WHERE battle_id=?",
            ("b027-pg-battle",),
        ).fetchone()[0] == 1
        seed.close()


@pytest.mark.parametrize(
    "spirit_id, answer_correct, encounter_class, incoming, outgoing, expected",
    [
        ("star_shell_hatchling", True, "BATTLEFIELD_BOSS", 0, 100, 112),
        ("star_shell_hatchling", True, "ELITE", 0, 100, 100),
        ("starpath_antlerling", True, "COMMON", 0, 100, 120),
        ("fatty", True, "COMMON", 0, 35, 42),
        ("whispering_void_kit", False, "COMMON", 5, 0, 4),
    ],
)
def test_shared_adapter_uses_one_locked_policy_for_effect_boundaries(
    spirit_id, answer_correct, encounter_class, incoming, outgoing, expected
):
    conn = sqlite3.connect(":memory:")
    try:
        result = apply_spirit_combat_effect(
            conn,
            101,
            answer_correct=answer_correct,
            encounter_class=encounter_class,
            monster_hp_before=100 if spirit_id != "fatty" else 35,
            monster_max_hp=100,
            incoming_damage_after_armor=incoming,
            outgoing_damage_after_equipment=outgoing,
            player_hp_before=100,
            player_max_hp=100,
            projection_resolver=lambda _conn, _uid: _projection(spirit_id),
        )
        assert result["triggered"] is (spirit_id != "star_shell_hatchling" or encounter_class == "BATTLEFIELD_BOSS")
        assert result["output_damage"] == expected
    finally:
        conn.close()
