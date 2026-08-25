"""Static validation for the A030-R2 Bright Adventure palette lock."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "docs" / "planning" / "art"


def _read_json(name: str):
    return json.loads((ART / name).read_text(encoding="utf-8"))


def test_bright_adventure_is_the_only_canonical_palette():
    tokens = _read_json("a030_rpg_visual_tokens.json")
    expected = {
        "adventure_blue": "#1E6FC7",
        "go_odyssey_teal": "#39C9B6",
        "sun_yellow": "#F6C957",
        "adventure_orange": "#F29B52",
        "cream": "#FFF4D8",
        "sky": "#DDF2FF",
        "growth_green": "#72C96B",
        "magic_purple": "#8968D8",
        "deep_navy": "#173653",
    }
    assert tokens["status"] == "canonical"
    assert tokens["palette_lock"]["selected"] == "BRIGHT_ADVENTURE"
    assert tokens["palette_lock"]["candidate_b_status"] == "NOT_SELECTED"
    assert tokens["palette_lock"]["candidate_c_status"] == "NOT_SELECTED"
    assert all(tokens["palette"][key] == value for key, value in expected.items())
    assert tokens["boundaries"]["game_world_first"] is True
    assert tokens["boundaries"]["white_dashboard_direction_rejected"] is True


def test_surface_matrix_carries_the_same_palette_lock():
    surfaces = _read_json("a030_rpg_surface_matrix.json")
    lock = surfaces["palette_lock"]
    assert lock["selected"] == "BRIGHT_ADVENTURE"
    assert lock["candidate_a_status"] == "OWNER_SELECTED"
    assert lock["candidate_b_status"] == "NOT_SELECTED"
    assert lock["candidate_c_status"] == "NOT_SELECTED"
    assert lock["game_world_first"] is True
    assert lock["white_dashboard_direction"] == "REJECTED"
    assert lock["light_world_colorful_surfaces_percent"] == {"min": 65, "max": 75}
    assert lock["dark_structural_chrome_percent"] == {"min": 25, "max": 35}


def test_r1_comparison_is_marked_historical_and_owner_decided():
    report = (ART / "A030_R1_RPG_ART_SYSTEM_COLOR_DIRECTION_CLOSURE_001.md").read_text(encoding="utf-8")
    historical = _read_json("a030_r1_rpg_color_tokens.json")
    assert "Historical Decision Evidence" in report
    assert "A / BRIGHT_ADVENTURE — OWNER_SELECTED / CANONICAL" in report
    assert "B / COLORFUL_FANTASY — NOT_SELECTED" in report
    assert "C / WARM_STORYBOOK — NOT_SELECTED" in report
    assert historical["decision_status"] == "SUPERSEDED_BY_A030_R2_OWNER_PALETTE_LOCK"
    assert historical["candidate_status"] == {
        "A": "OWNER_SELECTED",
        "B": "NOT_SELECTED",
        "C": "NOT_SELECTED",
    }


def test_r2_bible_preserves_world_first_and_art_production_boundary():
    bible = (ART / "A030_RPG_ART_SYSTEM_V1_001.md").read_text(encoding="utf-8")
    r2 = (ART / "A030_R2_BRIGHT_ADVENTURE_CANONICAL_PALETTE_LOCK_001.md").read_text(encoding="utf-8")
    assert "`GAME_WORLD_FIRST=YES`" in bible
    assert "`WHITE_DASHBOARD_DIRECTION=REJECTED`" in bible
    assert "Final art production note" in bible
    assert "BRIGHT_ADVENTURE" in r2
    assert "does not create final item icons" in r2
