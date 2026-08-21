"""Tests for ONE_HAND_SWORD_POSE plus modular dragon_scale compatibility."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/planning/rpg_wave2_weapon_pose_armor_compatibility"
MANIFEST = OUT / "manifest.json"
CHARACTERS = ("apprentice", "mage", "paladin")
CANONICAL_DRAGON_SCALE = ROOT / "assets/hero/equipment/wearables/overlays/dragon_scale.png"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_compatibility_scope_uses_one_pose_overlay_without_character_armor_assets():
    report = _manifest()
    assert report["task_id"] == "RPG_WAVE2_WEAPON_POSE_ARMOR_COMPATIBILITY_PROTOTYPE_001"
    assert report["head_before"] == "bac3cce880ec90539aa068760798120a834ed15d"
    assert report["test_pose"] == "ONE_HAND_SWORD_POSE"
    assert report["test_weapon"] == "iron_sword"
    assert report["test_armor"] == "dragon_scale"
    assert report["characters"] == list(CHARACTERS)
    assert report["pose_specific_armor_overlay_count"] == 1
    assert report["character_specific_armor_asset_count"] == 0
    assert report["item_character_bespoke_redraws"] == 0
    assert report["modular_armor_on_weapon_pose"] == "PASS"
    assert report["default_dragon_scale_changed"] == "NO"


def test_pose_aware_overlay_is_true_alpha_and_clears_face_zone():
    report = _manifest()
    overlay = OUT / report["outputs"]["pose_aware_overlay"]
    with Image.open(overlay) as image:
        assert image.mode == "RGBA"
        assert image.size == (1056, 1408)
        alpha = np.asarray(image.getchannel("A"))
        assert alpha.max() == 255
        assert alpha[0, 0] == 0
        left, top, right, bottom = report["safe_zones"]["face_safe_zone"]
        assert alpha[top:bottom, left:right].max() == 0
        pixels = np.asarray(image)
        assert np.all(pixels[alpha == 0, :3] == 0)
    assert report["safe_zones"]["face_safe_zone_violations"] == 0
    assert report["aggregate_qa"]["white_box"] == 0
    assert report["aggregate_qa"]["matte_halo"] == 0
    assert report["aggregate_qa"]["alpha_artifacts"] == 0


def test_all_three_pose_composites_and_matrices_are_present():
    report = _manifest()
    for character in CHARACTERS:
        path = OUT / report["outputs"]["composites"][character]
        assert path.is_file(), character
        with Image.open(path) as image:
            assert image.mode == "RGBA"
            assert image.size == (1056, 1408)
            assert image.getchannel("A").getbbox() is not None
    for key in ("matrix", "mobile_matrix", "comparison_matrix"):
        path = OUT / report["outputs"][key]
        assert path.is_file(), key
        with Image.open(path) as image:
            assert image.mode == "RGB"
    html = (OUT / report["outputs"]["review_html"]).read_text(encoding="utf-8")
    for character in CHARACTERS:
        assert f'data-character="{character}"' in html
    assert "player_inventory" in html
    assert "fetch(" not in html
    assert "localStorage" not in html


def test_default_dragon_scale_source_is_unchanged_and_authority_is_presentation_only():
    report = _manifest()
    assert _sha256(CANONICAL_DRAGON_SCALE) == "3a2a84a421b7b80039dc38b43b9447e7b1997f2f04aab826c35b6d6f5a5526c1"
    assert report["source_sha256"]["default_canonical_overlay"] == "3a2a84a421b7b80039dc38b43b9447e7b1997f2f04aab826c35b6d6f5a5526c1"
    assert report["authority"] == {
        "functional_equipment": "player_inventory",
        "weapon_effects": "server EQUIPMENT_DEFS",
        "armor_effects": "server EQUIPMENT_DEFS",
        "pose_and_overlay": "PRESENTATION_ONLY",
        "client_combat_authority": "NO",
        "combat_delta_from_rendering": 0,
    }
    assert report["preserved"]["dragon_scale_default_asset"] == "UNCHANGED"
    assert report["preserved"]["other_characters"] == "NOT_TESTED"
    assert report["preserved"]["other_weapons"] == "NOT_TESTED"
    for entry in report["qa"]:
        assert entry["armor_fit"] == "PASS_REVIEW_READY"
        assert entry["weapon_grip"] == "PASS_REVIEW_READY"
        assert entry["shoulder_clearance"] == "PASS_REVIEW_READY"
        assert entry["arm_clearance"] == "PASS_REVIEW_READY"
        assert entry["face_clearance"] == "PASS"
        assert entry["sword_visibility"] == "PASS_REVIEW_READY"
        assert entry["character_identity"] == "PASS_REVIEW_READY"
        assert entry["mobile_readability"] == "PASS_REVIEW_READY"
        assert entry["armor_covers_sword_hand"] is False
        assert entry["armor_clips_weapon"] is False
