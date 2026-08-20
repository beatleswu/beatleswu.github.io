"""Contracts for the first template-first modular equipment art batch."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
P1_ROOT = ROOT / "docs/planning/rpg_wave2_modular_equipment_production_v2_p1"
MANIFEST = P1_ROOT / "manifest.json"

EXPECTED_ITEMS = {
    "iron_sword": "WEAPON_WAIST",
    "dragon_scale": "TORSO_ARMOR",
    "fox_mask": "FACE_ACCESSORY",
    "void_mantle": "SHOULDER_MANTLE",
}
CHARACTERS = {
    "apprentice",
    "mage",
    "paladin",
    "trail_apprentice",
    "night_runner",
    "constellation_apprentice",
}


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_p1_selects_four_template_authorized_reference_items():
    report = _manifest()
    assert report["task_id"] == "RPG_WAVE2_MODULAR_2D_EQUIPMENT_PRODUCTION_V2_P1_001"
    assert report["foundation_head"] == "2575e79f14b62e3880cd66f61a4055cf01d67e1b"
    assert report["selected_templates"] == EXPECTED_ITEMS
    assert set(report["selected_items"]) == set(EXPECTED_ITEMS)
    assert report["selected_items"] == ["iron_sword", "dragon_scale", "fox_mask", "void_mantle"]
    assert report["inventory_only_policy"] == {"go_stone_black": "NONE"}


def test_p1_has_all_24_template_first_qa_results_and_no_bespoke_redraws():
    report = _manifest()
    assert report["characters"] == sorted(CHARACTERS, key=lambda value: [
        "apprentice", "mage", "paladin", "trail_apprentice", "night_runner", "constellation_apprentice",
    ].index(value))
    assert len(report["qa_matrix"]) == 24
    assert report["counts"] == {
        "fit_combinations": 24,
        "fit_pass_count": 24,
        "face_safe_zone_violations": 0,
        "alpha_artifacts": 0,
        "white_box_artifacts": 0,
        "matte_halo": 0,
        "chroma_residue": 0,
        "item_character_bespoke_redraws": 0,
    }
    assert all(entry["result"] == "PASS" for entry in report["qa_matrix"])
    assert all(entry["bespoke_redraw"] is False for entry in report["qa_matrix"])
    assert all(set(entry["metrics"]) == {
        "FACE_CLEARANCE", "HEAD_CLEARANCE", "SHOULDER_FIT", "TORSO_FIT", "WAIST_FIT",
        "HAIR_COLLISION", "ROBE_COLLISION", "ARMOR_COLLISION", "DEPTH_ORDER",
        "MOBILE_READABILITY", "ITEM_RECOGNIZABILITY", "CHARACTER_IDENTITY_PRESERVATION",
    } for entry in report["qa_matrix"])


def test_p1_overlays_are_true_alpha_and_inside_canonical_template_bounds():
    report = _manifest()
    for item_id, item in report["equipment"].items():
        path = P1_ROOT / item["asset"]
        assert path.is_file(), item_id
        with Image.open(path) as image:
            assert image.size == (1056, 1408), item_id
            rgba = image.convert("RGBA")
            assert rgba.getchannel("A").getbbox() is not None, item_id
            for red, green, blue, alpha in rgba.getdata():
                if alpha == 0:
                    assert (red, green, blue) == (0, 0, 0), item_id
            assert item["alpha_audit"]["inside_template_bbox"] is True
            assert item["alpha_audit"]["alpha_artifacts"] == 0
            assert item["alpha_audit"]["transparent_rgb_nonzero"] == 0


def test_p1_matrices_and_review_are_static_review_artifacts():
    report = _manifest()
    desktop = P1_ROOT / report["outputs"]["desktop_matrix"]
    mobile = P1_ROOT / report["outputs"]["mobile_matrix"]
    review = P1_ROOT / report["outputs"]["review_html"]
    assert desktop.is_file()
    assert mobile.is_file()
    assert review.is_file()
    with Image.open(desktop) as image:
        assert image.mode == "RGB"
        assert image.width == 1236
    with Image.open(mobile) as image:
        assert image.mode == "RGB"
        assert image.width == 430
    html = review.read_text(encoding="utf-8")
    for item_id in EXPECTED_ITEMS:
        assert f'data-item="{item_id}"' in html
    for character in CHARACTERS:
        assert f'data-character="{character}"' in html
    assert "player_inventory" in html
    assert "fetch(" not in html
    assert "go_stone_black" not in html


def test_p1_preserves_presentation_only_authority():
    report = _manifest()
    assert report["authority"] == {
        "ownership": "player_inventory",
        "equipped": "player_inventory.equipped",
        "effects": "server EQUIPMENT_DEFS",
        "wearable_renderer": "presentation only",
        "client_combat_authority": False,
        "combat_delta": 0,
    }
    assert report["template_first_workflow"]["post_hoc_character_dragging"] is False
    assert report["template_first_workflow"]["character_specific_art"] is False
    assert report["template_first_workflow"]["runtime_wiring_expanded"] is False
