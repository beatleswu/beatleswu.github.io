"""C048-R2 regression coverage for the canonical Coin Shop gate.

The tests use only disposable SQLite databases.  The Shop gate is exercised
through the real Flask routes and the existing C019/C026/C029/D024 services;
no payment, Production, or player data is touched.
"""

from __future__ import annotations

import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

os.environ.setdefault("SECRET_KEY", "c048-r2-shop-gate-test-secret")

import app as app_module
from test_e030_shop_coin_purchase_and_equipment_runtime_integration import (
    _DbContext,
    _client,
    _create_db,
    _seed_daily_slots,
)


FLAG = app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG
LOADOUT_FLAG = app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG
DISABLED = {
    "error": "shop_offer_unavailable",
    "code": "SHOP_PURCHASE_DISABLED",
}


def _state(path, user_id=1):
    with sqlite3.connect(path) as conn:
        return {
            "coins": conn.execute(
                "SELECT coins FROM user_stats WHERE user_id=?", (user_id,)
            ).fetchone()[0],
            "inventory_rows": conn.execute(
                "SELECT COUNT(*) FROM player_inventory WHERE user_id=?", (user_id,)
            ).fetchone()[0],
            "purchase_operations": conn.execute(
                "SELECT COUNT(*) FROM coin_purchase_operations WHERE user_id=?",
                (user_id,),
            ).fetchone()[0],
            "coin_debits": conn.execute(
                "SELECT COUNT(*) FROM currency_log WHERE user_id=? AND delta<0",
                (user_id,),
            ).fetchone()[0],
            "equipped": conn.execute(
                "SELECT COALESCE(SUM(equipped),0) FROM player_inventory "
                "WHERE user_id=?",
                (user_id,),
            ).fetchone()[0],
        }


def _inventory_rows(path, user_id=1):
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT user_id,equip_id,equipped,source FROM player_inventory "
            "WHERE user_id=? ORDER BY id",
            (user_id,),
        ).fetchall()


def _set_shop_flag(monkeypatch, value):
    if value is None:
        monkeypatch.delenv(FLAG, raising=False)
    else:
        monkeypatch.setenv(FLAG, value)


def _client_for_user(path, monkeypatch, user_id):
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(path))
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["username"] = f"c048-r2-user-{user_id}"
    return client


def _authenticated_client():
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "c048-r2-concurrent"
    return client


@pytest.mark.parametrize(
    "flag_value",
    [None, "", "false", "FALSE", "0", "null", "None", "malformed", "2", "1.0", "01"],
)
def test_shop_off_class_values_reject_before_any_purchase_mutation(
    tmp_path, monkeypatch, flag_value
):
    path = tmp_path / f"shop-off-{flag_value or 'unset'}.sqlite"
    _create_db(path, post_b033=True, purchase_schema=True, coins=1000)
    _set_shop_flag(monkeypatch, flag_value)
    client = _client(path, monkeypatch)

    before = _state(path)
    response = client.post(
        "/api/shop/buy",
        json={
            "item_id": "wooden_sword",
            "purchase_operation_id": f"c048-r2-off-{flag_value or 'unset'}",
            "price": 1,
        },
    )
    after = _state(path)

    assert response.status_code == 409
    assert response.get_json() == DISABLED
    assert after == before == {
        "coins": 1000,
        "inventory_rows": 0,
        "purchase_operations": 0,
        "coin_debits": 0,
        "equipped": 0,
    }


@pytest.mark.parametrize(
    "flag_value",
    ["1", "true", "TRUE", "yes", "on", " true "],
)
def test_existing_flag_parser_accepts_only_its_canonical_true_tokens(
    monkeypatch, flag_value
):
    monkeypatch.setenv(FLAG, flag_value)
    assert app_module._canonical_coin_shop_purchase_enabled() is True


def test_canonical_coin_purchase_succeeds_only_when_gate_is_validly_on(
    tmp_path, monkeypatch
):
    path = tmp_path / "shop-on-success.sqlite"
    _create_db(path, post_b033=True, purchase_schema=True, coins=1000)
    _set_shop_flag(monkeypatch, "true")
    monkeypatch.delenv(LOADOUT_FLAG, raising=False)
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/shop/buy",
        json={
            "item_id": "wooden_sword",
            "purchase_operation_id": "c048-r2-success",
            "price": 1,
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["coins_spent"] == 300
    assert body["coins_after"] == 700
    assert body["canonical_acquisition_result"]["destination"] == "PLAYER_INVENTORY"
    assert _state(path) == {
        "coins": 700,
        "inventory_rows": 1,
        "purchase_operations": 1,
        "coin_debits": 1,
        "equipped": 0,
    }
    assert _inventory_rows(path) == [(1, "wooden_sword", 0, "coin_shop")]

    reloaded = _client(path, monkeypatch)
    inventory = reloaded.get("/api/player/inventory")
    assert inventory.status_code == 200
    assert [entry["item_id"] for entry in inventory.get_json()] == ["wooden_sword"]


def test_shop_off_common_canonical_aliases_share_the_disabled_contract(
    tmp_path, monkeypatch
):
    path = tmp_path / "shop-off-aliases.sqlite"
    _create_db(
        path,
        purchase_schema=True,
        include_appearance=True,
        coins=1000,
    )
    _seed_daily_slots(
        path,
        [{
            "type": "appearance",
            "item_key": "robe_plain",
            "cosmetic_id": "robe_plain",
            "product_id": "cosmetic.outfit.robe_plain",
            "price": 200,
        }],
    )
    _set_shop_flag(monkeypatch, None)
    client = _client(path, monkeypatch)

    daily = client.post(
        "/api/shop/buy_appearance",
        json={
            "item_id": "robe_plain",
            "purchase_operation_id": "c048-r2-daily-off",
        },
    )
    cosmetic = client.post(
        "/api/cosmetic-commerce/purchase",
        json={
            "product_id": "cosmetic.outfit.robe_plain",
            "purchase_operation_id": "c048-r2-cosmetic-off",
        },
    )

    assert daily.status_code == cosmetic.status_code == 409
    assert daily.get_json() == cosmetic.get_json() == DISABLED
    assert _state(path) == {
        "coins": 1000,
        "inventory_rows": 0,
        "purchase_operations": 0,
        "coin_debits": 0,
        "equipped": 0,
    }
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=1"
        ).fetchone()[0] == 0


def test_insufficient_coins_fails_closed_without_reserving_operation(
    tmp_path, monkeypatch
):
    path = tmp_path / "shop-insufficient.sqlite"
    _create_db(path, post_b033=True, purchase_schema=True, coins=299)
    _set_shop_flag(monkeypatch, "1")
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/shop/buy",
        json={
            "item_id": "wooden_sword",
            "purchase_operation_id": "c048-r2-insufficient",
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "insufficient_coins",
        "code": "INSUFFICIENT_COINS",
        "coins": 299,
    }
    assert _state(path) == {
        "coins": 299,
        "inventory_rows": 0,
        "purchase_operations": 0,
        "coin_debits": 0,
        "equipped": 0,
    }


def test_already_owned_purchase_fails_closed_without_second_debit(
    tmp_path, monkeypatch
):
    path = tmp_path / "shop-already-owned.sqlite"
    _create_db(path, post_b033=True, purchase_schema=True, coins=1000)
    _set_shop_flag(monkeypatch, "1")
    client = _client(path, monkeypatch)

    first = client.post(
        "/api/shop/buy",
        json={"item_id": "wooden_sword", "purchase_operation_id": "c048-r2-owned-1"},
    )
    second = client.post(
        "/api/shop/buy",
        json={"item_id": "wooden_sword", "purchase_operation_id": "c048-r2-owned-2"},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.get_json() == {
        "error": "already_owned",
        "code": "EQUIPMENT_ALREADY_OWNED",
    }
    assert _state(path) == {
        "coins": 700,
        "inventory_rows": 1,
        "purchase_operations": 1,
        "coin_debits": 1,
        "equipped": 0,
    }


@pytest.mark.parametrize("item_id", ["not-a-real-item", "../wooden_sword", "xp_amulet"])
def test_invalid_or_noncanonical_item_id_fails_closed(tmp_path, monkeypatch, item_id):
    path = tmp_path / "shop-invalid-id.sqlite"
    _create_db(path, post_b033=True, purchase_schema=True, coins=1000)
    _set_shop_flag(monkeypatch, "1")
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/shop/buy",
        json={"item_id": item_id, "purchase_operation_id": f"c048-r2-invalid-{item_id}"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "shop_offer_unavailable"
    assert _state(path) == {
        "coins": 1000,
        "inventory_rows": 0,
        "purchase_operations": 0,
        "coin_debits": 0,
        "equipped": 0,
    }


@pytest.mark.parametrize("forged_price", [0, 1, -100, 999999])
def test_client_price_is_ignored_and_server_price_is_authoritative(
    tmp_path, monkeypatch, forged_price
):
    path = tmp_path / f"shop-forged-price-{forged_price}.sqlite"
    _create_db(path, post_b033=True, purchase_schema=True, coins=1000)
    _set_shop_flag(monkeypatch, "1")
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/shop/buy",
        json={
            "item_id": "wooden_sword",
            "purchase_operation_id": f"c048-r2-price-{forged_price}",
            "price": forged_price,
            "coin_cost": forged_price,
            "expected_price": forged_price,
            "owned": True,
            "metadata": {"price": forged_price},
        },
    )

    assert response.status_code == 200
    assert response.get_json()["coins_spent"] == 300
    assert _state(path)["coins"] == 700


def test_idempotent_replay_has_one_operation_one_debit_one_grant(
    tmp_path, monkeypatch
):
    path = tmp_path / "shop-replay.sqlite"
    _create_db(path, post_b033=True, purchase_schema=True, coins=1000)
    _set_shop_flag(monkeypatch, "true")
    client = _client(path, monkeypatch)
    payload = {
        "item_id": "wooden_sword",
        "purchase_operation_id": "c048-r2-replay",
        "price": 1,
    }

    first = client.post("/api/shop/buy", json=payload)
    replay = client.post("/api/shop/buy", json={**payload, "price": 999999})

    assert first.status_code == replay.status_code == 200
    assert replay.get_json()["replayed"] is True
    assert replay.get_json()["coins_spent"] == 300
    assert _state(path) == {
        "coins": 700,
        "inventory_rows": 1,
        "purchase_operations": 1,
        "coin_debits": 1,
        "equipped": 0,
    }


def test_concurrent_same_operation_cannot_double_spend_or_double_grant(
    tmp_path, monkeypatch
):
    path = tmp_path / "shop-concurrent.sqlite"
    _create_db(path, post_b033=True, purchase_schema=True, coins=1000)
    _set_shop_flag(monkeypatch, "1")
    _client(path, monkeypatch)
    payload = {
        "item_id": "wooden_sword",
        "purchase_operation_id": "c048-r2-concurrent",
        "price": 1,
    }

    def request_once():
        return _authenticated_client().post("/api/shop/buy", json=payload)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: request_once(), range(2)))

    assert all(response.status_code == 200 for response in responses)
    assert sum(response.get_json().get("replayed") is not True for response in responses) == 1
    assert _state(path) == {
        "coins": 700,
        "inventory_rows": 1,
        "purchase_operations": 1,
        "coin_debits": 1,
        "equipped": 0,
    }


def test_shop_on_loadout_off_grants_ownership_only(tmp_path, monkeypatch):
    path = tmp_path / "shop-loadout-off.sqlite"
    _create_db(path, post_b033=True, purchase_schema=True, coins=1000)
    _set_shop_flag(monkeypatch, "on")
    monkeypatch.delenv(LOADOUT_FLAG, raising=False)
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/shop/buy",
        json={
            "item_id": "cloth_robe",
            "purchase_operation_id": "c048-r2-loadout-off",
        },
    )

    assert response.status_code == 200
    assert app_module._equipment_canonical_loadout_enabled() is False
    assert response.get_json()["can_equip"] is True
    assert _inventory_rows(path) == [(1, "cloth_robe", 0, "coin_shop")]
    assert _state(path)["equipped"] == 0


def test_cross_player_purchase_ownership_isolation(tmp_path, monkeypatch):
    path = tmp_path / "shop-cross-player.sqlite"
    _create_db(path, post_b033=True, purchase_schema=True, coins=1000)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO user_stats(user_id,coins) VALUES(2,1000)"
        )
    _set_shop_flag(monkeypatch, "true")

    user_one = _client_for_user(path, monkeypatch, 1)
    user_two = _client_for_user(path, monkeypatch, 2)
    first = user_one.post(
        "/api/shop/buy",
        json={"item_id": "lucky_stone", "purchase_operation_id": "c048-r2-user-1"},
    )
    second = user_two.post(
        "/api/shop/buy",
        json={"item_id": "lucky_stone", "purchase_operation_id": "c048-r2-user-2"},
    )

    assert first.status_code == second.status_code == 200
    assert _state(path, 1)["coins"] == 600
    assert _state(path, 2)["coins"] == 600
    assert _inventory_rows(path, 1) == [(1, "lucky_stone", 0, "coin_shop")]
    assert _inventory_rows(path, 2) == [(2, "lucky_stone", 0, "coin_shop")]


def test_missing_operation_identity_keeps_validation_contract_without_mutation(
    tmp_path, monkeypatch
):
    path = tmp_path / "shop-missing-operation.sqlite"
    _create_db(path, post_b033=True, purchase_schema=True, coins=1000)
    _set_shop_flag(monkeypatch, None)
    client = _client(path, monkeypatch)

    response = client.post("/api/shop/buy", json={"item_id": "wooden_sword"})

    assert response.status_code == 400
    assert response.get_json() == {"error": "invalid_operation_identity"}
    assert _state(path) == {
        "coins": 1000,
        "inventory_rows": 0,
        "purchase_operations": 0,
        "coin_debits": 0,
        "equipped": 0,
    }
