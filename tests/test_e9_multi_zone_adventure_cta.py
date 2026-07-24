"""E9 Multi-Zone Progression Integration — regression tests for
`fix: wire E9 multi-zone adventure start CTA and seen/total display`.

Root cause (see GO_IMPLEMENT_E9_MULTI_ZONE_MINIMAL_FIX investigation):
the Beginner Village tutorial panel was the ONLY zone-detail view ever
wired to `window.E9.startAdventureFromE9(zone.key)`. Every other zone's
generic `#e9-world-stage-details` panel had a label/summary but no CTA at
all, even though `startAdventureFromE9()` itself is already fully
zone-generic (a URL handoff to the existing legacy Adventure flow).
Separately, `index.adv.boss_ready` (a `{seen}/{total}` template) was
rendered via `t(...)` with no substitution, leaking the raw placeholder.

`world_stage.js` has no browser/DOM test harness in this repo (matching
the existing convention in test_e9_stage_c1_1_integration.py /
test_e9_adventure_shell_integration.py) -- these are precise source-level
structural assertions on the real files, not source-level regex on a
mock. `normalizeZone()`'s seen/total behavior is covered with full
execution fidelity by the new Node tests in
tests/e9_node_tests/run_adapter_tests.js, not duplicated here.
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORLD_STAGE_PATH = ROOT / "js/e9/world_stage.js"
WORLD_STAGE = WORLD_STAGE_PATH.read_text(encoding="utf-8")
WORLD_STAGE_HTML = (ROOT / "components/adventure/world_stage.html").read_text(encoding="utf-8")
WORLD_STAGE_CSS = (ROOT / "css/e9/world_stage.css").read_text(encoding="utf-8")
SHELL_JS = (ROOT / "js/e9/shell.js").read_text(encoding="utf-8")
ADAPTER_JS = (ROOT / "js/e9/adapters/adventure_state.js").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")

NEW_SW_VERSION = "v206-e9-i18n-placeholder-fix"
PREVIOUS_SW_VERSION = "v205-e9-zone-cta-visual-parity"


def _render_selected_zone_body():
    start = WORLD_STAGE.index("function renderSelectedZone(")
    end = WORLD_STAGE.index("\n  function renderZones(", start)
    return WORLD_STAGE[start:end]


# ---------------------------------------------------------------------
# 1. normalizeZone seen/total -- covered with execution fidelity by
#    tests/e9_node_tests/run_adapter_tests.js (Node tests added in this
#    same change). Sanity-checked here at the source level only.
# ---------------------------------------------------------------------

def test_adapter_declares_seen_and_total_on_normalized_zone():
    assert "seen: seen," in ADAPTER_JS
    assert "total: total," in ADAPTER_JS
    # Safe-numeric-or-zero, same pattern as the existing `stars` field --
    # never lets undefined/NaN/a raw string reach the UI.
    assert "typeof raw.seen === 'number' && !isNaN(raw.seen)" in ADAPTER_JS
    assert "typeof raw.total === 'number' && !isNaN(raw.total)" in ADAPTER_JS


# ---------------------------------------------------------------------
# 2 & 3 & 4. Any unlocked, non-newbie zone shows the generic CTA and
# passes its own zone.key through -- structurally zone-agnostic (no
# special-casing beyond the single k26_30 exclusion), so this covers
# zone k21_25 ("Zone 2"), k16_20 ("Zone 3"), and every other zone alike.
# ---------------------------------------------------------------------

def test_generic_cta_shown_and_wired_for_any_non_newbie_unlocked_zone():
    body = _render_selected_zone_body()
    cta_block_start = body.index("if (cta) {")
    cta_block_end = body.index("renderBeginnerVillageMainline(root, zone);", cta_block_start)
    cta_block = body[cta_block_start:cta_block_end]
    # Exactly one zone-key special case in the whole CTA-visibility block:
    # k26_30 (Beginner Village). No per-zone branching exists for any
    # other zone -- so zone 2, zone 3, ... zone 10 all share one path.
    assert cta_block.count("zone.key === 'k26_30'") == 1
    else_branch = cta_block[cta_block.index("} else {"):]
    assert "cta.hidden = false;" in else_branch
    assert "window.E9.startAdventureFromE9(zone.key);" in else_branch
    assert "t('index.adv.start_challenge', 'Start Challenge')" in else_branch


def test_cta_click_handler_is_rebound_per_selection_not_stacked():
    body = _render_selected_zone_body()
    assert "cta.__e9AdventureHandler" in body
    assert "cta.removeEventListener('click', cta.__e9AdventureHandler)" in body


# ---------------------------------------------------------------------
# 5. Locked zones can never launch an encounter -- not merely via the
#    click handler (renderZones() already never attaches one to a locked
#    tile), but renderSelectedZone() itself must hide the CTA and return
#    before any wiring code runs, so a stale/replayed selection can't
#    launch one either.
# ---------------------------------------------------------------------

def test_locked_zone_early_return_hides_cta_before_any_wiring():
    body = _render_selected_zone_body()
    guard = body[body.index("if (!zone || zone.locked)"):body.index("state.selectedZoneKey")]
    assert "cta.hidden = true;" in guard
    assert "return;" in guard
    assert "startAdventureFromE9" not in guard


def test_locked_tiles_never_receive_a_click_handler_in_render_zones():
    start = WORLD_STAGE.index("function renderZones(")
    end = WORLD_STAGE.index("\n  function recoverToLegacy(", start)
    render_zones_body = WORLD_STAGE[start:end]
    guarded = render_zones_body[render_zones_body.index("if (!zone.locked) {\n        var activate"):]
    assert "e9:zone-selected" in guarded
    assert "renderSelectedZone(root, zones, zone.key, true);" in guarded


# ---------------------------------------------------------------------
# 6 & 7. {seen}/{total} must be substituted with real numbers, and no
# raw, unsubstituted template may ever reach textContent.
# ---------------------------------------------------------------------

def test_boss_ready_text_substitutes_seen_and_total():
    start = WORLD_STAGE.index("function bossReadyText(zone)")
    end = WORLD_STAGE.index("\n  function renderSelectedZone(", start)
    fn_body = WORLD_STAGE[start:end]
    assert ".replace('{seen}', String(zone.seen))" in fn_body
    assert ".replace('{total}', String(zone.total))" in fn_body
    assert "t('index.adv.boss_ready'" in fn_body


def test_renderselectedzone_uses_bossreadytext_helper_not_raw_t_call():
    body = _render_selected_zone_body()
    assert "bossReadyText(zone)" in body
    # The raw, unsubstituted call this bug consisted of must not reappear.
    assert "t('index.adv.boss_ready', 'Boss challenge ready')" not in body


def test_no_unsubstituted_seen_total_or_stars_placeholder_survives_in_world_stage_js():
    # Every literal '{seen}', '{total}', or '{stars}' in the file must
    # appear as the first argument of a .replace(...) call -- never as a
    # bare template left to reach the DOM unsubstituted. '{stars}' is
    # included here (generalizing the original {seen}/{total}-only scan)
    # specifically because that narrower scan is exactly what let the
    # "Defeated {stars}" / "已擊破 {stars}" bug ship through PR #213
    # undetected -- this closes that gap.
    for literal in ("{seen}", "{total}", "{stars}"):
        for match in re.finditer(re.escape("'" + literal + "'"), WORLD_STAGE):
            window = WORLD_STAGE[max(0, match.start() - 12):match.start()]
            assert ".replace(" in window, (
                f"found {literal!r} not immediately preceded by .replace( -- "
                f"context: {WORLD_STAGE[max(0, match.start()-40):match.start()+40]!r}"
            )


# ---------------------------------------------------------------------
# E9-UI-POLISH-PREFLIGHT-1 / GO_IMPLEMENT_E9_I18N_PLACEHOLDER_FIX:
# Bug A -- cleared-zone summary rendered the literal, unsubstituted
# "Defeated {stars}" / "已擊破 {stars}" template (index.adv.boss_cleared)
# for ANY cleared zone (server-side, a cleared zone's bossAvailable is
# always false, so the cleared branch is the only one ever reached once
# a zone is cleared). Fixed via a clearedText(zone) helper mirroring the
# pre-existing bossReadyText(zone) pattern exactly.
# ---------------------------------------------------------------------

def test_cleared_text_helper_substitutes_actual_stars_value():
    start = WORLD_STAGE.index("function clearedText(zone)")
    end = WORLD_STAGE.index("\n  function renderSelectedZone(", start)
    fn_body = WORLD_STAGE[start:end]
    assert "t('index.adv.boss_cleared'" in fn_body
    assert ".replace('{stars}', String(zone.stars))" in fn_body


def test_renderselectedzone_uses_clearedtext_helper_not_raw_t_call():
    body = _render_selected_zone_body()
    assert "clearedText(zone)" in body
    # The raw, unsubstituted call this bug consisted of must not reappear.
    assert "t('index.adv.boss_cleared', 'Area cleared')" not in body
    assert re.search(r"t\(\s*'index\.adv\.boss_cleared'", body) is None, (
        "index.adv.boss_cleared must only ever be read through "
        "clearedText(), never called directly without interpolation"
    )


# ---------------------------------------------------------------------
# Bug B -- the zone-tile "boss ready" badge truncated
# t('index.adv.boss_ready', ...) with .split(':')[0] to drop the
# "{seen}/{total}" portion for the compact tile badge. The Chinese
# dictionary string uses a FULL-WIDTH colon ('：', U+FF1A), not the
# ASCII ':' (U+003A) the English string uses -- so .split(':') silently
# failed to match in Chinese, leaking "封印解除：{seen}/{total} 題"
# verbatim onto the badge in that locale only.
#
# A colon-only split is still not sufficient on its own: a FUTURE
# translation could carry the same {seen}/{total} placeholders with no
# colon delimiter at all (e.g. "Seal broken {seen}/{total}"), which
# would sail straight through a colon split untouched. The fix moved the
# truncation into a dedicated bossReadyBadgeText() helper that ALSO
# splits on the literal placeholder tokens as an independent second
# safety net, so neither {seen} nor {total} can survive regardless of
# what delimiter (if any) a translation uses.
#
# These tests deliberately do not assert on any one exact source
# expression (e.g. a specific split()/regex call) -- a different,
# equally valid implementation of that same guarantee must be allowed
# to pass. Instead they (a) prove the tile badge is produced through a
# single named, testable helper rather than inline logic duplicated at
# the call site, and (b) prove actual resolved behavior by extracting
# bossReadyBadgeText()'s exact, current source out of the real
# world_stage.js and EXECUTING it for real inside a Node vm context
# (with a controlled t() stub standing in for I18nFallback) -- not by
# restating its truncation algorithm a second time in Python. world_stage.js
# is a browser-only file (a single top-level IIFE, no module.exports), so
# this is the only way to run its actual code from a Python test; see
# _run_boss_ready_badge_text_node_harness() below.
# ---------------------------------------------------------------------

def _i18n_entry_values(key):
    match = re.search(
        re.escape("'" + key + "'") + r"\s*:\s*\{\s*en:\s*'((?:[^'\\]|\\.)*)'\s*,\s*zh:\s*'((?:[^'\\]|\\.)*)'",
        I18N,
    )
    assert match, f"{key} not found in i18n.js in the expected {{ en: '...', zh: '...' }} shape"
    return match.group(1), match.group(2)


def test_renderzones_uses_bossreadybadgetext_helper_not_inline_logic():
    assert "function bossReadyBadgeText()" in WORLD_STAGE

    start = WORLD_STAGE.index("function renderZones(")
    end = WORLD_STAGE.index("\n  function recoverToLegacy(", start)
    fn_body = WORLD_STAGE[start:end]
    assert "bossReadyBadgeText()" in fn_body
    # The badge must be produced by calling the helper, not by
    # re-deriving the truncation inline at the call site again.
    assert ".split(" not in fn_body


def test_bossreadybadgetext_never_uses_ascii_only_colon_split():
    # Regression guard for the original Bug B defect: an ASCII-only
    # colon split silently fails to match the full-width '：' the
    # Chinese dictionary value uses, leaking "{seen}/{total}" in that
    # locale. This must never reappear anywhere in the file.
    assert "split(':')[0]" not in WORLD_STAGE


# Node harness: extracts bossReadyBadgeText()'s EXACT function source out
# of the real world_stage.js on disk (brace-matched substring, not
# retyped), then executes that exact source in a fresh vm context with an
# injectable t(key, fallback) stub, for each required (input, expected)
# case supplied via argv. This runs the real production code -- it does
# not reimplement the truncation algorithm.
_BOSS_READY_BADGE_NODE_HARNESS = r"""
'use strict';
const fs = require('fs');
const assert = require('assert');
const vm = require('vm');

const WORLD_STAGE_PATH = process.argv[1];
const CASES = JSON.parse(process.argv[2]);
const FUNCTION_NAME = 'bossReadyBadgeText';

function extractFunctionSource(fullSource, functionName) {
  const marker = 'function ' + functionName + '(';
  const startIdx = fullSource.indexOf(marker);
  if (startIdx === -1) throw new Error('function ' + functionName + '() not found');
  const braceStart = fullSource.indexOf('{', startIdx);
  if (braceStart === -1) throw new Error('opening brace not found for ' + functionName + '()');
  let depth = 0, endIdx = -1;
  for (let i = braceStart; i < fullSource.length; i++) {
    const ch = fullSource[i];
    if (ch === '{') depth++;
    else if (ch === '}') { depth--; if (depth === 0) { endIdx = i + 1; break; } }
  }
  if (endIdx === -1) throw new Error('matching closing brace not found for ' + functionName + '()');
  const extracted = fullSource.slice(startIdx, endIdx);
  if (!new RegExp('^function\\s+' + functionName + '\\s*\\(\\s*\\)\\s*\\{').test(extracted)) {
    throw new Error('extracted text does not look like a bare ' + functionName + '() declaration:\n' + extracted);
  }
  return extracted;
}

const worldStageSource = fs.readFileSync(WORLD_STAGE_PATH, 'utf8');
const functionSource = extractFunctionSource(worldStageSource, FUNCTION_NAME);
if (!/\bt\s*\(/.test(functionSource)) {
  throw new Error(FUNCTION_NAME + '() no longer calls t(...) -- cannot inject a controlled translation');
}

function runWithTranslation(translationValue) {
  const sandbox = { t: function () { return translationValue; }, __result: undefined };
  vm.createContext(sandbox);
  new vm.Script(functionSource + '\n__result = ' + FUNCTION_NAME + '();').runInContext(sandbox);
  return sandbox.__result;
}

let failures = [];
let passCount = 0;
CASES.forEach(function (c) {
  try {
    const result = runWithTranslation(c.input);
    assert.strictEqual(result, c.expected,
      'input ' + JSON.stringify(c.input) + ' resolved to ' + JSON.stringify(result) +
      ', expected ' + JSON.stringify(c.expected));
    assert.ok(result.indexOf('{seen}') === -1, 'leaked {seen} into badge text: ' + JSON.stringify(result));
    assert.ok(result.indexOf('{total}') === -1, 'leaked {total} into badge text: ' + JSON.stringify(result));
    passCount++;
  } catch (err) {
    failures.push(c.label + ': ' + (err.message || String(err)));
  }
});

if (failures.length) {
  console.error('FAILURES:');
  failures.forEach(f => console.error('  - ' + f));
  console.error('\n' + passCount + ' passed, ' + failures.length + ' failed');
  process.exit(1);
} else {
  console.log(passCount + ' passed, 0 failed');
  process.exit(0);
}
"""

BOSS_READY_BADGE_REQUIRED_CASES = [
    {"label": "current English dictionary value", "input": "Seal broken: {seen}/{total}", "expected": "Seal broken"},
    {"label": "current Chinese dictionary value (full-width colon)", "input": "封印解除：{seen}/{total} 題", "expected": "封印解除"},
    {"label": "hypothetical delimiter-free English translation", "input": "Seal broken {seen}/{total}", "expected": "Seal broken"},
    {"label": "hypothetical delimiter-free Chinese translation", "input": "封印解除 {seen}/{total} 題", "expected": "封印解除"},
]


def test_bossreadybadgetext_production_linked_behavior_via_node():
    en_value, zh_value = _i18n_entry_values('index.adv.boss_ready')
    assert en_value == 'Seal broken: {seen}/{total}'
    assert zh_value == '封印解除：{seen}/{total} 題'

    result = subprocess.run(
        ["node", "-e", _BOSS_READY_BADGE_NODE_HARNESS, "--",
         str(WORLD_STAGE_PATH), json.dumps(BOSS_READY_BADGE_REQUIRED_CASES)],
        capture_output=True, text=True, timeout=30, cwd=str(ROOT),
    )
    assert result.returncode == 0, (
        f"production-linked bossReadyBadgeText() behavioral tests failed:\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "passed" in result.stdout
    assert "0 failed" in result.stdout


# ---------------------------------------------------------------------
# i18n template guards: if a future copy edit ever removes these
# placeholders from the dictionary, the substitution calls above become
# silent no-ops rather than loud failures -- these guards make that
# scenario fail closed instead.
# ---------------------------------------------------------------------

def test_i18n_boss_cleared_retains_stars_placeholder():
    en_value, zh_value = _i18n_entry_values('index.adv.boss_cleared')
    assert '{stars}' in en_value
    assert '{stars}' in zh_value


def test_i18n_boss_ready_retains_seen_and_total_placeholders():
    en_value, zh_value = _i18n_entry_values('index.adv.boss_ready')
    assert '{seen}' in en_value and '{total}' in en_value
    assert '{seen}' in zh_value and '{total}' in zh_value


# ---------------------------------------------------------------------
# 8. Beginner Village's own tutorial CTA must not regress, and must never
# be shown alongside a second, duplicate generic CTA.
# ---------------------------------------------------------------------

def test_newbie_mainline_cta_untouched_and_generic_cta_hidden_for_it():
    assert "function renderBeginnerVillageMainline(root, zone)" in WORLD_STAGE
    assert "if (!panel || !zone || zone.key !== 'k26_30') return;" in WORLD_STAGE
    assert "#e9-newbie-mainline-cta" in WORLD_STAGE

    body = _render_selected_zone_body()
    if_block = body[body.index("if (cta) {"):body.index("} else {")]
    assert "zone.key === 'k26_30'" in if_block
    assert "cta.hidden = true;" in if_block


def test_html_has_exactly_one_generic_cta_button_hidden_by_default():
    details_section_start = WORLD_STAGE_HTML.index('id="e9-world-stage-details"')
    details_section_end = WORLD_STAGE_HTML.index("</section>", details_section_start)
    details_section = WORLD_STAGE_HTML[details_section_start:details_section_end]
    assert details_section.count("<button") == 1
    button_tag = re.search(r"<button[^>]*>", details_section).group(0)
    assert 'id="e9-world-stage-details-cta"' in button_tag
    assert 'type="button"' in button_tag
    classes = re.search(r'class="([^"]+)"', button_tag).group(1).split()
    assert "e9-zone-details__cta" in classes
    assert "e9-adventure-cta" in classes
    assert "hidden" in button_tag


def test_beginner_and_generic_ctas_share_one_adventure_button_class():
    buttons = {
        element_id: re.search(
            rf'<button[^>]*id="{re.escape(element_id)}"[^>]*>',
            WORLD_STAGE_HTML,
        ).group(0)
        for element_id in (
            "e9-world-stage-details-cta",
            "e9-newbie-mainline-cta",
        )
    }
    for button_tag in buttons.values():
        classes = re.search(r'class="([^"]+)"', button_tag).group(1).split()
        assert "e9-adventure-cta" in classes
        assert 'type="button"' in button_tag


def _shared_cta_rule(selector):
    match = re.search(
        re.escape(selector) + r"\s*\{(?P<body>[^}]*)\}",
        WORLD_STAGE_CSS,
    )
    assert match, f"{selector} rule missing"
    return match.group("body")


def test_shared_cta_has_non_default_primary_action_styling():
    rule = _shared_cta_rule(".e9-adventure-cta")
    required_properties = {
        "min-height": "44px",
        "border": "0",
        "border-radius": "10px",
        "background": "#6b5b3a",
        "color": "#fff",
        "font-weight": "700",
        "cursor": "pointer",
    }
    for prop, value in required_properties.items():
        assert re.search(
            rf"{re.escape(prop)}\s*:\s*{re.escape(value)}\s*;",
            rule,
        ), f"{prop}: {value} missing from shared CTA rule"


def test_shared_cta_has_pointer_keyboard_and_disabled_states():
    assert _shared_cta_rule(".e9-adventure-cta:hover")
    assert _shared_cta_rule(".e9-adventure-cta:active")
    focus = _shared_cta_rule(".e9-adventure-cta:focus-visible")
    assert "outline:" in focus
    assert ".e9-adventure-cta:disabled," in WORLD_STAGE_CSS
    assert '.e9-adventure-cta[aria-disabled="true"]' in WORLD_STAGE_CSS
    assert "cursor: not-allowed;" in WORLD_STAGE_CSS


def test_shared_cta_is_mobile_safe_and_allows_long_copy_to_wrap():
    base = _shared_cta_rule(".e9-adventure-cta")
    assert "max-width: 100%;" in base
    assert "white-space: normal;" in base
    assert "overflow-wrap: anywhere;" in base
    mobile = re.search(
        r"@media\s*\(max-width:\s*600px\)\s*\{"
        r"(?P<body>.*?)"
        r"\n\}",
        WORLD_STAGE_CSS,
        re.DOTALL,
    )
    assert mobile, "mobile CTA rule missing"
    assert ".e9-adventure-cta" in mobile.group("body")
    assert "width: 100%;" in mobile.group("body")


# ---------------------------------------------------------------------
# 9. zh/en copy: the reused key must exist in both languages, and no new
# i18n key was introduced for this fix.
# ---------------------------------------------------------------------

def test_start_challenge_key_exists_in_both_languages_and_is_reused():
    match = re.search(r"'index\.adv\.start_challenge':\s*\{([^}]*)\}", I18N)
    assert match, "index.adv.start_challenge key not found in i18n.js"
    entry = match.group(1)
    assert "en:" in entry and "zh:" in entry
    assert "t('index.adv.start_challenge'" in WORLD_STAGE


def test_no_new_i18n_key_introduced_for_this_fix():
    # Every index.adv.* key referenced by world_stage.js must already have
    # existed for a documented, pre-existing reason (per world_stage.html's
    # own header comment) -- this fix adds zero new keys.
    referenced = set(re.findall(r"t\('(index\.adv\.[a-z_]+)'", WORLD_STAGE))
    expected = {
        'index.adv.boss_ready', 'index.adv.boss_cleared', 'index.adv.panel_ready',
        'index.adv.summary', 'index.adv.zone_locked', 'index.adv.start_challenge',
    }
    assert referenced == expected, f"unexpected index.adv.* keys: {referenced - expected}"
    for key in referenced:
        assert re.search(re.escape("'" + key + "'") + r"\s*:\s*\{", I18N), f"{key} missing from i18n.js"


# ---------------------------------------------------------------------
# 10. Legacy URL handoff format must be byte-identical to before --
# this fix only adds CALLERS of startAdventureFromE9(), it must not
# change what that function itself does.
# ---------------------------------------------------------------------

def test_start_adventure_from_e9_url_format_unchanged():
    assert "global.location.href = '/?zone=' + encodeURIComponent(zoneKey) + '&adventure=1&resume=1';" in SHELL_JS


def test_legacy_own_href_builder_uses_the_same_format():
    index_html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "`/?zone=${encodeURIComponent(zone.key)}&adventure=1&resume=1`" in index_html


# ---------------------------------------------------------------------
# sw.js version bump (this Sprint changed world_stage.js, world_stage.html,
# and adapters/adventure_state.js -- all live-static/cache-first-governed
# files per the repo's established convention).
# ---------------------------------------------------------------------

def test_sw_version_bumped_for_this_change():
    assert NEW_SW_VERSION in SW
    assert PREVIOUS_SW_VERSION not in SW


def test_sw_diff_is_version_line_only():
    assert SW.count("const VERSION") == 1
    assert "self.addEventListener('fetch'" in SW
    assert "self.addEventListener('install'" in SW
    assert "self.addEventListener('activate'" in SW
