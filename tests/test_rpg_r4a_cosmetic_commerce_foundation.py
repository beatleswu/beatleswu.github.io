"""Lane C Wave 1 cosmetic-commerce vertical-slice contracts."""

import importlib
import os
import sqlite3
import sys
from pathlib import Path

import pytest


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
            CREATE TABLE badges_earned (
                user_id INTEGER NOT NULL,
                badge_id TEXT NOT NULL,
                earned_at TEXT NOT NULL,
                seen INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, badge_id)
            );
            INSERT INTO users(id, plan) VALUES (1, 'free'), (2, 'free');
            INSERT INTO user_stats(user_id, coins) VALUES (1, 500), (2, 0);
        """)

    app = _load_app(monkeypatch)
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
        json={"product_id": plain, "price": 1},
    )
    assert purchased.status_code == 200
    assert purchased.get_json()["price_charged"] == 200
    assert purchased.get_json()["granted"] is True
    assert _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1") == 300
    assert _scalar(path, "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=1") == 1
    assert _scalar(path, "SELECT delta FROM currency_log WHERE user_id=1") == -200

    duplicate = client.post(
        "/api/cosmetic-commerce/purchase",
        json={"product_id": plain, "price": 9999},
    )
    assert duplicate.status_code == 200
    assert duplicate.get_json()["status"] == "already_owned"
    assert duplicate.get_json()["granted"] is False
    assert _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1") == 300
    assert _scalar(path, "SELECT COUNT(*) FROM currency_log WHERE user_id=1") == 1

    failed = client.post(
        "/api/cosmetic-commerce/purchase",
        json={"product_id": bamboo, "price": -1},
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

    unlocked = client.post(
        "/api/cosmetic-commerce/purchase",
        json={"product_id": premium},
    )
    assert unlocked.status_code == 200
    assert unlocked.get_json()["status"] == "unlocked"
    assert unlocked.get_json()["price_charged"] is None
    assert _scalar(path, "SELECT COUNT(*) FROM currency_log WHERE user_id=2") == 0
    assert _scalar(path, "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=2 AND item_id='robe_premium'") == 1


def test_spend_coins_rejects_negative_amount(cosmetic_app):
    app, path = cosmetic_app
    with app.get_db() as conn:
        assert app._spend_coins(conn, 1, -1, "test:negative") is False
    assert _scalar(path, "SELECT coins FROM user_stats WHERE user_id=1") == 500
    assert _scalar(path, "SELECT COUNT(*) FROM currency_log WHERE user_id=1") == 0
