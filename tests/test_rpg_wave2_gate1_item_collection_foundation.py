"""Wave 2 Lane C Gate 1 item/collection foundation contracts."""

import importlib
import sqlite3
import sys
from pathlib import Path

import pytest

from rpg_item_registry import (
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


def test_first_eight_art_briefs_have_complete_non_final_visual_contract():
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
        assert item["asset_path"] is None
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


def test_badge_visual_system_covers_existing_static_families(monkeypatch):
    app = _load_app(monkeypatch)
    families = {badge_visual_metadata(badge)["visual_family"] for badge in app.BADGE_DEFS}
    assert families == set(BADGE_VISUAL_SYSTEM_V1["families"])
    badge_ids = {badge["id"] for badge in app.BADGE_DEFS}
    assert {prototype["badge_id"] for prototype in BADGE_PROTOTYPE_SELECTION} <= badge_ids
    assert all(badge_visual_metadata(badge)["visual_art_status"] == "system_spec_only" for badge in app.BADGE_DEFS)


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
    assert ITEM_ART_BIBLE_V1["final_art_generated"] is False
    assert ITEM_ART_BIBLE_V1["canvas"] == "256x256"
    assert ITEM_ART_BIBLE_V1["format"] == "RGBA PNG or WebP with transparent background"
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
    assert body["badge_collection"]["is_backpack_item"] is False
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT qty FROM shop_inventory WHERE item_key='rare_appearance_fragment'").fetchone()[0] == 2


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
