"""B036 proof: the legacy equip route preserves the xp_amulet hold lock."""

import os
import sqlite3

import pytest

os.environ.setdefault("SECRET_KEY", "b036-xp-amulet-test-secret")
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


def _create_inventory_db(path, rows):
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
                (row_id, 1, equip_id, equipped, "2026-08-25", "b036-test")
                for row_id, equip_id, equipped in rows
            ],
        )


def _client(path, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(path))
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "b036-test"
    return client


def _inventory(path):
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT id,equip_id,equipped FROM player_inventory ORDER BY id"
        ).fetchall()


def test_xp_amulet_equip_rejected_and_does_not_mutate_or_consume(tmp_path, monkeypatch):
    path = tmp_path / "xp-amulet-reject.sqlite"
    _create_inventory_db(path, [(1, "lucky_stone", 1), (2, "xp_amulet", 0)])
    client = _client(path, monkeypatch)

    before = _inventory(path)
    response = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 2, "action": "equip"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "XP_AMULET_HOLD_FOR_AUTHORITY"}
    assert _inventory(path) == before


def test_xp_amulet_rejection_preserves_existing_accessory(tmp_path, monkeypatch):
    path = tmp_path / "xp-amulet-slot.sqlite"
    _create_inventory_db(path, [(1, "lucky_stone", 1), (2, "xp_amulet", 0)])
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 2, "action": "equip"},
    )

    assert response.status_code == 400
    assert _inventory(path) == [
        (1, "lucky_stone", 1),
        (2, "xp_amulet", 0),
    ]


def test_malformed_equipped_xp_amulet_can_still_be_unequipped(tmp_path, monkeypatch):
    path = tmp_path / "xp-amulet-unequip.sqlite"
    _create_inventory_db(path, [(1, "xp_amulet", 1)])
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 1, "action": "unequip"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "item_id": "xp_amulet",
        "inv_id": 1,
        "equipped": False,
    }
    assert _inventory(path) == [(1, "xp_amulet", 0)]


def test_go_stone_black_equip_remains_rejected(tmp_path, monkeypatch):
    path = tmp_path / "go-stone.sqlite"
    _create_inventory_db(path, [(1, "go_stone_black", 0)])
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 1, "action": "equip"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "此物品僅供收藏，不能裝備"}
    assert _inventory(path) == [(1, "go_stone_black", 0)]


def test_normal_accessory_equip_still_succeeds(tmp_path, monkeypatch):
    path = tmp_path / "accessory.sqlite"
    _create_inventory_db(path, [(1, "lucky_stone", 0)])
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 1, "action": "equip"},
    )

    assert response.status_code == 200
    assert _inventory(path) == [(1, "lucky_stone", 1)]


@pytest.mark.parametrize("equip_id", ["iron_sword", "cloth_robe"])
def test_normal_weapon_and_armor_equip_still_succeed(tmp_path, monkeypatch, equip_id):
    path = tmp_path / f"{equip_id}.sqlite"
    _create_inventory_db(path, [(1, equip_id, 0)])
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 1, "action": "equip"},
    )

    assert response.status_code == 200
    assert _inventory(path) == [(1, equip_id, 1)]


def test_normal_unequip_still_succeeds(tmp_path, monkeypatch):
    path = tmp_path / "unequip.sqlite"
    _create_inventory_db(path, [(1, "iron_sword", 1)])
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 1, "action": "unequip"},
    )

    assert response.status_code == 200
    assert _inventory(path) == [(1, "iron_sword", 0)]


def test_client_cannot_override_owned_item_identity_or_slot(tmp_path, monkeypatch):
    path = tmp_path / "server-identity.sqlite"
    _create_inventory_db(path, [(1, "iron_sword", 0)])
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/player/inventory/equip",
        json={
            "inv_id": 1,
            "action": "equip",
            "equip_id": "xp_amulet",
            "slot": "accessory",
            "attack_bonus": 999,
        },
    )

    assert response.status_code == 200
    assert response.get_json()["item_id"] == "iron_sword"
    assert _inventory(path) == [(1, "iron_sword", 1)]
