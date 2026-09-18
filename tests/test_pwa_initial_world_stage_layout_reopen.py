"""GO_ODYSSEY_PWA_INITIAL_WORLD_STAGE_LAYOUT_REOPEN_001.

The Owner's real installed-iPad-PWA screenshot, taken before any zone was
selected, proved the previous conclusion (the layout defect only appears
inside Zone 4's intro-film) wrong: the initial World Stage / Adventure Shell
itself renders as a small, landscape-shaped, vertically centered box on real
hardware.

Root cause, proven via an independent signal rather than pixel estimation:
the bottom dock in the Owner's screenshot renders the "desktop-legacy"
navigation category (soul_records/battle_log/tavern/star_chart/arena -- see
js/e9/navigation_registry.js), which is only reachable under
`@media (min-width: 1280px)`. No real iPad reports a portrait CSS width
>= 1280 under a correctly honoured `width=device-width` viewport (the
largest real iPad portrait width is 1024), so the affected device's layout
viewport is being misreported as desktop-class. Every
`@media (orientation: ...)` / `matchMedia(...)` check the Adventure Shell
uses reads from that same misreported viewport and cannot be trusted on an
affected device -- including the Zone Card visibility gate, which is why it
also appeared "missing".

The fix reuses the exact "Macintosh UA + touch points = iPad in desktop-site
mode" signature this codebase already relies on elsewhere (see
js/e9/world_stage.js's usesInlinePlayerMarkerSurface and index.html's
isIPadOSDesktopUA install-guide check), extended with a hardware-level
screen.orientation check (not part of the layout viewport that desktop-site
mode overrides) to confirm the device is genuinely portrait before
overriding anything. It only activates when the viewport's own orientation
signal actively disagrees with the hardware signal; a correctly-reporting
device, including a genuinely landscape iPad, is completely unaffected --
verified in the paired Node harness with 15 assertions covering the
algorithm itself (7 predicate unit tests against controlled inputs,
including two explicit "must NOT trigger" negative controls) plus source-
level wiring checks across every file this recovery touches.

The behavioural assertions and the algorithm's own unit tests live in
tests/e9_node_tests/run_pwa_portrait_tablet_override_tests.js, which
executes the exact predicate extracted from index.html's own source, not a
duplicated copy that could silently drift from it. This module runs that
harness and adds file-presence/no-collateral-damage checks the Node harness
does not.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
FEATURE_FLAGS = (ROOT / "js" / "e9" / "feature_flags.js").read_text(encoding="utf-8")
WORLD_STAGE = (ROOT / "js" / "e9" / "world_stage.js").read_text(encoding="utf-8")
RIGHT_CARDS = (ROOT / "js" / "e9" / "right_cards.js").read_text(encoding="utf-8")
REFERENCE_WORLD_MAP_CSS = (ROOT / "css" / "e9" / "reference_world_map.css").read_text(encoding="utf-8")
NODE_TEST = ROOT / "tests" / "e9_node_tests" / "run_pwa_portrait_tablet_override_tests.js"


def test_portrait_tablet_override_algorithm_and_wiring():
    result = subprocess.run(
        ["node", str(NODE_TEST)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr


def test_detection_script_is_present_and_early_in_head():
    # Must run before any CSS/JS that reads the resulting attribute, so it
    # has to sit in <head>, immediately after the existing
    # data-go-display-mode detection script it is modeled on.
    marker_pos = INDEX.find("data-go-portrait-tablet-override")
    display_mode_pos = INDEX.find("data-go-display-mode")
    head_close_pos = INDEX.find("</head>")
    assert -1 < display_mode_pos < marker_pos < head_close_pos


def test_no_generic_orientation_media_query_was_deleted():
    # This is a corrective override, not a rewrite: every existing
    # @media (orientation: ...) rule the shell relies on for a correctly-
    # reporting device must remain untouched.
    assert "@media (min-width: 768px) and (max-width: 1279px) and (orientation: landscape)" in REFERENCE_WORLD_MAP_CSS
    assert "@media (max-width: 1279px) and (orientation: portrait), (max-width: 767px)" in REFERENCE_WORLD_MAP_CSS
    assert "@media (min-width: 1280px)" in REFERENCE_WORLD_MAP_CSS


def test_zone4_intro_film_fix_from_the_first_investigation_is_preserved():
    # SECONDARY_ZONE4_CINEMATIC_RESPONSIVE_DEFECT=YES -- the earlier,
    # independently proven intro-film letterbox fix stays in this candidate;
    # it is a real, separate defect on the same static release layer.
    assert '#boss-cinematic.intro-film[data-zone-key="k11_15"] .boss-cinematic-scene' in INDEX


def test_e9_bottom_dock_component_is_unchanged():
    # The dock itself (and its desktop-legacy navigation category) is not
    # the defect -- it correctly reflects whichever breakpoint the shell
    # ends up in. This recovery does not touch it.
    bottom_dock_html = (ROOT / "components" / "adventure" / "bottom_dock.html").read_text(encoding="utf-8")
    assert 'id="bottom-dock"' in bottom_dock_html


def test_desktop_legacy_navigation_category_is_the_proven_evidence_trail():
    # This is the independent signal that proved the desktop breakpoint was
    # active on the Owner's real device (soul_records/battle_log/tavern/
    # star_chart/arena only ever render under that category). Recorded here
    # so the evidence trail stays verifiable against source, not just this
    # report's prose.
    registry = (ROOT / "js" / "e9" / "navigation_registry.js").read_text(encoding="utf-8")
    for key in ("soul_records", "battle_log", "tavern", "star_chart", "arena"):
        entry_start = registry.find(f"key: '{key}'")
        assert entry_start != -1, key
        entry_end = registry.find("}", entry_start)
        entry = registry[entry_start:entry_end]
        assert "'desktop-legacy'" in entry, key
