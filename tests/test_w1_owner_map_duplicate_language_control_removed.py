"""Owner postdeploy acceptance corrective, Issue C.

The Adventure map's top-right carried a DUPLICATE language control: the
`.cg-brand-mark` goban glyph (a board with a black and a white stone, styled in
site-nav.js) plus the `.cg-nav-lang` EN / 中 switcher. `reference_world_map.css`
promoted the E10 session strip into a fixed floating utility to expose it.

The Owner removed that control. These tests pin the removal as a REMOVAL --
no glyph, no toggle, no hit target, no reserved space -- and pin that the
primary language switching mechanism is untouched.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLD_MAP_CSS = (ROOT / "css/e9/reference_world_map.css").read_text(encoding="utf-8")
IMMERSIVE_CSS = (ROOT / "css/e9/immersive_rpg.css").read_text(encoding="utf-8")
SITE_NAV = (ROOT / "site-nav.js").read_text(encoding="utf-8")
TOP_HUD_HTML = (ROOT / "components/adventure/top_hud.html").read_text(encoding="utf-8")
TOP_HUD_JS = (ROOT / "js/e9/top_hud.js").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")

STRIP_SELECTOR = 'body[data-e10-visual-skin="immersive-rpg"] .cg-nav[data-e10-session-strip="1"]'


def _strip_rules(css: str) -> list[str]:
    """Every rule body whose selector targets the E10 session strip."""
    bodies = []
    for match in re.finditer(re.escape(STRIP_SELECTOR), css):
        open_brace = css.find("{", match.start())
        close_brace = css.find("}", open_brace)
        if open_brace == -1 or close_brace == -1:
            continue
        # Only count this as a rule for the strip if the selector runs
        # uninterrupted from the match to the brace (i.e. it is not a comment).
        selector_tail = css[match.end():open_brace]
        if "*/" in selector_tail or "{" in selector_tail:
            continue
        bodies.append(css[open_brace + 1:close_brace])
    return bodies


def test_map_session_strip_is_removed_not_merely_clipped():
    rules = _strip_rules(WORLD_MAP_CSS)
    assert rules, "the session-strip rule must still exist, declaring the removal"
    combined = "\n".join(rules)
    assert "display: none" in combined
    # A clipped/sr-only element is still focusable and still an active hit
    # target -- explicitly NOT an acceptable removal per the Owner.
    assert "clip-path" not in combined
    assert "position: fixed" not in combined
    assert "position: absolute" not in combined


def test_no_floating_language_hit_target_on_the_map():
    combined = "\n".join(_strip_rules(WORLD_MAP_CSS))
    assert "pointer-events" not in combined
    # The former floating utility anchored itself to the map's top-right.
    assert "env(safe-area-inset-right" not in combined
    assert "z-index: 1000" not in combined


def test_no_reserved_space_or_inner_layout_for_the_removed_strip():
    # Inner layout rules (brand sizing / action alignment) must not survive the
    # control they laid out, or the map keeps reserving space for nothing.
    for css in (WORLD_MAP_CSS, IMMERSIVE_CSS):
        for selector_fragment in (
            f'{STRIP_SELECTOR} .cg-nav-inner',
            f'{STRIP_SELECTOR} .cg-brand',
            f'{STRIP_SELECTOR} .cg-nav-actions',
            f'{STRIP_SELECTOR} .cg-nav-lang',
            f'{STRIP_SELECTOR} #lang-switcher-index',
        ):
            assert selector_fragment not in css, selector_fragment


def test_primary_language_switching_is_untouched():
    # site-nav.js remains the primary switcher host on every non-map surface.
    assert ".cg-nav-lang" in SITE_NAV
    assert "I18n.renderSwitcher(box)" in SITE_NAV
    assert "lang-switcher-nav" in SITE_NAV
    # The shared renderer still emits both locales.
    assert "'EN'" in I18N and "'中'" in I18N
    assert "function renderSwitcher(container)" in I18N
    assert "function setLang(lang)" in I18N


def test_map_users_keep_a_non_duplicate_language_path():
    # Language switching on the map surface remains reachable through the E10
    # settings dialog, which is not a duplicate of the site-nav switcher.
    assert 'id="e10-settings-language"' in TOP_HUD_HTML
    assert "#e10-settings-language" in TOP_HUD_JS
    assert "window.I18n.renderSwitcher(language)" in TOP_HUD_JS


def test_goban_brand_mark_is_not_rendered_by_the_map_surface():
    # The glyph itself still belongs to site-nav's brand on ordinary pages;
    # what must not happen is the map surfacing it as a floating control.
    assert "cg-brand-mark" in SITE_NAV
    combined = "\n".join(_strip_rules(WORLD_MAP_CSS))
    assert "cg-brand" not in combined
