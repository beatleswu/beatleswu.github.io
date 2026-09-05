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


def test_owner_selected_variant_b_is_now_the_single_canonical_variant():
    wooden_sword = _registry()["equipment"]["wooden_sword"]
    assert wooden_sword["layer"] == "FRONT_WEAPON"
    assert wooden_sword["anchor"] == "right_palm"
    assert wooden_sword["presentation_mode"] == "HAND_HELD"
    assert wooden_sword["presentation_attachment"] == "RIGHT_PALM"
    assert wooden_sword["presentation_transform"] == {
        "mode": "FRONT_WEAPON_HAND_ALIGNED",
        "offset_percent": {"x": 5, "y": 3},
        "rotation_deg": 0,
        "scale": 0.95,
        "transform_origin": "center center",
        "occlusion": "FRONT_WEAPON",
    }
    assert "review_presentation_variants" not in wooden_sword


def test_no_runtime_item_keeps_a_review_only_presentation_variant():
    equipment = _registry()["equipment"]
    assert [item_id for item_id, item in equipment.items()
            if "review_presentation_variants" in item] == []


def test_renderer_promotes_canonical_layer_and_preserves_authority_boundary():
    runtime = RUNTIME.read_text(encoding="utf-8")
    assert "appendEntries('FRONT_WEAPON')" in runtime
    assert "server_equipped_projection" in runtime
    assert "gameplayAuthority = 'none'" in runtime
    assert "presentationVariant" not in runtime
    assert "review_presentation_variants" not in runtime
    assert "method: 'POST'" not in runtime
    assert "localStorage" not in runtime


def test_historical_review_page_uses_existing_art_and_remains_non_runtime_evidence():
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
