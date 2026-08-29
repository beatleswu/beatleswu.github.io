"""C049 appearance commerce route and mutation-authority proof."""

from __future__ import annotations

import sqlite3
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import pytest

import app as app_module
from coin_purchase_authority import AcquisitionFailed
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_purchase_operations
from migrations.domain_event_outbox_v1 import upgrade as upgrade_event_outbox
from test_rpg_r4a_cosmetic_commerce_foundation import (
    _client_for,
    _scalar,
    cosmetic_app,
)


ROOT = Path(__file__).resolve().parents[1]


class _PostgresDbContext:
    def __init__(self, url):
        import psycopg2
        from psycopg2.extras import DictCursor
        from db import PostgresConnectionWrapper

        raw = psycopg2.connect(url)
        raw.cursor_factory = DictCursor
        self.conn = PostgresConnectionWrapper(raw)

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.conn.close()


def _c049_postgres_url():
    url = os.environ.get("C049_APPEARANCE_COMMERCE_POSTGRES_URL")
    if not url or os.environ.get("C049_APPEARANCE_COMMERCE_POSTGRES_DISPOSABLE") != "1":
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if "test" not in database and "c049" not in database:
        pytest.skip("refusing PostgreSQL URL without a test/c049 database name")
    return url


def _create_c049_postgres_schema(url):
    conn = _PostgresDbContext(url).__enter__()
    try:
        for table in (
            "domain_event_outbox",
            "coin_purchase_operations",
            "daily_shop",
            "player_appearance",
            "player_wardrobe",
            "currency_log",
            "user_stats",
            "users",
        ):
            conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        conn.execute(
            "CREATE TABLE users("
            "id INTEGER PRIMARY KEY, plan TEXT NOT NULL DEFAULT 'free', "
            "premium_until TEXT, is_admin INTEGER NOT NULL DEFAULT 0)"
        )
        conn.execute(
            "CREATE TABLE user_stats(user_id INTEGER PRIMARY KEY, coins INTEGER NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE currency_log("
            "id BIGSERIAL PRIMARY KEY, user_id INTEGER NOT NULL, delta INTEGER NOT NULL, "
            "balance_after INTEGER NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE player_wardrobe("
            "id BIGSERIAL PRIMARY KEY, user_id INTEGER NOT NULL, item_id TEXT NOT NULL, "
            "obtained_at TEXT NOT NULL, source TEXT NOT NULL, UNIQUE(user_id,item_id))"
        )
        conn.execute(
            "CREATE TABLE player_appearance("
            "user_id INTEGER PRIMARY KEY, outfit_id TEXT, updated_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE daily_shop(shop_date TEXT PRIMARY KEY, slots TEXT NOT NULL)"
        )
        upgrade_event_outbox(conn)
        upgrade_purchase_operations(conn)
        conn.execute("INSERT INTO users(id,plan) VALUES(1,'free'),(2,'free')")
        conn.execute("INSERT INTO user_stats(user_id,coins) VALUES(1,500),(2,500)")
        conn.commit()
    finally:
        conn.close()


def _drop_c049_postgres_schema(url):
    conn = _PostgresDbContext(url).__enter__()
    try:
        for table in (
            "domain_event_outbox",
            "coin_purchase_operations",
            "daily_shop",
            "player_appearance",
            "player_wardrobe",
            "currency_log",
            "user_stats",
            "users",
        ):
            conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        conn.commit()
    finally:
        conn.close()


def test_coin_cosmetic_purchase_uses_c019_and_replays_canonically(cosmetic_app):
    app, path = cosmetic_app
    client = _client_for(app, 1)
    product_id = "cosmetic.outfit.robe_plain"

    first = client.post(
        "/api/cosmetic-commerce/purchase",
        json={
            "product_id": product_id,
            "purchase_operation_id": "c049-cosmetic-replay",
            "price": 1,
            "coin_cost": 0,
            "expected_price": 999999,
            "owned": True,
            "metadata": {"price": 1},
        },
    )
    replay = client.post(
        "/api/cosmetic-commerce/purchase",
        json={
            "product_id": product_id,
            "purchase_operation_id": "c049-cosmetic-replay",
            "price": 999999,
        },
    )

    assert first.status_code == 200
    first_body = first.get_json()
    assert first_body["status"] == "purchased"
    assert first_body["price_charged"] == 200
    assert first_body["coins_spent"] == 200
    assert first_body["canonical_acquisition_result"]["destination"] == "PLAYER_WARDROBE"
    assert first_body["canonical_acquisition_result"]["ownership_authority"] == "player_wardrobe"
    assert first_body["product"]["ownership"]["owned"] is True

    assert replay.status_code == 200
    replay_body = replay.get_json()
    assert replay_body["replayed"] is True
    assert replay_body["coins_spent"] == 200
    assert replay_body["price_charged"] == 200
    assert _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1") == 300
    assert _scalar(path, "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=1") == 1
    assert _scalar(path, "SELECT COUNT(*) FROM currency_log WHERE user_id=1") == 1
    assert _scalar(
        path,
        "SELECT COUNT(*) FROM coin_purchase_operations "
        "WHERE user_id=1 AND purchase_operation_id='c049-cosmetic-replay'",
    ) == 1

    already_owned = client.post(
        "/api/cosmetic-commerce/purchase",
        json={
            "product_id": product_id,
            "purchase_operation_id": "c049-cosmetic-owned",
            "price": 1,
        },
    )
    assert already_owned.status_code == 200
    assert already_owned.get_json()["status"] == "already_owned"
    assert already_owned.get_json()["granted"] is False
    assert _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1") == 300
    assert _scalar(path, "SELECT COUNT(*) FROM currency_log WHERE user_id=1") == 1
    assert _scalar(
        path,
        "SELECT COUNT(*) FROM coin_purchase_operations "
        "WHERE user_id=1 AND purchase_operation_id='c049-cosmetic-owned'",
    ) == 0


@pytest.mark.parametrize("forged_price", [1, 0, -100, 999999])
def test_forged_cosmetic_price_never_changes_server_debit(cosmetic_app, forged_price):
    app, path = cosmetic_app
    client = _client_for(app, 1)
    response = client.post(
        "/api/cosmetic-commerce/purchase",
        json={
            "product_id": "cosmetic.outfit.robe_plain",
            "purchase_operation_id": f"c049-forged-{forged_price}",
            "price": forged_price,
            "discount": 99,
            "expected_price": forged_price,
        },
    )
    assert response.status_code == 200
    assert response.get_json()["price_charged"] == 200
    assert response.get_json()["coins_spent"] == 200
    assert _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1") == 300


def test_insufficient_cosmetic_coins_roll_back_all_c019_state(cosmetic_app):
    app, path = cosmetic_app
    client = _client_for(app, 2)
    response = client.post(
        "/api/cosmetic-commerce/purchase",
        json={
            "product_id": "cosmetic.outfit.robe_plain",
            "purchase_operation_id": "c049-insufficient-cosmetic",
            "price": 1,
        },
    )
    assert response.status_code == 400
    assert response.get_json() == {
        "error": "insufficient_coins",
        "code": "INSUFFICIENT_COINS",
        "coins": 0,
    }
    assert _scalar(path, "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=2") == 0
    assert _scalar(path, "SELECT COUNT(*) FROM currency_log WHERE user_id=2") == 0
    assert _scalar(path, "SELECT COUNT(*) FROM coin_purchase_operations") == 0


def test_cosmetic_acquisition_failure_rolls_back_debit_wardrobe_and_operation(
    cosmetic_app, monkeypatch
):
    app, path = cosmetic_app
    client = _client_for(app, 1)

    def fail_acquisition(*args, **kwargs):
        raise AcquisitionFailed("forced C049 wardrobe failure")

    monkeypatch.setattr(app.SqlAcquisitionAuthority, "acquire", fail_acquisition)
    response = client.post(
        "/api/cosmetic-commerce/purchase",
        json={
            "product_id": "cosmetic.outfit.robe_plain",
            "purchase_operation_id": "c049-cosmetic-rollback",
        },
    )
    assert response.status_code == 422
    assert response.get_json()["error"] == "acquisition_failed"
    assert _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1") == 500
    assert _scalar(path, "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=1") == 0
    assert _scalar(path, "SELECT COUNT(*) FROM currency_log WHERE user_id=1") == 0
    assert _scalar(path, "SELECT COUNT(*) FROM coin_purchase_operations") == 0


def test_legacy_daily_appearance_route_is_canonical_or_retired_without_fallback(
    cosmetic_app, monkeypatch
):
    app, path = cosmetic_app
    client = _client_for(app, 1)
    monkeypatch.setattr(
        app,
        "_daily_shop_slots",
        lambda conn, persist=True: [{
            "type": "appearance",
            "item_key": "robe_plain",
            "product_id": "cosmetic.outfit.robe_plain",
            "price": 200,
        }],
    )

    canonical = client.post(
        "/api/shop/buy_appearance",
        json={
            "item_id": "robe_plain",
            "purchase_operation_id": "c049-daily-canonical",
            "price": 1,
        },
    )
    assert canonical.status_code == 200
    assert canonical.get_json()["coins_spent"] == 200
    assert _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1") == 300

    daily_duplicate = client.post(
        "/api/shop/buy_appearance",
        json={
            "item_id": "robe_plain",
            "purchase_operation_id": "c049-daily-owned",
            "price": 1,
        },
    )
    assert daily_duplicate.status_code == 200
    assert daily_duplicate.get_json()["status"] == "already_owned"
    assert daily_duplicate.get_json()["granted"] is False
    assert _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1") == 300

    # A valid appearance definition without a canonical C023 product cannot
    # reach the historical direct spend + wardrobe grant fallback.
    retired = client.post(
        "/api/shop/buy_appearance",
        json={
            "item_id": "hat_cloth",
            "purchase_operation_id": "c049-daily-legacy",
            "price": 1,
        },
    )
    assert retired.status_code == 409
    assert retired.get_json() == {
        "error": "shop_offer_unavailable",
        "code": "LEGACY_PURCHASE_RETIRED",
    }
    assert _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1") == 300
    assert _scalar(path, "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=1") == 1


def test_legacy_coin_gacha_appearance_surface_fails_closed_without_mutation(cosmetic_app):
    app, path = cosmetic_app
    client = _client_for(app, 1)

    response = client.post("/api/shop/gacha", json={})

    assert response.status_code == 409
    assert response.get_json() == {
        "error": "shop_offer_unavailable",
        "code": "LEGACY_PURCHASE_RETIRED",
    }
    assert _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1") == 500
    assert _scalar(path, "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=1") == 0
    assert _scalar(path, "SELECT COUNT(*) FROM gacha_log WHERE user_id=1") == 0


def test_appearance_equipment_routes_are_owned_only_and_fail_closed(cosmetic_app):
    app, path = cosmetic_app
    client = _client_for(app, 1)

    malformed = client.post(
        "/api/player/appearance/equip",
        json={"item_id": ["robe_plain"]},
    )
    assert malformed.status_code == 400

    unowned = client.post(
        "/api/cosmetic-commerce/equip",
        json={"product_id": "cosmetic.outfit.robe_plain"},
    )
    assert unowned.status_code == 403
    assert unowned.get_json()["error"] == "not_owned"

    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO player_wardrobe(user_id,item_id,obtained_at,source) "
            "VALUES(1,'robe_plain','2026-08-29T00:00:00','test')"
        )

    equipped = client.post(
        "/api/cosmetic-commerce/equip",
        json={"product_id": "cosmetic.outfit.robe_plain"},
    )
    assert equipped.status_code == 200
    assert _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1") == 500
    assert _scalar(path, "SELECT outfit_id FROM player_appearance WHERE user_id=1") == "robe_plain"

    reloaded = client.get("/api/player/appearance")
    assert reloaded.status_code == 200
    assert any(item["id"] == "robe_plain" and item["is_equipped"] for item in reloaded.get_json()["wardrobe"])


def test_appearance_http_auth_unknown_and_malformed_requests_fail_closed(cosmetic_app):
    app, path = cosmetic_app
    anonymous = app.app.test_client()
    unauthenticated = anonymous.post(
        "/api/cosmetic-commerce/purchase",
        json={
            "product_id": "cosmetic.outfit.robe_plain",
            "purchase_operation_id": "c049-anon",
        },
    )
    assert unauthenticated.status_code == 401

    client = _client_for(app, 1)
    for payload in [
        {"product_id": "cosmetic.unknown", "purchase_operation_id": "c049-unknown"},
        {"product_id": "../robe_plain", "purchase_operation_id": "c049-path"},
    ]:
        response = client.post("/api/cosmetic-commerce/purchase", json=payload)
        assert response.status_code == 400
    malformed = client.post(
        "/api/cosmetic-commerce/purchase",
        json=["cosmetic.outfit.robe_plain"],
    )
    assert malformed.status_code == 400
    assert _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1") == 500


def test_postgres_appearance_purchase_replay_race_and_rollback(monkeypatch):
    url = _c049_postgres_url()
    _create_c049_postgres_schema(url)
    monkeypatch.setattr(app_module, "get_db", lambda: _PostgresDbContext(url))
    app_module.app.config.update(
        TESTING=True,
        PROPAGATE_EXCEPTIONS=False,
        SESSION_COOKIE_SECURE=False,
    )

    def client_for(user_id):
        client = app_module.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = user_id
            session["username"] = f"c049-pg-{user_id}"
        return client

    try:
        catalog = client_for(1).get("/api/cosmetic-commerce/catalog")
        assert catalog.status_code == 200
        assert [product["product_id"] for product in catalog.get_json()["products"]] == [
            "cosmetic.outfit.robe_plain",
            "cosmetic.outfit.robe_bamboo",
            "cosmetic.outfit.robe_premium",
        ]

        first = client_for(1).post(
            "/api/cosmetic-commerce/purchase",
            json={
                "product_id": "cosmetic.outfit.robe_plain",
                "purchase_operation_id": "c049-pg-first",
                "price": 1,
            },
        )
        replay = client_for(1).post(
            "/api/cosmetic-commerce/purchase",
            json={
                "product_id": "cosmetic.outfit.robe_plain",
                "purchase_operation_id": "c049-pg-first",
                "price": 999999,
            },
        )
        assert first.status_code == replay.status_code == 200
        assert replay.get_json()["replayed"] is True

        with _PostgresDbContext(url) as conn:
            assert conn.execute(
                "SELECT coins FROM user_stats WHERE user_id=1"
            ).fetchone()["coins"] == 300
            assert conn.execute(
                "SELECT COUNT(*) AS n FROM player_wardrobe WHERE user_id=1"
            ).fetchone()["n"] == 1
            assert conn.execute(
                "SELECT COUNT(*) AS n FROM coin_purchase_operations "
                "WHERE user_id=1 AND purchase_operation_id='c049-pg-first'"
            ).fetchone()["n"] == 1
            appearance_row = conn.execute(
                "SELECT outfit_id FROM player_appearance WHERE user_id=1"
            ).fetchone()
            assert appearance_row is None or appearance_row["outfit_id"] is None

        reloaded = client_for(1).get("/api/player/appearance")
        assert reloaded.status_code == 200
        assert any(
            item["id"] == "robe_plain" for item in reloaded.get_json()["wardrobe"]
        )

        insufficient = client_for(2).post(
            "/api/cosmetic-commerce/purchase",
            json={
                "product_id": "cosmetic.outfit.robe_plain",
                "purchase_operation_id": "c049-pg-insufficient",
            },
        )
        assert insufficient.status_code == 200
        assert insufficient.get_json()["status"] == "purchased"

        with _PostgresDbContext(url) as conn:
            conn.execute("UPDATE user_stats SET coins=0 WHERE user_id=2")
            conn.commit()
        no_coins = client_for(2).post(
            "/api/cosmetic-commerce/purchase",
            json={
                "product_id": "cosmetic.outfit.robe_bamboo",
                "purchase_operation_id": "c049-pg-no-coins",
            },
        )
        assert no_coins.status_code == 400
        assert no_coins.get_json()["code"] == "INSUFFICIENT_COINS"

        with _PostgresDbContext(url) as conn:
            conn.execute("UPDATE user_stats SET coins=500 WHERE user_id=2")
            conn.commit()

        def submit_duplicate():
            return client_for(2).post(
                "/api/cosmetic-commerce/purchase",
                json={
                    "product_id": "cosmetic.outfit.robe_bamboo",
                    "purchase_operation_id": "c049-pg-race",
                },
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _unused: submit_duplicate(), (1, 2)))
        assert [response.status_code for response in responses] == [200, 200]
        assert sorted(response.get_json()["replayed"] for response in responses) == [False, True]

        original_acquire = app_module.SqlAcquisitionAuthority.acquire

        def fail_acquire(*args, **kwargs):
            raise AcquisitionFailed("forced PostgreSQL acquisition failure")

        with _PostgresDbContext(url) as conn:
            conn.execute("UPDATE user_stats SET coins=500 WHERE user_id=1")
            conn.commit()
        monkeypatch.setattr(app_module.SqlAcquisitionAuthority, "acquire", fail_acquire)
        failed = client_for(1).post(
            "/api/cosmetic-commerce/purchase",
            json={
                "product_id": "cosmetic.outfit.robe_bamboo",
                "purchase_operation_id": "c049-pg-rollback",
            },
        )
        assert failed.status_code == 422
        monkeypatch.setattr(app_module.SqlAcquisitionAuthority, "acquire", original_acquire)

        with _PostgresDbContext(url) as conn:
            assert conn.execute(
                "SELECT coins FROM user_stats WHERE user_id=1"
            ).fetchone()["coins"] == 500
            assert conn.execute(
                "SELECT COUNT(*) AS n FROM player_wardrobe "
                "WHERE user_id=1 AND item_id='robe_bamboo'"
            ).fetchone()["n"] == 0
            assert conn.execute(
                "SELECT COUNT(*) AS n FROM coin_purchase_operations "
                "WHERE user_id=1 AND purchase_operation_id='c049-pg-rollback'"
            ).fetchone()["n"] == 0
    finally:
        _drop_c049_postgres_schema(url)


def test_c049_source_closes_direct_paid_appearance_fallback_and_preserves_boundaries():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    purchase_route = source[source.index("def cosmetic_commerce_purchase():"):source.index("@app.route('/api/cosmetic-commerce/equip'")]
    daily_route = source[source.index("def shop_buy_appearance():"):source.index("# ── 扭蛋")]
    gacha_route = source[source.index("def shop_gacha():"):source.index("@app.route('/api/user/coins')")]
    assert "_purchase_cosmetic" not in source
    assert "_spend_coins" not in purchase_route
    assert "_spend_coins" not in daily_route
    assert "_spend_coins" not in gacha_route
    assert "_grant_shop_purchase" not in daily_route
    assert "LEGACY_PURCHASE_RETIRED" in daily_route
    assert "LEGACY_PURCHASE_RETIRED" in gacha_route
    assert "purchase_with_coins" in source
    assert "_canonical_cosmetic_purchase_response" in purchase_route
    assert "_canonical_shop_purchase_response" in source
    assert "player_wardrobe" in source
    assert "newebpay" not in purchase_route.lower()
    assert "paypal" not in purchase_route.lower()
