"""A017 visual-legibility contracts for the two remaining V1 candidates."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "rpg-wave2-lane-a-a017-test-secret")
import app as app_module  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
SHOP = (ROOT / "shop.html").read_text(encoding="utf-8")

TARGET_IDS = {"back_pack", "acc_dragon_pendant"}
PREVIOUS_PASSING_IDS = {"robe_plain", "robe_bamboo", "robe_fox"}
HIDDEN_IDS = {
    "robe_snow", "hat_scholar", "back_lantern", "back_scroll", "acc_goban_seal",
}


def test_target_focal_detail_uses_existing_canonical_fullbody_art():
    for item_id in TARGET_IDS:
        metadata = app_module._cosmetic_presentation_metadata(item_id)
        assert metadata["asset"].endswith(f"/fullbody/{item_id}.webp")
        assert metadata["asset_format"] == "WEBP"
        assert metadata["pure_presentation"] is True
        assert metadata["functional_effect_count"] == 0
        assert metadata["combat_authority"] == "NO"
        assert metadata["focal_detail"]["variant"] in {"back-pack", "dragon-pendant"}
        assert (ROOT / metadata["asset"].lstrip("/")).is_file()


def test_visual_candidates_are_read_only_and_exactly_two():
    candidates = app_module._cosmetic_visual_review_candidates()
    assert {candidate["cosmetic_id"] for candidate in candidates} == TARGET_IDS
    assert len(candidates) == 2
    for candidate in candidates:
        assert candidate["preview_only"] is True
        assert candidate["purchase_available"] is False
        assert candidate["equip_available"] is False
        assert candidate["ownership_authority"] == "player_wardrobe.item_id"
        assert candidate["combat_power"]["attack_delta"] == 0
        assert candidate["combat_power"]["defense_delta"] == 0
        assert candidate["combat_power"]["combat_authority"] == "NO"
        assert "price" not in candidate


def test_hidden_records_are_not_visual_candidates():
    candidates = app_module._cosmetic_visual_review_candidates()
    assert not ({candidate["cosmetic_id"] for candidate in candidates} & HIDDEN_IDS)
    assert app_module.HIDDEN_UNRELEASED_APPEARANCE_IDS == frozenset(HIDDEN_IDS)


def test_previous_three_passing_ids_remain_pure_and_unmodified_by_focus_contract():
    assert not (PREVIOUS_PASSING_IDS & set(app_module._COSMETIC_FOCAL_DETAILS))
    for item_id in PREVIOUS_PASSING_IDS:
        assert not app_module.APPEARANCE_EFFECTS.get(item_id, {})


def test_app_exposes_candidates_without_replacing_commerce_authority():
    assert "presentation_candidates" in APP
    assert "COSMETIC_VISUAL_REVIEW_CANDIDATE_IDS" in APP
    assert "purchase_available" in APP
    assert "equip_available" in APP
    assert "player_wardrobe.item_id" in APP
    assert "COSMETIC_COMMERCE_PRODUCTS.product_id" in APP


def test_shop_renders_focus_detail_for_cards_daily_and_preview():
    assert "focal_detail" in SHOP
    assert "cosmetic-art-focus-detail" in SHOP
    assert "cosmetic-art--focus-back-pack" in SHOP
    assert "cosmetic-art--focus-dragon-pendant" in SHOP
    assert "presentation_candidates" in SHOP
    assert "data-cosmetic-visual-preview" in SHOP
    assert "showCosmeticPreview(product)" in SHOP
    assert "No purchase, ownership, equip, or payment mutation." in SHOP


def test_no_emoji_or_legacy_renderer_is_used_when_canonical_target_art_exists():
    assert "canonical_art_available: true" not in SHOP.lower()
    assert "asset.canonical_art_available !== false" in SHOP
    assert "cosmetic-art-main" in SHOP
    assert "cosmetic-art-detail-img" in SHOP
