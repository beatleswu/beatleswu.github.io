"""SHOP-B proofs for canonical R1 consumable acquisition.

These tests exercise the caller-owned C019 transaction directly.  The Flask
use-path checks use only disposable SQLite files; the optional PostgreSQL race
uses an explicitly marked disposable database and never touches Production.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
import sqlite3
import threading
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from coin_purchase_authority import (
    AcquisitionFailed,
    BundleAcquisitionFacts,
    BundleGrantFact,
    InsufficientCoins,
    OwnershipAuthorityUnavailable,
    PurchaseOperationConflict,
    SqlAcquisitionAuthority,
    bind_bundle_acquisition_facts,
    canonical_bundle_acquisition_facts,
    purchase_with_coins,
)
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_purchase_operations
from migrations.domain_event_outbox_v1 import upgrade as upgrade_event_outbox
from migrations.item_use_operations_v1 import upgrade as upgrade_item_use_operations
from migrations.question_capacity_lineage_v1 import upgrade as upgrade_capacity_lineage
from shop_offer_authority import CoinShopOffer, StaticShopOfferAuthority


FIXED_NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
EFFECT_SKUS = (
    "small_xp_potion",
    "streak_shield",
    "extra_questions_small",
    "extra_questions",
    "xp_potion",
    "double_streak_shield",
)
EFFECT_PRICES = {
    "small_xp_potion": 70,
    "streak_shield": 80,
    "extra_questions_small": 60,
    "extra_questions": 100,
    "xp_potion": 120,
    "double_streak_shield": 150,
}
USE_EXPECTATIONS = {
    "small_xp_potion": ("xp_potion", 1.25, "item-use"),
    "streak_shield": ("streak_shield", 1, None),
    "extra_questions_small": ("extra_questions", 5, "capacity"),
    "extra_questions": ("extra_questions", 10, "capacity"),
    "xp_potion": ("xp_potion", 1.5, "item-use"),
    "double_streak_shield": ("streak_shield", 2, None),
}


def _connection(*, coins: int = 5000, include_pet: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE user_stats(
            user_id INTEGER PRIMARY KEY,
            coins INTEGER NOT NULL
        );
        CREATE TABLE currency_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            delta INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE shop_inventory(
            user_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            qty INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, item_key)
        );
        CREATE TABLE active_effects(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            effect_key TEXT NOT NULL,
            value REAL NOT NULL DEFAULT 1,
            expires_at TEXT,
            effect_date TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    if include_pet:
        conn.execute(
            """CREATE TABLE pet_inventory(
                   user_id INTEGER NOT NULL,
                   item_key TEXT NOT NULL,
                   qty INTEGER NOT NULL DEFAULT 0,
                   PRIMARY KEY(user_id, item_key))"""
        )
    upgrade_purchase_operations(conn)
    upgrade_event_outbox(conn)
    conn.execute("INSERT INTO user_stats(user_id,coins) VALUES(1,?)", (coins,))
    conn.commit()
    return conn


def _file_connection(path: Path, *, coins: int = 5000) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE user_stats(
                user_id INTEGER PRIMARY KEY,
                coins INTEGER NOT NULL
            );
            CREATE TABLE currency_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE shop_inventory(
                user_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                qty INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(user_id, item_key)
            );
            CREATE TABLE pet_inventory(
                user_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                qty INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(user_id, item_key)
            );
            """
        )
        upgrade_purchase_operations(conn)
        upgrade_event_outbox(conn)
        conn.execute("INSERT INTO user_stats(user_id,coins) VALUES(1,?)", (coins,))


def _offer(
    item_id: str,
    *,
    price: int = 50,
    offer_id: str | None = None,
    offer_type: str = "ITEM",
    eligibility_metadata: dict | None = None,
) -> CoinShopOffer:
    return CoinShopOffer(
        offer_id=offer_id or f"shop.static.{item_id}",
        item_id=item_id,
        quantity=1,
        currency_type="COINS",
        price=price,
        destination="shop_inventory",
        acquisition_class="CONSUMABLE",
        offer_type=offer_type,
        offer_version="shop-b-r1-v1",
        status="ACTIVE",
        duplicate_policy="STACK",
        eligibility_metadata=eligibility_metadata or {},
    )


def _bound_bundle(item_id: str, *, price: int) -> CoinShopOffer:
    base = _offer(item_id, price=price)
    return bind_bundle_acquisition_facts(
        base,
        canonical_bundle_acquisition_facts(item_id),
    )


def _purchase(
    conn,
    offer: CoinShopOffer,
    operation_id: str,
    *,
    acquisition: SqlAcquisitionAuthority | None = None,
    client_price=None,
):
    return purchase_with_coins(
        conn,
        1,
        operation_id,
        offer.offer_id,
        offer_authority=StaticShopOfferAuthority({offer.offer_id: offer}),
        acquisition_authority=acquisition or SqlAcquisitionAuthority(),
        client_price=client_price,
        now=FIXED_NOW,
    )


def _rollback(conn) -> None:
    conn.rollback()


@pytest.mark.parametrize("item_id", EFFECT_SKUS)
def test_effect_purchase_reuses_stack_acquisition_and_never_writes_active_effects(item_id):
    conn = _connection()
    try:
        conn.execute(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(1,?,2)",
            (item_id,),
        )
        result = _purchase(
            conn,
            _offer(item_id, price=EFFECT_PRICES[item_id]),
            f"effect-{item_id}",
            client_price=1,
        )
        conn.commit()
        row = conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key=?",
            (item_id,),
        ).fetchone()
        assert row["qty"] == 3
        assert result.ownership_result["ownership_state"] == "QUANTITY_OWNED"
        assert result.ownership_result["can_use"] is True
        assert conn.execute("SELECT COUNT(*) FROM active_effects").fetchone()[0] == 0
        assert result.coins_spent == EFFECT_PRICES[item_id]
    finally:
        conn.close()


@pytest.mark.parametrize("item_id", EFFECT_SKUS)
def test_effect_purchase_then_existing_shop_use_activates_only_on_use(tmp_path, monkeypatch, item_id):
    path = tmp_path / f"use-{item_id}.sqlite"
    _create_use_db(path)
    offer = _offer(item_id, price=EFFECT_PRICES[item_id])
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        _purchase(conn, offer, f"purchase-{item_id}")
        conn.commit()
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key=?",
            (item_id,),
        ).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM active_effects").fetchone()[0] == 0

    import app as app_module

    monkeypatch.setattr(app_module, "get_db", lambda: _UseDbContext(path))
    app_module.app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
    expected_effect, expected_value, operation_kind = USE_EXPECTATIONS[item_id]
    payload = {"item_key": item_id}
    if operation_kind in {"item-use", "capacity"}:
        payload["operation_id"] = f"use-{item_id}"
    response = client.post("/api/shop/use", json=payload)
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["effect"] == expected_effect
    assert body["value"] == expected_value
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key=?",
            (item_id,),
        ).fetchone()[0] == 0
        effect = conn.execute(
            "SELECT effect_key,value FROM active_effects WHERE user_id=1"
        ).fetchone()
        assert effect is not None
        assert effect[0] == expected_effect
        assert effect[1] == expected_value


@pytest.mark.parametrize(
    ("item_id", "price"),
    (("hint_ticket", 30), ("ai_explain_ticket", 50)),
)
def test_r1_direct_consumables_use_the_same_stack_acquisition(item_id, price):
    conn = _connection()
    try:
        result = _purchase(conn, _offer(item_id, price=price), f"direct-{item_id}")
        conn.commit()
        assert result.coins_spent == price
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key=?",
            (item_id,),
        ).fetchone()[0] == 1
        assert result.ownership_result["ownership_state"] == "QUANTITY_OWNED"
    finally:
        conn.close()


def test_premium_hint_bundle_grants_exact_hint_stack_and_no_bundle_row():
    conn = _connection()
    try:
        result = _purchase(
            conn,
            _bound_bundle("premium_hint_bundle", price=130),
            "premium-hint-1",
        )
        conn.commit()
        grant = result.ownership_result["presentation_metadata"]["bundle_grants"]
        assert [(entry["item_id"], entry["quantity"], entry["destination"])
                for entry in grant] == [("hint_ticket", 5, "shop_inventory")]
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='hint_ticket'"
        ).fetchone()[0] == 5
        assert conn.execute(
            "SELECT COUNT(*) FROM shop_inventory WHERE item_key='premium_hint_bundle'"
        ).fetchone()[0] == 0
        assert result.ownership_result["ownership_state"] == "BUNDLE_GRANTED"
        operation_payload = conn.execute(
            "SELECT result_payload FROM coin_purchase_operations "
            "WHERE user_id=1 AND purchase_operation_id='premium-hint-1'"
        ).fetchone()[0]
        persisted = json.loads(operation_payload)
        assert persisted["ownership_result"]["presentation_metadata"]["bundle_grants"] == grant
        lineage_payload = conn.execute(
            "SELECT payload FROM domain_event_outbox "
            "WHERE event_type='ITEM_ACQUISITION'"
        ).fetchone()[0]
        assert json.loads(lineage_payload)["ownership_result"]["presentation_metadata"]["bundle_grants"] == grant
    finally:
        conn.close()


def test_pet_snack_grants_exact_go_spirit_candy_to_existing_pet_inventory():
    conn = _connection()
    try:
        result = _purchase(conn, _bound_bundle("pet_snack", price=60), "pet-snack-1")
        conn.commit()
        grant = result.ownership_result["presentation_metadata"]["bundle_grants"]
        assert [(entry["item_id"], entry["quantity"], entry["destination"])
                for entry in grant] == [("go_spirit_candy", 3, "pet_inventory")]
        assert conn.execute(
            "SELECT qty FROM pet_inventory WHERE user_id=1 AND item_key='go_spirit_candy'"
        ).fetchone()[0] == 3
        assert conn.execute(
            "SELECT COUNT(*) FROM shop_inventory WHERE item_key='pet_snack'"
        ).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM active_effects").fetchone()[0] == 0
    finally:
        conn.close()


class _FailingSecondBundleGrant(SqlAcquisitionAuthority):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def _acquire_bundle_grant(self, conn, *, user_id, parent_offer, grant):
        self.calls += 1
        if self.calls == 2:
            raise AcquisitionFailed("forced partial-bundle failure")
        return super()._acquire_bundle_grant(
            conn,
            user_id=user_id,
            parent_offer=parent_offer,
            grant=grant,
        )


def test_partial_bundle_failure_rolls_back_coin_and_every_prior_child_grant():
    conn = _connection()
    facts = BundleAcquisitionFacts(
        (
            BundleGrantFact(
                item_id="hint_ticket",
                quantity=5,
                destination="shop_inventory",
                acquisition_class="CONSUMABLE",
            ),
            BundleGrantFact(
                item_id="go_spirit_candy",
                quantity=3,
                destination="pet_inventory",
                acquisition_class="SPIRIT_CONSUMABLE",
            ),
        )
    )
    offer = bind_bundle_acquisition_facts(_offer("test_partial_bundle", price=125), facts)
    try:
        with pytest.raises(AcquisitionFailed, match="forced partial-bundle failure"):
            _purchase(
                conn,
                offer,
                "partial-bundle-1",
                acquisition=_FailingSecondBundleGrant(),
            )
        conn.rollback()
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 5000
        assert conn.execute("SELECT COUNT(*) FROM currency_log").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM shop_inventory").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM pet_inventory").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM coin_purchase_operations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM domain_event_outbox").fetchone()[0] == 0
    finally:
        conn.close()


def test_response_loss_replay_is_exact_and_does_not_duplicate_bundle_grants():
    conn = _connection()
    offer = _bound_bundle("premium_hint_bundle", price=130)
    try:
        first = _purchase(conn, offer, "bundle-replay-1", client_price=1)
        conn.commit()
        replay = _purchase(conn, offer, "bundle-replay-1", client_price=999999)
        assert replay.replayed is True
        assert replay.coins_spent == first.coins_spent == 130
        assert replay.lineage_event_id == first.lineage_event_id
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='hint_ticket'"
        ).fetchone()[0] == 5
        assert conn.execute(
            "SELECT coins FROM user_stats WHERE user_id=1"
        ).fetchone()[0] == 4870
        assert conn.execute(
            "SELECT COUNT(*) FROM currency_log WHERE delta<0"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_same_operation_different_offer_fails_closed_without_second_mutation():
    conn = _connection()
    first_offer = _offer("hint_ticket", price=30)
    second_offer = _offer("ai_explain_ticket", price=50)
    try:
        _purchase(conn, first_offer, "offer-conflict-1")
        conn.commit()
        with pytest.raises(PurchaseOperationConflict):
            _purchase(conn, second_offer, "offer-conflict-1")
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 4970
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='hint_ticket'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM shop_inventory WHERE item_key='ai_explain_ticket'"
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_broken_bundle_identity_fails_closed_without_legacy_fallback():
    conn = _connection()
    broken = _offer("premium_hint_bundle", price=130, offer_type="BUNDLE")
    try:
        with pytest.raises(AcquisitionFailed):
            _purchase(conn, broken, "broken-bundle-1")
        conn.rollback()
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 5000
        assert conn.execute("SELECT COUNT(*) FROM coin_purchase_operations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM currency_log").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM shop_inventory").fetchone()[0] == 0
    finally:
        conn.close()


def test_pet_grant_schema_failure_rolls_back_instead_of_falling_back_to_shop_inventory():
    conn = _connection(include_pet=False)
    try:
        with pytest.raises(OwnershipAuthorityUnavailable):
            _purchase(conn, _bound_bundle("pet_snack", price=60), "pet-schema-1")
        conn.rollback()
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 5000
        assert conn.execute("SELECT COUNT(*) FROM shop_inventory").fetchone()[0] == 0
    finally:
        conn.close()


def test_insufficient_coins_is_atomic_and_client_price_cannot_change_server_price():
    conn = _connection(coins=10)
    try:
        with pytest.raises(InsufficientCoins):
            _purchase(conn, _offer("hint_ticket", price=30), "insufficient-1", client_price=1)
        conn.rollback()
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 10
        assert conn.execute("SELECT COUNT(*) FROM shop_inventory").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM currency_log").fetchone()[0] == 0
    finally:
        conn.close()


def test_server_price_authority_is_used_for_successful_purchase():
    conn = _connection(coins=100)
    try:
        result = _purchase(
            conn,
            _offer("hint_ticket", price=30),
            "price-authority-1",
            client_price=1,
        )
        conn.commit()
        assert result.coins_spent == 30
        assert result.coins_after == 70
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 70
    finally:
        conn.close()


def test_sqlite_concurrent_duplicate_has_one_debit_and_one_bundle_grant(tmp_path):
    path = tmp_path / "concurrent.sqlite"
    _file_connection(path)
    offer = _bound_bundle("premium_hint_bundle", price=130)
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker():
        conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            barrier.wait(timeout=15)
            result = _purchase(conn, offer, "concurrent-bundle-1")
            conn.commit()
            results.append(result)
        except Exception as exc:  # pragma: no cover - assertion reports the race
            errors.append(exc)
            conn.rollback()
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(worker) for _ in range(2)]
        for future in futures:
            future.result(timeout=45)
    assert not errors
    assert len(results) == 2
    assert sorted(result.replayed for result in results) == [False, True]
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 4870
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='hint_ticket'"
        ).fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM currency_log WHERE delta<0").fetchone()[0] == 1


class _UseDbContext:
    def __init__(self, path: Path):
        self.path = path
        self.conn = None

    def __enter__(self):
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.conn.close()


def _create_use_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE user_stats(
                user_id INTEGER PRIMARY KEY,
                coins INTEGER NOT NULL,
                xp INTEGER NOT NULL DEFAULT 0,
                rank_level INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE currency_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE shop_inventory(
                user_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                qty INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(user_id,item_key)
            );
            CREATE TABLE active_effects(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                effect_key TEXT NOT NULL,
                value REAL NOT NULL DEFAULT 1,
                expires_at TEXT,
                effect_date TEXT,
                created_at TEXT NOT NULL,
                operation_id TEXT,
                source_item_key TEXT
            );
            """
        )
        upgrade_purchase_operations(conn)
        upgrade_event_outbox(conn)
        upgrade_item_use_operations(conn)
        upgrade_capacity_lineage(conn)
        conn.execute(
            "INSERT INTO user_stats(user_id,coins) VALUES(1,5000)"
        )


def _postgres_url():
    url = os.environ.get("D5B_OUTBOX_POSTGRES_URL")
    if not url or os.environ.get("D5B_OUTBOX_POSTGRES_DISPOSABLE") != "1":
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if "test" not in database and "d5b" not in database:
        pytest.skip("refusing PostgreSQL URL without a test/d5b database name")
    return url


def _postgres_connection(url):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


def test_postgres_concurrent_duplicate_has_one_debit_and_one_bundle_grant():
    url = _postgres_url()
    setup = _postgres_connection(url)
    try:
        setup.execute("DROP TABLE IF EXISTS domain_event_outbox CASCADE")
        setup.execute("DROP TABLE IF EXISTS coin_purchase_operations CASCADE")
        setup.execute("DROP TABLE IF EXISTS pet_inventory CASCADE")
        setup.execute("DROP TABLE IF EXISTS shop_inventory CASCADE")
        setup.execute("DROP TABLE IF EXISTS currency_log CASCADE")
        setup.execute("DROP TABLE IF EXISTS user_stats CASCADE")
        setup.execute(
            "CREATE TABLE user_stats(user_id INTEGER PRIMARY KEY, coins INTEGER NOT NULL)"
        )
        setup.execute(
            "CREATE TABLE currency_log(id BIGSERIAL PRIMARY KEY, user_id INTEGER NOT NULL, "
            "delta INTEGER NOT NULL, balance_after INTEGER NOT NULL, reason TEXT NOT NULL, "
            "created_at TIMESTAMPTZ NOT NULL)"
        )
        setup.execute(
            "CREATE TABLE shop_inventory(user_id INTEGER NOT NULL, item_key TEXT NOT NULL, "
            "qty INTEGER NOT NULL, PRIMARY KEY(user_id,item_key))"
        )
        setup.execute(
            "CREATE TABLE pet_inventory(user_id INTEGER NOT NULL, item_key TEXT NOT NULL, "
            "qty INTEGER NOT NULL, PRIMARY KEY(user_id,item_key))"
        )
        upgrade_purchase_operations(setup)
        upgrade_event_outbox(setup)
        setup.execute("INSERT INTO user_stats(user_id,coins) VALUES(1,5000)")
        setup.commit()
    finally:
        setup.close()

    offer = _bound_bundle("premium_hint_bundle", price=130)
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker():
        conn = _postgres_connection(url)
        try:
            barrier.wait(timeout=15)
            result = _purchase(conn, offer, "pg-concurrent-bundle-1")
            conn.commit()
            results.append(result)
        except Exception as exc:  # pragma: no cover - assertion reports PG race
            errors.append(exc)
            conn.rollback()
        finally:
            conn.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker) for _ in range(2)]
            for future in futures:
                future.result(timeout=45)
        assert not errors
        assert len(results) == 2
        assert sorted(result.replayed for result in results) == [False, True]
        verify = _postgres_connection(url)
        try:
            assert verify.execute(
                "SELECT coins FROM user_stats WHERE user_id=1"
            ).fetchone()["coins"] == 4870
            assert verify.execute(
                "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='hint_ticket'"
            ).fetchone()["qty"] == 5
            assert verify.execute(
                "SELECT COUNT(*) AS n FROM currency_log WHERE delta<0"
            ).fetchone()["n"] == 1
        finally:
            verify.close()
    finally:
        cleanup = _postgres_connection(url)
        try:
            cleanup.execute("DROP TABLE IF EXISTS domain_event_outbox CASCADE")
            cleanup.execute("DROP TABLE IF EXISTS coin_purchase_operations CASCADE")
            cleanup.execute("DROP TABLE IF EXISTS pet_inventory CASCADE")
            cleanup.execute("DROP TABLE IF EXISTS shop_inventory CASCADE")
            cleanup.execute("DROP TABLE IF EXISTS currency_log CASCADE")
            cleanup.execute("DROP TABLE IF EXISTS user_stats CASCADE")
            cleanup.commit()
        finally:
            cleanup.close()


__all__ = ["EFFECT_SKUS"]
