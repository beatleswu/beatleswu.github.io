from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_locked_shell_and_learning_hub_have_exact_route_counts() -> None:
    shell = read("site-nav.js")
    nav_block = shell[shell.index("const NAV_ITEMS"):shell.index("const ICONS")]
    global_routes = re.findall(r"\{ href: '([^']+)',\s*key: '([^']+)'", nav_block)
    assert global_routes == [
        ("/curriculum", "learning_hub"),
        ("/play", "arena"),
        ("/community", "tavern"),
        ("/hero", "hero_hub"),
        ("/inventory", "backpack"),
        ("/shop", "shop"),
        ("/upgrade", "premium"),
    ]
    learning_block = shell[shell.index("const LEARNING_SECONDARY_ITEMS"):shell.index("const LEARNING_SURFACES")]
    learning_routes = re.findall(r"\{ href: '([^']+)',\s*key: '([^']+)'", learning_block)
    assert learning_routes == [
        ("/curriculum", "curriculum_map"),
        ("/stats", "learning_progress"),
        ("/daily-challenge", "daily_bounty"),
        ("/mistakes", "mistakes"),
        ("/rating_test", "rating_appraisal"),
    ]
    assert 'data-g009-global-nav="7"' in shell
    assert 'nav.dataset.g009LearningSecondary = \'5\';' in shell


def test_locked_surface_markers_and_copy_authority_are_connected() -> None:
    for name in (
        "curriculum.html", "stats.html", "daily_challenge.html", "mistakes.html",
        "rating_test.html", "community.html", "shop.html", "inventory.html", "hero.html", "index.html",
    ):
        assert 'data-g009-visual-authority="locked-12-surfaces"' in read(name), name
    i18n = read("i18n.js")
    assert "'g009.page.tavern':      { en: 'Tavern',       zh: '酒館' }" in i18n
    assert "'stats.title':           { en: 'Learning Progress',               zh: '學習進度' }" in i18n
    assert "'backpack.goShop': { en: 'View Shop', zh: '查看商店' }" in i18n
    assert "'shop.r1.consumables.kicker': { en: 'CONSUMABLES · PREVIEW', zh: '消耗品 · 預覽' }" in i18n
    shell = read("site-nav.js")
    assert 'body[data-g009-surface="learning-progress"] .stats-col-weak' in shell
    assert 'body[data-g009-surface="learning-progress"] .stat-delta' in shell
    assert 'data-g009-progress-presentation="player-journal-not-saas-dashboard"' in read("stats.html")


def test_shop_is_visible_catalog_preview_only() -> None:
    source = read("shop.html")
    assert 'data-g009-shop-mode="browse-preview"' in source
    assert 'data-g009-shop-forbidden="collection-progress" hidden' in source
    assert "const G009_SHOP_BROWSE_PREVIEW_ONLY = true;" in source
    assert "function browseOnlyDescription(value)" in source
    assert 'replaceAll("購買即獲得", "內含")' in source
    assert "isEn() ? 'Contains' : '內含'" in source
    assert 'data-g009-shop-preview-status="coming-soon"' in source
    assert "const browseOnly = G009_SHOP_BROWSE_PREVIEW_ONLY;" in source
    assert "${browseOnly ? '' : shopItemPurchaseUseCopy" in source
    assert '瀏覽伺服器目錄；購買功能已停用。' in source


def test_backpack_keeps_coin_projection_but_hides_write_and_use_actions() -> None:
    source = read("inventory.html")
    assert 'data-g009-backpack-coin-balance="authoritative"' in source
    assert 'id="backpack-coin-balance"' in source
    assert "const G009_BACKPACK_READ_ONLY = true;" in source
    assert 'data-g009-equipment-write="false" hidden' in source
    assert "if (G009_BACKPACK_READ_ONLY && !E10_BACKPACK_MODE)" in source
    assert "const coins = Number(catalog?.coins);" in source
    assert "E10_BACKPACK_MODE && capability.kind === 'manual'" in source
    assert 'data-g009-equipment-forbidden="comparison" hidden' in source


def test_tavern_does_not_expose_forbidden_social_or_messages_surface() -> None:
    source = read("community.html")
    assert 'data-g009-tavern-forbidden-surface="social-feed" hidden' in source
    assert 'data-g009-tavern-forbidden-surface="unbacked-notice" hidden' in source
    assert "/messages?u=" not in source
    assert 'data-g009-tavern-heading' in source


def test_world_map_and_hero_contracts_remain_present_without_new_surface() -> None:
    world_map = read("index.html")
    hero = read("hero.html")
    assert 'data-g009-global-nav-active-count="0"' in world_map
    assert '領主挑戰' in world_map
    assert '領主試煉' not in world_map
    assert 'data-g009-hero-sections="5"' in hero
    assert re.findall(r'data-g009-hero-section="([^"]+)"', hero)[:5] == [
        "character", "equipment", "appearance", "companion", "honors"
    ]
