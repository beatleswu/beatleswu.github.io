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
    const baseAsset = opts.baseAsset || character?.base || '';
    const baseCharacter = character
      ? { ...character, base: baseAsset }
      : (baseAsset ? {
          base: baseAsset,
          hair_front_mask: opts.maskAsset || '',
        } : null);
    const fallback = opts.fallbackElement || null;
    stage.innerHTML = '';
    stage.dataset.character = characterKey || '';
    stage.dataset.frame = registry.player_frame.id;
    delete stage.dataset.assetError;

    if (!baseCharacter) {
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
    appendLayer(stage, baseCharacter.base, 'character-base', `${characterKey} character base`);
    appendEntries('TORSO_ARMOR');
    appendEntries('FRONT_BODY');
    appendEntries('FRONT_ACCESSORY');
    appendEntries('HEAD_FACE');

    if (entries.some(item => (item.mask_requirements || []).includes('HAIR_FRONT_MASK'))) {
      const maskAsset = baseCharacter.hair_front_mask || opts.maskAsset || '';
      if (maskAsset) appendLayer(stage, maskAsset, 'character-hair-front-mask layer-hair-front-mask', 'reusable character hair mask');
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

  global.GoOdysseyWearableRenderer = {
    loadRegistry,
    normalizeEquipped,
    render,
    renderSafe,
    registryUrl: REGISTRY_URL,
  };
})(window);
