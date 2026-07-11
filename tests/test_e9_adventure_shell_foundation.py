"""E9.1A1 — Adventure Shell component foundation contract tests.

These are structural/source-level contract tests, not behavioral browser
tests (this repo has no JS test framework and E9.1A1 deliberately does not
introduce one — see docs/planning/e9_1a1_component_foundation.md). Real
runtime behavior (fragment loads, fail-safe fallback, no duplicate event
binding, i18n, screenshots) is verified via the manual browser checklist
in that same doc.

Scope guard: E9.1A1 must not touch index.html or app.py. Several tests
below assert that boundary explicitly so a future change to this PR (or a
rebase) cannot silently cross it.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENTS_DIR = REPO_ROOT / "components" / "adventure"
JS_DIR = REPO_ROOT / "js" / "e9"
CSS_DIR = REPO_ROOT / "css" / "e9"

FRAGMENTS = {
    "top_hud.html": "top-hud",
    "left_nav.html": "left-nav",
    "right_cards.html": "right-cards",
    "bottom_dock.html": "bottom-dock",
    "world_stage.html": "adventure-stage",
}

SLOT_TO_FRAGMENT = {
    "#e9-top-hud-slot": "/components/adventure/top_hud.html",
    "#e9-left-nav-slot": "/components/adventure/left_nav.html",
    "#e9-world-stage-slot": "/components/adventure/world_stage.html",
    "#e9-right-cards-slot": "/components/adventure/right_cards.html",
    "#e9-bottom-dock-slot": "/components/adventure/bottom_dock.html",
}

PRODUCTION_FLAG_NAMES = [
    "e9Shell", "e9TopHud", "e9LeftNav", "e9RightCards", "e9BottomDock", "e9WorldStage",
]


def _read(path):
    assert path.is_file(), f"expected file to exist: {path}"
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. All five fragments exist
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename", sorted(FRAGMENTS.keys()))
def test_fragment_file_exists(filename):
    assert (COMPONENTS_DIR / filename).is_file()


# ---------------------------------------------------------------------------
# 2. Stable root IDs are present, unique, and match Rule #6 naming
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename,expected_id", sorted(FRAGMENTS.items()))
def test_fragment_has_stable_root_id(filename, expected_id):
    html = _read(COMPONENTS_DIR / filename)
    assert f'id="{expected_id}"' in html, (
        f"{filename} must declare stable root id=\"{expected_id}\" (Rule #6)"
    )


def test_fragment_root_ids_are_globally_unique():
    ids = list(FRAGMENTS.values())
    assert len(ids) == len(set(ids)), "fragment root ids must be unique across all components"


# ---------------------------------------------------------------------------
# 3. Slot -> fragment mapping in shell.js is complete and correct
# ---------------------------------------------------------------------------

def test_shell_js_slot_mapping_matches_contract():
    shell_js = _read(JS_DIR / "shell.js")
    for selector, src in SLOT_TO_FRAGMENT.items():
        assert f"selector: '{selector}'" in shell_js, f"shell.js missing slot selector {selector}"
        assert f"src: '{src}'" in shell_js, f"shell.js missing fragment src {src} for {selector}"


def test_shell_js_references_exactly_five_slots():
    shell_js = _read(JS_DIR / "shell.js")
    # crude but effective: count "selector:" occurrences in the SLOTS array
    assert shell_js.count("selector:") == 5


# ---------------------------------------------------------------------------
# 4. Feature flag defaults are all false in production
# ---------------------------------------------------------------------------

def test_production_flags_default_to_false():
    flags_js = _read(JS_DIR / "feature_flags.js")
    for name in PRODUCTION_FLAG_NAMES:
        pattern = re.compile(rf"{name}\s*:\s*false")
        assert pattern.search(flags_js), (
            f"PRODUCTION_FLAGS.{name} must default to false in E9.1A1/E9.1A2 "
            f"(Stage C is the only stage allowed to flip this to true)"
        )


# ---------------------------------------------------------------------------
# 5. Query-param overrides cannot take effect without a debug-environment
#    check AND an explicit opt-in — a bare query param must never flip a
#    flag in production.
# ---------------------------------------------------------------------------

def test_query_override_requires_debug_environment_and_explicit_opt_in():
    flags_js = _read(JS_DIR / "feature_flags.js")
    assert "isDebugEnvironment" in flags_js, (
        "feature_flags.js must gate query overrides behind a debug-environment check"
    )
    assert "E9_DEBUG" in flags_js, (
        "feature_flags.js must require an explicit ?E9_DEBUG=1 opt-in"
    )
    # Both conditions must be checked together before any override is applied.
    guard_pattern = re.compile(
        r"if\s*\(\s*!debugOptIn\s*\|\|\s*!isDebugEnvironment\(\)\s*\)\s*\{\s*return base;"
    )
    assert guard_pattern.search(flags_js), (
        "resolveFlags() must bail out to production defaults unless BOTH "
        "debugOptIn and isDebugEnvironment() are true"
    )


# ---------------------------------------------------------------------------
# 6. Loader is fail-safe: checks response.ok, catches errors, renders a
#    fallback, and never lets an exception escape uncaught.
# ---------------------------------------------------------------------------

def test_loader_checks_response_ok():
    loader_js = _read(JS_DIR / "component_loader.js")
    assert "res.ok" in loader_js


def test_loader_has_catch_and_fallback():
    loader_js = _read(JS_DIR / "component_loader.js")
    assert ".catch(" in loader_js
    assert "fallbackHtml" in loader_js
    assert "data-e9-loaded', 'error'" in loader_js


def test_loader_is_idempotent_per_root():
    loader_js = _read(JS_DIR / "component_loader.js")
    assert "data-e9-loaded" in loader_js
    assert "Already settled" in loader_js or "already" in loader_js.lower()


def test_shell_init_is_wrapped_in_try_catch():
    shell_js = _read(JS_DIR / "shell.js")
    assert "try {" in shell_js and "} catch (err)" in shell_js, (
        "shell.js init() must never let an exception escape as an uncaught pageerror"
    )


# ---------------------------------------------------------------------------
# 7. Fragment URLs are versioned
# ---------------------------------------------------------------------------

def test_fragment_urls_are_versioned():
    loader_js = _read(JS_DIR / "component_loader.js")
    assert "versionedUrl" in loader_js
    assert "v=" in loader_js


def test_asset_version_constant_exists_and_is_nonempty():
    flags_js = _read(JS_DIR / "feature_flags.js")
    match = re.search(r"ASSET_VERSION\s*=\s*'([^']+)'", flags_js)
    assert match, "feature_flags.js must define a non-empty ASSET_VERSION constant"
    assert match.group(1).strip() != ""


def test_asset_version_sw_coupling_is_documented():
    flags_js = _read(JS_DIR / "feature_flags.js")
    assert "sw.js" in flags_js and "VERSION" in flags_js, (
        "feature_flags.js must document the required sw.js VERSION bump "
        "whenever E9 JS/CSS changes ship, since sw.js caches *.js/*.css "
        "cache-first"
    )


# ---------------------------------------------------------------------------
# 8. E9.1A1 scope guard: index.html / app.py must remain untouched by this
#    sprint. This test intentionally locks in the "not wired yet" boundary
#    and must be updated as part of E9.1A2, not silently broken by it.
# ---------------------------------------------------------------------------

def test_legacy_adventure_map_section_is_untouched():
    index_html = _read(REPO_ROOT / "index.html")
    assert 'id="skill-map"' in index_html, (
        "legacy #skill-map section must still exist untouched in E9.1A1"
    )


def test_index_html_does_not_yet_reference_e9_shell():
    index_html = _read(REPO_ROOT / "index.html")
    assert "e9-adventure-shell" not in index_html, (
        "E9.1A1 must not wire the shell into index.html — that is E9.1A2's job"
    )
    assert "js/e9/shell.js" not in index_html


# ---------------------------------------------------------------------------
# 9. CSS is preloaded independent of fragment fetch (all 6 stylesheets exist)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename", [
    "shell.css", "top_hud.css", "navigation.css", "cards.css", "world_stage.css", "rwd.css",
])
def test_css_module_exists(filename):
    assert (CSS_DIR / filename).is_file()


def test_shell_css_defines_skeleton_loading_state():
    shell_css = _read(CSS_DIR / "shell.css")
    assert "e9-component-skeleton" in shell_css
