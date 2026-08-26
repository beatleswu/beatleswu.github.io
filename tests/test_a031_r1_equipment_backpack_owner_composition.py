"""A031-R1 structural contracts for the Owner-approved RPG composition."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = (ROOT / "inventory.html").read_text(encoding="utf-8")
CSS = (ROOT / "css/e10/backpack.css").read_text(encoding="utf-8")


def test_owner_scene_markers_preserve_existing_authority_surfaces():
    for marker in (
        'data-a031-context-rail',
        'data-a031-scene-shell',
        'data-a031-equipment-window-filters',
        'data-a031-equipment-window',
        'data-a031-backpack-window',
        'data-a031-backpack-filters',
        'data-a031-equipment-board',
        'id="a031-loadout-grid"',
        'id="functional-equipment-detail"',
        'id="functional-equipment-grid"',
        'id="backpack-grid"',
    ):
        assert marker in INVENTORY

    for authority_marker in (
        "fetch('/api/player/inventory'",
        "fetch('/api/player/inventory/equip'",
        "fetch('/api/shop/catalog'",
        "fetch('/api/pet/status'",
        "player_inventory",
        "item.item_id === 'xp_amulet'",
        "item.item_id === 'go_stone_black'",
    ):
        assert authority_marker in INVENTORY


def test_primary_rpg_scene_uses_object_first_compact_windows():
    assert "grid-template-columns: minmax(300px, .98fr) minmax(350px, 1.08fr) minmax(390px, 1.18fr)" in CSS
    assert ".functional-detail-icon" in CSS
    assert "height: 232px" in CSS
    assert "display: flex !important" in CSS
    assert "overflow-x: auto" in CSS
    assert "functional-equipment-card-effects,\nhtml[data-e10-backpack-shell=\"true\"] .a031-functional-collection .functional-equipment-badge" in CSS
    assert "backpack-card-desc { display: none; }" in CSS
    assert "background:\n    linear-gradient(145deg, rgba(23, 54, 83, .78)" in CSS


def test_responsive_order_keeps_three_slots_and_reaches_backpack_without_catalog_stack():
    assert "@media (max-width: 767px)" in CSS
    assert "grid-template-columns: 1fr !important" in CSS
    assert ".a031-loadout-grid { gap: 6px; }" in CSS
    assert ".a031-functional-collection .functional-equipment-card { flex-basis: 166px" in CSS
    assert ".backpack-shell .backpack-card { flex-basis: 166px" in CSS
    assert "@media (prefers-reduced-motion: reduce)" in CSS


def test_item_journal_uses_locale_specific_dom_copy():
    assert 'href="/item-journal"' in INVENTORY
    assert 'data-a031-zh="物品圖鑑"' in INVENTORY
    assert 'data-a031-en="Item Journal"' in INVENTORY
    assert "物品圖鑑 / Item Journal" not in INVENTORY
