/* Go Odyssey Wave 2 P3 wearable presentation renderer.
 *
 * This module is deliberately presentation-only.  It consumes an
 * authoritative equipped projection supplied by the server; it never writes
 * inventory, effects, character selection, or combat state.
 */
(function (global) {
  'use strict';

  const REGISTRY_URL = '/assets/hero/equipment/wearables/wearable_registry.json';
  // Owner-approved transparent replacements are now integrated for the two
  // formerly blocked items. Keep this explicit list as the presentation
  // fail-closed seam for any future item that is not yet approved; it is not
  // an authority source and never changes the server-owned equipment state.
  const ART_REPLACEMENT_REQUIRED_IDS = Object.freeze([]);
  const ART_REPLACEMENT_REQUIRED = new Set(ART_REPLACEMENT_REQUIRED_IDS);
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
      if (!item
        || item.wearable_visibility === 'INVENTORY_ONLY'
        || ART_REPLACEMENT_REQUIRED.has(id)
        || !item.asset) return;
      if (bySlot.has(item.slot)) return;
      bySlot.set(item.slot, id);
    });
    return [...bySlot.values()];
  }

  function appendLayer(stage, source, className, alt, presentation) {
    const image = document.createElement('img');
    image.className = `rpg-wearable-layer ${className}`;
    image.src = source;
    image.alt = alt || '';
    image.decoding = 'async';
    image.draggable = false;
    const transform = presentation?.presentation_transform;
    if (transform && typeof transform === 'object') {
      const offset = transform.offset_percent || {};
      const x = Number(offset.x);
      const y = Number(offset.y);
      const rotation = Number(transform.rotation_deg ?? 0);
      const scale = Number(transform.scale);
      if (Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(scale)
        && Number.isFinite(rotation)
        && Math.abs(x) <= 30 && Math.abs(y) <= 30
        && Math.abs(rotation) <= 180 && scale > 0.5 && scale <= 1.1) {
        image.style.transform = `translate(${x}%, ${y}%) rotate(${rotation}deg) scale(${scale})`;
        image.style.transformOrigin = typeof transform.transform_origin === 'string'
          ? transform.transform_origin
          : 'center center';
        image.dataset.presentationMode = presentation?.presentation_mode || transform.mode || '';
        image.dataset.presentationAttachment = presentation?.presentation_attachment
          || transform.attachment || presentation?.anchor || '';
        image.dataset.presentationRotation = String(rotation);
        image.dataset.presentationOcclusion = transform.occlusion || '';
      }
    }
    image.dataset.presentationLayer = presentation?.layer || '';
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
    const requestedIds = [...new Set(
      (Array.isArray(equipped) ? equipped : []).map(equipmentId).filter(Boolean),
    )];
    const replacementIds = requestedIds.filter(id => ART_REPLACEMENT_REQUIRED.has(id));
    const selectedIds = normalizeEquipped(requestedIds, registry);
    const selected = new Set(selectedIds);
    const entries = selectedIds.map(id => registry.equipment[id]).filter(Boolean);
    const appendEntries = layer => entries
      .filter(item => item.layer === layer)
      .forEach(item => appendLayer(stage, item.asset, `equipment-${item.id} layer-${layer.toLowerCase()}`, item.canonical_identity, item));

    appendEntries('BACK_WEAPON');
    appendEntries('BACK_BODY');
    appendLayer(stage, baseCharacter.base, 'character-base', `${characterKey} character base`);
    appendEntries('FRONT_WEAPON');
    appendEntries('TORSO_ARMOR');
    appendEntries('FRONT_BODY');
    appendEntries('FRONT_ACCESSORY');
    appendEntries('HEAD_FACE');

    if (entries.some(item => (item.mask_requirements || []).includes('HAIR_FRONT_MASK'))) {
      const maskAsset = baseCharacter.hair_front_mask || opts.maskAsset || '';
      if (maskAsset) appendLayer(stage, maskAsset, 'character-hair-front-mask layer-hair-front-mask', 'reusable character hair mask');
    }
    stage.dataset.equippedIds = selectedIds.join(',');
    stage.dataset.replacementIds = replacementIds.join(',');
    stage.dataset.authority = 'server_equipped_projection';
    stage.dataset.gameplayAuthority = 'none';
    return {
      supported: true,
      character: characterKey,
      equipped: selectedIds,
      replacementRequired: replacementIds,
      frame: registry.player_frame.id,
    };
  }

  function renderSafe(stage, characterKey, equipped, options) {
    return render(stage, characterKey, equipped, options).catch(error => {
      if (stage) {
        stage.innerHTML = '';
        stage.hidden = true;
        stage.dataset.supported = 'false';
        stage.dataset.replacementIds = '';
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
    artReplacementRequiredIds: ART_REPLACEMENT_REQUIRED_IDS,
  };
})(window);
