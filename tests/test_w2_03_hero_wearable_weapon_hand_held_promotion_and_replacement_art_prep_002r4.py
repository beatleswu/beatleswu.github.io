"""Focused contract for the Owner-selected W2-03 hand-held promotion."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "assets/hero/equipment/wearables/wearable_registry.json"
TEMPLATES = ROOT / "docs/planning/rpg_modular_2d_equipment/templates.json"
VISIBILITY = ROOT / "docs/planning/rpg_modular_2d_equipment/visibility_matrix.json"
COMPATIBILITY = ROOT / "docs/planning/rpg_modular_2d_equipment/renderer_compatibility.json"
SPEC = ROOT / (
    "docs/planning/"
    "w2_03_hero_wearable_weapon_hand_held_promotion_and_replacement_art_prep_002r4.json"
)
RUNTIME = ROOT / "js/rpg_wave2_wearable_renderer.js"
APP = ROOT / "app.py"
WOODEN_SWORD = ROOT / "assets/hero/equipment/wearables/overlays/wooden_sword.png"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_owner_selected_variant_b_is_the_only_canonical_wooden_sword_path():
    registry = _json(REGISTRY)
    item = registry["equipment"]["wooden_sword"]

    assert registry["provenance"]["hand_held_static_mode"] == "OWNER_SELECTED_PER_ITEM"
    assert registry["provenance"]["owner_selected_hand_held_item"] == "wooden_sword"
    assert item == {
        **item,
        "wearable_class": "WEAPON_HAND_HELD",
        "anchor": "right_palm",
        "layer": "FRONT_WEAPON",
        "template_id": "WEAPON_HAND_HELD",
        "presentation_mode": "HAND_HELD",
        "presentation_attachment": "RIGHT_PALM",
        "presentation_transform": {
            "mode": "FRONT_WEAPON_HAND_ALIGNED",
            "offset_percent": {"x": 5, "y": 3},
            "rotation_deg": 0,
            "scale": 0.95,
            "transform_origin": "center center",
            "occlusion": "FRONT_WEAPON",
        },
    }
    assert "review_presentation_variants" not in item
    assert "CARRIED_AT_HIP" not in json.dumps(item)
    assert WOODEN_SWORD.is_file()


def test_renderer_uses_generic_per_item_front_weapon_metadata_without_review_switch():
    runtime = RUNTIME.read_text(encoding="utf-8")

    assert runtime.count("appendEntries('FRONT_WEAPON')") == 1
    assert "presentation?.presentation_transform" in runtime
    assert "presentation?.presentation_mode" in runtime
    assert "presentation?.presentation_attachment" in runtime
    assert "rotation_deg ?? 0" in runtime
    assert "Math.abs(rotation) <= 180" in runtime
    assert "presentationVariant" not in runtime
    assert "review_presentation_variants" not in runtime
    assert "review_only" not in runtime
    assert "wooden_sword" not in runtime
    assert "server_equipped_projection" in runtime
    assert "gameplayAuthority = 'none'" in runtime
    assert "method: 'POST'" not in runtime
    assert "localStorage" not in runtime


def test_modular_contract_records_the_narrow_owner_selected_template():
    templates = _json(TEMPLATES)
    template = templates["templates"]["WEAPON_HAND_HELD"]
    assert template["anchor"] == "right_palm"
    assert template["front_back_layer"] == ["FRONT_WEAPON"]
    assert "no_wrist_only_attachment" in template["occlusion_rule"]
    assert "no_hero_anatomy_redraw" in template["occlusion_rule"]

    visibility = _json(VISIBILITY)
    wood = next(row for row in visibility["items"] if row["equipment_id"] == "wooden_sword")
    assert wood["wearable_class"] == "WEAPON_HAND_HELD"
    assert wood["template_id"] == "WEAPON_HAND_HELD"
    assert wood["anchor"] == "right_palm"
    assert wood["layer"] == "FRONT_WEAPON"
    assert wood["presentation_mode"] == "HAND_HELD"
    assert wood["presentation_attachment"] == "RIGHT_PALM"

    compatibility = _json(COMPATIBILITY)
    assert compatibility["supported_contract"]["layer_order"][3] == "FRONT_WEAPON"
    assert compatibility["static_weapon_contract"]["hand_held_static_mode"] == (
        "OWNER_SELECTED_PER_ITEM"
    )
    assert compatibility["static_weapon_contract"]["owner_selected_per_item"] == {
        "wooden_sword": {
            "presentation": "HAND_HELD",
            "attachment": "RIGHT_PALM",
            "layer": "FRONT_WEAPON",
        }
    }


def test_replacement_art_specs_are_exact_and_do_not_create_runtime_art():
    spec = _json(SPEC)
    assert spec["task_id"] == (
        "W2_03_HERO_WEARABLE_WEAPON_HAND_HELD_PROMOTION_AND_REPLACEMENT_ART_PREP_002R4"
    )
    assert spec["new_art_created"] is False
    assert spec["canonical_wooden_sword"]["runtime_paths"] == 1
    assert spec["canonical_wooden_sword"]["review_only_override"] is False

    replacements = {row["item_id"]: row for row in spec["replacement_art"]}
    assert set(replacements) == {"cloth_robe", "fox_pelt"}
    assert replacements["cloth_robe"]["slot"] == "armor"
    assert replacements["cloth_robe"]["target_layer"] == "TORSO_ARMOR"
    assert replacements["fox_pelt"]["slot"] == "armor"
    assert replacements["fox_pelt"]["target_layer"] == "BACK_BODY"
    for row in replacements.values():
        assert row["transparent_background_required"] is True
        assert row["canvas_anchor_requirement"]["canvas"] == [1056, 1408]
        assert row["canvas_anchor_requirement"]["frame"] == "PLAYER_FRAME_A_STANDARD_CHIBI"
        assert row["hero_body_alignment_requirement"]
        assert row["occlusion_requirement"]
        assert row["target_silhouette"]


def test_accepted_visuals_and_authority_policies_remain_unchanged():
    registry = _json(REGISTRY)["equipment"]
    assert registry["dragon_scale"]["layer"] == "TORSO_ARMOR"
    assert registry["lucky_stone"]["layer"] == "FRONT_ACCESSORY"
    assert registry["dragon_scale"]["presentation_only"] is True
    assert registry["lucky_stone"]["presentation_only"] is True

    spec = _json(SPEC)
    assert spec["policy"]["xp_amulet"] == "HOLD_FOR_AUTHORITY"
    assert spec["policy"]["go_stone_black"] == "INVENTORY_ONLY"
    assert spec["policy"]["renderer_gameplay_authority"] is False
    assert spec["preserved"]["dragon_scale"] is True
    assert spec["preserved"]["lucky_stone"] is True

    # app.py owns the server projection metadata and is deliberately outside
    # this visual-only promotion; no source writer may turn the renderer into
    # an ownership/equip authority.
    app = APP.read_text(encoding="utf-8")
    assert "FUNCTIONAL_EQUIPMENT_PRESENTATION_REGISTRY" in app
    assert "def _functional_equipment_presentation_projection" in app
