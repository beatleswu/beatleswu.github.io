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
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORLD_STAGE = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
WORLD_STAGE_HTML = (ROOT / "components/adventure/world_stage.html").read_text(encoding="utf-8")
WORLD_STAGE_CSS = (ROOT / "css/e9/world_stage.css").read_text(encoding="utf-8")
SHELL_JS = (ROOT / "js/e9/shell.js").read_text(encoding="utf-8")
ADAPTER_JS = (ROOT / "js/e9/adapters/adventure_state.js").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")

NEW_SW_VERSION = "v205-e9-zone-cta-visual-parity"


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


def test_no_unsubstituted_seen_total_placeholder_survives_in_world_stage_js():
    # Every literal '{seen}' or '{total}' in the file must appear as the
    # first argument of a .replace(...) call -- never as a bare template
    # left to reach the DOM unsubstituted.
    for literal in ("{seen}", "{total}"):
        for match in re.finditer(re.escape("'" + literal + "'"), WORLD_STAGE):
            window = WORLD_STAGE[max(0, match.start() - 12):match.start()]
            assert ".replace(" in window, (
                f"found {literal!r} not immediately preceded by .replace( -- "
                f"context: {WORLD_STAGE[max(0, match.start()-40):match.start()+40]!r}"
            )


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
    assert "v203-e9-zone-name-i18n-fix" not in SW


def test_sw_diff_is_version_line_only():
    assert SW.count("const VERSION") == 1
    assert "self.addEventListener('fetch'" in SW
    assert "self.addEventListener('install'" in SW
    assert "self.addEventListener('activate'" in SW
