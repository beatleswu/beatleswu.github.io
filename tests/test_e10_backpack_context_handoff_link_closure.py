"""Producer-side contract for the explicit E10 Backpack handoff."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
REGISTRY = (ROOT / "js/e9/navigation_registry.js").read_text(encoding="utf-8")
SITE_NAV = (ROOT / "site-nav.js").read_text(encoding="utf-8")


def test_all_e10_backpack_producers_share_the_existing_handoff_helper():
    assert "[data-e10-backpack-entry], [data-e10-nav-key=\"backpack\"]" in INDEX
    assert "target.searchParams.set('e10', '1');" in INDEX
    assert "target.searchParams.delete('e10');" in INDEX
    assert "component !== 'left_nav'" in INDEX
    assert "component !== 'top_hud'" in INDEX
    assert "component !== 'bottom_dock'" in INDEX
    assert "Promise.resolve().then(() => syncE10BackpackEntryLinks());" in INDEX
    assert "key: 'backpack', target: '/inventory' + '?e10=1'" in REGISTRY


def test_generic_and_legacy_navigation_remain_unmarked():
    assert "{ href: '/inventory',   key: 'backpack'" in SITE_NAV
    assert "const e10Context = isE10AdventureShellOwner();" in INDEX
    assert "if (e10Context) target.searchParams.set('e10', '1');" in INDEX
    assert "else target.searchParams.delete('e10');" in INDEX
