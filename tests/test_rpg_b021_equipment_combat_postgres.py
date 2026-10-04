"""Opt-in PostgreSQL acceptance for the B021 equipment authority boundary.

The fixture is intentionally environment-gated.  The B021 acceptance runner
supplies a disposable PostgreSQL DSN through the known-good container-network
topology; ordinary unit runs remain SQLite-only and never connect to a shared
database.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
import threading
from urllib.parse import urlsplit

import pytest

import app as app_module
from db import PostgresConnectionWrapper


def _pg_url() -> str:
    url = os.environ.get("B021_RPG_POSTGRES_URL")
    if not url or os.environ.get("B021_RPG_POSTGRES_DISPOSABLE") != "1":
        pytest.skip("requires explicitly marked disposable B021 PostgreSQL")
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if "b021" not in database and "test" not in database:
        pytest.skip("refusing PostgreSQL URL without a test/b021 database")
    return url


def _connect(url: str) -> PostgresConnectionWrapper:
    import psycopg2
    from psycopg2.extras import DictCursor

    raw = psycopg2.connect(url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


def _reset_schema(conn: PostgresConnectionWrapper) -> None:
    conn.execute("DROP TABLE IF EXISTS player_inventory CASCADE")
    conn.execute("DROP TABLE IF EXISTS player_skills CASCADE")
    conn.execute(
        """CREATE TABLE player_inventory(
               id SERIAL PRIMARY KEY,
               user_id INTEGER NOT NULL,
               equip_id TEXT NOT NULL,
               equipped INTEGER NOT NULL DEFAULT 0,
               obtained_at TEXT,
               source TEXT,
               rarity TEXT
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
    from migrations.equipment_canonical_slot_v1 import upgrade
    upgrade(conn)
    conn.commit()


@pytest.fixture(scope="module")
def pg_database():
    url = _pg_url()
    conn = _connect(url)
    try:
        _reset_schema(conn)
        yield url
    finally:
        conn.rollback()
        conn.execute("DROP TABLE IF EXISTS player_inventory CASCADE")
        conn.execute("DROP TABLE IF EXISTS player_skills CASCADE")
        conn.commit()
        conn.close()


def _seed_inventory(url: str) -> None:
    conn = _connect(url)
    try:
        conn.execute("TRUNCATE player_inventory RESTART IDENTITY")
        conn.execute(
            "INSERT INTO player_inventory(user_id,equip_id,equipped,obtained_at,source,canonical_slot) "
            "VALUES(?,?,?,?,?,?)",
            (7, "wooden_sword", 1, "2026-08-22", "b021-test", "weapon"),
        )
        conn.execute(
            "INSERT INTO player_inventory(user_id,equip_id,equipped,obtained_at,source) "
            "VALUES(?,?,?,?,?)",
            (7, "iron_sword", 0, "2026-08-22", "b021-test"),
        )
        conn.commit()
    finally:
        conn.close()


def _authed_client(user_id: int = 7):
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client


def test_postgres_equipment_stats_are_server_defined_and_inventory_only_is_ignored(
    pg_database, monkeypatch
):
    url = pg_database
    _seed_inventory(url)
    monkeypatch.setattr(app_module, "get_db", lambda: _connect(url))

    conn = _connect(url)
    try:
        conn.execute(
            "INSERT INTO player_inventory(user_id,equip_id,equipped,obtained_at,source,canonical_slot) "
            "VALUES(?,?,?,?,?,?)",
            (7, "dragon_eye", 1, "2026-08-22", "b021-test", "accessory"),
        )
        conn.execute(
            "INSERT INTO player_inventory(user_id,equip_id,equipped,obtained_at,source) "
            "VALUES(?,?,?,?,?)",
            (7, "go_stone_black", 0, "2026-08-22", "b021-test"),
        )
        conn.commit()
        stats = app_module._get_authoritative_combat_stats(conn, 7, "dragon")
    finally:
        conn.close()

    assert stats["attack_bonus"] == pytest.approx(0.05)
    assert stats["crit_multiplier"] == pytest.approx(3.0)
    assert stats["counter_negated"] is False

    monkeypatch.delenv("EQUIPMENT_CANONICAL_LOADOUT_ENABLED", raising=False)
    for action, inv_id in (("equip", 2), ("unequip", 1)):
        disabled = _authed_client().post("/api/player/inventory/equip", json={"inv_id": inv_id, "action": action})
        assert disabled.status_code == 409
        assert disabled.get_json()["error"] == "LOADOUT_DISABLED"
    conn = _connect(url)
    try:
        assert [r["equipped"] for r in conn.execute("SELECT equipped FROM player_inventory ORDER BY id").fetchall()] == [1,0,1,0]
    finally:
        conn.close()
    monkeypatch.setenv("EQUIPMENT_CANONICAL_LOADOUT_ENABLED", "1")

    response = _authed_client().post(
        "/api/player/inventory/equip",
        json={"inv_id": 2, "action": "equip", "effects": {"dmg_bonus": 999}},
    )
    assert response.status_code == 200
    conn = _connect(url)
    try:
        row = conn.execute(
            "SELECT equipped FROM player_inventory WHERE id=?", (2,)
        ).fetchone()
    finally:
        conn.close()
    # A client-supplied effect payload is ignored.
    assert row["equipped"] == 1
    conn = _connect(url)
    try:
        actual = app_module._get_authoritative_combat_stats(conn, 7, "dragon")
        assert actual["attack_bonus"] == pytest.approx(app_module._EQUIP_MAP["iron_sword"]["effects"]["dmg_bonus"])
        assert actual["crit_multiplier"] == pytest.approx(3.0)
    finally:
        conn.close()

    trophy_response = _authed_client().post(
        "/api/player/inventory/equip", json={"inv_id": 4, "action": "equip"}
    )
    assert trophy_response.status_code == 400


def test_postgres_competing_weapon_equip_requests_leave_one_authoritative_slot(
    pg_database, monkeypatch
):
    url = pg_database
    _seed_inventory(url)
    monkeypatch.setattr(app_module, "get_db", lambda: _connect(url))
    monkeypatch.setitem(app_module.app.config, "TESTING", True)
    monkeypatch.delenv("EQUIPMENT_CANONICAL_LOADOUT_ENABLED", raising=False)
    for inv_id in (1, 2):
        disabled = _authed_client().post("/api/player/inventory/equip", json={"inv_id": inv_id, "action": "equip"})
        assert disabled.status_code == 409
    conn = _connect(url)
    try:
        assert [r["equipped"] for r in conn.execute("SELECT equipped FROM player_inventory ORDER BY id").fetchall()] == [1,0]
    finally:
        conn.close()
    monkeypatch.setenv("EQUIPMENT_CANONICAL_LOADOUT_ENABLED", "1")
    barrier = threading.Barrier(2)

    def equip(inv_id):
        barrier.wait(timeout=10)
        return _authed_client().post(
            "/api/player/inventory/equip",
            json={"inv_id": inv_id, "action": "equip"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(equip, (1, 2)))

    assert [response.status_code for response in responses] == [200, 200]
    conn = _connect(url)
    try:
        rows = conn.execute(
            "SELECT equip_id,equipped FROM player_inventory "
            "WHERE user_id=? AND equip_id IN (?,?) ORDER BY id",
            (7, "wooden_sword", "iron_sword"),
        ).fetchall()
    finally:
        conn.close()

    assert sum(int(row["equipped"]) for row in rows) == 1
    assert {row["equip_id"] for row in rows} == {"wooden_sword", "iron_sword"}
    conn = _connect(url)
    try:
        assert conn.execute("SELECT COUNT(*) AS n FROM player_inventory WHERE user_id=? AND canonical_slot='weapon' AND equipped=1", (7,)).fetchone()["n"] == 1
    finally:
        conn.close()
