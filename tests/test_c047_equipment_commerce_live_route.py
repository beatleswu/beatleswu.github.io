"""C047 authenticated HTTP proof for the Equipment Coins Shop route."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

# Keep the real app import on a synthetic test key.  The protected
# repository secret file is never used by this suite.
os.environ.setdefault("SECRET_KEY", "c047-route-test-secret")

import app as app_module
import equipment_commerce_service
from test_e030_shop_coin_purchase_and_equipment_runtime_integration import (
    _client,
    _coins,
    _create_db,
    _inventory,
)


APPROVED_OFFERS = {
    "wooden_sword": 300,
    "cloth_robe": 300,
    "lucky_stone": 400,
}
UNAUTHORIZED_IDS = (
    "iron_sword",
    "xp_amulet",
    "go_stone_black",
    "../wooden_sword",
)


def _route_fixture(tmp_path, monkeypatch, *, coins: int = 1000):
    path = tmp_path / "c047-route.sqlite"
    _create_db(
        path,
        post_b033=True,
        purchase_schema=True,
        include_wardrobe=True,
        coins=coins,
    )
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, plan TEXT, premium_until TEXT)"
        )
        conn.execute(
            "INSERT INTO users(id, plan, premium_until) VALUES(1, 'free', NULL)"
        )
        conn.execute(
            "CREATE TABLE gacha_log ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
            "pool TEXT NOT NULL, result_key TEXT NOT NULL, result_type TEXT NOT NULL, "
            "rarity TEXT, pity_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)"
        )
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    return path, _client(path, monkeypatch)


def test_catalog_route_returns_exact_server_owned_equipment_offers_and_ownership(
    tmp_path, monkeypatch
):
    path, client = _route_fixture(tmp_path, monkeypatch)

    response = client.get("/api/shop/catalog")

    assert response.status_code == 200
    body = response.get_json()
    offers = body["equipment_offers"]
    assert [offer["item_id"] for offer in offers] == list(APPROVED_OFFERS)
    assert [offer["price"] for offer in offers] == list(APPROVED_OFFERS.values())
    assert all(offer["currency_type"] == "COINS" for offer in offers)
    assert all(offer["destination"] == "player_inventory" for offer in offers)
    assert all(offer["duplicate_policy"] == "REJECT_IF_OWNED" for offer in offers)
    assert body["equipment_ownership"] == {
        item_id: {"owned_quantity": 0, "ownership_state": "NOT_OWNED"}
        for item_id in APPROVED_OFFERS
    }
    assert {offer["item_id"] for offer in offers}.isdisjoint(
        set(UNAUTHORIZED_IDS) | {"leather_armor", "fox_fang", "fox_pelt"}
    )
    assert _coins(path) == 1000

    # The consumer reads server equipment_offers; it has no fallback product
    # or price table for the approved item identities.
    shop_html = (Path(__file__).resolve().parents[1] / "shop.html").read_text(
        encoding="utf-8"
    )
    assert "equipment_offers" in shop_html
    assert all(item_id not in shop_html for item_id in APPROVED_OFFERS)


@pytest.mark.parametrize("item_id,price", list(APPROVED_OFFERS.items()))
def test_equipment_purchase_route_deducts_authoritative_price_and_persists_reload(
    tmp_path, monkeypatch, item_id, price
):
    path, client = _route_fixture(tmp_path, monkeypatch)
    operation_id = f"c047-success-{item_id}"

    response = client.post(
        "/api/shop/buy",
        json={
            "item_id": item_id,
            "purchase_operation_id": operation_id,
            "price": 1,
            "coin_cost": 0,
            "expected_price": 999999,
            "owned": True,
            "metadata": {"item_id": "forged"},
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["item_id"] == item_id
    assert body["coins_spent"] == price
    assert body["coins_after"] == 1000 - price
    canonical = body["canonical_acquisition_result"]
    assert canonical["source_type"] == "SHOP_COIN_PURCHASE"
    assert canonical["destination"] == "PLAYER_INVENTORY"
    assert canonical["item_id"] == item_id
    assert canonical["ownership_authority"] == "player_inventory"
    assert canonical["can_equip"] is True
    assert canonical["ownership_reference"].startswith("player_inventory:")

    rows = _inventory(path)
    assert len(rows) == 1
    assert rows[0][2:] == (item_id, 0, "coin_shop")
    assert body["ownership_reference"] == f"player_inventory:{rows[0][0]}"

    # A new authenticated client represents a reload/re-fetch, not a cached
    # frontend ownership state.
    reloaded = _client(path, monkeypatch)
    catalog = reloaded.get("/api/shop/catalog").get_json()
    assert catalog["coins"] == 1000 - price
    assert catalog["equipment_ownership"][item_id] == {
        "owned_quantity": 1,
        "ownership_state": "OWNED",
    }
    assert all(
        catalog["equipment_ownership"][other]["owned_quantity"] == 0
        for other in APPROVED_OFFERS
        if other != item_id
    )


def test_duplicate_operation_replays_without_second_deduction_or_duplicate_item(
    tmp_path, monkeypatch
):
    path, client = _route_fixture(tmp_path, monkeypatch)
    payload = {
        "item_id": "wooden_sword",
        "purchase_operation_id": "c047-replay",
        "price": 1,
    }

    first = client.post("/api/shop/buy", json=payload)
    replay = client.post(
        "/api/shop/buy",
        json={**payload, "price": 999999, "coin_cost": -100},
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.get_json()["replayed"] is True
    assert replay.get_json()["coins_spent"] == 300
    assert _coins(path) == 700
    assert len(_inventory(path)) == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM coin_purchase_operations "
            "WHERE purchase_operation_id='c047-replay'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM currency_log WHERE delta < 0"
        ).fetchone()[0] == 1


def test_insufficient_coins_returns_deterministic_failure_without_mutation(
    tmp_path, monkeypatch
):
    path, client = _route_fixture(tmp_path, monkeypatch, coins=299)

    response = client.post(
        "/api/shop/buy",
        json={
            "item_id": "wooden_sword",
            "purchase_operation_id": "c047-insufficient",
            "price": 1,
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "insufficient_coins",
        "code": "INSUFFICIENT_COINS",
        "coins": 299,
    }
    assert _coins(path) == 299
    assert _inventory(path) == []
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM coin_purchase_operations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM currency_log WHERE delta < 0").fetchone()[0] == 0


def test_already_owned_returns_no_duplicate_and_no_second_debit(tmp_path, monkeypatch):
    path, client = _route_fixture(tmp_path, monkeypatch)
    first = client.post(
        "/api/shop/buy",
        json={"item_id": "cloth_robe", "purchase_operation_id": "c047-owned-1"},
    )
    second = client.post(
        "/api/shop/buy",
        json={"item_id": "cloth_robe", "purchase_operation_id": "c047-owned-2"},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.get_json() == {
        "error": "already_owned",
        "code": "EQUIPMENT_ALREADY_OWNED",
    }
    assert _coins(path) == 700
    assert len(_inventory(path)) == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM coin_purchase_operations "
            "WHERE purchase_operation_id='c047-owned-2'"
        ).fetchone()[0] == 0


@pytest.mark.parametrize("item_id", UNAUTHORIZED_IDS)
def test_unauthorized_or_malformed_equipment_fails_closed_without_mutation(
    tmp_path, monkeypatch, item_id
):
    path, client = _route_fixture(tmp_path, monkeypatch)

    response = client.post(
        "/api/shop/buy",
        json={"item_id": item_id, "purchase_operation_id": f"c047-reject-{item_id}"},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "shop_offer_unavailable",
        "code": "UNKNOWN_OFFER",
    }
    assert _coins(path) == 1000
    assert _inventory(path) == []


def test_unauthenticated_equipment_route_is_rejected(tmp_path, monkeypatch):
    path, _ = _route_fixture(tmp_path, monkeypatch)
    client = app_module.app.test_client()

    response = client.post(
        "/api/shop/buy",
        json={"item_id": "wooden_sword", "purchase_operation_id": "c047-anon"},
    )

    assert response.status_code == 401
    assert response.get_json()["redirect"] == "/login"
    assert _coins(path) == 1000


@pytest.mark.parametrize("forged_price", [1, 0, -100, 999999])
def test_client_price_fields_never_change_server_deduction(
    tmp_path, monkeypatch, forged_price
):
    path, client = _route_fixture(tmp_path, monkeypatch)

    response = client.post(
        "/api/shop/buy",
        json={
            "item_id": "lucky_stone",
            "purchase_operation_id": f"c047-forged-{forged_price}",
            "price": forged_price,
            "coin_cost": forged_price,
            "expected_price": forged_price,
            "owned": True,
            "item_metadata": {"price": forged_price, "rarity": "legendary"},
        },
    )

    assert response.status_code == 200
    assert response.get_json()["coins_spent"] == 400
    assert _coins(path) == 600
    assert len(_inventory(path)) == 1


def test_equipment_acquisition_failure_rolls_back_coin_and_operation(
    tmp_path, monkeypatch
):
    path, client = _route_fixture(tmp_path, monkeypatch)

    def fail_acquisition(*args, **kwargs):
        raise equipment_commerce_service.EquipmentOwnershipError("forced test failure")

    monkeypatch.setattr(
        equipment_commerce_service,
        "grant_equipment_ownership",
        fail_acquisition,
    )
    response = client.post(
        "/api/shop/buy",
        json={"item_id": "wooden_sword", "purchase_operation_id": "c047-rollback"},
    )

    assert response.status_code == 422
    assert response.get_json()["error"] == "acquisition_failed"
    assert _coins(path) == 1000
    assert _inventory(path) == []
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM coin_purchase_operations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM currency_log WHERE delta < 0").fetchone()[0] == 0


def test_feature_gates_and_payment_boundaries_remain_default_off():
    assert app_module._canonical_coin_shop_purchase_enabled() is False
    assert app_module._equipment_canonical_loadout_enabled() is False
    assert app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG == (
        "CANONICAL_COIN_SHOP_PURCHASE_ENABLED"
    )
    source = (Path(__file__).resolve().parents[1] / "equipment_shop_offer_authority.py").read_text(
        encoding="utf-8"
    )
    assert "newebpay" not in source.lower()
    assert "paypal" not in source.lower()
