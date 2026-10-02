"""Focused WM-Q1 current-zone horizontal focus contracts.

The test is intentionally source-level: the browser receipt owns the numeric
viewport measurements, while this guard keeps the presentation implementation
inside the locked horizontal clamp boundary.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD_JS = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
WORLD_CSS = (ROOT / "css/e9/world_stage.css").read_text(encoding="utf-8")
REFERENCE_CSS = (ROOT / "css/e9/reference_world_map.css").read_text(encoding="utf-8")


def _function_body(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    end = source.find("\n  function ", start + 1)
    return source[start:] if end < 0 else source[start:end]


def test_current_zone_focus_uses_the_locked_horizontal_clamp_formula():
    focus = _function_body(WORLD_JS, "focusCurrentZone")
    for token in (
        "current_zone_center_x",
        "viewport_width",
        "desired_scroll_left = current_zone_center_x - viewport_center_x",
        "max_scroll_left",
        "target_scroll_left",
        "mapStage.scrollLeft = target_scroll_left",
        "data-wm-q1-clamped",
        "data-wm-q1-center-delta-x",
        "data-wm-q1-center-delta-y",
    ):
        assert token in focus
    assert "scrollIntoView" not in focus


def test_pan_surface_derives_width_from_governed_map_aspect_ratio_without_fake_space():
    pan = _function_body(WORLD_JS, "syncMapPanSurface")
    assert "Math.max(viewportWidth, viewportHeight * mapAspectRatio)" in pan
    assert "mobileCards ? 'auto' : viewportHeight + 'px'" in pan
    assert "ensureMapPanSurface(root)" in WORLD_JS
    assert ".e9-map-stage__pan-content" in REFERENCE_CSS
    assert "overflow-x: auto" in REFERENCE_CSS
    assert "overflow-y: hidden" in REFERENCE_CSS


def test_focus_runs_from_server_current_zone_and_preserves_existing_boundaries():
    render = _function_body(WORLD_JS, "renderZones")
    assert "var playerLocation = identities.current;" in render
    assert "focusCurrentZone(root, playerLocation);" in render
    assert "currentZoneKey" in WORLD_JS
    assert "selectedZoneKey" in WORLD_JS
    assert "data-player-location" in WORLD_JS
    assert "body[data-e10-visual-skin=\"immersive-rpg\"] #e9-map-stage" in REFERENCE_CSS
    assert ".e9-map-stage" in WORLD_CSS


def test_no_vertical_centering_or_intrinsic_spacing_hack_is_introduced():
    focus = _function_body(WORLD_JS, "focusCurrentZone")
    assert "scrollTop" not in focus
    assert "scrollIntoView" not in focus
    assert "padding" not in focus
