"""Lane A proof: owned functional equipment changes authoritative combat."""

import os
import sqlite3

import pytest

os.environ.setdefault("SECRET_KEY", "rpg-wave1-lane-a-test-secret")
import app as app_module  # noqa: E402
from map_battle_runtime import calculate_damage  # noqa: E402


class _DbContext:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.conn.close()


def _create_combat_db(path, *, appearance_weapon=None):
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
            (1, appearance_weapon, None),
        )
        conn.execute(
            """
            INSERT INTO battlefield_monster(
                user_id,bf_date,monster_idx,monster_type,monster_name,
                monster_avatar,max_hp,current_hp,defeated,kill_count
            ) VALUES(1,'2026-08-14',0,'goblin','LV1 哥布林','goblin.webp',1000,1000,0,0)
            """
        )


def _run_battle(path, monkeypatch, *, equipment=(), grade=5, monster_atk=20,
                appearance_weapon=None):
    _create_combat_db(path, appearance_weapon=appearance_weapon)
    with sqlite3.connect(path) as conn:
        for row in equipment:
            conn.execute(
                """
                INSERT INTO player_inventory(
                    id,user_id,equip_id,equipped,obtained_at,source,rarity
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (row[0], 1, row[1], row[2], "2026-08-14", "drop", row[3]),
            )
    monkeypatch.setattr(app_module, "_update_daily_quests", lambda *a, **k: [])
    monkeypatch.setattr(app_module, "_gain_sp", lambda conn, uid, amount: amount)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return app_module._update_monster_and_quests(
            conn,
            1,
            9001,
            grade,
            {"monster_atk": monster_atk},
            0,
            "2026-08-14",
        )


def test_weapon_baseline_upgrade_and_unequip_change_authoritative_damage(tmp_path, monkeypatch):
    baseline = _run_battle(tmp_path / "baseline.sqlite", monkeypatch)
    weapon_a = _run_battle(
        tmp_path / "weapon-a.sqlite",
        monkeypatch,
        equipment=((1, "wooden_sword", 1, "common"),),
    )
    weapon_b = _run_battle(
        tmp_path / "weapon-b.sqlite",
        monkeypatch,
        equipment=((1, "iron_sword", 1, "legendary"),),
    )
    unequipped = _run_battle(
        tmp_path / "unequipped.sqlite",
        monkeypatch,
        equipment=((1, "iron_sword", 0, "common"),),
    )

    assert baseline["monster"]["dmg"] == 80
    assert weapon_a["monster"]["dmg"] == 84
    assert weapon_b["monster"]["dmg"] == 90
    assert unequipped["monster"]["dmg"] == baseline["monster"]["dmg"]
    assert weapon_a["monster"]["dmg"] > baseline["monster"]["dmg"]
    assert weapon_b["monster"]["dmg"] > weapon_a["monster"]["dmg"]


def test_equipped_armor_reduces_retaliation_and_unequip_restores_baseline(tmp_path, monkeypatch):
    baseline = _run_battle(
        tmp_path / "baseline.sqlite", monkeypatch, grade=0, monster_atk=20
    )
    equipped = _run_battle(
        tmp_path / "equipped.sqlite",
        monkeypatch,
        equipment=((1, "cloth_robe", 1, "legendary"),),
        grade=0,
        monster_atk=20,
    )
    unequipped = _run_battle(
        tmp_path / "unequipped.sqlite",
        monkeypatch,
        equipment=((1, "cloth_robe", 0, "common"),),
        grade=0,
        monster_atk=20,
    )

    # The current F004 profile for legacy roster slot 0 is attack=2.  The
    # q_info monster_atk=20 compatibility value is intentionally not a
    # Combat authority on this real path.  Armor still consumes the
    # authoritative retaliation and reduces 2 -> 1.
    assert baseline["monster"]["player_dmg"] == 2
    assert equipped["monster"]["player_dmg"] == 1
    assert unequipped["monster"]["player_dmg"] == baseline["monster"]["player_dmg"]
    assert equipped["combat_stats"]["damage_reduction_pct"] == 8.0


def test_appearance_projection_forged_attack_and_rarity_do_not_grant_combat(tmp_path, monkeypatch):
    result = _run_battle(
        tmp_path / "forged.sqlite",
        monkeypatch,
        appearance_weapon="weapon_t10",
    )

    assert result["monster"]["dmg"] == 80
    assert result["combat_stats"]["attack_bonus"] == 0.0
    assert result["combat_stats"]["damage_reduction"] == 0.0


def test_unowned_item_equip_is_denied(tmp_path, monkeypatch):
    path = tmp_path / "ownership.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE player_inventory(
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                equip_id TEXT NOT NULL,
                equipped INTEGER NOT NULL DEFAULT 0,
                obtained_at TEXT,
                source TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO player_inventory VALUES(1,2,'iron_sword',0,'2026-08-14','drop')"
        )

    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(path))
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "lane-a-test"

    response = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 1, "action": "equip", "attack": 999, "rarity": "legendary"},
    )
    assert response.status_code == 404
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT equipped FROM player_inventory WHERE id=1").fetchone()[0] == 0


def test_duplicate_equip_request_is_idempotent(tmp_path, monkeypatch):
    path = tmp_path / "duplicate.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE player_inventory(
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                equip_id TEXT NOT NULL,
                equipped INTEGER NOT NULL DEFAULT 0,
                obtained_at TEXT,
                source TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO player_inventory VALUES(?,?,?,?,?,?)",
            [
                (1, 1, "wooden_sword", 1, "2026-08-14", "drop"),
                (2, 1, "iron_sword", 0, "2026-08-14", "drop"),
            ],
        )

    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(path))
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "lane-a-test"

    first = client.post("/api/player/inventory/equip", json={"inv_id": 2, "action": "equip"})
    second = client.post("/api/player/inventory/equip", json={"inv_id": 2, "action": "equip"})
    assert first.status_code == second.status_code == 409
    assert first.get_json() == second.get_json() == {"error": "LOADOUT_DISABLED"}
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM player_inventory WHERE user_id=1 AND equipped=1"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT equipped FROM player_inventory WHERE id=2"
        ).fetchone()[0] == 0


def test_legacy_player_without_equipment_is_safe(tmp_path, monkeypatch):
    result = _run_battle(tmp_path / "legacy.sqlite", monkeypatch)
    assert result["monster"]["dmg"] == 80
    assert result["combat_stats"]["attack_bonus_pct"] == 0.0
    assert result["combat_stats"]["damage_reduction_pct"] == 0.0


def test_accessory_effects_remain_non_combat_effects(tmp_path, monkeypatch):
    path = tmp_path / "accessory.sqlite"
    _create_combat_db(path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO player_inventory(id,user_id,equip_id,equipped,obtained_at,source) "
            "VALUES(1,1,'lucky_stone',1,'2026-08-14','drop')"
        )
        conn.row_factory = sqlite3.Row
        stats = app_module._get_authoritative_combat_stats(conn, 1, "goblin")
        loot_bonus = app_module._get_equip_effect(conn, 1, "loot_bonus")

    assert stats["attack_bonus"] == 0.0
    assert stats["damage_reduction"] == 0.0
    assert loot_bonus == pytest.approx(0.10)


def test_map_battle_uses_bounded_equipment_modifiers_without_client_authority():
    assert calculate_damage("CORRECT", 5, 1000, attack_bonus=0.12) == (90, 0)
    assert calculate_damage("INCORRECT", 0, 1000, {"monster_atk": 20}, damage_reduction=0.08) == (0, 18)
    assert calculate_damage("CORRECT", 5, 1000, attack_bonus=999) == (140, 0)
