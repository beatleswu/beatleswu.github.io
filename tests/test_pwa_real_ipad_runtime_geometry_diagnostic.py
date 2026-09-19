"""GO_ODYSSEY_PWA_REAL_IPAD_RUNTIME_GEOMETRY_DIAGNOSTIC_001.

The production fix candidate (3af808240) did not resolve the Owner's real
iPad. Rather than ship a fourth speculative CSS/JS fix based on emulation,
this adds a temporary, bounded, read-only diagnostic panel that reports the
EXACT runtime signals a real device sees -- window/screen/navigator/
matchMedia values, the actual recorded run of the portrait-tablet-override
algorithm (not a re-derivation), live computed geometry for the six named
shell elements, and the live Zone Card visibility decision already made by
world_stage.js -- as on-screen text the Owner can screenshot directly from
the installed PWA, with no Mac, no Safari remote inspector, and no need to
uninstall or clear any app state.

DIAGNOSTIC ONLY. This module asserts the panel exists, is inert by default,
captures every required signal, and ships no additional layout fix -- the
CSS/JS from the two earlier correctives (PWA desktop-breakpoint
misclassification, Zone4 intro-film) is unchanged.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")


def _panel_script():
    # The task-name marker also appears in the earlier detection script's
    # comment (documenting why it now records diagnostics); anchor on the
    # trigger element's own id instead, which only exists in the panel
    # script itself.
    idx = INDEX.index("go-pwa-diagnostic-trigger")
    start = INDEX.rindex("<script>", 0, idx)
    end = INDEX.index("</script>", start)
    return INDEX[start:end]


PANEL = _panel_script()


def test_diagnostic_panel_script_is_present_after_all_e9_shell_scripts():
    # Must load after shell.js so window.E9.isPortraitTabletOverride and the
    # live shell DOM are guaranteed present when the panel captures data.
    shell_js_pos = INDEX.index('src="/js/e9/shell.js')
    panel_pos = INDEX.index("go-pwa-diagnostic-trigger")
    body_close_pos = INDEX.index("</body>")
    assert shell_js_pos < panel_pos < body_close_pos


def test_trigger_is_invisible_and_does_not_block_normal_interaction():
    assert "go-pwa-diagnostic-trigger" in PANEL
    assert "background:transparent" in PANEL
    assert "width:60px;height:60px" in PANEL


def test_activation_requires_six_taps_within_a_bounded_window_not_one_tap():
    assert "tapCount >= 6" in PANEL
    assert "setTimeout(function () { tapCount = 0; }, 3000)" in PANEL


def test_close_button_exists_independent_of_the_corner_gesture():
    # The corner is covered by the panel's own content while open (the
    # button bar), so a reliable, unambiguous close path must not depend on
    # the same gesture landing on the same pixels.
    assert "關閉 Close" in PANEL
    assert "addEventListener('click', hidePanel)" in PANEL
    # The button bar must not sit on top of the external trigger's own
    # hit area, or a stray corner tap while the panel is open spam-clicks
    # whichever button renders first instead of doing anything useful.
    assert "margin-left:64px" in PANEL


def test_every_required_window_screen_navigator_signal_is_captured():
    for expr in (
        "window.innerWidth", "window.innerHeight",
        "html.clientWidth", "html.clientHeight",
        "vv.width", "vv.height", "vv.scale",
        "screen.width", "screen.height",
        "screen.availWidth", "screen.availHeight",
        "screen.orientation && screen.orientation.type",
        "screen.orientation && screen.orientation.angle",
        "window.devicePixelRatio",
        "navigator.userAgent", "navigator.platform", "navigator.maxTouchPoints",
    ):
        assert expr in PANEL, expr


def test_every_required_media_query_is_captured():
    for query in (
        "(display-mode: standalone)",
        "(orientation: portrait)",
        "(orientation: landscape)",
        "(min-width: 1280px)",
        "(max-width: 1279px)",
    ):
        assert query in PANEL, query


def test_portrait_override_diagnostic_reads_the_actual_recorded_run_not_a_reinference():
    # Must read window.__GO_PORTRAIT_DIAGNOSTIC__ (recorded by the real
    # detection script the moment it ran) rather than recomputing the
    # algorithm a second time inside the panel, which could silently drift
    # from what actually happened on the device.
    assert "window.__GO_PORTRAIT_DIAGNOSTIC__" in PANEL
    assert "window.__GO_PORTRAIT_TABLET_OVERRIDE__" in PANEL
    for field in (
        "portraitDiag.maxTouchPoints", "portraitDiag.userAgent",
        "portraitDiag.isAppleTouchSurface", "portraitDiag.hardwareOrientationSource",
        "portraitDiag.hardwareOrientation", "portraitDiag.matchMediaAvailable",
        "portraitDiag.viewportSaysPortrait", "portraitDiag.result",
    ):
        assert field in PANEL, field


def test_zone_card_decision_reads_the_live_dom_property_world_stage_js_set():
    # Must read #e9-world-stage-details.hidden directly -- the actual
    # decision world_stage.js's renderSelectedZone() already made -- not
    # recompute isPortraitTablet independently, which could disagree with
    # what really happened if the two code paths ever drift.
    assert "getElementById('e9-world-stage-details')" in PANEL
    assert "zoneCardEl.hidden" in PANEL


def test_all_six_required_shell_elements_are_captured():
    for selector in (
        "'#e9-adventure-shell'",
        "'#e9-map-stage'",
        "'#e9-map-stage .e9-map-stage__base'",
        "'#e9-world-stage-details'",
        "'#e9-bottom-dock-slot'",
        "'#e9-left-nav-slot'",
    ):
        assert selector in PANEL, selector


def test_element_snapshot_captures_every_required_computed_property():
    for prop in (
        "display", "position", "width", "height",
        "minWidth", "maxWidth", "minHeight", "maxHeight",
        "aspectRatio", "overflow", "flex", "gridTemplateColumns", "transform",
    ):
        assert prop in PANEL, prop


def test_panel_performs_no_network_call_and_mutates_no_app_state():
    # Read-only: no fetch/XHR, no localStorage/sessionStorage write, no
    # mutation of any element outside the panel's own DOM subtree.
    assert "fetch(" not in PANEL
    assert "XMLHttpRequest" not in PANEL
    assert ".setItem(" not in PANEL
    # The only DOM writes outside the panel's own tree are toggling the
    # existing data-go-portrait-tablet-override attribute, which is the
    # ALREADY-SHIPPED corrective's own behaviour (index.html's earlier
    # detection script), not something this diagnostic introduces.
    assert "appendChild(panel)" in PANEL
    assert "appendChild(trigger)" in PANEL


def test_diagnostic_does_not_change_the_two_prior_correctives():
    # SECONDARY_ZONE4_CINEMATIC_RESPONSIVE_DEFECT fix and the PWA desktop-
    # breakpoint override CSS/JS must be byte-for-byte the same shape as
    # before this diagnostic was added.
    assert '#boss-cinematic.intro-film[data-zone-key="k11_15"] .boss-cinematic-scene' in INDEX
    assert 'html[data-go-portrait-tablet-override] body[data-e10-visual-skin="immersive-rpg"] #e9-adventure-shell' in (
        ROOT / "css" / "e9" / "reference_world_map.css"
    ).read_text(encoding="utf-8")


def test_copy_button_uses_clipboard_api_with_a_silent_fallback():
    assert "navigator.clipboard && navigator.clipboard.writeText" in PANEL
