"""Contract tests for the review-only W2-03 wooden-sword A/B proof."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "assets/hero/equipment/wearables/wearable_registry.json"
RUNTIME = ROOT / "js/rpg_wave2_wearable_renderer.js"
REVIEW = ROOT / "docs/planning/w2_03_hero_wearable_weapon_hand_layer_ab_proof_002r3.html"
WOODEN_SWORD = ROOT / "assets/hero/equipment/wearables/overlays/wooden_sword.png"


def _registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_r2_default_remains_the_canonical_variant_and_b_is_review_only():
    wooden_sword = _registry()["equipment"]["wooden_sword"]
    assert wooden_sword["layer"] == "BACK_WEAPON"
    assert wooden_sword["presentation_transform"] == {
        "mode": "CARRIED_AT_HIP",
        "offset_percent": {"x": -12, "y": -7},
        "scale": 0.95,
        "transform_origin": "center center",
        "occlusion": "BACK_WEAPON",
    }
    variant = wooden_sword["review_presentation_variants"]["FRONT_WEAPON_HAND_ALIGNED"]
    assert variant["review_only"] is True
    assert variant["owner_selection_required"] is True
    assert variant["target"] == "RIGHT_PALM"
    assert variant["layer"] == "FRONT_WEAPON"
    assert variant["presentation_transform"]["mode"] == "FRONT_WEAPON_HAND_ALIGNED"
    assert variant["presentation_transform"]["occlusion"] == "FRONT_WEAPON"


def test_only_wooden_sword_has_the_owner_review_variant():
    equipment = _registry()["equipment"]
    assert [item_id for item_id, item in equipment.items()
            if "review_presentation_variants" in item] == ["wooden_sword"]


def test_renderer_keeps_variant_opt_in_and_preserves_authority_boundary():
    runtime = RUNTIME.read_text(encoding="utf-8")
    assert "options?.presentationVariant" in runtime
    assert "variant.review_only !== true" in runtime
    assert "appendEntries('FRONT_WEAPON')" in runtime
    assert "server_equipped_projection" in runtime
    assert "gameplayAuthority = 'none'" in runtime
    assert "method: 'POST'" not in runtime
    assert "localStorage" not in runtime


def test_review_page_uses_existing_art_and_requires_owner_selection():
    review = REVIEW.read_text(encoding="utf-8")
    assert "wooden_sword" in review
    assert "presentationVariant = 'FRONT_WEAPON_HAND_ALIGNED'" in review
    assert "OWNER_SELECTION_REQUIRED=YES" in review
    assert "assets/hero/characters/wave2_p1/apprentice_p1.png" in review
    assert "assets/hero/equipment/wearables/overlays/wooden_sword.png" not in review
    assert WOODEN_SWORD.exists()


def test_non_targeted_accepted_equipment_layers_remain_unchanged():
    equipment = _registry()["equipment"]
    assert equipment["dragon_scale"]["layer"] == "TORSO_ARMOR"
    assert equipment["lucky_stone"]["layer"] == "FRONT_ACCESSORY"
    assert "review_presentation_variants" not in equipment["dragon_scale"]
    assert "review_presentation_variants" not in equipment["lucky_stone"]
