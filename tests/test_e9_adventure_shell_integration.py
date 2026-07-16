"""E9.1A2 — Legacy Adventure Shell Integration contract tests.

Most of this file is structural/source-level, matching the convention in
tests/test_e9_adventure_shell_foundation.py. The static-route section below
is a real Flask request contract test: tests/test_admin_anchor_sidebar_phase_a_plus.py
already demonstrated (via a stubbed-heavy-import fixture) that app.py can be
imported and exercised with test_client() without a live Postgres connection
-- the E9 static routes never touch the database, so the same
`_install_app_import_stubs` + `app_module` fixture pattern is reused here
rather than repeating the (superseded) claim that this requires Postgres.

Browser-based behavioral checks (component load/bind/i18n/render, failure
isolation, the 8-viewport RWD matrix, flag ON/OFF parity) are recorded
separately in docs/planning/e9_1a2_legacy_shell_integration.md.
"""
import re
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_PY = REPO_ROOT / "app.py"
SW_JS = REPO_ROOT / "sw.js"
INDEX_HTML = REPO_ROOT / "index.html"
I18N_JS = REPO_ROOT / "i18n.js"
JS_DIR = REPO_ROOT / "js" / "e9"
COMPONENTS_DIR = REPO_ROOT / "components" / "adventure"

OLD_SW_VERSION = "v183-e9-1d2-layout-rwd"
# NEW_SW_VERSION tracks whatever Sprint most recently bumped sw.js VERSION
# (superseded by each subsequent Sprint that also changes E9 JS bytes --
# see RELEASE-FIX-B, docs/planning/release_fix_b_e9_i18n_fallback.md).
# Bumped in 2026-07-15's intro narration browser-TTS contract fix (the
# shell version const is shared by both E9 and legacy static routes).
NEW_SW_VERSION = "v192-e9-admin-shell-activation"


def _read(path):
    assert path.is_file(), f"expected file to exist: {path}"
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

def test_legacy_skill_map_section_still_present():
    html = _read(INDEX_HTML)
    assert 'id="skill-map"' in html, "legacy #skill-map must not be deleted"


def test_e9_shell_root_and_slots_present_with_correct_attributes():
    html = _read(INDEX_HTML)
    assert 'id="e9-adventure-shell"' in html
    assert 'data-e9-shell' in html
    # the shell tag itself must carry both hidden and aria-hidden="true"
    shell_tag = re.search(r'<section[^>]*id="e9-adventure-shell"[^>]*>', html)
    assert shell_tag, "e9-adventure-shell root tag not found"
    tag_text = shell_tag.group(0)
    assert "hidden" in tag_text
    assert 'aria-hidden="true"' in tag_text

    for slot_id, slot_attr in [
        ("e9-top-hud-slot", "topHud"),
        ("e9-left-nav-slot", "leftNav"),
        ("e9-world-stage-slot", "worldStage"),
        ("e9-right-cards-slot", "rightCards"),
        ("e9-bottom-dock-slot", "bottomDock"),
    ]:
        assert f'id="{slot_id}"' in html
        assert f'data-e9-slot="{slot_attr}"' in html


def test_production_flags_still_default_false():
    flags_js = _read(JS_DIR / "feature_flags.js")
    for name in ["e9Shell", "e9TopHud", "e9LeftNav", "e9RightCards", "e9BottomDock", "e9WorldStage"]:
        assert re.search(rf"{name}\s*:\s*false", flags_js), f"{name} must default to false"


def test_flag_off_returns_before_any_fragment_mount_call():
    shell_js = _read(JS_DIR / "shell.js")
    # resolveRequestedShellMode()/applyShellState() may still run in flag-off
    # mode to enforce aria-hidden/inert/tabbability, but init() must still
    # return before the first mountSlot(...) call so a legacy-owned page
    # makes zero fragment requests.
    start = shell_js.find("function init() {")
    end = shell_js.find("\n\n  function startAdventureFromE9")
    assert start != -1 and end != -1, "could not locate shell.js init() body"
    init_body = shell_js[start:end]
    early_return_pos = init_body.find("if (requestedMode !== 'e9')")
    first_mount_pos = init_body.find("mountSlot(")
    assert early_return_pos != -1, "missing legacy-owned early return guard"
    assert first_mount_pos == -1 or early_return_pos < first_mount_pos, (
        "flag-off guard must come before any mountSlot() call"
    )


def test_critical_failure_recovers_to_legacy():
    shell_js = _read(JS_DIR / "shell.js")
    assert "function recoverToLegacy" in shell_js
    assert "applyShellState('legacy')" in shell_js
    assert "global.ensureLegacyAdventureMapReady" in shell_js
    # No page reload anywhere in the recovery path.
    assert "location.reload" not in shell_js

    world_stage_js = _read(JS_DIR / "world_stage.js")
    assert "window.E9.recoverToLegacy" in world_stage_js, (
        "world_stage.js (critical component) must trigger shell recovery "
        "on its own data-fetch failure, not just show a local error"
    )

    html = _read(INDEX_HTML)
    assert "function ensureLegacyAdventureMapReady(options = {})" in html
    assert "window.ensureLegacyAdventureMapReady = ensureLegacyAdventureMapReady" in html


def test_e9_cta_uses_existing_adventure_start_action():
    shell_js = _read(JS_DIR / "shell.js")
    assert "global.startAdventureStage(zoneKey)" in shell_js, (
        "the E9 CTA adapter must call the existing legacy startAdventureStage(), "
        "not reimplement zone-entry logic"
    )
    world_stage_js = _read(JS_DIR / "world_stage.js")
    assert "window.E9.startAdventureFromE9(zone.key)" in world_stage_js


def test_no_duplicate_init_or_double_binding_guard_present():
    for name in ["top_hud", "left_nav", "right_cards", "bottom_dock", "world_stage"]:
        js = _read(JS_DIR / f"{name}.js")
        assert "data-e9-inited" in js, f"{name}.js must guard against duplicate init"
    shell_js = _read(JS_DIR / "shell.js")
    assert "mountStarted" in shell_js, "shell.js must guard against duplicate fragment mounts"


# ---------------------------------------------------------------------------
# Static routes (source-level)
# ---------------------------------------------------------------------------

def test_abort_is_imported():
    app_py = _read(APP_PY)
    assert re.search(r"from flask import \([^)]*\babort\b", app_py), (
        "abort must be imported to reject invalid-extension requests"
    )


@pytest.mark.parametrize("route,ext", [
    ("/js/e9/<path:subpath>", ".js"),
    ("/css/e9/<path:subpath>", ".css"),
    ("/components/adventure/<path:subpath>", ".html"),
])
def test_static_route_exists_with_extension_allowlist(route, ext):
    app_py = _read(APP_PY)
    route_pattern = re.escape(f"@app.route('{route}')")
    match = re.search(route_pattern + r"\ndef (\w+)\((\w+)\):\n(.*?)\n\n", app_py, re.S)
    assert match, f"route {route} not found in app.py"
    fn_body = match.group(3)
    assert f"endswith('{ext}')" in fn_body, f"{route} must reject anything not ending in {ext}"
    assert "abort(404)" in fn_body


def test_static_routes_delegate_to_reviewed_helper_not_reimplemented():
    app_py = _read(APP_PY)
    for route in ["/js/e9/<path:subpath>", "/css/e9/<path:subpath>", "/components/adventure/<path:subpath>"]:
        route_pattern = re.escape(f"@app.route('{route}')")
        match = re.search(route_pattern + r"\ndef (\w+)\((\w+)\):\n(.*?)\n\n", app_py, re.S)
        assert match
        assert "_serve_live_static_or_baked_subpath(" in match.group(3), (
            f"{route} must reuse the already-reviewed traversal-safe helper, "
            f"not a new path-resolution implementation"
        )


# ---------------------------------------------------------------------------
# Static routes (live Flask request contract -- 200 / 404 / traversal reject)
# ---------------------------------------------------------------------------

def _install_app_import_stubs():
    """Same stub set as tests/test_admin_anchor_sidebar_phase_a_plus.py.
    The E9 static routes never touch the database, so app.py can be
    imported and driven with test_client() without a live Postgres DSN."""
    if 'katago_explain' not in sys.modules:
        module = types.ModuleType('katago_explain')
        module.KataGoExplainer = type('KataGoExplainer', (), {})
        sys.modules['katago_explain'] = module
    if 'explain_overrides' not in sys.modules:
        module = types.ModuleType('explain_overrides')
        module.get_override = lambda *args, **kwargs: None
        sys.modules['explain_overrides'] = module
    if 'grimoire_api' not in sys.modules:
        from flask import Blueprint
        module = types.ModuleType('grimoire_api')
        module.grimoire_bp = Blueprint('grimoire_stub', __name__)
        sys.modules['grimoire_api'] = module
    if 'question_taxonomy' not in sys.modules:
        module = types.ModuleType('question_taxonomy')
        module.get_taxonomy = lambda *args, **kwargs: {}
        sys.modules['question_taxonomy'] = module
    if 'monster_taxonomy' not in sys.modules:
        module = types.ModuleType('monster_taxonomy')
        module.get_monster_taxonomy = lambda *args, **kwargs: {}
        module.mark_encounters = lambda *args, **kwargs: None
        sys.modules['monster_taxonomy'] = module
    if 'chapter_i18n' not in sys.modules:
        module = types.ModuleType('chapter_i18n')
        module.localize_topic = lambda *args, **kwargs: ''
        module.localize_level = lambda *args, **kwargs: ''
        sys.modules['chapter_i18n'] = module
    if 'backend_i18n' not in sys.modules:
        module = types.ModuleType('backend_i18n')
        module.badge_en = lambda *args, **kwargs: ''
        module.skill_node_en = lambda *args, **kwargs: ''
        module.title_en = lambda *args, **kwargs: ''
        sys.modules['backend_i18n'] = module
    if 'sgf_engine' not in sys.modules:
        sys.modules['sgf_engine'] = types.ModuleType('sgf_engine')
    if 'sgf_engine.parser' not in sys.modules:
        sys.modules['sgf_engine.parser'] = types.ModuleType('sgf_engine.parser')
    if 'sgf_engine.parser.sgf_parser' not in sys.modules:
        module = types.ModuleType('sgf_engine.parser.sgf_parser')
        module.parse_sgf = lambda *args, **kwargs: None
        sys.modules['sgf_engine.parser.sgf_parser'] = module


@pytest.fixture(scope='module')
def app_module():
    _install_app_import_stubs()
    import app as app_module
    return app_module


@pytest.fixture()
def client(app_module):
    return app_module.app.test_client()


@pytest.mark.parametrize("path", [
    "/js/e9/feature_flags.js",
    "/js/e9/shell.js",
    "/css/e9/shell.css",
    "/components/adventure/top_hud.html",
])
def test_e9_static_route_returns_200_for_real_file(client, path):
    response = client.get(path)
    assert response.status_code == 200


@pytest.mark.parametrize("path", [
    "/js/e9/feature_flags.css",   # real file, wrong extension for this route
    "/js/e9/does_not_exist.js",   # right extension, file absent
    "/css/e9/shell.js",           # real file, wrong extension for this route
    "/components/adventure/top_hud.js",  # right dir, wrong extension
])
def test_e9_static_route_returns_404_for_invalid_extension_or_missing_file(client, path):
    response = client.get(path)
    assert response.status_code == 404


@pytest.mark.parametrize("path", [
    "/js/e9/../app.py",
    "/js/e9/../../app.py",
    "/js/e9/%2e%2e/app.py",
    "/css/e9/../../secret_key.txt",
    "/components/adventure/../../app.py",
])
def test_e9_static_route_rejects_traversal(client, path):
    response = client.get(path)
    # Never 200, and never a redirect that would land on the traversal
    # target -- either Werkzeug's own path normalization 404s before the
    # view even runs, or the view runs and _resolve_live_static_path /
    # send_from_directory reject it. Both are acceptable; a 200 is not.
    assert response.status_code != 200
    assert response.status_code in (301, 302, 404)
    if response.status_code in (301, 302):
        location = response.headers.get('Location', '')
        assert 'app.py' not in location and 'secret_key' not in location


# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------

E9_I18N_KEYS = [
    "e9.shell.critical_error", "e9.top_hud.aria_label", "e9.top_hud.loading", "e9.top_hud.error",
    "e9.top_hud.level_label", "e9.left_nav.aria_label", "e9.left_nav.adventure", "e9.left_nav.hero",
    "e9.left_nav.equipment", "e9.left_nav.backpack", "e9.left_nav.missions", "e9.left_nav.shop",
    "e9.right_cards.aria_label", "e9.right_cards.daily_challenge_title", "e9.right_cards.boss_progress_title",
    "e9.right_cards.srs_due_title", "e9.right_cards.weakness_title", "e9.right_cards.loading",
    "e9.right_cards.empty", "e9.right_cards.error", "e9.bottom_dock.aria_label", "e9.bottom_dock.leaderboard",
    "e9.bottom_dock.achievements", "e9.bottom_dock.records", "e9.bottom_dock.friends",
    "e9.world_stage.aria_label", "e9.world_stage.loading", "e9.world_stage.error", "e9.world_stage.note",
]


@pytest.mark.parametrize("key", E9_I18N_KEYS)
def test_e9_key_exists_in_both_languages(key):
    i18n_js = _read(I18N_JS)
    match = re.search(re.escape(f"'{key}':") + r"\s*\{([^}]*)\}", i18n_js)
    assert match, f"missing dict entry for {key}"
    entry = match.group(1)
    assert "en:" in entry, f"{key} missing en translation"
    assert "zh:" in entry, f"{key} missing zh translation"


def test_no_fragment_has_hardcoded_interactive_labels():
    # Every nav/dock/card interactive element must carry a data-i18n
    # attribute rather than relying on its literal innerHTML text alone.
    checks = {
        "left_nav.html": ["data-i18n=\"e9.left_nav.hero\""],
        "bottom_dock.html": ["data-i18n=\"e9.bottom_dock.leaderboard\""],
        "right_cards.html": ["data-i18n=\"e9.right_cards.daily_challenge_title\""],
        "top_hud.html": ["data-i18n=\"e9.top_hud.level_label\""],
    }
    for filename, must_contain in checks.items():
        html = _read(COMPONENTS_DIR / filename)
        for marker in must_contain:
            assert marker in html, f"{filename} missing {marker}"


def test_loader_applies_i18n_before_dispatching_component_loaded():
    loader_js = _read(JS_DIR / "component_loader.js")
    inject_pos = loader_js.find("root.innerHTML = html;")
    apply_pos = loader_js.find("global.I18n.apply();")
    dispatch_pos = loader_js.find("dispatchEvent(new CustomEvent('e9:component-loaded'")
    assert inject_pos != -1 and apply_pos != -1 and dispatch_pos != -1
    assert inject_pos < apply_pos < dispatch_pos, (
        "order must be: inject -> apply i18n -> dispatch component-loaded"
    )


def test_no_second_translation_dictionary_introduced():
    for f in JS_DIR.glob("*.js"):
        js = _read(f)
        assert not re.search(r"\{\s*en\s*:\s*['\"]", js), (
            f"{f.name} appears to define its own {{en:...}} translation table — "
            f"reuse window.I18n instead"
        )
        assert not re.search(r"\bconst\s+dict\s*=", js), f"{f.name} must not define a second dict"


def test_loading_and_empty_error_states_are_translatable():
    top_hud_html = _read(COMPONENTS_DIR / "top_hud.html")
    assert 'data-i18n="e9.top_hud.loading"' in top_hud_html
    right_cards_html = _read(COMPONENTS_DIR / "right_cards.html")
    assert right_cards_html.count('data-i18n="e9.right_cards.loading"') == 4  # one per card
    top_hud_js = _read(JS_DIR / "top_hud.js")
    assert "e9.top_hud.error" in top_hud_js
    right_cards_js = _read(JS_DIR / "right_cards.js")
    assert "e9.right_cards.empty" in right_cards_js
    assert "e9.right_cards.error" in right_cards_js


def test_reuses_existing_window_onlangchange_mechanism_not_a_new_one():
    # No new setLang/onLangChange/localStorage-language-key implementation
    # anywhere in js/e9 -- the existing window.I18n.setLang()/apply()/
    # onLangChange contract (defined in i18n.js) is reused as-is.
    for f in JS_DIR.glob("*.js"):
        js = _read(f)
        assert "function setLang" not in js
        assert "onLangChange =" not in js
        assert "cgo_lang" not in js


# ---------------------------------------------------------------------------
# Service Worker
# ---------------------------------------------------------------------------

def test_sw_version_bumped():
    sw_js = _read(SW_JS)
    assert OLD_SW_VERSION not in sw_js, "sw.js VERSION must be bumped, not left at the pre-E9.1A2 value"
    assert NEW_SW_VERSION in sw_js


def test_sw_cache_strategy_functions_unchanged():
    sw_js = _read(SW_JS)
    # E9 JS/CSS is covered by the existing generic .js/.css cache-first
    # branch -- no special-casing needed, and none should be added (that
    # would be a SW refactor, which is out of scope this sprint).
    assert "url.pathname.endsWith('.js') ||" in sw_js
    assert "url.pathname.endsWith('.css')" in sw_js
    assert "function cacheFirst" in sw_js
    assert "function networkFirst" in sw_js


def test_sw_diff_is_version_line_only():
    # Regression guard: this sprint must not refactor sw.js beyond the
    # VERSION bump. If this ever fails, someone touched more than the
    # version line and it needs explicit review.
    sw_js = _read(SW_JS)
    assert sw_js.count("const VERSION") == 1
    assert "self.addEventListener('fetch'" in sw_js
    assert "self.addEventListener('install'" in sw_js
    assert "self.addEventListener('activate'" in sw_js


# ---------------------------------------------------------------------------
# Data: no fabricated resources
# ---------------------------------------------------------------------------

def test_top_hud_has_no_stars_hp_sp():
    top_hud_html = _read(COMPONENTS_DIR / "top_hud.html")
    for forbidden_id in ["top-hud-stars", "top-hud-hp", "top-hud-sp"]:
        assert forbidden_id not in top_hud_html
    top_hud_js = _read(JS_DIR / "top_hud.js")
    for forbidden_endpoint in ["/api/user/hp", "/api/user/sp", "/api/user/stars"]:
        assert forbidden_endpoint not in top_hud_js


def test_top_hud_coins_uses_real_endpoint_not_a_literal_number():
    # E9.1B: top_hud.js delegates to js/e9/adapters/player_state.js (single
    # source of truth) instead of parsing /api/user/coins inline -- the real
    # endpoint and real field access now live in the adapter.
    top_hud_js = _read(JS_DIR / "top_hud.js")
    assert "PlayerState" in top_hud_js
    assert re.search(r"data\.coins", top_hud_js)
    adapter_js = _read(JS_DIR / "adapters" / "player_state.js")
    assert "/api/user/coins" in adapter_js
    assert re.search(r"raw\.coins", adapter_js)


def test_no_guild_pass_card_or_key_anywhere():
    right_cards_html = _read(COMPONENTS_DIR / "right_cards.html")
    assert 'data-e9-card="guild_pass"' not in right_cards_html
    i18n_js = _read(I18N_JS)
    assert "guild_pass" not in i18n_js.lower().replace(" ", "")
    # Strip HTML comments before checking for the phrase itself -- an
    # explanatory dev comment noting the *absence* of a Guild Pass card
    # (as this fragment's own header comment does) is not the same as
    # actually shipping one, and must not fail this guard.
    visible_markup = re.sub(r"<!--.*?-->", "", right_cards_html, flags=re.S)
    for name_variant in ["Guild Pass", "公會通行證", "guildPass"]:
        assert name_variant not in visible_markup


def test_no_misleading_zero_fallback_values():
    # A hardcoded literal "0 HP" / "0 SP" / "0 ★" string would be more
    # misleading than an honest empty/error state -- assert none exist.
    for f in list(JS_DIR.glob("*.js")) + list(COMPONENTS_DIR.glob("*.html")):
        text = _read(f)
        assert "0 HP" not in text
        assert "0 SP" not in text
        assert "0/0 HP" not in text


def test_boss_progress_and_srs_and_weakness_use_real_endpoints():
    right_cards_js = _read(JS_DIR / "right_cards.js")
    assert "/api/adventure/bootstrap" in right_cards_js
    assert "/api/srs/due" in right_cards_js
    assert "/api/mistakes/stats" in right_cards_js
    assert "/api/daily-challenge/today" in right_cards_js


# ---------------------------------------------------------------------------
# i18n stale-rescan regression (E9.1A2 Rev2 — live-verified during browser
# verification: I18n.apply() is a global rescan of every [data-i18n] element.
# top_hud.js / right_cards.js / world_stage.js each dynamically overwrite an
# element that starts with a static data-i18n loading placeholder. Without
# removing that attribute once real content is set, ANY later, unrelated
# I18n.apply() call elsewhere on the page (site-nav.js, a language switch)
# silently reverts the element back to "Loading…" forever, since
# data-e9-inited already blocks re-fetching.
# ---------------------------------------------------------------------------

def test_top_hud_removes_data_i18n_after_setting_dynamic_text():
    js = _read(JS_DIR / "top_hud.js")
    assert "removeAttribute('data-i18n')" in js


def test_right_cards_removes_data_i18n_after_setting_dynamic_text():
    js = _read(JS_DIR / "right_cards.js")
    assert "removeAttribute('data-i18n')" in js


def test_world_stage_removes_data_i18n_after_setting_dynamic_text():
    js = _read(JS_DIR / "world_stage.js")
    assert "removeAttribute('data-i18n')" in js
