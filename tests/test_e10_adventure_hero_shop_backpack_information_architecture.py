from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
HERO = (ROOT / "hero.html").read_text(encoding="utf-8")
INVENTORY = (ROOT / "inventory.html").read_text(encoding="utf-8")
SHOP = (ROOT / "shop.html").read_text(encoding="utf-8")
REGISTRY = (ROOT / "js/e9/navigation_registry.js").read_text(encoding="utf-8")
SITE_NAV = (ROOT / "site-nav.js").read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_hero_has_five_canonical_accessible_domains_and_useful_default_landing():
    assert "const ALL_TABS = ['hero','equipment','appearance','pet','honors'];" in HERO
    assert 'class="main-tabs" role="tablist"' in HERO
    for tab, domain in (
        ("hero", "character"),
        ("equipment", "equipment"),
        ("appearance", "appearance"),
        ("pet", "spirit"),
        ("honors", "honors"),
    ):
        assert f'id="hero-tab-{tab}"' in HERO
        assert f'aria-controls="tab-{tab}"' in HERO
        assert f'id="tab-{tab}"' in HERO
        assert f'data-hero-domain="{domain}"' in HERO
    for summary_id in (
        "hero-overview-name",
        "hero-overview-rank",
        "hero-overview-archetype",
        "hero-overview-premium",
        "hero-overview-title",
        "hero-overview-spirit",
        "hero-overview-equipment",
        "hero-overview-xp",
        "hero-overview-bonus",
    ):
        assert f'id="{summary_id}"' in HERO
    for target in ("equipment", "appearance", "pet", "honors"):
        assert f'data-hero-target-tab="{target}"' in HERO
    assert '<a class="hero-quick-link" href="/inventory"' in HERO
    assert "renderHeroOverview();" in HERO


def test_hero_tab_state_uses_one_canonical_history_contract():
    assert "const LEGACY_TAB_ALIASES = { gear:'equipment', class:'hero', badges:'honors' };" in HERO
    assert "history.pushState({ heroTab: canonical }" in HERO
    assert "el.hidden = t !== canonical" in HERO
    assert "b.setAttribute('aria-selected', String(active))" in HERO
    assert "b.tabIndex = active ? 0 : -1" in HERO
    assert "['ArrowRight','ArrowDown','ArrowLeft','ArrowUp','Home','End']" in HERO
    assert "tabs[next].focus()" in HERO
    assert "window.addEventListener('popstate'" in HERO
    assert 'id="tab-gear"' not in HERO
    assert 'id="tab-class"' not in HERO
    assert 'id="tab-badges"' not in HERO


def test_equipment_appearance_spirit_and_honors_have_disjoint_surface_ownership():
    equipment = _between(HERO, 'id="tab-equipment"', '</div><!-- /tab-equipment -->')
    appearance = _between(HERO, 'id="tab-appearance"', '</div><!-- /tab-appearance -->')
    spirit = _between(HERO, 'id="tab-pet"', 'id="tab-honors"')
    honors = _between(HERO, 'id="tab-honors"', 'id="tab-equipment"')

    for required in (
        "combat-armor-grid",
        "combat-weapon-grid",
        "combat-offhand-grid",
        "combat-hat-grid",
        "combat-aura-grid",
        "combat-acc-grid",
    ):
        assert required in equipment
    for forbidden in ("stone-skin-grid", "board-skin-grid", "slot-title", "slot-pet"):
        assert forbidden not in equipment

    for required in (
        "combat-character-grid",
        "stone-skin-grid",
        "board-skin-grid",
        "slot-outfit",
        "slot-hat",
        "slot-back",
        "slot-accessory",
        "slot-aura",
    ):
        assert required in appearance
    assert "slot-title" not in appearance
    assert "slot-pet" not in appearance

    assert "pet-companion-root" in spirit
    assert "slot-pet" in spirit
    assert "hero-badge-grid" in honors
    assert "slot-title" in honors


def test_item_projection_contract_preserves_source_identity_without_inventory_duplication():
    assert "data-source-item-id" in HERO
    assert "'spirit_appearance_projection' : 'appearance_projection'" in HERO
    assert 'data-item-projection="honor_projection"' in HERO
    assert "data-item-domain=\"${projection}\"" in HERO
    assert "slot === 'character' ? 'appearance' : 'equipment'" in HERO
    assert "item.type === 'pet' ? 'spirit' : 'appearance'" in HERO
    assert "wardrobeHasGameplayEffect" in HERO
    assert 'id="wardrobe-effect-equipment-grid"' in HERO
    assert 'data-item-domain="equipment" data-item-projection="equipment_projection"' in HERO
    assert "source_item_id || `wardrobe:${item?.id || 'unknown'}`" in HERO
    assert "sourceItems.filter(i => slotType === 'pet' || slotType === 'title' || !wardrobeHasGameplayEffect(i))" in HERO
    assert "combat-item-effect" in HERO
    assert "data-equip-action" in HERO
    assert "disabled aria-disabled=\"true\"" in HERO


def test_backpack_is_an_enabled_independent_destination_with_exclusive_navigation():
    assert "@app.route('/inventory')" in APP
    assert "def inventory_page(): return _serve_live_static_or_baked('inventory.html')" in APP
    assert "key: 'backpack', target: '/inventory'" in REGISTRY
    assert "key: 'backpack', target: '/inventory'" in REGISTRY and "category: 'primary'" in REGISTRY
    assert "href: '/inventory'" in SITE_NAV
    assert "key: 'backpack'" in SITE_NAV
    assert 'data-backpack-destination' in INVENTORY
    assert 'data-authoritative-backpack-grid' in INVENTORY
    assert '<a href="/inventory"    class="nav-link active" aria-current="page"' in INVENTORY


def test_backpack_uses_real_catalog_inventory_and_truthful_capabilities():
    assert "fetch('/api/shop/catalog'" in INVENTORY
    assert "fetch('/api/pet/status'" in INVENTORY
    assert "catalog.inventory || {}" in INVENTORY
    assert "catalog.items || []" in INVENTORY
    assert "quantity:Number(quantity)" in INVENTORY
    assert "item.usable === 'activate'" in INVENTORY
    assert "item.usable === 'auto'" in INVENTORY
    assert "item.usable === 'in_question'" in INVENTORY
    assert "item.usable === 'instant'" in INVENTORY
    assert "fetch('/api/shop/use'" in INVENTORY
    assert "capability.kind === 'manual'" in INVENTORY
    assert "card.dataset.sourceItemId = item.key" in INVENTORY
    assert "card.dataset.itemCapability = capability.kind" in INVENTORY
    assert "card.dataset.itemCategory = backpackCategory(item).key" in INVENTORY
    assert "item.category === 'pet' || item.category === 'material'" in INVENTORY
    assert "inventory_source:'pet_inventory'" in INVENTORY
    assert "item.capability === 'spirit_managed'" in INVENTORY
    assert "setBackpackStatus('loading'" in INVENTORY
    assert "setBackpackStatus('error'" in INVENTORY
    assert 'class="backpack-empty"' in INVENTORY
    assert "price" not in _between(INVENTORY, "function renderBackpackGrid()", "async function useBackpackItem")
    assert "/api/shop/buy" not in INVENTORY


def test_shop_does_not_render_the_authoritative_backpack_inventory_grid():
    assert 'data-authoritative-backpack-grid' not in SHOP
    assert 'id="mine-grid"' not in SHOP
    assert "function renderMine" not in SHOP
    assert "renderMine(res)" not in SHOP
    assert "function useItem" not in SHOP
    assert 'id="mine-title"' not in SHOP
    assert "shop.mine.title" not in SHOP


def test_shop_purchase_confirmation_is_compact_and_navigates_to_backpack():
    assert 'id="purchase-confirmation"' in SHOP
    assert 'id="purchase-confirmation-copy"' in SHOP
    assert 'id="purchase-confirmation-backpack" href="/inventory"' in SHOP
    assert "await showPurchaseConfirmation(res, key)" in SHOP
    assert "async function resolvePurchaseGrants" in SHOP
    assert "foodGrants.forEach" in SHOP
    assert "await loadCatalog();" in SHOP
    assert "catalog?.inventory?.[grant.item_key || purchasedKey]" in SHOP
    assert "grants.length === 1 ? `/inventory?focus=${encodeURIComponent(grants[0].key)}` : '/inventory'" in SHOP
    assert "destination.href = '/hero?tab=pet'" not in SHOP
    assert "purchase-confirmation" not in INVENTORY


def test_backpack_and_shop_roles_share_item_identity_not_ownership_state():
    assert "item.key" in SHOP
    assert "item.key" in INVENTORY
    assert "catalog.inventory" in INVENTORY
    assert "catalog?.inventory?.[grant.item_key || purchasedKey]" in SHOP
    assert "inventory_source:'shop_inventory'" in INVENTORY
    assert "inventory_source:'pet_inventory'" in INVENTORY
    assert "let shop_inventory" not in INVENTORY
    assert "let shop_inventory" not in SHOP
    assert "mock" not in INVENTORY.lower()


def test_hero_and_backpack_have_touch_safe_responsive_layout_contracts():
    assert "min-height: 44px" in HERO
    assert "overflow-x: auto" in HERO
    assert "grid-template-columns: 1fr" in HERO
    assert "position: static" in HERO
    assert "env(safe-area-inset-bottom)" in INVENTORY
    assert "overflow-x: hidden" in INVENTORY
    assert "grid-template-columns:1fr" in INVENTORY
