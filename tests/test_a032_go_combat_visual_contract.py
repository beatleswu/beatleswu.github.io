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


def test_a032_r1_stacked_layout_is_board_first_and_prompt_stays_in_flow():
    css = CSS.read_text(encoding="utf-8")
    html = INDEX.read_text(encoding="utf-8")
    assert 'grid-template-areas: "board" "battle" !important' in css
    assert "#msg-box" in css
    assert "position: relative !important" in css
    assert "inset: auto !important" in css
    assert ".sgf-report-widget" in css
    assert "position: static !important" in css
    assert "a032-board-safe" in html
    assert "insertBefore(el, actionRow)" in html


def test_a032_r1_prevents_narrow_monster_identity_ellipsis():
    css = CSS.read_text(encoding="utf-8")
    assert "#monster-name" in css
    assert "white-space: normal !important" in css
    assert "text-overflow: clip !important" in css
    assert "overflow-wrap: anywhere" in css


def test_a032_r1_localizes_combat_question_and_report_surface_without_new_authority():
    html = INDEX.read_text(encoding="utf-8")
    widget = (ROOT / "sgf_report_widget.js").read_text(encoding="utf-8")
    assert "function _a032QuestionTitle(q)" in html
    assert "_zoneName(_ZONE_BY_KEY[zoneKey])" in html
    assert "mk.problemReport.trigger" in widget
    assert "mk.problemReport.reason.display_glitch" in widget
    assert "data-sgf-report-surface=\"main_practice\"" in widget
    assert "document.body.appendChild(host)" not in widget
    assert "_a032RefreshCombatLocale" in html
    assert "removeAttribute('data-i18n')" in html


def test_a032_r1_static_urls_use_existing_cache_busting_policy():
    html = INDEX.read_text(encoding="utf-8")
    assert "/css/e10/go_combat_owner_reference_v1.css?v=a032r1" in html
    assert "/sgf_report_widget.js?v=a032r1" in html


def test_a032_runtime_boundary_is_frontend_only():
    html = INDEX.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assert "/api/" not in css
    assert "app.py" not in css
    assert "schema" not in css.lower()
    assert "/api/" not in html.split('data-a032-combat-surface="v1"', 1)[-1].split("</main>", 1)[0]
