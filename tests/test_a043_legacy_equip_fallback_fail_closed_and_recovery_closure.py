"""A043 server-side closure of the disabled legacy functional equip path."""

from __future__ import annotations

import os
import sqlite3

import pytest

os.environ.setdefault("SECRET_KEY", "a043-legacy-equip-closure-test-secret")
import app as app_module  # noqa: E402
from db import PostgresConnectionWrapper  # noqa: E402
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_b033  # noqa: E402
from postgres_test_harness import disposable_postgres  # noqa: E402


class _DbContext:
    def __init__(self, path):
        self.path = path
        self.conn = None

    def __enter__(self):
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()


def _create_inventory(path, rows, *, b033=False):
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE player_inventory("
            "id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,equip_id TEXT NOT NULL,"
            "equipped INTEGER NOT NULL DEFAULT 0,obtained_at TEXT NOT NULL,"
            "source TEXT NOT NULL DEFAULT 'test')"
        )
        if b033:
            upgrade_b033(conn, equipment_defs=app_module.EQUIPMENT_DEFS)
        for row_id, user_id, equip_id, equipped in rows:
            slot = (
                app_module._EQUIP_MAP.get(equip_id, {}).get("slot")
                if equipped
                else None
            )
            if b033:
                conn.execute(
                    "INSERT INTO player_inventory"
                    "(id,user_id,equip_id,equipped,canonical_slot,obtained_at,source)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (row_id, user_id, equip_id, equipped, slot, "2026-08-29", "test"),
                )
            else:
                conn.execute(
                    "INSERT INTO player_inventory"
                    "(id,user_id,equip_id,equipped,obtained_at,source)"
                    " VALUES(?,?,?,?,?,?)",
                    (row_id, user_id, equip_id, equipped, "2026-08-29", "test"),
                )


def _rows(path):
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT id,user_id,equip_id,equipped FROM player_inventory ORDER BY id"
        ).fetchall()


def _client(path, monkeypatch, *, loadout_enabled=False, user_id=1):
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(path))
    if loadout_enabled:
        monkeypatch.setenv(app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG, "1")
    else:
        monkeypatch.delenv(app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG, raising=False)
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["username"] = f"a043-user-{user_id}"
    return client


def test_disabled_legacy_equip_and_replacement_fail_closed_without_mutation(
    tmp_path, monkeypatch
):
    path = tmp_path / "disabled-replacement.sqlite"
    _create_inventory(path, [(1, 1, "wooden_sword", 1), (2, 1, "iron_sword", 0)])
    client = _client(path, monkeypatch)
    before = _rows(path)

    response = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 2, "action": "equip"},
    )

    assert response.status_code == 409
    assert response.get_json() == {"error": "LOADOUT_DISABLED"}
    assert _rows(path) == before
    assert _rows(path)[0][3] == 1
    assert _rows(path)[1][3] == 0


def test_disabled_owned_unequipped_item_cannot_be_newly_equipped(tmp_path, monkeypatch):
    path = tmp_path / "disabled-new-equip.sqlite"
    _create_inventory(path, [(1, 1, "wooden_sword", 0)])
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 1, "action": "equip"},
    )

    assert response.status_code == 409
    assert response.get_json() == {"error": "LOADOUT_DISABLED"}
    assert _rows(path) == [(1, 1, "wooden_sword", 0)]


def test_disabled_unequip_recovery_is_fail_closed_and_replay_is_safe(tmp_path, monkeypatch):
    path = tmp_path / "legacy-unequip-recovery.sqlite"
    _create_inventory(path, [(1, 1, "wooden_sword", 1), (2, 1, "iron_sword", 0)])
    client = _client(path, monkeypatch)
    before = _rows(path)

    response = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 1, "action": "unequip"},
    )
    replay = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 1, "action": "unequip"},
    )

    assert response.status_code == 409
    assert response.get_json() == {"error": "LOADOUT_DISABLED"}
    assert replay.status_code == 409
    assert replay.get_json() == {"error": "LOADOUT_DISABLED"}
    assert _rows(path) == before == [
        (1, 1, "wooden_sword", 1),
        (2, 1, "iron_sword", 0),
    ]


def test_locks_preserved_while_disabled(tmp_path, monkeypatch):
    path = tmp_path / "disabled-locks.sqlite"
    _create_inventory(path, [(1, 1, "xp_amulet", 0), (2, 1, "xp_amulet", 1)])
    client = _client(path, monkeypatch)

    new_equip = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 1, "action": "equip"},
    )
    recovery = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 2, "action": "unequip"},
    )

    assert new_equip.status_code == 409
    assert recovery.status_code == 409
    assert recovery.get_json() == {"error": "LOADOUT_DISABLED"}
    assert _rows(path) == [
        (1, 1, "xp_amulet", 0),
        (2, 1, "xp_amulet", 1),
    ]


@pytest.mark.parametrize("action", ["equip", "unequip"])
def test_cross_user_and_malformed_requests_fail_closed(tmp_path, monkeypatch, action):
    path = tmp_path / f"security-{action}.sqlite"
    _create_inventory(path, [(1, 2, "wooden_sword", 1)])
    client = _client(path, monkeypatch, user_id=1)

    cross_user = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 1, "action": action},
    )
    malformed = client.post(
        "/api/player/inventory/equip",
        json={"action": action},
    )

    assert cross_user.status_code == 404
    assert malformed.status_code == 404
    assert _rows(path) == [(1, 2, "wooden_sword", 1)]


def test_unknown_owned_item_is_fail_closed_while_disabled(tmp_path, monkeypatch):
    path = tmp_path / "unknown-item.sqlite"
    _create_inventory(path, [(1, 1, "unknown_equipment", 0)])
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 1, "action": "equip", "slot": "weapon"},
    )

    assert response.status_code == 409
    assert response.get_json() == {"error": "LOADOUT_DISABLED"}
    assert _rows(path) == [(1, 1, "unknown_equipment", 0)]


def test_flag_on_canonical_loadout_behavior_is_preserved(tmp_path, monkeypatch):
    path = tmp_path / "flag-on-canonical.sqlite"
    _create_inventory(path, [(1, 1, "wooden_sword", 1), (2, 1, "iron_sword", 0)], b033=True)
    client = _client(path, monkeypatch, loadout_enabled=True)

    replacement = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 2, "action": "equip", "slot": "armor"},
    )
    unequip = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 2, "action": "unequip"},
    )

    assert replacement.status_code == 200
    assert replacement.get_json()["canonical_slot"] == "weapon"
    assert unequip.status_code == 200
    assert _rows(path) == [
        (1, 1, "wooden_sword", 0),
        (2, 1, "iron_sword", 0),
    ]


def _connect_postgres(url):
    import psycopg2
    from psycopg2.extras import DictCursor

    raw = psycopg2.connect(url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


class _PostgresDbContext:
    def __init__(self, url):
        self.url = url
        self.conn = None

    def __enter__(self):
        self.conn = _connect_postgres(self.url)
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()


@pytest.fixture()
def a043_postgres_url():
    with disposable_postgres(name_prefix="a043-legacy-equip") as record:
        url = str(record["database_url"])
        conn = _connect_postgres(url)
        try:
            conn.execute(
                "CREATE TABLE player_inventory("
                "id SERIAL PRIMARY KEY,user_id INTEGER NOT NULL,"
                "equip_id TEXT NOT NULL,equipped INTEGER NOT NULL DEFAULT 0,"
                "obtained_at TEXT,source TEXT)"
            )
            conn.commit()
        finally:
            conn.close()
        yield url
        conn = _connect_postgres(url)
        try:
            conn.execute("DROP TABLE IF EXISTS player_inventory CASCADE")
            conn.commit()
        finally:
            conn.close()


def _reset_postgres_inventory(url, *, b033=False):
    conn = _connect_postgres(url)
    try:
        conn.execute("TRUNCATE player_inventory RESTART IDENTITY")
        if b033:
            upgrade_b033(conn, equipment_defs=app_module.EQUIPMENT_DEFS)
        if b033:
            conn.execute(
                "INSERT INTO player_inventory"
                "(user_id,equip_id,equipped,canonical_slot,obtained_at,source)"
                " VALUES(?,?,?,?,?,?)",
                (7, "wooden_sword", 1, "weapon", "2026-08-29", "test"),
            )
            conn.execute(
                "INSERT INTO player_inventory"
                "(user_id,equip_id,equipped,canonical_slot,obtained_at,source)"
                " VALUES(?,?,?,?,?,?)",
                (7, "iron_sword", 0, None, "2026-08-29", "test"),
            )
        else:
            conn.execute(
                "INSERT INTO player_inventory"
                "(user_id,equip_id,equipped,obtained_at,source) VALUES(?,?,?,?,?)",
                (7, "wooden_sword", 1, "2026-08-29", "test"),
            )
            conn.execute(
                "INSERT INTO player_inventory"
                "(user_id,equip_id,equipped,obtained_at,source) VALUES(?,?,?,?,?)",
                (7, "iron_sword", 0, "2026-08-29", "test"),
            )
        conn.commit()
    finally:
        conn.close()


def _postgres_rows(url):
    conn = _connect_postgres(url)
    try:
        return [
            tuple(row)
            for row in conn.execute(
                "SELECT id,user_id,equip_id,equipped FROM player_inventory ORDER BY id"
            ).fetchall()
        ]
    finally:
        conn.close()


def _postgres_client(url, monkeypatch, *, loadout_enabled=False):
    monkeypatch.setattr(app_module, "get_db", lambda: _PostgresDbContext(url))
    if loadout_enabled:
        monkeypatch.setenv(app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG, "1")
    else:
        monkeypatch.delenv(app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG, raising=False)
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
        session["username"] = "a043-pg-test"
    return client


def test_postgres_disabled_loadout_and_flag_on_parity(a043_postgres_url, monkeypatch):
    _reset_postgres_inventory(a043_postgres_url)
    client = _postgres_client(a043_postgres_url, monkeypatch)

    replacement = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 2, "action": "equip"},
    )
    recovery = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 1, "action": "unequip"},
    )

    assert replacement.status_code == 409
    assert recovery.status_code == 409
    assert recovery.get_json() == {"error": "LOADOUT_DISABLED"}
    assert _postgres_rows(a043_postgres_url) == [
        (1, 7, "wooden_sword", 1),
        (2, 7, "iron_sword", 0),
    ]

    _reset_postgres_inventory(a043_postgres_url, b033=True)
    canonical_client = _postgres_client(
        a043_postgres_url, monkeypatch, loadout_enabled=True
    )
    canonical = canonical_client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 2, "action": "equip"},
    )
    assert canonical.status_code == 200
    assert canonical.get_json()["canonical_slot"] == "weapon"
    assert _postgres_rows(a043_postgres_url) == [
        (1, 7, "wooden_sword", 0),
        (2, 7, "iron_sword", 1),
    ]
