"""Objective tests for the isolated A054-P0 visual architecture prototype."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import tools.a054_p0_paper_doll_split_weapon_grip as prototype  # noqa: E402


CONTRACT = json.loads(prototype.CONTRACT_PATH.read_text(encoding="utf-8"))


def test_exact_four_layer_order_and_semantic_parents() -> None:
    assert CONTRACT["architecture"] == [
        "L10 CHARACTER_BASE",
        "L20 WEAPON_BACK",
        "L30 SWORD_GRIP_HAND",
        "L40 WEAPON_FRONT",
    ]
    hierarchy = CONTRACT["semantic_hierarchy"]
    assert hierarchy["RIGHT_HAND_SOCKET"] == "RIGHT_HAND"
    assert hierarchy["GRIP_POINT"] == "RIGHT_HAND_SOCKET"
    assert hierarchy["MAIN_HAND_WEAPON"] == "GRIP_POINT"
    assert hierarchy["WEAPON_BACK"] == "MAIN_HAND_WEAPON"
    assert hierarchy["WEAPON_FRONT"] == "MAIN_HAND_WEAPON"


def test_same_reusable_grip_pose_resolves_for_both_weapons() -> None:
    wooden = prototype.resolve_presentation("wooden_sword")
    iron = prototype.resolve_presentation("iron_sword")
    assert wooden["pose_id"] == prototype.POSE_ID
    assert iron["pose_id"] == prototype.POSE_ID
    assert wooden["pose_id"] == iron["pose_id"] == "ONE_HAND_SWORD_GRIP_POSE"
    assert CONTRACT["grip_hand"]["weapon_specific_hand_asset_created"] is False


def test_socket_grip_metadata_is_semantic_and_valid() -> None:
    socket = CONTRACT["socket"]
    axis = socket["grip_axis"]
    assert socket["node"] == "RIGHT_HAND_SOCKET"
    assert socket["grip_point_node"] == "GRIP_POINT"
    assert socket["coordinate_space"] == "PLAYER_FRAME_A_STANDARD_CHIBI"
    assert abs((axis[0] ** 2 + axis[1] ** 2) ** 0.5 - 1.0) < 1e-6
    assert CONTRACT["split_policy"]["front_window_projection_px"][0] < CONTRACT["split_policy"]["front_window_projection_px"][1]
    for weapon in ("wooden_sword", "iron_sword"):
        spec = CONTRACT["weapons"][weapon]
        assert spec["weapon_only"] is True
        assert spec["baked_into_hand"] is False
        assert spec["grip_width_px"] > 0
        assert len(spec["grip_point_normalized"]) == 2


def test_split_union_preserves_each_weapon_alpha_without_duplicate_pixels() -> None:
    for weapon in ("wooden_sword", "iron_sword"):
        full, _ = prototype.weapon_layer_and_grip(weapon)
        back, front = prototype.split_weapon_layers(weapon)
        assert ImageChops.lighter(back.getchannel("A"), front.getchannel("A")).tobytes() == full.getchannel("A").tobytes()
        overlap = ImageChops.multiply(back.getchannel("A"), front.getchannel("A"))
        assert overlap.getbbox() is None


def test_hand_layer_is_rgba_and_independent_from_weapon_split_layers() -> None:
    hand = prototype.load_grip_hand()
    assert hand.mode == "RGBA"
    assert hand.size == prototype.HAND_SIZE
    assert hand.getchannel("A").getbbox() is not None
    for weapon in ("wooden_sword", "iron_sword"):
        assert prototype.WEAPON_SPECS[weapon]["source"] != prototype.GRIP_HAND_PATH
        assert CONTRACT["weapons"][weapon]["baked_into_hand"] is False


def test_default_and_unknown_equipment_fail_safe_to_default_character() -> None:
    default = prototype.compose(None)
    unknown = prototype.compose("unknown_equipment")
    assert default.tobytes() == unknown.tobytes()
    assert prototype.resolve_presentation(None)["pose_id"] == "DEFAULT_POSE"
    assert prototype.resolve_presentation("unknown_equipment")["pose_id"] == "DEFAULT_POSE"


def test_supported_compositions_are_deterministic_and_generated() -> None:
    for weapon in ("wooden_sword", "iron_sword"):
        first = prototype.compose(weapon)
        second = prototype.compose(weapon)
        assert first.tobytes() == second.tobytes()
        assert first.size == prototype.CANVAS
        output = prototype.REVIEW_ROOT / f"p0_{weapon}_full.png"
        assert output.is_file()
        assert Image.open(output).convert("RGBA").getchannel("A").getbbox() is not None


def test_parent_child_translation_proof() -> None:
    before = prototype.resolve_world_transform(prototype.prototype_transform_nodes(), "MAIN_HAND_WEAPON")
    after = prototype.resolve_world_transform(
        prototype.prototype_transform_nodes(right_hand_delta=(17.0, -11.0)), "MAIN_HAND_WEAPON"
    )
    assert after.x - before.x == 17.0
    assert after.y - before.y == -11.0


def test_parent_child_rotation_proof() -> None:
    before = prototype.resolve_world_transform(prototype.prototype_transform_nodes(), "MAIN_HAND_WEAPON")
    after = prototype.resolve_world_transform(
        prototype.prototype_transform_nodes(right_hand_rotation=25.0), "MAIN_HAND_WEAPON"
    )
    assert after.rotation_deg - before.rotation_deg == 25.0


def test_scope_is_static_and_does_not_depend_on_app_or_runtime() -> None:
    scope = CONTRACT["scope"]
    assert scope["app_py_dependency"] is False
    assert scope["runtime_wiring_changed"] is False
    assert scope["equipment_authority_changed"] is False
    assert scope["combat_authority_changed"] is False
    assert scope["production_query"] is False
    assert scope["production_mutation"] is False
    assert scope["deploy"] is False
    assert CONTRACT["runtime_active"] is False


def test_review_pack_is_explicitly_pending_owner_and_not_live() -> None:
    review = prototype.REVIEW_ROOT
    required = (
        "a054_r3_failed_approach_reference.png",
        "p0_wooden_sword_full.png",
        "p0_iron_sword_full.png",
        "p0_wooden_sword_grip_closeup.png",
        "p0_iron_sword_grip_closeup.png",
        "p0_split_layer_architecture.png",
        "p0_wooden_layer_decomposition.png",
        "p0_iron_layer_decomposition.png",
        "p0_grip_axis_overlay.png",
        "p0_wooden_vs_iron_same_grip.png",
        "p0_before_after.png",
        "p0_motion_ready_transform_diagram.svg",
        "index.html",
    )
    assert all((review / name).is_file() for name in required)
    html = (review / "index.html").read_text(encoding="utf-8")
    assert "TECHNICAL CANDIDATE" in html
    assert "OWNER VISUAL ACCEPTANCE REQUIRED" in html
    assert "RUNTIME_ACTIVE=NO" in html
    assert "fetch(" not in html
    assert "localStorage" not in html
