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


# ---------------------------------------------------------------------------
# 6b. E9 Phase 1: component_loader.js timeout hardening (closes the confirmed
#     infinite-spinner gap for a permanently-pending fragment fetch).
# ---------------------------------------------------------------------------

def test_loader_has_bounded_overridable_timeout():
    loader_js = _read(JS_DIR / "component_loader.js")
    assert "AbortController" in loader_js
    assert "DEFAULT_COMPONENT_FETCH_TIMEOUT_MS" in loader_js
    assert "global.E9.COMPONENT_FETCH_TIMEOUT_MS" in loader_js, (
        "timeout must be overridable via window.E9.COMPONENT_FETCH_TIMEOUT_MS "
        "so tests are not forced to wait out the real default"
    )
    assert "signal: controller.signal" in loader_js


def test_loader_timeout_reuses_shell_registercleanup_not_a_parallel_mechanism():
    loader_js = _read(JS_DIR / "component_loader.js")
    assert "global.E9.registerCleanup" in loader_js, (
        "abort-on-destroy must reuse shell.js's existing generation-scoped "
        "registerCleanup/lifecycleCleanups mechanism, not a second cleanup path"
    )


def test_loader_does_not_introduce_a_separate_timedout_flag():
    loader_js = _read(JS_DIR / "component_loader.js")
    # Check for an actual variable declaration, not just the word appearing in
    # the explanatory comment about why one isn't needed.
    assert not re.search(r"\b(?:var|let|const)\s+timedOut\b", loader_js), (
        "the current()-plus-AbortError reasoning (documented inline) makes a "
        "separate timedOut boolean unnecessary; its presence would mean the "
        "two-abort-call-site invariant was broken without updating this test"
    )


def test_loader_timeout_and_destroy_are_the_only_two_abort_call_sites():
    loader_js = _read(JS_DIR / "component_loader.js")
    assert loader_js.count("controller.abort()") == 2, (
        "exactly two abort() call sites are required for the catch handler's "
        "current()+AbortError reasoning to hold -- a third call site must "
        "come with a re-examination of that reasoning, not silently appear"
    )


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


def test_index_html_shell_wiring_state_is_tracked():
    # E9.1A1 asserted index.html did NOT yet reference the shell (that was
    # E9.1A2's job). E9.1A2 has now landed that wiring — this test's job
    # going forward is just to confirm the wiring is real and present, not
    # to re-assert the old "not yet" boundary, which is obsolete by design
    # now that E9.1A2 is complete. See test_e9_adventure_shell_integration.py
    # for the full E9.1A2 contract (flag default, slot ids, legacy fallback).
    index_html = _read(REPO_ROOT / "index.html")
    assert "e9-adventure-shell" in index_html
    assert "js/e9/shell.js" in index_html


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


# ---------------------------------------------------------------------------
# 10. ARIA: every fragment root declares a role/label so the shell is
#    navigable by assistive tech even while still placeholder-only.
# ---------------------------------------------------------------------------

FRAGMENT_ARIA_MARKERS = {
    "top_hud.html": ("role=\"region\"", "aria-label="),
    "left_nav.html": ("aria-label=",),
    "right_cards.html": ("aria-label=",),
    "bottom_dock.html": ("role=\"toolbar\"", "aria-label="),
    "world_stage.html": ("aria-label=",),
}


@pytest.mark.parametrize("filename,markers", sorted(FRAGMENT_ARIA_MARKERS.items()))
def test_fragment_declares_aria_role_or_label(filename, markers):
    html = _read(COMPONENTS_DIR / filename)
    for marker in markers:
        assert marker in html, f"{filename} must declare {marker} for assistive tech"


# ---------------------------------------------------------------------------
# 11. Fragment isolation: the loader's failure path must only ever touch the
#    root element passed to it -- never reach into siblings or the document,
#    so one component's 404 cannot corrupt another component's DOM.
# ---------------------------------------------------------------------------

def test_loader_failure_path_only_touches_its_own_root():
    loader_js = _read(JS_DIR / "component_loader.js")
    # The catch block must operate on `root` only (root.innerHTML / root.setAttribute),
    # never on document.* or a different element reference.
    catch_block_match = re.search(r"\.catch\(function \(err\) \{(.*?)\}\);", loader_js, re.S)
    assert catch_block_match, "component_loader.js must have a .catch() fallback block"
    catch_body = catch_block_match.group(1)
    assert "root.innerHTML" in catch_body
    assert "root.setAttribute" in catch_body
    assert "document.querySelectorAll" not in catch_body
    assert "document.getElementById" not in catch_body
