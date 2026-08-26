"""D027 real-settlement proof for the locked Six-Spirit combat matrix.

These tests deliberately exercise the existing Map Battle settlement caller
with the real server projection reader.  The Monster profile and ownership
rows are disposable server-owned test fixtures; they are not product
acquisition paths for the three new Spirits.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

os.environ.setdefault("SECRET_KEY", "d027-six-spirit-real-settlement-test-secret")

import app as app_module  # noqa: E402
from map_battle_persistence import create_map_battle, ensure_map_battle_tables  # noqa: E402
from map_battle_runtime import (  # noqa: E402
    ensure_submission_lifecycle_schema,
    issue_attempt_for_context,
    issue_submission_nonce_for_attempt,
    settle_answer,
)
from monster_combat_profiles import resolve_monster_combat_profile  # noqa: E402
from spirit_combat_policy import evaluate_spirit_combat_effect  # noqa: E402
from spirit_runtime import build_b022_active_spirit_projection  # noqa: E402


USER_ID = 1027
QUESTION = {
    "id": 7027,
    "source": "d027/real-settlement.sgf",
    "content": "(;SZ[19];B[dd];W[ee])",
    "monster_atk": 6,
}


def _real_battle_db(
    *,
    spirit_id: str,
    level: int,
    monster_id: str,
    monster_hp: int | None = None,
    player_hp: int = 100,
    battle_id: str,
):
    """Build a disposable Map Battle with real active-Spirit projection rows."""

    profile = resolve_monster_combat_profile(
        {"monster_id": monster_id},
        context="MAP_BATTLE",
    )
    current_hp = profile.max_hp if monster_hp is None else monster_hp
    assert 0 < current_hp <= profile.max_hp

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO users(id) VALUES(?)", (USER_ID,))
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
    # The real B021 stats resolver sees the existing functional Equipment
    # row.  D027 does not replace that authority with a Spirit calculation.
    conn.execute(
        "INSERT INTO player_inventory(user_id,equip_id,equipped) VALUES(?,?,1)",
        (USER_ID, "iron_sword"),
    )
    conn.execute(
        """CREATE TABLE pet_collection(
               user_id INTEGER NOT NULL,
               pet_key TEXT NOT NULL,
               level INTEGER NOT NULL DEFAULT 1,
               xp INTEGER NOT NULL DEFAULT 0,
               PRIMARY KEY(user_id, pet_key)
           )"""
    )
    conn.execute(
        """CREATE TABLE user_pets(
               user_id INTEGER PRIMARY KEY,
               pet_key TEXT NOT NULL,
               level INTEGER NOT NULL DEFAULT 1,
               xp INTEGER NOT NULL DEFAULT 0
           )"""
    )
    # These rows are explicitly disposable server-owned ownership fixtures.
    conn.execute(
        "INSERT INTO pet_collection(user_id,pet_key,level,xp) VALUES(?,?,?,0)",
        (USER_ID, spirit_id, level),
    )
    conn.execute(
        "INSERT INTO user_pets(user_id,pet_key,level,xp) VALUES(?,?,?,0)",
        (USER_ID, spirit_id, level),
    )

    ensure_map_battle_tables(conn)
    ensure_submission_lifecycle_schema(conn)
    create_map_battle(
        conn,
        battle_id=battle_id,
        user_id=USER_ID,
        zone_key="d027::settlement",
        player_hp=player_hp,
        player_hp_max=100,
        monster_hp=current_hp,
        monster_hp_max=profile.max_hp,
        now="2026-08-24T00:00:00+00:00",
    )
    attempt_id = f"{battle_id}:attempt"
    issue_attempt_for_context(
        conn,
        user_id=USER_ID,
        battle_id=battle_id,
        question=QUESTION,
        initial_position_identity=f"{battle_id}:position",
        board_size=19,
        player_color="B",
        transform_version="transform-v1",
        transform_id="identity",
        attempt_id=attempt_id,
        issued_at="2026-08-24T00:00:00+00:00",
        expires_at="2026-08-25T00:00:00+00:00",
    )
    issued = issue_submission_nonce_for_attempt(
        conn,
        user_id=USER_ID,
        attempt_id=attempt_id,
        now="2026-08-24T00:01:00+00:00",
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
    )
    conn.commit()
    return conn, profile, issued["submission_nonce"]


def _payload(conn, nonce: str, battle_id: str, moves: list[dict[str, int]], revision: int = 0):
    attempt = conn.execute(
        "SELECT * FROM map_battle_attempts WHERE id=?",
        (f"{battle_id}:attempt",),
    ).fetchone()
    return {
        "battle_id": attempt["battle_id"],
        "attempt_id": attempt["id"],
        "submission_nonce": nonce,
        "battle_revision": revision,
        "question_revision": attempt["question_revision"],
        "player_color": "black",
        "transform_id": attempt["transform_id"],
        "transform_version": attempt["transform_version"],
        "moves": moves,
    }


def _settle(
    conn,
    profile,
    nonce: str,
    *,
    battle_id: str,
    correct: bool,
):
    return settle_answer(
        conn,
        user_id=USER_ID,
        payload=_payload(
            conn,
            nonce,
            battle_id,
            [{"x": 3, "y": 3}] if correct else [{"x": 0, "y": 0}],
        ),
        question_loader=lambda _question_id: QUESTION,
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
        now="2026-08-24T00:02:00+00:00",
        combat_stats_resolver=app_module._get_authoritative_combat_stats,
        monster_profile_resolver=lambda _conn, _uid, _battle_id: profile,
        spirit_projection_resolver=build_b022_active_spirit_projection,
    )


def test_kelpie_real_projection_settlement_applies_training_bonus():
    conn, profile, nonce = _real_battle_db(
        spirit_id="ink_drop_kelpie",
        level=25,
        monster_id="legacy_bf_08_normal",
        battle_id="d027-kelpie",
    )
    try:
        result = _settle(
            conn,
            profile,
            nonce,
            battle_id="d027-kelpie",
            correct=True,
        )
        conn.commit()
        # Canonical Stage-III B021 damage is 99; Kelpie adds floor(99 * 9%).
        assert result["damage_to_monster"] == 107
        assert result["monster_hp_after"] == 993
    finally:
        conn.close()


def test_void_real_settlement_reduces_incorrect_retaliation_and_honors_min_one():
    conn, profile, nonce = _real_battle_db(
        spirit_id="whispering_void_kit",
        level=1,
        monster_id="legacy_bf_01_normal",
        battle_id="d027-void",
    )
    try:
        result = _settle(
            conn,
            profile,
            nonce,
            battle_id="d027-void",
            correct=False,
        )
        conn.commit()
        assert result["result"] == "INCORRECT"
        # The canonical profile attacks for 2; Stage-I Void's 8% integer
        # reduction would round to zero, but the policy's min-one rule makes
        # the committed retaliation exactly 1.
        assert result["damage_to_player"] == 1
        assert conn.execute(
            "SELECT player_hp FROM map_battles WHERE id=?", ("d027-void",)
        ).fetchone()[0] == 99
    finally:
        conn.close()


def test_hatchling_real_battlefield_boss_settlement_and_normal_exclusion():
    boss_conn, boss_profile, boss_nonce = _real_battle_db(
        spirit_id="star_shell_hatchling",
        level=25,
        monster_id="legacy_bf_01_boss",
        battle_id="d027-hatchling-boss",
    )
    normal_conn, normal_profile, normal_nonce = _real_battle_db(
        spirit_id="star_shell_hatchling",
        level=25,
        monster_id="legacy_bf_01_normal",
        battle_id="d027-hatchling-normal",
    )
    try:
        boss = _settle(
            boss_conn,
            boss_profile,
            boss_nonce,
            battle_id="d027-hatchling-boss",
            correct=True,
        )
        normal = _settle(
            normal_conn,
            normal_profile,
            normal_nonce,
            battle_id="d027-hatchling-normal",
            correct=True,
        )
        # Stage-III B021 damage is 9 for the 100-HP canonical boss profile;
        # Hatchling adds floor(9 * 12%) = 1 only for BATTLEFIELD_BOSS.
        assert boss["damage_to_monster"] == 10
        assert normal["damage_to_monster"] == 8
    finally:
        boss_conn.close()
        normal_conn.close()


@pytest.mark.parametrize("encounter_class", ("ELITE", "RARE", "LORD"))
def test_hatchling_non_battlefield_encounters_fail_closed_at_policy_boundary(encounter_class):
    result = evaluate_spirit_combat_effect(
        {
            "active_spirit_id": "star_shell_hatchling",
            "ownership_validated": True,
            "evolution_stage": "STAGE_III",
            "progression_level": 25,
            "effect_profile_id": None,
            "effect_policy_version": None,
            "enabled": True,
            "single_active_spirit": True,
            "answer_correct": True,
            "encounter_class": encounter_class,
            "monster_hp_before": 100,
            "monster_max_hp": 100,
            "incoming_damage_after_armor": 0,
            "outgoing_damage_after_equipment": 100,
            "player_hp_before": 100,
            "player_max_hp": 100,
        }
    )
    assert result["triggered"] is False


def test_antlerling_real_settlement_requires_full_pre_hit_hp_and_correctness():
    full_conn, full_profile, full_nonce = _real_battle_db(
        spirit_id="starpath_antlerling",
        level=25,
        monster_id="legacy_bf_08_normal",
        battle_id="d027-antlerling-full",
    )
    partial_conn, partial_profile, partial_nonce = _real_battle_db(
        spirit_id="starpath_antlerling",
        level=25,
        monster_id="legacy_bf_08_normal",
        monster_hp=1099,
        battle_id="d027-antlerling-partial",
    )
    wrong_conn, wrong_profile, wrong_nonce = _real_battle_db(
        spirit_id="starpath_antlerling",
        level=25,
        monster_id="legacy_bf_08_normal",
        battle_id="d027-antlerling-wrong",
    )
    try:
        full = _settle(
            full_conn,
            full_profile,
            full_nonce,
            battle_id="d027-antlerling-full",
            correct=True,
        )
        partial = _settle(
            partial_conn,
            partial_profile,
            partial_nonce,
            battle_id="d027-antlerling-partial",
            correct=True,
        )
        wrong = _settle(
            wrong_conn,
            wrong_profile,
            wrong_nonce,
            battle_id="d027-antlerling-wrong",
            correct=False,
        )
        # Canonical Stage-III B021 damage is 99; full-HP Antlerling adds 19.
        assert full["damage_to_monster"] == 118
        assert partial["damage_to_monster"] == 99
        assert wrong["damage_to_monster"] == 0
        assert wrong["damage_to_player"] == 20
    finally:
        full_conn.close()
        partial_conn.close()
        wrong_conn.close()


def test_fatty_real_settlement_uses_inclusive_35_percent_boundary():
    boundary_conn, boundary_profile, boundary_nonce = _real_battle_db(
        spirit_id="fatty",
        level=25,
        monster_id="legacy_bf_08_normal",
        monster_hp=385,
        battle_id="d027-fatty-boundary",
    )
    above_conn, above_profile, above_nonce = _real_battle_db(
        spirit_id="fatty",
        level=25,
        monster_id="legacy_bf_08_normal",
        monster_hp=386,
        battle_id="d027-fatty-above",
    )
    wrong_conn, wrong_profile, wrong_nonce = _real_battle_db(
        spirit_id="fatty",
        level=25,
        monster_id="legacy_bf_08_normal",
        monster_hp=385,
        battle_id="d027-fatty-wrong",
    )
    try:
        boundary = _settle(
            boundary_conn,
            boundary_profile,
            boundary_nonce,
            battle_id="d027-fatty-boundary",
            correct=True,
        )
        above = _settle(
            above_conn,
            above_profile,
            above_nonce,
            battle_id="d027-fatty-above",
            correct=True,
        )
        wrong = _settle(
            wrong_conn,
            wrong_profile,
            wrong_nonce,
            battle_id="d027-fatty-wrong",
            correct=False,
        )
        assert boundary["damage_to_monster"] == 118
        assert above["damage_to_monster"] == 99
        assert wrong["damage_to_monster"] == 0
        assert wrong["damage_to_player"] == 20
    finally:
        boundary_conn.close()
        above_conn.close()
        wrong_conn.close()


def test_bastion_real_projection_settlement_preserves_incoming_reduction_without_min_one():
    conn, profile, nonce = _real_battle_db(
        spirit_id="obsidian_bastion",
        level=10,
        monster_id="legacy_bf_08_normal",
        player_hp=35,
        battle_id="d027-bastion",
    )
    try:
        result = _settle(
            conn,
            profile,
            nonce,
            battle_id="d027-bastion",
            correct=False,
        )
        conn.commit()
        # Stage-II Bastion reduces the canonical 20 incoming damage by 6;
        # unlike Void, this policy has no minimum-one override.
        assert result["damage_to_player"] == 14
        assert result["player_hp_after"] == 21
    finally:
        conn.close()


def _legacy_lord_db(spirit_id: str):
    """Minimal legacy caller fixture for the route's Lord exclusion seam."""

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
        """INSERT INTO player_inventory(id,user_id,equip_id,equipped)
           VALUES(1,1,'iron_sword',1)"""
    )
    conn.execute(
        """INSERT INTO battlefield_monster(
               user_id,bf_date,monster_idx,monster_type,monster_name,
               max_hp,current_hp
           ) VALUES(1,'2026-08-24',14,'golem','LV8 騎士 / 混沌領主',1100,1100)"""
    )
    conn.execute(
        """INSERT INTO user_pets(user_id,pet_key,selected_at,level)
           VALUES(1,?,'2026-08-24',25)""",
        (spirit_id,),
    )
    conn.execute(
        """INSERT INTO pet_collection(user_id,pet_key,selected_at,level,xp)
           VALUES(1,?,'2026-08-24',25,0)""",
        (spirit_id,),
    )
    conn.commit()
    return conn


def test_lord_trial_caller_excludes_all_six_spirits(monkeypatch):
    monkeypatch.setattr(app_module, "_update_daily_quests", lambda *args, **kwargs: [])
    monkeypatch.setattr(app_module, "_gain_sp", lambda _conn, _uid, amount: amount)

    def unexpected_spirit_call(*_args, **_kwargs):
        raise AssertionError("Lord Trial called the Spirit combat adapter")

    monkeypatch.setattr(app_module, "apply_spirit_combat_effect", unexpected_spirit_call)
    spirit_ids = (
        "ink_drop_kelpie",
        "whispering_void_kit",
        "star_shell_hatchling",
        "starpath_antlerling",
        "fatty",
        "obsidian_bastion",
    )
    committed_damage = []
    for index, spirit_id in enumerate(spirit_ids, start=1):
        conn = _legacy_lord_db(spirit_id)
        try:
            result = app_module._update_monster_and_quests(
                conn,
                1,
                9200 + index,
                5,
                {
                    "_server_authoritative_answer_correct": True,
                    # This is the same server-only exclusion marker set by
                    # the Lord Trial review caller in app.py.
                    "_spirit_effects_excluded": True,
                },
                0,
                "2026-08-24",
            )
            committed_damage.append(result["monster"]["dmg"])
        finally:
            conn.close()

    # Zone-8's canonical 1100-HP profile settles 99 before any Spirit
    # modifier; the same value for every active Spirit proves the Lord
    # exclusion, rather than a Spirit-specific damage result.
    assert committed_damage == [99] * 6
