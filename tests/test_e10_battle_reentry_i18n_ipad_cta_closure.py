"""E10_BATTLE_REENTRY_I18N_IPAD_PORTRAIT_CLOSURE.

New, focused tests for the three fixes bundled in this round. FIX A's own
narrow diff (reusing `_resolveMapBattleV1Resume` inside
`enterAdventureZoneInPage`) is already covered by the updated assertions in
test_e10_battle_explanation_and_return_actions.py and the async-conversion
regression fixes in test_e10_ipad_adventure_interaction_recovery.py -- not
duplicated here.

FIX B -- i18n closure for the E10 world-stage CTA's `actionLabel()` kinds
(challenge_lord/continue_adventure were the explicitly required pair;
resume_encounter/replenish_stars share the exact same missing-key defect in
the same function and are closed in the same pass per owner instruction).

FIX C -- iPad portrait (768-1279px, orientation: portrait) overflow of the
big map CTA's decorative frame, caused by reference_world_map.css's fixed
`height: 15%` (of the aspect-ratio-locked map stage) not leaving enough
room, at portrait's much shorter rendered map height, for the runtime-v1
skin's desktop-sized 72px icon / 29px label.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
I18N_JS = (ROOT / "i18n.js").read_text(encoding="utf-8")
WORLD = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
ART_CSS = (ROOT / "css/e9/art_directed_runtime.css").read_text(encoding="utf-8")
IMMERSIVE_CSS = (ROOT / "css/e9/immersive_rpg.css").read_text(encoding="utf-8")
REFERENCE_CSS = (ROOT / "css/e9/reference_world_map.css").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# FIX B -- i18n completeness for actionLabel()'s kinds
# ---------------------------------------------------------------------------

ACTION_LABEL_KEYS = {
    "e10.world_stage.challenge_lord": "挑戰領主",
    "e10.world_stage.continue_adventure": "繼續冒險",
    "e10.world_stage.resume_encounter": "繼續挑戰",
    "e10.world_stage.replenish_stars": "補星修行",
}


@pytest.mark.parametrize("key,zh_value", ACTION_LABEL_KEYS.items())
def test_action_label_key_resolves_to_required_zh_string(key, zh_value):
    pattern = re.escape("'" + key + "'") + r"\s*:\s*\{\s*en:\s*'[^']*'\s*,\s*zh:\s*'([^']*)'\s*\}"
    match = re.search(pattern, I18N_JS)
    assert match, f"{key} missing or malformed in i18n.js"
    assert match.group(1) == zh_value


def test_action_label_calls_the_now_defined_keys_with_matching_fallback():
    # actionLabel() itself is unchanged -- confirms the keys just added are
    # actually the ones this function reads, not a coincidentally similar key.
    assert "t('e10.world_stage.resume_encounter', 'Resume Encounter')" in WORLD
    assert "t('e10.world_stage.challenge_lord', 'Challenge Lord')" in WORLD
    assert "t('e10.world_stage.replenish_stars', 'Replenish Stars')" in WORLD
    assert "t('e10.world_stage.continue_adventure', 'Continue Adventure')" in WORLD


def test_dispatch_routing_is_never_derived_from_the_rendered_label():
    # Regression guard for the explicit no-string-routing constraint: the
    # click-routing dispatcher must branch on contract.kind only, and must
    # never call actionLabel()/t() to decide behavior.
    dispatch = WORLD.split("function dispatchAdventureAction(contract) {", 1)[1].split("\n  }\n", 1)[0]
    assert "actionLabel(" not in dispatch
    assert "contract.kind === 'challenge_lord'" in dispatch
    assert "t(" not in dispatch


# ---------------------------------------------------------------------------
# FIX C -- iPad portrait CTA overflow
# ---------------------------------------------------------------------------

def _portrait_tablet_block():
    marker = "@media (min-width: 768px) and (max-width: 1279px) and (orientation: portrait) {"
    start = ART_CSS.index(marker)
    depth = 0
    i = ART_CSS.index("{", start)
    block_start = i
    depth = 1
    i += 1
    while depth:
        if ART_CSS[i] == "{":
            depth += 1
        elif ART_CSS[i] == "}":
            depth -= 1
        i += 1
    return ART_CSS[block_start:i]


def test_ipad_portrait_cta_grows_to_fit_instead_of_clipping():
    block = _portrait_tablet_block()
    assert "height: auto" in block
    assert "min-height:" in block
    assert "overflow: hidden" not in block
    assert "overflow:hidden" not in block


def test_ipad_portrait_cta_touch_target_is_not_shrunk_below_accessible_minimum():
    block = _portrait_tablet_block()
    match = re.search(r"\.e10-map-primary-cta\s*\{[^}]*min-height:\s*(\d+)px", block)
    assert match, "expected an explicit min-height on the portrait-scoped CTA rule"
    assert int(match.group(1)) >= 44


def test_ipad_portrait_cta_icon_and_label_scale_down_to_fit_shorter_map_height():
    block = _portrait_tablet_block()
    icon_match = re.search(r"__icon\s*\{\s*width:\s*(\d+)px;\s*height:\s*(\d+)px", block)
    assert icon_match
    assert int(icon_match.group(1)) < 72
    assert int(icon_match.group(2)) < 72

    strong_match = re.search(r"__copy strong\s*\{\s*font-size:\s*(\d+)px", block)
    assert strong_match
    assert int(strong_match.group(1)) < 29


def test_ipad_landscape_baseline_is_untouched():
    # The task explicitly forbids regressing the already-correct landscape
    # rendering. Landscape at this exact 768-1279px breakpoint already had
    # its own pre-existing downsize block (gap/padding/icon/font) -- that is
    # WHY landscape was already fine while portrait, which had no equivalent
    # downsize at all (only `display: inline-flex !important`), overflowed.
    # FIX C must not modify a single byte of this pre-existing landscape
    # block; it only adds a new, separate portrait-scoped block.
    landscape_block_marker = "@media (min-width: 768px) and (max-width: 1279px) and (orientation: landscape) {"
    assert landscape_block_marker in ART_CSS
    landscape_start = ART_CSS.index(landscape_block_marker)
    portrait_marker = "@media (min-width: 768px) and (max-width: 1279px) and (orientation: portrait) {"
    portrait_start = ART_CSS.index(portrait_marker)
    landscape_block = ART_CSS[landscape_start:portrait_start]

    assert (
        "body[data-e10-visual-skin=\"immersive-rpg\"][data-e10-art-kit=\"runtime-v1\"] "
        "#e9-adventure-shell .e10-map-primary-cta {\n"
        "    gap: 6px;\n"
        "    padding: 8px 14px 8px 34px;\n"
        "  }"
    ) in landscape_block
    assert (
        "body[data-e10-visual-skin=\"immersive-rpg\"][data-e10-art-kit=\"runtime-v1\"] "
        ".e10-map-primary-cta__icon {\n"
        "    width: 46px;\n"
        "    height: 46px;\n"
        "  }"
    ) in landscape_block
    assert (
        "body[data-e10-visual-skin=\"immersive-rpg\"][data-e10-art-kit=\"runtime-v1\"] "
        "#e9-adventure-shell .e10-map-primary-cta__copy strong {\n"
        "    font-size: 21px;\n"
        "    line-height: 1.04;\n"
        "  }"
    ) in landscape_block
    landscape_cta_rule = landscape_block.split(
        'body[data-e10-visual-skin="immersive-rpg"][data-e10-art-kit="runtime-v1"] #e9-adventure-shell .e10-map-primary-cta {',
        1,
    )[1].split("}", 1)[0]
    assert "height: auto" not in landscape_cta_rule
    assert "min-height:" not in landscape_cta_rule

    # The unconditional (all-viewport) runtime-v1 rule -- what portrait fell
    # back to before this fix, since it had no downsize of its own -- must
    # still be untouched, since narrower/other contexts may still depend on it.
    unconditional_icon = ART_CSS.split(
        'body[data-e10-visual-skin="immersive-rpg"][data-e10-art-kit="runtime-v1"] .e10-map-primary-cta__icon {',
        1,
    )[1].split("}", 1)[0]
    assert "width: 72px;" in unconditional_icon
    assert "height: 72px;" in unconditional_icon


def test_reference_css_fixed_height_percentage_is_still_present_but_now_overridden_in_portrait():
    # Confirms the actual root cause (a fixed height: 15% tied to the
    # aspect-ratio-locked map stage, which shrinks much further in portrait
    # than landscape) is still there -- FIX C overrides it for portrait via
    # higher-specificity selector rather than editing this shared base rule,
    # so landscape/other skins relying on it are unaffected.
    assert "height: 15%;" in REFERENCE_CSS
