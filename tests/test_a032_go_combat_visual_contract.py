"""Static contracts for A032's narrow Go Combat presentation layer."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
CSS = ROOT / "css" / "e10" / "go_combat_owner_reference_v1.css"
BOARD = ROOT / "js" / "game" / "board_renderer.js"
REVIEW_TRANSPORT = ROOT / "js" / "game" / "review_transport.js"
MAP_BATTLE = ROOT / "js" / "map_battle_v1_adapter.js"


def test_a032_uses_real_board_and_narrow_surface_marker():
    html = INDEX.read_text(encoding="utf-8")
    assert 'data-a032-combat-surface="v1"' in html
    assert 'id="board-canvas-wrap"' in html
    assert 'new WGo.Board' in html
    assert 'initBoard(size, cropInfo, attemptNumber)' in html
    assert BOARD.exists()
    assert "GoOdysseyBoardRenderer" in BOARD.read_text(encoding="utf-8")


def test_a032_keeps_existing_authoritative_combat_paths():
    html = INDEX.read_text(encoding="utf-8")
    review_transport = REVIEW_TRANSPORT.read_text(encoding="utf-8")
    map_battle = MAP_BATTLE.read_text(encoding="utf-8")
    assert "/api/srs/review" in review_transport
    assert "/api/adventure/map-battles/v1/answers" in map_battle
    assert "_mapBattleV1RenderAuthoritative" in html
    assert "updatePlayerHPUI" in html
    assert "PRESENTATION_CAN_AUTHORIZE_DAMAGE" not in html


def test_a032_has_no_new_fake_combat_controls_or_stats():
    html = INDEX.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assert 'id="a032-attack' not in html
    assert 'id="a032-defend' not in html
    assert "combat-power" not in html.lower()
    assert "recommended power" not in html.lower()
    assert "data-a032-combat-surface" in css


def test_a032_world_framing_does_not_cover_playable_board():
    css = CSS.read_text(encoding="utf-8")
    assert "e10_world_stage_v1_base.webp" in css
    assert ".quiz-board-anchor" in css
    assert "#board-canvas-wrap" in css
    assert "pointer-events: none" in css
    assert "background: #e8c57b" in css


def test_a032_responsive_board_priority_and_no_horizontal_overflow_contract():
    css = CSS.read_text(encoding="utf-8")
    assert "@media (max-width: 1024px)" in css
    assert "@media (max-width: 600px)" in css
    assert "calc(100vw - 36px)" in css
    assert "min-height: 44px" in css
    assert "height: auto !important" in css
    assert "overflow: visible !important" in css
    assert "prefers-reduced-motion: reduce" in css


def test_a032_runtime_boundary_is_frontend_only():
    html = INDEX.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assert "/api/" not in css
    assert "app.py" not in css
    assert "schema" not in css.lower()
    assert "/api/" not in html.split('data-a032-combat-surface="v1"', 1)[-1].split("</main>", 1)[0]
