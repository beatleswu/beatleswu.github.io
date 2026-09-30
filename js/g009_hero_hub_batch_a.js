/*
 * G009 Hero Hub Batch A runtime presentation.
 *
 * Owner-locked visual authority: HERO_HUB_BATCH_A_OWNER_LOCK_RECEIPT.md.
 * V2 Future30 naming authority SHA-256:
 * 5C60C1A3FD60E45A83372CD6CB63FF758F2D209097AB1B933CBA22B7766AC70D
 *
 * This file is intentionally a presentation consumer. It reads the existing
 * server-owned Future30, equipment, Companion, and Honors projections and
 * delegates writes to the existing authoritative routes. It does not import
 * candidate Batch B/C art or the pending 84 derived identity renders.
 */
(function () {
  'use strict';

  const STARTER_KEYS = Object.freeze(['A1', 'R1', 'R2', 'R3', 'S2']);
  const COMPANION_KEYS = Object.freeze([
    'ink_drop_kelpie', 'whispering_void_kit', 'star_shell_hatchling',
    'starpath_antlerling', 'fatty', 'obsidian_bastion',
  ]);
  const TAB_ORDER = Object.freeze(['hero', 'equipment', 'appearance', 'pet', 'honors']);
  const TAB_COPY = Object.freeze({
    hero: {
      title: 'g009.hero.tab.character',
      subtitle: 'g009.hero.character.profileNote',
    },
    equipment: {
      title: 'g009.hero.tab.equipment',
      subtitle: 'g009.hero.equipment.note',
    },
    appearance: {
      title: 'g009.hero.tab.appearance',
      subtitle: 'g009.hero.appearance.title',
    },
    pet: {
      title: 'g009.hero.tab.companion',
      subtitle: 'g009.hero.companion.title',
    },
    honors: {
      title: 'g009.hero.tab.honors',
      subtitle: 'g009.hero.honors.title',
    },
  });

  // Exact Owner-approved player-facing V2 names. Runtime identity remains the
  // server character_key; these values are never used as identity keys.
  const FUTURE30_NAMES = Object.freeze({
    A1:  { zh: '洛恩・赤巾', en: 'Lorne Redscarf' },
    A3:  { zh: '博倫・赭衣', en: 'Boren Ochreclad' },
    V1:  { zh: '達恩・暮褐', en: 'Daren Duskmantle' },
    V2:  { zh: '卡洛・赤鬚', en: 'Karo Copperbeard' },
    V3:  { zh: '維爾・翠髮', en: 'Veyr Greenhair' },
    R1:  { zh: '奧倫・雪鬚赤冠', en: 'Oren Snowbeard' },
    R2:  { zh: '凱恩・赤金冠', en: 'Kaen Redgold' },
    R3:  { zh: '珊洛・緋披', en: 'Saro Scarletcape' },
    H1:  { zh: '赫倫・黯鐵', en: 'Heren Darkiron' },
    H2:  { zh: '諾爾・藍尖帽', en: 'Norl Bluepeak' },
    H3:  { zh: '伊文・蒼巾', en: 'Iven Palewrap' },
    K1:  { zh: '格嵐・鈕盔', en: 'Garan Knobhelm' },
    K2:  { zh: '洛克・炭甲', en: 'Rokk Charcoalplate' },
    K3:  { zh: '維斯・白金面甲', en: 'Vess Whitegold' },
    W1:  { zh: '奧斯・雪鬚藍冠', en: 'Ors Bluecrown' },
    W2:  { zh: '雷恩・赤兜', en: 'Raen Redhood' },
    W3:  { zh: '提倫・青兜', en: 'Teren Tealhood' },
    M1:  { zh: '莫爾・白骨', en: 'Mor Barebones' },
    M2:  { zh: '格羅・褐腰骨', en: 'Gro Brownwrap' },
    S1:  { zh: '索恩・金弧', en: 'Sorn Goldcurve' },
    S2:  { zh: '凱洛・黑髻', en: 'Kyro Blackknot' },
    F1:  { zh: '米菈・橄欖衣', en: 'Mira Oliveclad' },
    F2:  { zh: '菲恩・銅髮', en: 'Feyn Copperhair' },
    F3:  { zh: '艾菈・翠衣', en: 'Aira Greenclad' },
    AR1: { zh: '阿登・橙羽', en: 'Arden Orangeplume' },
    AR2: { zh: '凱爾・橙帶', en: 'Kael Ochrebelt' },
    AR3: { zh: '維恩・金額', en: 'Vaen Goldbrow' },
    E1:  { zh: '伊爾・綠帽', en: 'Eir Greencap' },
    E2:  { zh: '雷克・赤刺', en: 'Rek Redspike' },
    E3:  { zh: '希恩・青刺', en: 'Sien Cyanspike' },
  });

  const state = {
    appearance: null,
    catalog: null,
    inventory: null,
    pet: null,
    initialized: false,
    refreshing: null,
    generation: 0,
    selectionInFlight: false,
  };

  function root() {
    return document.getElementById('g009-hero-hub');
  }

  function esc(value) {
    if (typeof escapeHTML === 'function') return escapeHTML(value);
    return String(value ?? '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch]));
  }

  function en() {
    return typeof I18n !== 'undefined' && I18n.getLang && I18n.getLang() === 'en';
  }

  function tx(key, fallback) {
    if (typeof I18n !== 'undefined' && I18n.t) {
      const value = I18n.t(key);
      return value === key ? fallback : value;
    }
    return fallback;
  }

  function legacyValue(name) {
    try {
      return typeof window[name] !== 'undefined' ? window[name] : undefined;
    } catch (_) {
      return undefined;
    }
  }

  function lexicalValue(name) {
    // Top-level classic-script let bindings are intentionally read through
    // guarded direct references. This keeps the existing runtime as the data
    // authority without publishing a second state store.
    try {
      if (name === '_future30CharacterCatalog' && typeof _future30CharacterCatalog !== 'undefined') return _future30CharacterCatalog;
      if (name === '_future30CharacterCatalogState' && typeof _future30CharacterCatalogState !== 'undefined') return _future30CharacterCatalogState;
      if (name === '_characterAuthorityKey' && typeof _characterAuthorityKey !== 'undefined') return _characterAuthorityKey;
      if (name === '_functionalEquipmentItems' && typeof _functionalEquipmentItems !== 'undefined') return _functionalEquipmentItems;
      if (name === '_petState' && typeof _petState !== 'undefined') return _petState;
    } catch (_) {}
    return undefined;
  }

  function safeAssetPath(value) {
    return typeof value === 'string'
      && value.startsWith('/assets/')
      && !value.includes('..')
      && !value.includes('\\')
      ? value
      : '';
  }

  function currentCatalog() {
    return state.catalog || lexicalValue('_future30CharacterCatalog') || null;
  }

  function currentPet() {
    return state.pet || lexicalValue('_petState') || null;
  }

  function activeCharacterKey() {
    const appearanceKey = state.appearance?.character_key;
    if (typeof appearanceKey === 'string' && appearanceKey.trim()) return appearanceKey;
    const runtimeKey = lexicalValue('_characterAuthorityKey');
    if (typeof runtimeKey === 'string' && runtimeKey.trim()) return runtimeKey;
    const applied = currentCatalog()?.applied_character_key;
    return typeof applied === 'string' && applied.trim() ? applied : null;
  }

  function catalogEntry(key) {
    return (currentCatalog()?.entries || []).find(entry => entry?.character_key === key) || null;
  }

  function future30Name(key, entry) {
    const identity = FUTURE30_NAMES[String(key || '')];
    if (identity) return en() ? identity.en : identity.zh;
    const raw = en()
      ? (entry?.display_name_en || entry?.display_name || entry?.name_en || entry?.name)
      : (entry?.display_name || entry?.name || entry?.display_name_en || entry?.name_en);
    if (typeof raw === 'string' && raw.trim() && raw.trim().toUpperCase() !== String(key || '').toUpperCase()) {
      return raw.trim();
    }
    return en() ? 'Future30 character' : 'Future30 角色';
  }

  function petName(pet) {
    if (!pet) return en() ? 'Companion' : '夥伴';
    if (pet.nickname) return pet.nickname;
    return en() ? (pet.name_en || pet.name || 'Companion') : (pet.name || pet.name_en || '夥伴');
  }

  function petImage(pet) {
    if (!pet) return '';
    try {
      if (typeof petAnimatedImage === 'function') {
        const animated = safeAssetPath(petAnimatedImage(pet));
        if (animated) return animated;
      }
    } catch (_) {}
    const level = Number(pet.level) || 1;
    const stage = level >= 25 ? 3 : level >= 10 ? 2 : 1;
    return safeAssetPath(pet.image)
      || safeAssetPath(pet.images?.[stage])
      || safeAssetPath(pet.images?.[1]);
  }

  function stageNumber(level) {
    const n = Number(level);
    if (!Number.isFinite(n)) return null;
    return n >= 25 ? 3 : n >= 10 ? 2 : 1;
  }

  function stageLabel(pet) {
    if (!pet) return '';
    const level = Number(pet.level);
    const stage = stageNumber(level);
    if (pet.stage_label) return pet.stage_label;
    if (!stage) return '';
    return tx('g009.hero.companion.stage', en() ? 'Stage {n}' : '第 {n} 階段').replace('{n}', String(stage));
  }

  async function readJSON(url, options = {}) {
    const response = await fetch(url, {
      credentials: 'include', cache: 'no-store', ...options,
    });
    if (!response.ok) throw new Error(`${url} HTTP ${response.status}`);
    return response.json();
  }

  function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value == null || value === '' ? '—' : String(value);
  }

  function renderTab(tab) {
    const canonical = TAB_ORDER.includes(tab) ? tab : 'hero';
    const buttons = [...document.querySelectorAll('[data-g009-hub-tab]')];
    buttons.forEach(button => {
      const active = button.dataset.g009HubTab === canonical;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', String(active));
      button.tabIndex = active ? 0 : -1;
    });
    document.querySelectorAll('[data-g009-panel]').forEach(panel => {
      panel.hidden = panel.dataset.g009Panel !== canonical;
    });
    document.body.dataset.g009HeroTab = canonical;
    const copy = TAB_COPY[canonical];
    const title = document.getElementById('g009-panel-title');
    const subtitle = document.getElementById('g009-panel-subtitle');
    if (title) title.textContent = tx(copy.title, canonical);
    if (subtitle) subtitle.textContent = tx(copy.subtitle, '');
  }

  function navigate(tab) {
    if (typeof selectHeroTab === 'function') {
      selectHeroTab(tab, true);
    } else {
      renderTab(tab);
    }
  }

  function installTabBridge() {
    if (typeof selectHeroTab === 'function' && !selectHeroTab.__g009BatchA) {
      const original = selectHeroTab;
      const bridged = function (tab, push) {
        original(tab, push);
        renderTab(tab);
        if (tab === 'pet') void refreshRuntime();
        if (tab === 'honors' && typeof loadBadgesTab === 'function') void loadBadgesTab();
      };
      bridged.__g009BatchA = true;
      selectHeroTab = bridged;
    }

    document.querySelectorAll('[data-g009-hub-tab]').forEach(button => {
      button.addEventListener('click', () => navigate(button.dataset.g009HubTab));
    });
    document.querySelectorAll('[data-g009-go-tab]').forEach(button => {
      button.addEventListener('click', () => navigate(button.dataset.g009GoTab));
    });
    document.getElementById('g009-hero-subnav')?.addEventListener('keydown', event => {
      if (!['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
      const buttons = [...document.querySelectorAll('[data-g009-hub-tab]')];
      const current = buttons.indexOf(document.activeElement);
      if (current < 0) return;
      event.preventDefault();
      let next = current;
      if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = buttons.length - 1;
      else if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (current + 1) % buttons.length;
      else next = (current - 1 + buttons.length) % buttons.length;
      navigate(buttons[next].dataset.g009HubTab);
      buttons[next].focus();
    });
  }

  function relocateLegacyRuntimeNodes() {
    const move = (id, targetId) => {
      const element = document.getElementById(id);
      const target = document.getElementById(targetId);
      if (element && target && !target.contains(element)) target.appendChild(element);
    };
    move('hero-badge-filters', 'g009-honors-filter-slot');
    move('hero-badge-count', 'g009-honors-count-slot');
    move('hero-badge-grid', 'g009-honors-grid-slot');
    move('slot-title', 'g009-title-grid-slot');

    const titleFilter = document.querySelector('.filter-tabs[data-slot="title"]');
    const titleTarget = document.getElementById('g009-title-filter-slot');
    if (titleFilter && titleTarget && !titleTarget.contains(titleFilter)) titleTarget.appendChild(titleFilter);

    const avatar = document.getElementById('char-avatar');
    const stageHost = document.getElementById('g009-stage-host');
    if (avatar && stageHost && !stageHost.contains(avatar)) {
      stageHost.appendChild(avatar);
      avatar.removeAttribute('aria-hidden');
      avatar.dataset.g009BatchAStage = 'shared-runtime-host';
    }
    document.getElementById('g008-future30-hero-stage')?.removeAttribute('aria-hidden');
  }

  function renderCharacter() {
    const key = activeCharacterKey();
    const entry = catalogEntry(key);
    const name = future30Name(key, entry);
    const profileName = document.getElementById('char-name')?.textContent
      || document.getElementById('username-display')?.textContent
      || '—';
    setText('g009-player-display-name', profileName);
    setText('g009-character-display-name', key ? name : tx('g009.hero.character.noSelection', 'Future30 selection is loading.'));
    setText('g009-character-card-name', key ? name : tx('g009.hero.character.noSelection', 'Future30 selection is loading.'));
    const companion = currentPet()?.pet;
    setText('g009-character-companion-summary', companion ? petName(companion) : tx('g009.hero.companion.none', 'No active companion.'));
    const items = Array.isArray(state.inventory)
      ? state.inventory.filter(item => item && item.equipped === true)
      : [];
    const equipmentNames = items.map(equipmentName).filter(Boolean);
    setText('g009-character-equipment-summary', equipmentNames.length
      ? equipmentNames.slice(0, 2).join(' · ')
      : tx('g009.hero.equipment.empty', 'No server-owned equipment is equipped.'));
  }

  function equipmentName(item) {
    const raw = en()
      ? (item?.display_name_en || item?.name_en || item?.display_name || item?.name)
      : (item?.display_name || item?.name || item?.display_name_en || item?.name_en);
    return typeof raw === 'string' && raw.trim() ? raw.trim() : '';
  }

  function equipmentSlotLabel(item) {
    const slot = String(item?.slot || '').toLowerCase();
    const labels = en()
      ? { weapon: 'Main hand', offhand: 'Off hand', armor: 'Armor', cape: 'Back', hat: 'Head', accessory: 'Accessory', aura: 'Aura' }
      : { weapon: '主手', offhand: '副手', armor: '防具', cape: '背部', hat: '頭部', accessory: '配飾', aura: '光環' };
    return labels[slot] || (en() ? 'Equipment' : '裝備');
  }

  function renderEquipment() {
    const list = document.getElementById('g009-equipment-list');
    if (!list) return;
    const inventory = Array.isArray(state.inventory) ? state.inventory : null;
    if (!inventory) {
      list.innerHTML = `<div class="g009-loading">${esc(tx('g009.hero.equipment.unavailable', 'Equipment presentation is temporarily unavailable.'))}</div>`;
      return;
    }
    const equipped = inventory.filter(item => item && item.equipped === true);
    if (!equipped.length) {
      list.innerHTML = `<div class="g009-loading">${esc(tx('g009.hero.equipment.empty', 'No server-owned equipment is equipped.'))}</div>`;
      return;
    }
    list.innerHTML = equipped.map(item => {
      const icon = safeAssetPath(item.icon || item.art);
      const iconHTML = icon
        ? `<img src="${esc(icon)}" alt="" loading="lazy" decoding="async">`
        : (String(item.slot || '').toLowerCase() === 'offhand' ? '◇' : '◆');
      return `<article class="g009-slot-row" data-equipment-item="${esc(item.item_id || item.id || '')}">
        <span class="g009-slot-icon" aria-hidden="true">${iconHTML}</span>
        <span class="g009-slot-copy"><span>${esc(equipmentSlotLabel(item))}</span><strong>${esc(equipmentName(item) || (en() ? 'Equipment' : '裝備'))}</strong></span>
        <span class="g009-owned-chip">${esc(tx('g009.hero.equipment.serverOwned', 'Server-owned'))}</span>
      </article>`;
    }).join('');
  }

  function renderAppearance() {
    const grid = document.getElementById('g009-character-switch-grid');
    if (!grid) return;
    const catalog = currentCatalog();
    const entries = Array.isArray(catalog?.entries)
      ? catalog.entries.filter(entry => entry && entry.owned === true)
      : [];
    if (!entries.length) {
      grid.innerHTML = `<div class="g009-loading">${esc(tx('g009.hero.appearance.unavailable', 'Future30 character selection is temporarily unavailable.'))}</div>`;
      return;
    }
    const active = activeCharacterKey();
    grid.innerHTML = entries.map(entry => {
      const key = String(entry.character_key || '');
      const isActive = key === active || entry.is_applied === true || key === catalog.applied_character_key;
      return `<button type="button" class="g009-character-switch${isActive ? ' is-active' : ''}"
        data-g009-character-key="${esc(key)}" aria-pressed="${String(isActive)}">
        <span class="g009-character-switch-mark" aria-hidden="true">✦</span>
        <span class="g009-character-switch-name">${esc(future30Name(key, entry))}</span>
        ${isActive ? `<span class="g009-character-switch-state">${esc(tx('g009.hero.appearance.active', 'Active'))}</span>` : ''}
      </button>`;
    }).join('');
    grid.querySelectorAll('[data-g009-character-key]').forEach(button => {
      button.addEventListener('click', () => selectCharacter(button.dataset.g009CharacterKey));
    });
  }

  async function selectCharacter(key) {
    if (state.selectionInFlight || !key) return;
    const entry = (currentCatalog()?.entries || []).find(item => item?.character_key === key && item.owned === true);
    if (!entry) return;
    state.selectionInFlight = true;
    document.querySelectorAll('[data-g009-character-key]').forEach(button => { button.disabled = true; });
    try {
      const response = await fetch('/api/skills/character', {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ character_key: key }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || result.error || result.rejected?.includes?.('character')) {
        throw new Error(result.error || 'Future30 character selection rejected');
      }
      if (typeof showToast === 'function') showToast(en() ? 'Future30 character applied.' : 'Future30 角色已套用。');
      if (typeof refreshAuthoritativeHeroPresentation === 'function') await refreshAuthoritativeHeroPresentation();
      state.appearance = null;
      state.catalog = null;
      await refreshRuntime();
    } catch (error) {
      if (typeof showToast === 'function') showToast(error instanceof Error ? error.message : (en() ? 'Selection failed.' : '角色切換失敗。'));
      renderAppearance();
    } finally {
      state.selectionInFlight = false;
    }
  }

  function renderCompanion() {
    const activeRoot = document.getElementById('g009-companion-active');
    const rosterRoot = document.getElementById('g009-companion-roster');
    if (!activeRoot || !rosterRoot) return;
    const snapshot = currentPet();
    const pet = snapshot?.pet;
    if (!snapshot) {
      activeRoot.innerHTML = `<div class="g009-loading">${esc(tx('g009.hero.companion.loading', 'Loading companion data…'))}</div>`;
      rosterRoot.replaceChildren();
      return;
    }
    if (!pet) {
      activeRoot.innerHTML = `<div class="g009-loading">${esc(tx('g009.hero.companion.none', 'No active companion.'))}</div>`;
    } else {
      const image = petImage(pet);
      const imageHTML = image ? `<img src="${esc(image)}" alt="" loading="lazy" decoding="async">` : '♧';
      const stage = stageLabel(pet);
      activeRoot.innerHTML = `<div class="g009-companion-card" data-pet-key="${esc(pet.pet_key || '')}">
        <span class="g009-companion-art" aria-hidden="true">${imageHTML}</span>
        <span class="g009-companion-copy">
          <strong>${esc(petName(pet))}</strong>
          <span>${esc(stage || (en() ? 'Server level' : '伺服器等級'))} · ${esc(tx('g009.hero.companion.withYou', 'With you'))}</span>
        </span>
      </div>`;
    }
    const catalog = Array.isArray(snapshot.catalog) ? snapshot.catalog : [];
    const entries = catalog.filter(item => item && COMPANION_KEYS.includes(item.key || item.pet_key));
    rosterRoot.innerHTML = entries.map(item => {
      const key = item.key || item.pet_key;
      const isActive = pet?.pet_key === key;
      const image = petImage(item);
      const imageHTML = image ? `<img src="${esc(image)}" alt="" loading="lazy" decoding="async">` : '♧';
      return `<div class="g009-companion-tile${isActive ? ' is-active' : ''}" data-pet-key="${esc(key)}">
        ${imageHTML}<strong>${esc(petName(item))}</strong>${isActive ? `<span>${esc(tx('g009.hero.companion.withYou', 'With you'))}</span>` : ''}
      </div>`;
    }).join('');
  }

  function renderAll() {
    renderCharacter();
    renderEquipment();
    renderAppearance();
    renderCompanion();
  }

  async function refreshRuntime() {
    if (state.refreshing) return state.refreshing;
    const token = ++state.generation;
    state.refreshing = (async () => {
      const catalogFromLegacy = lexicalValue('_future30CharacterCatalog');
      const catalogState = lexicalValue('_future30CharacterCatalogState');
      const inventoryFromLegacy = lexicalValue('_functionalEquipmentItems');
      const petFromLegacy = lexicalValue('_petState');
      const inventoryJob = state.inventory
        ? Promise.resolve(state.inventory)
        : readJSON('/api/player/inventory').catch(() => (
          Array.isArray(inventoryFromLegacy) && inventoryFromLegacy.length
            ? inventoryFromLegacy
            : null
        ));
      const jobs = [
        state.appearance ? Promise.resolve(state.appearance) : readJSON('/api/player/appearance').catch(() => null),
        state.catalog || (catalogState === 'ready' ? Promise.resolve(catalogFromLegacy) : readJSON('/api/player/character-catalog').catch(() => null)),
        inventoryJob,
        state.pet || (petFromLegacy ? Promise.resolve(petFromLegacy) : readJSON('/api/pet/status').catch(() => null)),
      ];
      const [appearance, catalog, inventory, pet] = await Promise.all(jobs);
      if (token !== state.generation) return;
      if (appearance) state.appearance = appearance;
      if (catalog) state.catalog = catalog;
      if (Array.isArray(inventory)) state.inventory = inventory;
      if (pet) state.pet = pet;
      renderAll();
    })().finally(() => {
      state.refreshing = null;
    });
    return state.refreshing;
  }

  function installRuntimeSignals() {
    window.addEventListener('g009:companion-status', () => {
      const pet = lexicalValue('_petState');
      if (pet) state.pet = pet;
      renderCompanion();
      renderCharacter();
    });
    document.addEventListener('e9:i18n-changed', () => {
      renderTab(document.body.dataset.heroTab || 'hero');
      renderAll();
    });
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) {
        state.appearance = null;
        state.catalog = null;
        state.pet = null;
        void refreshRuntime();
      }
    });
  }

  function initialize() {
    if (state.initialized || !root()) return;
    state.initialized = true;
    relocateLegacyRuntimeNodes();
    installTabBridge();
    installRuntimeSignals();
    if (typeof I18n !== 'undefined' && I18n.apply) I18n.apply();
    const requested = new URLSearchParams(location.search).get('tab');
    renderTab(requested === 'gear' ? 'equipment' : requested === 'class' ? 'hero' : requested === 'badges' ? 'honors' : requested || document.body.dataset.heroTab || 'hero');
    void refreshRuntime();
    // The existing Hero bootstrap resolves profile/Future30 state asynchronously.
    // These bounded refreshes only mirror that state; they never become authority.
    [350, 1200, 2600].forEach(delay => setTimeout(() => void refreshRuntime(), delay));
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
  else initialize();
})();
