"""A018 truthful back-pack projection and visual-closure contracts."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

os.environ.setdefault("SECRET_KEY", "rpg-wave2-lane-a-a018-test-secret")
import app as app_module  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
SHOP = (ROOT / "shop.html").read_text(encoding="utf-8")
BACKPACK_ASSET = ROOT / "assets/hero/items/fullbody/back_pack.webp"


def test_canonical_source_contains_real_back_pack_pixels():
    metadata = app_module._cosmetic_presentation_metadata("back_pack")
    detail = metadata["focal_detail"]
    assert metadata["asset"] == "/assets/hero/items/fullbody/back_pack.webp"
    assert detail["region"] == "side_back_pack"
    assert detail["projection"] == "canonical_fullbody_side_rear_pixels"
    assert detail["source_region"] == {
        "x": 0.54,
        "y": 0.14,
        "width": 0.34,
        "height": 0.42,
    }
    with Image.open(BACKPACK_ASSET) as image:
        assert image.size == (1056, 1408)
        assert image.mode == "RGBA"
        region = detail["source_region"]
        crop = image.crop(
            (
                int(image.width * region["x"]),
                int(image.height * region["y"]),
                int(image.width * (region["x"] + region["width"])),
                int(image.height * (region["y"] + region["height"])),
            )
        )
        assert crop.getchannel("A").getbbox() is not None


def test_back_pack_uses_truthful_focus_projection_not_legacy_svg_or_emoji():
    assert "canonicalAsset" in SHOP
    assert "asset.canonical_art_available !== false" in SHOP
    assert "cosmetic-art--focus-back-pack" in SHOP
    assert "transform:scale(3); transform-origin:82% 38%;" in SHOP
    assert "canonical_fullbody_side_rear_pixels" in (ROOT / "app.py").read_text(encoding="utf-8")
    assert "assets/hero/items/back_pack.svg" not in SHOP
    assert "🎒" not in SHOP


def test_previous_four_candidates_and_hidden_cosmetics_remain_unchanged():
    focal = app_module._COSMETIC_FOCAL_DETAILS
    assert {"robe_plain", "robe_bamboo", "robe_fox"}.isdisjoint(focal)
    assert focal["acc_dragon_pendant"] == {
        "variant": "dragon-pendant",
        "label": "配飾特寫",
        "label_en": "Accessory detail",
        "region": "upper_torso",
        "note": "放大胸前玉佩與龍形吊墜，仍保留角色全身作為上下文。",
        "note_en": "A focused upper-torso detail makes the jade dragon pendant identifiable while keeping the full-body context.",
    }
    assert app_module.HIDDEN_UNRELEASED_APPEARANCE_IDS == frozenset(
        {"robe_snow", "hat_scholar", "back_lantern", "back_scroll", "acc_goban_seal"}
    )
    assert {candidate["cosmetic_id"] for candidate in app_module._cosmetic_visual_review_candidates()} == {
        "back_pack", "acc_dragon_pendant"
    }


def test_back_pack_remains_pure_presentation_and_non_mutating():
    metadata = app_module._cosmetic_presentation_metadata("back_pack")
    candidate = next(
        item for item in app_module._cosmetic_visual_review_candidates()
        if item["cosmetic_id"] == "back_pack"
    )
    assert metadata["pure_presentation"] is True
    assert metadata["functional_effect_count"] == 0
    assert metadata["combat_authority"] == "NO"
    assert candidate["preview_only"] is True
    assert candidate["purchase_available"] is False
    assert candidate["equip_available"] is False
    assert "price" not in candidate
