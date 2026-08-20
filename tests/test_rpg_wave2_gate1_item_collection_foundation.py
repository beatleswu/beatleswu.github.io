"""Wave 2 Lane C Gate 1 item/collection foundation contracts."""

import importlib
import sqlite3
import sys
from pathlib import Path

import pytest

from rpg_item_registry import (
    BADGE_PROTOTYPE_ASSETS,
    BADGE_PROTOTYPE_SELECTION,
    BADGE_VISUAL_SYSTEM_V1,
    ITEM_ART_BIBLE_V1,
    LIVE_ITEM_ART_PACK_8,
    BUNDLE_POLISH_PACK_6,
    NON_EQUIPMENT_DROP_INTERFACE,
    ZONE_MATERIAL_DESIGN_CONTRACT,
    build_shop_product_grant_registry,
    badge_visual_metadata,
)


ROOT = Path(__file__).resolve().parents[1]
TEST_SECRET = "test-only-wave2-item-journal-secret"


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


def _load_app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET)
    monkeypatch.setenv("GO_ODYSSEY_LIVE_STATIC_ROOT", str(ROOT))
    sys.path.insert(0, str(ROOT))
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def test_first_eight_art_pack_has_complete_integrated_visual_contract():
    assert set(LIVE_ITEM_ART_PACK_8) == {
        "rare_appearance_fragment",
        "pet_evolution_core",
        "ai_analysis_pack",
        "collector_archive_crate",
        "growth_vault",
        "go_spirit_candy",
        "starfruit",
        "moon_drop",
    }
    required = {
        "item_id", "name", "name_en", "category", "current_ownership",
        "current_effect", "current_source", "current_art", "canonical_art_key",
        "icon_concept", "silhouette", "primary_material", "world_visual_language",
        "mobile_readability", "art_priority",
    }
    for item_id, item in LIVE_ITEM_ART_PACK_8.items():
        assert required <= set(item), item_id
        assert item["item_id"] == item_id
        assert item["asset_path"].startswith("/assets/items/")
        assert item["asset_path"].endswith(".svg")
        assert item["art_status"] == "dedicated_asset"
        asset = ROOT.joinpath(*item["asset_path"].lstrip("/").split("/"))
        assert asset.is_file(), item_id
        asset_text = asset.read_text(encoding="utf-8")
        assert "<svg" in asset_text
        assert "_ph_" not in asset_text
        assert "emoji" not in asset_text.lower()
        assert item["art_priority"] in {"P0", "P1"}
        assert item["canonical_art_key"].startswith("item.")


def test_bundle_pack_is_explicit_and_not_a_second_ownership_model():
    assert set(BUNDLE_POLISH_PACK_6) == {
        "premium_hint_bundle",
        "ai_explain_ticket_bundle",
        "pet_snack",
        "starfruit_basket",
        "moon_dew_vial",
        "pet_feast_box",
    }
    for product_id, bundle in BUNDLE_POLISH_PACK_6.items():
        assert bundle["product_id"] == product_id
        assert bundle["grants"]
        assert "立即獲得" in bundle["display_copy"]
        assert "Contains" in bundle["display_copy_en"]
        assert "persistent" not in bundle["display_copy"].lower()


def test_shop_product_registry_preserves_all_current_products_and_server_price_authority(monkeypatch):
    app = _load_app(monkeypatch)
    registry = build_shop_product_grant_registry(app.SHOP_ITEMS, app.PET_FOOD_CATALOG)
    assert len(registry) == 21
    assert {entry["product_id"] for entry in registry} == set(app.SHOP_ITEMS)
    assert all(entry["price_authority"].startswith("server:") for entry in registry)
    assert all("price" not in entry for entry in registry)
    by_id = {entry["product_id"]: entry for entry in registry}
    assert by_id["pet_snack"]["persistent_product_ownership"] is False
    assert by_id["pet_snack"]["granted_ids"] == ["go_spirit_candy"]
    assert by_id["moon_dew_vial"]["granted_ids"] == ["moon_drop"]
    assert by_id["extra_questions"]["art_status"] == "shared_asset"
    for product_id, entry in by_id.items():
        product = app.SHOP_ITEMS[product_id]
        expected = product.get("grants_items") or product.get("grants_food") or {product_id: 1}
        assert entry["quantities"] == {key: int(value) for key, value in expected.items()}
        assert entry["persistent_product_ownership"] == (not bool(
            product.get("grants_items") or product.get("grants_food")
        ))


def test_shop_uses_server_price_and_grants_components_without_bundle_ownership(tmp_path, monkeypatch):
    app = _load_app(monkeypatch)
    path = tmp_path / "shop-authority.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE user_stats (user_id INTEGER PRIMARY KEY, coins INTEGER NOT NULL);
            CREATE TABLE shop_inventory (user_id INTEGER, item_key TEXT, qty INTEGER, UNIQUE(user_id,item_key));
            CREATE TABLE currency_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, delta INTEGER, balance_after INTEGER, reason TEXT, created_at TEXT);
            INSERT INTO user_stats VALUES (1, 500), (2, 0);
            """
        )
    monkeypatch.setattr(app, "get_db", lambda: _DbContext(path))
    monkeypatch.setattr(app, "_daily_shop_slots", lambda conn: [])
    app.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
    purchased = client.post(
        "/api/shop/buy",
        json={"item_key": "premium_hint_bundle", "price": 1},
    )
    assert purchased.status_code == 200
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 370
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='hint_ticket'"
        ).fetchone()[0] == 5
        assert conn.execute(
            "SELECT COUNT(*) FROM shop_inventory WHERE user_id=1 AND item_key='premium_hint_bundle'"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT delta FROM currency_log WHERE user_id=1"
        ).fetchone()[0] == -130

    with client.session_transaction() as session:
        session["user_id"] = 2
    failed = client.post(
        "/api/shop/buy",
        json={"item_key": "hint_ticket", "price": -999},
    )
    assert failed.status_code == 400
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=2").fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM shop_inventory WHERE user_id=2"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM currency_log WHERE user_id=2"
        ).fetchone()[0] == 0


def test_badge_visual_system_covers_existing_static_families(monkeypatch):
    app = _load_app(monkeypatch)
    families = {badge_visual_metadata(badge)["visual_family"] for badge in app.BADGE_DEFS}
    assert families == set(BADGE_VISUAL_SYSTEM_V1["families"])
    badge_ids = {badge["id"] for badge in app.BADGE_DEFS}
    assert len(BADGE_PROTOTYPE_SELECTION) == 10
    assert {prototype["family"] for prototype in BADGE_PROTOTYPE_SELECTION} == set(BADGE_VISUAL_SYSTEM_V1["families"])
    assert {prototype["badge_id"] for prototype in BADGE_PROTOTYPE_SELECTION} <= badge_ids
    assert {prototype["family"] for prototype in BADGE_PROTOTYPE_SELECTION} == set(BADGE_PROTOTYPE_ASSETS)
    prototype_ids = {prototype["badge_id"] for prototype in BADGE_PROTOTYPE_SELECTION}
    for badge in app.BADGE_DEFS:
        metadata = badge_visual_metadata(badge)
        expected = "prototype_asset" if badge["id"] in prototype_ids else "system_spec_only"
        assert metadata["visual_art_status"] == expected
        if badge["id"] in prototype_ids:
            assert metadata["prototype_asset"].endswith(".svg")


def test_badge_visual_metadata_does_not_activate_community_awards(monkeypatch):
    app = _load_app(monkeypatch)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE badges_earned (user_id INTEGER, badge_id TEXT, earned_at TEXT, seen INTEGER DEFAULT 0)")
    awarded = app.check_and_award(conn, 1, {
        "rank_level": "LV50",
        "total_correct": 99999,
        "current_streak": 999,
        "max_streak": 999,
        "mistake_corrected": 999,
        "xp": 99999,
        "max_combo": 999,
    })
    assert "badge_lb_weekly_1" not in awarded
    assert not conn.execute(
        "SELECT 1 FROM badges_earned WHERE badge_id='badge_lb_weekly_1'"
    ).fetchone()
    conn.close()


def test_zone_material_and_drop_contracts_keep_item_power_and_drop_authority_server_side():
    assert ZONE_MATERIAL_DESIGN_CONTRACT["identity_fields"] == (
        "ITEM_ID", "DISPLAY_NAME", "ZONE_ID", "MONSTER_FAMILY",
        "RARITY_IF_NEEDED", "SOURCE_TYPE", "QUEST_ROLE", "COLLECTION_ROLE",
        "SHOP_ALLOWED", "COMBAT_POWER", "ASSET_KEY",
    )
    assert ZONE_MATERIAL_DESIGN_CONTRACT["rules"]["COMBAT_POWER"] == "NONE"
    assert ZONE_MATERIAL_DESIGN_CONTRACT["rules"]["SHOP_ALLOWED_DEFAULT"] == "NO"
    assert NON_EQUIPMENT_DROP_INTERFACE["client_authority"] == "none"
    assert NON_EQUIPMENT_DROP_INTERFACE["drop_rate_authority"] == "unchanged and server-side"


def test_item_art_bible_forbids_emoji_and_placeholders_as_final_art():
    assert ITEM_ART_BIBLE_V1["final_art_generated"] is True
    assert "P1" in ITEM_ART_BIBLE_V1["final_art_scope"]
    assert ITEM_ART_BIBLE_V1["canvas"] == "256x256"
    assert "SVG" in ITEM_ART_BIBLE_V1["format"]
    assert "No emoji as final art" in ITEM_ART_BIBLE_V1["prohibitions"]
    assert "No _ph_* placeholder as production art" in ITEM_ART_BIBLE_V1["prohibitions"]
    assert "Chest art does not imply chest ownership" in ITEM_ART_BIBLE_V1["prohibitions"]


def test_item_journal_api_is_read_only_and_projects_existing_stores(tmp_path, monkeypatch):
    app = _load_app(monkeypatch)
    path = tmp_path / "item-journal.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE shop_inventory (user_id INTEGER, item_key TEXT, qty INTEGER, UNIQUE(user_id,item_key));
            CREATE TABLE pet_inventory (user_id INTEGER, item_key TEXT, qty INTEGER, UNIQUE(user_id,item_key));
            CREATE TABLE badges_earned (user_id INTEGER, badge_id TEXT, earned_at TEXT, seen INTEGER DEFAULT 0);
            CREATE TABLE currency_log (id INTEGER PRIMARY KEY, user_id INTEGER, delta INTEGER, balance_after INTEGER, reason TEXT, created_at TEXT);
            CREATE TABLE gacha_log (id INTEGER PRIMARY KEY, user_id INTEGER, result_key TEXT, created_at TEXT);
            INSERT INTO shop_inventory VALUES (1, 'rare_appearance_fragment', 2);
            INSERT INTO shop_inventory VALUES (1, 'unapproved_runtime_item', 99);
            INSERT INTO pet_inventory VALUES (1, 'starfruit', 3);
            INSERT INTO badges_earned VALUES (1, 'streak_3', '2026-08-20T00:00:00', 0);
            INSERT INTO currency_log VALUES (1, 1, -980, 20, 'buy:rare_appearance_fragmentx1', '2026-08-20T00:00:00');
            """
        )
    monkeypatch.setattr(app, "get_db", lambda: _DbContext(path))
    app.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1

    response = client.get("/api/item-journal")
    assert response.status_code == 200
    body = response.get_json()
    assert len(body["items"]) == 24
    assert body["mutation_boundary"] == {
        "ownership_mutation": 0,
        "purchase_mutation": 0,
        "equip_mutation": 0,
        "journal_write": 0,
    }
    items = {item["item_id"]: item for item in body["items"]}
    assert items["rare_appearance_fragment"]["owned_amount"] == 2
    assert items["starfruit"]["owned_amount"] == 3
    assert items["rare_appearance_fragment"]["recently_obtained"] is True
    assert "unapproved_runtime_item" not in items
    assert body["badge_collection"]["is_backpack_item"] is False
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT qty FROM shop_inventory WHERE item_key='rare_appearance_fragment'").fetchone()[0] == 2


def test_item_journal_route_contains_no_mutation_operation():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("@app.route('/api/item-journal')")
    end = source.index("# ── 商城 API", start)
    route = source[start:end]
    assert "SELECT " in route
    assert "INSERT" not in route
    assert "UPDATE" not in route
    assert "DELETE" not in route
    assert "commit(" not in route


def test_item_journal_and_shop_presentation_contracts_are_present():
    journal = (ROOT / "item_journal.html").read_text(encoding="utf-8")
    shop = (ROOT / "shop.html").read_text(encoding="utf-8")
    bible = (ROOT / "GO_ODYSSEY_RPG_VISUAL_BIBLE.md").read_text(encoding="utf-8")
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    journal_lower = journal.lower()
    for token in (
        "Item categories", "owned_amount", "Effect / Use", "where to get more",
        "recently_obtained", "Read-only projection", "/api/item-journal",
        "/inventory", "/hero?tab=appearance", "/badges",
    ):
        assert token.lower() in journal_lower
    assert "立即獲得" in shop
    assert "Contains" in shop
    assert "productRegistryEntry" in shop
    assert "def item_journal_page()" in app_source
    assert "'item_journal.html'" in app_source
    for token in (
        "rare_appearance_fragment", "pet_evolution_core", "ai_analysis_pack",
        "collector_archive_crate", "growth_vault", "go_spirit_candy", "starfruit", "moon_drop",
        "ZONE_ID", "MONSTER_FAMILY", "COMBAT_POWER", "server settlement",
    ):
        assert token in bible
