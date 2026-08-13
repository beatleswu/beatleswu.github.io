"""R2A regression coverage for authoritative equipment combat effects."""

import os
import sqlite3
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "r2a-combat-equipment-test-secret")
import app as app_module  # noqa: E402


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


def _install_db(monkeypatch, path):
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(path))


def _create_combat_db(path, *, weapon="none", armor="cloth"):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
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
                character_key TEXT,
                combat_weapon TEXT,
                combat_armor TEXT,
                updated_at TEXT
            );
            CREATE TABLE player_inventory (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                equip_id TEXT NOT NULL,
                equipped INTEGER NOT NULL DEFAULT 0,
                obtained_at TEXT,
                source TEXT
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
            """
            INSERT INTO player_appearance(user_id,character_key,combat_weapon,
                                          combat_armor,updated_at)
            VALUES(1,'apprentice',?,?,?)
            """,
            (weapon, armor, "2026-08-14T00:00:00"),
        )
        conn.execute(
            """
            INSERT INTO battlefield_monster(
                user_id,bf_date,monster_idx,monster_type,monster_name,
                monster_avatar,max_hp,current_hp,defeated,kill_count
            ) VALUES(1,'2026-08-14',0,'goblin','LV1 哥布林','goblin.webp',1000,1000,0,0)
            """
        )


def _run_battle(path, monkeypatch, *, weapon="none", armor="cloth", grade=5, monster_atk=20):
    _create_combat_db(path, weapon=weapon, armor=armor)
    monkeypatch.setattr(app_module, "_update_daily_quests", lambda *args, **kwargs: [])
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


def test_equipped_weapon_changes_server_damage_and_unequip_restores_baseline(tmp_path, monkeypatch):
    baseline = _run_battle(tmp_path / "baseline.sqlite", monkeypatch)
    equipped = _run_battle(
        tmp_path / "equipped.sqlite", monkeypatch, weapon="weapon_t5"
    )
    unequipped = _run_battle(tmp_path / "unequipped.sqlite", monkeypatch)

    assert baseline["monster"]["dmg"] == 80
    assert equipped["monster"]["dmg"] == 88
    assert unequipped["monster"]["dmg"] == baseline["monster"]["dmg"]
    assert equipped["combat_stats"]["attack_bonus_pct"] == 10.0
    assert equipped["combat_stats"]["damage_reduction_pct"] == 0.0


def test_equipped_armor_changes_incoming_damage_and_unequip_restores_baseline(tmp_path, monkeypatch):
    baseline = _run_battle(
        tmp_path / "baseline.sqlite", monkeypatch, grade=0, monster_atk=20
    )
    equipped = _run_battle(
        tmp_path / "equipped.sqlite",
        monkeypatch,
        armor="armor_t5",
        grade=0,
        monster_atk=20,
    )
    unequipped = _run_battle(
        tmp_path / "unequipped.sqlite", monkeypatch, grade=0, monster_atk=20
    )

    assert baseline["monster"]["player_dmg"] == 20
    assert equipped["monster"]["player_dmg"] == 19
    assert unequipped["monster"]["player_dmg"] == baseline["monster"]["player_dmg"]
    assert equipped["combat_stats"]["damage_reduction_pct"] == 5.0


def test_legacy_weapon_effect_is_consumed_without_one_hit_scaling(tmp_path, monkeypatch):
    path = tmp_path / "legacy.sqlite"
    _create_combat_db(path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO player_inventory(id,user_id,equip_id,equipped,obtained_at,source)
            VALUES(1,1,'wooden_sword',1,'2026-08-14','drop')
            """
        )
    monkeypatch.setattr(app_module, "_update_daily_quests", lambda *args, **kwargs: [])
    monkeypatch.setattr(app_module, "_gain_sp", lambda conn, uid, amount: amount)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        result = app_module._update_monster_and_quests(
            conn, 1, 9001, 5, {"monster_atk": 8}, 0, "2026-08-14"
        )

    assert result["monster"]["dmg"] == 84
    assert result["monster"]["dmg"] < 1000
    assert result["combat_stats"]["attack_bonus_pct"] == 5.0


def test_invalid_or_legacy_loadout_data_contributes_no_combat_bonus(tmp_path):
    path = tmp_path / "invalid.sqlite"
    _create_combat_db(path, weapon="weapon_t999", armor="armor_removed")
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        stats = app_module._get_authoritative_combat_stats(conn, 1, "goblin")

    assert stats["attack_bonus"] == 0.0
    assert stats["damage_reduction"] == 0.0
    assert app_module._known_combat_gear_key("weapon", "weapon_t999") is False


def test_forged_client_stat_and_unknown_loadout_are_rejected(tmp_path, monkeypatch):
    path = tmp_path / "character.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE player_appearance(
                user_id INTEGER PRIMARY KEY,
                character_key TEXT,
                combat_weapon TEXT,
                updated_at TEXT
            )
            """
        )
    _install_db(monkeypatch, path)
    monkeypatch.setattr(
        app_module,
        "_compute_title_metrics",
        lambda uid, conn: {"go_rank": "7d", "total_correct": 20000},
    )
    monkeypatch.setattr(app_module, "_cosmetic_unlocked", lambda *args: True)
    monkeypatch.setattr(app_module, "is_premium", lambda uid: False)
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "r2a-test"

    response = client.post(
        "/api/skills/character",
        json={
            "character_key": "apprentice",
            "combat_weapon": "weapon_t999",
            "attack_bonus": 999999,
        },
    )
    assert response.status_code == 200
    assert "combat_weapon" in response.get_json()["rejected"]
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT combat_weapon FROM player_appearance WHERE user_id=1"
        ).fetchone()
    assert row[0] is None


def test_item_not_owned_cannot_be_equipped(tmp_path, monkeypatch):
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
            "INSERT INTO player_inventory VALUES(1,2,'wooden_sword',0,'2026-08-14','drop')"
        )
    _install_db(monkeypatch, path)
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "r2a-test"

    response = client.post(
        "/api/player/inventory/equip", json={"inv_id": 1, "action": "equip"}
    )
    assert response.status_code == 404
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT equipped FROM player_inventory WHERE id=1").fetchone()[0] == 0


def test_effective_stats_are_exposed_to_existing_player_ui():
    hero_source = Path(__file__).resolve().parents[1].joinpath("hero.html").read_text(
        encoding="utf-8"
    )
    assert "'combat_stats':      combat_stats" in Path(
        __file__
    ).resolve().parents[1].joinpath("app.py").read_text(encoding="utf-8")
    assert "res.combat_stats" in hero_source
    assert "attack_bonus_pct" in hero_source
    assert "damage_reduction_pct" in hero_source
