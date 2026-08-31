"""Focused static-contract tests for the A057-R1 Paladin prototype.

These tests prove the prototype boundary and deterministic metadata. They do
not declare Owner visual acceptance; that remains a human review gate.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs/planning/a057_r1_paladin_one_hand_sword_validation"
CONTRACT = PACKAGE / "a057_r1_contract.json"
REVIEW = PACKAGE / "review/index.html"


def _contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_paladin_adapter_is_separate_from_the_reusable_pose_family():
    contract = _contract()
    assert contract["character"]["id"] == "paladin"
    assert contract["character"]["adapter_required"] is True
    assert contract["pose_family"]["pose_id"] == "ONE_HAND_SWORD_POSE_V1"
    assert contract["pose_family"]["family"] == "ONE_HAND_SWORD"
    assert contract["pose_family"]["slot"] == "MAIN_HAND"
    assert contract["pose_family"]["same_pose_family_used_for_all_prototype_weapons"] is True
    assert contract["pose_family"]["weapon_specific_full_character_pose_asset_count"] == 0
    assert set(contract["paladin_adapter_fields"]) >= {
        "shoulder_anchor",
        "elbow_target",
        "forearm_direction",
        "wrist_angle_degrees",
        "palm_center",
        "right_hand_socket",
        "sleeve_armor_clearance",
        "occlusion_order",
    }


def test_wooden_and_iron_share_pose_family_and_are_the_only_weapon_variants():
    contract = _contract()
    weapons = contract["weapon_contract"]["supported_weapons"]
    assert set(weapons) == {"wooden_sword", "iron_sword"}
    assert contract["weapon_contract"]["excluded_weapons"] == ["fox_fang"]
    assert all(item["pose_id"] == "ONE_HAND_SWORD_POSE_V1" for item in weapons.values())
    assert all(item["slot"] == "MAIN_HAND" for item in weapons.values())
    assert all(item["weapon_family"] == "ONE_HAND_SWORD" for item in weapons.values())
    assert all(item["weapon_specific_pose"] is False for item in weapons.values())
    assert all(len(item["grip_point_normalized"]) == 2 for item in weapons.values())
    assert all(len(item["grip_axis"]) == 2 for item in weapons.values())
    assert weapons["wooden_sword"]["grip_width"] != weapons["iron_sword"]["grip_width"]


def test_identity_source_and_review_outputs_are_present_and_hashable():
    contract = _contract()
    identity = ROOT / contract["character"]["canonical_identity_asset"]
    prior_pose = ROOT / contract["character"]["prior_accepted_pose_review_evidence"]
    source = PACKAGE / "source_reference/paladin_one_hand_sword_pose_v1_weapon_free.png"
    wooden = PACKAGE / "review/01_paladin_one_hand_sword_wooden_normal.png"
    iron = PACKAGE / "review/02_paladin_one_hand_sword_iron_normal.png"

    assert identity.is_file()
    assert _sha256(identity) == contract["character"]["canonical_identity_asset_sha256"]
    assert prior_pose.is_file()
    assert _sha256(prior_pose) == contract["character"]["prior_accepted_pose_review_evidence_sha256"]
    assert source.is_file()
    assert wooden.is_file()
    assert iron.is_file()
    assert _sha256(source) == contract["pose_family"]["pose_source_sha256"]
    assert _sha256(wooden) == contract["weapon_contract"]["supported_weapons"]["wooden_sword"]["prototype_review_render_sha256"]
    assert _sha256(iron) == contract["weapon_contract"]["supported_weapons"]["iron_sword"]["prototype_review_render_sha256"]
    assert len({_sha256(source), _sha256(wooden), _sha256(iron)}) == 3
    assert _png_size(wooden) == (1086, 1448)
    assert _png_size(iron) == (1086, 1448)


def test_static_review_pack_is_in_owner_review_order_without_runtime_wiring():
    contract = _contract()
    html = REVIEW.read_text(encoding="utf-8")
    order = contract["visual_review"]["normal_size_unannotated_review_order"]
    assert order[0].endswith("01_paladin_one_hand_sword_wooden_normal.png")
    assert order[1].endswith("02_paladin_one_hand_sword_iron_normal.png")
    for asset in (
        "01_paladin_one_hand_sword_wooden_normal.png",
        "02_paladin_one_hand_sword_iron_normal.png",
        "03_paladin_wooden_vs_iron.svg",
        "04_paladin_wooden_grip_closeup.svg",
        "05_paladin_iron_grip_closeup.svg",
        "06_paladin_adapter_layer_contract.svg",
    ):
        assert (PACKAGE / "review" / asset).is_file(), asset
        assert asset in html
    for forbidden in ("fetch(", "XMLHttpRequest", "localStorage", "sessionStorage"):
        assert forbidden not in html
    assert "Owner visual acceptance is still required" in html


def test_true_grip_and_armor_review_flags_are_recorded_for_both_variants():
    visual = _contract()["visual_review"]
    for weapon_id in ("wooden_sword", "iron_sword"):
        result = visual[weapon_id]
        assert result["handle_enters_palm"] is True
        assert result["four_fingers_wrap"] is True
        assert result["thumb_opposes"] is True
        assert result["wrist_continuity"] == "PASS_REVIEW_READY"
        assert result["forearm_continuity"] == "PASS_REVIEW_READY"
        assert result["shoulder_to_hand_action"] == "PASS_REVIEW_READY"
        assert result["armor_clearance"] == "PASS_REVIEW_READY"
        assert result["owner_review_required"] is True


def test_presentation_and_authority_firewalls_are_explicit():
    scope = _contract()["authority_and_scope"]
    assert scope == {
        "runtime_changed": False,
        "app_py_changed": False,
        "combat_authority_changed": False,
        "equipment_authority_changed": False,
        "schema_changed": False,
        "production_query": False,
        "production_mutation": False,
        "deploy": False,
        "fox_fang_implemented": False,
        "owner_visual_acceptance": "NOT_GRANTED",
    }
    weapons = _contract()["weapon_contract"]
    assert weapons["authority"] == "server-owned player_inventory.equipped"
    assert weapons["presentation_only"] is True
    assert weapons["acquire_triggers_pose"] is False
    assert weapons["purchase_triggers_pose"] is False
    assert weapons["ownership_alone_triggers_pose"] is False
    assert weapons["authoritative_equipped_state_triggers_pose"] is True
