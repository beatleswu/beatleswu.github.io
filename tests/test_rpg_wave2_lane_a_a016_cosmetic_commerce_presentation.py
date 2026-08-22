"""A016 contracts for canonical cosmetic commerce presentation and hiding."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "rpg-wave2-lane-a-a016-test-secret")
import app as app_module  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
SHOP = (ROOT / "shop.html").read_text(encoding="utf-8")

TARGET_IDS = {
    "robe_plain", "robe_bamboo", "robe_fox", "back_pack", "acc_dragon_pendant",
}
HIDDEN_IDS = {
    "robe_snow", "hat_scholar", "back_lantern", "back_scroll", "acc_goban_seal",
}


def test_exact_five_use_the_existing_canonical_fullbody_registry():
    registry = app_module.PURE_COSMETIC_PRESENTATION_REGISTRY
    for item_id in TARGET_IDS:
        row = registry[item_id]
        assert row["mode"] == "FULL_BODY_COSMETIC_REFERENCE"
        assert row["asset_format"] == "WEBP"
        assert row["asset_id"] == item_id
        assert (ROOT / row["asset"].lstrip("/")).is_file()


def test_product_payload_adds_canonical_art_without_changing_authority():
    for item_id in ("robe_plain", "robe_bamboo"):
        product = next(
            p for p in app_module.COSMETIC_COMMERCE_PRODUCTS
            if p["cosmetic_id"] == item_id
        )
        payload = app_module._cosmetic_product_payload(
            product, owned=False, equipped=False
        )
        art = payload["preview_asset"]
        assert art["asset"].endswith(f"/fullbody/{item_id}.webp")
        assert art["canonical_art_available"] is True
        assert art["renderer_contract"] == "canonical_asset_first_with_emoji_fallback"
        assert payload["ownership"]["source"] == "player_wardrobe.item_id"
        assert payload["combat_power"]["attack_delta"] == 0
        assert payload["combat_power"]["defense_delta"] == 0
        assert payload["combat_power"]["combat_authority"] == "NO"


def test_daily_slot_resolver_reuses_art_and_filters_hidden_records():
    slot = {"type": "appearance", "item_key": "robe_fox", "icon": "🧣"}
    decorated = app_module._decorate_daily_shop_slots([slot])
    assert decorated[0]["presentation"]["asset"].endswith("/fullbody/robe_fox.webp")
    assert app_module._decorate_daily_shop_slots([
        {"type": "appearance", "item_key": "robe_snow", "icon": "🧥"}
    ]) == []


def test_hidden_unreleased_ids_are_not_player_projected():
    assert app_module.HIDDEN_UNRELEASED_APPEARANCE_IDS == HIDDEN_IDS
    assert "_is_hidden_unreleased_appearance" in APP
    assert "if _is_hidden_unreleased_appearance(item['id']):" in APP
    assert "if not item or _is_hidden_unreleased_appearance(r['item_id']):" in APP
    assert "return _decorate_daily_shop_slots(json.loads(row['slots']))" in APP


def test_shop_uses_shared_canonical_art_renderer_for_cards_preview_and_rotation():
    assert "function cosmeticPresentationArtHTML" in SHOP
    assert "bindCanonicalCosmeticArt(grid);" in SHOP
    assert "cosmeticPresentationArtHTML(asset, artClass)" in SHOP
    assert "cosmeticPresentationArtHTML(asset, 'cosmetic-modal-art-frame')" in SHOP
    assert "cosmeticPresentationArtHTML(slot.presentation" in SHOP
    assert "data-canonical-cosmetic-art=\"yes\"" in SHOP
    assert "asset.color || '#233')}\">${cosmeticEsc(asset.emoji" not in SHOP


def test_functional_or_legacy_premium_appearances_stay_out_of_pure_pool():
    assert "robe_premium" not in TARGET_IDS
    assert "acc_premium" not in TARGET_IDS
    assert not app_module.APPEARANCE_EFFECTS.get("robe_plain", {})
    assert not app_module.APPEARANCE_EFFECTS.get("robe_bamboo", {})
    assert not app_module.APPEARANCE_EFFECTS.get("robe_fox", {})
    assert not app_module.APPEARANCE_EFFECTS.get("back_pack", {})
    assert not app_module.APPEARANCE_EFFECTS.get("acc_dragon_pendant", {})
    assert app_module.APPEARANCE_EFFECTS.get("robe_premium")
    assert app_module.APPEARANCE_EFFECTS.get("acc_premium")

