"""Focused review-only contract checks for Sword Pose Batch 2."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/planning/rpg_wave2_full_body_weapon_pose_batch2"
MANIFEST = OUT / "manifest.json"
REVIEW = OUT / "one_hand_sword_pose_batch2_review.html"
BATCH = ("trail_apprentice", "night_runner", "constellation_apprentice")
APPROVED = ("apprentice", "mage", "paladin")
ALL = APPROVED + BATCH


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_batch2_scope_and_authority_are_explicit():
    report = _manifest()
    assert report["task_id"] == "RPG_WAVE2_ONE_HAND_SWORD_POSE_BATCH2_001"
    assert report["base_head"] == "bac3cce880ec90539aa068760798120a834ed15d"
    assert report["method"] == "FULL_BODY_POSE_REDRAW"
    assert report["pose_family"] == "ONE_HAND_SWORD_POSE"
    assert report["player_frame"]["id"] == "PLAYER_FRAME_A_STANDARD_CHIBI"
    assert report["batch2_characters"] == list(BATCH)
    assert report["approved_reference_characters"] == list(APPROVED)
    assert report["total_one_hand_sword_pose_count"] == 6
    assert report["architecture"] == {
        "local_hand_patch_used": False,
        "local_forearm_patch_used": False,
        "item_character_bespoke_weapon_art": False,
        "item_character_bespoke_redraws": 0,
        "full_body_pose_variant_count": 3,
        "review_composites_include_weapon_pixels": True,
        "runtime_composition_still_requires_universal_weapon_layer": True,
    }
    assert report["weapon"]["test_weapon"] == "iron_sword"
    assert report["weapon"]["universal_weapon_asset_count"] == 1
    assert report["authority"] == {
        "functional_equipment_ownership": "player_inventory",
        "functional_effects": "server EQUIPMENT_DEFS",
        "pose_selection": "PRESENTATION_ONLY",
        "client_combat_authority": "NO",
        "combat_delta": 0,
    }


def test_batch2_variants_are_full_canvas_true_alpha_and_clean():
    report = _manifest()
    assert set(report["outputs"]["variants"]) == set(BATCH)
    for character in BATCH:
        path = OUT / report["outputs"]["variants"][character]
        assert path.is_file(), character
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            assert rgba.size == (1056, 1408)
            assert rgba.getchannel("A").getbbox() is not None
            assert rgba.getpixel((0, 0))[3] == 0
            assert rgba.getpixel((1055, 1407))[3] == 0
            assert all((r, g, b) == (0, 0, 0) for r, g, b, a in rgba.get_flattened_data() if a == 0)
    assert report["aggregate_qa"]["pasted_limb_appearance_count"] == 0
    assert report["aggregate_qa"]["alpha_artifacts"] == 0
    assert report["aggregate_qa"]["white_box_artifacts"] == 0
    assert report["aggregate_qa"]["matte_halo_artifacts"] == 0
    assert report["aggregate_qa"]["chroma_residue"] == 0


def test_batch2_and_final_six_matrices_and_review_exist():
    report = _manifest()
    for key in ("batch_matrix", "batch_mobile_matrix", "final_matrix", "final_mobile_matrix", "review_html"):
        assert (OUT / report["outputs"][key]).is_file(), key
    for key in ("batch_matrix", "batch_mobile_matrix", "final_matrix", "final_mobile_matrix"):
        with Image.open(OUT / report["outputs"][key]) as image:
            assert image.mode == "RGB"
    html = REVIEW.read_text(encoding="utf-8")
    for character in ALL:
        assert f'data-character="{character}"' in html
    assert "player_inventory" in html
    assert "EQUIPMENT_DEFS" in html
    assert "PRESENTATION_ONLY" in html
    assert "client combat authority is <code>NO</code>" in html
    assert "fetch(" not in html
    assert "localStorage" not in html
    for forbidden in ("dragon_scale", "fox_mask", "void_mantle"):
        assert forbidden not in html


def test_each_batch2_visual_qa_record_is_review_ready():
    report = _manifest()
    assert len(report["qa"]) == 3
    for entry, character in zip(report["qa"], BATCH):
        assert entry["character_key"] == character
        assert entry["same_character_identity"] == "PASS_REVIEW_READY"
        assert entry["full_body_anatomy_coherence"] == "PASS_REVIEW_READY"
        assert entry["hand_grip_believability"] == "PASS_REVIEW_READY"
        assert entry["sword_recognizability"] == "PASS_REVIEW_READY"
        assert entry["mobile_readability"] == "PASS_REVIEW_READY"
        assert entry["pasted_limb_appearance"] == 0
