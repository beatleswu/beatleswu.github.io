"""Focused disposable tests for the B033 canonical-slot schema candidate."""

from __future__ import annotations

from contextlib import contextmanager
import os
import sqlite3
from urllib.parse import urlsplit

import pytest

from migrations.equipment_canonical_slot_v1 import (
    CANONICAL_SLOT_COLUMN,
    MalformedInventoryState,
    UNIQUE_INDEX_NAME,
    build_slot_projection,
    detect_malformed_rows,
    upgrade,
    validate_schema,
)


TEST_EQUIPMENT_DEFS = (
    {"id": "wooden_sword", "slot": "weapon"},
    {"id": "iron_sword", "slot": "weapon"},
    {"id": "cloth_robe", "slot": "armor"},
    {"id": "lucky_stone", "slot": "accessory"},
    {"id": "xp_amulet", "slot": "accessory"},
    {"id": "go_stone_black", "slot": "accessory"},
)


def _new_sqlite_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
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
    conn,
    user_id: int,
    equip_id: str,
    equipped: int = 0,
    canonical_slot: str | None = None,
) -> int:
    columns = ["user_id", "equip_id", "equipped"]
    values = [user_id, equip_id, equipped]
    if CANONICAL_SLOT_COLUMN in {
        str(row[1]) for row in conn.execute("PRAGMA table_info(player_inventory)")
    }:
        columns.append(CANONICAL_SLOT_COLUMN)
        values.append(canonical_slot)
    placeholders = ",".join("?" for _ in values)
    cursor = conn.execute(
        f"INSERT INTO player_inventory({','.join(columns)}) VALUES({placeholders})",
        values,
    )
    return int(cursor.lastrowid)


def _apply_clean_sqlite(conn: sqlite3.Connection):
    result = upgrade(conn, equipment_defs=TEST_EQUIPMENT_DEFS)
    conn.commit()
    return result


def _assert_blocked(conn, category: str):
    with pytest.raises(MalformedInventoryState) as error:
        upgrade(conn, equipment_defs=TEST_EQUIPMENT_DEFS)
    report = error.value.report
    assert category in report["blocking_categories"]
    assert report["clean"] is False
    assert validate_schema(conn)["partial_unique_index"] is False
    return report


def test_clean_backfill_creates_nullable_projection_and_final_gates():
    conn = _new_sqlite_connection()
    try:
        iron_id = _insert(conn, 1, "iron_sword", equipped=1)
        robe_id = _insert(conn, 1, "cloth_robe", equipped=0)
        _insert(conn, 2, "lucky_stone", equipped=1)
        _insert(conn, 3, "go_stone_black", equipped=0)
        _insert(conn, 4, "legacy_unknown", equipped=0)

        result = _apply_clean_sqlite(conn)

        assert result["valid"] is True
        assert result["malformed_preflight"]["clean"] is True
        assert validate_schema(conn)["canonical_slot_nullable"] is True
        assert conn.execute(
            "SELECT canonical_slot FROM player_inventory WHERE id=?", (iron_id,)
        ).fetchone()[0] == "weapon"
        assert conn.execute(
            "SELECT canonical_slot FROM player_inventory WHERE id=?", (robe_id,)
        ).fetchone()[0] == "armor"
    finally:
        conn.close()


def test_projection_uses_server_registry_and_excludes_locked_items():
    projection = build_slot_projection(TEST_EQUIPMENT_DEFS)
    assert projection == {
        "wooden_sword": "weapon",
        "iron_sword": "weapon",
        "cloth_robe": "armor",
        "lucky_stone": "accessory",
    }


def test_default_projection_reads_current_equipment_definitions():
    from app import EQUIPMENT_DEFS

    projection = build_slot_projection(EQUIPMENT_DEFS)
    assert projection["iron_sword"] == "weapon"
    assert projection["dragon_scale"] == "armor"
    assert projection["dragon_eye"] == "accessory"
    assert "go_stone_black" not in projection
    assert "xp_amulet" not in projection


def test_unknown_equipped_id_blocks_without_repair():
    conn = _new_sqlite_connection()
    try:
        row_id = _insert(conn, 1, "unknown_equipment", equipped=1)
        report = _assert_blocked(conn, "UNKNOWN_EQUIPPED_EQUIP_ID")
        assert "EQUIPPED_WITH_NULL_CANONICAL_SLOT" in report["blocking_categories"]
        row = conn.execute(
            "SELECT equip_id, equipped FROM player_inventory WHERE id=?", (row_id,)
        ).fetchone()
        assert tuple(row) == ("unknown_equipment", 1)
    finally:
        conn.close()


def test_duplicate_effective_weapon_blocks_before_unique_index_creation():
    conn = _new_sqlite_connection()
    try:
        _insert(conn, 1, "iron_sword", equipped=1)
        _insert(conn, 1, "wooden_sword", equipped=1)
        report = _assert_blocked(conn, "DUPLICATE_EQUIPPED_WEAPON")
        assert report["blockers"]["DUPLICATE_EQUIPPED_WEAPON"][0]["canonical_slot"] == "weapon"
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name=?",
            (UNIQUE_INDEX_NAME,),
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_equipped_null_slot_detector_is_explicit_and_read_only():
    conn = _new_sqlite_connection()
    try:
        conn.execute("ALTER TABLE player_inventory ADD COLUMN canonical_slot TEXT")
        row_id = _insert(conn, 1, "iron_sword", equipped=1, canonical_slot=None)
        report = detect_malformed_rows(conn, TEST_EQUIPMENT_DEFS)
        assert report["clean"] is False
        assert report["blocking_categories"] == ["EQUIPPED_WITH_NULL_CANONICAL_SLOT"]
        assert report["blockers"]["EQUIPPED_WITH_NULL_CANONICAL_SLOT"][0]["id"] == row_id
        assert conn.execute(
            "SELECT equipped, canonical_slot FROM player_inventory WHERE id=?", (row_id,)
        ).fetchone()[0:2] == (1, None)
    finally:
        conn.close()


def test_go_stone_black_equipped_is_rejected_as_malformed():
    conn = _new_sqlite_connection()
    try:
        _insert(conn, 1, "go_stone_black", equipped=1)
        report = _assert_blocked(conn, "GO_STONE_BLACK_EQUIPPED")
        assert "EQUIPPED_WITH_NULL_CANONICAL_SLOT" in report["blocking_categories"]
    finally:
        conn.close()


def test_xp_amulet_equipped_remains_hold_for_authority_and_is_rejected():
    conn = _new_sqlite_connection()
    try:
        _insert(conn, 1, "xp_amulet", equipped=1)
        report = _assert_blocked(conn, "XP_AMULET_EQUIPPED")
        assert "EQUIPPED_WITH_NULL_CANONICAL_SLOT" in report["blocking_categories"]
    finally:
        conn.close()


def test_validity_gate_rejects_equipped_null_and_allows_unequipped_null():
    conn = _new_sqlite_connection()
    try:
        _apply_clean_sqlite(conn)
        unequipped_id = _insert(conn, 2, "legacy_unknown", equipped=0)
        conn.commit()
        assert conn.execute(
            "SELECT canonical_slot FROM player_inventory WHERE id=?", (unequipped_id,)
        ).fetchone()[0] is None

        with pytest.raises(sqlite3.IntegrityError):
            _insert(conn, 3, "iron_sword", equipped=1, canonical_slot=None)
        conn.rollback()

        _insert(conn, 4, "iron_sword", equipped=0, canonical_slot=None)
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE player_inventory SET equipped=1 WHERE user_id=4"
            )
    finally:
        conn.close()


def test_partial_unique_gate_rejects_second_equipped_item_in_same_slot():
    conn = _new_sqlite_connection()
    try:
        _apply_clean_sqlite(conn)
        _insert(conn, 1, "iron_sword", equipped=1, canonical_slot="weapon")
        with pytest.raises(sqlite3.IntegrityError):
            _insert(conn, 1, "wooden_sword", equipped=1, canonical_slot="weapon")
        conn.rollback()

        _insert(conn, 2, "wooden_sword", equipped=1, canonical_slot="weapon")
        _insert(conn, 3, "legacy_unknown", equipped=0, canonical_slot=None)
        conn.commit()
    finally:
        conn.close()


def test_upgrade_is_idempotent_and_does_not_duplicate_objects():
    conn = _new_sqlite_connection()
    try:
        _insert(conn, 1, "iron_sword", equipped=1)
        first = _apply_clean_sqlite(conn)
        second = upgrade(conn, equipment_defs=TEST_EQUIPMENT_DEFS)
        conn.commit()

        assert first["valid"] is True
        assert second["valid"] is True
        assert second["created"] == []
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name=?",
            (UNIQUE_INDEX_NAME,),
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
            "AND name LIKE 'trg_player_inventory_equipped_requires_slot_%'"
        ).fetchone()[0] == 2
    finally:
        conn.close()


def test_dry_run_is_non_mutating_and_reports_planned_projection():
    conn = _new_sqlite_connection()
    try:
        result = upgrade(conn, equipment_defs=TEST_EQUIPMENT_DEFS, dry_run=True)
        assert result["dry_run"] is True
        assert result["planned"]["add_projection"] is True
        assert CANONICAL_SLOT_COLUMN not in {
            str(row[1]) for row in conn.execute("PRAGMA table_info(player_inventory)")
        }
    finally:
        conn.close()


def _postgres_url() -> str:
    url = os.environ.get("B033_EQUIPMENT_POSTGRES_URL")
    if not url or os.environ.get("B033_EQUIPMENT_POSTGRES_DISPOSABLE") != "1":
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if not database or not any(token in database for token in ("b033", "test", "equipment")):
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


@contextmanager
def _pg_savepoint(conn, name: str):
    conn.execute(f"SAVEPOINT {name}")
    try:
        yield
    finally:
        conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
        conn.execute(f"RELEASE SAVEPOINT {name}")


@pytest.fixture
def postgres_conn():
    url = _postgres_url()
    conn = _postgres_connection(url)
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
        conn.commit()
        yield conn
    finally:
        try:
            conn.rollback()
            conn.execute("DROP TABLE IF EXISTS public.player_inventory CASCADE")
            conn.commit()
        finally:
            conn.close()


def test_postgres_clean_backfill_validity_unique_and_idempotency(postgres_conn):
    conn = postgres_conn
    _insert_pg = lambda user_id, equip_id, equipped=0, slot=None: conn.execute(
        "INSERT INTO public.player_inventory(user_id,equip_id,equipped,canonical_slot) "
        "VALUES(?,?,?,?)",
        (user_id, equip_id, equipped, slot),
    )
    conn.execute(
        "INSERT INTO public.player_inventory(user_id,equip_id,equipped) VALUES(?,?,?)",
        (1, "iron_sword", 1),
    )
    result = upgrade(conn, equipment_defs=TEST_EQUIPMENT_DEFS)
    conn.commit()
    assert result["valid"] is True
    assert result["canonical_slot_nullable"] is True
    assert validate_schema(conn)["dialect"] == "postgresql"

    second = upgrade(conn, equipment_defs=TEST_EQUIPMENT_DEFS)
    conn.commit()
    assert second["valid"] is True
    assert second["created"] == []

    _insert_pg(2, "legacy_unknown", 0, None)
    conn.commit()
    with pytest.raises(Exception):
        with _pg_savepoint(conn, "b033_null_slot"):
            _insert_pg(3, "iron_sword", 1, None)
    with pytest.raises(Exception):
        with _pg_savepoint(conn, "b033_duplicate_slot"):
            _insert_pg(1, "wooden_sword", 1, "weapon")


def test_postgres_malformed_preflight_blocks_without_repair(postgres_conn):
    conn = postgres_conn
    conn.execute(
        "INSERT INTO public.player_inventory(user_id,equip_id,equipped) VALUES(?,?,?)",
        (1, "iron_sword", 1),
    )
    conn.execute(
        "INSERT INTO public.player_inventory(user_id,equip_id,equipped) VALUES(?,?,?)",
        (1, "wooden_sword", 1),
    )
    conn.execute(
        "INSERT INTO public.player_inventory(user_id,equip_id,equipped) VALUES(?,?,?)",
        (2, "unknown_equipment", 1),
    )
    with pytest.raises(MalformedInventoryState) as error:
        upgrade(conn, equipment_defs=TEST_EQUIPMENT_DEFS)
    report = error.value.report
    assert "DUPLICATE_EQUIPPED_WEAPON" in report["blocking_categories"]
    assert "UNKNOWN_EQUIPPED_EQUIP_ID" in report["blocking_categories"]
    assert "EQUIPPED_WITH_NULL_CANONICAL_SLOT" in report["blocking_categories"]
    conn.rollback()
    assert validate_schema(conn)["valid"] is False


def test_postgres_locked_items_are_preflight_blockers(postgres_conn):
    conn = postgres_conn
    conn.execute(
        "INSERT INTO public.player_inventory(user_id,equip_id,equipped) VALUES(?,?,?)",
        (1, "go_stone_black", 1),
    )
    conn.execute(
        "INSERT INTO public.player_inventory(user_id,equip_id,equipped) VALUES(?,?,?)",
        (2, "xp_amulet", 1),
    )
    with pytest.raises(MalformedInventoryState) as error:
        upgrade(conn, equipment_defs=TEST_EQUIPMENT_DEFS)
    categories = error.value.report["blocking_categories"]
    assert "GO_STONE_BLACK_EQUIPPED" in categories
    assert "XP_AMULET_EQUIPPED" in categories
    assert "EQUIPPED_WITH_NULL_CANONICAL_SLOT" in categories
    conn.rollback()


def test_postgres_unequipped_null_slot_is_allowed(postgres_conn):
    conn = postgres_conn
    result = upgrade(conn, equipment_defs=TEST_EQUIPMENT_DEFS)
    conn.commit()
    assert result["valid"] is True
    conn.execute(
        "INSERT INTO public.player_inventory(user_id,equip_id,equipped,canonical_slot) "
        "VALUES(?,?,?,?)",
        (1, "legacy_unknown", 0, None),
    )
    conn.commit()
    assert conn.execute(
        "SELECT COUNT(*) FROM public.player_inventory "
        "WHERE equip_id='legacy_unknown' AND equipped=0 AND canonical_slot IS NULL"
    ).fetchone()[0] == 1
