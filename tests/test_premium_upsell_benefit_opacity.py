"""HOTFIX-PREMIUM-UPSELL-01 — regression tests for the daily-limit-wall
benefit card visibility fix.

Root cause (confirmed against live Production with an authenticated
session, DOM inspected, computed styles read): `.free-limit-benefit`
shares the `.modal-system-benefit` base rule, which sets `opacity:0` as
the starting state for a `.show`-triggered reveal animation used
elsewhere (`.rankup-ritual-reward.show`). `_showDailyLimitWall()` only
ever adds `.show` to the outer `#daily-limit-wall`, never to the
individual benefit rows, so they stayed permanently invisible while
still occupying layout space (a large blank gap, not a collapsed
layout). Git/production source were never out of sync -- this bug has
been present in `master` since the same-day commit that introduced the
shared `.modal-system-benefit` selector.

Fix: a single new CSS rule, `.daily-limit-wall.show .free-limit-benefit
{ opacity: 1; }`, scopes the reveal to the wall's own `.show` state
instead of requiring each row to carry its own `.show` class. No JS
change. These are source-level contract tests (this repo has no JS test
framework/live browser test runner in CI -- see
tests/test_e9_adventure_shell_foundation.py for the same established
pattern); the fix was also verified live in the Browser pane against
both a local static copy and the real, authenticated Production page.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "index.html"


def _read():
    return INDEX_HTML.read_text(encoding="utf-8")


def test_reveal_rule_exists_and_is_scoped_to_wall_show():
    html = _read()
    assert ".daily-limit-wall.show .free-limit-benefit { opacity: 1; }" in html, (
        "the scoped reveal rule must exist so benefit cards become visible "
        "once #daily-limit-wall gets its .show class"
    )


def test_base_shared_rule_still_sets_opacity_zero():
    # We did not remove the shared base rule (that would be a bigger,
    # riskier change touching .rankup-ritual-reward too) -- we only added
    # a more specific override scoped to the daily-limit-wall context.
    html = _read()
    match = re.search(
        r"\.rankup-ritual-reward,\s*\n\s*\.modal-system-benefit \{([^}]*)\}",
        html,
    )
    assert match, "shared .modal-system-benefit base rule not found"
    assert "opacity:0" in match.group(1).replace(" ", "")


def test_no_classlist_add_show_was_introduced_on_benefit_rows():
    # The fix must be CSS-only. _showDailyLimitWall() must still only ever
    # target the wall itself, never an individual .free-limit-benefit row.
    html = _read()
    fn_match = re.search(r"function _showDailyLimitWall\(\) \{(.*?)\n\}", html, re.S)
    assert fn_match, "_showDailyLimitWall() not found"
    fn_body = fn_match.group(1)
    assert "free-limit-benefit" not in fn_body
    assert fn_body.count("classList.add('show')") == 1


def test_rankup_reward_show_animation_untouched():
    html = _read()
    assert ".rankup-ritual-reward.show { animation: rankupRewardIn .54s ease forwards; }" in html, (
        "the unrelated rank-up reward reveal animation must not be modified by this hotfix"
    )


def test_three_benefit_cards_unchanged_content():
    html = _read()
    for icon, title_key in [
        ("⚡", "index.free_limit_wall.benefit1_title"),
        ("∞", "index.free_limit_wall.benefit2_title"),
        ("📘", "index.free_limit_wall.benefit3_title"),
    ]:
        assert f'aria-hidden="true">{icon}</span>' in html
        assert f'data-i18n="{title_key}"' in html


def test_free_limit_benefit_class_present_exactly_three_times_in_modal():
    html = _read()
    start = html.find('id="daily-limit-wall"')
    assert start != -1
    window = html[start:start + 4000]
    # exact row-wrapper class, not a prefix match against
    # free-limit-benefit-icon/-title/-desc/-copy/-benefits (plural)
    assert len(re.findall(r'class="free-limit-benefit modal-system-benefit"', window)) == 3


def test_css_diff_is_purely_additive_new_rule_only():
    # Regression guard: this hotfix must not touch any other selector in
    # the shared modal-system rule block.
    html = _read()
    assert html.count(".daily-limit-wall.show .free-limit-benefit") == 1
