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
    // Answer screens can be refreshed while an earlier inventory/appearance
    // request is still in flight (for example after an equip swap in another
    // tab).  The caller owns the revision token; do not let an older render
    // commit after a newer one has started.
    if (typeof opts.isCurrent === 'function' && !opts.isCurrent()) {
      return { supported: false, reason: 'stale_render' };
    }
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

/* EQ-C recovery: the true-handheld paper-doll API is kept in this already
 * served presentation module, without a new server route or authority. */
(function (global) {
  'use strict';

  const HANDHELD_REGISTRY_URL = '/assets/hero/equipment/wearables/handheld/handheld_runtime_registry.json';
  const HANDHELD_FRAME = { width: 1056, height: 1408 };
  let handheldRegistryPromise = null;
  const handheldImages = new Map();

  function handheldStyles() {
    if (document.getElementById('go-odyssey-eq-c-handheld-styles')) return;
    const style = document.createElement('style');
    style.id = 'go-odyssey-eq-c-handheld-styles';
    style.textContent = `
      .rpg-handheld-weapon-stage { position:absolute; inset:0; z-index:4; overflow:visible; display:block; pointer-events:none; aspect-ratio:1056 / 1408; }
      .rpg-handheld-weapon-stage canvas { display:block; width:100%; height:100%; object-fit:contain; image-rendering:auto; pointer-events:none; }
      #player-avatar-figure.handheld-paper-doll-active > .player-combat-layer { visibility:hidden !important; }
      #player-avatar-figure.handheld-paper-doll-active > #player-answer-equipment-stage { visibility:hidden !important; }
    `;
    document.head.appendChild(style);
  }

  function handheldRegistry() {
    if (!handheldRegistryPromise) {
      handheldRegistryPromise = fetch(HANDHELD_REGISTRY_URL, {
        credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' },
      }).then(response => {
        if (!response.ok) throw new Error(`handheld registry HTTP ${response.status}`);
        return response.json();
      }).then(registry => {
        if (!registry || registry.schema !== 'go-odyssey.true-handheld-weapon-runtime.v1'
          || registry.frame?.id !== 'PLAYER_FRAME_A_STANDARD_CHIBI'
          || registry.pose_id !== 'ONE_HAND_SWORD' || registry.renderer_slot !== 'MAIN_HAND') {
          throw new Error('unsupported true-handheld registry');
        }
        return registry;
      });
    }
    return handheldRegistryPromise;
  }

  function handheldImage(source) {
    if (!handheldImages.has(source)) {
      handheldImages.set(source, new Promise((resolve, reject) => {
        const image = new global.Image();
        image.decoding = 'async';
        image.onload = () => resolve(image);
        image.onerror = () => reject(new Error(`handheld asset failed: ${source}`));
        image.src = source;
      }));
    }
    return handheldImages.get(source);
  }

  function handheldRows(inventory) {
    if (Array.isArray(inventory)) return inventory;
    if (Array.isArray(inventory?.items)) return inventory.items;
    if (Array.isArray(inventory?.inventory)) return inventory.inventory;
    return [];
  }

  function resolveHandheldWeapon(inventory, registry) {
    const weapons = registry?.weapons || {};
    return handheldRows(inventory).find(item => {
      if (!item || item.equipped !== true || item.functional_equipment !== true) return false;
      const id = String(item.item_id || item.id || '').trim();
      return item.slot === 'weapon' && Boolean(weapons[id]) && weapons[id].runtime_supported !== false;
    }) || null;
  }

  function handheldFallback(stage, fallback, visible) {
    if (stage) {
      stage.hidden = visible;
      stage.setAttribute('aria-hidden', visible ? 'true' : 'false');
      stage.dataset.supported = visible ? 'false' : 'true';
    }
    if (fallback) fallback.hidden = !visible;
  }

  function eraseHandheldMask(context, maskImage) {
    const maskCanvas = document.createElement('canvas');
    maskCanvas.width = HANDHELD_FRAME.width;
    maskCanvas.height = HANDHELD_FRAME.height;
    const maskContext = maskCanvas.getContext('2d', { willReadFrequently: true });
    maskContext.drawImage(maskImage, 0, 0, HANDHELD_FRAME.width, HANDHELD_FRAME.height);
    const maskData = maskContext.getImageData(0, 0, HANDHELD_FRAME.width, HANDHELD_FRAME.height);
    const eraseData = maskContext.createImageData(HANDHELD_FRAME.width, HANDHELD_FRAME.height);
    for (let i = 0; i < maskData.data.length; i += 4) eraseData.data[i + 3] = maskData.data[i];
    maskContext.clearRect(0, 0, HANDHELD_FRAME.width, HANDHELD_FRAME.height);
    maskContext.putImageData(eraseData, 0, 0);
    context.save();
    context.globalCompositeOperation = 'destination-out';
    context.drawImage(maskCanvas, 0, 0);
    context.restore();
  }

  function drawHandheldWeapon(context, image, spec, anchor) {
    const width = Number(spec.asset_width || image.naturalWidth);
    const height = Number(spec.asset_height || image.naturalHeight);
    const scale = Number(spec.scale || 1);
    context.save();
    context.translate(Number(anchor.x || 0), Number(anchor.y || 0));
    context.rotate(Number(spec.rotation_deg || 0) * Math.PI / 180);
    context.scale(scale, scale);
    context.translate(-Number(spec.weapon_grip_x) * width, -Number(spec.weapon_grip_y) * height);
    context.drawImage(image, 0, 0, width, height);
    context.restore();
  }

  function drawHandheldFrontGrip(context, image, registry) {
    const grip = registry.grip_anchor || {};
    const height = Number(grip.front_grip_target_height || 240);
    const width = image.naturalWidth * height / image.naturalHeight;
    const x = Number(grip.x || 0) - Number(grip.front_grip_asset_anchor_x || 0.8) * width;
    const y = Number(grip.y || 0) - Number(grip.front_grip_asset_anchor_y || 0.58) * height;
    context.drawImage(image, x, y, width, height);
  }

  function equippedWearableIds(inventory, wearableRegistry) {
    const bySlot = new Map();
    handheldRows(inventory).forEach(item => {
      if (!item || item.equipped !== true || item.functional_equipment !== true) return;
      const id = String(item.item_id || item.id || '').trim();
      const entry = wearableRegistry?.equipment?.[id];
      if (!entry || entry.wearable_visibility === 'INVENTORY_ONLY' || !entry.asset) return;
      if (bySlot.has(entry.slot)) return;
      bySlot.set(entry.slot, id);
    });
    return [...bySlot.values()];
  }

  function drawWearableEntry(context, image, entry) {
    context.drawImage(image, 0, 0, HANDHELD_FRAME.width, HANDHELD_FRAME.height);
  }

  async function renderHandheldComposition(
    context,
    character,
    weapon,
    inventory,
    handheldRegistryValue,
    wearableRegistry,
    characterKey,
  ) {
    const wearableCharacter = wearableRegistry?.characters?.[characterKey] || {};
    const wearableIds = equippedWearableIds(inventory, wearableRegistry);
    const wearableEntries = wearableIds
      .map(id => wearableRegistry?.equipment?.[id])
      .filter(Boolean);
    const layerOrder = Array.isArray(wearableRegistry?.layer_order)
      ? wearableRegistry.layer_order
      : [
          'BACK_WEAPON', 'BACK_BODY', 'CHARACTER_BASE', 'TORSO_ARMOR',
          'FRONT_BODY', 'FRONT_ACCESSORY', 'HEAD_FACE', 'HAIR_FRONT_MASK',
        ];
    const assets = new Map();
    const needed = [
      character.base_asset,
      character.open_hand_suppression_mask,
      character.front_grip_hand_asset,
      weapon.asset,
      ...wearableEntries.map(entry => entry.asset),
    ];
    if (wearableEntries.some(entry => (entry.mask_requirements || []).includes('HAIR_FRONT_MASK'))) {
      if (wearableCharacter.hair_front_mask) needed.push(wearableCharacter.hair_front_mask);
    }
    await Promise.all([...new Set(needed)].map(async source => {
      assets.set(source, await handheldImage(source));
    }));
    context.clearRect(0, 0, HANDHELD_FRAME.width, HANDHELD_FRAME.height);
    context.drawImage(assets.get(character.base_asset), 0, 0, HANDHELD_FRAME.width, HANDHELD_FRAME.height);
    eraseHandheldMask(context, assets.get(character.open_hand_suppression_mask));
    for (const layer of layerOrder) {
      if (layer === 'CHARACTER_BASE' || layer === 'HAIR_FRONT_MASK') continue;
      wearableEntries
        .filter(entry => entry.layer === layer)
        .filter(entry => entry.layer !== 'MAIN_HAND_WEAPON' && entry.handheld_runtime_supported !== true)
        .forEach(entry => drawWearableEntry(context, assets.get(entry.asset), entry));
      if (layer === 'HEAD_FACE' && wearableEntries.some(entry => (entry.mask_requirements || []).includes('HAIR_FRONT_MASK'))) {
        const mask = wearableCharacter.hair_front_mask;
        if (mask && assets.get(mask)) drawWearableEntry(context, assets.get(mask), { layer: 'HAIR_FRONT_MASK' });
      }
    }
    drawHandheldWeapon(context, assets.get(weapon.asset), weapon, handheldRegistryValue.grip_anchor);
    drawHandheldFrontGrip(context, assets.get(character.front_grip_hand_asset), handheldRegistryValue);
  }

  async function renderHandheld(stage, characterKey, inventory, options) {
    handheldStyles();
    if (!stage) return { supported: false, reason: 'missing_stage' };
    const opts = options || {};
    const registry = await handheldRegistry();
    if (typeof opts.isCurrent === 'function' && !opts.isCurrent()) {
      return { supported: false, reason: 'stale_render' };
    }
    const character = registry.characters?.[characterKey];
    const equipped = resolveHandheldWeapon(inventory, registry);
    const weaponId = equipped ? String(equipped.item_id || equipped.id) : '';
    const weapon = weaponId ? registry.weapons?.[weaponId] : null;
    const fallback = opts.fallbackElement || null;
    stage.dataset.authority = 'server_equipped_projection';
    stage.dataset.gameplayAuthority = 'none';
    stage.dataset.frame = registry.frame.id;
    stage.dataset.poseId = registry.pose_id;
    stage.dataset.rendererSlot = registry.renderer_slot;
    delete stage.dataset.renderError;
    if (!character || !weapon) {
      handheldFallback(stage, fallback, true);
      if (opts.figureElement) opts.figureElement.classList.remove('handheld-paper-doll-active');
      return { supported: false, reason: !character ? 'unsupported_character' : 'no_equipped_supported_weapon' };
    }
    const wearableRegistry = global.GoOdysseyWearableRenderer
      ? await global.GoOdysseyWearableRenderer.loadRegistry()
      : null;
    if (typeof opts.isCurrent === 'function' && !opts.isCurrent()) {
      return { supported: false, reason: 'stale_render' };
    }
    const canvas = document.createElement('canvas');
    canvas.width = HANDHELD_FRAME.width;
    canvas.height = HANDHELD_FRAME.height;
    canvas.className = 'rpg-handheld-weapon-canvas';
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', `${weaponId} equipped in hand`);
    const context = canvas.getContext('2d');
    // The final answer composition is one canvas: the existing EQ-B
    // registry-driven armor/accessory layers remain present beneath the EQ-C
    // handheld weapon, so a full-frame base canvas cannot cover them.
    await renderHandheldComposition(
      context,
      character,
      weapon,
      inventory,
      registry,
      wearableRegistry,
      characterKey,
    );
    if (typeof opts.isCurrent === 'function' && !opts.isCurrent()) {
      return { supported: false, reason: 'stale_render' };
    }
    stage.innerHTML = '';
    stage.appendChild(canvas);
    stage.hidden = false;
    stage.setAttribute('aria-hidden', 'false');
    stage.dataset.supported = 'true';
    stage.dataset.weaponId = weaponId;
    stage.dataset.layerOrder = registry.layer_order.join(',');
    if (fallback) fallback.hidden = true;
    if (opts.figureElement) opts.figureElement.classList.add('handheld-paper-doll-active');
    return { supported: true, character: characterKey, weaponId, poseId: registry.pose_id, rendererSlot: registry.renderer_slot, layerOrder: registry.layer_order.slice(), responsive: 'scale_composition_as_unit' };
  }

  function renderHandheldSafe(stage, characterKey, inventory, options) {
    return renderHandheld(stage, characterKey, inventory, options).catch(error => {
      if (stage) {
        stage.innerHTML = '';
        stage.hidden = true;
        stage.setAttribute('aria-hidden', 'true');
        stage.dataset.supported = 'false';
        stage.dataset.renderError = error.message || 'handheld_render_failed';
      }
      if (options?.fallbackElement) options.fallbackElement.hidden = false;
      if (options?.figureElement) options.figureElement.classList.remove('handheld-paper-doll-active');
      return { supported: false, reason: 'render_error', error: error.message };
    });
  }

  global.GoOdysseyHandheldWeaponRenderer = {
    loadRegistry: handheldRegistry,
    inventoryRows: handheldRows,
    resolveEquippedWeapon: resolveHandheldWeapon,
    render: renderHandheld,
    renderSafe: renderHandheldSafe,
    registryUrl: HANDHELD_REGISTRY_URL,
  };
})(window);
