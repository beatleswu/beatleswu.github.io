"""Focused contract tests for the A053 Paper Doll Lite static prototype.

These tests exercise the semantic data model and deterministic compositor;
they do not activate or replace the live Hero renderer.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.a053_paper_doll_lite_prototype import (
    CANVAS,
    CHARACTER_BASE_PATH,
    CONTRACT_PATH,
    GRIP_LAYER_PATH,
    IMPLEMENTED_SLOT,
    POSE_FAMILY,
    REVIEW_ROOT,
    SUPPRESSION_MASK_PATH,
    WEAPON_ROOT,
    WEAPON_SPECS,
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


def _approx_pair(actual: tuple[float, float], expected: tuple[float, float], tolerance: float = 1e-6) -> None:
    assert math.isclose(actual[0], expected[0], abs_tol=tolerance)
    assert math.isclose(actual[1], expected[1], abs_tol=tolerance)


def test_contract_is_static_review_only_and_has_one_implemented_slot():
    report = _contract()
    assert report["status"] == "STATIC_PROTOTYPE_PENDING_OWNER_VISUAL_REVIEW"
    assert report["runtime_active"] is False
    assert report["owner_visual_acceptance"] == "NOT_GRANTED"
    assert report["implemented_slots"] == [IMPLEMENTED_SLOT]
    assert report["future_slots_documented_only"] == ["OFF_HAND", "HEAD", "BODY", "FEET"]
    assert report["scope"] == {
        "full_character_per_weapon_assets_created": 0,
        "grip_hand_per_weapon_assets_created": 0,
        "shared_character_grip_structure": True,
        "animation_implemented": False,
        "app_py_changed": False,
        "runtime_renderer_changed": False,
        "registry_changed": False,
        "schema_changed": False,
        "data_changed": False,
    }


def test_semantic_hierarchy_has_parent_relationship_and_transform_fields():
    report = _contract()
    nodes = {entry["node_id"]: entry for entry in report["transform_hierarchy"]}
    assert nodes["CHARACTER_ROOT"]["parent"] is None
    assert nodes["BODY"]["parent"] == "CHARACTER_ROOT"
    assert nodes["RIGHT_ARM"]["parent"] == "BODY"
    assert nodes["RIGHT_HAND"]["parent"] == "RIGHT_ARM"
    assert nodes["GRIP_ANCHOR"]["parent"] == "RIGHT_HAND"
    assert nodes["MAIN_HAND_WEAPON"]["parent"] == "GRIP_ANCHOR"
    assert nodes["FRONT_GRIP_HAND"]["parent"] == "RIGHT_HAND"
    for entry in nodes.values():
        assert entry["transform_fields"] == ["x", "y", "rotation_deg", "scale"]


def test_apprentice_base_grip_and_mask_are_existing_true_alpha_inputs():
    assert CHARACTER_BASE_PATH.is_file()
    assert GRIP_LAYER_PATH.is_file()
    assert SUPPRESSION_MASK_PATH.is_file()
    with Image.open(CHARACTER_BASE_PATH) as image:
        assert image.size == CANVAS
        assert image.mode == "RGBA"
        assert image.getchannel("A").getbbox() is not None
    with Image.open(GRIP_LAYER_PATH) as image:
        assert image.mode == "RGBA"
        assert image.getchannel("A").getbbox() is not None
    with Image.open(SUPPRESSION_MASK_PATH) as image:
        assert image.mode == "L"
        assert image.getextrema()[0] == 0
        assert image.getextrema()[1] == 255


def test_three_weapon_records_are_weapon_only_and_share_one_main_hand_contract():
    report = _contract()
    assert tuple(report["weapons"]) == WEAPONS
    assert len({report["weapons"][weapon]["asset_sha256"] for weapon in WEAPONS}) == 3
    assert report["character"]["grip_anchor"]["one_character_pose_one_grip_anchor"] is True
    for weapon in WEAPONS:
        spec = report["weapons"][weapon]
        assert spec["slot"] == IMPLEMENTED_SLOT
        assert spec["pose_family"] == POSE_FAMILY
        assert spec["weapon_only"] is True
        assert spec["baked_character_pixels"] is False
        path = ROOT / spec["asset"]
        assert path == WEAPON_ROOT / f"{weapon}.png"
        assert path.is_file()
        with Image.open(path) as image:
            assert image.mode == "RGBA"
            assert image.getchannel("A").getbbox() is not None
            assert image.size != CANVAS


def test_presentation_resolves_only_from_authoritative_equipped_item():
    assert resolve_presentation(None) == {"pose_family": "DEFAULT_POSE", "weapon_id": None}
    assert resolve_presentation("unknown_item") == {"pose_family": "DEFAULT_POSE", "weapon_id": None}
    for weapon in WEAPONS:
        assert resolve_presentation(weapon) == {"pose_family": POSE_FAMILY, "weapon_id": weapon}
    report = _contract()
    assert report["authority"]["equipped_state"].startswith("server-owned")
    assert report["authority"]["client_equipment_authority"] is False
    assert report["authority"]["acquire_does_not_equip"] is True
    assert report["authority"]["purchase_does_not_equip"] is True


def test_shared_grip_anchor_and_weapon_specific_grip_points_align():
    report = _contract()
    anchor = report["character"]["grip_anchor"]
    assert (anchor["x"], anchor["y"]) == (800.0, 800.0)
    points = [tuple(report["weapons"][weapon]["grip_point_normalized"]) for weapon in WEAPONS]
    assert len(set(points)) == 3
    for weapon in WEAPONS:
        layer, world_grip = weapon_layer_and_grip(weapon)
        assert layer.size == CANVAS
        _approx_pair(world_grip, (800.0, 800.0))


def test_parent_child_translation_proof_passes():
    before = resolve_world_transform(prototype_transform_nodes(), "MAIN_HAND_WEAPON")
    after = resolve_world_transform(
        prototype_transform_nodes(right_hand_delta=(17.0, -11.0)), "MAIN_HAND_WEAPON"
    )
    _approx_pair((after.x - before.x, after.y - before.y), (17.0, -11.0))


def test_parent_child_rotation_proof_preserves_local_relationship():
    before_nodes = prototype_transform_nodes()
    rotated_nodes = prototype_transform_nodes(right_hand_rotation=25.0)
    before = resolve_world_transform(before_nodes, "MAIN_HAND_WEAPON")
    rotated = resolve_world_transform(rotated_nodes, "MAIN_HAND_WEAPON")
    assert math.isclose(rotated.rotation_deg - before.rotation_deg, 25.0, abs_tol=1e-6)
    actual = transform_point(rotated, (10.0, 0.0))
    expected_delta = (
        800.0 + 10.0 * math.cos(math.radians(25.0)),
        800.0 + 10.0 * math.sin(math.radians(25.0)),
    )
    _approx_pair(actual, expected_delta)


def test_default_owned_but_unequipped_and_unknown_equipment_fall_back_to_default():
    default = compose(None)
    assert compose(None).tobytes() == default.tobytes()
    assert compose("unknown_item").tobytes() == default.tobytes()
    for weapon in WEAPONS:
        assert compose(weapon).tobytes() != default.tobytes()


def test_supported_compositions_use_deterministic_three_layer_order_and_common_frame():
    report = _contract()
    assert [(layer["order"], layer["layer_id"]) for layer in report["layers"]] == [
        (10, "CHARACTER_BASE"),
        (20, "MAIN_HAND_WEAPON"),
        (30, "FRONT_GRIP_HAND"),
    ]
    for weapon in WEAPONS:
        layers = compose_layers(weapon)
        assert tuple(layers) == ("CHARACTER_BASE", "MAIN_HAND_WEAPON", "FRONT_GRIP_HAND")
        assert all(layer.size == CANVAS for layer in layers.values())
        assert compose(weapon).size == CANVAS


def test_review_pack_contains_static_evidence_not_live_runtime_hooks():
    report = _contract()
    for relative in report["review_outputs"].values():
        assert (ROOT / relative).is_file(), relative
    html = (REVIEW_ROOT / "index.html").read_text(encoding="utf-8")
    assert "STATIC PROTOTYPE" in html
    assert "PENDING OWNER VISUAL REVIEW" in html
    assert "player_inventory.equipped" in html
    assert "Loadout remains OFF" in html
    assert "fetch(" not in html
    assert "localStorage" not in html


def test_authority_contract_preserves_combat_and_future_slot_firewalls():
    report = _contract()
    authority = report["authority"]
    assert authority["equipment_effects"] == "server-owned EQUIPMENT_DEFS"
    assert authority["no_client_combat_authority"] is True
    assert authority["combat_damage_unchanged"] == {"baseline": 80, "wooden_sword": 84, "iron_sword": 90}
    assert authority["xp_amulet_new_equip"] is False
    assert authority["xp_amulet_legacy_unequip"] is True
    assert authority["go_stone_black_combat_power"] == 0
