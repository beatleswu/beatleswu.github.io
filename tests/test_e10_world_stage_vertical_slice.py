"""VS1D-1 static contracts for the immersive World Stage layers."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "components/adventure/world_stage.html").read_text(encoding="utf-8")
JS = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
CSS = (ROOT / "css/e9/world_stage.css").read_text(encoding="utf-8")
CARDS_JS = (ROOT / "js/e9/right_cards.js").read_text(encoding="utf-8")
CARDS_HTML = (ROOT / "components/adventure/right_cards.html").read_text(encoding="utf-8")


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


def test_right_drawer_is_closed_by_default_and_uses_existing_payload_summary():
    assert 'id="e9-right-drawer-toggle"' in CARDS_HTML
    assert 'aria-controls="e9-right-drawer-panel"' in CARDS_HTML
    assert 'aria-expanded="false"' in CARDS_HTML
    assert 'setOpen(false);' in CARDS_JS
    assert "d.cleared" in CARDS_JS and "d.total" in CARDS_JS


def test_right_drawer_escape_and_lifecycle_listener_contract():
    assert "evt.key === 'Escape'" in CARDS_JS
    assert "window.E9.on(toggle, 'click'" in CARDS_JS
    assert "window.E9.on(document, 'keydown'" in CARDS_JS
    assert 'localStorage' not in CARDS_JS
