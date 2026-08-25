import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "docs" / "planning" / "art"


def _load_tokens():
    return json.loads((ART / "a030_r1_rpg_color_tokens.json").read_text(encoding="utf-8"))


def test_three_palette_candidates_are_exact_and_machine_readable():
    tokens = _load_tokens()
    assert list(tokens["palette_candidates"]) == ["A", "B", "C"]
    assert [tokens["palette_candidates"][key]["name"] for key in ("A", "B", "C")] == [
        "BRIGHT_ADVENTURE",
        "COLORFUL_FANTASY",
        "WARM_STORYBOOK",
    ]
    assert tokens["palette_candidates"]["A"]["recommended"] is True
    assert tokens["palette_candidates"]["B"]["recommended"] is False
    assert tokens["palette_candidates"]["C"]["recommended"] is False


def test_surface_balance_and_gold_policy_are_child_readable():
    tokens = _load_tokens()
    balance = tokens["surface_balance_target"]
    assert balance["light_world_colorful_surfaces_percent"] == {"min": 65, "max": 75}
    assert balance["dark_structural_chrome_percent"] == {"min": 25, "max": 35}
    assert tokens["gold_policy"]["default_panel_outline"] is False
    assert "LEGENDARY" in tokens["gold_policy"]["reserved_for"]
    assert list(tokens["rarity_language"]) == [
        "COMMON",
        "UNCOMMON",
        "RARE",
        "EPIC",
        "LEGENDARY",
    ]
    assert all(
        tokens["rarity_language"][rarity]["symbol"]
        and tokens["rarity_language"][rarity]["geometry"]
        for rarity in tokens["rarity_language"]
    )


def test_renderable_board_preserves_structure_and_required_views():
    board = (ART / "a030_r1_palette_comparison_board.html").read_text(encoding="utf-8")
    assert 'data-structure-source="A030 accepted renderable board; color variables only"' in board
    for palette in ("a", "b", "c"):
        assert f'data-palette="{palette}"' in board
    for view in (
        "equipment-comparison",
        "candidate-a-equipment",
        "candidate-a-combat",
        "candidate-a-reward",
        "candidate-a-shop",
        "palette-contact-sheet",
    ):
        assert f'id="{view}"' in board
        assert f'data-view="{view}"' in board
    assert "GET /api/" not in board
    assert "app.py" not in board
