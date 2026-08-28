"""Focused C043-C backend Equipment commerce tests.

These tests use only disposable SQLite databases. They bind the service to
server-fact offer projections, C019's purchase-operation schema, and B040's
ownership writer; no Flask route or feature gate is enabled.
"""

from __future__ import annotations

from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any

import pytest

import equipment_commerce_service as commerce
from coin_purchase_authority import (
    AcquisitionFailed,
    InsufficientCoins,
    PurchaseOperationConflict,
)
from equipment_ownership_service import SUPPORTED_SOURCES
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_purchase_operations
from migrations.domain_event_outbox_v1 import upgrade as upgrade_event_outbox
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_b033
from shop_offer_identity_projection import ServerShopOfferFacts


FIXED_NOW = datetime(2026, 8, 28, 4, 0, tzinfo=timezone.utc)
EQUIPMENT_DEFS = (
    {"id": "iron_sword", "slot": "weapon"},
    {"id": "cloth_robe", "slot": "armor"},
    {"id": "lucky_stone", "slot": "accessory"},
)


def _fact(
    equipment_id: str = "iron_sword",
    *,
    acquisition_class: str = "WEAPON",
    duplicate_policy: str = "REJECT_IF_OWNED",
    price: int = 100,
) -> ServerShopOfferFacts:
    return ServerShopOfferFacts(
        offer_family="STATIC_SHOP_ITEM",
        item_key=equipment_id,
        item_id=equipment_id,
        server_price=price,
        quantity=1,
        destination="player_inventory",
        acquisition_class=acquisition_class,
        duplicate_policy=duplicate_policy,
        eligibility_reference="server:authenticated_shop_player",
        price_reference=f"server:SHOP_ITEMS:{equipment_id}:price",
        catalog_reference="server:SHOP_ITEMS",
    )


def _connection(*, coins: int = 500, path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(
        str(path) if path is not None else ":memory:",
        timeout=10,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
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
        "obtained_at TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'test')"
    )
    upgrade_b033(conn, equipment_defs=EQUIPMENT_DEFS)
    upgrade_purchase_operations(conn)
    upgrade_event_outbox(conn)
    conn.execute("INSERT INTO user_stats(user_id, coins) VALUES(1, ?)", (coins,))
    conn.commit()
    return conn


def _open_existing(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _purchase(
    conn: sqlite3.Connection,
    *,
    operation_id: str,
    equipment_id: str = "iron_sword",
    price: int = 100,
    duplicate_policy: str = "REJECT_IF_OWNED",
    catalog_authority: Any = None,
):
    authority = catalog_authority or commerce.ServerFactEquipmentOfferAuthority(
        [_fact(equipment_id, price=price, duplicate_policy=duplicate_policy)]
    )
    return commerce.purchase_equipment_with_coins(
        conn,
        1,
        operation_id,
        equipment_id,
        catalog_authority=authority,
        equipment_defs=EQUIPMENT_DEFS,
        now=FIXED_NOW,
    )


def _coins(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0])


def _inventory(conn: sqlite3.Connection):
    return conn.execute(
        "SELECT id, equip_id, equipped, canonical_slot, source "
        "FROM player_inventory ORDER BY id"
    ).fetchall()


def test_success_uses_server_price_b040_and_never_equips() -> None:
    conn = _connection()
    try:
        result = _purchase(conn, operation_id="c043-success", price=125)
        conn.commit()

        rows = _inventory(conn)
        assert len(rows) == 1
        assert tuple(rows[0][1:]) == ("iron_sword", 0, "weapon", "coin_shop")
        assert result.coins_spent == 125
        assert result.coins_after == 375
        assert result.ownership_reference == f"player_inventory:{rows[0][0]}"
        assert result.ownership_result["ownership_state"] == "EQUIPMENT_OWNED"
        assert result.ownership_result["can_equip"] is True
        assert _coins(conn) == 375
        assert conn.execute(
            "SELECT COUNT(*) FROM currency_log WHERE delta < 0"
        ).fetchone()[0] == 1
        assert "coin_shop" in SUPPORTED_SOURCES
    finally:
        conn.close()


def test_committed_purchase_survives_close_and_reload(tmp_path: Path) -> None:
    path = tmp_path / "c043-reload.sqlite"
    conn = _connection(path=path)
    try:
        result = _purchase(conn, operation_id="c043-reload")
        conn.commit()
        ownership_reference = result.ownership_reference
    finally:
        conn.close()

    reloaded = _open_existing(path)
    try:
        row = reloaded.execute(
            "SELECT coins FROM user_stats WHERE user_id=1"
        ).fetchone()
        assert row[0] == 400
        inventory = reloaded.execute(
            "SELECT id, equip_id, equipped, source FROM player_inventory"
        ).fetchone()
        assert tuple(inventory) == (1, "iron_sword", 0, "coin_shop")
        operation = reloaded.execute(
            "SELECT operation_status, result_payload FROM coin_purchase_operations "
            "WHERE user_id=1 AND purchase_operation_id=?",
            ("c043-reload",),
        ).fetchone()
        assert operation[0] == "COMMITTED"
        assert json.loads(operation[1])["ownership_reference"] == ownership_reference
    finally:
        reloaded.close()


@pytest.mark.parametrize(
    ("user_id", "operation_id", "equipment_id"),
    [
        (True, "c043-invalid-user", "iron_sword"),
        (1, "", "iron_sword"),
        (1, "c043-invalid-equipment", "Iron Sword"),
    ],
)
def test_request_validation_happens_before_any_mutation(
    user_id: Any, operation_id: Any, equipment_id: Any
) -> None:
    conn = _connection()
    try:
        with pytest.raises(commerce.EquipmentPurchaseValidationError):
            commerce.purchase_equipment_with_coins(
                conn,
                user_id,
                operation_id,
                equipment_id,
                catalog_authority=commerce.ServerFactEquipmentOfferAuthority(
                    [_fact()]
                ),
                equipment_defs=EQUIPMENT_DEFS,
            )
        assert _coins(conn) == 500
        assert _inventory(conn) == []
        assert conn.execute(
            "SELECT COUNT(*) FROM coin_purchase_operations"
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_client_price_fields_are_not_accepted_as_server_facts() -> None:
    with pytest.raises(commerce.EquipmentOfferInvalid):
        commerce.ServerFactEquipmentOfferAuthority(
            [{**_fact().__dict__, "price": 1}]
        )
    assert "client_price" not in inspect.signature(
        commerce.purchase_equipment_with_coins
    ).parameters


def test_insufficient_coins_rolls_back_operation_debit_and_inventory() -> None:
    conn = _connection(coins=50)
    try:
        with pytest.raises(InsufficientCoins) as error:
            _purchase(conn, operation_id="c043-poor", price=100)
        assert error.value.balance == 50
        conn.rollback()
        assert _coins(conn) == 50
        assert _inventory(conn) == []
        assert conn.execute(
            "SELECT COUNT(*) FROM currency_log WHERE delta < 0"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM coin_purchase_operations"
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_lineage_failure_rolls_back_debit_operation_and_ownership() -> None:
    conn = _connection()
    try:
        def fail_lineage(*args: Any, **kwargs: Any):
            raise RuntimeError("forced lineage failure")

        with pytest.raises(AcquisitionFailed):
            commerce.purchase_equipment_with_coins(
                conn,
                1,
                "c043-lineage-failure",
                "iron_sword",
                catalog_authority=commerce.ServerFactEquipmentOfferAuthority(
                    [_fact()]
                ),
                equipment_defs=EQUIPMENT_DEFS,
                lineage_writer=fail_lineage,
                now=FIXED_NOW,
            )
        conn.rollback()
        assert _coins(conn) == 500
        assert _inventory(conn) == []
        assert conn.execute(
            "SELECT COUNT(*) FROM coin_purchase_operations"
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_already_owned_rejects_without_second_debit_or_operation() -> None:
    conn = _connection()
    try:
        first = _purchase(conn, operation_id="c043-owned-a")
        conn.commit()
        with pytest.raises(commerce.EquipmentAlreadyOwned) as error:
            _purchase(conn, operation_id="c043-owned-b")
        assert error.value.code == "EQUIPMENT_ALREADY_OWNED"
        conn.rollback()

        assert first.ownership_reference == "player_inventory:1"
        assert len(_inventory(conn)) == 1
        assert _coins(conn) == 400
        assert conn.execute(
            "SELECT COUNT(*) FROM currency_log WHERE delta < 0"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM coin_purchase_operations"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_allow_duplicate_creates_distinct_unequipped_rows() -> None:
    conn = _connection()
    try:
        first = _purchase(
            conn,
            operation_id="c043-duplicate-a",
            duplicate_policy="ALLOW_DUPLICATE",
        )
        conn.commit()
        second = _purchase(
            conn,
            operation_id="c043-duplicate-b",
            duplicate_policy="ALLOW_DUPLICATE",
        )
        conn.commit()

        assert first.ownership_reference != second.ownership_reference
        assert [row[2] for row in _inventory(conn)] == [0, 0]
        assert _coins(conn) == 300
    finally:
        conn.close()


def test_retry_replays_c019_result_without_consulting_refreshed_catalog() -> None:
    conn = _connection()
    try:
        first = _purchase(conn, operation_id="c043-retry")
        conn.commit()

        class CatalogMustNotBeConsulted:
            def resolve(self, equipment_id: str):
                raise AssertionError("committed retry consulted the catalog")

        replay = _purchase(
            conn,
            operation_id="c043-retry",
            catalog_authority=CatalogMustNotBeConsulted(),
        )
        assert replay.replayed is True
        assert replay.ownership_reference == first.ownership_reference
        assert _coins(conn) == 400
        assert len(_inventory(conn)) == 1
    finally:
        conn.close()


def test_same_operation_id_bound_to_another_equipment_conflicts_before_catalog() -> None:
    conn = _connection()
    try:
        _purchase(conn, operation_id="c043-conflict", equipment_id="iron_sword")
        conn.commit()

        class CatalogMustNotBeConsulted:
            def resolve(self, equipment_id: str):
                raise AssertionError("operation conflict consulted the catalog")

        with pytest.raises(PurchaseOperationConflict):
            _purchase(
                conn,
                operation_id="c043-conflict",
                equipment_id="cloth_robe",
                catalog_authority=CatalogMustNotBeConsulted(),
            )
        assert _coins(conn) == 400
        assert len(_inventory(conn)) == 1
    finally:
        conn.close()


def test_concurrent_same_operation_id_has_one_commit_and_one_replay(tmp_path: Path) -> None:
    path = tmp_path / "c043-concurrent.sqlite"
    setup = _connection(path=path)
    setup.close()
    results: list[Any] = []
    errors: list[BaseException] = []
    start = threading.Barrier(2)

    def run() -> None:
        conn = _open_existing(path)
        try:
            start.wait(timeout=5)
            result = _purchase(conn, operation_id="c043-concurrent")
            conn.commit()
            results.append(result)
        except BaseException as error:  # pragma: no cover - diagnostic assertion below
            errors.append(error)
            conn.rollback()
        finally:
            conn.close()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert not errors
    assert len(results) == 2
    assert sorted(result.replayed for result in results) == [False, True]

    verify = sqlite3.connect(str(path))
    try:
        assert verify.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 400
        assert verify.execute("SELECT COUNT(*) FROM player_inventory").fetchone()[0] == 1
        assert verify.execute(
            "SELECT COUNT(*) FROM currency_log WHERE delta < 0"
        ).fetchone()[0] == 1
        assert verify.execute(
            "SELECT COUNT(*) FROM coin_purchase_operations"
        ).fetchone()[0] == 1
    finally:
        verify.close()


def test_module_is_purchase_only_and_does_not_enable_runtime_gates() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "equipment_commerce_service.py"
    ).read_text(encoding="utf-8")
    assert "import app" not in source
    assert "equipment_loadout_service" not in source
    assert "equip_owned_item" not in source
    assert "equipped=1" not in source
    assert "os.environ" not in source
    assert "upgrade_purchase_operations" not in source
    assert "SHOP_ENABLED" not in source
    assert "LOADOUT_ENABLED" not in source
