"""B042 proof that canonical Equipment state reaches Combat exactly once."""

from __future__ import annotations

import os
import sqlite3

import pytest

os.environ.setdefault("SECRET_KEY", "b042-equipment-combat-effect-test-secret")

import app as app_module  # noqa: E402
import equipment_loadout_service as loadout  # noqa: E402


def _inventory_conn(rows=()):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE player_inventory (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            equip_id TEXT NOT NULL,
            equipped INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE player_skills (
            user_id INTEGER NOT NULL,
            skill_id TEXT NOT NULL,
            equipped INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    conn.executemany(
        "INSERT INTO player_inventory(id,user_id,equip_id,equipped) VALUES(?,?,?,?)",
        rows,
    )
    return conn


def test_equipped_weapon_changes_canonical_damage_and_unequip_restores_baseline():
    conn = _inventory_conn()
    try:
        baseline_stats = app_module._get_authoritative_combat_stats(conn, 1)
        baseline_damage = app_module._calc_damage(
            5,
            1000,
            attack_bonus=baseline_stats["attack_bonus"],
            crit_multiplier=baseline_stats["crit_multiplier"],
        )

        conn.execute(
            "INSERT INTO player_inventory(id,user_id,equip_id,equipped) VALUES(1,1,'iron_sword',1)"
        )
        equipped_stats = app_module._get_authoritative_combat_stats(conn, 1)
        equipped_damage = app_module._calc_damage(
            5,
            1000,
            attack_bonus=equipped_stats["attack_bonus"],
            crit_multiplier=equipped_stats["crit_multiplier"],
        )

        conn.execute("UPDATE player_inventory SET equipped=0 WHERE id=1")
        unequipped_stats = app_module._get_authoritative_combat_stats(conn, 1)
        unequipped_damage = app_module._calc_damage(
            5,
            1000,
            attack_bonus=unequipped_stats["attack_bonus"],
            crit_multiplier=unequipped_stats["crit_multiplier"],
        )

        assert baseline_damage == 80
        assert equipped_stats["attack_bonus"] == pytest.approx(0.12)
        assert equipped_damage == 90
        assert unequipped_stats["attack_bonus"] == 0
        assert unequipped_damage == baseline_damage
    finally:
        conn.close()


def test_equipped_armor_changes_canonical_incoming_damage_and_unequip_restores_baseline():
    conn = _inventory_conn()
    try:
        baseline_stats = app_module._get_authoritative_combat_stats(conn, 1)
        baseline_damage = app_module._mitigate_authoritative_retaliation(
            20, baseline_stats["damage_reduction"]
        )

        conn.execute(
            "INSERT INTO player_inventory(id,user_id,equip_id,equipped) VALUES(1,1,'leather_armor',1)"
        )
        equipped_stats = app_module._get_authoritative_combat_stats(conn, 1)
        equipped_damage = app_module._mitigate_authoritative_retaliation(
            20, equipped_stats["damage_reduction"]
        )

        conn.execute("UPDATE player_inventory SET equipped=0 WHERE id=1")
        unequipped_stats = app_module._get_authoritative_combat_stats(conn, 1)
        unequipped_damage = app_module._mitigate_authoritative_retaliation(
            20, unequipped_stats["damage_reduction"]
        )

        assert baseline_stats["damage_reduction"] == 0
        assert baseline_damage == 20
        assert equipped_stats["damage_reduction"] == pytest.approx(0.15)
        assert equipped_damage == 17
        assert unequipped_stats["damage_reduction"] == 0
        assert unequipped_damage == baseline_damage
    finally:
        conn.close()


def test_server_defined_accessory_critical_effect_changes_grade_five_damage():
    conn = _inventory_conn(
        rows=((1, 1, "dragon_eye", 1),),
    )
    try:
        stats = app_module._get_authoritative_combat_stats(conn, 1)
        damage = app_module._calc_damage(
            5,
            1000,
            attack_bonus=stats["attack_bonus"],
            crit_multiplier=stats["crit_multiplier"],
        )

        assert stats["crit_multiplier"] == pytest.approx(3.0)
        assert damage == 240
    finally:
        conn.close()


def test_duplicate_ownership_uses_only_the_exact_equipped_row():
    conn = _inventory_conn(
        rows=(
            (101, 1, "iron_sword", 0),
            (205, 1, "iron_sword", 1),
        ),
    )
    try:
        stats = app_module._get_authoritative_combat_stats(conn, 1)
        damage = app_module._calc_damage(
            5,
            1000,
            attack_bonus=stats["attack_bonus"],
            crit_multiplier=stats["crit_multiplier"],
        )

        assert stats["attack_bonus"] == pytest.approx(0.12)
        assert damage == 90
        assert [tuple(row) for row in conn.execute(
            "SELECT id FROM player_inventory WHERE user_id=1 AND equipped=1"
        ).fetchall()] == [(205,)]
    finally:
        conn.close()


def test_hold_and_inventory_only_items_have_no_canonical_combat_effect():
    conn = _inventory_conn(
        rows=(
            (1, 1, "xp_amulet", 1),
            (2, 1, "go_stone_black", 1),
        ),
    )
    try:
        stats = app_module._get_authoritative_combat_stats(conn, 1)

        assert stats == {
            "attack_bonus": 0.0,
            "attack_bonus_pct": 0.0,
            "damage_reduction": 0.0,
            "damage_reduction_pct": 0.0,
            "crit_multiplier": 1.0,
            "counter_negated": False,
            "combo_multiplier_double": False,
        }
        assert app_module._get_active_equip_effect(conn, 1, "first_question_ace") == 0
        assert app_module._get_active_equip_effect(conn, 1, "xp_bonus") == 0
    finally:
        conn.close()


def test_malformed_equipped_state_is_rejected_by_loadout_authority(
    monkeypatch,
):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE player_inventory(
             id INTEGER PRIMARY KEY,
             user_id INTEGER NOT NULL,
             equip_id TEXT NOT NULL,
             equipped INTEGER NOT NULL DEFAULT 0,
             canonical_slot TEXT
        )"""
    )
    conn.executemany(
        "INSERT INTO player_inventory(id,user_id,equip_id,equipped,canonical_slot) "
        "VALUES(?,?,?,?,?)",
        (
            (101, 1, "wooden_sword", 1, "weapon"),
            (205, 1, "iron_sword", 1, "weapon"),
        ),
    )
    monkeypatch.setattr(loadout, "validate_schema", lambda _conn: {"valid": True})
    try:
        with pytest.raises(loadout.EquipmentLoadoutError) as error:
            loadout.equip_owned_item(
                conn,
                1,
                "iron_sword",
                ownership_row_id=205,
                equipment_defs=(
                    {"id": "wooden_sword", "slot": "weapon"},
                    {"id": "iron_sword", "slot": "weapon"},
                ),
            )

        assert error.value.code == "MALFORMED_EQUIPPED_STATE"
        assert tuple(
            conn.execute(
                "SELECT id,equipped,canonical_slot FROM player_inventory ORDER BY id"
            ).fetchall()[0]
        ) == (101, 1, "weapon")
        assert tuple(
            conn.execute(
                "SELECT id,equipped,canonical_slot FROM player_inventory ORDER BY id"
            ).fetchall()[1]
        ) == (205, 1, "weapon")
    finally:
        conn.close()
