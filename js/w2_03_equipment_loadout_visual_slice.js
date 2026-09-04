/* W2-03 Equipment / Loadout visual vertical slice.
 *
 * The module is intentionally a projection boundary.  It consumes the
 * server-owned /api/player/inventory rows and the server capability from
 * /api/auth/me; it never invents ownership, slot authority, effects, or
 * equipped state.  The default mutation path is the existing canonical
 * /api/player/inventory/equip endpoint and every successful mutation is
 * followed by a fresh read.
 */
(function (global) {
  'use strict';

  const API = Object.freeze({
    inventory: '/api/player/inventory',
    capability: '/api/auth/me',
    appearance: '/api/player/appearance',
    mutation: '/api/player/inventory/equip',
  });

  // Presentation vocabulary only.  These are not an equipment allowlist or
  // a client-side equippability authority.
  const PAPER_DOLL_LAYER_ORDER = Object.freeze([
    'BACK_WEAPON',
    'BACK_BODY',
    'CHARACTER_BASE',
    'TORSO_ARMOR',
    'FRONT_BODY',
    'FRONT_ACCESSORY',
    'HEAD_FACE',
    'HAIR_FRONT_MASK',
  ]);
  const PAPER_DOLL_LAYER_COUNT = PAPER_DOLL_LAYER_ORDER.length;
  const SLOT_LABELS = Object.freeze({
    weapon: Object.freeze({ zh: '武器', en: 'Weapon' }),
    armor: Object.freeze({ zh: '防具', en: 'Armor' }),
    accessory: Object.freeze({ zh: '飾品', en: 'Accessory' }),
  });
  const RARITY_LABELS = Object.freeze({
    common: Object.freeze({ zh: '普通', en: 'Common' }),
    uncommon: Object.freeze({ zh: '非凡', en: 'Uncommon' }),
    rare: Object.freeze({ zh: '稀有', en: 'Rare' }),
    epic: Object.freeze({ zh: '史詩', en: 'Epic' }),
    legendary: Object.freeze({ zh: '傳說', en: 'Legendary' }),
  });

  function escapeHTML(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (character) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[character]));
  }

  function isEnglish() {
    try {
      if (global.I18n && typeof global.I18n.getLang === 'function') {
        return global.I18n.getLang() === 'en';
      }
    } catch (_) {
      // A language helper is optional for this isolated surface.
    }
    return String(document.documentElement?.lang || '').toLowerCase().startsWith('en');
  }

  function text(zh, en) {
    return isEnglish() ? en : zh;
  }

  function stringValue(value) {
    return typeof value === 'string' ? value.trim() : '';
  }

  function itemIdFromRow(row) {
    return stringValue(
      row?.item_id
      || row?.equip_id
      || row?.itemId
      || (typeof row?.id === 'string' ? row.id : '')
    );
  }

  function inventoryIdFromRow(row) {
    const value = row?.inv_id ?? row?.inventory_id ?? row?.ownership_row_id;
    return value == null || value === '' ? '' : String(value);
  }

  function safeAssetPath(value) {
    const path = stringValue(value);
    if (!path || !path.startsWith('/assets/') || path.includes('..')) return '';
    if (!/^\/assets\/[A-Za-z0-9_./-]+$/.test(path)) return '';
    return path;
  }

  function itemSelectionKey(item) {
    return `${item.itemId}::${item.invId || 'no-row'}`;
  }

  function displayName(item) {
    return isEnglish()
      ? (item.displayNameEn || item.nameEn || item.displayName || item.itemId)
      : (item.displayName || item.name || item.displayNameEn || item.itemId);
  }

  function slotLabel(slot) {
    const labels = SLOT_LABELS[slot];
    return labels ? (isEnglish() ? labels.en : labels.zh) : (slot || text('未分類', 'Unassigned'));
  }

  function rarityLabel(rarity) {
    const key = stringValue(rarity).toLowerCase();
    const labels = RARITY_LABELS[key];
    return labels ? (isEnglish() ? labels.en : labels.zh) : (rarity || text('普通', 'Common'));
  }

  function normalizeSnapshot(payload) {
    const input = payload && typeof payload === 'object' ? payload : {};
    const sourceRows = Array.isArray(input.inventory)
      ? input.inventory
      : (Array.isArray(input.items) ? input.items : []);
    const items = sourceRows.map((row) => {
      if (!row || typeof row !== 'object') return null;
      const itemId = itemIdFromRow(row);
      if (!itemId) return null;
      const presentation = row.presentation && typeof row.presentation === 'object'
        ? { ...row.presentation }
        : {};
      const rawQuantity = Number(row.owned_quantity);
      return {
        ...row,
        itemId,
        invId: inventoryIdFromRow(row),
        displayName: stringValue(row.display_name || row.name),
        displayNameEn: stringValue(row.display_name_en || row.name_en),
        name: stringValue(row.name),
        nameEn: stringValue(row.name_en),
        displaySlot: stringValue(row.slot),
        canonicalSlot: stringValue(row.canonical_slot),
        rarity: stringValue(row.rarity).toLowerCase() || 'common',
        icon: safeAssetPath(row.icon),
        presentation,
        // An inventory row is an ownership projection.  If a test or a
        // future endpoint sends owned=false explicitly, retain that state;
        // an omitted field remains owned because the row came from the
        // server-owned player_inventory collection.
        owned: row.owned !== false,
        equipped: row.equipped === true,
        canonicalEquippable: row.canonical_equippable === true,
        ownedQuantity: Number.isFinite(rawQuantity) && rawQuantity > 0
          ? Math.floor(rawQuantity)
          : 1,
        activeEffectDetails: Array.isArray(row.active_effect_details)
          ? row.active_effect_details.filter((effect) => effect && typeof effect === 'object')
          : [],
        unsupportedEffects: Array.isArray(row.unsupported_effects)
          ? row.unsupported_effects.filter((effect) => effect && typeof effect === 'object')
          : [],
      };
    }).filter(Boolean);

    const itemGroups = new Map();
    items.forEach((item) => {
      const group = itemGroups.get(item.itemId) || [];
      group.push(item);
      itemGroups.set(item.itemId, group);
    });
    items.forEach((item) => {
      const group = itemGroups.get(item.itemId) || [];
      item.groupCount = group.length;
      item.ambiguousOwnership = group.length > 1 && !group.some((candidate) => candidate.equipped);
    });

    const equippedBySlot = new Map();
    items.forEach((item) => {
      if (!item.equipped || !item.canonicalSlot) return;
      const rows = equippedBySlot.get(item.canonicalSlot) || [];
      rows.push(item);
      equippedBySlot.set(item.canonicalSlot, rows);
    });
    const conflictedSlots = new Set();
    equippedBySlot.forEach((rows, slot) => {
      if (rows.length > 1) conflictedSlots.add(slot);
    });
    items.forEach((item) => {
      item.equippedConflict = Boolean(item.canonicalSlot && conflictedSlots.has(item.canonicalSlot));
    });

    const capability = input.capability || input.me || input.auth || {};
    const appearance = input.appearance || input.character || {};
    const characterKey = stringValue(
      appearance.character_key
      || appearance.characterKey
      || input.character_key
      || input.characterKey
    );

    return {
      items,
      capability: {
        // Strict true is intentional: a missing or failed capability read
        // fails closed and cannot expose Equip/Unequip controls.
        loadoutEnabled: capability.equipment_loadout_enabled === true,
      },
      characterKey,
      equippedBySlot,
      conflictedSlots,
      source: 'server_owned_projection',
    };
  }

  function template() {
    return `
      <div class="w2-03-slice-header">
        <div>
          <p class="w2-03-slice-kicker">WAVE 2 · EQUIPMENT</p>
          <h2 class="w2-03-slice-title">裝備工坊 / Equipment Wardrobe</h2>
          <p class="w2-03-slice-copy">查看你真正持有的功能裝備、同槽比較與目前角色投影。所有持有、效果與已裝備狀態均來自伺服器；外觀預覽不會建立第二份權限。</p>
        </div>
        <span class="w2-03-capability" data-w2-capability data-state="unknown">Loadout checking…</span>
      </div>
      <div class="w2-03-status" data-w2-status role="status" aria-live="polite"></div>
      <div class="w2-03-slice-layout">
        <section class="w2-03-paper-card" aria-labelledby="w2-03-paper-title">
          <div class="w2-03-panel-heading">
            <h3 class="w2-03-panel-title" id="w2-03-paper-title">英雄紙娃娃 / Hero Paper Doll</h3>
            <span class="w2-03-panel-note">8 composable layers</span>
          </div>
          <div class="w2-03-paper-stage-wrap">
            <div class="w2-03-paper-stage rpg-wearable-host" data-w2-paper-stage data-paper-doll-layer-count="8" data-authority="server_equipped_projection" data-gameplay-authority="none" hidden aria-hidden="true"></div>
            <div class="w2-03-paper-fallback" data-w2-paper-fallback>角色外觀載入中…<br>Character preview is loading.</div>
          </div>
          <p class="w2-03-layer-caption">base · hair · outfit · cape · weapon layers remain composable; unsupported assets stay hidden.</p>
          <ul class="w2-03-equipped-summary" data-w2-equipped-summary aria-label="目前已裝備摘要"></ul>
        </section>
        <section class="w2-03-inventory-card" aria-labelledby="w2-03-inventory-title">
          <div class="w2-03-panel-heading">
            <h3 class="w2-03-panel-title" id="w2-03-inventory-title">已持有裝備 / Owned equipment</h3>
            <span class="w2-03-panel-note" data-w2-owned-count>0 items</span>
          </div>
          <div class="w2-03-filter-row" data-w2-filter-row role="tablist" aria-label="Equipment slots"></div>
          <div class="w2-03-inventory-grid" data-w2-inventory-grid aria-live="polite"></div>
        </section>
        <aside class="w2-03-detail-card" data-w2-detail-card aria-labelledby="w2-03-detail-title" aria-live="polite"></aside>
      </div>
    `;
  }

  function ensureMarkup(root) {
    if (!root.querySelector('[data-w2-inventory-grid]')) root.innerHTML = template();
  }

  function iconMarkup(item, className) {
    const name = escapeHTML(displayName(item));
    const initial = escapeHTML(displayName(item).slice(0, 1) || '?');
    if (!item.icon) return `<span class="${className}"><span aria-hidden="true">${initial}</span></span>`;
    return `<span class="${className}"><img data-w2-image src="${escapeHTML(item.icon)}" alt="${name}" loading="lazy" decoding="async"><span data-w2-image-fallback hidden aria-hidden="true">${initial}</span></span>`;
  }

  function effectLabel(effect) {
    if (!effect || typeof effect !== 'object') return text('已定義效果', 'Defined effect');
    return stringValue(isEnglish() ? (effect.label_en || effect.label) : (effect.label || effect.label_en))
      || text('已定義效果', 'Defined effect');
  }

  function effectValue(effect) {
    if (!effect || typeof effect !== 'object') return '';
    return stringValue(isEnglish()
      ? (effect.value_label_en || effect.value_label || effect.declared_value_label_en || effect.declared_value_label)
      : (effect.value_label || effect.value_label_en || effect.declared_value_label || effect.declared_value_label_en));
  }

  function effectMarkup(item, limit) {
    if (!item.canonicalEquippable) {
      return `<li class="w2-03-effect-muted">${escapeHTML(text('伺服器不允許裝備；不投影戰鬥效果。', 'The server does not allow equipping this item. No combat effect is projected.'))}</li>`;
    }
    const active = item.activeEffectDetails.slice(0, limit || 3);
    const unsupported = item.unsupportedEffects.slice(0, Math.max(0, (limit || 3) - active.length));
    const rows = active.map((effect) => `<li><span>${escapeHTML(effectLabel(effect))}</span><strong>${escapeHTML(effectValue(effect) || '—')}</strong></li>`);
    unsupported.forEach((effect) => rows.push(`<li class="w2-03-effect-muted"><span>${escapeHTML(effectLabel(effect))}</span><strong>${escapeHTML(effectValue(effect) || '—')}</strong></li>`));
    return rows.length
      ? rows.join('')
      : `<li class="w2-03-effect-muted">${escapeHTML(text('目前沒有啟用效果', 'No active effect'))}</li>`;
  }

  function statusForItem(item) {
    if (item.equipped) return text('已裝備', 'Equipped');
    if (!item.owned) return text('未持有', 'Unavailable');
    return text('已持有', 'Owned');
  }

  function itemMatchesFilter(item, filter) {
    if (filter === 'all') return true;
    if (filter === 'equipped') return item.equipped;
    return item.displaySlot === filter || item.canonicalSlot === filter;
  }

  function currentReplacement(snapshot, item) {
    if (!item || item.equipped || !item.canonicalSlot) return null;
    const candidates = (snapshot.equippedBySlot.get(item.canonicalSlot) || [])
      .filter((candidate) => candidate.itemId !== item.itemId);
    return candidates.length === 1 ? candidates[0] : null;
  }

  function findSelected(snapshot, selectedKey) {
    if (!snapshot || !selectedKey) return null;
    return snapshot.items.find((item) => itemSelectionKey(item) === selectedKey) || null;
  }

  function filterButtons(state) {
    const root = state.root.querySelector('[data-w2-filter-row]');
    if (!root) return;
    const filters = [
      ['all', text('全部', 'All')],
      ['weapon', text('武器', 'Weapon')],
      ['armor', text('防具', 'Armor')],
      ['accessory', text('飾品', 'Accessory')],
      ['equipped', text('已裝備', 'Equipped')],
    ];
    root.innerHTML = filters.map(([key, label]) => {
      const count = state.snapshot
        ? state.snapshot.items.filter((item) => item.owned && itemMatchesFilter(item, key)).length
        : 0;
      return `<button type="button" class="w2-03-filter" data-w2-filter="${key}" role="tab" aria-selected="${String(state.filter === key)}">${escapeHTML(label)} ${count}</button>`;
    }).join('');
  }

  function renderGrid(state) {
    const grid = state.root.querySelector('[data-w2-inventory-grid]');
    if (!grid) return;
    const items = state.snapshot
      ? state.snapshot.items.filter((item) => item.owned && itemMatchesFilter(item, state.filter))
      : [];
    const ownedCount = state.snapshot
      ? state.snapshot.items.filter((item) => item.owned).length
      : 0;
    const countElement = state.root.querySelector('[data-w2-owned-count]');
    if (countElement) countElement.textContent = text(`${ownedCount} 件`, `${ownedCount} item${ownedCount === 1 ? '' : 's'}`);
    if (!items.length) {
      grid.innerHTML = `<div class="w2-03-empty">${escapeHTML(state.loading ? text('正在同步伺服器裝備…', 'Syncing server equipment…') : text('此分類目前沒有已持有裝備。', 'No owned equipment in this slot.'))}</div>`;
      return;
    }
    grid.innerHTML = items.map((item) => {
      const selected = itemSelectionKey(item) === state.selectedKey;
      const equippable = item.canonicalEquippable;
      const conflict = item.equippedConflict;
      const blockedLabel = conflict
        ? text('同槽狀態需確認', 'Slot state needs review')
        : (equippable ? '' : text('不可裝備', 'Not equippable'));
      const label = `${displayName(item)} · ${slotLabel(item.displaySlot || item.canonicalSlot)}`;
      return `<button type="button" class="w2-03-item-card" data-w2-item-key="${escapeHTML(itemSelectionKey(item))}" data-selected="${String(selected)}" data-equipped="${String(item.equipped)}" data-equippable="${String(equippable)}" aria-pressed="${String(selected)}" aria-label="${escapeHTML(label)}">
        ${iconMarkup(item, 'w2-03-item-icon')}
        <span class="w2-03-item-copy">
          <span class="w2-03-item-name">${escapeHTML(displayName(item))}</span>
          <span class="w2-03-item-meta">${escapeHTML(slotLabel(item.displaySlot || item.canonicalSlot))} · ${escapeHTML(rarityLabel(item.rarity))}</span>
          <span class="w2-03-item-state">${escapeHTML(statusForItem(item))}</span>
          ${blockedLabel ? `<span class="w2-03-item-blocked">${escapeHTML(blockedLabel)}</span>` : ''}
        </span>
        <span class="w2-03-item-count">×${escapeHTML(item.ownedQuantity)}</span>
      </button>`;
    }).join('');
  }

  function renderPaperDollSummary(state) {
    const list = state.root.querySelector('[data-w2-equipped-summary]');
    if (!list) return;
    const equipped = state.snapshot
      ? state.snapshot.items.filter((item) => item.equipped)
      : [];
    if (!equipped.length) {
      list.innerHTML = `<li><span>${escapeHTML(text('目前配置', 'Current loadout'))}</span><strong>${escapeHTML(text('尚無功能裝備', 'No functional equipment'))}</strong></li>`;
      return;
    }
    list.innerHTML = equipped.map((item) => `<li><span>${escapeHTML(slotLabel(item.displaySlot || item.canonicalSlot))}</span><strong>${escapeHTML(displayName(item))}</strong></li>`).join('');
  }

  function renderPaperDoll(state) {
    const stage = state.root.querySelector('[data-w2-paper-stage]');
    const fallback = state.root.querySelector('[data-w2-paper-fallback]');
    if (!stage || !fallback) return;
    const token = ++state.paperDollToken;
    stage.dataset.paperDollLayerCount = String(PAPER_DOLL_LAYER_COUNT);
    stage.dataset.authority = 'server_equipped_projection';
    stage.dataset.gameplayAuthority = 'none';
    stage.innerHTML = '';
    stage.hidden = true;
    stage.setAttribute('aria-hidden', 'true');
    fallback.hidden = false;
    fallback.innerHTML = escapeHTML(text('角色外觀載入中…', 'Character preview is loading.'));

    const snapshot = state.snapshot;
    if (!snapshot || !snapshot.characterKey) {
      fallback.innerHTML = escapeHTML(text('目前無法取得角色外觀；裝備清單仍可查看。', 'Character preview is unavailable; the equipment list remains available.'));
      renderPaperDollSummary(state);
      return;
    }
    const equipped = snapshot.items
      .filter((item) => item.equipped && item.canonicalEquippable)
      .filter((item) => item.presentation?.mode === 'FULL_BODY_OVERLAY')
      .filter((item) => safeAssetPath(item.presentation?.asset))
      .map((item) => ({
        equipment_id: item.itemId,
        slot: item.displaySlot || item.canonicalSlot,
        equipped: true,
      }));
    const renderer = global.GoOdysseyWearableRenderer;
    if (!renderer || typeof renderer.renderSafe !== 'function') {
      fallback.innerHTML = escapeHTML(text('紙娃娃渲染器尚未載入；裝備狀態仍以文字呈現。', 'Paper Doll renderer is unavailable; equipment state remains visible as text.'));
      renderPaperDollSummary(state);
      return;
    }
    Promise.resolve(renderer.renderSafe(stage, snapshot.characterKey, equipped, { fallbackElement: fallback }))
      .then((result) => {
        if (state.destroyed || token !== state.paperDollToken) return;
        if (!result || result.supported !== true) {
          stage.hidden = true;
          stage.setAttribute('aria-hidden', 'true');
          fallback.hidden = false;
          fallback.innerHTML = escapeHTML(text('此角色目前沒有可用的紙娃娃資產。', 'No Paper Doll asset is available for this character.'));
        } else {
          stage.hidden = false;
          stage.setAttribute('aria-hidden', 'true');
          stage.dataset.authority = 'server_equipped_projection';
          stage.dataset.gameplayAuthority = 'none';
        }
        renderPaperDollSummary(state);
      })
      .catch(() => {
        if (state.destroyed || token !== state.paperDollToken) return;
        stage.hidden = true;
        stage.setAttribute('aria-hidden', 'true');
        fallback.hidden = false;
        fallback.innerHTML = escapeHTML(text('角色外觀展示失敗；清單仍可使用。', 'Character preview failed; the equipment list remains usable.'));
        renderPaperDollSummary(state);
      });
  }

  function renderDetail(state) {
    const detail = state.root.querySelector('[data-w2-detail-card]');
    if (!detail) return;
    const item = findSelected(state.snapshot, state.selectedKey);
    if (!item) {
      detail.innerHTML = `<div class="w2-03-detail-empty" id="w2-03-detail-title">${escapeHTML(text('選取一件已持有裝備，以查看效果、同槽比較與角色投影。', 'Select owned equipment to review effects, slot comparison, and the Hero projection.'))}</div>`;
      return;
    }
    const equippable = item.canonicalEquippable;
    const replacement = state.snapshot ? currentReplacement(state.snapshot, item) : null;
    const conflict = item.equippedConflict;
    const action = item.equipped ? 'unequip' : 'equip';
    const actionLabel = item.equipped ? text('卸下', 'Unequip') : text('裝備', 'Equip');
    let control = '';
    if (!equippable) {
      control = `<div class="w2-03-blocked-note" role="status">${escapeHTML(text('已持有，但伺服器標記為不可裝備。此物品不會進入 Hero 紙娃娃。', 'Owned, but the server marks this item as not equippable. It will not enter the Hero Paper Doll.'))}</div>`;
    } else if (!state.snapshot?.capability.loadoutEnabled) {
      control = `<div class="w2-03-blocked-note" role="status">${escapeHTML(text('Loadout 目前未開啟。你可以查看持有與已裝備狀態，但不會顯示功能性裝備操作。', 'Loadout is currently off. Ownership and equipped state remain visible, but functional Equip controls are not exposed.'))}</div>`;
    } else if (conflict) {
      control = `<div class="w2-03-blocked-note" role="status">${escapeHTML(text('同一 canonical slot 有多筆已裝備狀態；已停止操作，等待伺服器狀態修復。', 'Multiple equipped rows exist for this canonical slot; actions are paused until the server state is repaired.'))}</div>`;
    } else if (!item.invId) {
      control = `<div class="w2-03-blocked-note" role="status">${escapeHTML(text('缺少 ownership row reference；為安全起見不執行操作。', 'The ownership-row reference is unavailable; no action is attempted.'))}</div>`;
    } else {
      control = `<div class="w2-03-action-row"><button type="button" class="w2-03-action" data-w2-mutation="${action}"${state.mutating ? ' disabled' : ''}>${escapeHTML(state.mutating ? text('同步中…', 'Syncing…') : actionLabel)}</button></div>`;
    }
    const replacementMarkup = replacement
      ? `<div class="w2-03-replacement" role="status">${escapeHTML(text(`將替換目前同槽裝備：${displayName(replacement)}。`, `This will replace the current ${slotLabel(item.canonicalSlot)} item: ${displayName(replacement)}.`))}</div>`
      : '';
    const conflictMarkup = conflict
      ? `<div class="w2-03-blocked-note" role="status">${escapeHTML(text('此 slot 的 server projection 有衝突，沒有自動選擇任何一件。', 'This slot has a conflicting server projection; no item was selected automatically.'))}</div>`
      : '';
    const stateLabel = item.equipped ? text('目前已裝備', 'Currently equipped') : text('已持有，尚未裝備', 'Owned, not equipped');
    detail.innerHTML = `
      <div class="w2-03-detail-top">
        ${iconMarkup(item, 'w2-03-detail-icon')}
        <div>
          <h3 class="w2-03-detail-name" id="w2-03-detail-title">${escapeHTML(displayName(item))}</h3>
          <p class="w2-03-detail-meta">${escapeHTML(slotLabel(item.displaySlot || item.canonicalSlot))} · ${escapeHTML(rarityLabel(item.rarity))}</p>
          <span class="w2-03-detail-badge" data-kind="${equippable ? 'functional' : 'blocked'}">${escapeHTML(equippable ? text('功能裝備', 'Functional equipment') : text('不可裝備', 'Not equippable'))}</span>
        </div>
      </div>
      <dl class="w2-03-detail-grid">
        <div class="w2-03-detail-stat"><dt>${escapeHTML(text('持有數量', 'Owned quantity'))}</dt><dd>×${escapeHTML(item.ownedQuantity)}</dd></div>
        <div class="w2-03-detail-stat"><dt>${escapeHTML(text('目前狀態', 'Current state'))}</dt><dd>${escapeHTML(stateLabel)}</dd></div>
      </dl>
      <div class="w2-03-detail-section"><h4>${escapeHTML(text('效果 / Effects', 'Effects'))}</h4><ul class="w2-03-effect-list">${effectMarkup(item, 3)}</ul></div>
      ${replacementMarkup}
      ${conflictMarkup}
      ${control}
      <p class="w2-03-authority-note">${escapeHTML(text('持有與效果：server-owned player_inventory / EQUIPMENT_DEFS。操作：canonical Loadout API。選取本身不會自動裝備。', 'Ownership and effects: server-owned player_inventory / EQUIPMENT_DEFS. Mutations: canonical Loadout API. Selection never auto-equips.'))}</p>
    `;
  }

  function renderCapability(state) {
    const capability = state.root.querySelector('[data-w2-capability]');
    if (!capability) return;
    if (!state.snapshot) {
      capability.dataset.state = 'unknown';
      capability.textContent = text('檢查配裝權限…', 'Loadout checking…');
      return;
    }
    const enabled = state.snapshot.capability.loadoutEnabled;
    capability.dataset.state = enabled ? 'enabled' : 'disabled';
    capability.textContent = enabled
      ? text('Loadout · 已開啟', 'Loadout · enabled')
      : text('Loadout · 未開啟', 'Loadout · off');
  }

  function renderStatus(state) {
    const status = state.root.querySelector('[data-w2-status]');
    if (!status) return;
    status.dataset.state = state.statusState || '';
    status.textContent = state.statusMessage || '';
  }

  function renderImages(state) {
    state.root.querySelectorAll('[data-w2-image]').forEach((image) => {
      if (image.dataset.w2ImageBound === 'true') return;
      image.dataset.w2ImageBound = 'true';
      image.addEventListener('error', () => {
        image.hidden = true;
        const fallback = image.parentElement?.querySelector('[data-w2-image-fallback]');
        if (fallback) fallback.hidden = false;
      }, { once: true });
    });
  }

  function render(state) {
    if (state.destroyed) return;
    state.root.dataset.w2LoadoutCapability = state.snapshot?.capability.loadoutEnabled ? 'enabled' : 'disabled';
    state.root.dataset.w2ProjectionAuthority = 'server_owned_projection';
    state.root.setAttribute('aria-busy', String(Boolean(state.loading || state.mutating)));
    renderCapability(state);
    renderStatus(state);
    filterButtons(state);
    renderGrid(state);
    renderDetail(state);
    renderPaperDoll(state);
    renderImages(state);
  }

  async function fetchCanonicalSnapshot(fetchImpl) {
    const request = fetchImpl || global.fetch.bind(global);
    const responses = await Promise.all([
      request(API.inventory, { credentials: 'include', cache: 'no-store' }),
      request(API.capability, { credentials: 'include', cache: 'no-store' }),
      request(API.appearance, { credentials: 'include', cache: 'no-store' }),
    ]);
    if (!responses[0].ok) throw new Error(`inventory HTTP ${responses[0].status}`);
    const inventory = await responses[0].json();
    const capability = responses[1].ok ? await responses[1].json() : {};
    const appearance = responses[2].ok ? await responses[2].json() : {};
    return { inventory, capability, appearance };
  }

  async function postCanonicalMutation(item, action, fetchImpl) {
    const request = fetchImpl || global.fetch.bind(global);
    const response = await request(API.mutation, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ inv_id: item.invId, action }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || result.error) throw new Error(result.error || `mutation HTTP ${response.status}`);
    return result;
  }

  function create(root, options) {
    if (!root || root.nodeType !== 1) throw new TypeError('W2-03 equipment root is required');
    const opts = options && typeof options === 'object' ? options : {};
    ensureMarkup(root);
    const state = {
      root,
      snapshot: null,
      filter: 'all',
      selectedKey: '',
      loading: false,
      mutating: false,
      destroyed: false,
      statusState: '',
      statusMessage: '',
      requestToken: 0,
      paperDollToken: 0,
    };

    function selectItem(key) {
      if (!state.snapshot || !findSelected(state.snapshot, key)) return;
      state.selectedKey = key;
      render(state);
    }

    async function load(focus) {
      const token = ++state.requestToken;
      state.loading = true;
      state.statusState = 'loading';
      state.statusMessage = text('正在同步伺服器裝備狀態…', 'Syncing server equipment state…');
      render(state);
      try {
        const raw = typeof opts.snapshotLoader === 'function'
          ? await opts.snapshotLoader()
          : (opts.snapshot && !state.snapshot ? opts.snapshot : await fetchCanonicalSnapshot(opts.fetchImpl));
        if (token !== state.requestToken || state.destroyed) return state.snapshot;
        const next = normalizeSnapshot(raw);
        state.snapshot = next;
        const focusString = focus == null ? '' : String(focus);
        const focused = next.items.find((item) => String(item.invId) === focusString || item.itemId === focusString);
        if (focused) state.selectedKey = itemSelectionKey(focused);
        if (!findSelected(next, state.selectedKey)) {
          // Selecting the first card only opens its read-only detail panel;
          // it never invokes the equip endpoint or changes server state.
          const first = next.items.find((item) => item.owned);
          state.selectedKey = first ? itemSelectionKey(first) : '';
        }
        state.statusState = 'ready';
        state.statusMessage = text('裝備投影已從伺服器更新。', 'Equipment projection refreshed from the server.');
        return next;
      } catch (error) {
        if (token !== state.requestToken || state.destroyed) return state.snapshot;
        state.statusState = 'error';
        state.statusMessage = text('裝備投影暫時無法載入；未執行任何操作。', 'Equipment projection is unavailable; no action was performed.');
        if (!state.snapshot) state.snapshot = normalizeSnapshot({});
        return state.snapshot;
      } finally {
        if (token === state.requestToken && !state.destroyed) {
          state.loading = false;
          render(state);
        }
      }
    }

    async function performMutation(action) {
      const item = findSelected(state.snapshot, state.selectedKey);
      if (!item || state.mutating || !state.snapshot?.capability.loadoutEnabled) return;
      if (!item.canonicalEquippable || !item.invId || item.equippedConflict) return;
      state.mutating = true;
      state.statusState = 'loading';
      state.statusMessage = text('正在等待 canonical Loadout 回應…', 'Waiting for the canonical Loadout response…');
      render(state);
      try {
        if (typeof opts.mutator === 'function') {
          await opts.mutator({ item, action });
        } else {
          await postCanonicalMutation(item, action, opts.fetchImpl);
        }
        await load(item.invId);
        state.statusState = 'success';
        state.statusMessage = action === 'equip'
          ? text('已重新讀取裝備狀態；替換由伺服器決定。', 'Equipment state reloaded; replacement was decided by the server.')
          : text('已重新讀取卸下後的裝備狀態。', 'Unequipped state reloaded from the server.');
      } catch (error) {
        state.statusState = 'error';
        state.statusMessage = text('裝備操作未完成；伺服器狀態未在瀏覽器中偽造。', 'The equipment action did not complete; browser state was not fabricated.');
      } finally {
        state.mutating = false;
        render(state);
      }
    }

    function onClick(event) {
      const filter = event.target.closest('[data-w2-filter]');
      if (filter && state.root.contains(filter)) {
        state.filter = filter.dataset.w2Filter || 'all';
        render(state);
        return;
      }
      const card = event.target.closest('[data-w2-item-key]');
      if (card && state.root.contains(card)) {
        selectItem(card.dataset.w2ItemKey || '');
        return;
      }
      const mutation = event.target.closest('[data-w2-mutation]');
      if (mutation && state.root.contains(mutation)) {
        performMutation(mutation.dataset.w2Mutation || '');
      }
    }

    root.addEventListener('click', onClick);
    root.dataset.w2Mounted = 'true';
    render(state);

    const controller = {
      load,
      refresh: load,
      select: selectItem,
      render: () => render(state),
      getState: () => ({
        snapshot: state.snapshot,
        filter: state.filter,
        selectedKey: state.selectedKey,
        loading: state.loading,
        mutating: state.mutating,
      }),
      destroy() {
        if (state.destroyed) return;
        state.destroyed = true;
        state.requestToken += 1;
        state.paperDollToken += 1;
        root.removeEventListener('click', onClick);
        root.removeAttribute('aria-busy');
        root.removeAttribute('data-w2-mounted');
        root.innerHTML = '';
      },
    };
    return controller;
  }

  function mount(root, options) {
    const controller = create(root, options);
    if (!options || options.autoLoad !== false) {
      controller.load(options?.focus);
    }
    return controller;
  }

  global.GoOdysseyEquipmentLoadoutVisualSlice = Object.freeze({
    API,
    PAPER_DOLL_LAYER_COUNT,
    PAPER_DOLL_LAYER_ORDER,
    normalizeSnapshot,
    create,
    mount,
  });

  function boot() {
    document.querySelectorAll('[data-w2-03-equipment-slice]').forEach((root) => {
      if (root.dataset.w2Mounted === 'true' || root.hasAttribute('data-w2-03-no-auto-mount')) return;
      mount(root);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})(window);
