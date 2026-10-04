"""Producer-side contract for the explicit E10 Backpack handoff."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
REGISTRY = (ROOT / "js/e9/navigation_registry.js").read_text(encoding="utf-8")
SITE_NAV = (ROOT / "site-nav.js").read_text(encoding="utf-8")


def test_all_e10_backpack_producers_share_the_existing_handoff_helper():
    from tests.test_e10_ui_nav_guild_and_single_map_return import _canonical_navigation
    nav = _canonical_navigation()
    assert next(x for x in nav['items'] if x['key']=='backpack')['target']=='/inventory?e10=1'
    assert "target.searchParams.set('e10', '1');" in INDEX
    assert "target.searchParams.delete('e10');" in INDEX
    assert "syncE10BackpackEntryLinks()" in INDEX

    # PATH-B assertion retention, Owner packet case 28.
    assert '[data-e10-backpack-entry], [data-e10-nav-key="backpack"]' in INDEX
    # PATH-B assertion retention, Owner packet case 29.
    assert "component !== 'left_nav'" in INDEX
    # PATH-B assertion retention, Owner packet case 30.
    assert "component !== 'top_hud'" in INDEX
    # PATH-B assertion retention, Owner packet case 31.
    assert "component !== 'bottom_dock'" in INDEX
    # PATH-B assertion retention, Owner packet case 32.
    assert 'Promise.resolve().then(() => syncE10BackpackEntryLinks());' in INDEX


def test_generic_and_legacy_navigation_remain_unmarked():
    from tests.test_e10_ui_nav_guild_and_single_map_return import _canonical_navigation
    nav = _canonical_navigation()
    assert len([x for x in nav['items'] if x['key']=='backpack'])==1
    assert "const e10Context = isE10AdventureShellOwner();" in INDEX
    assert "if (e10Context) target.searchParams.set('e10', '1');" in INDEX
    assert "else target.searchParams.delete('e10');" in INDEX
    assert "href: '/inventory'" in SITE_NAV
