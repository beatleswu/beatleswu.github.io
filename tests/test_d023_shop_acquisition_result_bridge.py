"""Focused D023 tests for the read-only Shop ownership-reference bridge."""

from __future__ import annotations

import copy
import inspect
import sqlite3

import pytest

from canonical_acquisition_result import AcquisitionResultValidationError
import shop_acquisition_result_bridge as bridge


class ReadOnlyConnection:
    """Reject mutation SQL and transaction control while recording reads."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.statements: list[str] = []
        self.transaction_calls: list[str] = []

    def execute(self, sql: str, parameters=()):
        self.statements.append(sql)
        normalized = sql.strip().upper()
        assert not normalized.startswith(
            ("INSERT", "UPDATE", "DELETE", "REPLACE", "ALTER", "DROP", "CREATE")
        )
        assert "MAX(" not in normalized
        assert "ORDER BY" not in normalized
        assert "LAST_INSERT_ROWID" not in normalized
        return self.connection.execute(sql, parameters)

    def commit(self):
        self.transaction_calls.append("commit")
        raise AssertionError("D023 bridge must not commit")

    def rollback(self):
        self.transaction_calls.append("rollback")
        raise AssertionError("D023 bridge must not rollback")


def _database() -> tuple[sqlite3.Connection, ReadOnlyConnection]:
    raw = sqlite3.connect(":memory:")
    raw.execute(
        "CREATE TABLE shop_inventory (user_id INTEGER NOT NULL, item_key TEXT NOT NULL, qty INTEGER NOT NULL, PRIMARY KEY (user_id, item_key))"
    )
    raw.execute(
        "CREATE TABLE player_wardrobe (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, item_id TEXT NOT NULL, UNIQUE (user_id, item_id))"
    )
    return raw, ReadOnlyConnection(raw)


def _facts(
    *,
    destination: str = "shop_inventory",
    operation_id: str = "purchase-1",
    item_id: str = "starfruit",
    quantity: int = 2,
    resulting_quantity: int | None = 7,
    is_new: bool | None = False,
    replayed: bool = False,
    item_class: str = "CONSUMABLE",
    can_equip: bool = False,
    can_use: bool = True,
    can_wear: bool = False,
    lineage_event_id: str = "lineage-1",
):
    result = {
        "operation_id": operation_id,
        "source_operation_id": operation_id,
        "offer_id": f"offer:{item_id}",
        "item_id": item_id,
        "quantity": quantity,
        "destination": destination,
        "ownership_result": {
            "destination": destination,
            "item_id": item_id,
            "quantity": quantity,
            "new_quantity": resulting_quantity,
            "is_new": is_new,
            "can_equip": can_equip,
            "can_use": can_use,
            "can_wear": can_wear,
        },
        "is_new": is_new,
        "can_equip": can_equip,
        "can_use": can_use,
        "can_wear": can_wear,
        "lineage_event_id": lineage_event_id,
        "replayed": replayed,
    }
    operation = {
        "user_id": 7,
        "purchase_operation_id": operation_id,
        "offer_id": f"offer:{item_id}",
        "item_id": item_id,
        "reward_id": item_id,
        "reward_quantity": quantity,
        "destination": destination,
        "acquisition_class": item_class,
        "operation_status": "COMMITTED",
        "lineage_event_id": lineage_event_id,
    }
    lineage = {
        "event_id": lineage_event_id,
        "event_type": "ITEM_ACQUISITION",
        "player_id": "7",
        "payload": {
            "source_operation_id": operation_id,
            "offer_id": f"offer:{item_id}",
            "item_id": item_id,
            "quantity": quantity,
            "destination": destination,
            "ownership_authority": destination,
        },
    }
    return result, operation, lineage


def _run(
    connection: ReadOnlyConnection,
    *,
    result,
    operation,
    lineage,
):
    return bridge.adapt_committed_shop_purchase(
        connection,
        result,
        operation,
        lineage,
    )


def test_stack_result_uses_composite_reference_and_committed_quantity():
    raw, connection = _database()
    raw.execute("INSERT INTO shop_inventory (user_id, item_key, qty) VALUES (7, 'starfruit', 7)")

    result, operation, lineage = _facts()
    canonical = _run(connection, result=result, operation=operation, lineage=lineage)

    assert canonical.destination == "STACK_INVENTORY"
    assert canonical.ownership_authority == "shop_inventory"
    assert canonical.ownership_reference == "shop_inventory:7:starfruit"
    assert canonical.quantity == 2
    assert canonical.resulting_quantity == 7


def test_stack_replay_has_the_same_reference_and_does_not_read_current_quantity():
    raw, connection = _database()
    raw.execute("INSERT INTO shop_inventory (user_id, item_key, qty) VALUES (7, 'starfruit', 7)")
    result, operation, lineage = _facts(replayed=True)

    first = _run(connection, result=result, operation=operation, lineage=lineage)
    raw.execute("UPDATE shop_inventory SET qty = 99 WHERE user_id = 7 AND item_key = 'starfruit'")
    replay = _run(connection, result=result, operation=operation, lineage=lineage)

    assert replay.ownership_reference == first.ownership_reference
    assert replay.replayed is True
    assert replay.resulting_quantity == 7
    assert replay.quantity == 2


def test_missing_stack_authority_row_fails_closed_without_writes():
    raw, connection = _database()
    before = raw.execute("SELECT * FROM shop_inventory").fetchall()
    result, operation, lineage = _facts()

    with pytest.raises(bridge.ShopAcquisitionBridgeError) as exc_info:
        _run(connection, result=result, operation=operation, lineage=lineage)

    assert exc_info.value.code == "OWNERSHIP_AUTHORITY_ROW_MISSING"
    assert raw.execute("SELECT * FROM shop_inventory").fetchall() == before
    assert connection.transaction_calls == []


def test_wardrobe_result_uses_user_bound_membership_reference():
    raw, connection = _database()
    raw.execute("INSERT INTO player_wardrobe (user_id, item_id) VALUES (7, 'ember_cape')")
    result, operation, lineage = _facts(
        destination="player_wardrobe",
        item_id="ember_cape",
        quantity=1,
        resulting_quantity=1,
        is_new=True,
        item_class="COSMETIC",
        can_use=False,
        can_wear=True,
    )

    canonical = _run(connection, result=result, operation=operation, lineage=lineage)

    assert canonical.destination == "PLAYER_WARDROBE"
    assert canonical.ownership_reference == "player_wardrobe:7:ember_cape"
    assert canonical.ownership_reference != "ember_cape"
    assert canonical.can_equip is False
    assert canonical.can_use is False
    assert canonical.can_wear is True


def test_wardrobe_replay_reference_is_stable_and_preserves_is_new_evidence():
    raw, connection = _database()
    raw.execute("INSERT INTO player_wardrobe (user_id, item_id) VALUES (7, 'ember_cape')")
    result, operation, lineage = _facts(
        destination="player_wardrobe",
        item_id="ember_cape",
        quantity=1,
        resulting_quantity=1,
        is_new=True,
        replayed=True,
        item_class="COSMETIC",
        can_use=False,
        can_wear=True,
    )

    canonical = _run(connection, result=result, operation=operation, lineage=lineage)

    assert canonical.ownership_reference == "player_wardrobe:7:ember_cape"
    assert canonical.replayed is True
    assert canonical.is_new is True
    assert canonical.metadata["ownership_evidence"]["pre_grant_owned"] is False


def test_payload_ownership_reference_is_not_an_authority_input():
    raw, connection = _database()
    raw.execute("INSERT INTO shop_inventory (user_id, item_key, qty) VALUES (7, 'starfruit', 7)")
    result, operation, lineage = _facts()
    result["ownership_result"]["ownership_reference"] = "starfruit"

    with pytest.raises(bridge.ShopAcquisitionBridgeError) as exc_info:
        _run(connection, result=result, operation=operation, lineage=lineage)

    assert exc_info.value.code == "CLIENT_OWNERSHIP_REFERENCE_REJECTED"


def test_player_inventory_fails_closed_before_any_authority_query():
    raw, connection = _database()
    result, operation, lineage = _facts(destination="player_inventory")

    with pytest.raises(bridge.ShopAcquisitionBridgeError) as exc_info:
        _run(connection, result=result, operation=operation, lineage=lineage)

    assert exc_info.value.code == bridge.PLAYER_INVENTORY_FAILURE_CODE
    assert connection.statements == []


@pytest.mark.parametrize(
    "destination",
    ["pet_inventory", "capacity", "credit", "entitlement", "unknown_destination"],
)
def test_other_destinations_fail_closed(destination):
    raw, connection = _database()
    result, operation, lineage = _facts(destination=destination)

    with pytest.raises(bridge.ShopAcquisitionBridgeError) as exc_info:
        _run(connection, result=result, operation=operation, lineage=lineage)

    assert exc_info.value.code == "UNSUPPORTED_DESTINATION"
    assert connection.statements == []


def test_reference_does_not_use_purchase_operation_lineage_or_canonical_slot():
    raw, connection = _database()
    raw.execute("INSERT INTO shop_inventory (user_id, item_key, qty) VALUES (7, 'starfruit', 7)")
    result, operation, lineage = _facts(operation_id="purchase-unique", lineage_event_id="lineage-unique")
    result["canonical_slot"] = "weapon"
    result["ownership_result"]["canonical_slot"] = "weapon"

    canonical = _run(connection, result=result, operation=operation, lineage=lineage)

    assert canonical.ownership_reference == "shop_inventory:7:starfruit"
    assert "purchase-unique" not in canonical.ownership_reference
    assert "lineage-unique" not in canonical.ownership_reference
    assert "weapon" not in canonical.ownership_reference


def test_success_status_without_separate_commit_evidence_fails_closed():
    raw, connection = _database()
    raw.execute("INSERT INTO shop_inventory (user_id, item_key, qty) VALUES (7, 'starfruit', 7)")
    result, operation, lineage = _facts()
    operation["operation_status"] = "SUCCESS"

    with pytest.raises(bridge.ShopAcquisitionBridgeError) as exc_info:
        _run(connection, result=result, operation=operation, lineage=lineage)

    assert exc_info.value.code == "COMMITTED_RESULT_EVIDENCE_REQUIRED"


def test_success_status_with_explicit_commit_marker_is_accepted():
    raw, connection = _database()
    raw.execute("INSERT INTO shop_inventory (user_id, item_key, qty) VALUES (7, 'starfruit', 7)")
    result, operation, lineage = _facts()
    operation["operation_status"] = "SUCCESS"
    operation["committed"] = True

    canonical = _run(connection, result=result, operation=operation, lineage=lineage)

    assert canonical.ownership_reference == "shop_inventory:7:starfruit"


def test_settled_status_is_commit_evidence():
    raw, connection = _database()
    raw.execute("INSERT INTO shop_inventory (user_id, item_key, qty) VALUES (7, 'starfruit', 7)")
    result, operation, lineage = _facts()
    operation["operation_status"] = "SETTLED"

    canonical = _run(connection, result=result, operation=operation, lineage=lineage)

    assert canonical.source_operation_id == "purchase-1"


def test_missing_lineage_or_mismatched_lineage_fails_closed():
    raw, connection = _database()
    raw.execute("INSERT INTO shop_inventory (user_id, item_key, qty) VALUES (7, 'starfruit', 7)")
    result, operation, lineage = _facts()

    with pytest.raises(bridge.ShopAcquisitionBridgeError) as missing:
        _run(connection, result=result, operation=operation, lineage={})
    assert missing.value.code == "REQUIRED_TRUSTED_FACT_MISSING"

    mismatched = copy.deepcopy(lineage)
    mismatched["event_id"] = "other-lineage"
    with pytest.raises(bridge.ShopAcquisitionBridgeError) as mismatch:
        _run(connection, result=result, operation=operation, lineage=mismatched)
    assert mismatch.value.code == "LINEAGE_ID_MISMATCH"


def test_result_object_as_dict_is_accepted_for_c023_compatibility():
    raw, connection = _database()
    raw.execute("INSERT INTO shop_inventory (user_id, item_key, qty) VALUES (7, 'starfruit', 7)")
    result, operation, lineage = _facts()

    class CoinPurchaseResultLike:
        def as_dict(self):
            return result

    canonical = _run(
        connection,
        result=CoinPurchaseResultLike(),
        operation=operation,
        lineage=lineage,
    )

    assert canonical.item_id == "starfruit"


def test_adapter_is_read_only_and_uses_only_fixed_membership_selects():
    raw, connection = _database()
    raw.execute("INSERT INTO shop_inventory (user_id, item_key, qty) VALUES (7, 'starfruit', 7)")
    result, operation, lineage = _facts()
    before = raw.execute("SELECT user_id, item_key, qty FROM shop_inventory").fetchall()

    _run(connection, result=result, operation=operation, lineage=lineage)

    after = raw.execute("SELECT user_id, item_key, qty FROM shop_inventory").fetchall()
    assert before == after
    assert len(connection.statements) == 1
    assert connection.statements[0].strip().upper() == (
        "SELECT 1 FROM SHOP_INVENTORY WHERE USER_ID = ? AND ITEM_KEY = ?"
    )
    assert connection.transaction_calls == []
    source = inspect.getsource(bridge)
    assert ".commit(" not in source
    assert ".rollback(" not in source


def test_xp_amulet_hold_is_preserved_without_adding_capabilities():
    raw, connection = _database()
    raw.execute("INSERT INTO shop_inventory (user_id, item_key, qty) VALUES (7, 'xp_amulet', 1)")
    result, operation, lineage = _facts(
        item_id="xp_amulet",
        quantity=1,
        resulting_quantity=1,
        item_class="ACCESSORY",
        can_equip=False,
        can_use=False,
        can_wear=False,
    )
    operation["special_status"] = "HOLD_FOR_AUTHORITY"

    canonical = _run(connection, result=result, operation=operation, lineage=lineage)

    assert canonical.metadata["special_status"] == "HOLD_FOR_AUTHORITY"
    assert canonical.can_equip is False
    assert canonical.can_use is False
    assert canonical.can_wear is False


def test_go_stone_black_cannot_be_reclassified_as_supported_stack_acquisition():
    raw, connection = _database()
    raw.execute("INSERT INTO shop_inventory (user_id, item_key, qty) VALUES (7, 'go_stone_black', 1)")
    result, operation, lineage = _facts(
        item_id="go_stone_black",
        quantity=1,
        resulting_quantity=1,
        item_class="TROPHY",
        can_equip=False,
        can_use=False,
        can_wear=False,
    )

    with pytest.raises(AcquisitionResultValidationError) as exc_info:
        _run(connection, result=result, operation=operation, lineage=lineage)

    assert exc_info.value.code == "GO_STONE_BLACK_LOCK"
