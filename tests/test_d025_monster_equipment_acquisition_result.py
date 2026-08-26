"""Focused D025 tests for the detached Monster Equipment result contract."""

from __future__ import annotations

import copy
import inspect
import sqlite3
from typing import Any

import pytest

from equipment_ownership_service import grant_equipment_ownership
from monster_settlement import MonsterSettlementResult
from monster_equipment_acquisition_result import (
    DATABASE_WRITES,
    MUTATION_CAPABILITY,
    MonsterEquipmentAcquisitionError,
    build_monster_equipment_acquisition_result,
)


TEST_EQUIPMENT_DEFS = (
    {"id": "iron_sword", "slot": "weapon"},
    {"id": "cloth_robe", "slot": "armor"},
    {"id": "lucky_stone", "slot": "accessory"},
    {"id": "xp_amulet", "slot": "accessory"},
    {"id": "go_stone_black", "slot": "accessory"},
)


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


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE player_inventory (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER NOT NULL,
             equip_id TEXT NOT NULL,
             equipped INTEGER NOT NULL DEFAULT 0,
             obtained_at TEXT NOT NULL,
             source TEXT NOT NULL DEFAULT 'drop'
        )"""
    )
    return connection


def _ownership(
    connection: sqlite3.Connection,
    *,
    user_id: int = 1,
    item_id: str = "iron_sword",
    is_new: bool | None = True,
    replayed: bool = False,
    resulting_quantity: int | None = None,
) -> dict[str, Any]:
    result = grant_equipment_ownership(
        connection,
        user_id,
        item_id,
        "drop",
        equipment_defs=TEST_EQUIPMENT_DEFS,
    )
    facts = result.as_dict()
    facts.update(
        {
            "ownership_committed": True,
            "quantity": 1,
            "is_new": is_new,
            "replayed": replayed,
            "resulting_quantity": resulting_quantity,
        }
    )
    return facts


def _settlement(
    *,
    settlement_id: str = "monster-settlement-1",
    operation_id: str | None = None,
    user_id: int = 1,
    item_id: str = "iron_sword",
    lineage_event_id: str = "monster-item-acquisition-1",
    encounter_class: str = "NORMAL",
    quantity: int = 1,
    committed: bool = True,
) -> dict[str, Any]:
    return {
        "committed": committed,
        "settlement_id": settlement_id,
        "source_operation_id": operation_id or settlement_id,
        "user_id": user_id,
        "monster_id": "legacy_bf_01_normal",
        "encounter_class": encounter_class,
        "functional_drop_id": item_id,
        "functional_drop_quantity": quantity,
        "source": "drop",
        "lineage_event_id": lineage_event_id,
    }


def _build(connection: sqlite3.Connection, **overrides: Any):
    item_id = overrides.pop("item_id", "iron_sword")
    ownership = _ownership(connection, item_id=item_id)
    settlement = _settlement(item_id=item_id, **overrides)
    return build_monster_equipment_acquisition_result(settlement, ownership)


def test_exact_b040_row_id_becomes_the_detached_canonical_reference():
    connection = _connection()
    ownership = _ownership(connection)
    canonical = build_monster_equipment_acquisition_result(
        _settlement(), ownership
    )

    assert canonical.ownership_reference == f"player_inventory:{ownership['row_id']}"
    assert canonical.ownership_authority == "player_inventory"
    assert canonical.destination == "PLAYER_INVENTORY"
    assert canonical.item_id == "iron_sword"
    assert canonical.source_type == "MONSTER_DROP"
    assert canonical.source_reference == "monster-settlement-1"
    assert canonical.metadata["ownership_row_id"] == ownership["row_id"]


def test_actual_b040_result_and_monster_settlement_objects_are_supported():
    connection = _connection()
    ownership = grant_equipment_ownership(
        connection,
        1,
        "iron_sword",
        "drop",
        equipment_defs=TEST_EQUIPMENT_DEFS,
    )
    settlement = MonsterSettlementResult(
        event_record={
            "event_id": "monster-settlement-event-object",
            "player_id": "1",
            "outcome": "SUCCESS",
            "payload": {
                "settlement_id": "object-settlement-1",
                "monster_id": "legacy_bf_01_normal",
                "functional_drop_id": "iron_sword",
                "functional_drop_quantity": 1,
            },
        },
        duplicate=False,
        monster_id="legacy_bf_01_normal",
        functional_drop_id="iron_sword",
        functional_drop_quantity=1,
        appearance_drop_id=None,
        coins_granted=0,
        functional_lineage_count=1,
        wardrobe_lineage_count=0,
        functional_payload=None,
        appearance_payload=None,
        quest_event={"event_type": "MONSTER_DEFEATED"},
    )
    canonical = build_monster_equipment_acquisition_result(
        settlement,
        ownership,
        committed_facts={
            "committed": True,
            "ownership_committed": True,
            "source": "drop",
            "lineage_event_id": "item-lineage-object",
        },
    )

    assert canonical.ownership_reference == f"player_inventory:{ownership.row_id}"
    assert canonical.source_reference == "object-settlement-1"
    assert canonical.lineage_event_id == "item-lineage-object"


def test_duplicate_same_equip_id_rows_keep_distinct_exact_references():
    connection = _connection()
    first_ownership = _ownership(connection, is_new=True)
    second_ownership = _ownership(connection, is_new=False)

    first = build_monster_equipment_acquisition_result(
        _settlement(settlement_id="settlement-a", lineage_event_id="lineage-a"),
        first_ownership,
    )
    second = build_monster_equipment_acquisition_result(
        _settlement(settlement_id="settlement-b", lineage_event_id="lineage-b"),
        second_ownership,
    )

    assert first_ownership["equip_id"] == second_ownership["equip_id"]
    assert first.ownership_reference != second.ownership_reference
    assert first.is_new is True
    assert second.is_new is False


def test_replay_preserves_the_original_detached_row_reference():
    connection = _connection()
    ownership = _ownership(connection, is_new=False, replayed=True)
    first = build_monster_equipment_acquisition_result(
        _settlement(), ownership
    )
    # A later acquisition is deliberately irrelevant: D025 has no inventory
    # lookup and can only replay the exact B040 fact it was given.
    _ownership(connection, is_new=False)
    replay = build_monster_equipment_acquisition_result(
        _settlement(), ownership
    )

    assert replay.replayed is True
    assert replay.ownership_reference == first.ownership_reference
    assert replay.to_json() == first.to_json()


def test_wrong_user_ownership_is_rejected():
    connection = _connection()
    ownership = _ownership(connection)
    ownership["user_id"] = 2

    with pytest.raises(MonsterEquipmentAcquisitionError) as error:
        build_monster_equipment_acquisition_result(_settlement(), ownership)

    assert error.value.code == "OWNERSHIP_USER_BINDING_MISMATCH"


def test_settlement_and_exact_row_item_mismatch_is_rejected():
    connection = _connection()
    ownership = _ownership(connection, item_id="iron_sword")

    with pytest.raises(MonsterEquipmentAcquisitionError) as error:
        build_monster_equipment_acquisition_result(
            _settlement(item_id="cloth_robe"), ownership
        )

    assert error.value.code == "OWNERSHIP_ITEM_MISMATCH"


def test_missing_or_malformed_exact_row_reference_fails_closed():
    connection = _connection()
    missing = _ownership(connection)
    missing.pop("row_id")
    with pytest.raises(MonsterEquipmentAcquisitionError) as missing_error:
        build_monster_equipment_acquisition_result(_settlement(), missing)
    assert missing_error.value.code == "OWNERSHIP_REFERENCE_UNAVAILABLE"

    malformed = _ownership(connection)
    malformed["ownership_reference"] = "player_inventory:01"
    malformed.pop("row_id")
    with pytest.raises(MonsterEquipmentAcquisitionError) as malformed_error:
        build_monster_equipment_acquisition_result(_settlement(), malformed)
    assert malformed_error.value.code == "MALFORMED_OWNERSHIP_REFERENCE"


def test_row_id_and_explicit_reference_mismatch_fails_closed():
    connection = _connection()
    ownership = _ownership(connection)
    ownership["ownership_reference"] = "player_inventory:999"

    with pytest.raises(MonsterEquipmentAcquisitionError) as error:
        build_monster_equipment_acquisition_result(_settlement(), ownership)

    assert error.value.code == "OWNERSHIP_REFERENCE_MISMATCH"


@pytest.mark.parametrize(
    ("item_id", "expected_class", "status"),
    [
        ("xp_amulet", "ACCESSORY", "HOLD_FOR_AUTHORITY"),
        (
            "go_stone_black",
            "TROPHY",
            "TROPHY_INVENTORY_ONLY_NO_COMBAT_POWER",
        ),
    ],
)
def test_locked_items_preserve_d020_capability_semantics(
    item_id: str, expected_class: str, status: str
):
    connection = _connection()
    ownership = _ownership(connection, item_id=item_id)
    canonical = build_monster_equipment_acquisition_result(
        _settlement(item_id=item_id), ownership
    )

    assert canonical.item_class == expected_class
    assert canonical.can_equip is False
    assert canonical.can_use is False
    assert canonical.can_wear is False
    assert canonical.metadata["special_status"] == status


def test_battlefield_boss_metadata_does_not_become_lord_authority():
    connection = _connection()
    canonical = _build(connection, encounter_class="BATTLEFIELD_BOSS")

    assert canonical.metadata["encounter_class"] == "BATTLEFIELD_BOSS"
    assert canonical.metadata["source_authority"] == "MONSTER_SETTLEMENT"
    assert "LORD" not in canonical.metadata["encounter_class"]


def test_success_alone_is_not_committed_acquisition_evidence():
    connection = _connection()
    ownership = _ownership(connection)
    settlement = _settlement(committed=False)
    settlement.pop("committed")
    settlement["settlement_status"] = "SUCCESS"

    with pytest.raises(MonsterEquipmentAcquisitionError) as error:
        build_monster_equipment_acquisition_result(settlement, ownership)

    assert error.value.code == "COMMITTED_RESULT_EVIDENCE_REQUIRED"


def test_commit_status_is_accepted_when_separate_from_success():
    connection = _connection()
    ownership = _ownership(connection)
    settlement = _settlement(committed=False)
    settlement.pop("committed")
    settlement["settlement_status"] = "SUCCESS"
    settlement["settlement_committed"] = True
    ownership["ownership_committed"] = True

    canonical = build_monster_equipment_acquisition_result(settlement, ownership)
    assert canonical.source_type == "MONSTER_DROP"


def test_caller_rollback_boundary_is_untouched_by_detached_result_builder():
    raw = _connection()
    connection = TransactionSpy(raw)
    ownership = _ownership(connection)
    canonical = build_monster_equipment_acquisition_result(_settlement(), ownership)

    assert canonical.ownership_reference == "player_inventory:1"
    assert connection.commit_count == 0
    assert connection.rollback_count == 0
    raw.rollback()
    assert raw.execute("SELECT COUNT(*) FROM player_inventory").fetchone()[0] == 0
    raw.close()


def test_bridge_is_pure_and_does_not_use_identity_lookup_or_writer_hooks():
    import monster_equipment_acquisition_result as module

    source = inspect.getsource(module)
    assert "import app" not in source
    assert ".execute(" not in source
    assert ".commit(" not in source
    assert ".rollback(" not in source
    assert "MAX(id)" not in source
    assert "ORDER BY" not in source
    assert DATABASE_WRITES == 0
    assert MUTATION_CAPABILITY == "NO"


def test_nested_b040_reference_must_agree_with_top_level_reference():
    connection = _connection()
    ownership = _ownership(connection)
    nested = copy.deepcopy(ownership)
    nested["ownership_result"] = {"ownership_reference": "player_inventory:999"}

    with pytest.raises(MonsterEquipmentAcquisitionError) as error:
        build_monster_equipment_acquisition_result(_settlement(), nested)

    assert error.value.code == "OWNERSHIP_REFERENCE_MISMATCH"


def test_nested_b040_user_and_item_bindings_cannot_override_the_exact_row():
    connection = _connection()
    ownership = _ownership(connection)
    ownership["ownership_result"] = {"user_id": 2, "equip_id": "iron_sword"}
    with pytest.raises(MonsterEquipmentAcquisitionError) as wrong_user:
        build_monster_equipment_acquisition_result(_settlement(), ownership)
    assert wrong_user.value.code == "OWNERSHIP_USER_BINDING_MISMATCH"

    ownership = _ownership(connection)
    ownership["ownership_result"] = {"user_id": 1, "equip_id": "cloth_robe"}
    with pytest.raises(MonsterEquipmentAcquisitionError) as wrong_item:
        build_monster_equipment_acquisition_result(_settlement(), ownership)
    assert wrong_item.value.code == "OWNERSHIP_ITEM_MISMATCH"
