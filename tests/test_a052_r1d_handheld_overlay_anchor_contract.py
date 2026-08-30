"""Focused contract checks for A052-R1D handheld composition preparation."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
HANDHELD_DIR = ROOT / "assets/hero/equipment/wearables/handheld"
CONTRACT_PATH = HANDHELD_DIR / "handheld_pose_contract.json"
REGISTRY_PATH = ROOT / "assets/hero/equipment/wearables/wearable_registry.json"
REVIEW_DIR = ROOT / "docs/planning/a052_r1d_handheld_overlay_review"

SUPPORTED_WEAPONS = ("wooden_sword", "iron_sword", "fox_fang")
CHARACTERS = (
    "apprentice",
    "mage",
    "paladin",
    "trail_apprentice",
    "night_runner",
    "constellation_apprentice",
)

HANDHELD_EXPECTED = {
    "wooden_sword": {
        "sha256": "4b26cd361d2920efc428dcf13fe377257f175da9ad56bac96d1ef0afa18c4b48",
        "size": (1070, 1087),
        "alpha_bbox": (24, 24, 1046, 1063),
    },
    "iron_sword": {
        "sha256": "ef6b4619f1131ccd087080163261ec047e5a08944d35ef0cd586017feafc1c2f",
        "size": (737, 1457),
        "alpha_bbox": (41, 24, 641, 1371),
    },
    "fox_fang": {
        "sha256": "3e0b7dc09b4a5924318dc81c85d94db94ebc413b76465c5f5a0f821146e8b676",
        "size": (1073, 1178),
        "alpha_bbox": (24, 24, 1049, 1154),
    },
}

R1B_POSE_EXPECTED = {
    "apprentice": "deae3f2df02b8bcadc493ca74ebd1896a4849e65f3151572c3e8854f27ea3ae6",
    "mage": "59c6cd1a4c4428d7b5d3f655e7541e15e8481f824c6a9201fa21c49790beef1a",
    "paladin": "363d99db99a6bc0f769b7caf58274a35f0b2da2a10be49f58385b978fcc74243",
    "trail_apprentice": "7fbc61c38e2b1aa2fc5f09e4f56b75b894f1df0f4ef4f87c56cde0689c624cd2",
    "night_runner": "591c1c61ff4aaaa2f180658099ec7c0389d1f536a1227918e0214c5e9e299eb8",
    "constellation_apprentice": "360f195a9277c6956faa9a38047273c6393c4579111e0f5946d83934753bda02",
}

R1B_POSE_PATHS = {
    "apprentice": ROOT / "assets/hero/characters/wave2_p1/poses/one_hand_sword/apprentice_one_hand_sword_weapon_free.png",
    "mage": ROOT / "assets/hero/characters/wave2_p1/poses/one_hand_sword/mage_one_hand_sword_weapon_free.png",
    "paladin": ROOT / "assets/hero/characters/wave2_p1/poses/one_hand_sword/paladin_one_hand_sword_weapon_free.png",
    "trail_apprentice": ROOT / "assets/hero/characters/wave2_p1/poses/one_hand_sword/trail_apprentice_one_hand_sword_weapon_free.png",
    "night_runner": ROOT / "assets/hero/characters/wave2_p1/poses/one_hand_sword/night_runner_one_hand_sword_weapon_free.png",
    "constellation_apprentice": ROOT / "assets/hero/characters/wave2_p1/poses/one_hand_sword/constellation_apprentice_one_hand_sword_weapon_free.png",
}

ORIGINAL_REVIEW_ASSETS = {
    "apprentice": (ROOT / "docs/planning/rpg_wave2_full_body_weapon_pose_system/variants/apprentice_one_hand_sword_pose.png", "d7c1b2d631da009640972d41d9c9818ac983dd7a3beaf4e51d43249d9d7b3956"),
    "mage": (ROOT / "docs/planning/rpg_wave2_full_body_weapon_pose_system/variants/mage_one_hand_sword_pose.png", "f12c9ea4fa362390f319d1fd46a34d6c06fa53aa6e5a2a8aa75b11e5662d260f"),
    "paladin": (ROOT / "docs/planning/rpg_wave2_full_body_weapon_pose_system/variants/paladin_one_hand_sword_pose.png", "5d2ed28399d5ceb41655eea98f271e281e201f71b4e3c4db81522045c5a6f291"),
    "trail_apprentice": (ROOT / "docs/planning/rpg_wave2_full_body_weapon_pose_batch2/variants/trail_apprentice_one_hand_sword_pose.png", "0127c9e325cb4bdfd43a192443b848f1f375897b14c0809c320c20dc20f0d0d3"),
    "night_runner": (ROOT / "docs/planning/rpg_wave2_full_body_weapon_pose_batch2/variants/night_runner_one_hand_sword_pose.png", "b07a3da36f26fb1a03a27b466527594831a99b5ea83da92011ecd1f860a56639"),
    "constellation_apprentice": (ROOT / "docs/planning/rpg_wave2_full_body_weapon_pose_batch2/variants/constellation_apprentice_one_hand_sword_pose.png", "56c42ab7c7d35c48959e0fc41828949547166b8797bd1ee540d7ddd35c5a416b"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_contract_is_dormant_and_server_authoritative() -> None:
    contract = load_contract()
    assert contract["status"] == "PREPARED_PENDING_OWNER_VISUAL_REVIEW"
    assert contract["runtime_active"] is False
    assert contract["owner_visual_acceptance"] == "NOT_GRANTED"
    assert contract["authority"] == {
        "equipment": "server_owned.player_inventory.equipped",
        "pose": "visual_only",
        "client_equipment_authority": False,
        "purchase_does_not_equip": True,
        "acquire_does_not_equip": True,
        "combat_effect_source": "server_owned.EQUIPMENT_DEFS",
    }
    assert contract["runtime_activation"]["loadout_default"] is False
    assert contract["runtime_activation"]["server_changes"] is False


def test_handheld_assets_are_exact_transparent_weapon_only_candidates() -> None:
    contract = load_contract()
    assert set(contract["supported_weapons"]) == set(SUPPORTED_WEAPONS)
    for weapon_id in SUPPORTED_WEAPONS:
        expected = HANDHELD_EXPECTED[weapon_id]
        entry = contract["supported_weapons"][weapon_id]
        path = HANDHELD_DIR / f"{weapon_id}.png"
        assert path.is_file()
        assert sha256(path) == expected["sha256"]
        with Image.open(path) as image:
            assert image.mode == "RGBA"
            assert image.size == expected["size"]
            alpha = image.getchannel("A")
            assert alpha.getbbox() == expected["alpha_bbox"]
            assert alpha.getextrema()[0] == 0
        assert entry["alpha_valid"] is True
        assert entry["weapon_only"] is True
        assert entry["baked_character_pixels"] is False
        assert entry["asset_path"].endswith(f"/handheld/{weapon_id}.png")


def test_all_six_r1b_pose_hashes_and_anchors_are_present() -> None:
    contract = load_contract()
    assert set(contract["characters"]) == set(CHARACTERS)
    for character in CHARACTERS:
        entry = contract["characters"][character]
        pose_path = R1B_POSE_PATHS[character]
        assert pose_path.is_file()
        assert sha256(pose_path) == R1B_POSE_EXPECTED[character]
        assert entry["pose_sha256"] == R1B_POSE_EXPECTED[character]
        assert 0.0 <= entry["grip_x"] <= 1.0
        assert 0.0 <= entry["grip_y"] <= 1.0
        assert entry["anchor_coordinate_space"] == "PLAYER_FRAME_A_STANDARD_CHIBI_NORMALIZED"
        assert entry["render_layer"] == "BACK_WEAPON"
        assert entry["z_order"] == 10
        assert entry["mask_required"] is False


def test_transform_and_occlusion_contract_is_deterministic() -> None:
    contract = load_contract()
    adjustments = contract["per_weapon_adjustments"]
    assert set(adjustments) == set(SUPPORTED_WEAPONS)
    for adjustment in adjustments.values():
        assert adjustment == {
            "offset_x": 0.0,
            "offset_y": 0.0,
            "rotation_delta_deg": 0.0,
            "scale_multiplier": 1.0,
        }
    grip_points = {
        weapon_id: tuple(entry["weapon_grip_point"])
        for weapon_id, entry in contract["supported_weapons"].items()
    }
    for character in CHARACTERS:
        entry = contract["characters"][character]
        assert entry["weapon_grip_point_by_weapon"] == {
            weapon_id: list(grip_points[weapon_id]) for weapon_id in SUPPORTED_WEAPONS
        }
        assert entry["occlusion"] == "SIMPLE_BACK_OVERLAY_CHARACTER_BASE_OCCLUDES_HAND_CONTACT"
    assert all(contract["characters"][character]["mask_required"] is False for character in CHARACTERS)


def test_deferred_weapon_and_failure_fallbacks_are_explicit() -> None:
    contract = load_contract()
    assert contract["fallbacks"]["dragon_claw"] == "DEFERRED_EXISTING_GOVERNED_PRESENTATION"
    assert contract["fallbacks"]["celestial_blade"] == "DEFERRED_EXISTING_GOVERNED_PRESENTATION"
    assert contract["fallbacks"]["unknown_weapon"] == "DEFAULT_POSE_NO_WEAPON_OVERLAY"
    assert contract["fallbacks"]["unsupported_character"] == "DEFAULT_POSE_KEEP_AUTHORITATIVE_EQUIPMENT"
    assert contract["fallbacks"]["asset_load_failure"] == "WEAPON_FREE_POSE_NO_WEAPON_OVERLAY"


def test_existing_waist_contract_remains_unchanged() -> None:
    contract = load_contract()
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert registry["provenance"]["static_sword_mode"] == "WAIST_SHEATHED"
    assert registry["provenance"]["hand_held_static_mode"] == "FORBIDDEN"
    for weapon_id in SUPPORTED_WEAPONS:
        item = registry["equipment"][weapon_id]
        assert item["wearable_class"] == "WEAPON_WAIST"
        assert item["anchor"] == "waist_right"
        assert item["layer"] == "BACK_WEAPON"
        assert item["asset"].endswith(f"/overlays/{weapon_id}.png")
        assert item["presentation_only"] is True
    assert set(contract["supported_weapons"]) == set(SUPPORTED_WEAPONS)


def test_owner_sources_and_r1d_review_pack_are_present() -> None:
    for _, (path, expected_hash) in ORIGINAL_REVIEW_ASSETS.items():
        assert path.is_file()
        assert sha256(path) == expected_hash
    pack = REVIEW_DIR / "owner_review_pack.html"
    assert pack.is_file()
    pack_text = pack.read_text(encoding="utf-8")
    assert "PENDING_OWNER_VISUAL_REVIEW" in pack_text
    for character in CHARACTERS:
        assert character in pack_text or character.replace("_", " ") in pack_text
    for filename in (
        "wooden_sword_all_characters.png",
        "iron_sword_all_characters.png",
        "fox_fang_all_characters.png",
        "wooden_sword_hand_alignment_crops.png",
    ):
        assert (REVIEW_DIR / filename).is_file()


def test_no_runtime_registry_wiring_is_active_in_r1d_contract() -> None:
    contract = load_contract()
    assert contract["runtime_activation"]["hero_wiring"] == "NOT_YET_IMPLEMENTED"
    assert contract["runtime_activation"]["registry_wiring"] == "NOT_YET_IMPLEMENTED"
    registry_text = REGISTRY_PATH.read_text(encoding="utf-8")
    assert "/handheld/" not in registry_text


def test_frame_safe_padded_composition_contract_is_explicit() -> None:
    frame = load_contract()["frame"]
    assert frame["width"] == 1056
    assert frame["height"] == 1408
    assert frame["composition"] == {
        "mode": "PADDED_CANONICAL_FRAME",
        "canvas_width": 1264,
        "canvas_height": 1408,
        "canonical_frame_offset_px": [104, 0],
        "padding_px": {"left": 104, "right": 104, "top": 0, "bottom": 0},
        "shift_character_and_weapon_together": True,
        "overflow": "FORBIDDEN",
        "minimum_visual_margin_px": {"x": 20, "y": 39},
        "coordinate_space": "CANONICAL_FRAME_PIXELS_THEN_PADDED_CANVAS",
        "responsive_rule": "scale_with_padded_character_container",
    }


def test_all_18_compositions_have_positive_frame_safety_margin() -> None:
    contract = load_contract()
    frame = contract["frame"]
    composition = frame["composition"]
    canonical_width = frame["width"]
    canonical_height = frame["height"]
    canvas_width = composition["canvas_width"]
    canvas_height = composition["canvas_height"]
    offset_x, offset_y = composition["canonical_frame_offset_px"]
    minimum_margin_x = composition["minimum_visual_margin_px"]["x"]
    minimum_margin_y = composition["minimum_visual_margin_px"]["y"]

    checked = 0
    observed_margins = []
    for weapon_id, weapon in contract["supported_weapons"].items():
        weapon_path = ROOT / weapon["asset_path"].lstrip("/").replace("/", "\\")
        with Image.open(weapon_path) as image:
            source = image.convert("RGBA")
        resized_size = (
            round(source.width * weapon["base_scale"]),
            round(source.height * weapon["base_scale"]),
        )
        resized = source.resize(resized_size, Image.Resampling.LANCZOS)
        rotated = resized.rotate(
            weapon["base_rotation_deg"],
            resample=Image.Resampling.BICUBIC,
            expand=True,
        )
        weapon_bbox = rotated.getchannel("A").getbbox()
        assert weapon_bbox is not None
        grip_x = weapon["weapon_grip_point"][0] * resized.width
        grip_y = weapon["weapon_grip_point"][1] * resized.height
        # PIL's expanded rotate uses the inverse-sign coordinate transform for
        # the point used by the existing R1D static composition evidence.
        angle = math.radians(-weapon["base_rotation_deg"])
        source_center = (resized.width / 2, resized.height / 2)
        rotated_center = (rotated.width / 2, rotated.height / 2)
        transformed_grip_x = (
            math.cos(angle) * (grip_x - source_center[0])
            - math.sin(angle) * (grip_y - source_center[1])
            + rotated_center[0]
        )
        transformed_grip_y = (
            math.sin(angle) * (grip_x - source_center[0])
            + math.cos(angle) * (grip_y - source_center[1])
            + rotated_center[1]
        )

        for character_id, character in contract["characters"].items():
            pose_path = ROOT / character["pose_asset"].lstrip("/").replace("/", "\\")
            with Image.open(pose_path) as image:
                pose_bbox = image.convert("RGBA").getchannel("A").getbbox()
            assert pose_bbox is not None
            anchor_x = character["grip_x"] * canonical_width
            anchor_y = character["grip_y"] * canonical_height
            weapon_left = anchor_x - transformed_grip_x
            weapon_top = anchor_y - transformed_grip_y
            combined_bbox = (
                min(offset_x + pose_bbox[0], offset_x + weapon_left + weapon_bbox[0]),
                min(offset_y + pose_bbox[1], offset_y + weapon_top + weapon_bbox[1]),
                max(offset_x + pose_bbox[2], offset_x + weapon_left + weapon_bbox[2]),
                max(offset_y + pose_bbox[3], offset_y + weapon_top + weapon_bbox[3]),
            )
            left_margin = combined_bbox[0]
            top_margin = combined_bbox[1]
            right_margin = canvas_width - combined_bbox[2]
            bottom_margin = canvas_height - combined_bbox[3]
            assert left_margin >= minimum_margin_x
            assert top_margin >= minimum_margin_y
            assert right_margin >= minimum_margin_x
            assert bottom_margin >= minimum_margin_y
            observed_margins.extend(
                (left_margin, top_margin, right_margin, bottom_margin)
            )
            checked += 1

    assert checked == 18
    assert min(observed_margins) >= min(minimum_margin_x, minimum_margin_y)
