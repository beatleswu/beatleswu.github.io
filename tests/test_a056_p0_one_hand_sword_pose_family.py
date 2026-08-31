"""Focused contract tests for the isolated A056 visual prototype."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools/build_a056_p0_one_hand_sword_pose_family.py"
CONTRACT_PATH = ROOT / "docs/planning/a056_p0_one_hand_sword_pose_family/a056_p0_contract.json"


def _load_tool():
    spec = importlib.util.spec_from_file_location("a056_pose_family_tool", TOOL_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_pose_identity_and_exact_layer_order() -> None:
    contract = _contract()
    assert contract["character"] == "apprentice"
    assert contract["pose_id"] == "ONE_HAND_SWORD_POSE_V1"
    assert contract["slot"] == "MAIN_HAND"
    assert contract["layers"] == [
        "L10_CHARACTER_BASE",
        "L20_WEAPON_BACK",
        "L30_SWORD_GRIP_HAND",
        "L40_WEAPON_FRONT",
    ]


def test_both_weapons_use_one_pose_family_and_independent_layers() -> None:
    weapons = _contract()["weapons"]
    assert set(weapons) == {"wooden_sword", "iron_sword"}
    assert {record["pose_family"] for record in weapons.values()} == {"ONE_HAND_SWORD"}
    assert {record["slot"] for record in weapons.values()} == {"MAIN_HAND"}
    assert all(record["compatible"] is True for record in weapons.values())
    assert weapons["wooden_sword"]["independent_layer"]["full"] != weapons["iron_sword"]["independent_layer"]["full"]
    assert _contract()["character_pose_asset"] != weapons["wooden_sword"]["independent_layer"]["full"]
    assert _contract()["grip_hand_asset"] != weapons["iron_sword"]["independent_layer"]["full"]


def test_grip_socket_axis_and_weapon_grip_metadata_are_valid() -> None:
    contract = _contract()
    socket = contract["right_hand_weapon_socket"]
    axis = contract["grip_axis"]
    assert len(socket) == 2
    assert len(axis) == 2
    assert abs((axis[0] ** 2 + axis[1] ** 2) ** 0.5 - 1.0) < 0.001
    assert contract["grip_width_px"] > 0
    for record in contract["weapons"].values():
        x, y = record["grip_point_normalized"]
        assert 0.0 <= x <= 1.0
        assert 0.0 <= y <= 1.0
        assert record["grip_width_px"] > 0


def test_transform_hierarchy_propagates_parent_translation_and_rotation() -> None:
    tool = _load_tool()
    base = tool.resolve_world_transform(tool.transform_nodes(), "MAIN_HAND_WEAPON")
    translated = tool.resolve_world_transform(
        tool.transform_nodes(hand_delta=(23.0, -17.0)), "MAIN_HAND_WEAPON"
    )
    rotated = tool.resolve_world_transform(
        tool.transform_nodes(hand_rotation=19.0), "MAIN_HAND_WEAPON"
    )
    assert (base.x, base.y) == (300.0, 650.0)
    assert (translated.x, translated.y) == (323.0, 633.0)
    assert rotated.rotation_deg == 19.0


def test_authority_and_fallback_contract_is_presentation_only() -> None:
    contract = _contract()
    authority = contract["authority"]
    assert contract["runtime_active"] is False
    assert contract["visual_acceptance"] == "OWNER_REQUIRED"
    assert contract["weapon_baked_into_character"] is False
    assert authority["equipment_authority"] == "server-owned equipped state"
    assert authority["client_equipment_authority"] is False
    assert authority["acquire_triggers_pose"] is False
    assert authority["purchase_triggers_pose"] is False
    assert authority["owned_but_unequipped_hidden"] is True
    assert authority["unsupported_equipment_safe"] is True
    assert contract["combat_authority_changed"] is False


def test_prototype_layers_are_rgba_and_review_normals_are_opaque() -> None:
    contract = _contract()
    paths = [
        ROOT / contract["character_pose_asset"],
        ROOT / contract["grip_hand_asset"],
    ]
    for record in contract["weapons"].values():
        paths.extend(
            ROOT / record["independent_layer"][key]
            for key in ("full", "back", "front")
        )
    for path in paths:
        with Image.open(path) as image:
            assert image.mode == "RGBA"
            assert image.size == (1056, 1408)
            assert image.getchannel("A").getbbox() is not None

    review_root = ROOT / "docs/planning/a056_p0_one_hand_sword_pose_family/review"
    for name in (
        "01_apprentice_one_hand_sword_wooden_normal.png",
        "02_apprentice_one_hand_sword_iron_normal.png",
    ):
        with Image.open(review_root / name) as image:
            assert image.getchannel("A").getextrema() == (255, 255)


def test_required_review_pack_is_complete() -> None:
    names = _contract()["review_pack"]
    review_root = ROOT / "docs/planning/a056_p0_one_hand_sword_pose_family/review"
    assert len(names) == 12
    assert all((review_root / name).is_file() for name in names)


def test_composition_outputs_are_deterministic() -> None:
    tool = _load_tool()
    contract_before = _contract()
    output_paths = [
        ROOT / contract_before["weapons"][weapon]["independent_layer"]["full"]
        for weapon in ("wooden_sword", "iron_sword")
    ]
    before = [_sha256(path) for path in output_paths]
    tool.build()
    after = [_sha256(path) for path in output_paths]
    assert before == after
    assert _contract()["pose_id"] == "ONE_HAND_SWORD_POSE_V1"
