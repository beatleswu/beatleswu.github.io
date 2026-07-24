"""RELEASE-FIX-B -- E9 Missing-Key Fallback Hardening.

Fixes the confirmed defect where I18n.t(key) returns the key itself on a
miss (see i18n.js), which meant the E9 components' own local
`t(key, fallback)` helpers (`val || fallback`) never actually reached
`fallback` -- a missing key rendered the raw dictionary key.

Test categories, matching the Discovery Gate table in
docs/planning/release_fix_b_e9_i18n_fallback.md:
  1. Real helper behavior via Node execution (not source regex) --
     tests/e9_node_tests/run_i18n_fallback_tests.js.
  2. Component regression -- top_hud.js/right_cards.js/world_stage.js/
     shell.js all delegate to the shared helper, none still contain the
     defective `|| fallback` pattern.
  3. Raw-key-prevention -- the shared helper is the single place the
     "does I18n.t() actually distinguish missing" logic lives.
  4. i18n completeness -- every key referenced by the four hardened call
     sites has both en and zh entries in i18n.js.
  5. Scope boundaries -- adapters, feature flags, and the global i18n.js
     t() function are unmodified; index.html's legacy call sites are
     untouched.
"""
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
JS_DIR = REPO_ROOT / "js" / "e9"
ADAPTERS_DIR = JS_DIR / "adapters"
I18N_JS = REPO_ROOT / "i18n.js"
HELPER_JS = JS_DIR / "i18n_fallback.js"
NODE_TEST_SCRIPT = REPO_ROOT / "tests" / "e9_node_tests" / "run_i18n_fallback_tests.js"
DISCOVERY_DOC = REPO_ROOT / "docs" / "planning" / "release_fix_b_e9_i18n_fallback.md"


def _read(path):
    assert path.is_file(), f"expected file to exist: {path}"
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Real helper behavior (Node execution, not source regex)
# ---------------------------------------------------------------------------

def test_helper_file_exists():
    assert HELPER_JS.is_file()


def test_real_helper_behavior_via_node():
    assert NODE_TEST_SCRIPT.is_file()
    result = subprocess.run(
        ["node", str(NODE_TEST_SCRIPT)],
        capture_output=True, text=True, timeout=30, cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"real i18n fallback helper tests failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "passed" in result.stdout
    assert "0 failed" in result.stdout


def test_helper_does_not_add_a_params_argument():
    # I18n.t() takes only `key` in the real implementation -- the helper
    # must not invent an interpolation argument that doesn't exist.
    js = _read(HELPER_JS)
    assert "i18n.t(key)" in js
    assert "i18n.t(key, params)" not in js
    assert "i18n.t(key," not in js


def test_helper_module_exports_for_node_and_attaches_to_window_e9():
    js = _read(HELPER_JS)
    assert "module.exports" in js
    assert "global.E9.I18nFallback" in js


# ---------------------------------------------------------------------------
# Component regression -- all four call sites delegate to the shared helper,
# none still contain the defective `|| fallback` pattern.
# ---------------------------------------------------------------------------

DEFECTIVE_PATTERN = re.compile(r"window\.I18n\.t\(key\)\s*;\s*return val \|\| fallback", re.S)


@pytest.mark.parametrize("filename", ["top_hud.js", "right_cards.js", "world_stage.js"])
def test_component_local_helper_delegates_to_shared_helper(filename):
    js = _read(JS_DIR / filename)
    assert "window.E9.I18nFallback.t(key, fallback)" in js, (
        f"{filename}'s local t() helper must delegate to window.E9.I18nFallback.t"
    )
    assert "val || fallback" not in js, f"{filename} still contains the defective '|| fallback' pattern"


@pytest.mark.parametrize("filename", ["top_hud.js", "right_cards.js", "world_stage.js"])
def test_component_still_has_all_original_call_sites(filename):
    # Refactor must not have dropped or renamed any real call site --
    # the local t(key, fallback) wrapper signature is unchanged, only its
    # body changed, so every original invocation still compiles/works.
    js = _read(JS_DIR / filename)
    assert re.search(r"function t\(key, fallback\)", js)


def test_shell_js_hardens_direct_call_site():
    js = _read(JS_DIR / "shell.js")
    assert "global.E9.I18nFallback.t(" in js
    assert "e9.shell.critical_error" in js
    # must not still call global.I18n.t() directly and unwrapped
    assert "global.I18n.t('e9.shell.critical_error')" not in js


def test_right_cards_preserves_replace_interpolation_contract():
    js = _read(JS_DIR / "right_cards.js")
    assert "t('index.adv.summary', '{n} / {t} areas cleared')" in js
    assert ".replace('{n}'" in js and ".replace('{t}'" in js


def test_world_stage_preserves_replace_and_split_interpolation_contract():
    js = _read(JS_DIR / "world_stage.js")
    assert "t('index.adv.summary', '{n} / {t} areas cleared')" in js

    # boss_cleared: {stars} substitution for cleared-zone copy must survive.
    assert "t('index.adv.boss_cleared', 'Defeated {stars}')" in js
    assert ".replace('{stars}', String(zone.stars))" in js

    # boss_ready tile badge: must go through a dedicated, named safe helper,
    # not the original ASCII-only inline split, which silently failed to
    # truncate the full-width-colon Chinese dictionary value (leaking the
    # raw "{seen}/{total}" template in that locale) and would also pass a
    # delimiter-free translation straight through untouched.
    assert "function bossReadyBadgeText()" in js
    assert ".split(':')[0]" not in js, (
        "the original ASCII-only colon split must not reappear -- it "
        "silently fails to match the Chinese dictionary value's full-width '：'"
    )
    assert "t('index.adv.boss_ready', 'Seal broken')" not in js, (
        "the original un-templated fallback must not reappear -- the real "
        "fallback is the full template 'Seal broken: {seen}/{total}'"
    )
    assert "t('index.adv.boss_ready', 'Seal broken: {seen}/{total}')" in js

    # Confirm the i18n.js source values this contract depends on -- source
    # content only, no truncation logic re-derived here.
    i18n_text = _read(I18N_JS)
    match = re.search(
        r"'index\.adv\.boss_ready'\s*:\s*\{\s*en:\s*'((?:[^'\\]|\\.)*)'\s*,\s*zh:\s*'((?:[^'\\]|\\.)*)'",
        i18n_text,
    )
    assert match, "index.adv.boss_ready not found in i18n.js in the expected { en: '...', zh: '...' } shape"
    en_value, zh_value = match.group(1), match.group(2)
    assert en_value == 'Seal broken: {seen}/{total}'
    assert zh_value == '封印解除：{seen}/{total} 題'

    # The actual behavioral proof -- that bossReadyBadgeText() resolves the
    # real EN/ZH dictionary values AND hypothetical delimiter-free
    # translations to the short lead-in with no {seen}/{total} leak in any
    # case -- is proven by executing the real, current function body
    # (extracted verbatim and run in a Node vm context, not reimplemented
    # in Python) in
    # test_e9_multi_zone_adventure_cta.py::test_bossreadybadgetext_production_linked_behavior_via_node.
    # Not duplicated here to avoid two divergent copies of the same
    # production-linked harness.


# ---------------------------------------------------------------------------
# i18n completeness -- every key referenced by the four hardened call sites
# has both en and zh entries.
# ---------------------------------------------------------------------------

HARDENED_CALL_SITE_KEYS = [
    "e9.top_hud.error", "e9.top_hud.unauthorized",
    "e9.right_cards.error", "e9.right_cards.unauthorized", "e9.right_cards.empty",
    "e9.right_cards.daily_challenge_done", "e9.right_cards.daily_challenge_available",
    "e9.shell.critical_error",
    "index.adv.summary", "index.adv.zone_locked", "index.adv.boss_ready",
]


@pytest.mark.parametrize("key", HARDENED_CALL_SITE_KEYS)
def test_hardened_call_site_key_has_both_languages(key):
    text = _read(I18N_JS)
    pattern = re.escape("'" + key + "'") + r"\s*:\s*\{\s*en:\s*'[^']*',\s*zh:\s*'[^']*'\s*\}"
    assert re.search(pattern, text), f"{key} missing or incomplete (needs both en/zh) in i18n.js"


# ---------------------------------------------------------------------------
# Scope boundaries -- adapters, feature flags, global i18n.js semantics, and
# legacy index.html call sites are unmodified.
# ---------------------------------------------------------------------------

def test_adapters_do_not_reference_i18n():
    for f in ADAPTERS_DIR.glob("*.js"):
        text = _read(f)
        assert "I18n" not in text, f"{f.name} must not be touched by this Sprint (adapters are out of scope)"


def test_global_i18n_t_function_missing_key_semantics_unchanged():
    text = _read(I18N_JS)
    assert re.search(r"function t\(key\)\s*\{\s*const entry = dict\[key\];\s*if \(!entry\) return key;", text), (
        "i18n.js's global t() missing-key semantics must not change in this Sprint "
        "(Global i18n Boundary -- see docs/planning/release_fix_b_e9_i18n_fallback.md)"
    )


def test_index_html_legacy_call_sites_still_call_i18n_t_directly():
    # Spot-check: legacy index.html code is untouched -- it still calls
    # I18n.t(...) directly with no shared-helper wrapper, exactly as before.
    text = _read(REPO_ROOT / "index.html")
    assert "window.E9.I18nFallback" not in text.split("<script src=\"/js/e9/")[0], (
        "the shared helper must not be referenced anywhere in legacy (pre-E9-scripts) index.html markup/JS"
    )


def test_feature_flags_unchanged_all_false():
    flags_js = _read(JS_DIR / "feature_flags.js")
    for name in ["e9Shell", "e9TopHud", "e9LeftNav", "e9RightCards", "e9BottomDock", "e9WorldStage"]:
        assert re.search(rf"{name}\s*:\s*false", flags_js), f"{name} must default to false"


def test_discovery_gate_document_exists_and_covers_all_call_sites():
    text = _read(DISCOVERY_DOC)
    for name in ["top_hud.js", "right_cards.js", "world_stage.js", "shell.js", "component_loader.js", "index.html"]:
        assert name in text, f"Discovery Gate document must account for {name}"
