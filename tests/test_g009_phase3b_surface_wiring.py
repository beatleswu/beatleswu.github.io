"""Source-level guards for the locked G009 Phase 3B-A surface contract."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_locked_global_navigation_has_seven_stable_route_hooks() -> None:
    source = read("site-nav.js")
    nav_block = source[source.index("const NAV_ITEMS"):source.index("const ICONS")]
    expected = [
        ("/curriculum", "learning_hub", "學習公會"),
        ("/play", "arena", "競技場"),
        ("/community", "tavern", "酒館"),
        ("/hero", "hero_hub", "英雄殿"),
        ("/inventory", "backpack", "背包"),
        ("/shop", "shop", "商店"),
        ("/upgrade", "premium", "通行證"),
    ]
    actual = re.findall(
        r'\{ href: [\'\"]([^\'\"]+)[\'\"],\s*key: [\'\"]([^\'\"]+)[\'\"].*?label: [\'\"]([^\'\"]+)[\'\"]',
        nav_block,
        flags=re.DOTALL,
    )
    assert actual == expected
    assert 'data-g009-global-nav="7"' in source
    assert "data-g009-nav-key=\"${item.key}\"" in source
    assert "冒險公會" not in nav_block
    assert "學習中心" not in nav_block
    assert "Hero's Hall" not in nav_block
    assert "Pass" not in nav_block


def test_release_surface_roots_and_learning_secondary_reachability_are_stable() -> None:
    expected = {
        "curriculum.html": 'data-g009-surface="learning-hub"',
        "stats.html": 'data-g009-surface="learning-progress"',
        "community.html": 'data-g009-surface="tavern"',
        "hero.html": 'data-g009-surface="hero-hub"',
        "inventory.html": 'data-g009-surface="backpack"',
        "shop.html": 'data-g009-surface="shop"',
    }
    for name, marker in expected.items():
        assert marker in read(name), name
    curriculum = read("curriculum.html")
    assert 'data-g009-secondary-surfaces="curriculum-map learning-progress daily-bounty mistakes rating-appraisal"' in curriculum
    assert 'data-g009-visual-authority="locked-12-surfaces"' in curriculum
    assert 'data-g009-surface="home"' in read("index.html")
    assert 'data-g009-global-nav-active-count="0"' in read("index.html")


def test_hero_hub_exposes_exactly_five_locked_section_hooks() -> None:
    source = read("hero.html")
    assert 'data-g009-hero-sections="5"' in source
    buttons = re.findall(
        r'<button[^>]+data-g009-hero-section="([^"]+)"[^>]*data-sfx="ui_tab"',
        source,
    )
    assert buttons == ["character", "equipment", "appearance", "companion", "honors"]
    for section in buttons:
        assert f'data-g009-hero-section="{section}"' in source


def test_shop_is_locked_to_browse_preview_only() -> None:
    source = read("shop.html")
    assert 'data-g009-shop-mode="browse-preview"' in source
    assert "const G009_SHOP_BROWSE_PREVIEW_ONLY = true;" in source
    purchase_fn = source[source.index("function shopPurchaseEnabled"):source.index("function shopPurchaseClosedCopy")]
    assert "if (G009_SHOP_BROWSE_PREVIEW_ONLY) return false;" in purchase_fn
    assert 'data-i18n="g009.shop.coming_soon"' in source
    assert 'data-i18n="g009.shop.browse_only"' in source
    assert 'body[data-g009-shop-mode="browse-preview"] .price' in source
    assert "display: none !important;" in source
    assert 'data-g009-shop-purchase-disabled="browse-preview" disabled' in source


def test_phase3b_shop_i18n_contains_locked_copy() -> None:
    source = read("i18n.js")
    assert "'g009.shop.coming_soon'" in source
    assert "'g009.shop.browse_only'" in source
    assert "Coming Soon" in source
    assert "即將開放" in source
