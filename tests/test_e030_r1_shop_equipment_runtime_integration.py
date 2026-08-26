"""E030-R1 regression tests for pre-mutation Shop dispatch and exact rows."""

from __future__ import annotations

import sqlite3

import pytest

import app as app_module
from test_e030_shop_coin_purchase_and_equipment_runtime_integration import (
    _DbContext,
    _client,
    _coins,
    _create_db,
    _inventory,
    _seed_daily_slots,
)


def test_shop_classifier_is_read_only_before_legacy_dispatch(tmp_path):
    path = tmp_path / "dispatch-read-only.sqlite"
    _create_db(path, include_wardrobe=False, purchase_schema=False)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM daily_shop").fetchone()[0] == 0
        with _DbContext(path) as dispatch_conn:
            result = app_module._classify_shop_request(
                dispatch_conn,
                {"item_key": "premium_hint_bundle"},
            )
        assert result["classification"] == app_module.LEGACY_SHOP_DISPATCH
        assert conn.execute("SELECT COUNT(*) FROM daily_shop").fetchone()[0] == 0


@pytest.mark.parametrize("item_key", ["premium_hint_bundle", "extra_questions_small"])
def test_known_legacy_only_products_use_legacy_path_once(tmp_path, monkeypatch, item_key):
    path = tmp_path / f"legacy-{item_key}.sqlite"
    _create_db(path, include_wardrobe=False, purchase_schema=False, coins=500)
    _seed_daily_slots(path, [])
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/shop/buy",
        json={"item_key": item_key, "qty": 1, "price": 1},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["item_key"] == item_key
    assert body["qty"] == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT coins FROM user_stats WHERE user_id=1"
        ).fetchone()[0] == 500 - app_module.SHOP_ITEMS[item_key]["price"]
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name='coin_purchase_operations'"
        ).fetchone()[0] == 0


def test_known_legacy_only_appearance_uses_existing_route(tmp_path, monkeypatch):
    path = tmp_path / "legacy-appearance.sqlite"
    _create_db(path, purchase_schema=False, coins=500)
    with sqlite3.connect(path) as conn:
        # The current legacy route reads the historical row id.  Keep this
        # disposable fixture faithful to that route without changing the
        # shared E030 fixture or production schema.
        conn.execute("ALTER TABLE player_wardrobe ADD COLUMN id INTEGER")
    _seed_daily_slots(
        path,
        [{"type": "appearance", "item_key": "hat_cloth", "price": 200}],
    )
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/shop/buy_appearance",
        json={"item_id": "hat_cloth"},
    )

    assert response.status_code == 200
    assert response.get_json()["item_id"] == "hat_cloth"
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM player_wardrobe "
            "WHERE user_id=1 AND item_id='hat_cloth'"
        ).fetchone()[0] == 1


def test_unknown_shop_offer_fails_closed_before_legacy_mutation(tmp_path, monkeypatch):
    path = tmp_path / "unknown-offer.sqlite"
    _create_db(path, include_wardrobe=False, purchase_schema=False, coins=500)
    _seed_daily_slots(path, [])
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/shop/buy",
        json={"item_key": "not-a-real-shop-item"},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "shop_offer_unavailable",
        "code": "UNKNOWN_OFFER",
    }
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT coins FROM user_stats WHERE user_id=1"
        ).fetchone()[0] == 500


def test_conflicting_shop_selectors_fail_closed_before_mutation(tmp_path, monkeypatch):
    path = tmp_path / "ambiguous-offer.sqlite"
    _create_db(path, include_wardrobe=False, purchase_schema=False, coins=500)
    _seed_daily_slots(path, [])
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/shop/buy",
        json={
            "item_key": "hint_ticket",
            "product_id": "cosmetic.outfit.robe_plain",
        },
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "AMBIGUOUS_OFFER"
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT coins FROM user_stats WHERE user_id=1"
        ).fetchone()[0] == 500


def test_canonical_offer_id_selector_uses_derived_server_identity(tmp_path, monkeypatch):
    path = tmp_path / "derived-offer-id.sqlite"
    _create_db(path, include_wardrobe=False, purchase_schema=True, coins=500)
    _seed_daily_slots(
        path,
        [{"type": "item", "item_key": "hint_ticket", "price": 30}],
    )
    with _DbContext(path) as conn:
        facts = app_module._canonical_shop_offer_facts(conn)
        offer = app_module.normalize_shop_offer(
            next(fact for fact in facts if fact.item_key == "hint_ticket")
        )
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/shop/buy",
        json={
            "offer_id": offer.offer_id,
            "purchase_operation_id": "e030-r1-derived-offer-id",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["offer_id"] == offer.offer_id


def test_canonical_failure_never_falls_back_to_legacy(tmp_path, monkeypatch):
    path = tmp_path / "canonical-no-fallback.sqlite"
    _create_db(path, include_wardrobe=False, purchase_schema=False)
    _seed_daily_slots(path, [])
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    calls = {"canonical": 0, "legacy": 0}

    def canonical_failure(*args, **kwargs):
        calls["canonical"] += 1
        return app_module.jsonify({
            "error": "canonical_result_unavailable",
            "code": "TEST_CANONICAL_FAILURE",
        }), 503

    def legacy_should_not_run(*args, **kwargs):
        calls["legacy"] += 1
        raise AssertionError("legacy Shop mutation was reached after canonical dispatch")

    monkeypatch.setattr(app_module, "_canonical_shop_purchase_response", canonical_failure)
    monkeypatch.setattr(app_module, "_grant_shop_purchase", legacy_should_not_run)
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/shop/buy",
        json={"item_key": "hint_ticket", "purchase_operation_id": "e030-r1-no-fallback"},
    )

    assert response.status_code == 503
    assert calls == {"canonical": 1, "legacy": 0}


def test_post_commit_d024_failure_never_falls_back_to_legacy(tmp_path, monkeypatch):
    path = tmp_path / "post-commit-no-fallback.sqlite"
    _create_db(path, include_wardrobe=False, purchase_schema=True, coins=500)
    _seed_daily_slots(path, [{"type": "item", "item_key": "hint_ticket", "price": 30}])
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    legacy_calls = []

    def legacy_should_not_run(*args, **kwargs):
        legacy_calls.append(True)
        raise AssertionError("legacy Shop mutation was reached after D024 failure")

    def fail_d024(*args, **kwargs):
        raise RuntimeError("forced E030-R1 D024 failure")

    monkeypatch.setattr(app_module, "_grant_shop_purchase", legacy_should_not_run)
    monkeypatch.setattr(app_module, "adapt_committed_shop_purchase", fail_d024)
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/shop/buy",
        json={"item_key": "hint_ticket", "purchase_operation_id": "e030-r1-post-commit"},
    )

    assert response.status_code == 503
    assert response.get_json()["error"] == "canonical_result_unavailable"
    assert legacy_calls == []


def test_canonical_offer_without_purchase_schema_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "canonical-schema-unavailable.sqlite"
    _create_db(path, include_wardrobe=False, purchase_schema=False, coins=500)
    _seed_daily_slots(
        path,
        [{"type": "item", "item_key": "hint_ticket", "price": 30}],
    )
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/shop/buy",
        json={
            "item_key": "hint_ticket",
            "purchase_operation_id": "e030-r1-schema-unavailable",
        },
    )

    assert response.status_code == 503
    assert response.get_json() == {
        "error": "schema_unavailable",
        "code": "SCHEMA_UNAVAILABLE",
    }
    assert _coins(path) == 500
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM shop_inventory"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name='coin_purchase_operations'"
        ).fetchone()[0] == 0


@pytest.mark.parametrize(
    ("equip_id", "canonical_slot"),
    [
        ("iron_sword", "weapon"),
        ("cloth_robe", "armor"),
        ("lucky_stone", "accessory"),
    ],
)
def test_b041_equip_targets_exact_requested_duplicate_row(
    tmp_path, monkeypatch, equip_id, canonical_slot
):
    path = tmp_path / f"exact-equip-{equip_id}.sqlite"
    _create_db(path, post_b033=True, include_shop_inventory=False, include_wardrobe=False)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO player_inventory"
            "(id,user_id,equip_id,equipped,canonical_slot,obtained_at,source) "
            "VALUES(101,1,?,0,NULL,'2026-08-26','test')",
            (equip_id,),
        )
        conn.execute(
            "INSERT INTO player_inventory"
            "(id,user_id,equip_id,equipped,canonical_slot,obtained_at,source) "
            "VALUES(205,1,?,0,NULL,'2026-08-26','test')",
            (equip_id,),
        )
    monkeypatch.setenv(app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG, "1")
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/player/inventory/equip",
        json={
            "inv_id": 205,
            "action": "equip",
            "equip_id": "xp_amulet",
            "slot": "armor",
            "canonical_slot": "armor",
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["inv_id"] == 205
    assert body["target_ownership_row_id"] == 205
    assert body["item_id"] == equip_id
    assert body["canonical_slot"] == canonical_slot
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT id,equipped,canonical_slot FROM player_inventory ORDER BY id"
        ).fetchall()
    assert rows == [
        (101, 0, None),
        (205, 1, canonical_slot),
    ]


def test_b041_unequip_does_not_touch_another_duplicate_row(tmp_path, monkeypatch):
    path = tmp_path / "exact-unequip.sqlite"
    _create_db(path, post_b033=True, include_shop_inventory=False, include_wardrobe=False)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO player_inventory"
            "(id,user_id,equip_id,equipped,canonical_slot,obtained_at,source) "
            "VALUES(101,1,'iron_sword',1,'weapon','2026-08-26','test')"
        )
        conn.execute(
            "INSERT INTO player_inventory"
            "(id,user_id,equip_id,equipped,canonical_slot,obtained_at,source) "
            "VALUES(205,1,'iron_sword',0,NULL,'2026-08-26','test')"
        )
    monkeypatch.setenv(app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG, "1")
    client = _client(path, monkeypatch)

    response = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 205, "action": "unequip", "equip_id": "iron_sword"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["inv_id"] == 205
    assert body["target_ownership_row_id"] == 205
    assert body["changed"] is False
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT equipped,canonical_slot FROM player_inventory WHERE id=101"
        ).fetchone() == (1, "weapon")
        assert conn.execute(
            "SELECT equipped,canonical_slot FROM player_inventory WHERE id=205"
        ).fetchone() == (0, None)
