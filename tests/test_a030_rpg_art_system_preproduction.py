"""Static validation for the A030 docs/design-only art system package."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "docs" / "planning" / "art"


def _read_json(name: str):
    with (ART / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def test_a030_machine_readable_packages_parse_and_cover_required_surfaces():
    tokens = _read_json("a030_rpg_visual_tokens.json")
    surfaces = _read_json("a030_rpg_surface_matrix.json")
    taxonomy = _read_json("a030_rpg_asset_taxonomy.json")

    assert tokens["task"] == "A030_RPG_ART_SYSTEM_V1_PREPRODUCTION_001"
    assert tokens["boundaries"]["presentation_authorizes_reward"] is False
    assert tokens["boundaries"]["lord_trial_visual_authority_separate"] is True
    assert taxonomy["runtime_move_in_a030"] is False

    required = {
        "ADVENTURE_WORLD",
        "HERO_OVERVIEW",
        "BACKPACK",
        "EQUIPMENT_LOADOUT",
        "COMBAT",
        "REWARD_DROP",
        "SHOP",
        "SPIRIT_COMPANION",
        "BATTLEFIELD_BOSS",
        "QUEST",
    }
    rows = surfaces["surfaces"]
    assert {row["surface_id"] for row in rows} == required
    assert len(rows) == len(required)
    for row in rows:
        for key in (
            "current_runtime_exists",
            "visual_priority",
            "gameplay_importance",
            "art_system_component_dependencies",
            "runtime_data_dependencies",
            "desktop_layout_required",
            "mobile_layout_required",
            "final_asset_dependency",
            "implementation_phase",
        ):
            assert key in row


def test_a030_board_is_self_contained_and_has_required_renderable_evidence_views():
    board = (ART / "a030_core_loop_visual_board.html").read_text(encoding="utf-8")
    assert "A030" in board
    assert "assets/maps/e10_world_stage_v2_clean.webp" in board
    assert "data-surface=\"equipment-backpack\"" in board
    assert "data-surface=\"combat\"" in board
    assert "data-surface=\"reward-drop\"" in board
    assert "data-surface=\"shop\"" in board
    for evidence_id in (
        "01_equipment_backpack_desktop",
        "03_combat_desktop",
        "05_reward_desktop",
        "07_shop_desktop",
        "09_tablet_reference",
        "10_core_loop_storyboard",
        "11_visual_system_contact_sheet",
    ):
        assert f'data-evidence="{evidence_id}"' in board
    assert "https://" not in board
    assert "http://" not in board
    assert "gacha" not in board.lower()


def test_a030_visual_boundaries_are_documented():
    bible = (ART / "A030_RPG_ART_SYSTEM_V1_001.md").read_text(encoding="utf-8")
    for phrase in (
        "Lord Trial is not a fourth tier",
        "The Go board is the main interaction",
        "Functional Equipment is visibly different from pure cosmetics",
        "No roulette, spin, paid reveal",
        "A030 does not move or promote any assets",
        "Explicit non-goals",
    ):
        assert phrase in bible
