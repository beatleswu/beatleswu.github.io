"""Focused tests for the A053-R2 apprentice grip refinement contract.

The visual acceptance itself remains an Owner decision.  These tests cover
the deterministic asset, layer, authority, transform, and frame contracts.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.a053_r2_grip_hand_forearm_integration import (  # noqa: E402
    CANVAS,
    CHARACTER_BASE_PATH,
    CONTRACT_PATH,
    GRIP_ANCHOR,
    IMPLEMENTED_SLOT,
    POSE_FAMILY,
    R1_GRIP_LAYER_PATH,
    R1_MASK_PATH,
    R2_GRIP_LAYER_PATH,
    R2_MASK_PATH,
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


def test_r1_parent_assets_remain_unchanged_and_r2_inputs_are_separate():
    report = _contract()
    assert report["base"]["a053_r1_head"] == "776afd24093b91b3e6ca561cc374ce585c472da0"
    assert report["base"]["a053_r1_tree"] == "ce5f4d6faa6f083a873b88ff53254fdd28d3d7a5"
    assert report["character"]["r1_grip_layer_sha256"] == _sha256(R1_GRIP_LAYER_PATH)
    assert report["character"]["r1_mask_sha256"] == _sha256(R1_MASK_PATH)
    assert R2_GRIP_LAYER_PATH != R1_GRIP_LAYER_PATH
    assert R2_MASK_PATH != R1_MASK_PATH
    assert CHARACTER_BASE_PATH.is_file()


def test_r2_local_grip_forearm_patch_and_mask_have_expected_local_formats():
    with Image.open(R2_GRIP_LAYER_PATH) as image:
        assert image.mode == "RGBA"
        assert image.size == (170, 380)
        assert image.getchannel("A").getbbox() is not None
    with Image.open(R2_MASK_PATH) as image:
        assert image.mode == "L"
        assert image.size == CANVAS
        assert image.getextrema() == (0, 255)
        assert image.getbbox() is not None


def test_semantic_hierarchy_preserves_character_hand_grip_weapon_relationship():
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
    assert report["character"]["grip_anchor"]["one_character_pose_one_grip_anchor"] is True
    assert report["layers"] == [
        {"order": 10, "layer_id": "CHARACTER_BASE", "parent": "BODY", "asset": "assets/hero/characters/wave2_p1/apprentice_p1.png", "mask": "docs/planning/a053_r2_grip_hand_forearm_integration/masks/apprentice_open_hand_suppression_r2.png"},
        {"order": 20, "layer_id": "MAIN_HAND_WEAPON", "parent": "GRIP_ANCHOR", "local_origin": "weapon grip point"},
        {"order": 30, "layer_id": "FRONT_GRIP_HAND", "parent": "RIGHT_HAND", "asset": "docs/planning/a053_r2_grip_hand_forearm_integration/assets/apprentice_grip_forearm_r2.png", "semantic_role": "localized sleeve/wrist/forearm continuity"},
    ]


def test_all_supported_weapons_use_one_shared_anchor_and_data_driven_grip_points():
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


def test_supported_compositions_are_frame_safe_and_default_fallback_is_visible():
    default = compose(None)
    assert default.size == CANVAS
    assert default.getchannel("A").getbbox() is not None
    assert compose("unknown_item").tobytes() == default.tobytes()
    for weapon in WEAPONS:
        layer, world_grip = weapon_layer_and_grip(weapon)
        assert layer.size == CANVAS
        assert world_grip == GRIP_ANCHOR
        bbox = layer.getchannel("A").getbbox()
        assert bbox is not None
        assert bbox[0] >= 0 and bbox[1] >= 0 and bbox[2] <= CANVAS[0] and bbox[3] <= CANVAS[1]
        final = compose(weapon)
        assert final.size == CANVAS
        assert final.getchannel("A").getbbox() is not None
        assert final.tobytes() != default.tobytes()


def test_authoritative_presentation_and_firewalls_remain_explicit():
    report = _contract()
    authority = report["authority"]
    assert resolve_presentation(None) == {"pose_family": "DEFAULT_POSE", "weapon_id": None}
    assert resolve_presentation("unknown_item") == {"pose_family": "DEFAULT_POSE", "weapon_id": None}
    for weapon in WEAPONS:
        assert resolve_presentation(weapon) == {"pose_family": POSE_FAMILY, "weapon_id": weapon}
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


def test_parent_child_translation_proof_passes():
    before = resolve_world_transform(prototype_transform_nodes(), "MAIN_HAND_WEAPON")
    after = resolve_world_transform(prototype_transform_nodes(right_hand_delta=(17.0, -11.0)), "MAIN_HAND_WEAPON")
    assert math.isclose(after.x - before.x, 17.0, abs_tol=1e-6)
    assert math.isclose(after.y - before.y, -11.0, abs_tol=1e-6)


def test_parent_child_rotation_proof_passes():
    before = resolve_world_transform(prototype_transform_nodes(), "MAIN_HAND_WEAPON")
    rotated = resolve_world_transform(prototype_transform_nodes(right_hand_rotation=25.0), "MAIN_HAND_WEAPON")
    assert math.isclose(rotated.rotation_deg - before.rotation_deg, 25.0, abs_tol=1e-6)
    actual = transform_point(rotated, (10.0, 0.0))
    expected = (GRIP_ANCHOR[0] + 10.0 * math.cos(math.radians(25.0)), GRIP_ANCHOR[1] + 10.0 * math.sin(math.radians(25.0)))
    assert math.isclose(actual[0], expected[0], abs_tol=1e-6)
    assert math.isclose(actual[1], expected[1], abs_tol=1e-6)


def test_composition_has_no_extra_runtime_layer_or_client_hook():
    report = _contract()
    assert tuple(compose_layers("wooden_sword")) == ("CHARACTER_BASE", "MAIN_HAND_WEAPON", "FRONT_GRIP_HAND")
    assert report["runtime_active"] is False
    assert report["scope"]["animation_implemented"] is False
    assert report["scope"]["app_py_changed"] is False
    assert report["scope"]["runtime_renderer_changed"] is False
    assert report["scope"]["registry_changed"] is False
    assert report["scope"]["combat_authority_changed"] is False


def test_review_pack_is_complete_and_explicitly_pending_owner_review():
    report = _contract()
    assert report["owner_visual_acceptance"] == "NOT_GRANTED"
    expected = {
        "default_reference", "before_full", "after_full", "before_after_full",
        "before_grip", "after_grip", "before_after_hand", "continuity_crop",
        "exploded_layers", "responsive", "motion_diagram", "owner_review_html",
    }
    assert set(report["review_outputs"]) == expected
    for relative in report["review_outputs"].values():
        assert (ROOT / relative).is_file(), relative
    html = (REVIEW_ROOT / "index.html").read_text(encoding="utf-8")
    assert "PENDING OWNER VISUAL REVIEW" in html
    assert "Owner visual acceptance is not granted" in html
    assert "player_inventory.equipped" in html
    assert "Loadout remains OFF" in html
    assert "localStorage" not in html
    assert "fetch(" not in html


def test_visual_contract_records_the_r2_target_assessment_without_granting_owner_pass():
    assessment = _contract()["visual_self_assessment"]
    assert assessment["grip_hand_oversized"] is False
    assert assessment["hand_scale_matches_character"] is True
    assert assessment["forearm_to_wrist_contour_continuous"] is True
    assert assessment["wrist_to_hand_direction_natural"] is True
    assert assessment["detached_replacement_hand_appearance"] is False
    assert assessment["weapon_handle_enters_palm"] is True
    assert assessment["front_fingers_occlude_handle"] is True
    assert assessment["handle_on_back_of_hand"] is False
    assert assessment["frame_clipping"] is False
