"""A034 Lane A runtime proof for the existing functional Equipment loop.

This test suite exercises the current c2 route path with a disposable legacy
SQLite inventory.  It intentionally leaves ``app.py`` and the schema
unchanged: the runtime already has a default-off canonical service seam, and
the live default path is the existing server-owned ``player_inventory`` route
writer.  The assertions prove that acquisition, Backpack, equip/replace,
unequip, Hero projection, reload, and the permanent locks all observe that
same state.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "a034-runtime-test-secret")
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
    def __init__(self, path: Path):
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


def _create_db(path: Path) -> None:
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
        conn.execute(
            """
            CREATE TABLE player_wardrobe(
                user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                obtained_at TEXT NOT NULL,
                source TEXT NOT NULL,
                PRIMARY KEY(user_id, item_id)
            )
            """
        )
        conn.execute(
            "INSERT INTO player_wardrobe(user_id,item_id,obtained_at,source) "
            "VALUES(1,'robe_plain','2026-08-28','drop')"
        )


def _client(path: Path, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(path))
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "a034-runtime"
    return client


def _grant(path: Path, equip_id: str):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        result = app_module.grant_equipment_ownership(
            conn, 1, equip_id, "drop", equipment_defs=app_module.EQUIPMENT_DEFS
        )
        conn.commit()
        return result


def _rows(path: Path):
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT id,equip_id,equipped FROM player_inventory "
            "WHERE user_id=1 ORDER BY id"
        ).fetchall()


def test_canonical_equipment_registry_has_exact_three_functional_slots():
    definitions = {str(item["id"]): item for item in app_module.EQUIPMENT_DEFS}
    assert set(definitions) == FUNCTIONAL_IDS
    assert len(definitions) == 15
    assert {
        slot for item in definitions.values() if (slot := item.get("slot"))
    } == {"weapon", "armor", "accessory"}
    assert {
        slot: sum(1 for item in definitions.values() if item.get("slot") == slot)
        for slot in ("weapon", "armor", "accessory")
    } == {"weapon": 5, "armor": 5, "accessory": 5}
    assert "go_stone_black" in app_module.INVENTORY_ONLY_EQUIPMENT_IDS

    for equip_id in sorted(FUNCTIONAL_IDS):
        payload = app_module._functional_equipment_payload(definitions[equip_id])
        assert payload["item_id"] == equip_id
        assert payload["functional_equipment"] is True
        assert payload["style_equipment"] is False


def test_acquire_backpack_equip_replace_unequip_and_reload_use_one_authority(
    tmp_path: Path, monkeypatch
):
    path = tmp_path / "a034-runtime.sqlite"
    _create_db(path)
    wooden = _grant(path, "wooden_sword")
    iron = _grant(path, "iron_sword")
    client = _client(path, monkeypatch)

    backpack = client.get("/api/player/inventory")
    assert backpack.status_code == 200
    by_id = {item["item_id"]: item for item in backpack.get_json()}
    assert set(by_id) == {"wooden_sword", "iron_sword"}
    assert all(item["equipped"] is False for item in by_id.values())
    assert all(item["functional_equipment"] is True for item in by_id.values())
    assert all(item["style_equipment"] is False for item in by_id.values())

    first = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": wooden.row_id, "action": "equip"},
    )
    assert first.status_code == 200
    assert first.get_json()["item_id"] == "wooden_sword"

    replacement = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": iron.row_id, "action": "equip"},
    )
    assert replacement.status_code == 200
    assert replacement.get_json()["item_id"] == "iron_sword"
    assert [(row[1], row[2]) for row in _rows(path)] == [
        ("wooden_sword", 0),
        ("iron_sword", 1),
    ]

    # Hero's functional projection and Backpack both read player_inventory;
    # no browser-local state or cosmetic wardrobe row is involved.
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        projection = app_module._functional_equipment_presentation_projection(conn, 1)
        combat = app_module._get_authoritative_combat_stats(conn, 1)
    assert projection == [
        {
            "equipment_id": "iron_sword",
            "slot": "weapon",
            "equipped": True,
            "presentation_only": True,
        }
    ]
    assert combat["attack_bonus"] == pytest.approx(0.12)

    reloaded = _client(path, monkeypatch)
    reloaded_items = {item["item_id"]: item for item in reloaded.get("/api/player/inventory").get_json()}
    assert reloaded_items["wooden_sword"]["equipped"] is False
    assert reloaded_items["iron_sword"]["equipped"] is True

    unequip = reloaded.post(
        "/api/player/inventory/equip",
        json={"inv_id": iron.row_id, "action": "unequip"},
    )
    assert unequip.status_code == 200
    assert [(row[1], row[2]) for row in _rows(path)] == [
        ("wooden_sword", 0),
        ("iron_sword", 0),
    ]
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        assert app_module._functional_equipment_presentation_projection(conn, 1) == []

    final_reload = _client(path, monkeypatch)
    final_items = final_reload.get("/api/player/inventory").get_json()
    assert all(item["equipped"] is False for item in final_items)


def test_duplicate_acquisition_is_distinct_owned_rows_and_unknown_fails_closed(
    tmp_path: Path, monkeypatch
):
    path = tmp_path / "a034-duplicate.sqlite"
    _create_db(path)
    first = _grant(path, "iron_sword")
    second = _grant(path, "iron_sword")
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO player_inventory(user_id,equip_id,equipped,obtained_at,source) "
            "VALUES(1,'unknown_item',0,'2026-08-28','drop')"
        )

    client = _client(path, monkeypatch)
    items = client.get("/api/player/inventory").get_json()
    assert {item["inv_id"] for item in items} == {first.row_id, second.row_id}
    assert {item["owned_quantity"] for item in items} == {2}
    assert all(item["item_id"] == "iron_sword" for item in items)

    bad_unknown = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 3, "action": "equip"},
    )
    assert bad_unknown.status_code == 400
    assert bad_unknown.get_json()["error"] == "無效的功能裝備"
    assert client.post(
        "/api/player/inventory/equip", json={"inv_id": 999, "action": "equip"}
    ).status_code == 404


def test_locked_items_stay_out_of_new_equip_but_legacy_xp_unequip_recovers(
    tmp_path: Path, monkeypatch
):
    path = tmp_path / "a034-locks.sqlite"
    _create_db(path)
    xp = _grant(path, "xp_amulet")
    stone = _grant(path, "go_stone_black")
    client = _client(path, monkeypatch)

    xp_equip = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": xp.row_id, "action": "equip"},
    )
    stone_equip = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": stone.row_id, "action": "equip"},
    )
    assert xp_equip.status_code == 400
    assert xp_equip.get_json()["error"] == "XP_AMULET_HOLD_FOR_AUTHORITY"
    assert stone_equip.status_code == 400
    assert stone_equip.get_json()["error"] == "此物品僅供收藏，不能裝備"

    # Simulate a pre-lock legacy row that was already equipped.  The existing
    # legacy route may remove it, but must never allow a new equip transition.
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE player_inventory SET equipped=1 WHERE id=?", (xp.row_id,))
    recovered = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": xp.row_id, "action": "unequip"},
    )
    assert recovered.status_code == 200
    assert recovered.get_json()["equipped"] is False
    assert _rows(path)[0][2] == 0

    # A legacy/corrupt trophy flag still cannot grant combat power: the
    # server active-effect allow-list excludes the inventory-only identity.
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE player_inventory SET equipped=1 WHERE id=?", (stone.row_id,))
        combat = app_module._get_authoritative_combat_stats(conn, 1)
    assert combat["attack_bonus"] == 0
    assert combat["crit_multiplier"] == 1
    assert combat["combo_multiplier_double"] is False
