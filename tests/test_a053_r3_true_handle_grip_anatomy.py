"""Focused tests for the A053-R3 true-handle-grip visual refinement.

These tests cover deterministic composition and authority invariants.  They
do not grant Owner visual acceptance; the review pack remains a human visual
gate.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.a053_r3_true_handle_grip_anatomy import (  # noqa: E402
    CANVAS,
    CHARACTER_BASE_PATH,
    CONTRACT_PATH,
    GRIP_ANCHOR,
    IMPLEMENTED_SLOT,
    POSE_FAMILY,
    R2_GRIP_LAYER_PATH,
    R2_MASK_PATH,
    R3_GRIP_LAYER_PATH,
    R3_MASK_PATH,
    REVIEW_ROOT,
    WEAPON_SPECS,
    _sha256,
    compose,
    compose_layers,
    prototype_transform_nodes,
    resolve_presentation,
    resolve_world_transform,
    transform_point,
    weapon_layer_and_grip,
)


WEAPONS = ("wooden_sword", "iron_sword", "fox_fang")


def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_r2_parent_and_r3_derived_assets_are_separate_and_immutable():
    report = _contract()
    assert R2_GRIP_LAYER_PATH != R3_GRIP_LAYER_PATH
    assert R2_MASK_PATH != R3_MASK_PATH
    assert report["character"]["r2_grip_layer"]["sha256"] == _sha256(R2_GRIP_LAYER_PATH)
    assert report["character"]["r2_mask_sha256"] == _sha256(R2_MASK_PATH)
    assert report["character"]["r3_grip_layer"]["sha256"] == _sha256(R3_GRIP_LAYER_PATH)
    assert report["character"]["r3_mask"]["sha256"] == _sha256(R3_MASK_PATH)
    assert CHARACTER_BASE_PATH.is_file()


def test_r3_local_grip_asset_and_suppression_mask_have_expected_formats():
    with Image.open(R3_GRIP_LAYER_PATH) as image:
        assert image.mode == "RGBA"
        assert image.size == (340, 380)
        assert image.getchannel("A").getbbox() is not None
    with Image.open(R3_MASK_PATH) as image:
        assert image.mode == "L"
        assert image.size == CANVAS
        assert image.getextrema() == (0, 255)
        assert image.getbbox() is not None


def test_paper_doll_has_exact_three_layers_and_semantic_parentage():
    report = _contract()
    parents = {entry["node_id"]: entry["parent"] for entry in report["transform_hierarchy"]}
    assert parents == {
        "CHARACTER_ROOT": None,
        "BODY": "CHARACTER_ROOT",
        "RIGHT_ARM": "BODY",
        "RIGHT_HAND": "RIGHT_ARM",
        "GRIP_ANCHOR": "RIGHT_HAND",
        "MAIN_HAND_WEAPON": "GRIP_ANCHOR",
        "FRONT_GRIP_HAND": "RIGHT_HAND",
    }
    assert report["layers"] == [
        {
            "order": 10,
            "layer_id": "CHARACTER_BASE",
            "parent": "BODY",
            "asset": "assets/hero/characters/wave2_p1/apprentice_p1.png",
            "mask": "docs/planning/a053_r3_true_handle_grip_anatomy/masks/apprentice_open_hand_suppression_r3.png",
        },
        {"order": 20, "layer_id": "MAIN_HAND_WEAPON", "parent": "GRIP_ANCHOR", "local_origin": "weapon grip point"},
        {
            "order": 30,
            "layer_id": "FRONT_GRIP_HAND",
            "parent": "RIGHT_HAND",
            "asset": "docs/planning/a053_r3_true_handle_grip_anatomy/assets/apprentice_grip_forearm_r3.png",
            "semantic_role": "localized true-handle grip anatomy",
        },
    ]
    assert tuple(compose_layers("wooden_sword")) == ("CHARACTER_BASE", "MAIN_HAND_WEAPON", "FRONT_GRIP_HAND")


def test_shared_anchor_and_independent_weapon_grip_points_are_preserved():
    report = _contract()
    anchor = report["character"]["grip_anchor"]
    assert (anchor["x"], anchor["y"]) == GRIP_ANCHOR
    assert tuple(anchor["normalized"]) == (GRIP_ANCHOR[0] / CANVAS[0], GRIP_ANCHOR[1] / CANVAS[1])
    assert tuple(report["weapons"]) == WEAPONS
    assert len({tuple(report["weapons"][weapon]["grip_point_normalized"]) for weapon in WEAPONS}) == 3
    for weapon in WEAPONS:
        spec = report["weapons"][weapon]
        assert spec["slot"] == IMPLEMENTED_SLOT
        assert spec["pose_family"] == POSE_FAMILY
        assert spec["weapon_independent_grip_layer"] is True


def test_authoritative_equipped_item_controls_visibility_and_default_fallback():
    default = compose(None)
    assert default.size == CANVAS
    assert default.getchannel("A").getbbox() is not None
    assert compose("unknown_item").tobytes() == default.tobytes()
    for weapon in WEAPONS:
        assert resolve_presentation(weapon) == {"pose_family": POSE_FAMILY, "weapon_id": weapon}
        final = compose(weapon)
        assert final.size == CANVAS
        assert final.getchannel("A").getbbox() is not None
        assert final.tobytes() != default.tobytes()
    assert resolve_presentation(None) == {"pose_family": "DEFAULT_POSE", "weapon_id": None}


def test_all_supported_weapon_layers_are_frame_safe():
    for weapon in WEAPONS:
        layer, world_grip = weapon_layer_and_grip(weapon)
        assert layer.size == CANVAS
        assert world_grip == GRIP_ANCHOR
        bbox = layer.getchannel("A").getbbox()
        assert bbox is not None
        assert bbox[0] >= 0 and bbox[1] >= 0 and bbox[2] <= CANVAS[0] and bbox[3] <= CANVAS[1]


def test_true_grip_visual_contract_is_explicit_without_owner_pass():
    report = _contract()
    assessment = report["visual_self_assessment"]
    assert report["owner_visual_acceptance"] == "NOT_GRANTED"
    assert assessment["r2_proportions_preserved"] is True
    assert assessment["grip_hand_oversized"] is False
    assert assessment["hand_scale_matches_character"] is True
    assert assessment["forearm_to_wrist_contour_continuous"] is True
    assert assessment["wrist_to_hand_direction_natural"] is True
    assert assessment["detached_replacement_hand_appearance"] is False
    assert assessment["weapon_handle_enters_palm"] is True
    assert assessment["front_fingers_occlude_handle"] is True
    assert assessment["thumb_opposes_fingers"] is True
    assert assessment["handle_behind_required_fingers"] is True
    assert assessment["floating_fist_appearance"] is False
    assert assessment["pasted_handle_appearance"] is False
    assert assessment["handle_on_back_of_hand"] is False
    assert assessment["mask_visual_seam"] == "NONE"
    assert assessment["wooden_sword_baked_into_hand_asset"] is False


def test_transform_hierarchy_translation_and_rotation_proofs_pass():
    before = resolve_world_transform(prototype_transform_nodes(), "MAIN_HAND_WEAPON")
    translated = resolve_world_transform(prototype_transform_nodes(right_hand_delta=(17.0, -11.0)), "MAIN_HAND_WEAPON")
    assert math.isclose(translated.x - before.x, 17.0, abs_tol=1e-6)
    assert math.isclose(translated.y - before.y, -11.0, abs_tol=1e-6)

    rotated = resolve_world_transform(prototype_transform_nodes(right_hand_rotation=25.0), "MAIN_HAND_WEAPON")
    assert math.isclose(rotated.rotation_deg - before.rotation_deg, 25.0, abs_tol=1e-6)
    actual = transform_point(rotated, (10.0, 0.0))
    expected = (GRIP_ANCHOR[0] + 10.0 * math.cos(math.radians(25.0)), GRIP_ANCHOR[1] + 10.0 * math.sin(math.radians(25.0)))
    assert math.isclose(actual[0], expected[0], abs_tol=1e-6)
    assert math.isclose(actual[1], expected[1], abs_tol=1e-6)


def test_authority_and_scope_firewalls_remain_unchanged():
    report = _contract()
    authority = report["authority"]
    assert authority["equipment_state"].startswith("server-owned")
    assert authority["presentation_only"] is True
    assert authority["client_equipment_authority"] is False
    assert authority["acquire_does_not_equip"] is True
    assert authority["purchase_does_not_equip"] is True
    assert authority["combat_authority_changed"] is False
    assert authority["damage"] == {"baseline": 80, "wooden_sword": 84, "iron_sword": 90}
    assert authority["xp_amulet_new_equip"] is False
    assert authority["xp_amulet_legacy_unequip"] is True
    assert authority["go_stone_black_combat_power"] == 0
    scope = report["scope"]
    assert scope["animation_implemented"] is False
    assert scope["app_py_changed"] is False
    assert scope["runtime_renderer_changed"] is False
    assert scope["registry_changed"] is False
    assert scope["combat_authority_changed"] is False
    assert scope["schema_changed"] is False
    assert scope["data_changed"] is False


def test_review_pack_is_complete_and_pending_owner_visual_review():
    report = _contract()
    expected = {
        "r1_r2_r3_full",
        "r2_grip_before",
        "r3_grip_after",
        "r2_r3_grip_comparison",
        "r3_extreme_grip",
        "r3_full",
        "layer_decomposition",
        "responsive",
        "motion_diagram",
        "owner_review_html",
    }
    assert set(report["review_outputs"]) == expected
    for relative in report["review_outputs"].values():
        assert (ROOT / relative).is_file(), relative
    html = (REVIEW_ROOT / "index.html").read_text(encoding="utf-8")
    assert "PENDING OWNER VISUAL REVIEW" in html
    assert "Owner visual acceptance is not granted" in html
    assert "player_inventory.equipped" in html
    assert "Loadout OFF" in html
    assert "localStorage" not in html
    assert "fetch(" not in html
