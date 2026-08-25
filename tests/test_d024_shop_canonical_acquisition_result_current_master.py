"""D024 current-master integration tests for all three Shop destinations."""

from __future__ import annotations

from datetime import datetime, timezone
import copy
import json
import sqlite3
from typing import Any

import pytest

from canonical_acquisition_result import AcquisitionResultValidationError
import shop_acquisition_result_bridge as bridge
from coin_purchase_authority import (
    CoinPurchaseResult,
    SqlAcquisitionAuthority,
    purchase_with_coins,
)
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_purchase_operations
from migrations.domain_event_outbox_v1 import upgrade as upgrade_event_outbox
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_b033
from shop_offer_authority import CoinShopOffer, StaticShopOfferAuthority


FIXED_NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
SLOT_DEFS = (
    {"id": "iron_sword", "slot": "weapon"},
    {"id": "cloth_robe", "slot": "armor"},
)
SLOT_SOURCE = {"iron_sword": "weapon", "cloth_robe": "armor"}


class CallerConnection:
    def __init__(self, raw: sqlite3.Connection):
        self._conn = raw
        self.commit_count = 0
        self.rollback_count = 0

    def execute(self, sql: str, parameters: Any = ()):
        return self._conn.execute(sql, parameters)

    def commit(self):
        self.commit_count += 1
        self._conn.commit()

    def rollback(self):
        self.rollback_count += 1
        self._conn.rollback()

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


class BridgeReadOnlyConnection:
    """Allow only the fixed D023 membership reads and no transaction calls."""

    def __init__(self, raw: sqlite3.Connection):
        self.raw = raw
        self.statements: list[str] = []
        self.commit_count = 0
        self.rollback_count = 0

    def execute(self, sql: str, parameters: Any = ()):
        normalized = sql.strip().upper()
        self.statements.append(sql)
        assert not normalized.startswith(
            ("INSERT", "UPDATE", "DELETE", "REPLACE", "ALTER", "DROP", "CREATE")
        )
        assert "FROM PLAYER_INVENTORY" not in normalized
        assert "MAX(" not in normalized
        assert "ORDER BY" not in normalized
        assert "TIMESTAMP" not in normalized
        return self.raw.execute(sql, parameters)

    def commit(self):
        self.commit_count += 1
        raise AssertionError("D024 bridge must not commit")

    def rollback(self):
        self.rollback_count += 1
        raise AssertionError("D024 bridge must not rollback")


def _connection() -> CallerConnection:
    raw = sqlite3.connect(":memory:")
    raw.row_factory = sqlite3.Row
    conn = CallerConnection(raw)
    conn.execute(
        "CREATE TABLE user_stats (user_id INTEGER PRIMARY KEY, coins INTEGER NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE currency_log ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
        "delta INTEGER NOT NULL, balance_after INTEGER NOT NULL, reason TEXT NOT NULL, "
        "created_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE player_inventory ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
        "equip_id TEXT NOT NULL, equipped INTEGER NOT NULL DEFAULT 0, "
        "obtained_at TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'drop')"
    )
    upgrade_b033(conn, equipment_defs=SLOT_DEFS)
    conn.execute(
        "CREATE TABLE shop_inventory ("
        "user_id INTEGER NOT NULL, item_key TEXT NOT NULL, qty INTEGER NOT NULL DEFAULT 0, "
        "PRIMARY KEY (user_id, item_key))"
    )
    conn.execute(
        "CREATE TABLE player_wardrobe ("
        "user_id INTEGER NOT NULL, item_id TEXT NOT NULL, obtained_at TEXT NOT NULL, "
        "source TEXT NOT NULL, PRIMARY KEY (user_id, item_id))"
    )
    upgrade_purchase_operations(conn)
    upgrade_event_outbox(conn)
    conn.execute("INSERT INTO user_stats(user_id, coins) VALUES(1, 1000)")
    conn.commit()
    return conn


def _offer(
    *,
    item_id: str,
    destination: str,
    acquisition_class: str,
    duplicate_policy: str,
    price: int,
) -> CoinShopOffer:
    return CoinShopOffer(
        offer_id=f"shop.static.{item_id}",
        item_id=item_id,
        quantity=1,
        currency_type="COINS",
        price=price,
        destination=destination,
        acquisition_class=acquisition_class,
        offer_type="ITEM",
        offer_version="v1-d024",
        status="ACTIVE",
        duplicate_policy=duplicate_policy,
    )


def _purchase(
    conn: CallerConnection,
    *,
    operation_id: str,
    offer: CoinShopOffer,
) -> CoinPurchaseResult:
    authority = StaticShopOfferAuthority({offer.offer_id: offer})
    return purchase_with_coins(
        conn,
        1,
        operation_id,
        offer.offer_id,
        offer_authority=authority,
        acquisition_authority=SqlAcquisitionAuthority(
            equipment_slot_source=SLOT_SOURCE
        ),
        now=FIXED_NOW,
    )


def _committed_facts(
    conn: CallerConnection,
    result: CoinPurchaseResult,
) -> tuple[dict[str, Any], dict[str, Any]]:
    operation = conn.execute(
        "SELECT user_id, purchase_operation_id, offer_id, reward_id, reward_quantity, "
        "destination, acquisition_class, operation_status, lineage_event_id "
        "FROM coin_purchase_operations "
        "WHERE user_id=? AND purchase_operation_id=?",
        (1, result.operation_id),
    ).fetchone()
    assert operation is not None
    event = conn.execute(
        "SELECT event_id, event_type, player_id, payload "
        "FROM domain_event_outbox WHERE event_id=?",
        (result.lineage_event_id,),
    ).fetchone()
    assert event is not None
    return dict(operation), dict(event)


def _bridge(
    conn: CallerConnection,
    result: CoinPurchaseResult,
) -> tuple[Any, BridgeReadOnlyConnection]:
    operation, lineage = _committed_facts(conn, result)
    readonly = BridgeReadOnlyConnection(conn._conn)
    canonical = bridge.adapt_committed_shop_purchase(
        readonly,
        result,
        operation,
        lineage,
    )
    return canonical, readonly


def test_committed_c026_player_inventory_result_uses_exact_inserted_reference():
    conn = _connection()
    result = _purchase(
        conn,
        operation_id="op-player-a",
        offer=_offer(
            item_id="iron_sword",
            destination="player_inventory",
            acquisition_class="WEAPON",
            duplicate_policy="ALLOW_DUPLICATE",
            price=100,
        ),
    )
    conn.commit()

    canonical, readonly = _bridge(conn, result)
    row = conn.execute(
        "SELECT id FROM player_inventory WHERE user_id=1 AND equip_id='iron_sword'"
    ).fetchone()

    assert row is not None
    assert canonical.destination == "PLAYER_INVENTORY"
    assert canonical.ownership_reference == f"player_inventory:{row['id']}"
    assert canonical.ownership_reference == result.ownership_reference
    assert readonly.statements == []


def test_allow_duplicate_operations_have_distinct_refs_and_replay_first_is_stable():
    conn = _connection()
    offer = _offer(
        item_id="iron_sword",
        destination="player_inventory",
        acquisition_class="WEAPON",
        duplicate_policy="ALLOW_DUPLICATE",
        price=100,
    )

    first = _purchase(conn, operation_id="op-a", offer=offer)
    conn.commit()
    first_canonical, first_reads = _bridge(conn, first)

    second = _purchase(conn, operation_id="op-b", offer=offer)
    conn.commit()
    second_canonical, second_reads = _bridge(conn, second)

    replay = _purchase(conn, operation_id="op-a", offer=offer)
    replay_canonical, replay_reads = _bridge(conn, replay)

    assert first_canonical.ownership_reference != second_canonical.ownership_reference
    assert replay.replayed is True
    assert replay_canonical.ownership_reference == first_canonical.ownership_reference
    assert replay_canonical.ownership_reference != second_canonical.ownership_reference
    assert first_reads.statements == second_reads.statements == replay_reads.statements == []


@pytest.mark.parametrize(
    "bad_reference",
    [
        "player_inventory:0",
        "player_inventory:-1",
        "player_inventory:01",
        "PLAYER_INVENTORY:1",
        "shop_inventory:1",
    ],
)
def test_player_inventory_malformed_reference_fails_closed(bad_reference: str):
    conn = _connection()
    result = _purchase(
        conn,
        operation_id=f"op-bad-{bad_reference.replace(':', '-')}",
        offer=_offer(
            item_id="iron_sword",
            destination="player_inventory",
            acquisition_class="WEAPON",
            duplicate_policy="ALLOW_DUPLICATE",
            price=100,
        ),
    )
    conn.commit()
    operation, lineage = _committed_facts(conn, result)
    payload = result.as_dict()
    payload["ownership_reference"] = bad_reference
    payload["ownership_result"]["ownership_reference"] = bad_reference

    with pytest.raises(bridge.ShopAcquisitionBridgeError) as exc_info:
        bridge.adapt_committed_shop_purchase(
            BridgeReadOnlyConnection(conn._conn),
            payload,
            operation,
            lineage,
        )

    assert exc_info.value.code == "MALFORMED_OWNERSHIP_REFERENCE"


def test_missing_player_inventory_reference_fails_closed():
    conn = _connection()
    result = _purchase(
        conn,
        operation_id="op-missing-ref",
        offer=_offer(
            item_id="iron_sword",
            destination="player_inventory",
            acquisition_class="WEAPON",
            duplicate_policy="ALLOW_DUPLICATE",
            price=100,
        ),
    )
    conn.commit()
    operation, lineage = _committed_facts(conn, result)
    payload = result.as_dict()
    payload["ownership_reference"] = None
    payload["ownership_result"]["ownership_reference"] = None

    with pytest.raises(bridge.ShopAcquisitionBridgeError) as exc_info:
        bridge.adapt_committed_shop_purchase(
            BridgeReadOnlyConnection(conn._conn),
            payload,
            operation,
            lineage,
        )

    assert exc_info.value.code == bridge.PLAYER_INVENTORY_FAILURE_CODE


def test_top_level_nested_and_lineage_reference_mismatch_fails_closed():
    conn = _connection()
    result = _purchase(
        conn,
        operation_id="op-mismatch",
        offer=_offer(
            item_id="iron_sword",
            destination="player_inventory",
            acquisition_class="WEAPON",
            duplicate_policy="ALLOW_DUPLICATE",
            price=100,
        ),
    )
    conn.commit()
    operation, lineage = _committed_facts(conn, result)

    payload = result.as_dict()
    payload["ownership_result"]["ownership_reference"] = "player_inventory:999"
    with pytest.raises(bridge.ShopAcquisitionBridgeError) as nested:
        bridge.adapt_committed_shop_purchase(
            BridgeReadOnlyConnection(conn._conn),
            payload,
            operation,
            lineage,
        )
    assert nested.value.code == "OWNERSHIP_REFERENCE_MISMATCH"

    payload = result.as_dict()
    lineage_copy = copy.deepcopy(lineage)
    lineage_payload = json.loads(lineage_copy["payload"])
    lineage_payload["ownership_result"]["ownership_reference"] = "player_inventory:999"
    lineage_copy["payload"] = json.dumps(lineage_payload)
    with pytest.raises(bridge.ShopAcquisitionBridgeError) as lineage_error:
        bridge.adapt_committed_shop_purchase(
            BridgeReadOnlyConnection(conn._conn),
            payload,
            operation,
            lineage_copy,
        )
    assert lineage_error.value.code == "OWNERSHIP_REFERENCE_MISMATCH"


def test_d5a_event_operation_and_canonical_slot_are_not_ownership_references():
    conn = _connection()
    result = _purchase(
        conn,
        operation_id="op-identities",
        offer=_offer(
            item_id="iron_sword",
            destination="player_inventory",
            acquisition_class="WEAPON",
            duplicate_policy="ALLOW_DUPLICATE",
            price=100,
        ),
    )
    conn.commit()
    canonical, _ = _bridge(conn, result)

    assert canonical.ownership_reference.startswith("player_inventory:")
    assert result.lineage_event_id != canonical.ownership_reference
    assert result.operation_id != canonical.ownership_reference
    assert "weapon" not in canonical.ownership_reference


def test_stack_and_wardrobe_keep_d023_composite_references_with_none_payload_refs():
    conn = _connection()
    stack_offer = _offer(
        item_id="hint_ticket",
        destination="shop_inventory",
        acquisition_class="CONSUMABLE",
        duplicate_policy="STACK",
        price=30,
    )
    wardrobe_offer = _offer(
        item_id="robe_plain",
        destination="player_wardrobe",
        acquisition_class="COSMETIC",
        duplicate_policy="REJECT_IF_OWNED",
        price=200,
    )

    stack = _purchase(conn, operation_id="op-stack", offer=stack_offer)
    conn.commit()
    stack_canonical, stack_reads = _bridge(conn, stack)

    wardrobe = _purchase(conn, operation_id="op-wardrobe", offer=wardrobe_offer)
    conn.commit()
    wardrobe_canonical, wardrobe_reads = _bridge(conn, wardrobe)

    assert stack_canonical.ownership_reference == "shop_inventory:1:hint_ticket"
    assert wardrobe_canonical.ownership_reference == "player_wardrobe:1:robe_plain"
    assert stack_reads.statements == [
        "SELECT 1 FROM shop_inventory WHERE user_id = ? AND item_key = ?"
    ]
    assert wardrobe_reads.statements == [
        "SELECT 1 FROM player_wardrobe WHERE user_id = ? AND item_id = ?"
    ]


@pytest.mark.parametrize("status", ["SUCCESS", "IN_PROGRESS", "FAILED"])
def test_uncommitted_or_success_only_operation_evidence_fails_closed(status: str):
    conn = _connection()
    result = _purchase(
        conn,
        operation_id=f"op-status-{status.lower()}",
        offer=_offer(
            item_id="hint_ticket",
            destination="shop_inventory",
            acquisition_class="CONSUMABLE",
            duplicate_policy="STACK",
            price=30,
        ),
    )
    conn.commit()
    operation, lineage = _committed_facts(conn, result)
    operation["operation_status"] = status

    with pytest.raises(bridge.ShopAcquisitionBridgeError) as exc_info:
        bridge.adapt_committed_shop_purchase(
            BridgeReadOnlyConnection(conn._conn),
            result,
            operation,
            lineage,
        )

    assert exc_info.value.code == "COMMITTED_RESULT_EVIDENCE_REQUIRED"


def test_bridge_has_no_writes_commits_rollbacks_or_player_inventory_identity_read():
    conn = _connection()
    result = _purchase(
        conn,
        operation_id="op-read-only",
        offer=_offer(
            item_id="hint_ticket",
            destination="shop_inventory",
            acquisition_class="CONSUMABLE",
            duplicate_policy="STACK",
            price=30,
        ),
    )
    conn.commit()
    before = {
        "shop": conn.execute("SELECT * FROM shop_inventory").fetchall(),
        "wardrobe": conn.execute("SELECT * FROM player_wardrobe").fetchall(),
        "inventory": conn.execute("SELECT * FROM player_inventory").fetchall(),
    }
    _, readonly = _bridge(conn, result)
    after = {
        "shop": conn.execute("SELECT * FROM shop_inventory").fetchall(),
        "wardrobe": conn.execute("SELECT * FROM player_wardrobe").fetchall(),
        "inventory": conn.execute("SELECT * FROM player_inventory").fetchall(),
    }

    assert before == after
    assert readonly.commit_count == 0
    assert readonly.rollback_count == 0
    assert bridge.DATABASE_WRITES == 0
    assert bridge.MUTATION_CAPABILITY == "NO"


def test_actual_c026_result_object_is_accepted_without_reconstructing_row_identity():
    conn = _connection()
    result = _purchase(
        conn,
        operation_id="op-object",
        offer=_offer(
            item_id="cloth_robe",
            destination="player_inventory",
            acquisition_class="ARMOR",
            duplicate_policy="ALLOW_DUPLICATE",
            price=125,
        ),
    )
    conn.commit()

    canonical, readonly = _bridge(conn, result)

    assert isinstance(result, CoinPurchaseResult)
    assert canonical.ownership_reference == result.ownership_reference
    assert readonly.statements == []
