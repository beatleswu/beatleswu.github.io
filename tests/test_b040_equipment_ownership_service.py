"""Focused tests for the B040 route-independent ownership writer."""

from __future__ import annotations

import inspect
from pathlib import Path
import sqlite3
from typing import Any

import pytest

import equipment_loadout_service as loadout
import equipment_ownership_service as ownership
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_b033


TEST_EQUIPMENT_DEFS = (
    {"id": "wooden_sword", "slot": "weapon"},
    {"id": "iron_sword", "slot": "weapon"},
    {"id": "cloth_robe", "slot": "armor"},
    {"id": "lucky_stone", "slot": "accessory"},
    {"id": "xp_amulet", "slot": "accessory"},
    {"id": "go_stone_black", "slot": "accessory"},
)


def _new_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE player_inventory (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER NOT NULL,
             equip_id TEXT NOT NULL,
             equipped INTEGER NOT NULL DEFAULT 0,
             obtained_at TEXT NOT NULL,
             source TEXT NOT NULL DEFAULT 'test'
        )"""
    )
    return conn


def _apply_b033(conn: sqlite3.Connection) -> None:
    upgrade_b033(conn, equipment_defs=TEST_EQUIPMENT_DEFS)
    conn.commit()


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {str(row[1]) for row in conn.execute("PRAGMA table_info(player_inventory)")}


class TransactionSpy:
    def __init__(self, raw: sqlite3.Connection):
        self._conn = raw
        self.commit_count = 0
        self.rollback_count = 0

    def execute(self, sql: str, parameters: Any = ()):
        return self._conn.execute(sql, parameters)

    def commit(self) -> None:
        self.commit_count += 1
        self._conn.commit()

    def rollback(self) -> None:
        self.rollback_count += 1
        self._conn.rollback()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


@pytest.mark.parametrize(
    ("equip_id", "slot"),
    (
        ("iron_sword", "weapon"),
        ("cloth_robe", "armor"),
        ("lucky_stone", "accessory"),
    ),
)
def test_pre_b033_functional_grants_preserve_legacy_schema(equip_id: str, slot: str):
    conn = _new_connection()
    try:
        result = ownership.grant_equipment_ownership(
            conn, 1, equip_id, "drop", equipment_defs=TEST_EQUIPMENT_DEFS
        )
        assert result.row_id == 1
        assert result.canonical_slot == slot
        assert result.equipped is False
        assert "canonical_slot" not in _columns(conn)
        row = conn.execute(
            "SELECT user_id, equip_id, equipped, obtained_at, source "
            "FROM player_inventory WHERE id=1"
        ).fetchone()
        assert row[0:3] == (1, equip_id, 0)
        assert row[3]
        assert row[4] == "drop"
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("equip_id", "slot"),
    (
        ("iron_sword", "weapon"),
        ("cloth_robe", "armor"),
        ("lucky_stone", "accessory"),
    ),
)
def test_post_b033_functional_grants_persist_server_slot(equip_id: str, slot: str):
    conn = _new_connection()
    try:
        _apply_b033(conn)
        result = ownership.grant_equipment_ownership(
            conn, 1, equip_id, "drop", equipment_defs=TEST_EQUIPMENT_DEFS
        )
        assert result.canonical_slot == slot
        row = conn.execute(
            "SELECT equip_id, equipped, canonical_slot, source "
            "FROM player_inventory WHERE id=?",
            (result.row_id,),
        ).fetchone()
        assert tuple(row) == (equip_id, 0, slot, "drop")
    finally:
        conn.close()


@pytest.mark.parametrize("equip_id", ("xp_amulet", "go_stone_black"))
def test_locked_items_remain_slotless_unequipped_ownership(equip_id: str):
    conn = _new_connection()
    try:
        _apply_b033(conn)
        result = ownership.grant_equipment_ownership(
            conn, 1, equip_id, "admin", equipment_defs=TEST_EQUIPMENT_DEFS
        )
        assert result.canonical_slot is None
        assert result.equipped is False
        row = conn.execute(
            "SELECT equipped, canonical_slot, source FROM player_inventory WHERE id=?",
            (result.row_id,),
        ).fetchone()
        assert tuple(row) == (0, None, "admin")
    finally:
        conn.close()


def test_unknown_equipment_fails_closed_without_insert():
    conn = _new_connection()
    try:
        with pytest.raises(ownership.EquipmentOwnershipError) as error:
            ownership.grant_equipment_ownership(
                conn, 1, "missing_item", "drop", equipment_defs=TEST_EQUIPMENT_DEFS
            )
        assert error.value.code == "UNKNOWN_EQUIPMENT"
        assert conn.execute("SELECT COUNT(*) FROM player_inventory").fetchone()[0] == 0
    finally:
        conn.close()


def test_invalid_server_slot_fails_closed():
    conn = _new_connection()
    try:
        invalid_defs = ({"id": "ring_of_unknown_slot", "slot": "ring"},)
        with pytest.raises(ownership.EquipmentOwnershipError) as error:
            ownership.grant_equipment_ownership(
                conn,
                1,
                "ring_of_unknown_slot",
                "drop",
                equipment_defs=invalid_defs,
            )
        assert error.value.code == "EQUIPMENT_DEFINITION_INVALID"
        assert conn.execute("SELECT COUNT(*) FROM player_inventory").fetchone()[0] == 0
    finally:
        conn.close()


def test_client_cannot_author_canonical_slot():
    signature = inspect.signature(ownership.grant_equipment_ownership)
    assert "canonical_slot" not in signature.parameters
    conn = _new_connection()
    try:
        with pytest.raises(TypeError):
            ownership.grant_equipment_ownership(
                conn,
                1,
                "iron_sword",
                "drop",
                canonical_slot="armor",
                equipment_defs=TEST_EQUIPMENT_DEFS,
            )
        assert conn.execute("SELECT COUNT(*) FROM player_inventory").fetchone()[0] == 0
    finally:
        conn.close()


def test_invalid_source_is_rejected_as_non_server_provenance():
    conn = _new_connection()
    try:
        with pytest.raises(ownership.EquipmentOwnershipError) as error:
            ownership.grant_equipment_ownership(
                conn,
                1,
                "iron_sword",
                "client_drop",
                equipment_defs=TEST_EQUIPMENT_DEFS,
            )
        assert error.value.code == "INVALID_OWNERSHIP_SOURCE"
    finally:
        conn.close()


def test_exact_inserted_row_id_and_duplicate_semantics_are_preserved():
    conn = _new_connection()
    try:
        first = ownership.grant_equipment_ownership(
            conn, 1, "iron_sword", "drop", equipment_defs=TEST_EQUIPMENT_DEFS
        )
        second = ownership.grant_equipment_ownership(
            conn, 1, "iron_sword", "drop", equipment_defs=TEST_EQUIPMENT_DEFS
        )
        assert first.row_id == 1
        assert second.row_id == 2
        assert first.as_dict()["row_id"] == first.row_id
        assert conn.execute(
            "SELECT COUNT(*) FROM player_inventory WHERE equip_id='iron_sword'"
        ).fetchone()[0] == 2
    finally:
        conn.close()


def test_service_never_commits_or_rolls_back():
    raw = _new_connection()
    conn = TransactionSpy(raw)
    try:
        result = ownership.grant_equipment_ownership(
            conn, 1, "iron_sword", "admin", equipment_defs=TEST_EQUIPMENT_DEFS
        )
        assert result.row_id == 1
        assert conn.commit_count == 0
        assert conn.rollback_count == 0
    finally:
        raw.close()


def test_caller_rollback_removes_ownership(tmp_path: Path):
    db_path = tmp_path / "b040_caller_rollback.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE player_inventory (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER NOT NULL,
             equip_id TEXT NOT NULL,
             equipped INTEGER NOT NULL DEFAULT 0,
             obtained_at TEXT NOT NULL,
             source TEXT NOT NULL DEFAULT 'test'
        )"""
    )
    result = ownership.grant_equipment_ownership(
        conn, 1, "iron_sword", "drop", equipment_defs=TEST_EQUIPMENT_DEFS
    )
    assert result.row_id == 1
    assert conn.execute("SELECT COUNT(*) FROM player_inventory").fetchone()[0] == 1
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM player_inventory").fetchone()[0] == 0
    conn.close()


@pytest.mark.parametrize(
    ("equip_id", "slot"),
    (
        ("iron_sword", "weapon"),
        ("cloth_robe", "armor"),
        ("lucky_stone", "accessory"),
    ),
)
def test_b040_grant_to_b034_equip_passes(equip_id: str, slot: str):
    conn = _new_connection()
    try:
        _apply_b033(conn)
        grant = ownership.grant_equipment_ownership(
            conn, 1, equip_id, "drop", equipment_defs=TEST_EQUIPMENT_DEFS
        )
        result = loadout.equip_owned_item(
            conn, 1, equip_id, equipment_defs=TEST_EQUIPMENT_DEFS
        )
        assert grant.canonical_slot == slot
        assert result["changed"] is True
        assert conn.execute(
            "SELECT equipped, canonical_slot FROM player_inventory WHERE id=?",
            (grant.row_id,),
        ).fetchone()[0:2] == (1, slot)
    finally:
        conn.close()


def test_partial_b033_schema_fails_closed_before_insert():
    conn = _new_connection()
    try:
        conn.execute("ALTER TABLE player_inventory ADD COLUMN canonical_slot TEXT")
        with pytest.raises(ownership.EquipmentOwnershipError) as error:
            ownership.grant_equipment_ownership(
                conn, 1, "iron_sword", "drop", equipment_defs=TEST_EQUIPMENT_DEFS
            )
        assert error.value.code == "B033_MALFORMED_SCHEMA"
        assert error.value.details["schema_state"] == ownership.B033_MALFORMED_SCHEMA
        assert conn.execute("SELECT COUNT(*) FROM player_inventory").fetchone()[0] == 0
    finally:
        conn.close()


def test_current_monster_and_admin_source_semantics_map_without_drift():
    conn = _new_connection()
    try:
        _apply_b033(conn)
        drop = ownership.grant_equipment_ownership(
            conn, 1, "iron_sword", "drop", equipment_defs=TEST_EQUIPMENT_DEFS
        )
        admin = ownership.grant_equipment_ownership(
            conn, 1, "cloth_robe", "admin", equipment_defs=TEST_EQUIPMENT_DEFS
        )
        rows = conn.execute(
            "SELECT equip_id, equipped, canonical_slot, source, obtained_at "
            "FROM player_inventory ORDER BY id"
        ).fetchall()
        assert drop.source == "drop"
        assert admin.source == "admin"
        assert [(row[0], row[1], row[2], row[3]) for row in rows] == [
            ("iron_sword", 0, "weapon", "drop"),
            ("cloth_robe", 0, "armor", "admin"),
        ]
        assert all(row[4] for row in rows)
    finally:
        conn.close()


def test_server_slot_projection_matches_c026_meaning():
    conn = _new_connection()
    try:
        _apply_b033(conn)
        result = ownership.grant_equipment_ownership(
            conn, 1, "lucky_stone", "drop", equipment_defs=TEST_EQUIPMENT_DEFS
        )
        assert result.canonical_slot == "accessory"
        assert conn.execute(
            "SELECT canonical_slot FROM player_inventory WHERE id=?",
            (result.row_id,),
        ).fetchone()[0] == result.canonical_slot
    finally:
        conn.close()
