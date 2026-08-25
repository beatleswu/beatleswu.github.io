"""C026 exact player_inventory ownership-reference tests."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

import pytest

from coin_purchase_authority import (
    AcquisitionFailed,
    CoinPurchaseError,
    CoinPurchaseResult,
    SqlAcquisitionAuthority,
    purchase_with_coins,
)
from migrations.domain_event_outbox_v1 import upgrade as upgrade_event_outbox
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_b033
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_purchase_operations
from shop_offer_authority import CoinShopOffer, StaticShopOfferAuthority
from shop_offer_identity_projection import (
    ServerShopOfferFacts,
    normalize_shop_offer,
)


FIXED_NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
SLOT_DEFS = (
    {"id": "iron_sword", "slot": "weapon"},
    {"id": "cloth_robe", "slot": "armor"},
    {"id": "lucky_stone", "slot": "accessory"},
    {"id": "xp_amulet"},
    {"id": "go_stone_black"},
)
SLOT_SOURCE = {
    "iron_sword": "weapon",
    "cloth_robe": "armor",
    "lucky_stone": "accessory",
}


class CountingConnection:
    """Small caller-owned connection wrapper for commit/rollback assertions."""

    def __init__(self, raw: sqlite3.Connection) -> None:
        self._conn = raw
        self.commit_count = 0
        self.rollback_count = 0
        self.fail_result_persistence = False

    def execute(self, sql: str, parameters: Any = ()):
        if self.fail_result_persistence and (
            "UPDATE coin_purchase_operations" in sql
            and "operation_status='COMMITTED'" in sql
        ):
            raise RuntimeError("test result persistence failure")
        return self._conn.execute(sql, parameters)

    def commit(self) -> None:
        self.commit_count += 1
        self._conn.commit()

    def rollback(self) -> None:
        self.rollback_count += 1
        self._conn.rollback()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


def _connection(*, post_b033: bool = True) -> CountingConnection:
    raw = sqlite3.connect(":memory:")
    raw.row_factory = sqlite3.Row
    conn = CountingConnection(raw)
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
    if post_b033:
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
    item_id: str = "iron_sword",
    destination: str = "player_inventory",
    acquisition_class: str = "WEAPON",
    duplicate_policy: str = "ALLOW_DUPLICATE",
    price: int = 100,
    offer_id: str | None = None,
) -> CoinShopOffer:
    return CoinShopOffer(
        offer_id=offer_id or f"shop.static.{item_id}",
        item_id=item_id,
        quantity=1,
        currency_type="COINS",
        price=price,
        destination=destination,
        acquisition_class=acquisition_class,
        offer_type="ITEM",
        offer_version="v1-c026",
        status="ACTIVE",
        duplicate_policy=duplicate_policy,
    )


def _purchase(
    conn: CountingConnection,
    *,
    operation_id: str,
    offer: CoinShopOffer,
    acquisition: SqlAcquisitionAuthority | None = None,
    lineage_writer=None,
) -> CoinPurchaseResult:
    authority = StaticShopOfferAuthority({offer.offer_id: offer})
    return purchase_with_coins(
        conn,
        1,
        operation_id,
        offer.offer_id,
        offer_authority=authority,
        acquisition_authority=acquisition
        or SqlAcquisitionAuthority(equipment_slot_source=SLOT_SOURCE),
        lineage_writer=lineage_writer,
        now=FIXED_NOW,
    )


def _inventory_rows(conn: CountingConnection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, user_id, equip_id, equipped, canonical_slot, source "
        "FROM player_inventory ORDER BY id"
    ).fetchall()


def test_exact_inserted_row_id_and_post_b033_slot_are_returned() -> None:
    conn = _connection()

    result = _purchase(conn, operation_id="op-a", offer=_offer())
    rows = _inventory_rows(conn)

    assert len(rows) == 1
    assert rows[0]["id"] > 0
    assert result.ownership_reference == f"player_inventory:{rows[0]['id']}"
    assert result.ownership_result["ownership_reference"] == result.ownership_reference
    assert rows[0]["canonical_slot"] == "weapon"
    assert rows[0]["equipped"] == 0
    assert result.ownership_result["new_quantity"] == 1


def test_reference_is_persisted_in_committed_result_payload_and_replayed() -> None:
    conn = _connection()
    result = _purchase(conn, operation_id="op-a", offer=_offer())
    conn.commit()

    operation = conn.execute(
        "SELECT operation_status, result_payload, lineage_event_id "
        "FROM coin_purchase_operations WHERE user_id=1 AND purchase_operation_id='op-a'"
    ).fetchone()
    payload = json.loads(operation["result_payload"])

    assert operation["operation_status"] == "COMMITTED"
    assert payload["ownership_reference"] == result.ownership_reference
    assert payload["ownership_result"]["ownership_reference"] == result.ownership_reference
    assert result.ownership_reference in result.canonical_payload().values()

    replay = _purchase(conn, operation_id="op-a", offer=_offer())
    assert replay.replayed is True
    assert replay.ownership_reference == result.ownership_reference
    assert len(_inventory_rows(conn)) == 1


def test_allow_duplicate_operations_capture_distinct_rows_and_replay_first() -> None:
    conn = _connection()
    offer = _offer(duplicate_policy="ALLOW_DUPLICATE")

    first = _purchase(conn, operation_id="op-a", offer=offer)
    conn.commit()
    second = _purchase(conn, operation_id="op-b", offer=offer)
    conn.commit()
    rows = _inventory_rows(conn)
    replay = _purchase(conn, operation_id="op-a", offer=offer)

    assert len(rows) == 2
    assert first.ownership_reference != second.ownership_reference
    assert first.ownership_reference == f"player_inventory:{rows[0]['id']}"
    assert second.ownership_reference == f"player_inventory:{rows[1]['id']}"
    assert replay.ownership_reference == first.ownership_reference
    assert replay.ownership_reference != second.ownership_reference
    assert len(_inventory_rows(conn)) == 2


def test_reject_if_owned_rolls_back_without_second_row_or_coin_loss() -> None:
    conn = _connection()
    offer = _offer(duplicate_policy="REJECT_IF_OWNED")
    first = _purchase(conn, operation_id="op-a", offer=offer)
    conn.commit()
    before_coins = conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0]

    with pytest.raises(AcquisitionFailed):
        _purchase(conn, operation_id="op-b", offer=offer)
    conn.rollback()

    assert first.ownership_reference == "player_inventory:1"
    assert len(_inventory_rows(conn)) == 1
    assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == before_coins
    assert conn.execute(
        "SELECT COUNT(*) FROM coin_purchase_operations WHERE purchase_operation_id='op-b'"
    ).fetchone()[0] == 0


def test_lineage_failure_after_insert_is_removed_by_caller_rollback() -> None:
    conn = _connection()

    def fail_lineage(*args, **kwargs):
        raise RuntimeError("D5A failure")

    with pytest.raises(AcquisitionFailed):
        _purchase(
            conn,
            operation_id="op-lineage-fail",
            offer=_offer(),
            lineage_writer=fail_lineage,
        )
    conn.rollback()

    assert _inventory_rows(conn) == []
    assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 1000
    assert conn.execute(
        "SELECT COUNT(*) FROM coin_purchase_operations"
    ).fetchone()[0] == 0


def test_result_persistence_failure_rolls_back_insert_and_coin_debit() -> None:
    conn = _connection()
    conn.fail_result_persistence = True

    with pytest.raises(CoinPurchaseError):
        _purchase(conn, operation_id="op-result-fail", offer=_offer())
    conn.rollback()

    assert _inventory_rows(conn) == []
    assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 1000


def test_service_never_commits_or_rolls_back_the_caller_transaction() -> None:
    conn = _connection()
    commits_before = conn.commit_count
    rollbacks_before = conn.rollback_count

    _purchase(conn, operation_id="op-transaction-boundary", offer=_offer())

    assert conn.commit_count == commits_before
    assert conn.rollback_count == rollbacks_before
    conn.rollback()


def test_d5a_event_id_is_distinct_from_ownership_and_operation_references() -> None:
    conn = _connection()
    result = _purchase(conn, operation_id="op-lineage", offer=_offer())
    conn.commit()
    event = conn.execute(
        "SELECT event_id, payload FROM domain_event_outbox "
        "WHERE player_id='1' AND event_type='ITEM_ACQUISITION'"
    ).fetchone()
    payload = json.loads(event["payload"])

    assert result.lineage_event_id == event["event_id"]
    assert event["event_id"] != result.ownership_reference
    assert result.operation_id != result.ownership_reference
    assert payload["ownership_result"]["ownership_reference"] == result.ownership_reference


def test_xp_amulet_is_rejected_without_an_inventory_row() -> None:
    conn = _connection()
    offer = _offer(item_id="xp_amulet", acquisition_class="ACCESSORY")

    with pytest.raises(AcquisitionFailed):
        _purchase(conn, operation_id="op-xp-amulet", offer=offer)
    conn.rollback()

    assert _inventory_rows(conn) == []
    assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 1000


def test_go_stone_black_is_rejected_without_an_inventory_row() -> None:
    conn = _connection()
    offer = _offer(
        item_id="go_stone_black",
        acquisition_class="TROPHY",
    )

    with pytest.raises(AcquisitionFailed):
        _purchase(conn, operation_id="op-go-stone", offer=offer)
    conn.rollback()

    assert _inventory_rows(conn) == []


def test_unknown_functional_item_fails_closed_before_insert() -> None:
    conn = _connection()
    offer = _offer(item_id="unknown_sword")

    with pytest.raises(AcquisitionFailed):
        _purchase(conn, operation_id="op-unknown", offer=offer)
    conn.rollback()

    assert _inventory_rows(conn) == []


def test_client_canonical_slot_cannot_override_server_slot_source() -> None:
    conn = _connection()
    mapping = {
        "offer_id": "shop.static.iron_sword",
        "item_id": "iron_sword",
        "quantity": 1,
        "currency_type": "COINS",
        "price": 100,
        "destination": "player_inventory",
        "acquisition_class": "WEAPON",
        "offer_version": "v1-c026",
        "duplicate_policy": "ALLOW_DUPLICATE",
        "canonical_slot": "armor",
    }
    offer = CoinShopOffer.from_mapping(mapping)

    _purchase(conn, operation_id="op-slot-client", offer=offer)
    row = _inventory_rows(conn)[0]

    assert row["canonical_slot"] == "weapon"


def test_pre_b033_schema_keeps_old_insert_shape_but_captures_exact_id() -> None:
    conn = _connection(post_b033=False)

    result = _purchase(conn, operation_id="op-pre-b033", offer=_offer())
    row = conn.execute(
        "SELECT id, equip_id, equipped FROM player_inventory"
    ).fetchone()
    columns = {
        item[1] for item in conn.execute("PRAGMA table_info(player_inventory)").fetchall()
    }

    assert "canonical_slot" not in columns
    assert result.ownership_reference == f"player_inventory:{row['id']}"
    assert row["equipped"] == 0


def test_shop_inventory_result_remains_without_player_inventory_reference() -> None:
    conn = _connection()
    offer = _offer(
        item_id="hint_ticket",
        destination="shop_inventory",
        acquisition_class="CONSUMABLE",
        duplicate_policy="STACK",
        price=30,
    )

    result = _purchase(conn, operation_id="op-shop-inventory", offer=offer)

    assert result.ownership_reference is None
    assert conn.execute(
        "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='hint_ticket'"
    ).fetchone()[0] == 1


def test_player_wardrobe_result_remains_without_player_inventory_reference() -> None:
    conn = _connection()
    offer = _offer(
        item_id="robe_plain",
        destination="player_wardrobe",
        acquisition_class="COSMETIC",
        duplicate_policy="REJECT_IF_OWNED",
        price=200,
    )

    result = _purchase(conn, operation_id="op-wardrobe", offer=offer)

    assert result.ownership_reference is None
    assert conn.execute(
        "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=1 AND item_id='robe_plain'"
    ).fetchone()[0] == 1


def test_from_payload_preserves_reference_and_rejects_disagreement() -> None:
    conn = _connection()
    result = _purchase(conn, operation_id="op-payload", offer=_offer())
    payload = result.canonical_payload()

    replay = CoinPurchaseResult.from_payload(payload, replayed=True)
    assert replay.ownership_reference == result.ownership_reference

    payload["ownership_result"]["ownership_reference"] = "player_inventory:999"
    with pytest.raises(CoinPurchaseError):
        CoinPurchaseResult.from_payload(payload, replayed=True)


def test_old_non_player_inventory_payload_without_reference_remains_readable() -> None:
    conn = _connection()
    result = _purchase(
        conn,
        operation_id="op-old-shape",
        offer=_offer(
            item_id="hint_ticket",
            destination="shop_inventory",
            acquisition_class="CONSUMABLE",
            duplicate_policy="STACK",
            price=30,
        ),
    )
    payload = result.canonical_payload()
    payload.pop("ownership_reference", None)
    payload["ownership_result"].pop("ownership_reference", None)

    replay = CoinPurchaseResult.from_payload(payload, replayed=True)
    assert replay.ownership_reference is None


def test_c025_normalized_mapping_is_accepted_by_c019_offer_contract() -> None:
    facts = ServerShopOfferFacts.from_mapping(
        {
            "offer_family": "STATIC_SHOP_ITEM",
            "item_key": "hint_ticket",
            "item_id": "hint_ticket",
            "server_price": 30,
            "quantity": 1,
            "currency": "COINS",
            "destination": "shop_inventory",
            "acquisition_class": "CONSUMABLE",
            "duplicate_policy": "STACK",
            "eligibility_reference": "server:shop_items.hint_ticket",
            "price_reference": "server:shop_items.hint_ticket.price",
            "catalog_reference": "server:shop_items",
        }
    )
    normalized = normalize_shop_offer(facts)
    offer = CoinShopOffer.from_mapping(normalized.as_c019_mapping())

    assert offer.offer_id == normalized.offer_id
    assert offer.offer_version == normalized.offer_version
    assert offer.price == normalized.server_price


def test_source_has_no_latest_row_or_duplicate_schema_history() -> None:
    source = Path(__file__).resolve().parents[1] / "coin_purchase_authority.py"
    text = source.read_text(encoding="utf-8")

    assert "MAX(id)" not in text
    assert "ORDER BY id DESC" not in text
    assert "ORDER BY obtained_at DESC" not in text
    assert "SELECT id FROM player_inventory" not in text
    assert "migrations.equipment_canonical_slot_v1" in text
    assert "equipment_canonical_slot_v1.py" not in text
    assert "item_use_operations_v1" not in text
    assert "append_item_use" not in text


def test_c026_schema_does_not_add_an_ownership_reference_column() -> None:
    from migrations.coin_purchase_operations_v1 import COLUMNS

    assert "ownership_reference" not in {column.name for column in COLUMNS}
