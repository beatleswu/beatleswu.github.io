"""Wave 2 Gate 2 P1 proof for the functional-equipment Backpack surface.

These tests deliberately use small SQLite fixtures so they exercise the same
server routes and settlement helpers without changing the production schema or
requiring a shop, style-gear, or combat migration.
"""

import os
import sqlite3
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "rpg-wave2-gate2-equipment-test-secret")
import app as app_module  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
FUNCTIONAL_IDS = {
    "wooden_sword",
    "iron_sword",
    "fox_fang",
    "dragon_claw",
    "celestial_blade",
    "cloth_robe",
    "leather_armor",
    "fox_pelt",
    "dragon_scale",
    "void_mantle",
    "lucky_stone",
    "xp_amulet",
    "fox_mask",
    "dragon_eye",
    "go_stone_black",
}


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


def _create_inventory_db(path, rows=()):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE player_inventory(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                equip_id TEXT NOT NULL,
                equipped INTEGER NOT NULL DEFAULT 0,
                obtained_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'drop'
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO player_inventory(
                id,user_id,equip_id,equipped,obtained_at,source
            ) VALUES(?,?,?,?,?,?)
            """,
            rows,
        )


def _client_for(path, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(path))
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "wave2-gate2-test"
    return client


def _create_settlement_db(path, *, existing_drop=False):
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE user_stats(
                user_id INTEGER PRIMARY KEY,
                total_correct INTEGER NOT NULL DEFAULT 0,
                go_rank TEXT NOT NULL DEFAULT '30k',
                xp INTEGER NOT NULL DEFAULT 0,
                rank_level TEXT NOT NULL DEFAULT 'LV1',
                player_hp INTEGER NOT NULL DEFAULT 100,
                player_max_hp INTEGER NOT NULL DEFAULT 100
            );
            CREATE TABLE player_inventory(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                equip_id TEXT NOT NULL,
                equipped INTEGER NOT NULL DEFAULT 0,
                obtained_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'drop'
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
            INSERT INTO user_stats(
                user_id,total_correct,go_rank,xp,rank_level,player_hp,player_max_hp
            ) VALUES(1,2000,'5k',0,'LV1',100,100);
            INSERT INTO battlefield_monster(
                user_id,bf_date,monster_idx,monster_type,monster_name,
                monster_avatar,max_hp,current_hp,defeated,kill_count
            ) VALUES(1,'2026-08-14',0,'goblin','LV1 Goblin','goblin.webp',1000,80,0,0);
            """
        )
        if existing_drop:
            conn.execute(
                """
                INSERT INTO player_inventory(
                    user_id,equip_id,equipped,obtained_at,source
                ) VALUES(1,'iron_sword',0,'2026-08-13','drop')
                """
            )


def _run_settlement(path, monkeypatch, *, q_info=None, grade=5):
    monkeypatch.setattr(app_module, "_update_daily_quests", lambda *a, **k: [])
    monkeypatch.setattr(app_module, "_gain_sp", lambda conn, uid, amount: amount)
    monkeypatch.setattr(app_module, "_roll_loot", lambda monster_type, loot_bonus: "iron_sword")
    monkeypatch.setattr(app_module, "_roll_appearance_loot", lambda monster_type: None)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return app_module._update_monster_and_quests(
            conn,
            1,
            9001,
            grade,
            q_info or {"monster_atk": 999},
            0,
            "2026-08-14",
        )


def test_functional_registry_has_fifteen_dedicated_transparent_icons():
    assert set(app_module.FUNCTIONAL_EQUIPMENT_ART) == FUNCTIONAL_IDS
    assert len(app_module.FUNCTIONAL_EQUIPMENT_ART) == 15

    for item_id in FUNCTIONAL_IDS:
        art = app_module.FUNCTIONAL_EQUIPMENT_ART[item_id]
        assert art["icon_key"].startswith("rpg.equipment.functional.")
        assert art["icon_path"] == f"/assets/hero/equipment/functional/{item_id}.svg"
        icon_path = ROOT / art["icon_path"].lstrip("/")
        assert icon_path.is_file(), item_id
        svg = icon_path.read_text(encoding="utf-8")
        assert 'width="256"' in svg
        assert 'height="256"' in svg
        assert 'viewBox="0 0 256 256"' in svg
        assert "emoji" not in svg.lower()

        payload = app_module._functional_equipment_payload(app_module._EQUIP_MAP[item_id])
        assert payload["icon"] == art["icon_path"]
        assert payload["functional_equipment"] is True
        assert payload["style_equipment"] is False
        assert not any(character in payload["icon"] for character in "🗡️🛡️🎒💎")

    assert app_module._functional_effect_value_label("dmg_bonus", -0.05)[0] == "-5%"


def test_backpack_payload_matches_db_and_only_advertises_server_effects(tmp_path, monkeypatch):
    path = tmp_path / "backpack.sqlite"
    _create_inventory_db(
        path,
        rows=[
            (1, 1, "wooden_sword", 1, "2026-08-14", "drop"),
            (2, 1, "iron_sword", 0, "2026-08-13", "drop"),
            (3, 1, "iron_sword", 0, "2026-08-12", "drop"),
            (4, 1, "fox_pelt", 0, "2026-08-11", "drop"),
            (5, 1, "xp_amulet", 0, "2026-08-10", "drop"),
        ],
    )
    client = _client_for(path, monkeypatch)

    response = client.get("/api/player/inventory")
    assert response.status_code == 200
    items = response.get_json()
    by_id = {item["inv_id"]: item for item in items}

    assert set(by_id) == {1, 2, 3, 4, 5}
    assert by_id[1]["equipped"] is True
    assert by_id[2]["equipped"] is False
    assert by_id[2]["owned_quantity"] == 2
    assert by_id[2]["comparison_summary"]["same_slot_item_id"] == "wooden_sword"
    assert any(
        delta["key"] == "dmg_bonus" and delta["delta"] == pytest.approx(0.07)
        for delta in by_id[2]["comparison_summary"]["deltas"]
    )

    assert by_id[1]["effect_status"] == "SERVER_EFFECTIVE"
    assert by_id[4]["effect_status"] == "PARTIAL"
    assert {item["key"] for item in by_id[4]["unsupported_effects"]} == {"xp_bonus"}
    assert by_id[5]["effect_status"] == "DEFINED_ONLY"
    assert {item["key"] for item in by_id[5]["unsupported_effects"]} == {"xp_bonus"}
    assert all(item["icon"].startswith("/assets/hero/equipment/functional/") for item in items)
    assert all(item["functional_equipment"] is True for item in items)


def test_equip_unequip_uses_owned_inventory_and_ignores_client_effect_forgery(tmp_path, monkeypatch):
    path = tmp_path / "equip.sqlite"
    _create_inventory_db(
        path,
        rows=[
            (1, 1, "wooden_sword", 1, "2026-08-14", "drop"),
            (2, 1, "iron_sword", 0, "2026-08-13", "drop"),
            (3, 2, "dragon_claw", 0, "2026-08-13", "drop"),
        ],
    )
    client = _client_for(path, monkeypatch)

    response = client.post(
        "/api/player/inventory/equip",
        json={
            "inv_id": 2,
            "action": "equip",
            "damage": 999999,
            "rarity": "legendary",
            "effects": {"dmg_bonus": 999999},
        },
    )
    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "item_id": "iron_sword",
        "inv_id": 2,
        "equipped": True,
    }
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT equipped FROM player_inventory WHERE id=1"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT equipped FROM player_inventory WHERE id=2"
        ).fetchone()[0] == 1

    response = client.post(
        "/api/player/inventory/equip", json={"inv_id": 2, "action": "unequip"}
    )
    assert response.status_code == 200
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT equipped FROM player_inventory WHERE id=2"
        ).fetchone()[0] == 0

    assert client.post(
        "/api/player/inventory/equip", json={"inv_id": 2, "action": "forge"}
    ).status_code == 400
    assert client.post(
        "/api/player/inventory/equip", json={"inv_id": 3, "action": "equip"}
    ).status_code == 404


def test_loot_reveal_inserts_server_drop_as_un_equipped_and_handles_duplicates(tmp_path, monkeypatch):
    first_path = tmp_path / "first-drop.sqlite"
    _create_settlement_db(first_path)
    first = _run_settlement(first_path, monkeypatch)
    loot = first["loot"]

    assert loot["item_id"] == "iron_sword"
    assert loot["new"] is True
    assert loot["duplicate"] is False
    assert loot["currently_equipped"] is False
    assert loot["owned_quantity"] == 1
    assert loot["icon"] == "/assets/hero/equipment/functional/iron_sword.svg"
    with sqlite3.connect(first_path) as conn:
        assert conn.execute(
            "SELECT equip_id,equipped,source FROM player_inventory"
        ).fetchone() == ("iron_sword", 0, "drop")

    duplicate_path = tmp_path / "duplicate-drop.sqlite"
    _create_settlement_db(duplicate_path, existing_drop=True)
    duplicate = _run_settlement(duplicate_path, monkeypatch)["loot"]

    assert duplicate["item_id"] == "iron_sword"
    assert duplicate["new"] is False
    assert duplicate["duplicate"] is True
    assert duplicate["owned_quantity"] == 2
    assert duplicate["currently_equipped"] is False
    with sqlite3.connect(duplicate_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM player_inventory WHERE equip_id='iron_sword'"
        ).fetchone()[0] == 2
        assert conn.execute(
            "SELECT MAX(equipped) FROM player_inventory WHERE equip_id='iron_sword'"
        ).fetchone()[0] == 0


def test_monster_attack_input_cannot_override_server_roster():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "server_q_info['monster_atk'] = profile['attack']" in source
    assert "server_q_info['monster_atk'] = q_info.get('monster_atk')" not in source


def test_monster_settlement_uses_roster_attack_at_runtime(tmp_path, monkeypatch):
    path = tmp_path / "roster-attack.sqlite"
    _create_settlement_db(path)
    result = _run_settlement(path, monkeypatch, q_info={"monster_atk": 999}, grade=0)
    assert result["monster"]["player_dmg"] == 2
    assert result["monster"]["retaliation"] == {
        "attack": 2,
        "encounter_kind": "normal",
    }


def test_backpack_and_loot_frontend_contracts_keep_functional_and_style_separate():
    inventory = (ROOT / "inventory.html").read_text(encoding="utf-8")
    index = (ROOT / "index.html").read_text(encoding="utf-8")

    for label in (
        "戰鬥裝備 / Functional Equipment",
        "武器 / Weapon",
        "防具 / Armor",
        "飾品 / Accessory",
        "已裝備 / Equipped",
        "新取得 / New",
        "外觀裝備 / Hero Style Gear",
        "尚未啟用",
        "Not currently effective",
    ):
        assert label in inventory
    assert "fetch('/api/player/inventory'" in inventory
    assert "fetch('/api/player/inventory/equip'" in inventory
    assert "JSON.stringify({ inv_id:item.inv_id, action })" in inventory
    assert "comparison_summary" in inventory
    assert 'href="/hero?tab=equipment"' in inventory

    assert 'id="loot-toast-backpack"' in index
    assert "/inventory?equipment=" in index
    assert "functional_equipment_new_ids" in index
