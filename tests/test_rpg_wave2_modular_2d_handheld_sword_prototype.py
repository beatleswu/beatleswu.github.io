"""Tests for the review-only reusable handheld sword pose prototype."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/planning/rpg_wave2_modular_2d_handheld_sword_prototype"
MANIFEST = OUT / "manifest.json"
CHARACTERS = (
    "apprentice",
    "mage",
    "paladin",
    "trail_apprentice",
    "night_runner",
    "constellation_apprentice",
)


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_handheld_prototype_is_exactly_scoped_and_presentation_only():
    report = _manifest()
    assert report["task_id"] == "RPG_WAVE2_MODULAR_2D_HANDHELD_SWORD_PROTOTYPE_001"
    assert report["foundation_head"] == "2575e79f14b62e3880cd66f61a4055cf01d67e1b"
    assert report["head_before"] == "336f0ba1b93923384d329449556de2b53db2e739"
    assert report["review_only"] is True
    assert report["player_frame"]["id"] == "PLAYER_FRAME_A_STANDARD_CHIBI"
    assert report["weapon"]["id"] == "iron_sword"
    assert report["weapon"]["family"] == "HANDHELD_SWORD"
    assert report["authority"] == {
        "functional_equipment_ownership": "player_inventory",
        "functional_equipment_equipped": "player_inventory.equipped",
        "functional_effects": "server EQUIPMENT_DEFS",
        "renderer": "PRESENTATION_ONLY",
        "client_combat_authority": "NO",
        "combat_delta_from_rendering": 0,
    }
    assert report["fallback"] == {
        "missing_grip_pose": "WAIST_SHEATHED",
        "presentation_only": True,
        "unequip": False,
        "database_write": False,
    }
    assert report["security_checks"] == {
        "unowned_visual_forgery": "FAIL_CLOSED_NO_RUNTIME_STATE_INPUT",
        "authoritative_equipped_state": "UNCHANGED",
        "missing_grip_pose_fallback": "WAIST_SHEATHED",
    }


def test_one_universal_weapon_and_six_reusable_pose_assets():
    report = _manifest()
    assert report["architecture"] == {
        "character_grip_pose_asset_count": 6,
        "universal_weapon_asset_count": 1,
        "mask_asset_count": 6,
        "item_character_bespoke_redraws": 0,
        "weapon_art_is_universal": True,
        "pose_assets_are_reusable_character_assets": True,
    }
    assert [entry["character_key"] for entry in report["pose_assets"]] == list(CHARACTERS)
    assert report["aggregate_qa"]["fake_open_hand_grip"] == 0
    assert report["aggregate_qa"]["fit_pass_count"] == 6


def test_pose_assets_and_composites_are_true_alpha_without_background_artifacts():
    report = _manifest()
    for entry in report["pose_assets"]:
        for relative in (entry["asset"],):
            path = OUT / relative
            with Image.open(path) as image:
                assert image.mode == "RGBA"
                assert image.getchannel("A").getbbox() is not None
                assert all((r, g, b) == (0, 0, 0) for r, g, b, a in image.getdata() if a == 0)
    assert report["aggregate_qa"]["alpha_artifacts"] == 0
    assert report["aggregate_qa"]["white_box_artifacts"] == 0
    assert report["aggregate_qa"]["matte_halo_artifacts"] == 0
    assert report["aggregate_qa"]["chroma_residue"] == 0
    for character in CHARACTERS:
        for mode in ("handheld", "waist"):
            path = OUT / "composites" / mode / f"{character}.png"
            with Image.open(path) as image:
                assert image.size == (1056, 1408)
                assert image.mode == "RGBA"


def test_required_review_matrices_and_fallback_review_exist():
    report = _manifest()
    for output_key in ("handheld_matrix", "handheld_mobile_matrix", "handheld_vs_waist_matrix", "review_html"):
        output = report["outputs"][output_key]
        path = OUT / output
        assert path.is_file(), output
    with Image.open(OUT / report["outputs"]["handheld_matrix"]) as image:
        assert image.mode == "RGB"
        assert image.width == 6 * 230 + 5 * 14 + 2 * 20
    with Image.open(OUT / report["outputs"]["handheld_mobile_matrix"]) as image:
        assert image.mode == "RGB"
        assert image.width == 3 * 160 + 2 * 10 + 2 * 16
    html = (OUT / report["outputs"]["review_html"]).read_text(encoding="utf-8")
    for character in CHARACTERS:
        assert f'data-character="{character}"' in html
    assert 'data-mode="handheld"' in html
    assert 'data-mode="waist"' in html
    assert "player_inventory.equipped" in html
    assert "server EQUIPMENT_DEFS" in html
    assert "fetch(" not in html
    assert "localStorage" not in html


def test_owner_references_are_not_runtime_art_sources_and_other_approved_items_are_locked():
    report = _manifest()
    assert report["owner_references"] == {
        "reference_a_used": True,
        "reference_b_used": True,
        "usage": "VISUAL_DIRECTION_ONLY",
        "pixels_reused": False,
    }
    assert report["preserved"] == {
        "dragon_scale_changed": "NO",
        "fox_mask_changed": "NO",
        "void_mantle_changed": "NO",
        "go_stone_black_render": "NONE",
        "waist_sheathed_fallback": "PASS",
    }
    assert not list(OUT.rglob("iron_sword_apprentice*"))
    assert not list(OUT.rglob("iron_sword_mage*"))
    assert not list(OUT.rglob("iron_sword_paladin*"))
