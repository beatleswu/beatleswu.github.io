/* Go Odyssey Wave 2 P3 wearable presentation renderer.
 *
 * This module is deliberately presentation-only.  It consumes an
 * authoritative equipped projection supplied by the server; it never writes
 * inventory, effects, character selection, or combat state.
 */
(function (global) {
  'use strict';

  const REGISTRY_URL = '/assets/hero/equipment/wearables/wearable_registry.json';
  let registryPromise = null;

  function ensureStyles() {
    if (document.getElementById('go-odyssey-p3-wearable-styles')) return;
    const style = document.createElement('style');
    style.id = 'go-odyssey-p3-wearable-styles';
    style.textContent = `
      .rpg-wearable-host { position:relative; overflow:hidden; }
      .rpg-wearable-stage { position:absolute; inset:0; overflow:visible; pointer-events:none; }
      .rpg-wearable-stage img.rpg-wearable-layer {
        position:absolute; inset:0; width:100%; height:100%;
        object-fit:contain; object-position:center bottom;
        display:block; pointer-events:none;
      }
      .rpg-wearable-stage[data-supported="false"] { display:none; }
      .rpg-cosmetic-reference {
        display:flex; flex-wrap:wrap; justify-content:center; gap:6px;
        width:100%; margin-top:6px;
      }
      .rpg-cosmetic-reference-card {
        display:inline-flex; align-items:center; gap:5px; min-width:0;
        padding:4px 6px; border:1px solid rgba(255,255,255,.18);
        border-radius:8px; background:rgba(255,255,255,.08);
        color:inherit; font:600 9px/1.2 system-ui,sans-serif;
      }
      .rpg-cosmetic-reference-card img {
        display:block; flex:0 0 auto; object-fit:contain;
      }
      .rpg-cosmetic-reference-card img.rpg-cosmetic-reference-fullbody {
        width:34px; height:46px;
      }
      .rpg-cosmetic-reference-card img.rpg-cosmetic-reference-icon {
        width:28px; height:28px;
      }
      .rpg-cosmetic-reference-card[data-visual-generation="LEGACY_ICON"] {
        border-style:dashed;
      }
      .rpg-cosmetic-reference-card span { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    `;
    document.head.appendChild(style);
  }

  function loadRegistry() {
    if (!registryPromise) {
      registryPromise = fetch(REGISTRY_URL, {
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { Accept: 'application/json' },
      }).then(response => {
        if (!response.ok) throw new Error(`wearable registry HTTP ${response.status}`);
        return response.json();
      }).then(registry => {
        if (!registry || registry.player_frame?.id !== 'PLAYER_FRAME_A_STANDARD_CHIBI') {
          throw new Error('unsupported wearable frame registry');
        }
        return registry;
      });
    }
    return registryPromise;
  }

  function equipmentId(value) {
    if (typeof value === 'string') return value;
    if (!value || value.equipped === false) return '';
    return value.equipment_id || value.item_id || value.id || '';
  }

  function normalizeEquipped(equipped, registry) {
    const bySlot = new Map();
    (Array.isArray(equipped) ? equipped : []).forEach(value => {
      const id = equipmentId(value);
      const item = registry.equipment?.[id];
      if (!item || item.wearable_visibility === 'INVENTORY_ONLY' || !item.asset) return;
      if (bySlot.has(item.slot)) return;
      bySlot.set(item.slot, id);
    });
    return [...bySlot.values()];
  }

  function normalizeCosmeticProjection(equipped) {
    const result = [];
    (Array.isArray(equipped) ? equipped : []).forEach(value => {
      if (!value || value.owned !== true || value.equipped !== true) return;
      const presentation = value.presentation || {};
      const id = value.id || value.item_id || '';
      const asset = presentation.asset || '';
      if (!id || presentation.selected !== true || presentation.visible !== true) return;
      if (presentation.hero_projection_allowed === false) return;
      if (presentation.asset_id !== id || presentation.combat_authority !== 'NO') return;
      if (!asset.startsWith('/assets/hero/items/') || asset.includes('..')) return;
      result.push({ item: value, id, presentation });
    });
    return result;
  }

  function appendLayer(stage, source, className, alt) {
    const image = document.createElement('img');
    image.className = `rpg-wearable-layer ${className}`;
    image.src = source;
    image.alt = alt || '';
    image.decoding = 'async';
    image.draggable = false;
    image.addEventListener('error', () => {
      image.hidden = true;
      stage.dataset.assetError = source;
    }, { once: true });
    stage.appendChild(image);
    return image;
  }

  function setFallback(fallback, visible) {
    if (!fallback) return;
    fallback.hidden = !visible;
  }

  async function render(stage, characterKey, equipped, options) {
    ensureStyles();
    if (!stage) return { supported: false, reason: 'missing_stage' };
    const opts = options || {};
    const registry = await loadRegistry();
    const character = registry.characters?.[characterKey];
    const fallback = opts.fallbackElement || null;
    stage.innerHTML = '';
    stage.dataset.character = characterKey || '';
    stage.dataset.frame = registry.player_frame.id;
    delete stage.dataset.assetError;

    if (!character) {
      stage.hidden = true;
      stage.dataset.supported = 'false';
      setFallback(fallback, true);
      return { supported: false, reason: 'unsupported_character', character: characterKey };
    }

    stage.hidden = false;
    stage.dataset.supported = 'true';
    setFallback(fallback, false);
    const selectedIds = normalizeEquipped(equipped, registry);
    const selected = new Set(selectedIds);
    const entries = selectedIds.map(id => registry.equipment[id]).filter(Boolean);
    const appendEntries = layer => entries
      .filter(item => item.layer === layer)
      .forEach(item => appendLayer(stage, item.asset, `equipment-${item.id} layer-${layer.toLowerCase()}`, item.canonical_identity));

    appendEntries('BACK_WEAPON');
    appendEntries('BACK_BODY');
    appendLayer(stage, character.base, 'character-base', `${characterKey} character base`);
    appendEntries('TORSO_ARMOR');
    appendEntries('FRONT_BODY');
    appendEntries('FRONT_ACCESSORY');
    appendEntries('HEAD_FACE');

    if (entries.some(item => (item.mask_requirements || []).includes('HAIR_FRONT_MASK'))) {
      appendLayer(stage, character.hair_front_mask, 'character-hair-front-mask layer-hair-front-mask', 'reusable character hair mask');
    }
    stage.dataset.equippedIds = selectedIds.join(',');
    stage.dataset.authority = 'server_equipped_projection';
    stage.dataset.gameplayAuthority = 'none';
    return {
      supported: true,
      character: characterKey,
      equipped: selectedIds,
      frame: registry.player_frame.id,
    };
  }

  function renderSafe(stage, characterKey, equipped, options) {
    return render(stage, characterKey, equipped, options).catch(error => {
      if (stage) {
        stage.innerHTML = '';
        stage.hidden = true;
        stage.dataset.supported = 'false';
        stage.dataset.renderError = error.message || 'wearable_render_failed';
      }
      if (options?.fallbackElement) setFallback(options.fallbackElement, true);
      return { supported: false, reason: 'render_error', error: error.message };
    });
  }

  function appendCosmeticReference(stage, entry) {
    const { item, id, presentation } = entry;
    const card = document.createElement('div');
    const fullBody = presentation.mode === 'FULL_BODY_COSMETIC_REFERENCE';
    card.className = 'rpg-cosmetic-reference-card';
    card.dataset.itemId = id;
    card.dataset.presentationMode = presentation.mode || 'CATALOG_ICON';
    card.dataset.visualGeneration = presentation.visual_generation || (
      fullBody ? 'WAVE2_FULLBODY' : 'LEGACY_ICON'
    );
    card.dataset.gameplayAuthority = 'none';

    const image = document.createElement('img');
    image.className = fullBody
      ? 'rpg-cosmetic-reference-fullbody'
      : 'rpg-cosmetic-reference-icon';
    image.src = presentation.asset;
    image.alt = item.name || id;
    image.decoding = 'async';
    image.draggable = false;
    image.addEventListener('error', () => {
      image.hidden = true;
      card.dataset.assetError = presentation.asset;
    }, { once: true });
    card.appendChild(image);

    const label = document.createElement('span');
    label.textContent = item.name || id;
    card.appendChild(label);
    stage.appendChild(card);
  }

  function renderCosmetic(stage, equipped) {
    ensureStyles();
    if (!stage) return { supported: false, reason: 'missing_stage' };
    stage.innerHTML = '';
    const selected = normalizeCosmeticProjection(equipped);
    if (!selected.length) {
      stage.hidden = true;
      stage.dataset.supported = 'false';
      stage.dataset.authority = 'server_wardrobe_projection';
      stage.dataset.gameplayAuthority = 'none';
      return { supported: false, reason: 'no_server_selected_cosmetic', items: [] };
    }
    selected.forEach(entry => appendCosmeticReference(stage, entry));
    stage.hidden = false;
    stage.dataset.supported = 'true';
    stage.dataset.authority = 'server_wardrobe_projection';
    stage.dataset.gameplayAuthority = 'none';
    stage.dataset.equippedIds = selected.map(entry => entry.id).join(',');
    return {
      supported: true,
      items: selected.map(entry => entry.id),
      fullBodyItems: selected
        .filter(entry => entry.presentation.mode === 'FULL_BODY_COSMETIC_REFERENCE')
        .map(entry => entry.id),
    };
  }

  function renderCosmeticSafe(stage, equipped) {
    try {
      return Promise.resolve(renderCosmetic(stage, equipped));
    } catch (error) {
      if (stage) {
        stage.innerHTML = '';
        stage.hidden = true;
        stage.dataset.supported = 'false';
        stage.dataset.renderError = error.message || 'cosmetic_render_failed';
      }
      return Promise.resolve({ supported: false, reason: 'render_error' });
    }
  }

  global.GoOdysseyWearableRenderer = {
    loadRegistry,
    normalizeEquipped,
    normalizeCosmeticProjection,
    render,
    renderSafe,
    renderCosmetic,
    renderCosmeticSafe,
    registryUrl: REGISTRY_URL,
  };
})(window);
