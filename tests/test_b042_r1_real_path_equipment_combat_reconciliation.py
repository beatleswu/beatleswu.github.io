"""B042-R1 executable reconciliation of the current real Combat path."""

from __future__ import annotations

import os
import sqlite3

import pytest

os.environ.setdefault("SECRET_KEY", "b042-r1-real-path-combat-test-secret")

import app as app_module  # noqa: E402
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_b033  # noqa: E402


TEST_EQUIPMENT_DEFS = (
    {"id": "wooden_sword", "slot": "weapon"},
    {"id": "iron_sword", "slot": "weapon"},
    {"id": "cloth_robe", "slot": "armor"},
)


def _create_real_path_db(path, *, monster_idx: int, equipment=()):
    monster_type, monster_name, max_hp, _attack, _encounter_kind = (
        app_module._BATTLEFIELD_ROSTER[monster_idx]
    )
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE user_stats (
                user_id INTEGER PRIMARY KEY,
                total_correct INTEGER NOT NULL DEFAULT 0,
                go_rank TEXT NOT NULL DEFAULT '30k',
                xp INTEGER NOT NULL DEFAULT 0,
                rank_level TEXT NOT NULL DEFAULT 'LV1',
                player_hp INTEGER NOT NULL DEFAULT 100,
                player_max_hp INTEGER NOT NULL DEFAULT 100
            );
            CREATE TABLE player_appearance (
                user_id INTEGER PRIMARY KEY,
                combat_weapon TEXT,
                combat_armor TEXT
            );
            CREATE TABLE player_inventory (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                equip_id TEXT NOT NULL,
                equipped INTEGER NOT NULL DEFAULT 0,
                obtained_at TEXT,
                source TEXT,
                rarity TEXT
            );
            CREATE TABLE player_skills (
                user_id INTEGER NOT NULL,
                skill_id TEXT NOT NULL,
                equipped INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, skill_id)
            );
            CREATE TABLE battlefield_monster (
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
                PRIMARY KEY (user_id, bf_date)
            );
            """
        )
        conn.execute(
            "INSERT INTO user_stats(user_id,total_correct,go_rank) VALUES(1,?,?)",
            (2000, "5k"),
        )
        conn.execute(
            "INSERT INTO player_appearance(user_id,combat_weapon,combat_armor) VALUES(?,?,?)",
            (1, None, None),
        )
        conn.execute(
            """INSERT INTO battlefield_monster(
                 user_id,bf_date,monster_idx,monster_type,monster_name,
                 monster_avatar,max_hp,current_hp,defeated,kill_count
               ) VALUES(1,'2026-08-14',?,?,?,?,?,?,0,0)""",
            (monster_idx, monster_type, monster_name, "golem.webp", max_hp, max_hp),
        )
        for row_id, equip_id, equipped in equipment:
            conn.execute(
                """INSERT INTO player_inventory(
                     id,user_id,equip_id,equipped,obtained_at,source,rarity
                   ) VALUES(?,?,?,?,?,?,?)""",
                (row_id, 1, equip_id, equipped, "2026-08-14", "test", "common"),
            )


def _run_real_path_battle(path, monkeypatch, *, monster_idx, equipment=(), grade=0):
    _create_real_path_db(path, monster_idx=monster_idx, equipment=equipment)
    monkeypatch.setattr(app_module, "_update_daily_quests", lambda *args, **kwargs: [])
    monkeypatch.setattr(app_module, "_gain_sp", lambda conn, uid, amount: amount)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return app_module._update_monster_and_quests(
            conn,
            1,
            9042,
            grade,
            # This value is deliberately different from the canonical slot
            # 16 attack. The real path must not use question-side attack data.
            {"monster_atk": 999},
            0,
            "2026-08-14",
        )


def test_real_path_armor_consumes_f008_attack_and_restores_on_unequip(
    tmp_path, monkeypatch
):
    baseline = _run_real_path_battle(
        tmp_path / "baseline.sqlite", monkeypatch, monster_idx=16
    )
    equipped = _run_real_path_battle(
        tmp_path / "equipped.sqlite",
        monkeypatch,
        monster_idx=16,
        equipment=((1, "cloth_robe", 1),),
    )
    unequipped = _run_real_path_battle(
        tmp_path / "unequipped.sqlite",
        monkeypatch,
        monster_idx=16,
        equipment=((1, "cloth_robe", 0),),
    )

    # Persisted index 16 resolves through the current F004 identity registry
    # to legacy_bf_09_normal, whose authoritative profile attack is 28.
    assert baseline["monster"]["player_dmg"] == 28
    assert equipped["monster"]["player_dmg"] == 26
    assert unequipped["monster"]["player_dmg"] == baseline["monster"]["player_dmg"]
    assert equipped["combat_stats"]["damage_reduction_pct"] == 8.0
    assert baseline["monster"]["retaliation"]["attack"] == 28


def test_real_path_dragon_eye_reaches_grade_five_damage(tmp_path, monkeypatch):
    baseline = _run_real_path_battle(
        tmp_path / "baseline.sqlite", monkeypatch, monster_idx=16, grade=5
    )
    equipped = _run_real_path_battle(
        tmp_path / "dragon-eye.sqlite",
        monkeypatch,
        monster_idx=16,
        equipment=((1, "dragon_eye", 1),),
        grade=5,
    )

    assert baseline["monster"]["dmg"] == 136
    assert equipped["monster"]["dmg"] == 408
    assert equipped["combat_stats"]["crit_multiplier"] == pytest.approx(3.0)


def test_b033_valid_storage_rejects_null_equipped_slot_and_duplicate_slot():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
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
    try:
        upgrade_b033(conn, equipment_defs=TEST_EQUIPMENT_DEFS)
        conn.commit()
        conn.execute(
            "INSERT INTO player_inventory"
            "(id,user_id,equip_id,equipped,canonical_slot) VALUES(?,?,?,?,?)",
            (1, 1, "iron_sword", 1, "weapon"),
        )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO player_inventory"
                "(id,user_id,equip_id,equipped,canonical_slot) VALUES(?,?,?,?,?)",
                (2, 1, "wooden_sword", 1, "weapon"),
            )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO player_inventory"
                "(id,user_id,equip_id,equipped,canonical_slot) VALUES(?,?,?,?,?)",
                (3, 1, "cloth_robe", 1, None),
            )

        assert [tuple(row) for row in conn.execute(
            "SELECT id,equipped,canonical_slot FROM player_inventory"
        ).fetchall()] == [(1, 1, "weapon")]
    finally:
        conn.close()
