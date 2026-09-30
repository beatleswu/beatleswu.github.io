"""Focused source contracts for the G009 Phase 3B-A browser corrective.

These checks guard the four browser blockers without replacing F's real-browser
acceptance: the drawer and responsive state still require viewport evidence.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAV = (ROOT / "site-nav.js").read_text(encoding="utf-8")
WORLD_STAGE = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
WORLD_MAP_CSS = (ROOT / "css/e9/reference_world_map.css").read_text(encoding="utf-8")
UPGRADE = (ROOT / "upgrade.html").read_text(encoding="utf-8")


def test_compact_world_map_navigation_has_real_drawer_contract():
    expected = (
        ("/curriculum", "learning_hub", "學習公會"),
        ("/play", "arena", "競技場"),
        ("/community", "tavern", "酒館"),
        ("/hero", "hero_hub", "英雄殿"),
        ("/inventory", "backpack", "背包"),
        ("/shop", "shop", "商店"),
        ("/upgrade", "premium", "通行證"),
    )
    for href, key, label in expected:
        assert f"href: '{href}'" in NAV
        assert f"key: '{key}'" in NAV
        assert f"label: '{label}'" in NAV
    assert "ownsE10MapNavigation" in NAV
    assert "if (e10Owned && !ownsE10MapNavigation())" in NAV
    assert "data-g009-global-drawer" in NAV
    assert "data-g009-drawer-close" in NAV
    assert "data-g009-drawer-link" in NAV
    assert "width: 44px" in NAV
    assert "min-width: 44px" in NAV
    assert "height: 44px" in NAV
    assert "min-height: 44px" in NAV
    assert "display: inline-flex !important" in WORLD_MAP_CSS
    assert "@media (max-width: 1024px)" in WORLD_MAP_CSS


def test_world_map_locked_selected_state_is_a_true_render_boundary():
    assert "targetZone.locked || targetZone.canEnter === false" in WORLD_STAGE
    assert "button.replaceChildren();" in WORLD_STAGE
    assert "#e9-world-stage-details-cta[hidden]" in WORLD_MAP_CSS
    assert "#e9-world-stage-details-secondary-cta[hidden]" in WORLD_MAP_CSS
    assert "#e9-world-stage-primary-cta[hidden]" in WORLD_MAP_CSS
    assert "display: none !important" in WORLD_MAP_CSS
    assert "pointer-events: none !important" in WORLD_MAP_CSS


def test_mobile_zone_details_are_interaction_revealed():
    assert ".e9-zone:not(.e9-zone--locked):not(.is-current):not(.is-selected):not(:focus) .e9-zone__name" in WORLD_MAP_CSS
    assert ".e9-zone:not(.e9-zone--locked):not(.is-current):not(.is-selected):not(:focus) .e9-zone__stars" in WORLD_MAP_CSS
    assert ".e9-zone:not(.e9-zone--locked):not(.is-current):not(.is-selected):not(:focus) .e9-zone__status-text" in WORLD_MAP_CSS
    assert "@media (max-width: 767px)" in WORLD_MAP_CSS


def test_upgrade_gets_the_shared_seven_item_premium_identity():
    assert '<body data-g009-surface="premium">' in UPGRADE
    assert "const isPremiumSurface" in NAV
    assert "normalize(location.pathname) === '/upgrade'" in NAV
    assert "document.body.insertBefore(header, document.body.firstChild)" in NAV
    assert 'data-g009-global-nav="7"' in NAV
    assert "key: 'premium'" in NAV
