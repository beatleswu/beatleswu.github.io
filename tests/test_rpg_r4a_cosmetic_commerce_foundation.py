"""Lane C Wave 1 cosmetic-commerce vertical-slice contracts."""

import importlib
import os
import sqlite3
import sys
from pathlib import Path

import pytest

from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_purchase_operations


TEST_SECRET = "test-only-r4a-cosmetic-commerce-secret"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET)
    monkeypatch.setenv("GO_ODYSSEY_LIVE_STATIC_ROOT", str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT))
    sys.modules.pop("app", None)
    return importlib.import_module("app")


class _DbContext:
    def __init__(self, path):
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row

    def execute(self, sql, params=()):
        return self._conn.execute(sql, params)

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        self._conn.close()


@pytest.fixture()
def cosmetic_app(tmp_path, monkeypatch):
    path = tmp_path / "r4a-cosmetic.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                plan TEXT NOT NULL DEFAULT 'free',
                premium_until TEXT,
                is_admin INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE user_stats (
                user_id INTEGER PRIMARY KEY,
                coins INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE player_wardrobe (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                obtained_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'drop',
                UNIQUE(user_id, item_id)
            );
            CREATE TABLE player_appearance (
                user_id INTEGER PRIMARY KEY,
                outfit_id TEXT,
                hat_id TEXT,
                back_id TEXT,
                title_id TEXT,
                accessory_id TEXT,
                pet_id TEXT,
                aura_id TEXT,
                updated_at TEXT
            );
            CREATE TABLE currency_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE gacha_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                pool TEXT NOT NULL,
                result_key TEXT,
                result_type TEXT NOT NULL,
                rarity TEXT,
                pity_count INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE badges_earned (
                user_id INTEGER NOT NULL,
                badge_id TEXT NOT NULL,
                earned_at TEXT NOT NULL,
                seen INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, badge_id)
            );
            CREATE TABLE shop_inventory (
                user_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                qty INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(user_id, item_key)
            );
            CREATE TABLE daily_shop (
                shop_date TEXT PRIMARY KEY,
                slots TEXT NOT NULL
            );
            INSERT INTO users(id, plan) VALUES (1, 'free'), (2, 'free');
            INSERT INTO user_stats(user_id, coins) VALUES (1, 500), (2, 0);
        """)
        # D5C acquisition evidence is caller-transactional and therefore
        # belongs in the same disposable fixture as the existing ownership
        # authority. This is a candidate schema setup only, never Production.
        upgrade_purchase_operations(conn)
        upgrade_outbox(conn)

    app = _load_app(monkeypatch)
    monkeypatch.setenv(app.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "true")
    monkeypatch.setattr(app, "get_db", lambda: _DbContext(path))
    app.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    return app, path


def _client_for(app, user_id):
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["is_admin"] = False
    return client


def _scalar(path, sql, params=()):
    with sqlite3.connect(path) as conn:
        return conn.execute(sql, params).fetchone()[0]


def _product(payload, product_id):
    return next(item for item in payload["products"] if item["product_id"] == product_id)


def test_lane_c_copy_preserves_non_combat_effect_boundary():
    copy = (REPO_ROOT / "shop.html").read_text(encoding="utf-8")
    assert "攻擊增量與防禦增量固定為 0" in copy
    assert "沒有戰鬥權限" in copy
    assert "非戰鬥 XP／掉落效果仍可能保留" in copy
    assert "只改變英雄的視覺呈現" not in copy


def test_catalog_and_preview_are_canonically_mapped_and_read_only(cosmetic_app):
    app, path = cosmetic_app
    client = _client_for(app, 1)
    product_id = "cosmetic.outfit.robe_plain"

    catalog = client.get("/api/cosmetic-commerce/catalog")
    assert catalog.status_code == 200
    body = catalog.get_json()
    product = _product(body, product_id)
    assert body["categories"] == ["outfit"]
    assert product["cosmetic_id"] == "robe_plain"
    assert product["ownership"]["source"] == "player_wardrobe.item_id"
    assert product["equipped_state"]["state_field"] == "outfit_id"
    assert product["preview_asset"]["asset_key"] == "robe_plain"
    assert product["visible_result"]["renderer"] == "hero.html#applyEquippedVisuals"
    for item in body["products"]:
        assert item["combat_power"] == {
            "attack_delta": 0,
            "defense_delta": 0,
            "combat_authority": "NO",
        }

    before = (
        _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1"),
        _scalar(path, "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=1"),
        _scalar(path, "SELECT COUNT(*) FROM currency_log WHERE user_id=1"),
    )
    preview = client.get(f"/api/cosmetic-commerce/preview/{product_id}")
    assert preview.status_code == 200
    preview_body = preview.get_json()
    assert preview_body["preview_only"] is True
    assert preview_body["ownership_mutation"] == 0
    assert preview_body["purchase_mutation"] == 0
    assert preview_body["equip_mutation"] == 0
    assert preview_body["product"]["ownership"]["owned"] is False
    assert (
        _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1"),
        _scalar(path, "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=1"),
        _scalar(path, "SELECT COUNT(*) FROM currency_log WHERE user_id=1"),
    ) == before


def test_server_price_purchase_idempotency_failed_grant_and_persistence(cosmetic_app):
    app, path = cosmetic_app
    client = _client_for(app, 1)
    plain = "cosmetic.outfit.robe_plain"
    bamboo = "cosmetic.outfit.robe_bamboo"

    purchased = client.post(
        "/api/cosmetic-commerce/purchase",
        json={"product_id": plain, "purchase_operation_id": "r4a-plain-1", "price": 1},
    )
    assert purchased.status_code == 200
    assert purchased.get_json()["price_charged"] == 200
    assert purchased.get_json()["granted"] is True
    assert _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1") == 300
    assert _scalar(path, "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=1") == 1
    assert _scalar(path, "SELECT delta FROM currency_log WHERE user_id=1") == -200

    duplicate = client.post(
        "/api/cosmetic-commerce/purchase",
        json={"product_id": plain, "purchase_operation_id": "r4a-plain-2", "price": 9999},
    )
    assert duplicate.status_code == 200
    assert duplicate.get_json()["status"] == "already_owned"
    assert duplicate.get_json()["granted"] is False
    assert _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1") == 300
    assert _scalar(path, "SELECT COUNT(*) FROM currency_log WHERE user_id=1") == 1

    failed = client.post(
        "/api/cosmetic-commerce/purchase",
        json={"product_id": bamboo, "purchase_operation_id": "r4a-bamboo-1", "price": -1},
    )
    assert failed.status_code == 400
    assert failed.get_json()["error"] == "insufficient_coins"
    assert _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1") == 300
    assert _scalar(path, "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=1") == 1
    assert _scalar(path, "SELECT COUNT(*) FROM currency_log WHERE user_id=1") == 1

    denied = client.post(
        "/api/cosmetic-commerce/equip", json={"product_id": bamboo}
    )
    assert denied.status_code == 403
    assert denied.get_json()["error"] == "not_owned"

    equipped = client.post(
        "/api/cosmetic-commerce/equip", json={"product_id": plain}
    )
    assert equipped.status_code == 200
    assert equipped.get_json()["product"]["equipped_state"]["equipped"] is True
    assert _scalar(path, "SELECT outfit_id FROM player_appearance WHERE user_id=1") == "robe_plain"

    reloaded = client.get("/api/cosmetic-commerce/catalog").get_json()
    assert _product(reloaded, plain)["equipped_state"]["equipped"] is True


def test_premium_unlock_uses_durable_entitlement_not_client_flag(cosmetic_app):
    app, path = cosmetic_app
    client = _client_for(app, 2)
    premium = "cosmetic.outfit.robe_premium"

    forged = client.post(
        "/api/cosmetic-commerce/purchase",
        json={"product_id": premium, "premium": True},
    )
    assert forged.status_code == 403
    assert forged.get_json()["error"] == "premium_required"
    assert _scalar(path, "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=2") == 0

    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE users SET plan='premium' WHERE id=2")

    equip_before_unlock = client.post(
        "/api/cosmetic-commerce/equip", json={"product_id": premium}
    )
    assert equip_before_unlock.status_code == 403
    assert equip_before_unlock.get_json()["error"] == "not_owned"
    assert _scalar(
        path, "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=2"
    ) == 0
    assert _scalar(
        path, "SELECT COUNT(*) FROM badges_earned WHERE user_id=2"
    ) == 0
    assert _scalar(
        path, "SELECT COUNT(*) FROM player_appearance WHERE user_id=2"
    ) == 0

    unlocked = client.post(
        "/api/cosmetic-commerce/purchase",
        json={"product_id": premium},
    )
    assert unlocked.status_code == 200
    assert unlocked.get_json()["status"] == "unlocked"
    assert unlocked.get_json()["granted"] is True
    assert unlocked.get_json()["price_charged"] is None
    assert _scalar(path, "SELECT COUNT(*) FROM currency_log WHERE user_id=2") == 0
    assert _scalar(path, "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=2 AND item_id='robe_premium'") == 1
    assert _scalar(path, "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=2") == 1
    assert _scalar(path, "SELECT COUNT(*) FROM badges_earned WHERE user_id=2") == 0
    assert _scalar(path, "SELECT COUNT(*) FROM player_appearance WHERE user_id=2") == 0

    unrelated_premium_items = tuple(
        item_id for item_id in app.PREMIUM_ITEMS if item_id != "robe_premium"
    )
    assert _scalar(
        path,
        "SELECT COUNT(*) FROM player_wardrobe "
        "WHERE user_id=2 AND item_id IN (%s)"
        % ",".join("?" for _ in unrelated_premium_items),
        unrelated_premium_items,
    ) == 0

    duplicate = client.post(
        "/api/cosmetic-commerce/purchase", json={"product_id": premium}
    )
    assert duplicate.status_code == 200
    assert duplicate.get_json()["status"] == "already_owned"
    assert duplicate.get_json()["granted"] is False
    assert _scalar(path, "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=2") == 1
    assert _scalar(path, "SELECT COUNT(*) FROM badges_earned WHERE user_id=2") == 0
    assert _scalar(path, "SELECT COUNT(*) FROM player_appearance WHERE user_id=2") == 0

    equipped = client.post(
        "/api/cosmetic-commerce/equip", json={"product_id": premium}
    )
    assert equipped.status_code == 200
    assert equipped.get_json()["product"]["equipped_state"]["equipped"] is True
    assert _scalar(path, "SELECT outfit_id FROM player_appearance WHERE user_id=2") == "robe_premium"
    assert _scalar(path, "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=2") == 1
    assert _scalar(path, "SELECT COUNT(*) FROM badges_earned WHERE user_id=2") == 0


def test_spend_coins_rejects_negative_amount(cosmetic_app):
    app, path = cosmetic_app
    with app.get_db() as conn:
        assert app._spend_coins(conn, 1, -1, "test:negative") is False
    assert _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1") == 500
    assert _scalar(path, "SELECT COUNT(*) FROM currency_log WHERE user_id=1") == 0


def test_existing_shop_and_retired_gacha_endpoints_smoke(cosmetic_app, monkeypatch):
    app, path = cosmetic_app
    client = _client_for(app, 1)
    item_key = next(iter(app.SHOP_ITEMS))
    appearance = next(
        item for item in app.APPEARANCE_DEFS
        if item.get("id") in app._COSMETIC_PRODUCT_BY_COSMETIC_ID
        and app._COSMETIC_PRODUCT_BY_COSMETIC_ID[item["id"]]["unlock_type"] == "coins"
    )

    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE user_stats SET coins=10000 WHERE user_id=1")

    monkeypatch.setattr(app, "_daily_shop_slots", lambda conn, persist=True: [])
    monkeypatch.setattr(
        app,
        "_grant_shop_purchase",
        lambda conn, uid, item, qty=1: ([{"item_key": item["key"], "qty": qty}], []),
    )
    shop_buy = client.post(
        "/api/shop/buy",
        json={"item_key": item_key, "qty": 1, "purchase_operation_id": "r4a-shop-1"},
    )
    assert shop_buy.status_code == 200

    monkeypatch.setattr(
        app,
        "_daily_shop_slots",
        lambda conn, persist=True: [{
            "type": "appearance",
            "item_key": appearance["id"],
            "price": 200,
        }],
    )
    buy_appearance = client.post(
        "/api/shop/buy_appearance",
        json={"item_id": appearance["id"], "purchase_operation_id": "r4a-appearance-1"},
    )
    assert buy_appearance.status_code == 200
    coins_before_gacha = _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1")

    gacha = client.post("/api/shop/gacha", json={})
    assert gacha.status_code == 409
    assert gacha.get_json() == {
        "error": "shop_offer_unavailable",
        "code": "LEGACY_PURCHASE_RETIRED",
    }
    assert _scalar(path, "SELECT COUNT(*) FROM gacha_log WHERE user_id=1") == 0
    assert _scalar(path, "SELECT COUNT(*) FROM currency_log WHERE user_id=1") == 2
    assert _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1") == coins_before_gacha
