"""C048 proof that the canonical Shop purchase route is durable and gated."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "c048-route-test-secret")

import app as app_module
from test_e030_shop_coin_purchase_and_equipment_runtime_integration import (
    _client,
    _coins,
    _create_db,
    _inventory,
)


def _default_client(path, monkeypatch):
    monkeypatch.delenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, raising=False)
    return _client(path, monkeypatch)


def _canonical_client(path, monkeypatch):
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "true")
    return _client(path, monkeypatch)


def test_canonical_stackable_purchase_uses_durable_operation_and_replays_once(
    tmp_path, monkeypatch
):
    path = tmp_path / "c048-default-stackable.sqlite"
    _create_db(path, purchase_schema=True, include_wardrobe=False, coins=500)

    def legacy_should_not_run(*args, **kwargs):
        raise AssertionError("default /api/shop/buy reached legacy mutation")

    monkeypatch.setattr(app_module, "_spend_coins", legacy_should_not_run)
    monkeypatch.setattr(app_module, "_grant_shop_purchase", legacy_should_not_run)
    client = _canonical_client(path, monkeypatch)

    first = client.post(
        "/api/shop/buy",
        json={
            "item_key": "hint_ticket",
            "purchase_operation_id": "c048-stackable-replay",
            "qty": 99,
            "price": 1,
        },
    )
    replay = client.post(
        "/api/shop/buy",
        json={
            "item_key": "hint_ticket",
            "purchase_operation_id": "c048-stackable-replay",
            "price": 999999,
        },
    )

    assert first.status_code == 200
    assert first.get_json()["offer_id"] == "shop.static.hint_ticket"
    assert first.get_json()["coins_spent"] == 30
    assert first.get_json()["canonical_acquisition_result"]["destination"] == "STACK_INVENTORY"
    assert replay.status_code == 200
    assert replay.get_json()["replayed"] is True
    assert replay.get_json()["coins_spent"] == 30
    assert _coins(path) == 470
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='hint_ticket'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM coin_purchase_operations "
            "WHERE user_id=1 AND purchase_operation_id='c048-stackable-replay'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM currency_log WHERE user_id=1 AND delta<0"
        ).fetchone()[0] == 1


def test_canonical_equipment_purchase_persists_unequipped_ownership(tmp_path, monkeypatch):
    path = tmp_path / "c048-default-equipment.sqlite"
    _create_db(path, post_b033=True, purchase_schema=True, coins=1000)
    client = _canonical_client(path, monkeypatch)

    response = client.post(
        "/api/shop/buy",
        json={
            "item_id": "wooden_sword",
            "purchase_operation_id": "c048-equipment-1",
            "price": 1,
            "owned": True,
            "metadata": {"equip_id": "forged"},
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["item_id"] == "wooden_sword"
    assert body["coins_spent"] == 300
    assert body["coins_after"] == 700
    assert body["can_equip"] is True
    rows = _inventory(path)
    assert len(rows) == 1
    assert rows[0][2:] == ("wooden_sword", 0, "coin_shop")

    reloaded = _canonical_client(path, monkeypatch)
    inventory = reloaded.get("/api/player/inventory")
    assert inventory.status_code == 200
    owned = [entry for entry in inventory.get_json() if entry["item_id"] == "wooden_sword"]
    assert len(owned) == 1
    assert owned[0]["equipped"] == 0
    assert _coins(path) == 700


@pytest.mark.parametrize("item_key", ["premium_hint_bundle", "extra_questions_small", "pet_snack"])
def test_default_legacy_compatibility_products_fail_closed_without_mutation(
    tmp_path, monkeypatch, item_key
):
    path = tmp_path / f"c048-legacy-{item_key}.sqlite"
    _create_db(path, purchase_schema=True, include_wardrobe=False, coins=500)

    def legacy_should_not_run(*args, **kwargs):
        raise AssertionError("default /api/shop/buy reached legacy mutation")

    monkeypatch.setattr(app_module, "_spend_coins", legacy_should_not_run)
    monkeypatch.setattr(app_module, "_grant_shop_purchase", legacy_should_not_run)
    client = _default_client(path, monkeypatch)

    response = client.post(
        "/api/shop/buy",
        json={
            "item_key": item_key,
            "purchase_operation_id": f"c048-legacy-{item_key}",
            "price": 1,
        },
    )

    assert response.status_code == 409
    assert response.get_json() == {
        "error": "shop_offer_unavailable",
        "code": "LEGACY_PURCHASE_RETIRED",
    }
    assert _coins(path) == 500
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM coin_purchase_operations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM currency_log WHERE delta<0").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM shop_inventory").fetchone()[0] == 0


def test_default_route_rejects_missing_operation_identity_before_mutation(tmp_path, monkeypatch):
    path = tmp_path / "c048-operation-required.sqlite"
    _create_db(path, purchase_schema=True, include_wardrobe=False, coins=500)
    client = _default_client(path, monkeypatch)

    response = client.post("/api/shop/buy", json={"item_key": "hint_ticket"})

    assert response.status_code == 400
    assert response.get_json() == {"error": "invalid_operation_identity"}
    assert _coins(path) == 500
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM coin_purchase_operations").fetchone()[0] == 0


def test_default_route_keeps_shop_ui_flag_default_off_and_removes_legacy_fallback():
    source = Path(app_module.__file__).read_text(encoding="utf-8")
    route = source[source.index("def shop_buy():"):source.index("@app.route('/api/shop/use'")]
    assert app_module._canonical_coin_shop_purchase_enabled() is False
    assert "_spend_coins" not in route
    assert "_grant_shop_purchase" not in route
    assert "LEGACY_PURCHASE_RETIRED" in route
