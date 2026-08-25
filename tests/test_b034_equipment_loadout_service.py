"""Focused tests for the route-independent B034 Equipment command core."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from threading import Barrier
from urllib.parse import urlsplit

import pytest

import equipment_loadout_service as loadout
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_b033


TEST_EQUIPMENT_DEFS = (
    {"id": "wooden_sword", "slot": "weapon"},
    {"id": "iron_sword", "slot": "weapon"},
    {"id": "cloth_robe", "slot": "armor"},
    {"id": "leather_armor", "slot": "armor"},
    {"id": "lucky_stone", "slot": "accessory"},
    {"id": "xp_amulet", "slot": "accessory"},
    {"id": "go_stone_black", "slot": "accessory"},
)


def _new_sqlite_connection(path: str | Path = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE player_inventory (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER NOT NULL,
             equip_id TEXT NOT NULL,
             equipped INTEGER NOT NULL DEFAULT 0,
             obtained_at TEXT,
             source TEXT NOT NULL DEFAULT 'test'
        )"""
    )
    return conn


def _insert(
    conn: sqlite3.Connection,
    user_id: int,
    equip_id: str,
    equipped: int = 0,
    canonical_slot: str | None = None,
) -> int:
    columns = ["user_id", "equip_id", "equipped"]
    values = [user_id, equip_id, equipped]
    if "canonical_slot" in {
        str(row[1]) for row in conn.execute("PRAGMA table_info(player_inventory)")
    }:
        columns.append("canonical_slot")
        values.append(canonical_slot)
    cursor = conn.execute(
        f"INSERT INTO player_inventory({','.join(columns)}) "
        f"VALUES({','.join('?' for _ in values)})",
        values,
    )
    return int(cursor.lastrowid)


def _apply_b033(conn: sqlite3.Connection) -> None:
    upgrade_b033(conn, equipment_defs=TEST_EQUIPMENT_DEFS)
    conn.commit()


def _equipped_by_id(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        str(row["equip_id"]): int(row["equipped"])
        for row in conn.execute(
            "SELECT equip_id, equipped FROM player_inventory ORDER BY id"
        ).fetchall()
    }


def test_owned_weapon_equips_with_server_derived_slot():
    conn = _new_sqlite_connection()
    try:
        _apply_b033(conn)
        _insert(conn, 1, "iron_sword")

        result = loadout.equip_owned_item(
            conn, 1, "iron_sword", equipment_defs=TEST_EQUIPMENT_DEFS
        )

        assert result == {
            "user_id": 1,
            "target_equip_id": "iron_sword",
            "canonical_slot": "weapon",
            "changed": True,
            "previous_equipped_item_id": None,
            "equipped_item_id": "iron_sword",
        }
        assert _equipped_by_id(conn)["iron_sword"] == 1
        assert conn.execute(
            "SELECT canonical_slot FROM player_inventory WHERE equip_id='iron_sword'"
        ).fetchone()[0] == "weapon"
    finally:
        conn.close()


def test_same_target_replay_is_desired_state_idempotent():
    conn = _new_sqlite_connection()
    try:
        _apply_b033(conn)
        row_id = _insert(conn, 1, "iron_sword")
        first = loadout.equip_owned_item(
            conn, 1, "iron_sword", equipment_defs=TEST_EQUIPMENT_DEFS
        )
        conn.commit()
        second = loadout.equip_owned_item(
            conn, 1, "iron_sword", equipment_defs=TEST_EQUIPMENT_DEFS
        )

        assert first["changed"] is True
        assert second["changed"] is False
        assert second["previous_equipped_item_id"] == "iron_sword"
        assert conn.execute(
            "SELECT COUNT(*) FROM player_inventory WHERE id=? AND equipped=1", (row_id,)
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_second_weapon_replaces_first_atomically_with_one_effective_slot():
    conn = _new_sqlite_connection()
    try:
        _apply_b033(conn)
        _insert(conn, 1, "iron_sword")
        _insert(conn, 1, "wooden_sword")
        loadout.equip_owned_item(
            conn, 1, "iron_sword", equipment_defs=TEST_EQUIPMENT_DEFS
        )
        replacement = loadout.equip_owned_item(
            conn, 1, "wooden_sword", equipment_defs=TEST_EQUIPMENT_DEFS
        )

        assert replacement["changed"] is True
        assert replacement["previous_equipped_item_id"] == "iron_sword"
        assert _equipped_by_id(conn) == {"iron_sword": 0, "wooden_sword": 1}
        assert conn.execute(
            "SELECT COUNT(*) FROM player_inventory "
            "WHERE user_id=1 AND equipped=1 AND canonical_slot='weapon'"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_cross_slot_equipment_is_preserved():
    conn = _new_sqlite_connection()
    try:
        _apply_b033(conn)
        for equip_id in ("iron_sword", "cloth_robe", "lucky_stone"):
            _insert(conn, 1, equip_id)
        for equip_id in ("iron_sword", "cloth_robe", "lucky_stone"):
            loadout.equip_owned_item(
                conn, 1, equip_id, equipment_defs=TEST_EQUIPMENT_DEFS
            )

        rows = conn.execute(
            "SELECT canonical_slot, equip_id FROM player_inventory "
            "WHERE user_id=1 AND equipped=1 ORDER BY canonical_slot"
        ).fetchall()
        assert [(row[0], row[1]) for row in rows] == [
            ("accessory", "lucky_stone"),
            ("armor", "cloth_robe"),
            ("weapon", "iron_sword"),
        ]
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("equip_id", "error_code"),
    (
        ("missing_sword", "UNKNOWN_EQUIPMENT"),
        ("go_stone_black", "GO_STONE_BLACK_NOT_EQUIPPABLE"),
        ("xp_amulet", "XP_AMULET_HOLD_FOR_AUTHORITY"),
    ),
)
def test_unknown_and_locked_targets_fail_before_mutation(equip_id, error_code):
    conn = _new_sqlite_connection()
    try:
        _apply_b033(conn)
        _insert(conn, 1, "iron_sword")
        with pytest.raises(loadout.EquipmentLoadoutError) as error:
            loadout.equip_owned_item(
                conn, 1, equip_id, equipment_defs=TEST_EQUIPMENT_DEFS
            )
        assert error.value.code == error_code
        assert _equipped_by_id(conn)["iron_sword"] == 0
    finally:
        conn.close()


def test_unowned_target_fails_closed():
    conn = _new_sqlite_connection()
    try:
        _apply_b033(conn)
        with pytest.raises(loadout.EquipmentLoadoutError) as error:
            loadout.equip_owned_item(
                conn, 1, "iron_sword", equipment_defs=TEST_EQUIPMENT_DEFS
            )
        assert error.value.code == "EQUIPMENT_NOT_OWNED"
    finally:
        conn.close()


def _raw_canonical_connection() -> sqlite3.Connection:
    conn = _new_sqlite_connection()
    conn.execute("ALTER TABLE player_inventory ADD COLUMN canonical_slot TEXT")
    return conn


def _pretend_b033_schema(monkeypatch):
    monkeypatch.setattr(
        loadout,
        "validate_schema",
        lambda _conn: {"valid": True, "missing": []},
    )


@pytest.mark.parametrize(
    "rows,category",
    (
        (
            ((1, "iron_sword", 1, "weapon"), (1, "wooden_sword", 1, "weapon")),
            "DUPLICATE_EQUIPPED_WEAPON",
        ),
        (((1, "iron_sword", 1, None),), "EQUIPPED_WITH_NULL_CANONICAL_SLOT"),
        (((1, "iron_sword", 0, "armor"),), "CANONICAL_SLOT_PROJECTION_DISAGREEMENT"),
    ),
)
def test_malformed_pre_state_fails_closed_without_auto_repair(monkeypatch, rows, category):
    conn = _raw_canonical_connection()
    try:
        _pretend_b033_schema(monkeypatch)
        for user_id, equip_id, equipped, slot in rows:
            _insert(conn, user_id, equip_id, equipped, slot)
        before = [tuple(row) for row in conn.execute(
            "SELECT equip_id, equipped, canonical_slot FROM player_inventory"
        ).fetchall()]
        with pytest.raises(loadout.EquipmentLoadoutError) as error:
            loadout.equip_owned_item(
                conn, 1, "iron_sword", equipment_defs=TEST_EQUIPMENT_DEFS
            )
        assert error.value.code == "MALFORMED_EQUIPPED_STATE"
        assert category in error.value.details["report"]["blocking_categories"]
        after = [tuple(row) for row in conn.execute(
            "SELECT equip_id, equipped, canonical_slot FROM player_inventory"
        ).fetchall()]
        assert after == before
    finally:
        conn.close()


def test_service_does_not_commit_and_caller_rollback_restores_state(tmp_path):
    db_path = tmp_path / "b034_no_service_commit.sqlite"
    setup = _new_sqlite_connection(db_path)
    _insert(setup, 1, "iron_sword")
    _insert(setup, 1, "wooden_sword")
    upgrade_b033(setup, equipment_defs=TEST_EQUIPMENT_DEFS)
    setup.commit()
    setup.close()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    result = loadout.equip_owned_item(
        conn, 1, "iron_sword", equipment_defs=TEST_EQUIPMENT_DEFS
    )
    assert result["changed"] is True

    reader = sqlite3.connect(db_path)
    try:
        assert reader.execute(
            "SELECT equipped FROM player_inventory "
            "WHERE user_id=1 AND equip_id='iron_sword'"
        ).fetchone()[0] == 0
        conn.rollback()
        assert reader.execute(
            "SELECT equipped FROM player_inventory "
            "WHERE user_id=1 AND equip_id='iron_sword'"
        ).fetchone()[0] == 0
    finally:
        reader.close()
        conn.close()


def test_rollback_restores_previous_equipment_state():
    conn = _new_sqlite_connection()
    try:
        _apply_b033(conn)
        _insert(conn, 1, "iron_sword")
        _insert(conn, 1, "wooden_sword")
        loadout.equip_owned_item(
            conn, 1, "iron_sword", equipment_defs=TEST_EQUIPMENT_DEFS
        )
        conn.commit()
        loadout.equip_owned_item(
            conn, 1, "wooden_sword", equipment_defs=TEST_EQUIPMENT_DEFS
        )
        conn.rollback()
        assert _equipped_by_id(conn) == {"iron_sword": 1, "wooden_sword": 0}
    finally:
        conn.close()


def test_unequip_is_route_independent_and_does_not_consume_ownership():
    conn = _new_sqlite_connection()
    try:
        _apply_b033(conn)
        row_id = _insert(conn, 1, "iron_sword")
        loadout.equip_owned_item(
            conn, 1, "iron_sword", equipment_defs=TEST_EQUIPMENT_DEFS
        )
        result = loadout.unequip_owned_item(
            conn, 1, "iron_sword", equipment_defs=TEST_EQUIPMENT_DEFS
        )
        assert result["changed"] is True
        assert result["equipped_item_id"] is None
        row = conn.execute(
            "SELECT equip_id, equipped, canonical_slot FROM player_inventory WHERE id=?",
            (row_id,),
        ).fetchone()
        assert tuple(row) == ("iron_sword", 0, "weapon")
    finally:
        conn.close()


def test_client_cannot_author_slot_or_combat_fields():
    conn = _new_sqlite_connection()
    try:
        _apply_b033(conn)
        _insert(conn, 1, "iron_sword")
        with pytest.raises(TypeError):
            loadout.equip_owned_item(
                conn,
                1,
                "iron_sword",
                canonical_slot="armor",
                attack_bonus=999,
            )
    finally:
        conn.close()


def test_schema_precondition_fails_closed_without_b033():
    conn = _new_sqlite_connection()
    try:
        _insert(conn, 1, "iron_sword")
        with pytest.raises(loadout.EquipmentLoadoutError) as error:
            loadout.equip_owned_item(
                conn, 1, "iron_sword", equipment_defs=TEST_EQUIPMENT_DEFS
            )
        assert error.value.code == "SCHEMA_INVARIANT_UNAVAILABLE"
        assert _equipped_by_id(conn)["iron_sword"] == 0
    finally:
        conn.close()


def _postgres_url() -> str:
    url = os.environ.get("B034_EQUIPMENT_POSTGRES_URL")
    if not url or os.environ.get("B034_EQUIPMENT_POSTGRES_DISPOSABLE") != "1":
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if not database or not any(token in database for token in ("b034", "test", "equipment")):
        pytest.skip("refusing PostgreSQL URL without an explicitly disposable database name")
    return url


def _postgres_connection(url: str):
    try:
        import psycopg2
        from psycopg2.extras import DictCursor
        from db import PostgresConnectionWrapper
    except ImportError as error:  # pragma: no cover - environment-dependent
        pytest.skip(f"psycopg2 unavailable: {error}")
    raw = psycopg2.connect(url, connect_timeout=5)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


@pytest.fixture
def postgres_conn():
    conn = _postgres_connection(_postgres_url())
    try:
        conn.execute("DROP TABLE IF EXISTS public.player_inventory CASCADE")
        conn.execute(
            """CREATE TABLE public.player_inventory (
                 id SERIAL PRIMARY KEY,
                 user_id INTEGER NOT NULL,
                 equip_id TEXT NOT NULL,
                 equipped INTEGER NOT NULL DEFAULT 0,
                 obtained_at TEXT,
                 source TEXT NOT NULL DEFAULT 'test'
            )"""
        )
        upgrade_b033(conn, equipment_defs=TEST_EQUIPMENT_DEFS)
        conn.commit()
        yield conn
    finally:
        try:
            conn.rollback()
            conn.execute("DROP TABLE IF EXISTS public.player_inventory CASCADE")
            conn.commit()
        finally:
            conn.close()


def _insert_pg(conn, user_id, equip_id, equipped=0, canonical_slot=None):
    conn.execute(
        "INSERT INTO public.player_inventory(user_id,equip_id,equipped,canonical_slot) "
        "VALUES(?,?,?,?)",
        (user_id, equip_id, equipped, canonical_slot),
    )


def test_postgres_equip_replay_replacement_and_b033_invariant(postgres_conn):
    conn = postgres_conn
    _insert_pg(conn, 1, "iron_sword")
    _insert_pg(conn, 1, "wooden_sword")
    first = loadout.equip_owned_item(
        conn, 1, "iron_sword", equipment_defs=TEST_EQUIPMENT_DEFS
    )
    replay = loadout.equip_owned_item(
        conn, 1, "iron_sword", equipment_defs=TEST_EQUIPMENT_DEFS
    )
    replacement = loadout.equip_owned_item(
        conn, 1, "wooden_sword", equipment_defs=TEST_EQUIPMENT_DEFS
    )
    conn.commit()
    assert first["changed"] is True
    assert replay["changed"] is False
    assert replacement["previous_equipped_item_id"] == "iron_sword"
    assert conn.execute(
        "SELECT COUNT(*) FROM public.player_inventory "
        "WHERE user_id=1 AND equipped=1 AND canonical_slot='weapon'"
    ).fetchone()[0] == 1


def test_postgres_service_does_not_commit_until_caller_commits(postgres_conn):
    conn = postgres_conn
    _insert_pg(conn, 1, "iron_sword")
    conn.commit()
    result = loadout.equip_owned_item(
        conn, 1, "iron_sword", equipment_defs=TEST_EQUIPMENT_DEFS
    )
    assert result["changed"] is True
    reader = _postgres_connection(_postgres_url())
    try:
        assert reader.execute(
            "SELECT equipped FROM public.player_inventory "
            "WHERE user_id=1 AND equip_id='iron_sword'"
        ).fetchone()[0] == 0
        conn.rollback()
    finally:
        reader.close()


def test_postgres_concurrent_competing_changes_leave_one_effective_slot(postgres_conn):
    conn = postgres_conn
    _insert_pg(conn, 1, "iron_sword")
    _insert_pg(conn, 1, "wooden_sword")
    conn.commit()
    url = _postgres_url()
    barrier = Barrier(2)

    def submit(equip_id):
        worker = _postgres_connection(url)
        try:
            barrier.wait(timeout=10)
            result = loadout.equip_owned_item(
                worker, 1, equip_id, equipment_defs=TEST_EQUIPMENT_DEFS
            )
            worker.commit()
            return result
        finally:
            worker.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(submit, ("iron_sword", "wooden_sword"))
        )
    assert all(result["changed"] is True for result in results)
    assert conn.execute(
        "SELECT COUNT(*) FROM public.player_inventory "
        "WHERE user_id=1 AND equipped=1 AND canonical_slot='weapon'"
    ).fetchone()[0] == 1


def test_postgres_malformed_state_fails_before_mutation(postgres_conn):
    conn = postgres_conn
    _insert_pg(conn, 1, "iron_sword")
    conn.commit()
    conn.execute(
        "ALTER TABLE public.player_inventory DROP CONSTRAINT "
        "ck_player_inventory_equipped_requires_slot"
    )
    conn.execute(
        "DROP INDEX public.uq_player_inventory_user_equipped_slot"
    )
    conn.execute(
        "DROP TRIGGER IF EXISTS trg_player_inventory_equipped_requires_slot_insert "
        "ON public.player_inventory"
    )
    conn.execute(
        "DROP TRIGGER IF EXISTS trg_player_inventory_equipped_requires_slot_update "
        "ON public.player_inventory"
    )
    _insert_pg(conn, 1, "wooden_sword", 1, "weapon")
    conn.commit()
    with pytest.raises(loadout.EquipmentLoadoutError) as error:
        loadout.equip_owned_item(
            conn, 1, "iron_sword", equipment_defs=TEST_EQUIPMENT_DEFS
        )
    assert error.value.code == "SCHEMA_INVARIANT_UNAVAILABLE"
