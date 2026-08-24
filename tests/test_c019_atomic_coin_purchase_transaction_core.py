from __future__ import annotations

from collections import Counter
import sqlite3
import threading
import time
import uuid

import pytest

from coin_purchase_authority import (
    AcquisitionFailed,
    CoinDebitFailed,
    InsufficientCoins,
    OwnershipAuthorityUnavailable,
    PurchaseOperationConflict,
    SqlAcquisitionAuthority,
    UnknownOffer,
    purchase_with_coins,
)
from migrations.coin_purchase_operations_v1 import (
    TABLE_NAME as PURCHASE_TABLE,
    upgrade as upgrade_purchase_schema,
    validate_schema as validate_purchase_schema,
)
from migrations.domain_event_outbox_v1 import (
    upgrade as upgrade_outbox_schema,
    validate_schema as validate_outbox_schema,
)
from shop_offer_authority import StaticShopOfferAuthority


def _create_runtime(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE user_stats ("
        "user_id INTEGER PRIMARY KEY, coins INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE currency_log ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
        "delta INTEGER NOT NULL, balance_after INTEGER NOT NULL, "
        "reason TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE shop_inventory ("
        "user_id INTEGER NOT NULL, item_key TEXT NOT NULL, "
        "qty INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,item_key))"
    )
    conn.execute(
        "CREATE TABLE player_inventory ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
        "equip_id TEXT NOT NULL, equipped INTEGER NOT NULL DEFAULT 0, "
        "obtained_at TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'drop')"
    )
    conn.execute(
        "CREATE TABLE player_wardrobe ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
        "item_id TEXT NOT NULL, obtained_at TEXT NOT NULL, "
        "source TEXT NOT NULL DEFAULT 'drop', UNIQUE(user_id,item_id))"
    )
    upgrade_outbox_schema(conn)
    upgrade_purchase_schema(conn)
    conn.commit()


@pytest.fixture()
def runtime() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    _create_runtime(conn)
    yield conn
    conn.close()


def _offers() -> StaticShopOfferAuthority:
    return StaticShopOfferAuthority.from_mappings(
        [
            {
                "offer_id": "shop.starfruit.bundle.v1",
                "item_id": "starfruit",
                "quantity": 2,
                "currency": "coins",
                "price": 30,
                "destination": "shop_inventory",
                "acquisition_class": "CONSUMABLE",
                "offer_version": "v1",
                "duplicate_policy": "STACK",
            },
            {
                "offer_id": "shop.moon-drop.bundle.v1",
                "item_id": "moon_drop",
                "quantity": 1,
                "currency": "COINS",
                "price": 40,
                "destination": "shop_inventory",
                "acquisition_class": "CONSUMABLE",
                "offer_version": "v1",
                "duplicate_policy": "STACK",
            },
            {
                "offer_id": "shop.iron-sword.v1",
                "item_id": "iron_sword",
                "quantity": 1,
                "currency": "COINS",
                "price": 50,
                "destination": "player_inventory",
                "acquisition_class": "WEAPON",
                "offer_version": "v1",
                "duplicate_policy": "ALLOW_DUPLICATE",
            },
            {
                "offer_id": "shop.robe-plain.v1",
                "item_id": "robe_plain",
                "quantity": 1,
                "currency": "COINS",
                "price": 45,
                "destination": "player_wardrobe",
                "acquisition_class": "COSMETIC",
                "offer_version": "v1",
                "duplicate_policy": "REJECT_IF_OWNED",
            },
            {
                "offer_id": "shop.disabled-go-stone.v1",
                "item_id": "go_stone_black",
                "quantity": 1,
                "currency": "COINS",
                "price": 5,
                "destination": "player_inventory",
                "acquisition_class": "TROPHY",
                "status": "DISABLED",
                "duplicate_policy": "REJECT_IF_OWNED",
            },
            {
                "offer_id": "shop.xp-amulet.v1",
                "item_id": "xp_amulet",
                "quantity": 1,
                "currency": "COINS",
                "price": 60,
                "destination": "player_inventory",
                "acquisition_class": "ACCESSORY",
                "duplicate_policy": "ALLOW_DUPLICATE",
            },
            {
                "offer_id": "shop.capacity-credit.v1",
                "item_id": "extra_questions_credit",
                "quantity": 1,
                "currency": "COINS",
                "price": 10,
                "destination": "capacity",
                "acquisition_class": "XP_CONSUMABLE",
                "duplicate_policy": "STACK",
            },
        ]
    )


def _seed_user(conn: sqlite3.Connection, *, user_id: int = 1, coins: int = 100) -> None:
    conn.execute("INSERT INTO user_stats(user_id,coins) VALUES(?,?)", (user_id, coins))
    conn.commit()


def _purchase(conn: sqlite3.Connection, *, user_id: int = 1, operation_id: str, offer_id: str, **kwargs):
    try:
        result = purchase_with_coins(
            conn,
            user_id,
            operation_id,
            offer_id,
            offer_authority=_offers(),
            **kwargs,
        )
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def _balance(conn: sqlite3.Connection, user_id: int = 1) -> int:
    return conn.execute(
        "SELECT coins FROM user_stats WHERE user_id=?", (user_id,)
    ).fetchone()["coins"]


def _count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]


def test_schema_is_additive_and_d5a_is_separate(runtime):
    assert validate_purchase_schema(runtime)["missing"] == []
    assert validate_outbox_schema(runtime)["missing"] == []
    columns = {
        row[1] for row in runtime.execute(f"PRAGMA table_info({PURCHASE_TABLE})")
    }
    assert {
        "user_id",
        "purchase_operation_id",
        "offer_id",
        "request_fingerprint",
        "offer_version",
        "currency_type",
        "resolved_price",
        "reward_id",
        "reward_quantity",
        "destination",
        "acquisition_class",
        "operation_status",
        "result_payload",
        "lineage_event_id",
        "created_at",
        "updated_at",
        "committed_at",
    } == columns


def test_successful_purchase_debits_and_acquires_and_records_authoritative_result(runtime):
    _seed_user(runtime)

    result = _purchase(
        runtime,
        operation_id="c019-success-1",
        offer_id="shop.starfruit.bundle.v1",
        client_price=1,
    )

    assert result.replayed is False
    assert result.offer_id == "shop.starfruit.bundle.v1"
    assert result.item_id == "starfruit"
    assert result.quantity == 2
    assert result.coins_before == 100
    assert result.coins_spent == 30
    assert result.coins_after == 70
    assert result.destination == "shop_inventory"
    assert result.can_use is True
    assert runtime.execute(
        "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='starfruit'"
    ).fetchone()["qty"] == 2
    assert runtime.execute(
        "SELECT delta, balance_after FROM currency_log WHERE user_id=1"
    ).fetchone()[:2] == (-30, 70)
    operation = runtime.execute(
        "SELECT offer_id,resolved_price,reward_id,reward_quantity,operation_status "
        "FROM coin_purchase_operations WHERE user_id=1"
    ).fetchone()
    assert tuple(operation) == (
        "shop.starfruit.bundle.v1",
        30,
        "starfruit",
        2,
        "COMMITTED",
    )
    event = runtime.execute(
        "SELECT event_type,idempotency_key FROM domain_event_outbox"
    ).fetchone()
    assert tuple(event) == (
        "ITEM_ACQUISITION",
        "coin-purchase-acquisition:c019-success-1",
    )


def test_same_operation_replay_returns_original_result_without_second_mutation(runtime):
    _seed_user(runtime)
    first = _purchase(
        runtime,
        operation_id="c019-replay-1",
        offer_id="shop.starfruit.bundle.v1",
    )
    second = _purchase(
        runtime,
        operation_id="c019-replay-1",
        offer_id="shop.starfruit.bundle.v1",
        client_price=999999,
    )

    assert second.replayed is True
    assert second.canonical_payload() == first.canonical_payload()
    assert _balance(runtime) == 70
    assert runtime.execute(
        "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='starfruit'"
    ).fetchone()["qty"] == 2
    assert _count(runtime, "currency_log") == 1
    assert _count(runtime, "domain_event_outbox") == 1
    assert _count(runtime, "coin_purchase_operations") == 1


def test_same_operation_different_offer_fails_closed_without_mutation(runtime):
    _seed_user(runtime)
    _purchase(
        runtime,
        operation_id="c019-conflict-1",
        offer_id="shop.starfruit.bundle.v1",
    )

    with pytest.raises(PurchaseOperationConflict) as error:
        _purchase(
            runtime,
            operation_id="c019-conflict-1",
            offer_id="shop.moon-drop.bundle.v1",
        )

    assert error.value.code == "PURCHASE_OPERATION_CONFLICT"
    assert _balance(runtime) == 70
    assert _count(runtime, "currency_log") == 1
    assert _count(runtime, "domain_event_outbox") == 1
    assert runtime.execute(
        "SELECT COUNT(*) AS n FROM shop_inventory WHERE item_key='moon_drop'"
    ).fetchone()["n"] == 0


def test_insufficient_coins_has_no_operation_debit_acquisition_or_lineage(runtime):
    _seed_user(runtime, coins=20)

    with pytest.raises(InsufficientCoins) as error:
        _purchase(
            runtime,
            operation_id="c019-insufficient-1",
            offer_id="shop.starfruit.bundle.v1",
        )

    assert error.value.code == "INSUFFICIENT_COINS"
    assert _balance(runtime) == 20
    assert _count(runtime, "currency_log") == 0
    assert _count(runtime, "domain_event_outbox") == 0
    assert _count(runtime, "coin_purchase_operations") == 0
    assert _count(runtime, "shop_inventory") == 0


def test_unknown_offer_is_fail_closed_and_client_price_cannot_change_server_price(runtime):
    _seed_user(runtime)
    with pytest.raises(UnknownOffer):
        _purchase(
            runtime,
            operation_id="c019-unknown-1",
            offer_id="not-a-server-offer",
            client_price=1,
        )
    assert _balance(runtime) == 100
    assert _count(runtime, "currency_log") == 0
    assert _count(runtime, "coin_purchase_operations") == 0

    result = _purchase(
        runtime,
        operation_id="c019-price-1",
        offer_id="shop.starfruit.bundle.v1",
        client_price=1,
    )
    assert result.coins_spent == 30
    assert _balance(runtime) == 70


class _FailingAcquisition:
    def acquire(self, conn, *, user_id, offer, purchase_operation_id):
        del conn, user_id, offer, purchase_operation_id
        raise RuntimeError("simulated acquisition failure")


def test_acquisition_failure_rolls_back_coin_debit_and_operation(runtime):
    _seed_user(runtime)

    with pytest.raises(AcquisitionFailed) as error:
        _purchase(
            runtime,
            operation_id="c019-acquisition-failure-1",
            offer_id="shop.starfruit.bundle.v1",
            acquisition_authority=_FailingAcquisition(),
        )

    assert error.value.code == "ACQUISITION_FAILED"
    assert _balance(runtime) == 100
    assert _count(runtime, "currency_log") == 0
    assert _count(runtime, "shop_inventory") == 0
    assert _count(runtime, "coin_purchase_operations") == 0
    assert _count(runtime, "domain_event_outbox") == 0


class _RecordingAcquisition:
    def __init__(self):
        self.calls = 0

    def acquire(self, conn, *, user_id, offer, purchase_operation_id):
        del conn, user_id, offer, purchase_operation_id
        self.calls += 1
        raise AssertionError("acquisition must not run after Coin debit failure")


def test_coin_debit_failure_does_not_grant_item(runtime):
    _seed_user(runtime)
    acquisition = _RecordingAcquisition()

    def fail_spend(conn, *, user_id, amount, reason):
        del conn, user_id, amount, reason
        raise CoinDebitFailed("simulated debit failure")

    with pytest.raises(CoinDebitFailed):
        _purchase(
            runtime,
            operation_id="c019-debit-failure-1",
            offer_id="shop.starfruit.bundle.v1",
            acquisition_authority=acquisition,
            spend_coins=fail_spend,
        )

    assert acquisition.calls == 0
    assert _balance(runtime) == 100
    assert _count(runtime, "currency_log") == 0
    assert _count(runtime, "shop_inventory") == 0
    assert _count(runtime, "coin_purchase_operations") == 0


def test_functional_equipment_routes_to_player_inventory_without_consuming_item(runtime):
    _seed_user(runtime)
    result = _purchase(
        runtime,
        operation_id="c019-equipment-1",
        offer_id="shop.iron-sword.v1",
    )

    assert result.destination == "player_inventory"
    assert result.can_equip is True
    assert result.can_use is False
    assert result.can_wear is False
    assert runtime.execute(
        "SELECT equip_id,equipped,source FROM player_inventory WHERE user_id=1"
    ).fetchone()[:3] == ("iron_sword", 0, "coin_shop")
    assert _count(runtime, "shop_inventory") == 0


def test_cosmetic_routes_to_wardrobe_without_combat_capability(runtime):
    _seed_user(runtime)
    result = _purchase(
        runtime,
        operation_id="c019-cosmetic-1",
        offer_id="shop.robe-plain.v1",
    )

    assert result.destination == "player_wardrobe"
    assert result.can_wear is True
    assert result.can_equip is False
    assert result.can_use is False
    assert runtime.execute(
        "SELECT item_id,source FROM player_wardrobe WHERE user_id=1"
    ).fetchone()[:2] == ("robe_plain", "coin_shop")
    assert _count(runtime, "player_inventory") == 0


def test_duplicate_cosmetic_purchase_is_rejected_without_conversion_or_second_debit(runtime):
    _seed_user(runtime)
    _purchase(
        runtime,
        operation_id="c019-cosmetic-duplicate-first",
        offer_id="shop.robe-plain.v1",
    )

    with pytest.raises(AcquisitionFailed):
        _purchase(
            runtime,
            operation_id="c019-cosmetic-duplicate-second",
            offer_id="shop.robe-plain.v1",
        )

    assert _balance(runtime) == 55
    assert _count(runtime, "currency_log") == 1
    assert _count(runtime, "player_wardrobe") == 1
    assert _count(runtime, "coin_purchase_operations") == 1
    assert _count(runtime, "domain_event_outbox") == 1


def test_disabled_trophy_and_authority_hold_are_not_sellable(runtime):
    _seed_user(runtime)
    with pytest.raises(UnknownOffer):
        _purchase(
            runtime,
            operation_id="c019-trophy-1",
            offer_id="shop.disabled-go-stone.v1",
        )
    with pytest.raises(AcquisitionFailed):
        _purchase(
            runtime,
            operation_id="c019-xp-amulet-1",
            offer_id="shop.xp-amulet.v1",
        )
    assert _balance(runtime) == 100
    assert _count(runtime, "currency_log") == 0
    assert _count(runtime, "player_inventory") == 0
    assert _count(runtime, "coin_purchase_operations") == 0


def test_unsupported_destination_fails_closed_without_coin_or_ownership_mutation(runtime):
    _seed_user(runtime)
    with pytest.raises(OwnershipAuthorityUnavailable):
        _purchase(
            runtime,
            operation_id="c019-capacity-1",
            offer_id="shop.capacity-credit.v1",
        )
    assert _balance(runtime) == 100
    assert _count(runtime, "currency_log") == 0
    assert _count(runtime, "coin_purchase_operations") == 0
    assert _count(runtime, "shop_inventory") == 0


def test_d5a_acquisition_is_used_and_d5c_item_use_is_not_used(runtime):
    _seed_user(runtime)
    result = _purchase(
        runtime,
        operation_id="c019-d5a-1",
        offer_id="shop.starfruit.bundle.v1",
    )
    event = runtime.execute(
        "SELECT event_type,payload FROM domain_event_outbox WHERE event_id=?",
        (result.lineage_event_id,),
    ).fetchone()
    assert event["event_type"] == "ITEM_ACQUISITION"
    assert '"source":"SHOP"' in event["payload"]
    assert "ITEM_CONSUME_EFFECT" not in {
        row[0] for row in runtime.execute("SELECT event_type FROM domain_event_outbox")
    }
    assert not runtime.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='item_use_operations'"
    ).fetchone()


def _shared_runtime():
    uri = f"file:c019-{uuid.uuid4().hex}?mode=memory&cache=shared"
    anchor = sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=5)
    _create_runtime(anchor)
    _seed_user(anchor)
    return uri, anchor


def _concurrent_purchase(uri, *, operation_id: str, offer_id: str, barrier, results, errors):
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        barrier.wait(timeout=5)
        for attempt in range(8):
            try:
                conn.execute("BEGIN IMMEDIATE")
                result = purchase_with_coins(
                    conn,
                    1,
                    operation_id,
                    offer_id,
                    offer_authority=_offers(),
                )
                conn.commit()
                results.append(result)
                break
            except sqlite3.OperationalError as exc:
                conn.rollback()
                if "locked" not in str(exc).lower() or attempt == 7:
                    raise
                # SQLite's shared in-memory test database can report a table
                # lock before busy_timeout applies to a competing writer.
                # Retry the whole caller-owned transaction, as a PostgreSQL
                # serialization/deadlock retry would do.
                time.sleep(0.02)
    except Exception as exc:
        conn.rollback()
        errors.append(exc)
    finally:
        conn.close()


def test_concurrent_same_operation_has_one_debit_one_acquisition_and_replay():
    uri, anchor = _shared_runtime()
    try:
        barrier = threading.Barrier(2)
        results = []
        errors = []
        threads = [
            threading.Thread(
                target=_concurrent_purchase,
                kwargs={
                    "uri": uri,
                    "operation_id": "c019-concurrent-same-1",
                    "offer_id": "shop.starfruit.bundle.v1",
                    "barrier": barrier,
                    "results": results,
                    "errors": errors,
                },
            )
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        assert all(not thread.is_alive() for thread in threads)
        assert errors == []
        assert Counter(result.replayed for result in results) == Counter(
            {False: 1, True: 1}
        )
        assert results[0].canonical_payload() == results[1].canonical_payload()
        assert _balance(anchor) == 70
        assert _count(anchor, "currency_log") == 1
        assert _count(anchor, "shop_inventory") == 1
        assert _count(anchor, "domain_event_outbox") == 1
    finally:
        anchor.close()


def test_concurrent_competing_operations_never_go_negative_or_double_grant():
    uri, anchor = _shared_runtime()
    try:
        anchor.execute("UPDATE user_stats SET coins=70 WHERE user_id=1")
        anchor.commit()
        barrier = threading.Barrier(2)
        results = []
        errors = []
        threads = [
            threading.Thread(
                target=_concurrent_purchase,
                kwargs={
                    "uri": uri,
                    "operation_id": f"c019-concurrent-competing-{index}",
                    "offer_id": "shop.iron-sword.v1",
                    "barrier": barrier,
                    "results": results,
                    "errors": errors,
                },
            )
            for index in (1, 2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        assert all(not thread.is_alive() for thread in threads)
        assert len(results) == 1
        assert len(errors) == 1
        assert isinstance(errors[0], InsufficientCoins)
        assert _balance(anchor) == 20
        assert _balance(anchor) >= 0
        assert _count(anchor, "currency_log") == 1
        assert _count(anchor, "player_inventory") == 1
        assert _count(anchor, "coin_purchase_operations") == 1
        assert _count(anchor, "domain_event_outbox") == 1
    finally:
        anchor.close()
