/*
 * A034 Shop Presentation V1
 *
 * Presentation-only adapter for the existing Shop payload and DOM.
 * It deliberately does not fetch, price, own, grant, equip, consume, or
 * infer commerce state.  The existing shop.html handlers remain the only
 * callers of Shop/Cosmetic/Premium mutations.
 */
(function shopPresentationV1(global) {
  'use strict';

  const VERSION = 'A034_SHOP_PRESENTATION_V1';
  const SECTION_BY_GRID = Object.freeze({
    'daily-grid': 'daily_rotation',
    'weekly-grid': 'weekly_shop',
    'monthly-grid': 'monthly_collection',
    'items-grid': 'tools',
  });

  function finiteNumber(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function firstString(...values) {
    return values.find(value => typeof value === 'string' && value.trim())?.trim() || '';
  }

  function registryFor(catalog, id) {
    const registry = Array.isArray(catalog?.shop_product_grant_registry)
      ? catalog.shop_product_grant_registry
      : [];
    return registry.find(entry => String(entry?.product_id || '') === id) || null;
  }

  function quantityFor(catalog, id) {
    const inventory = catalog?.inventory;
    if (!inventory || typeof inventory !== 'object') return null;
    const quantity = finiteNumber(inventory[id]);
    return quantity === null ? null : Math.max(0, quantity);
  }

  /*
   * Narrow an already-authoritative item record for object-first rendering.
   * A missing value remains null/empty; this adapter never manufactures stock,
   * discount, rarity, ownership, availability, or a purchase action.
   */
  function normalizeItem(raw, catalog = {}) {
    if (!raw || typeof raw !== 'object') return null;
    const itemId = firstString(raw.item_key, raw.key, raw.product_id, raw.id);
    if (!itemId) return null;

    const registry = registryFor(catalog, itemId);
    const quantity = quantityFor(catalog, itemId);
    const explicitOwned = typeof raw.owned === 'boolean' ? raw.owned : null;
    const owned = explicitOwned === null && quantity !== null ? quantity > 0 : explicitOwned;
    const explicitAvailable = typeof raw.available === 'boolean'
      ? raw.available
      : typeof raw.purchase_available === 'boolean'
        ? raw.purchase_available
        : null;

    return Object.freeze({
      item_id: itemId,
      display_name: firstString(raw.display_name, raw.name, raw.name_en, itemId),
      display_name_en: firstString(raw.display_name_en, raw.name_en, raw.name, itemId),
      category: firstString(raw.category, registry?.category),
      image: firstString(
        raw.image,
        raw.asset,
        raw.current_asset,
        raw.preview_asset?.asset,
        registry?.current_asset,
      ),
      server_price: finiteNumber(raw.price),
      owned,
      owned_quantity: quantity,
      available: explicitAvailable,
      legal_action: firstString(raw.legal_action, raw.action),
      art_status: firstString(raw.art_status, registry?.art_status),
    });
  }

  /*
   * This is intentionally a detached, immutable presentation snapshot.
   * It is useful for focused contract tests and future surface adapters, but
   * it is not a replacement for any backend or ownership authority.
   */
  function normalizeCatalog(payload) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return Object.freeze({
        valid: false,
        coins: null,
        sections: Object.freeze({}),
        items: Object.freeze([]),
      });
    }

    const allItems = Array.isArray(payload.items) ? payload.items : [];
    const sectionItems = {};
    Object.entries(SECTION_BY_GRID).forEach(([key, section]) => {
      const sourceKey = section === 'daily_rotation'
        ? 'daily_items'
        : section === 'weekly_shop'
          ? 'weekly_items'
          : section === 'monthly_collection'
            ? 'monthly_items'
            : 'items';
      const source = Array.isArray(payload[sourceKey]) ? payload[sourceKey] : [];
      sectionItems[section] = Object.freeze(
        source.map(item => normalizeItem(item, payload)).filter(Boolean),
      );
    });

    const normalized = {
      valid: true,
      coins: finiteNumber(payload.coins),
      earned_today: finiteNumber(payload.earned_today),
      daily_cap: finiteNumber(payload.daily_cap),
      items: Object.freeze(allItems.map(item => normalizeItem(item, payload)).filter(Boolean)),
      sections: Object.freeze(sectionItems),
    };
    return Object.freeze(normalized);
  }

  function markCard(card) {
    if (!card || card.nodeType !== 1) return;
    card.classList.add('a034-item-card');
    const image = card.querySelector('img');
    card.dataset.a034Art = image ? 'canonical' : 'fallback';
    const buyButton = card.querySelector('[data-cosmetic-purchase], .card-foot .btn:not(.secondary)');
    const previewButton = card.querySelector('[data-cosmetic-preview], [data-cosmetic-visual-preview]');
    const equipButton = card.querySelector('[data-cosmetic-equip]');
    if (buyButton) buyButton.dataset.a034Action = 'purchase';
    if (previewButton) previewButton.dataset.a034Action = 'preview';
    if (equipButton) equipButton.dataset.a034Action = 'equip';
  }

  function decorate(root = document) {
    const body = root?.body || document.body;
    if (body) body.classList.add('a034-shop');

    Object.entries(SECTION_BY_GRID).forEach(([gridId, sectionName]) => {
      const grid = root.getElementById?.(gridId) || root.querySelector?.('#' + gridId);
      if (!grid) return;
      grid.dataset.a034Grid = sectionName;
      const section = grid.closest('section');
      if (section) section.dataset.a034Section = sectionName;
      grid.querySelectorAll('.item-card').forEach(markCard);
    });

    root.querySelectorAll?.('.cosmetic-commerce-panel').forEach(section => {
      section.dataset.a034Section = 'cosmetic_commerce';
    });
    root.querySelectorAll?.('.premium-v1-panel').forEach(section => {
      section.dataset.a034Section = 'premium_entitlement';
    });

    const gacha = root.getElementById?.('gacha-title')?.closest('section')
      || root.querySelector?.('#gacha-title')?.closest('section');
    if (gacha) {
      gacha.dataset.a034Section = 'legacy_gacha';
      gacha.dataset.a034Legacy = 'yes';
      gacha.classList.add('a034-legacy-gacha');
    }

    root.querySelectorAll?.('.cosmetic-card').forEach(card => {
      card.classList.add('a034-cosmetic-card');
    });
  }

  function init() {
    decorate(document);
    if (typeof MutationObserver !== 'function' || !document.body) return;
    const observer = new MutationObserver(() => decorate(document));
    observer.observe(document.body, { childList: true, subtree: true });
  }

  const api = Object.freeze({
    VERSION,
    SECTION_BY_GRID,
    normalizeItem,
    normalizeCatalog,
    decorate,
  });
  global.ShopPresentationV1 = api;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})(window);
