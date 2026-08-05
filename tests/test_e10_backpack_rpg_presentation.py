"""Acceptance contracts for the presentation-only E10 Backpack route.

The shared inventory controller remains the authority for item data and use
eligibility. These tests protect that boundary while checking the E10-only
shell, lifecycle return, responsive treatment, and dialog accessibility.
"""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = (ROOT / "inventory.html").read_text(encoding="utf-8")
REGISTRY = (ROOT / "js/e9/navigation_registry.js").read_text(encoding="utf-8")
CSS = (ROOT / "css/e10/backpack.css").read_text(encoding="utf-8")


def test_e10_route_marker_is_narrow_and_owned_by_the_existing_shell_contract():
    assert "new URLSearchParams(location.search).get('e10') === '1'" in INVENTORY
    assert "root.dataset.e10BackpackShell = 'true';" in INVENTORY
    assert "root.dataset.e10VisualSkin = 'immersive-rpg';" in INVENTORY
    assert "root.dataset.e10ArtKit = 'runtime-v1';" in INVENTORY
    assert "marker.name = 'go-odyssey-static-contract';" in INVENTORY
    assert "marker.content = 'e10-vs1f-integrated-world-map';" in INVENTORY
    assert "key: 'backpack', target: '/inventory' + '?e10=1'" in REGISTRY


def test_inventory_data_categories_counts_and_api_authority_are_unchanged():
    category_block = re.search(
        r"const BACKPACK_CATEGORIES = \[(.*?)\n\];", INVENTORY, re.DOTALL
    )
    assert category_block
    assert re.findall(r"key:'([^']+)'", category_block.group(1)) == [
        "all",
        "consumable",
        "training",
        "growth",
        "guard",
        "collection",
        "quest",
        "material",
        "chest",
        "exchange",
        "other",
    ]
    for contract in (
        "Object.entries(catalog.inventory || {}).filter(([, quantity]) => Number(quantity) > 0)",
        "quantity:Number(quantity)",
        "const petInventory = (petStatus.inventory || []).filter(item => Number(item.qty) > 0)",
        "quantity:Number(item.qty)",
        "backpackItems.push(...petInventory.filter(item => !backpackItems.some(existing => existing.key === item.key)))",
        "backpackItems.reduce((total, item) => total + item.quantity, 0)",
        "backpackItems.length.toLocaleString()",
        "backpackItems.filter(item => backpackCapability(item).kind === 'manual')",
        "backpackItems.filter(item => backpackCapability(item).kind === 'automatic')",
        "fetch('/api/shop/catalog'",
        "fetch('/api/auth/me'",
        "fetch('/api/pet/status'",
    ):
        assert contract in INVENTORY


def test_use_eligibility_and_non_manual_protection_remain_controller_owned():
    for contract in (
        "if (item.capability === 'spirit_managed')",
        "if (item.usable === 'activate') return { kind:'manual'",
        "if (item.usable === 'auto') return { kind:'automatic'",
        "if (item.usable === 'in_question') return { kind:'automatic'",
        "if (item.usable === 'instant') return { kind:'automatic'",
        "fetch('/api/shop/use'",
        "${capability.kind === 'manual' ?",
        "useButton.hidden = capability.kind !== 'manual';",
        "if (useButton) useButton.addEventListener('click'",
    ):
        assert contract in INVENTORY
    assert "fetch('/api/shop/buy'" not in INVENTORY


def test_return_action_uses_the_existing_world_map_lifecycle_target():
    assert INVENTORY.count("data-e10-return-map") == 2
    assert INVENTORY.count('data-e10-lifecycle-return="world-map"') == 2
    assert '<a class="e10-backpack-header-brand" href="/"' in INVENTORY
    assert '<a class="e10-backpack-return" href="/"' in INVENTORY
    assert "返回地圖" in INVENTORY


def test_e10_skips_global_navigation_while_legacy_keeps_the_shared_scripts():
    guard = "if (!window.__GO_E10_BACKPACK_MODE__) {"
    assert guard in INVENTORY
    guarded_scripts = INVENTORY[INVENTORY.index(guard) :]
    assert "'/mobile-nav.js?v=20260603mn'" in guarded_scripts
    assert "'/site-nav.js?v=20260625presence1'" in guarded_scripts
    assert "document.body.appendChild(script);" in guarded_scripts
    assert INVENTORY.index(guard) < INVENTORY.index("document.body.appendChild(script);")
    assert 'data-legacy-backpack-header' in INVENTORY
    assert 'class="cg-nav"' not in INVENTORY


def test_e10_has_one_page_shell_with_scoped_rpg_frame_and_existing_art_tokens():
    assert INVENTORY.count('<header id="inventory-page-header">') == 1
    assert INVENTORY.count('<div class="e10-backpack-header" data-e10-backpack-only hidden>') == 1
    assert '<link rel="stylesheet" href="/css/e10/backpack.css?' in INVENTORY
    assert 'html[data-e10-backpack-shell="true"]' in CSS
    assert 'html:not([data-e10-backpack-shell="true"])' not in CSS
    for token in (
        "--e10-ref-gold",
        "--e10-ref-wood",
        "--e10-ref-teal",
        "--e10-art-panel-frame",
        "--e10-art-title-plaque",
        "--e10-art-label-plaque",
        "--e10-art-corner",
        "--e10-art-backpack",
        "/assets/e10/ui/panels/zone-panel-frame.webp",
        "/assets/e10/ui/plaques/title-plaque.webp",
        "/assets/e10/ui/icons/backpack.webp",
    ):
        assert token in CSS
    assert "visibility: visible !important" in CSS
    assert "z-index: 1600" in CSS
    assert "z-index: 1700" in CSS


def test_rarity_status_cards_and_dialogs_are_e10_presentation_only():
    for contract in (
        "item.rarity || item.rarity_tier || item.quality || 'common'",
        "card.dataset.itemRarity = rarity.key;",
        "data-e10-backpack-status",
        "e10-backpack-rarity",
        'role="dialog" aria-modal="true"',
        "data-e10-dialog-dismiss",
        "data-e10-dialog-close",
        "aria-hidden=\"true\" hidden",
        "event.key === 'Escape'",
        "event.key !== 'Tab'",
        "trigger.focus()",
    ):
        assert contract in INVENTORY
    assert ".e10-backpack-dialog[hidden]" in CSS
    assert ".e10-backpack-dialog" in CSS
    assert ".e10-backpack-details" in CSS


def test_touch_keyboard_and_ipad_orientation_contract_is_explicit():
    for contract in (
        "min-height: 44px",
        "aria-controls', 'backpack-grid'",
        "event.key === 'ArrowRight'",
        "event.key === 'ArrowLeft'",
        "event.key === 'Home'",
        "event.key === 'End'",
        "@media (min-width: 768px) and (max-width: 1199px) and (orientation: landscape)",
        "@media (min-width: 768px) and (max-width: 1199px) and (orientation: portrait)",
        "@media (max-width: 767px)",
        "@media (prefers-reduced-motion: reduce)",
    ):
        assert contract in (INVENTORY + CSS)
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in CSS
    assert "grid-template-columns: 1fr" in CSS
