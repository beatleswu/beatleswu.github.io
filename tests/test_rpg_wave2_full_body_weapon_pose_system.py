"""Tests for the review-only full-body weapon-pose prototype."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/planning/rpg_wave2_full_body_weapon_pose_system"
MANIFEST = OUT / "manifest.json"
CHARACTERS = ("apprentice", "mage", "paladin")


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_full_body_pose_is_review_only_and_uses_the_new_pose_family():
    report = _manifest()
    assert report["task_id"] == "RPG_WAVE2_FULL_BODY_WEAPON_POSE_SYSTEM_PROTOTYPE_001"
    assert report["review_only"] is True
    assert report["pose_family"] == "ONE_HAND_SWORD_POSE"
    assert report["player_frame"]["id"] == "PLAYER_FRAME_A_STANDARD_CHIBI"
    assert report["characters"] == list(CHARACTERS)
    assert report["architecture"]["local_hand_patch_used"] is False
    assert report["architecture"]["local_forearm_patch_used"] is False
    assert report["architecture"]["oversized_grip_hand"] is False
    assert report["architecture"]["item_character_bespoke_redraws"] == 0
    assert report["architecture"]["full_body_pose_variant_count"] == 3


def test_pose_variants_are_true_alpha_normalized_and_have_no_preview_box():
    report = _manifest()
    for character in CHARACTERS:
        path = OUT / report["outputs"]["variants"][character]
        assert path.is_file(), character
        with Image.open(path) as image:
            assert image.mode == "RGBA"
            assert image.size == (1056, 1408)
            assert image.getchannel("A").getbbox() is not None
            assert image.getpixel((0, 0))[3] == 0
            assert image.getpixel((1055, 1407))[3] == 0
            assert all((r, g, b) == (0, 0, 0) for r, g, b, a in image.getdata() if a == 0)
    aggregate = report["aggregate_qa"]
    assert aggregate["pasted_limb_appearance_count"] == 0
    assert aggregate["alpha_artifacts"] == 0
    assert aggregate["white_box_artifacts"] == 0
    assert aggregate["matte_halo_artifacts"] == 0
    assert aggregate["chroma_residue"] == 0


def test_required_matrices_and_review_page_exist():
    report = _manifest()
    for key in ("matrix", "mobile_matrix", "comparison", "review_html"):
        assert (OUT / report["outputs"][key]).is_file(), key
    for key in ("matrix", "mobile_matrix", "comparison"):
        with Image.open(OUT / report["outputs"][key]) as image:
            assert image.mode == "RGB"
    html = (OUT / report["outputs"]["review_html"]).read_text(encoding="utf-8")
    for character in CHARACTERS:
        assert f'data-character="{character}"' in html
        assert f"variants/{character}_one_hand_sword_pose.png" in html
    assert "player_inventory.equipped" in html
    assert "PRESENTATION_ONLY" in html
    assert "fetch(" not in html
    assert "localStorage" not in html


def test_authority_and_compatibility_boundaries_are_explicit():
    report = _manifest()
    assert report["weapon"]["test_weapon"] == "iron_sword"
    assert report["weapon"]["universal_weapon_asset_count"] == 1
    assert report["weapon"]["runtime_asset_status"] == "NOT_CREATED_REVIEW_ONLY"
    assert report["modular_armor_compatibility"] == "REQUIRES_NEW_POSE_OVERLAY_VARIANT"
    assert report["fallback"] == {"unsupported_pose": "WAIST_SHEATHED", "presentation_only": True}
    assert report["authority"] == {
        "functional_equipment_ownership": "player_inventory",
        "functional_effects": "server EQUIPMENT_DEFS",
        "pose_selection": "PRESENTATION_ONLY",
        "client_combat_authority": "NO",
        "combat_delta": 0,
    }
    for entry in report["qa"]:
        assert entry["same_character_identity"] == "PASS_REVIEW_READY"
        assert entry["full_body_anatomy_coherence"] == "PASS_REVIEW_READY"
        assert entry["hand_grip_believability"] == "PASS_REVIEW_READY"
        assert entry["sword_recognizability"] == "PASS_REVIEW_READY"
        assert entry["sleeve_cuff_continuity"] == "PASS_REVIEW_READY"
        assert entry["mobile_readability"] == "PASS_REVIEW_READY"
        assert entry["pasted_limb_appearance"] == 0
