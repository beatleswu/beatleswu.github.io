"""VS1D-1 static contracts for the immersive World Stage layers."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "components/adventure/world_stage.html").read_text(encoding="utf-8")
JS = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
CSS = (ROOT / "css/e9/world_stage.css").read_text(encoding="utf-8")
RWD_CSS = (ROOT / "css/e9/rwd.css").read_text(encoding="utf-8")
CARDS_JS = (ROOT / "js/e9/right_cards.js").read_text(encoding="utf-8")
CARDS_HTML = (ROOT / "components/adventure/right_cards.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")


def test_governed_base_map_and_independent_route_are_present():
    assert '/assets/maps/e10_world_stage_v1_base.webp' in HTML
    assert '<svg class="e9-map-stage__route"' in HTML
    assert 'pointer-events: none' in CSS
    assert 'e9-route__ascension' in HTML


def test_all_ten_canonical_keys_have_normalized_node_and_reserved_boss_anchors():
    for key in ('k26_30', 'k21_25', 'k16_20', 'k11_15', 'k6_10', 'k1_5', 'd1_2', 'd3_4', 'd5_6', 'd7_plus'):
        assert key in JS
    assert 'var ZONE_ANCHORS' in JS
    assert 'var BOSS_ANCHORS' in JS
    assert "data-zone-boss-anchor" in JS


def test_nodes_are_real_buttons_and_locked_nodes_never_receive_activation_handlers():
    assert "document.createElement('button')" in JS
    assert 'tile.disabled = true;' in JS
    assert 'if (!zone.locked) {' in JS
    assert "window.E9.startAdventureFromE9(zone.key)" in JS


def test_mobile_uses_ordered_dom_journey_instead_of_shrinking_the_map():
    assert '@media (max-width: 767px)' in CSS
    assert '.e9-map-stage__nodes { position: absolute;' in CSS
    assert 'object-position: var(--focus-x) var(--focus-y)' in CSS
    assert "mapStage.style.setProperty('--focus-x'" in JS
    assert "e9-zone__inline-details" in JS
    assert "behavior: 'smooth'" in JS
    assert 'grid-auto-rows: minmax(75px, auto)' in CSS


def test_right_drawer_is_closed_by_default_and_uses_existing_payload_summary():
    assert 'id="e9-right-drawer-toggle"' in CARDS_HTML
    assert 'aria-controls="e9-right-drawer-panel"' in CARDS_HTML
    assert 'aria-expanded="false"' in CARDS_HTML
    assert 'setOpen(false);' in CARDS_JS
    assert "d.cleared" in CARDS_JS and "d.total" in CARDS_JS
    assert 'e10.world_stage.progress_compact' in CARDS_JS
    assert 'e9-drawer-mobile-summary' in CARDS_HTML


def test_progress_initial_copy_and_map_aria_labels_use_runtime_i18n_contracts():
    assert CARDS_HTML.count('data-i18n="e10.world_stage.progress_compact"') == 2
    assert '進度 0/0' not in CARDS_HTML
    assert 'Progress {n}/{t}' not in CARDS_JS
    assert "function formatCompactProgress(cleared, total)" in CARDS_JS
    assert "return t('e10.world_stage.progress_compact', '')" in CARDS_JS
    assert "setCompactProgress(root, 0, 0);" in CARDS_JS
    assert "setCompactProgress(root, d.cleared, d.total);" in CARDS_JS
    assert 'data-i18n-aria-label="e10.world_stage.map_aria_label"' in HTML
    assert 'data-i18n-aria-label="e10.world_stage.zones_aria_label"' in HTML
    assert 'aria-label="Adventure world map"' not in HTML
    assert 'aria-label="Adventure zones"' not in HTML
    for key, en, zh in (
        ('e10.world_stage.progress_compact', 'Progress {n}/{t}', '進度 {n}/{t}'),
        ('e10.world_stage.map_aria_label', 'Adventure world map', '冒險世界地圖'),
        ('e10.world_stage.zones_aria_label', 'Adventure zones', '冒險區域'),
    ):
        assert key in I18N and en in I18N and zh in I18N
    assert "aria-controls=\"e9-right-drawer-panel\"" in CARDS_HTML
    assert "aria-expanded=\"false\"" in CARDS_HTML

    start = CARDS_JS.index('function formatCompactProgress(cleared, total)')
    end = CARDS_JS.index('\n  function setCompactProgress', start)
    formatter = CARDS_JS[start:end]
    result = subprocess.run(
        ['node', '-e', "function t() { return 'Progress {n}/{t}'; }\n" + formatter + "\nconsole.log(formatCompactProgress(9, 10));"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == 'Progress 9/10'


def test_right_drawer_escape_and_lifecycle_listener_contract():
    assert "evt.key === 'Escape'" in CARDS_JS
    assert "window.E9.on(toggle, 'click'" in CARDS_JS
    assert "window.E9.on(document, 'keydown'" in CARDS_JS
    assert 'localStorage' not in CARDS_JS


def test_nodes_have_dom_number_and_state_markers_and_hidden_details_do_not_render():
    assert "e9-zone__number" in JS
    assert "e9-zone__state" in JS
    assert "data-zone-state" in JS
    assert "isCompleted ? '\\u2713' : ''" in JS
    assert 'data-zone-state="locked"' in CSS
    assert '.e9-zone__state[data-zone-state="locked"]::before' in CSS
    assert 'right: 2px; top: 2px;' in CSS
    assert '.e9-zone__number { position: relative; z-index: 3;' in CSS
    assert '.e9-zone-details[hidden] { display: none; }' in CSS


def test_tablet_drawer_is_an_overlay_and_hidden_detail_panel_has_no_layout_box():
    assert '.e9-zone-details[hidden] { display: none; }' in CSS
    assert '@media (min-width: 768px) and (max-width: 1279px)' in RWD_CSS
    assert '#right-cards .e9-drawer-panel:not([hidden])' in RWD_CSS
    assert 'position: fixed;' in RWD_CSS
    assert 'overflow-y: auto;' in RWD_CSS
