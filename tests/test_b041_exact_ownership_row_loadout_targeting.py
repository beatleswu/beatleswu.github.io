"""Focused tests for B041 exact player_inventory row targeting."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

import equipment_loadout_service as loadout
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
             obtained_at TEXT,
             source TEXT NOT NULL DEFAULT 'test'
        )"""
    )
    return conn


def _apply_b033(conn: sqlite3.Connection) -> None:
    upgrade_b033(conn, equipment_defs=TEST_EQUIPMENT_DEFS)
    conn.commit()


def _insert(
    conn: sqlite3.Connection,
    user_id: int,
    equip_id: str,
    *,
    row_id: int | None = None,
    equipped: int = 0,
    canonical_slot: str | None = None,
) -> int:
    if row_id is None:
        cursor = conn.execute(
            "INSERT INTO player_inventory(user_id,equip_id,equipped,canonical_slot) "
            "VALUES(?,?,?,?)",
            (user_id, equip_id, equipped, canonical_slot),
        )
    else:
        cursor = conn.execute(
            "INSERT INTO player_inventory"
            "(id,user_id,equip_id,equipped,canonical_slot) VALUES(?,?,?,?,?)",
            (row_id, user_id, equip_id, equipped, canonical_slot),
        )
    return int(row_id if row_id is not None else cursor.lastrowid)


def _row(conn: sqlite3.Connection, row_id: int) -> tuple[Any, ...]:
    result = conn.execute(
        "SELECT id,user_id,equip_id,equipped,canonical_slot "
        "FROM player_inventory WHERE id=?",
        (row_id,),
    ).fetchone()
    assert result is not None
    return tuple(result)


def test_item_identity_mode_remains_backward_compatible():
    conn = _new_connection()
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
        assert "target_ownership_row_id" not in result
    finally:
        conn.close()


def test_exact_duplicate_equip_targets_requested_ownership_row():
    conn = _new_connection()
    try:
        _apply_b033(conn)
        _insert(conn, 1, "iron_sword", row_id=101)
        _insert(conn, 1, "iron_sword", row_id=205)

        result = loadout.equip_owned_item(
            conn,
            1,
            "iron_sword",
            ownership_row_id=205,
            equipment_defs=TEST_EQUIPMENT_DEFS,
        )

        assert result["target_ownership_row_id"] == 205
        assert result["equipped_ownership_row_id"] == 205
        assert _row(conn, 101) == (101, 1, "iron_sword", 0, None)
        assert _row(conn, 205) == (205, 1, "iron_sword", 1, "weapon")
    finally:
        conn.close()


def test_exact_equip_replaces_existing_slot_and_proves_target_row():
    conn = _new_connection()
    try:
        _apply_b033(conn)
        _insert(conn, 1, "wooden_sword", row_id=10)
        _insert(conn, 1, "iron_sword", row_id=205)
        loadout.equip_owned_item(
            conn, 1, "wooden_sword", equipment_defs=TEST_EQUIPMENT_DEFS
        )

        result = loadout.equip_owned_item(
            conn,
            1,
            "iron_sword",
            ownership_row_id=205,
            equipment_defs=TEST_EQUIPMENT_DEFS,
        )

        assert result["target_ownership_row_id"] == 205
        assert result["equipped_ownership_row_id"] == 205
        assert result["previous_equipped_item_id"] == "wooden_sword"
        assert _row(conn, 10) == (10, 1, "wooden_sword", 0, "weapon")
        assert _row(conn, 205) == (205, 1, "iron_sword", 1, "weapon")
    finally:
        conn.close()


def test_exact_equip_replay_is_idempotent_for_same_row():
    conn = _new_connection()
    try:
        _apply_b033(conn)
        _insert(conn, 1, "iron_sword", row_id=205)
        first = loadout.equip_owned_item(
            conn,
            1,
            "iron_sword",
            ownership_row_id=205,
            equipment_defs=TEST_EQUIPMENT_DEFS,
        )
        second = loadout.equip_owned_item(
            conn,
            1,
            "iron_sword",
            ownership_row_id=205,
            equipment_defs=TEST_EQUIPMENT_DEFS,
        )

        assert first["changed"] is True
        assert second["changed"] is False
        assert second["target_ownership_row_id"] == 205
        assert second["equipped_ownership_row_id"] == 205
        assert _row(conn, 205) == (205, 1, "iron_sword", 1, "weapon")
    finally:
        conn.close()


def test_exact_unequip_changes_only_requested_duplicate_row():
    conn = _new_connection()
    try:
        _apply_b033(conn)
        _insert(conn, 1, "iron_sword", row_id=101)
        _insert(conn, 1, "iron_sword", row_id=205)
        loadout.equip_owned_item(
            conn,
            1,
            "iron_sword",
            ownership_row_id=205,
            equipment_defs=TEST_EQUIPMENT_DEFS,
        )

        result = loadout.unequip_owned_item(
            conn,
            1,
            "iron_sword",
            ownership_row_id=205,
            equipment_defs=TEST_EQUIPMENT_DEFS,
        )

        assert result["changed"] is True
        assert result["target_ownership_row_id"] == 205
        assert result["equipped_ownership_row_id"] is None
        assert _row(conn, 101) == (101, 1, "iron_sword", 0, None)
        assert _row(conn, 205) == (205, 1, "iron_sword", 0, "weapon")
    finally:
        conn.close()


def test_exact_unequip_of_already_unequipped_duplicate_is_noop():
    conn = _new_connection()
    try:
        _apply_b033(conn)
        _insert(conn, 1, "iron_sword", row_id=101)
        _insert(conn, 1, "iron_sword", row_id=205, equipped=1, canonical_slot="weapon")

        result = loadout.unequip_owned_item(
            conn,
            1,
            "iron_sword",
            ownership_row_id=101,
            equipment_defs=TEST_EQUIPMENT_DEFS,
        )

        assert result["changed"] is False
        assert result["target_ownership_row_id"] == 101
        assert result["equipped_ownership_row_id"] is None
        assert _row(conn, 205) == (205, 1, "iron_sword", 1, "weapon")
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("operation", "equip_id", "row_id", "expected_code"),
    (
        ("equip", "iron_sword", 999, "EQUIPMENT_OWNERSHIP_ROW_NOT_FOUND"),
        ("equip", "iron_sword", 205, "EQUIPMENT_OWNERSHIP_IDENTITY_MISMATCH"),
        ("equip", "iron_sword", 301, "EQUIPMENT_OWNERSHIP_IDENTITY_MISMATCH"),
    ),
)
def test_exact_row_identity_failures_are_stable(
    operation: str,
    equip_id: str,
    row_id: int,
    expected_code: str,
):
    conn = _new_connection()
    try:
        _apply_b033(conn)
        _insert(conn, 1, "wooden_sword", row_id=205)
        _insert(conn, 2, "iron_sword", row_id=301)
        with pytest.raises(loadout.EquipmentLoadoutError) as error:
            getattr(loadout, f"{operation}_owned_item")(
                conn,
                1,
                equip_id,
                ownership_row_id=row_id,
                equipment_defs=TEST_EQUIPMENT_DEFS,
            )
        assert error.value.code == expected_code
        assert _row(conn, 205) == (205, 1, "wooden_sword", 0, None)
        assert _row(conn, 301) == (301, 2, "iron_sword", 0, None)
    finally:
        conn.close()


@pytest.mark.parametrize("bad_row_id", (0, -1, True, "205"))
def test_invalid_exact_row_id_fails_before_mutation(bad_row_id: Any):
    conn = _new_connection()
    try:
        _apply_b033(conn)
        _insert(conn, 1, "iron_sword", row_id=205)
        with pytest.raises(loadout.EquipmentLoadoutError) as error:
            loadout.equip_owned_item(
                conn,
                1,
                "iron_sword",
                ownership_row_id=bad_row_id,
                equipment_defs=TEST_EQUIPMENT_DEFS,
            )
        assert error.value.code == "INVALID_OWNERSHIP_ROW_ID"
        assert _row(conn, 205) == (205, 1, "iron_sword", 0, None)
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("equip_id", "slot"),
    (("cloth_robe", "armor"), ("lucky_stone", "accessory")),
)
def test_exact_targeting_preserves_armor_and_accessory_authority(
    equip_id: str, slot: str
):
    conn = _new_connection()
    try:
        _apply_b033(conn)
        row_id = _insert(conn, 1, equip_id, row_id=205)
        result = loadout.equip_owned_item(
            conn,
            1,
            equip_id,
            ownership_row_id=row_id,
            equipment_defs=TEST_EQUIPMENT_DEFS,
        )
        assert result["target_ownership_row_id"] == row_id
        assert result["equipped_ownership_row_id"] == row_id
        assert _row(conn, row_id) == (row_id, 1, equip_id, 1, slot)
    finally:
        conn.close()


@pytest.mark.parametrize("equip_id", ("xp_amulet", "go_stone_black"))
def test_exact_targeting_cannot_bypass_locked_items(equip_id: str):
    conn = _new_connection()
    try:
        _apply_b033(conn)
        row_id = _insert(conn, 1, equip_id, row_id=205)
        expected = (
            "XP_AMULET_HOLD_FOR_AUTHORITY"
            if equip_id == "xp_amulet"
            else "GO_STONE_BLACK_NOT_EQUIPPABLE"
        )
        with pytest.raises(loadout.EquipmentLoadoutError) as error:
            loadout.equip_owned_item(
                conn,
                1,
                equip_id,
                ownership_row_id=row_id,
                equipment_defs=TEST_EQUIPMENT_DEFS,
            )
        assert error.value.code == expected
        assert _row(conn, row_id) == (row_id, 1, equip_id, 0, None)
    finally:
        conn.close()


def test_exact_inv_id_service_contract_matches_e030_resolution():
    conn = _new_connection()
    try:
        _apply_b033(conn)
        inv_id = _insert(conn, 1, "iron_sword", row_id=205)
        requested = conn.execute(
            "SELECT id,equip_id FROM player_inventory WHERE id=? AND user_id=?",
            (inv_id, 1),
        ).fetchone()
        assert requested is not None

        result = loadout.equip_owned_item(
            conn,
            1,
            requested["equip_id"],
            ownership_row_id=requested["id"],
            equipment_defs=TEST_EQUIPMENT_DEFS,
        )

        assert result["target_ownership_row_id"] == 205
        assert result["equipped_ownership_row_id"] == 205
        assert _row(conn, 205)[3] == 1
    finally:
        conn.close()


def test_malformed_b033_fails_closed_without_exact_row_mutation(monkeypatch):
    conn = _new_connection()
    try:
        conn.execute("ALTER TABLE player_inventory ADD COLUMN canonical_slot TEXT")
        _insert(conn, 1, "iron_sword", row_id=205)
        monkeypatch.setattr(
            loadout,
            "validate_schema",
            lambda _conn: {"valid": False, "missing": ["uq_player_inventory_user_equipped_slot"]},
        )
        with pytest.raises(loadout.EquipmentLoadoutError) as error:
            loadout.equip_owned_item(
                conn,
                1,
                "iron_sword",
                ownership_row_id=205,
                equipment_defs=TEST_EQUIPMENT_DEFS,
            )
        assert error.value.code == "SCHEMA_INVARIANT_UNAVAILABLE"
        assert _row(conn, 205) == (205, 1, "iron_sword", 0, None)
    finally:
        conn.close()


def test_caller_rollback_reverses_exact_row_mutation(tmp_path: Path):
    db_path = tmp_path / "b041_exact_row_rollback.sqlite"
    setup = sqlite3.connect(db_path)
    setup.row_factory = sqlite3.Row
    setup.execute(
        """CREATE TABLE player_inventory (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER NOT NULL,
             equip_id TEXT NOT NULL,
             equipped INTEGER NOT NULL DEFAULT 0,
             obtained_at TEXT,
             source TEXT NOT NULL DEFAULT 'test'
        )"""
    )
    upgrade_b033(setup, equipment_defs=TEST_EQUIPMENT_DEFS)
    _insert(setup, 1, "iron_sword", row_id=205)
    setup.commit()
    setup.close()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        result = loadout.equip_owned_item(
            conn,
            1,
            "iron_sword",
            ownership_row_id=205,
            equipment_defs=TEST_EQUIPMENT_DEFS,
        )
        assert result["equipped_ownership_row_id"] == 205
        conn.rollback()
        assert _row(conn, 205) == (205, 1, "iron_sword", 0, None)
    finally:
        conn.close()


class _TransactionSpy:
    def __init__(self, raw: sqlite3.Connection):
        self._conn = raw
        self.commit_count = 0
        self.rollback_count = 0

    def execute(self, sql: str, parameters: Any = ()):
        return self._conn.execute(sql, parameters)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


def test_service_does_not_commit_or_rollback_for_exact_target():
    raw = _new_connection()
    conn = _TransactionSpy(raw)
    try:
        _apply_b033(raw)
        _insert(raw, 1, "iron_sword", row_id=205)
        result = loadout.equip_owned_item(
            conn,
            1,
            "iron_sword",
            ownership_row_id=205,
            equipment_defs=TEST_EQUIPMENT_DEFS,
        )
        assert result["target_ownership_row_id"] == 205
        assert conn.commit_count == 0
        assert conn.rollback_count == 0
    finally:
        raw.close()
